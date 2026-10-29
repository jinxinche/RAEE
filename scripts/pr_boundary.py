#!/usr/bin/env python3
"""No-dependency, fail-closed inspection of a fork PR as passive file data.

Always run this script from the trusted base checkout. No imports from PR head.
Avoid symlink traversal and restrict memory/bytes. This does NOT assess code quality.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import stat
import sys
from pathlib import Path

MAX_FILES = 10000
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
BLOCKED_PREFIXES = (
    '.github/workflows/', 'scripts/',
)
BLOCKED_EXACT = {
    '.github/CODEOWNERS', '.github/branch-protection.json',
    '.gitattributes', '.gitmodules', 'pyproject.toml',
    'src/raee_lite/ci_attestation.py',
}


def snapshot(root: Path) -> dict[str, str]:
    root = root.resolve(strict=True)
    found: dict[str, str] = {}
    total = 0
    for current, dirs, files in os.walk(root, followlinks=False):
        # Surface new/changed directory symlinks as an explicit review boundary;
        # never traverse them or silently omit them from the diff inventory.
        safe_dirs = []
        for d in sorted(dirs):
            if d in {'.git', '.raee', '__pycache__', '.venv', '.tox'}:
                continue
            candidate = Path(current) / d
            if candidate.is_symlink():
                found[candidate.relative_to(root).as_posix()] = 'symlink'
            else:
                safe_dirs.append(d)
        dirs[:] = safe_dirs
        for name in sorted(files):
            p = Path(current) / name
            relative = p.relative_to(root).as_posix()
            meta = p.lstat()
            if stat.S_ISLNK(meta.st_mode):
                found[relative] = 'symlink'
                continue
            if not stat.S_ISREG(meta.st_mode):
                raise ValueError(f'Unsafe special file: {relative}')
            if len(found) >= MAX_FILES or meta.st_size > MAX_FILE_BYTES or total + meta.st_size > MAX_TOTAL_BYTES:
                raise ValueError('PR inspection size limit exceeded; refuse to mark safe')
            total += meta.st_size
            digest = hashlib.sha256()
            with p.open('rb') as inp:
                remaining = meta.st_size
                while remaining:
                    chunk = inp.read(min(65536, remaining))
                    if not chunk:
                        raise ValueError('File changed while reading')
                    remaining -= len(chunk)
                    digest.update(chunk)
            found[relative] = digest.hexdigest()
    return found


def evaluate(base: Path, head: Path) -> tuple[bool, list[str]]:
    old, new = snapshot(base), snapshot(head)
    changed = sorted(path for path in old.keys() | new.keys() if old.get(path) != new.get(path))
    risky = [path for path in changed if path in BLOCKED_EXACT or
             any(path.startswith(prefix) for prefix in BLOCKED_PREFIXES) or
             new.get(path) == 'symlink']
    return not risky, risky


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--head', type=Path, required=True)
    args = parser.parse_args()
    try:
        safe, risky = evaluate(args.base, args.head)
    except (OSError, ValueError) as exc:
        print(f'REJECTED: unable to inspect PR safely ({type(exc).__name__})')
        return 2
    if not safe:
        print('REVIEW REQUIRED: PR changes evidence trust-boundary files:')
        for path in risky[:50]:
            print(f' - {path}')
        return 1
    print('STATIC BOUNDARY PASS: no changes to protected workflow/security paths.')
    print('This result does NOT prove PR code passes tests or is secure.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
