"""Bounded, read-only developer preflight. It does NOT certify security.

Never executes repository scripts or opens raw agent transcripts. Findings are
static and may be incomplete. Targeted paths only; no unbounded file traversal.
"""
from __future__ import annotations

import json
import re
import stat
from pathlib import Path

MAX_WORKFLOW_BYTES = 256_000
MAX_WORKFLOWS = 80
ACTION = re.compile(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)")
PINNED = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./-]+)?@[0-9a-fA-F]{40}$")


def _small_regular_file(path: Path, limit: int) -> str | None:
    """Reject symlinks and special files, and bound reads."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError('Untrusted, non-regular, or oversized preflight input')
    # If the path changes during read, only a bounded text value is used.
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Preflight input exceeds byte budget')
    return data.decode('utf-8', errors='replace')


def evaluate(root: Path) -> dict:
    """Static observations. Results always require developer interpretation."""
    if not root.is_dir():
        raise ValueError('Project directory does not exist')
    findings: list[dict] = []
    def mark(code: str, level: str, message: str, remediation: str) -> None:
        findings.append({'id': code, 'severity': level, 'message': message,
                         'next_action': remediation})

    if not (root / 'README.md').is_file():
        mark('DOCS_MISSING', 'review', 'README.md missing.', 'Add a minimal install/use example and limitations.')
    if not any((root / f).is_file() for f in ('LICENSE', 'LICENSE.md', 'COPYING')):
        mark('LICENSE_MISSING', 'review', 'No obvious open-source license.', 'Choose and include an appropriate LICENSE.')
    if not (root / 'tests').is_dir():
        mark('TESTS_MISSING', 'review', 'No tests directory found.', 'Add runnable tests and a CI smoke check.')
    if (root / 'package.json').is_file() and not any((root / p).is_file()
        for p in ('package-lock.json', 'pnpm-lock.yaml', 'yarn.lock', 'bun.lockb', 'bun.lock')):
        mark('LOCKFILE_MISSING', 'review', 'JavaScript lockfile not found.', 'Commit a deterministic lockfile if using managed JS dependencies.')

    workflow_dir = root / '.github' / 'workflows'
    workflow_files = []
    if workflow_dir.exists() or workflow_dir.is_symlink():
        if (root / '.github').is_symlink() or workflow_dir.is_symlink() or not workflow_dir.is_dir():
            mark('WORKFLOW_DIR_UNSAFE', 'blocker', 'Workflow directory is not a regular directory.', 'Review symlink or special paths.')
        else:
            workflow_files = sorted([p for p in workflow_dir.iterdir() if p.suffix in ('.yml', '.yaml')])
            if len(workflow_files) > MAX_WORKFLOWS:
                mark('WORKFLOW_LIMIT', 'blocker', 'Too many workflow files for bounded review.', 'Review workflow directory manually.')
                workflow_files = workflow_files[:MAX_WORKFLOWS]
    if not workflow_files:
        mark('CI_NOT_FOUND', 'review', 'No active GitHub Actions workflow detected.', 'Add low-privilege tests and explicit PR policy.')

    for wf in workflow_files:
        try:
            body = _small_regular_file(wf, MAX_WORKFLOW_BYTES)
        except (OSError, ValueError):
            mark('WORKFLOW_UNREADABLE', 'blocker', 'Workflow cannot be safely inspected.', 'Review size, symlinks and file type manually.')
            continue
        if body is None:
            continue
        if re.search(r'(?m)^\s*pull_request_target\s*:', body) or re.search(r'(?m)^\s*-\s*pull_request_target\s*$', body):
            mark('PR_TARGET_TRIGGER', 'review', 'Privileged pull_request_target trigger detected.', 'Ensure no fork-controlled code/artifacts are executed with credentials.')
        if re.search(r'(?m)^\s*workflow_run\s*:', body):
            mark('WORKFLOW_RUN_TRIGGER', 'review', 'workflow_run trigger detected.', 'Treat artifacts from previous jobs as untrusted.')
        if re.search(r'(?m)^\s*permissions\s*:\s*write-all\s*$', body):
            mark('WRITE_ALL', 'blocker', 'Unrestricted token permissions detected.', 'Use explicit least-privilege job permissions.')
        for match in ACTION.finditer(body):
            action = match.group(1)
            if action.startswith('./'):
                continue
            if not PINNED.fullmatch(action):
                mark('UNPINNED_ACTION', 'review', 'An Action is not pinned to a 40-character commit SHA.',
                     'Pin external actions to reviewed commit digests.')
                break
        # Not proof of injection; only flags expressions in shell commands.
        if re.search(r'(?s)\brun\s*:\s*[^\n]*\$\{\{\s*github\.event\.', body):
            mark('EVENT_IN_RUN', 'review', 'GitHub event expression appears in a shell step.',
                 'Pass untrusted values through quoted environment variables, not shell interpolation.')

    manifest = root / '.raee' / 'manifest.json'
    report_path = root / '.raee' / 'report.json'
    if manifest.exists():
        try:
            from .enhanced import audit
            evidence = audit(root)
            state = evidence.get('overall', 'UNKNOWN')
            if state not in ('CHECKS_PASSED_WITH_LIMITS', 'AUTOCHECKS_PASSED_WITH_LIMITS'):
                mark('EVIDENCE_GAPS', 'review', 'Current evidence state is not passing.',
                     'Run `raee-lite plan`; inspect unmet scopes and stale checks.')
            if evidence.get('source', {}).get('skipped'):
                mark('PARTIAL_FINGERPRINT', 'review', 'Source fingerprint has excluded/over-budget files.',
                     'Review coverage limits before signing evidence.')
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            mark('INVALID_EVIDENCE', 'blocker', 'Existing .raee evidence cannot be safely audited.',
                 'Review ledger and manifest integrity; avoid treating the report as verified.')
    elif report_path.exists():
        mark('REPORT_WITHOUT_MANIFEST', 'review', 'Report exists without requirements manifest.',
             'Reconcile evidence files before sharing.')
    else:
        mark('NO_EVIDENCE', 'info', 'No local role-aware evidence has been recorded.',
             'Run `raee-lite check` then declare critical requirements and checks.')

    counts = {level: sum(f['severity'] == level for f in findings) for level in ('blocker', 'review', 'info')}
    return {'tool': 'RAEE-Lite', 'schema': 'raee-preflight-v1',
            'result': 'BLOCKED' if counts['blocker'] else 'REVIEW_REQUIRED' if counts['review'] else 'NO_STATIC_BLOCKERS_FOUND',
            'counts': counts, 'findings': findings,
            'limitations': ('Read-only heuristic inventory. Not a vulnerability scan, proof of code correctness, '
                            'branch-protection status, CI signing identity, or security certification. '
                            'Does not run any project-owned command or access the network.')}
