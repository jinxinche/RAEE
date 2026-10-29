"""Explicitly opted-in process execution with bounded retained output.

This is not a sandbox. Run untrusted commands only in disposable, restricted VMs.
"""
from __future__ import annotations
import os
import signal
import subprocess
import time

MAX_TIMEOUT = 3600


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
