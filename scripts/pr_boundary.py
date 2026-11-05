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
MAX_ENTRIES = 20000  # Includes directories, even empty ones; bounds traversal work.
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


def symlink_signature(path: Path) -> str:
    """Record the link target text without resolving/following the target.

    A constant 'symlink' marker wrongly treats a retargeted symlink as unchanged.
    Hash the target to avoid leaking paths in public CI output.
    """
    target = os.fsencode(os.readlink(path))
    if len(target) > 4096:
        raise ValueError('Symlink target exceeds bounded inspection limit')
    return 'symlink:' + hashlib.sha256(target).hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    root = root.resolve(strict=True)
    found: dict[str, str] = {}
    total = 0
    entries = 0
    pending = [root]
    while pending:
        current = pending.pop()
        # Iterate incrementally instead of materializing an unbounded directory
        # listing. Unlike os.walk's default, scandir propagates traversal errors.
        with os.scandir(current) as children:
            for entry in children:
                entries += 1
                if entries > MAX_ENTRIES:
                    raise ValueError('PR inspection entry-count limit exceeded')
                p = Path(entry.path)
                relative = p.relative_to(root).as_posix()
                meta = entry.stat(follow_symlinks=False)
                # Classify links before the metadata exception. Cache/environment
                # names are ordinary PR data and cannot hide a link or script.
                if stat.S_ISLNK(meta.st_mode):
                    if len(found) >= MAX_FILES:
                        raise ValueError('PR inspection file-count limit exceeded')
                    found[relative] = symlink_signature(p)
                    continue
                if stat.S_ISDIR(meta.st_mode):
                    # Only the checkout's own Git metadata is out of scope.
                    if current == root and entry.name == '.git':
                        continue
                    pending.append(p)
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
             new.get(path, '').startswith('symlink:')]
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
