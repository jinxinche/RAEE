"""No-follow, bounded, atomic writes for untrusted working trees."""
from __future__ import annotations
import os
import json
import tempfile
import stat
import math
import errno
import time
from contextlib import contextmanager
from pathlib import Path

MAX_STORED_JSON = 16_000_000


def _reject_links(path: Path):
    # Reject symlink in the output parent chain; root is allowed to be a normal
    # resolved working directory. Path traversal is not allowed by callers.
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError('Refusing symlink path for evidence IO')


def _try_lock(fd: int) -> None:
    if os.name == 'nt':
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fd: int) -> None:
    if os.name == 'nt':
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def exclusive_lock(path: Path, *, timeout: float = 5.0):
    """Serialize cooperating local writers using a permanent, regular lockfile.

    Never unlink or replace this file, including on timeout or failure: waiters
    must continue to lock the same inode. Filesystem lock support is required;
    this does not isolate callers from a hostile filesystem owner.
    """
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or
            not 0 <= timeout <= 60 or not math.isfinite(timeout)):
        raise ValueError('Lock timeout must be finite and between 0 and 60 seconds')
    path = Path(path)
    _reject_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_links(path)
    try:
        before = path.lstat()
    except FileNotFoundError:
        before = None
    if before is not None and (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1):
        raise ValueError('Lockfile must be a single-link regular file')
    flags = (os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0) |
             getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0))
    fd = os.open(path, flags, 0o600)
    acquired = False
    try:
        opened = os.fstat(fd)

        def check_identity():
            _reject_links(path)
            current = path.lstat()
            if (not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(current.st_mode) or
                    opened.st_nlink != 1 or current.st_nlink != 1 or
                    (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino) or
                    (before is not None and
                     (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino))):
                raise ValueError('Lockfile changed while opening or waiting')

        check_identity()
        deadline = time.monotonic() + timeout
        while True:
            try:
                _try_lock(fd)
                acquired = True
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK, errno.EINTR):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Timed out waiting for evidence lock') from exc
                time.sleep(min(0.01, remaining))
        check_identity()
        # Windows byte-range locks may extend past EOF. Initialize only after
        # locking, avoiding competing writes to an already locked first byte.
        if os.fstat(fd).st_size == 0:
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, b'\0')
        yield
    finally:
        try:
            if acquired:
                _unlock(fd)
        finally:
            os.close(fd)


def bounded_walk(root: Path, *, max_entries: int, max_directories: int,
                 exclude_dirs=()):
    """Yield sorted directory inventories with limits applied before filtering.

    Only real directories are traversed; symlinks remain file entries. The root
    counts as one directory, and excluded directories still consume the budget.
    Both pending paths and each scandir allocation share the global entry cap.
    """
    pending = [Path(root)]
    entries_seen, directories_seen = 0, 1
    if max_entries < 0 or max_directories < 1:
        raise ValueError('Invalid traversal budget')
    while pending:
        folder = pending.pop()
        directories, files = [], []
        try:
            _reject_links(folder)
            if not stat.S_ISDIR(folder.lstat().st_mode):
                raise ValueError('Traversal requires a regular directory')
            with os.scandir(folder) as entries:
                for entry in entries:
                    entries_seen += 1
                    if entries_seen > max_entries:
                        raise ValueError('Source traversal exceeds entry budget')
                    if entry.is_dir(follow_symlinks=False):
                        directories_seen += 1
                        if directories_seen > max_directories:
                            raise ValueError('Source traversal exceeds directory budget')
                        directories.append(entry.name)
                    else:
                        files.append(entry.name)
            _reject_links(folder)
        except OSError as exc:
            raise ValueError('Source traversal refused unreadable directory') from exc
        directories.sort()
        files.sort()
        yield folder, directories, files
        pending.extend(folder / name for name in reversed(directories)
                       if name not in exclude_dirs)


@contextmanager
def open_regular_read(path: Path, limit: int):
    """Open a bounded regular file without following a linked path.

    Refuse FIFO/device inputs before opening, and detect common replacement
    races. This is not isolation from a hostile concurrent filesystem owner.
    """
    path = Path(path)
    _reject_links(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise ValueError('Input must be a bounded regular file')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
    fd = os.open(path, flags)
    try:
        after = os.fstat(fd)
        if (not stat.S_ISREG(after.st_mode) or after.st_size > limit or
                (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)):
            raise ValueError('Input changed while opening')
        _reject_links(path)
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            yield stream
    finally:
        os.close(fd)


def read_bytes(path: Path, limit: int) -> bytes:
    with open_regular_read(path, limit) as stream:
        before = os.fstat(stream.fileno())
        # Size against this opened regular file, not the usually much larger
        # configured cap. Read one extra byte to detect growth without reserving
        # a multi-megabyte buffer for every tiny metadata document.
        value = stream.read(min(limit, before.st_size) + 1)
        after = os.fstat(stream.fileno())
        if len(value) > limit:
            raise ValueError('Input exceeds byte limit')
        if (len(value) != before.st_size or
                (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError('Input changed while reading')
    _reject_links(Path(path))
    return value


def strict_json_loads(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate JSON field')
            value[key] = item
        return value

    def invalid_constant(value):
        raise ValueError('Non-finite JSON number')

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('Non-finite JSON number')
        return number

    def validate_strings(value):
        if isinstance(value, str):
            value.encode('utf-8', errors='strict')
        elif isinstance(value, dict):
            for key, item in value.items():
                validate_strings(key)
                validate_strings(item)
        elif isinstance(value, list):
            for item in value:
                validate_strings(item)

    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode('utf-8', errors='strict')
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant,
                           parse_float=finite_float)
        validate_strings(value)
        return value
    except (UnicodeError, RecursionError) as exc:
        raise ValueError('Invalid JSON encoding or nesting') from exc


def safe_read_json(path: Path, default=None):
    try:
        raw = read_bytes(path, MAX_STORED_JSON)
    except FileNotFoundError:
        return default
    return strict_json_loads(raw)


def write_text(path: Path, content: str) -> None:
    _reject_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_links(path)
    name = None
    try:
        fd, name = tempfile.mkstemp(prefix='.raee-tmp-', dir=path.parent)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        _reject_links(path)
        os.replace(name, path)
        name = None
    finally:
        if name is not None:
            try:
                os.unlink(name)
            except FileNotFoundError:
                pass


def write_json(path: Path, obj) -> None:
    # Stop traversing oversized collections while encoding, including the
    # final newline in the budget before any filesystem changes.
    encoder = json.JSONEncoder(indent=2, ensure_ascii=False, allow_nan=False)
    chunks, size = [], 1
    try:
        for chunk in encoder.iterencode(obj):
            size += len(chunk.encode('utf-8'))
            if size > MAX_STORED_JSON:
                raise ValueError('Evidence JSON exceeds byte limit')
            chunks.append(chunk)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError('Invalid JSON encoding or nesting') from exc
    content = ''.join(chunks) + '\n'
    # Python permits keys such as 1 and '1' in one dict, but both serialize as
    # '1'. Never replace a shared document with JSON our reader will reject.
    strict_json_loads(content)
    write_text(path, content)
