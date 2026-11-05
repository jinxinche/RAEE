"""Requirement/evidence associations: explicit attribution, non-satisfying suggestions."""
from __future__ import annotations

from pathlib import Path
from . import core
from .agent_logs import IMPORTS
from .evidence_binding import evaluate_binding, evaluate_environment, valid_execution
from .safe_io import exclusive_lock
from .topic_tags import tags

LINKS = Path('.raee/links.json')
LINKS_LOCK = Path('.raee/links.lock')


def _read_records(path: Path, field: str) -> dict:
    store = core.read_json(path, {'schema': 1, field: []})
    if (not isinstance(store, dict) or not isinstance(store.get(field), list) or
            any(not isinstance(row, dict) for row in store[field])):
        raise ValueError(f'Invalid {path.name}: expected an object with {field} records')
    return store


def _require_strings(row: dict, fields: tuple[str, ...], filename: str) -> None:
    if any(not isinstance(row.get(key), str) or not row[key].strip() for key in fields):
        raise ValueError(f'Invalid {filename}: missing or malformed record fields')


def _read_links(root: Path) -> dict:
    store = _read_records(root / LINKS, 'links')
    pairs = set()
    for row in store['links']:
        _require_strings(row, ('requirement', 'evidence_id', 'rationale'), LINKS.name)
        pair = (row['requirement'], row['evidence_id'])
        if pair in pairs:
            raise ValueError('Invalid links.json: duplicate requirement/evidence pair')
        pairs.add(pair)
    return store


def _validate_link_targets(links: list[dict], requirements: set[str], evidence: dict[str, dict]) -> None:
    for row in links:
        if row['requirement'] not in requirements:
            raise ValueError('Invalid links.json: dangling requirement reference')
        if row['evidence_id'] not in evidence:
            raise ValueError('Invalid links.json: dangling evidence reference')


def available_evidence(root: Path) -> dict[str, dict]:
    manual = core.read_json(root / core.LEDGER, {'schema': 1, 'runs': []}).get('runs', [])
    imported = _read_records(root / IMPORTS, 'observations')['observations']
    for row in imported:
        _require_strings(row, ('id', 'provider', 'command_family', 'log_status'), IMPORTS.name)
        if (row.get('provenance') != 'UNVERIFIED_AGENT_TRANSCRIPT' or
                (row.get('check_kind_hint') is not None and not isinstance(row['check_kind_hint'], str)) or
                not isinstance(row.get('topic_tags', []), list) or
                any(not isinstance(tag, str) for tag in row.get('topic_tags', []))):
            raise ValueError('Invalid imports.json: malformed transcript metadata')
    evidence = {}
    for row in manual + imported:
        _require_strings(row, ('id',), 'evidence')
        if row['id'] in evidence:
            raise ValueError('Ambiguous evidence IDs')
        evidence[row['id']] = row
    return evidence


def _linked_state(receipt: dict, source: dict, requirements: dict[str, dict]) -> str:
    if receipt.get('provenance') == 'UNVERIFIED_AGENT_TRANSCRIPT':
        return 'LOG_ONLY_NOT_VALIDATED'
    if not valid_execution(receipt):
        return 'INVALID_EVIDENCE'
    if 'dependency_scope' in receipt:
        return 'SCOPE_CONTEXT_REQUIRED' if isinstance(receipt['dependency_scope'], dict) else 'SCOPE_UNBOUND'
    if (receipt.get('source_fingerprint') != source['sha256'] or
            receipt.get('source_fingerprint_after') != receipt.get('source_fingerprint')):
        return 'STALE'
    if receipt.get('origin') == 'auto_discovered':
        binding = evaluate_environment(receipt)
    else:
        # Attribution to another requirement does not replace the receipt's
        # original intent binding or establish coverage of the linked target.
        rid = receipt.get('requirement')
        requirement = requirements.get(rid) if isinstance(rid, str) else None
        if requirement is None:
            return 'INTENT_UNBOUND'
        binding = evaluate_binding(receipt, requirement['description'])
    if binding != 'BINDING_MATCHED':
        return binding
    if receipt['observed_exit_code'] != 0:
        return 'OBSERVED_FAILED_SELF_LINKED'
    if receipt.get('files_skipped') or source.get('skipped'):
        return 'PARTIAL_COVERAGE'
    return 'OBSERVED_PASS_SELF_LINKED'


def link_evidence(root: Path, requirement: str, evidence_id: str, reason: str) -> dict:
    # Read the latest table under the same permanent lock as every mutation;
    # atomic replacement alone cannot preserve another writer's updates.
    with exclusive_lock(root / LINKS_LOCK):
        store = _read_links(root)
        reqs = {r['id'] for r in core.get_manifest(root).get('requirements', [])}
        if requirement not in reqs:
            raise ValueError(f'Unknown requirement: {requirement}')
        evidence = available_evidence(root)
        if evidence_id not in evidence:
            raise ValueError(f'Unknown evidence: {evidence_id}')
        if len(reason.strip()) < 8:
            raise ValueError('Provide a specific reason of at least 8 characters explaining relevance')
        _validate_link_targets(store['links'], reqs, evidence)
        record = {'requirement': requirement, 'evidence_id': evidence_id,
                  'rationale': reason.strip()[:1000], 'created_at': core.utcnow(),
                  'self_declared': True}
        # update manual association, preserving unique pair
        store['links'] = [x for x in store['links'] if not (x['requirement'] == requirement and x['evidence_id'] == evidence_id)]
        store['links'].append(record)
        core.write_json(root / LINKS, store)
        return record


def build_associations(root: Path, source: dict) -> dict:
    reqs = core.get_manifest(root).get('requirements', [])
    by_id = {r['id']: r for r in reqs}
    evidence = available_evidence(root)
    links = _read_links(root)['links']
    _validate_link_targets(links, set(by_id), evidence)
    explicit = []
    for l in links:
        e = evidence[l['evidence_id']]
        state = _linked_state(e, source, by_id)
        explicit.append({**l, 'state': state, 'basis': 'USER_ASSERTED_ASSOCIATION_NOT_COVERAGE_PROOF'})
    imported = [e for e in evidence.values() if e.get('provenance') == 'UNVERIFIED_AGENT_TRANSCRIPT']
    suggestions = []
    by_kind = {}
    for e in imported:
        by_kind.setdefault(e.get('check_kind_hint'), []).append(e)
    # Weak hints only. This intentionally avoids any semantic claim or score.
    for r in reqs:
        requirement_tags = set(tags(r.get('description', '')))
        if not requirement_tags:
            continue  # refuse weak topic-less suggestions rather than guess
        linked = {a['evidence_id'] for a in explicit if a['requirement'] == r['id']}
        count = 0
        for kind in r.get('expected_checks', []):
            for e in by_kind.get(kind, []):
                if e['id'] in linked or not (requirement_tags & set(e.get('topic_tags', []))):
                    continue
                suggestions.append({'requirement': r['id'], 'evidence_id': e['id'],
                                    'matched_kind': kind, 'strength': 'WEAK_SCOPE_AND_TOPIC_HINT',
                                    'reason': 'Matching coarse check category and allowlisted topic; still does not establish test relevance or coverage.'})
                count += 1
                if count >= 5:
                    break
            if count >= 5:
                break
    return {'explicit': explicit, 'suggestions': suggestions, 'imported': imported,
            'note': 'User links are attribution only. Imported transcripts are unverified and never fulfill contracts.'}
