"""Requirement/evidence associations: explicit attribution, non-satisfying suggestions."""
from __future__ import annotations

from pathlib import Path
from . import core
from .agent_logs import IMPORTS
from .topic_tags import tags

LINKS = Path('.raee/links.json')


def available_evidence(root: Path) -> dict[str, dict]:
    manual = core.read_json(root / core.LEDGER, {'runs': []}).get('runs', [])
    imported = core.read_json(root / IMPORTS, {'observations': []}).get('observations', [])
    return {str(e['id']): e for e in manual + imported}


def link_evidence(root: Path, requirement: str, evidence_id: str, reason: str) -> dict:
    reqs = {r['id'] for r in core.get_manifest(root).get('requirements', [])}
    if requirement not in reqs:
        raise ValueError(f'Unknown requirement: {requirement}')
    evidence = available_evidence(root)
    if evidence_id not in evidence:
        raise ValueError(f'Unknown evidence: {evidence_id}')
    if len(reason.strip()) < 8:
        raise ValueError('Provide a specific reason of at least 8 characters explaining relevance')
    store = core.read_json(root / LINKS, {'schema': 1, 'links': []})
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
    evidence = available_evidence(root)
    links = core.read_json(root / LINKS, {'links': []}).get('links', [])
    explicit = []
    for l in links:
        e = evidence.get(l.get('evidence_id'))
        if not e or not any(r['id'] == l['requirement'] for r in reqs):
            continue
        if e.get('provenance') == 'UNVERIFIED_AGENT_TRANSCRIPT':
            state = 'LOG_ONLY_NOT_VALIDATED'
        elif e.get('source_fingerprint') != source['sha256'] or e.get('source_fingerprint_after') != e.get('source_fingerprint'):
            state = 'STALE'
        elif e.get('observed_exit_code') == 0:
            state = 'OBSERVED_PASS_SELF_LINKED'
        else:
            state = 'OBSERVED_FAILED_SELF_LINKED'
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
