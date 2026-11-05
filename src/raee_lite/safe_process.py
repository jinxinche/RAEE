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


def capture_bounded(command, cwd, *, limit=250_000, timeout=15):
    """Bound trusted metadata output and the wait for both process exit and EOF.

    Abnormal exits kill the POSIX process group, including inherited pipe writers.
    On Windows only the direct child is killed: descendants may survive and keep
    the daemon reader alive until they close stdout. This is not containment.
    """
    if (not isinstance(limit, int) or isinstance(limit, bool) or
            not 1 <= limit <= 8_000_000 or not 0 < timeout <= MAX_TIMEOUT):
        raise ValueError('Invalid capture budget')
    deadline = time.monotonic() + timeout
    options = {'start_new_session': True} if os.name == 'posix' else {}
    proc = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **options)
    output, failures = [], []
    reader = None
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

    try:
        reader = threading.Thread(target=consume, daemon=True)
        reader.start()
        proc.wait(timeout=max(0, deadline - time.monotonic()))
        reader.join(timeout=max(0, deadline - time.monotonic()))
        if reader.is_alive():
            raise subprocess.TimeoutExpired(command, timeout)
        if failures:
            raise ValueError('Unable to complete bounded command output') from failures[0]
        raw = output[0] if output else b''
        result = proc.returncode, raw[:limit], len(raw) > limit
        completed = True
        return result
    finally:
        try:
            if not completed:
                stop()
        finally:
            try:
                # Reap even after KeyboardInterrupt or failure to start a reader.
                proc.wait(timeout=1)
            finally:
                if reader is not None and reader.ident is not None:
                    reader.join(timeout=1)
                if reader is None or not reader.is_alive():
                    proc.stdout.close()


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
             r'^filter\..*\.(clean|process|required)$'], cwd)
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
    if not command or not 1 <= timeout <= MAX_TIMEOUT:
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
    try:
        code = proc.wait(timeout=timeout)
        return code, None, round(time.monotonic() - start, 2)
    except subprocess.TimeoutExpired:
        try:
            if os.name == 'posix':
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()  # Windows descendants may survive; not a security boundary
        except (ProcessLookupError, PermissionError):
            proc.kill()
        proc.wait()
        return 124, 'TimeoutExpired', round(time.monotonic() - start, 2)
