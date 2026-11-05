"""No-follow, bounded, atomic writes for untrusted working trees."""
from __future__ import annotations
import os
import json
import tempfile
from pathlib import Path

MAX_STORED_JSON = 16_000_000


def _reject_links(path: Path):
    # Reject symlink in the output parent chain; root is allowed to be a normal
    # resolved working directory. Path traversal is not allowed by callers.
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError('Refusing symlink path for evidence IO')


def safe_read_json(path: Path, default=None):
    _reject_links(path)
    if not path.exists():
        return default
    if path.stat().st_size > MAX_STORED_JSON:
        raise ValueError('Evidence JSON exceeds 16 MB limit')
    return json.loads(path.read_text(encoding='utf-8'))


def write_text(path: Path, content: str) -> None:
    _reject_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_links(path)
    name = None
    try:
        fd, name = tempfile.mkstemp(prefix='.raee-tmp-', dir=path.parent)
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
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
    write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + '\n')
