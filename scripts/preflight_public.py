"""Release gate for obviously unsafe files. NOT a complete secret scanner."""
from __future__ import annotations
import os
import sys
from pathlib import Path

DANGER_SUFFIX = {'.pem', '.p12', '.pfx', '.key'}
DANGER_BASENAMES = {'.env', '.env.local', 'id_rsa', 'id_ed25519', 'credentials.json', 'token.json'}
MAX_FILE_SIZE = 25_000_000
EXCLUDED_DIRS = {'.git', '__pycache__', '.venv', 'build', 'dist', '.raee'}

def find_risks(root: Path) -> list[str]:
    risks=[]
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not (Path(base) / d).is_symlink()]
        for name in files:
            f=Path(base)/name
            rel=f.relative_to(root).as_posix()
            if f.is_symlink():
                risks.append(f'symlink file: {rel}')
            elif name in DANGER_BASENAMES or f.suffix.lower() in DANGER_SUFFIX:
                risks.append(f'potential credential file: {rel}')
            elif f.stat().st_size > MAX_FILE_SIZE:
                risks.append(f'oversized file: {rel}')
    return risks

if __name__ == '__main__':
    issues = find_risks(Path('.'))
    if issues:
        print('PUBLIC RELEASE PRECHECK FAILED:\n'+'\n'.join(issues[:25]),file=sys.stderr)
        sys.exit(1)
    print('Preflight checks passed; run a separate full secrets scan before publication.')
