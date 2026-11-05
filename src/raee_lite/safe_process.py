"""Explicitly opted-in process execution with bounded retained output.

This is not a sandbox. Run untrusted commands only in disposable, restricted VMs.
"""
from __future__ import annotations
import os
import signal
import subprocess
import time
import threading

MAX_TIMEOUT = 3600


def capture_bounded(command, cwd, *, limit=250_000, timeout=15, reject_stderr=False):
    """Bound trusted metadata output and the wait for both process exit and EOF.

    Abnormal exits kill the POSIX process group, including inherited pipe writers.
    With reject_stderr, the first stderr byte aborts capture with ValueError;
    stderr is never accumulated or included in the error. Otherwise it is ignored.
    On Windows only the direct child is killed: descendants may survive and keep
    daemon readers alive until they close the inherited pipes. This is not
    containment, and process creation itself cannot be interrupted by the deadline.
    """
    if (not isinstance(limit, int) or isinstance(limit, bool) or
            not 1 <= limit <= 8_000_000 or
            not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or
            not 0 < timeout <= MAX_TIMEOUT):
        raise ValueError('Invalid capture budget')
    deadline = time.monotonic() + timeout
    options = {'start_new_session': True} if os.name == 'posix' else {}
    proc = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE if reject_stderr else subprocess.DEVNULL,
                            **options)
    output, failures = [], []
    readers = []
    stderr_seen = threading.Event()
    timeout_error = None
    completed = False

    def stop():
        try:
            if os.name == 'posix':
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except ProcessLookupError:
            pass
        except PermissionError:
            proc.kill()

    def consume():
        try:
            output.append(proc.stdout.read(limit + 1))
            if len(output[0]) > limit:
                stop()
        except Exception as exc:
            failures.append(exc)
            stop()
        finally:
            # The reader owns closure: closing a BufferedReader from another
            # thread can block indefinitely on its read lock (notably Windows).
            proc.stdout.close()

    def inspect_stderr():
        try:
            # Read only one byte: waiting for a larger buffer or EOF can delay
            # rejection indefinitely when a warning is followed by a stalled child.
            if proc.stderr.read(1):
                stderr_seen.set()
                stop()
        except Exception as exc:
            failures.append(exc)
            stop()
        finally:
            proc.stderr.close()

    try:
        streams = [(proc.stdout, consume)]
        if reject_stderr:
            streams.append((proc.stderr, inspect_stderr))
        for stream, target in streams:
            reader = threading.Thread(target=target, daemon=True)
            readers.append((stream, reader))
            reader.start()
        proc.wait(timeout=max(0, deadline - time.monotonic()))
        for _, reader in readers:
            reader.join(timeout=max(0, deadline - time.monotonic()))
            if reader.is_alive():
                raise subprocess.TimeoutExpired(command, timeout)
        completed = True
    except subprocess.TimeoutExpired as exc:
        timeout_error = exc
    finally:
        try:
            if not completed:
                stop()
        finally:
            try:
                # Reap even after KeyboardInterrupt or failure to start a reader.
                proc.wait(timeout=1)
            finally:
                cleanup_deadline = time.monotonic() + 1
                for _, reader in readers:
                    if reader.ident is not None:
                        reader.join(timeout=max(0, cleanup_deadline - time.monotonic()))
                for stream in (proc.stdout, proc.stderr):
                    if stream is not None and not any(
                            owned is stream and reader.is_alive() for owned, reader in readers):
                        stream.close()
    # Cleanup may observe stderr after a timeout, so check it before reporting
    # the timeout. No successful/truncated result can conceal observed stderr.
    if stderr_seen.is_set():
        raise ValueError('Command emitted stderr')
    if timeout_error is not None:
        raise timeout_error
    if failures:
        raise ValueError('Unable to complete bounded command output') from failures[0]
    raw = output[0] if output else b''
    return proc.returncode, raw[:limit], len(raw) > limit


def git_metadata_command(command, cwd):
    """Disable every configured filter, or return None if enumeration is unsafe.

    Config lookup is trusted metadata only; includes and command/environment
    overrides are read without invoking any configured clean/process command.
    A failed, malformed or truncated lookup is unavailable, never permission to
    proceed with status/diff. Enumerated drivers have clean/process cleared and
    required=false, so harmless global definitions (such as LFS) remain usable.
    """
    try:
        code, raw, truncated = capture_bounded(
            [*command, 'config', '--includes', '--null', '--name-only', '--get-regexp',
             r'^filter\..*\.(clean|process|required)$'], cwd, reject_stderr=True)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    if truncated or code not in (0, 1):
        return None
    if code == 1:
        return None if raw else list(command)
    if not raw or not raw.endswith(b'\x00'):
        return None
    drivers = set()
    try:
        for key in raw[:-1].split(b'\x00'):
            section, separator, setting = key.rpartition(b'.')
            if (not separator or not section.startswith(b'filter.') or
                    len(section) <= len(b'filter.') or
                    b'=' in section or
                    setting not in (b'clean', b'process', b'required')):
                return None
            drivers.add(section.decode('utf-8'))
    except UnicodeError:
        return None
    result = list(command)
    for driver in sorted(drivers):
        result.extend(['-c', driver + '.clean=', '-c', driver + '.process=',
                       '-c', driver + '.required=false'])
    return result


def run(command, cwd, timeout=120, env=None):
    """Discard command output and reap the direct child on abnormal waits.

    Process creation consumes the budget but cannot itself be interrupted.
    Killing a Windows child does not terminate or isolate its descendants.
    """
    if (not command or not isinstance(timeout, (int, float)) or
            isinstance(timeout, bool) or not 1 <= timeout <= MAX_TIMEOUT):
        raise ValueError('Command required; timeout must be between 1 and 3600 seconds')
    start = time.monotonic()
    # Never capture untrusted stdout/stderr in process memory or persist secrets.
    params = {'cwd': cwd, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL,
              'stdin': subprocess.DEVNULL, 'env': env}
    if os.name == 'posix':
        params['start_new_session'] = True
    else:
        params['creationflags'] = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    try:
        proc = subprocess.Popen(list(command), **params)
    except (FileNotFoundError, PermissionError) as ex:
        return 127, type(ex).__name__, round(time.monotonic() - start, 2)
    completed = False
    error = None
    try:
        remaining = start + timeout - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, timeout)
        code = proc.wait(timeout=remaining)
        completed = True
    except subprocess.TimeoutExpired:
        code, error = 124, 'TimeoutExpired'
    finally:
        if not completed:
            try:
                try:
                    if os.name == 'posix':
                        os.killpg(proc.pid, signal.SIGKILL)
                    else:
                        proc.kill()
                except ProcessLookupError:
                    pass
                except PermissionError:
                    proc.kill()
            finally:
                proc.wait(timeout=1)
    return code, error, round(time.monotonic() - start, 2)
