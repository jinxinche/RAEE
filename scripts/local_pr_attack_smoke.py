#!/usr/bin/env python3
"""Credential-free local PR boundary acceptance (not a real GitHub fork run)."""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / 'scripts' / 'pr_boundary.py'


def scenario(mode: str) -> dict:
    with tempfile.TemporaryDirectory() as temp:
        base, head = Path(temp) / 'base', Path(temp) / 'head'
        base.mkdir(); head.mkdir()
        for root in (base,head):
            (root / 'README.md').write_text('read me\n')
        if mode == 'ordinary':
            (head / 'README.md').write_text('changed\n')
        elif mode == 'security-workflow':
            dest = head / '.github' / 'workflows'
            dest.mkdir(parents=True)
            (dest/'injected.yml').write_text('on: pull_request_target\n')
        elif mode == 'file-symlink':
            (head / 'untrusted-link').symlink_to('/etc/passwd')
        elif mode == 'dir-symlink':
            (head / 'untrusted-dir').symlink_to('/tmp', target_is_directory=True)
        elif mode == 'untrusted-code':
            # A very visible would-be side effect; scanner must not import/execute this.
            (head/'injected.py').write_text('raise RuntimeError("ATTACK CODE EXECUTED")\n')
        else:
            raise ValueError('Unsupported scenario')
        run = subprocess.run([sys.executable, str(CHECKER), '--base', str(base), '--head', str(head)],
                             capture_output=True, text=True, timeout=15)
        expect = 1 if mode in {'security-workflow','file-symlink','dir-symlink'} else 0
        # Only safe status, not untrusted text, is emitted as JSON.
        return {'case':mode,'expected_exit':expect,'observed_exit':run.returncode,
                'passed':run.returncode==expect}


if __name__ == '__main__':
    results = [scenario(x) for x in ('ordinary','security-workflow','file-symlink','dir-symlink','untrusted-code')]
    print(json.dumps({'scenario':'local-only-untrusted-pr-boundary','results':results,
                      'passed':sum(x['passed'] for x in results),'total':len(results),
                      'note':'Local subprocess verification only; no actual GitHub fork PR was executed.'}, indent=2))
    sys.exit(0 if all(x['passed'] for x in results) else 1)
