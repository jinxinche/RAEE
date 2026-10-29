"""Offline evidence attestations using Ed25519 and DSSE.

A signature authenticates the *signer's assertion*, not that a test was genuinely
run or that a repository is secure. Trust anchors MUST be pinned separately.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from pathlib import Path

from . import core
from .safe_io import safe_read_json, write_json

MAX_REPORT = 8_000_000
MAX_LEDGER = 16_000_000
MAX_ENVELOPE = 512_000
MAX_KEY_BYTES = 16_384
TYPE = 'application/vnd.in-toto+json'
STATEMENT_TYPE = 'https://in-toto.io/Statement/v1'
PREDICATE_TYPE = 'urn:raee-lite:evidence-attestation:v1'
SHA_RE = re.compile(r'^[a-f0-9]{64}$')
GIT_RE = re.compile(r'^[a-f0-9]{40}(?:[a-f0-9]{24})?$')


def _crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise ValueError('Attestation needs cryptography: pip install "raee-lite[attest]"') from exc
    return serialization, Ed25519PrivateKey, Ed25519PublicKey, InvalidSignature


def _file(path: Path, limit: int, *, private: bool = False) -> bytes:
    # Conservative protection against paths that redirect to unexpected files.
    from .safe_io import _reject_links
    _reject_links(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError(f'Missing or oversized input: {path}')
    if private and os.name == 'posix' and (stat.S_IMODE(path.stat().st_mode) & 0o077):
        raise ValueError('Private signing key must have permissions 0600 (or stricter)')
    # Use O_NOFOLLOW where supported to avoid a final-component symlink swap.
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        data = os.read(fd, limit + 1)
    finally:
        os.close(fd)
    if len(data) > limit:
        raise ValueError('Input exceeds byte limit')
    return data


def _read_json(path: Path, limit: int) -> dict:
    raw = _file(path, limit)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid UTF-8 JSON document') from exc
    if not isinstance(value, dict):
        raise ValueError('Expected JSON object')
    return value


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _pae(payload_type: bytes, payload: bytes) -> bytes:
    return b'DSSEv1 ' + str(len(payload_type)).encode() + b' ' + payload_type + b' ' + str(len(payload)).encode() + b' ' + payload


def _b64decode(value: object, max_bytes: int) -> bytes:
    if not isinstance(value, str) or len(value) > ((max_bytes + 2) // 3) * 4 + 4:
        raise ValueError('Invalid or oversized base64 field')
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, __import__('binascii').Error) as exc:
        raise ValueError('Invalid base64 field') from exc


def _key_id(public_key) -> str:
    serialization, *_ = _crypto()
    raw = public_key.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    return _digest(raw)


def keygen(private_path: Path, public_path: Path, project: Path) -> dict:
    serialization, Private, _, _ = _crypto()
    from .safe_io import _reject_links
    private_path, public_path = private_path.expanduser().absolute(), public_path.expanduser().absolute()
    if private_path == public_path:
        raise ValueError('Private and public key paths must be different')
    # A private signing key should never be checked in to the project.
    if private_path.is_relative_to(project.resolve()) or private_path.resolve().is_relative_to(project.resolve()):
        raise ValueError('Private keys must be stored outside the project directory')
    for p in (private_path, public_path):
        _reject_links(p)
        if p.exists():
            raise ValueError(f'Refusing to overwrite existing key: {p}')
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    _reject_links(private_path)
    _reject_links(public_path)
    key = Private.generate()
    secret = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                               serialization.NoEncryption())
    pub = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(secret)
            f.flush()
            os.fsync(f.fileno())
        fd = os.open(public_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o644)
        with os.fdopen(fd, 'wb') as f:
            f.write(pub)
    except BaseException:
        # Never leave a partial keypair on an I/O failure.
        private_path.unlink(missing_ok=True)
        public_path.unlink(missing_ok=True)
        raise
    return {'public_key_fingerprint': _key_id(key.public_key()), 'private_key': str(private_path),
            'public_key': str(public_path)}


def _load_private(path: Path):
    serialization, Private, _, _ = _crypto()
    raw = _file(path, MAX_KEY_BYTES, private=True)
    try:
        key = serialization.load_pem_private_key(raw, password=None)
    except (ValueError, TypeError) as exc:
        raise ValueError('Unsupported private key or unencrypted key required') from exc
    if not isinstance(key, Private):
        raise ValueError('Expected Ed25519 private key')
    return key


def _load_public(path: Path):
    serialization, _, Public, _ = _crypto()
    try:
        key = serialization.load_pem_public_key(_file(path, MAX_KEY_BYTES))
    except (ValueError, TypeError) as exc:
        raise ValueError('Invalid public key') from exc
    if not isinstance(key, Public):
        raise ValueError('Expected Ed25519 public key')
    return key


def _git_identity(root: Path, report: dict, *, allow_dirty: bool, allow_no_git: bool) -> dict:
    actual = core.git_context(root)
    record = report.get('git')
    if not isinstance(record, dict):
        raise ValueError('Report lacks Git context. Regenerate the report.')
    if actual.get('available') != record.get('available'):
        raise ValueError('Git availability changed since the report')
    if not actual.get('available'):
        if not allow_no_git:
            raise ValueError('A Git repository is required; use --allow-no-git to attest source-only')
        return {'available': False, 'head': None, 'dirty': None}
    head = actual.get('head')
    if not isinstance(head, str) or not GIT_RE.fullmatch(head) or head != record.get('head'):
        raise ValueError('Git HEAD differs from the report')
    if actual.get('changed_paths_truncated') or record.get('changed_paths_truncated'):
        raise ValueError('Truncated Git status; cannot attest reliably')
    if actual.get('changed_paths') != record.get('changed_paths'):
        raise ValueError('Git working-tree status differs from the report')
    dirty = bool(actual.get('changed_paths'))
    if dirty and not allow_dirty:
        raise ValueError('Git working tree is dirty; commit changes or explicitly use --allow-dirty')
    return {'available': True, 'head': head, 'dirty': dirty}


def _valid_snapshot(root: Path, report: dict, *, allow_partial: bool) -> dict:
    reported = report.get('source')
    if not isinstance(reported, dict) or not isinstance(reported.get('sha256'), str) or not SHA_RE.fullmatch(reported['sha256']):
        raise ValueError('Report has no valid source fingerprint')
    actual = core.fingerprint(root)
    if actual['sha256'] != reported['sha256'] or actual.get('skipped') != reported.get('skipped'):
        raise ValueError('Source changed since report; regenerate report')
    if actual['skipped'] and not allow_partial:
        raise ValueError('Source fingerprint incomplete; use --allow-partial with documented limits')
    return actual


def _verify_ledger_references(report: dict, ledger: dict, source_sha256: str) -> list[dict]:
    # Keep a bounded, explicit summary; these are locally recorded *assertions*.
    rows = ledger.get('runs')
    if not isinstance(rows, list) or len(rows) > 2000:
        raise ValueError('Invalid evidence ledger')
    seen = set()
    selected = []
    for run in rows:
        if not isinstance(run, dict) or not isinstance(run.get('id'), str) or run['id'] in seen:
            raise ValueError('Invalid or duplicate evidence receipt')
        seen.add(run['id'])
        if run.get('source_fingerprint') != source_sha256 or run.get('source_fingerprint_after') != source_sha256:
            continue
        if run.get('origin') != 'isolated_replay' or run.get('observed_status') != 'pass' or run.get('observed_exit_code') != 0:
            continue
        iso = run.get('isolation')
        if not isinstance(iso, dict) or iso.get('backend') != 'docker' or not isinstance(iso.get('resolved_image_id'), str):
            continue
        selected.append({'id': run['id'], 'origin': run['origin'], 'snapshot_sha256': iso.get('snapshot_sha256'),
                         'image_id': iso['resolved_image_id'], 'status': run['observed_status'],
                         'snapshot_excluded_total': iso.get('snapshot_excluded_total')})
        if len(selected) >= 100:
            break
    return selected


def create(root: Path, key_path: Path, out: Path, *, allow_dirty=False, allow_no_git=False,
           allow_partial=False, require_isolated=False) -> dict:
    root = root.resolve()
    report_path = root / '.raee' / 'report.json'
    ledger_path = root / '.raee' / 'ledger.json'
    manifest_path = root / '.raee' / 'manifest.json'
    report = _read_json(report_path, MAX_REPORT)
    ledger = _read_json(ledger_path, MAX_LEDGER)
    _read_json(manifest_path, MAX_REPORT)
    snapshot = _valid_snapshot(root, report, allow_partial=allow_partial)
    git = _git_identity(root, report, allow_dirty=allow_dirty, allow_no_git=allow_no_git)
    # Re-audit current local ledger/manifest before signing, so a stale report
    # cannot claim a newer outcome just because the source tree is unchanged.
    from .enhanced import audit as live_audit
    live = live_audit(root)
    for field in ('overall', 'requirements', 'evidence_contracts', 'automatic_checks',
                  'verification_provenance', 'boundary_notes'):
        if report.get(field) != live.get(field):
            raise ValueError(f'Report is stale relative to current evidence ledger/manifest: {field}')
    isolated = _verify_ledger_references(report, ledger, snapshot['sha256'])
    if require_isolated and not isolated:
        raise ValueError('No matching successful isolated replay receipt in this source snapshot')
    if key_path.expanduser().resolve().is_relative_to(root):
        raise ValueError('Private signing key cannot reside inside the project directory')
    key = _load_private(key_path)
    source_digest = snapshot['sha256']
    report_sha = _digest(_file(report_path, MAX_REPORT))
    statement = {
        '_type': STATEMENT_TYPE,
        'subject': [{'name': 'source-snapshot', 'digest': {'sha256': source_digest}},
                    {'name': '.raee/report.json', 'digest': {'sha256': report_sha}}],
        'predicateType': PREDICATE_TYPE,
        'predicate': {
            'schema_version': 1, 'tool': 'RAEE-Lite', 'tool_version': '0.7.0',
            'source': {'sha256': source_digest, 'files': snapshot['files'],
                       'skipped_count': len(snapshot['skipped']),
                       'ignored_and_external_inputs_unverified': True},
            'git': git, 'report_sha256': report_sha,
            'ledger_sha256': _digest(_file(ledger_path, MAX_LEDGER)),
            'manifest_sha256': _digest(_file(manifest_path, MAX_REPORT)),
            'report_overall': report.get('overall'),
            'isolated_receipts': isolated,
            'limitations': ['Signing does not establish that the declared checks test real requirements.',
                            'All local evidence and Git context are assertions from the signing host.',
                            'No trusted execution environment or remotely verifiable runner identity.',
                            'Git-ignored, excluded, external and runtime inputs can be unaccounted for.'],
        },
    }
    payload = _canonical(statement)
    sig = key.sign(_pae(TYPE.encode(), payload))
    envelope = {'payloadType': TYPE, 'payload': base64.b64encode(payload).decode('ascii'),
                'signatures': [{'keyid': _key_id(key.public_key()),
                                'sig': base64.b64encode(sig).decode('ascii')}]}
    if len(_canonical(envelope)) > MAX_ENVELOPE:
        raise ValueError('Attestation is too large')
    if out.resolve() in (report_path.resolve(), ledger_path.resolve(), manifest_path.resolve()):
        raise ValueError('Attestation output cannot overwrite input evidence')
    # A new output path is deliberate; reject overwrites of previous signed artifacts.
    if out.exists() or out.is_symlink():
        raise ValueError('Attestation output already exists (refusing overwrite)')
    write_json(out, envelope)
    return {'attestation': str(out), 'keyid': envelope['signatures'][0]['keyid'],
            'git_commit': git['head'], 'source_sha256': source_digest,
            'isolated_receipts': len(isolated), 'verified': False}


def verify(root: Path, envelope_path: Path, public_path: Path, report_path: Path, *,
           expected_commit: str | None = None, check_current=False,
           require_isolated=False, require_clean=False, ledger_path: Path | None = None,
           manifest_path: Path | None = None) -> dict:
    """Fail closed. PUBLIC KEY IS EXTERNAL TRUST INPUT, never read from envelope."""
    _, _, _, InvalidSignature = _crypto()
    env = _read_json(envelope_path, MAX_ENVELOPE)
    if set(env) != {'payloadType', 'payload', 'signatures'} or env['payloadType'] != TYPE:
        raise ValueError('Invalid or unsupported DSSE envelope')
    if not isinstance(env['signatures'], list) or len(env['signatures']) != 1:
        raise ValueError('Expected exactly one attestation signature')
    signature = env['signatures'][0]
    if not isinstance(signature, dict) or set(signature) != {'keyid', 'sig'}:
        raise ValueError('Malformed signature entry')
    public = _load_public(public_path)
    keyid = _key_id(public)
    if signature['keyid'] != keyid:
        raise ValueError('Signer is not the independently trusted public key')
    payload = _b64decode(env['payload'], MAX_ENVELOPE)
    sig = _b64decode(signature['sig'], 128)
    try:
        public.verify(sig, _pae(TYPE.encode(), payload))
    except InvalidSignature as exc:
        raise ValueError('Invalid attestation signature') from exc
    try:
        stmt = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid signed JSON payload') from exc
    if not isinstance(stmt, dict) or stmt.get('_type') != STATEMENT_TYPE or stmt.get('predicateType') != PREDICATE_TYPE:
        raise ValueError('Unrecognized attestation statement or predicate')
    predicate = stmt.get('predicate')
    if not isinstance(predicate, dict) or predicate.get('schema_version') != 1:
        raise ValueError('Unsupported predicate version')
    source = predicate.get('source')
    git = predicate.get('git')
    if not isinstance(source, dict) or not SHA_RE.fullmatch(str(source.get('sha256', ''))) or not isinstance(git, dict):
        raise ValueError('Invalid signed source or Git claim')
    if stmt.get('subject') != [
        {'name': 'source-snapshot', 'digest': {'sha256': source['sha256']}},
        {'name': '.raee/report.json', 'digest': {'sha256': predicate.get('report_sha256')}}]:
        raise ValueError('Subject does not match signed predicate')
    if not SHA_RE.fullmatch(str(predicate.get('report_sha256', ''))):
        raise ValueError('Invalid report digest')
    report = _read_json(report_path, MAX_REPORT)
    if _digest(_file(report_path, MAX_REPORT)) != predicate['report_sha256']:
        raise ValueError('Evidence report changed since signing')
    if report.get('source', {}).get('sha256') != source['sha256'] or report.get('overall') != predicate.get('report_overall'):
        raise ValueError('Report content conflicts with signed predicate')
    if not isinstance(report.get('git'), dict) or report['git'].get('head') != git.get('head'):
        raise ValueError('Signed Git commit conflicts with report')
    if expected_commit is not None:
        if not GIT_RE.fullmatch(expected_commit.lower()) or git.get('head') != expected_commit.lower():
            raise ValueError('Signed evidence does not match expected Git commit')
    if require_clean and (not git.get('available') or git.get('dirty') is not False):
        raise ValueError('Signed evidence does not claim a clean Git checkout')
    receipts = predicate.get('isolated_receipts')
    if not isinstance(receipts, list) or len(receipts) > 100:
        raise ValueError('Invalid isolated receipt list')
    if require_isolated and not receipts:
        raise ValueError('No isolated execution receipt recorded in signed statement')
    if ledger_path is not None:
        ledger = _read_json(ledger_path, MAX_LEDGER)
        if _digest(_file(ledger_path, MAX_LEDGER)) != predicate.get('ledger_sha256'):
            raise ValueError('Ledger digest differs from signed record')
        found = _verify_ledger_references(report, ledger, source['sha256'])
        if found != receipts:
            raise ValueError('Isolated receipt inventory differs from signed ledger')
    if manifest_path is not None:
        _read_json(manifest_path, MAX_REPORT)
        if _digest(_file(manifest_path, MAX_REPORT)) != predicate.get('manifest_sha256'):
            raise ValueError('Manifest digest differs from signed record')
    if check_current:
        actual = core.fingerprint(root.resolve())
        if actual['sha256'] != source['sha256']:
            raise ValueError('Current project sources differ from signed snapshot')
        if actual.get('skipped') and not predicate['source'].get('skipped_count'):
            raise ValueError('Unreported fingerprint coverage gap')
        ctx = core.git_context(root.resolve())
        if ctx.get('available') != git.get('available') or ctx.get('head') != git.get('head'):
            raise ValueError('Current Git context differs from signed evidence')
        if bool(ctx.get('changed_paths')) != bool(git.get('dirty')) and ctx.get('available'):
            raise ValueError('Current Git dirty state differs from signed evidence')
    return {'signature': 'VALID', 'trust_anchor_keyid': keyid, 'source_sha256': source['sha256'],
            'git_commit': git.get('head'), 'clean_checkout_claim': git.get('dirty') is False,
            'report_digest': predicate['report_sha256'], 'isolated_receipts': len(receipts),
            'current_snapshot_checked': bool(check_current), 'code_correctness_proven': False,
            'note': 'Authentic signer claim only; runner independence, semantics and completeness are not proven.'}
