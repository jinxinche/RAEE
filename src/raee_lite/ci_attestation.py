"""Trusted-CI *integration* with GitHub's artifact attestations.

Safety model: an exported manifest is UNTRUSTED until independently verified
using the official `gh attestation verify` Sigstore verifier. GitHub workflow
identity is policy checked outside the artifact via explicit pinned arguments.
A valid attestation proves artifact origin/integrity, NOT that its claims are true.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Mapping

from . import core
from .attestation import _file as bounded_file
from .safe_io import write_json

REPO = re.compile(r'^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$')
SHA = re.compile(r'^[0-9a-f]{40}(?:[0-9a-f]{24})?$')
WORKFLOW = re.compile(r'^\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml$')
REF = re.compile(r'^refs/heads/[A-Za-z0-9_./-]{1,200}$')
RUN_ID = re.compile(r'^[1-9][0-9]{0,19}$')
SCHEMA = 'urn:raee-lite:ci-evidence:v1'
MAX_MANIFEST = 65_536
MAX_REPORT = 8_000_000
MAX_VERIFIER_OUT = 256_000
# CVE-2026-64655: older gh versions mishandle regex metacharacters in signer
# identity checks. Reject those versions before trusting a provenance decision.
MIN_SAFE_GH = (2, 97, 0)


def require_safe_gh(gh: str, timeout: int = 10) -> tuple[int, int, int]:
    """Fail closed when the official GitHub CLI is missing or vulnerable.

    A valid version check does not establish authenticity of a replaced executable;
    the verifier must also trust its local installation and execution host.
    """
    try:
        result = subprocess.run([gh, 'version'], capture_output=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Unable to inspect GitHub CLI version safely') from exc
    if result.returncode or len(result.stdout) > 8192:
        raise ValueError('Cannot trust unknown GitHub CLI version')
    try:
        first = result.stdout.decode('utf-8').splitlines()[0]
    except (UnicodeError, IndexError) as exc:
        raise ValueError('Cannot parse GitHub CLI version') from exc
    match = re.fullmatch(r'gh version ([0-9]+)\.([0-9]+)\.([0-9]+)(?: \(.*\))?', first)
    if not match:
        raise ValueError('Unrecognized GitHub CLI version format')
    found = tuple(int(x) for x in match.groups()[:3])
    if found < MIN_SAFE_GH:
        raise ValueError('Outdated GitHub CLI (<2.97.0): update before verifying attestations')
    return found


def _assert(value: str, pattern: re.Pattern, name: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value) or '..' in value or '\\' in value:
        raise ValueError(f'Invalid {name}')
    return value


def _obj_file(path: Path, max_size: int) -> tuple[dict, bytes]:
    raw = bounded_file(path, max_size)
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError('Invalid evidence JSON') from exc
    if not isinstance(value, dict):
        raise ValueError('Evidence JSON must be an object')
    return value, raw


def _workflow_ref(value: str, repo: str, workflow: str, ref: str) -> None:
    if value != f'{repo}/{workflow}@{ref}':
        raise ValueError('GitHub workflow identity does not match the expected trusted workflow')


def export(root: Path, *, expected_repo: str, trusted_ref: str,
           workflow: str, environ: Mapping[str, str] | None = None,
           require_passed: bool = True) -> dict:
    """Export *claimed* CI evidence only from selected trusted workflow contexts.

    Environment checks are defense in depth and provide NO identity guarantee.
    Later verifier must validate a GitHub/Sigstore attestation for this exact file.
    """
    env = os.environ if environ is None else environ
    repo = _assert(expected_repo, REPO, 'expected repository')
    ref = _assert(trusted_ref, REF, 'trusted ref')
    path = _assert(workflow, WORKFLOW, 'workflow path')
    if env.get('GITHUB_ACTIONS') != 'true' or env.get('CI', '').lower() != 'true':
        raise ValueError('CI export requires an explicitly recognized GitHub Actions context')
    if env.get('GITHUB_EVENT_NAME') not in {'push', 'workflow_dispatch'}:
        raise ValueError('Only trusted push/workflow_dispatch runs may export CI evidence')
    if env.get('GITHUB_REPOSITORY') != repo or env.get('GITHUB_REF') != ref:
        raise ValueError('Repository or ref differs from trusted policy')
    _workflow_ref(env.get('GITHUB_WORKFLOW_REF', ''), repo, path, ref)
    sha = _assert(env.get('GITHUB_SHA', ''), SHA, 'Git commit SHA')
    run_id = _assert(env.get('GITHUB_RUN_ID', ''), RUN_ID, 'GitHub run ID')
    git = core.git_context(root)
    if not git.get('available') or git.get('head') != sha:
        raise ValueError('Checked-out Git HEAD differs from CI source SHA')
    if git.get('changed_paths') or git.get('changed_paths_truncated'):
        raise ValueError('Dirty or truncated Git checkout is not eligible for CI export')
    report, raw = _obj_file(root / '.raee/report.json', MAX_REPORT)
    source = core.fingerprint(root)
    if source.get('skipped'):
        raise ValueError('Partial source snapshot cannot be exported as trusted CI evidence')
    if report.get('git', {}).get('head') != sha or report.get('git', {}).get('changed_paths'):
        raise ValueError('Evidence report has stale or dirty Git context')
    if report.get('source', {}).get('sha256') != source['sha256'] or report.get('source', {}).get('skipped'):
        raise ValueError('Evidence report does not bind to current source snapshot')
    # Strict rule: a generic auto-discovered passing command cannot justify CI PASS.
    from .enhanced import audit, is_passing
    # Recompute critical semantics against current ledger + manifest. Prevent a
    # modified underlying receipt from inheriting an older PASS report.
    fresh = audit(root)
    for field in ('overall', 'requirements', 'evidence_contracts', 'verification_provenance'):
        if report.get(field) != fresh.get(field):
            raise ValueError('Evidence ledger/manifest differs from generated report; regenerate report')
    passing = is_passing(fresh, strict=True)
    if require_passed and not passing:
        raise ValueError('Explicit acceptance evidence is not passing; cannot export passed CI receipt')
    rows = report.get('requirements', [])
    if not isinstance(rows, list) or len(rows) > 500:
        raise ValueError('Malformed requirement summary')
    summary = {key: sum(r.get('state') == key for r in rows if isinstance(r, dict))
               for key in ('OBSERVED_PASS', 'FAILED_CHECK', 'STALE', 'UNTESTED', 'PARTIAL_COVERAGE')}
    # Never include commands, labels/descriptions, logs, user names or raw report content.
    result = {
        'schema': SCHEMA,
        'source': {'repository': repo, 'ref': ref, 'commit': sha, 'fingerprint_sha256': source['sha256']},
        'workflow': {'path': path, 'event': env['GITHUB_EVENT_NAME'], 'run_id': run_id},
        'report': {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                   'outcome': report.get('overall'), 'strict_check_passed': passing,
                   'requirements_total': len(rows), 'state_counts': summary},
        'assurance': 'UNTRUSTED_EXPORT_UNTIL_GITHUB_ATTESTATION_VERIFIED',
        'notice': 'A GitHub attestation verifies provenance/integrity of this claim, not test validity or code correctness.',
    }
    dest = root / '.raee/ci-evidence.json'
    write_json(dest, result)
    if dest.stat().st_size > MAX_MANIFEST:
        dest.unlink(missing_ok=True)
        raise ValueError('CI receipt unexpectedly oversized')
    return result


def verify(manifest_path: Path, *, expected_repo: str, expected_ref: str,
           expected_sha: str, expected_workflow: str, report_path: Path | None = None,
           gh_executable: str | None = None, timeout: int = 60,
           require_passed: bool = True) -> dict:
    """Use GitHub CLI to cryptographically verify official identity and provenance.

    No OIDC JWT is accepted as proof, no self-declared fields grant trust, no
    shell and no automatic network downloads. Missing CLI => FAIL CLOSED.
    """
    repo = _assert(expected_repo, REPO, 'repository')
    ref = _assert(expected_ref, REF, 'source ref')
    sha = _assert(expected_sha, SHA, 'source SHA')
    workflow = _assert(expected_workflow, WORKFLOW, 'workflow path')
    if timeout <= 0 or timeout > 300:
        raise ValueError('Verifier timeout must be between 1 and 300 seconds')
    manifest, _ = _obj_file(manifest_path, MAX_MANIFEST)
    if manifest.get('schema') != SCHEMA:
        raise ValueError('Unsupported CI evidence schema')
    source = manifest.get('source')
    origin = manifest.get('workflow')
    report = manifest.get('report')
    if not isinstance(source, dict) or not isinstance(origin, dict) or not isinstance(report, dict):
        raise ValueError('Incomplete CI evidence manifest')
    if (source.get('repository'), source.get('ref'), source.get('commit')) != (repo, ref, sha):
        raise ValueError('CI evidence source does not match pinned policy')
    if origin.get('path') != workflow or origin.get('event') not in ('push', 'workflow_dispatch'):
        raise ValueError('CI evidence workflow or event does not match policy')
    _assert(origin.get('run_id', ''), RUN_ID, 'run id')
    _assert(source.get('fingerprint_sha256', ''), re.compile(r'^[0-9a-f]{64}$'), 'source fingerprint')
    _assert(report.get('sha256', ''), re.compile(r'^[0-9a-f]{64}$'), 'report digest')
    if report.get('bytes', 0) <= 0 or report.get('bytes', 0) > MAX_REPORT:
        raise ValueError('Invalid report size')
    if require_passed and (report.get('strict_check_passed') is not True or
                           report.get('outcome') != 'CHECKS_PASSED_WITH_LIMITS'):
        raise ValueError('CI report does not claim passing explicit acceptance checks')
    if report_path is not None:
        _, content = _obj_file(report_path, MAX_REPORT)
        if len(content) != report['bytes'] or hashlib.sha256(content).hexdigest() != report['sha256']:
            raise ValueError('Attached report content differs from attested digest')
    gh = gh_executable if gh_executable is not None else shutil.which('gh')
    if not gh:
        raise ValueError('GitHub CLI (gh) is required for authenticated CI provenance verification')
    require_safe_gh(gh, timeout=min(timeout, 10))
    args = [gh, 'attestation', 'verify', str(manifest_path),
            '--repo', repo, '--signer-workflow', f'{repo}/{workflow}',
            '--source-digest', sha, '--source-ref', ref,
            '--deny-self-hosted-runners', '--format', 'json']
    try:
        completed = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Official GitHub attestation verification unavailable or timed out') from exc
    if completed.returncode != 0:
        # Do not leak raw CLI stderr, which could contain service metadata.
        raise ValueError('GitHub attestation signature/identity verification FAILED')
    if len(completed.stdout) > MAX_VERIFIER_OUT:
        raise ValueError('GitHub verification response exceeds limit')
    try:
        rows = json.loads(completed.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid GitHub verification response') from exc
    if not isinstance(rows, list) or not rows:
        raise ValueError('GitHub verifier did not return a verified attestation')
    return {'result': 'GITHUB_ATTESTATION_VERIFIED', 'repository': repo, 'commit': sha,
            'ref': ref, 'signer_workflow': f'{repo}/{workflow}',
            'report_sha256': report['sha256'], 'report_content_checked': report_path is not None,
            'verified_attestations': len(rows), 'code_correctness_proven': False,
            'notice': 'Verified CI provenance does not prove test quality, isolation or code correctness.'}
