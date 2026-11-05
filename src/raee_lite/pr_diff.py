"""Offline comparison of independently generated JSON evidence snapshots."""
from __future__ import annotations

import html
import re
import json
from pathlib import Path

from . import core
from .safe_io import write_text as atomic_text


def load_report(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8_000_000:
        raise ValueError('Report missing, symlink, or larger than 8 MB')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError('Invalid report encoding or JSON') from exc
    if not isinstance(data, dict) or data.get('tool') != 'RAEE-Lite' or not isinstance(data.get('requirements'), list):
        raise ValueError('Not a RAEE-Lite evidence report')
    for key in ('requirements', 'automatic_checks', 'evidence_contracts'):
        rows = data.get(key, [])
        if not isinstance(rows, list) or len(rows) > 2000 or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f'Invalid or oversized report section: {key}')
    for row in data.get('evidence_contracts', []):
        if not isinstance(row.get('evidence_by_kind', []), list) or len(row.get('evidence_by_kind', [])) > 32:
            raise ValueError('Invalid evidence contract section')
        if any(not isinstance(x, dict) for x in row.get('evidence_by_kind', [])):
            raise ValueError('Invalid contract evidence row')
    src = data.get('source')
    if not isinstance(src, dict) or not re.fullmatch(r'[0-9a-f]{64}', str(src.get('sha256', ''))):
        raise ValueError('Invalid source fingerprint')
    if not isinstance(data.get('git', {}), dict):
        raise ValueError('Invalid Git provenance in report')
    return data


def _states(report: dict) -> dict:
    """Requirements matched by description, not unstable local R1/R2 identifiers."""
    matrix = {}
    descriptions = {x.get('id'): x.get('requirement', '') for x in report.get('requirements', [])}
    contracted = {r.get('id') for r in report.get('evidence_contracts', []) if r.get('expected_checks')}
    for r in report.get('requirements', []):
        # When contract scopes exist, avoid counting the same stale receipt twice.
        if r.get('id') in contracted:
            continue
        key = (str(r.get('requirement', '')).strip().casefold(), 'requirement')
        matrix[key] = str(r.get('state', 'UNKNOWN'))
    for row in report.get('automatic_checks', []):
        matrix[(str(row.get('id', row.get('kind','?'))).casefold(), 'autocheck')] = str(row.get('state','UNKNOWN'))
    for row in report.get('evidence_contracts', []):
        descr = str(row.get('requirement') or descriptions.get(row.get('id'), '')).strip().casefold()
        for e in row.get('evidence_by_kind', []):
            matrix[(descr, str(e.get('kind', 'unknown')))] = str(e.get('state', 'UNKNOWN'))
    return matrix


PASS = {'OBSERVED_PASS', 'CHECKS_PASSED_WITH_LIMITS', 'RECORDED'}
RISK = {'FAILED', 'FAILED_CHECK', 'STALE', 'UNTESTED', 'MISSING', 'PARTIAL', 'PARTIAL_COVERAGE', 'UNKNOWN'}


def compare_reports(base: dict, head: dict) -> dict:
    b, h = _states(base), _states(head)
    changes = []
    for key in sorted(b.keys() | h.keys()):
        before, after = b.get(key), h.get(key)
        if before == after:
            continue
        if before is None:
            classification = 'ADDED'
        elif after is None:
            classification = 'REMOVED_VERIFIED_EVIDENCE' if before in PASS else 'REMOVED_UNVERIFIED'
        elif before in PASS and after not in PASS:
            classification = 'REGRESSION'
        elif before not in PASS and after in PASS:
            classification = 'IMPROVED_OBSERVATION'
        else:
            classification = 'CHANGED_REVIEW'
        changes.append({'requirement': key[0], 'kind': key[1], 'base': before,
                        'head': after, 'classification': classification})
    old_imports = len(base.get('agent_evidence', {}).get('imported', []))
    new_imports = len(head.get('agent_evidence', {}).get('imported', []))
    return {'tool': 'RAEE-Lite PR evidence diff', 'version': '0.5.0',
            'base_snapshot': base.get('source', {}).get('sha256', ''),
            'base_commit': base.get('git', {}).get('head'), 'head_commit': head.get('git', {}).get('head'),
            'head_snapshot': head.get('source', {}).get('sha256', ''),
            'base_outcome': base.get('overall'), 'head_outcome': head.get('overall'),
            'changes': changes, 'regressions': sum(x['classification'] in ('REGRESSION', 'REMOVED_VERIFIED_EVIDENCE') for x in changes),
            'base_agent_observations': old_imports, 'head_agent_observations': new_imports,
            'caveat': 'This compares two supplied reports. It does not prove they represent the actual PR base/head commits, nor that tests adequately cover requirements.'}


def diff_markdown(diff: dict) -> str:
    def c(x):
        return html.escape(str(x if x is not None else '—'), quote=True).replace('|', '\\|').replace('\n', ' ')
    lines = ['# RAEE-Lite · Pull Request evidence delta', '',
             f"**Base outcome:** `{c(diff['base_outcome'])}` → **Head outcome:** `{c(diff['head_outcome'])}`",
             f"**Regression signals:** {diff['regressions']}", '',
             '| Requirement | Kind | Before | After | Classification |',
             '|---|---|---|---|---|']
    for item in diff['changes']:
        lines.append(f"| {c(item['requirement'])} | {c(item['kind'])} | {c(item['base'])} | {c(item['head'])} | {c(item['classification'])} |")
    if not diff['changes']:
        lines.append('| — | — | — | — | No state changes recorded |')
    lines += ['', f"Imported agent observations: {diff['base_agent_observations']} → {diff['head_agent_observations']}",
              '', diff['caveat'], '']
    return '\n'.join(lines)


def diff_html(diff: dict) -> str:
    esc = lambda x: html.escape(str(x if x is not None else '—'), quote=True)
    rows = ''.join('<tr>' + ''.join(f'<td>{esc(x.get(k))}</td>' for k in ('requirement','kind','base','head','classification')) + '</tr>' for x in diff['changes'])
    from .dashboard import STYLE
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>RAEE-Lite · PR Diff</title><style>{STYLE}</style></head><body><main><div class="eyebrow">RAEE-Lite / Evidence Diff</div><h1>What changed in the evidence?</h1><p class="sub">Compare two supplied evidence snapshots. No tests run during comparison.</p><section class="hero"><div class="kpi"><small>BASE</small><strong>{esc(diff['base_outcome'])}</strong></div><div class="arrow">→</div><div class="kpi"><small>HEAD</small><strong>{esc(diff['head_outcome'])}</strong></div><div class="kpi"><small>REGRESSIONS</small><strong>{esc(diff['regressions'])}</strong></div></section><section class="panel"><h2>Evidence state changes</h2><div class="scroll"><table><thead><tr><th>Requirement</th><th>Scope</th><th>Base</th><th>Head</th><th>Delta</th></tr></thead><tbody>{rows or '<tr><td colspan="5">No changes observed in compared states.</td></tr>'}</tbody></table></div></section><p class="foot">{esc(diff['caveat'])}</p></main></body></html>'''


def save_diff(base_path: Path, head_path: Path, output_dir: Path,
              expected_base_sha=None, expected_head_sha=None) -> dict:
    base = load_report(base_path)
    head = load_report(head_path)
    for expected, actual, label in (
        (expected_base_sha, base.get('git', {}).get('head'), 'base'),
        (expected_head_sha, head.get('git', {}).get('head'), 'head'),
    ):
        if expected is not None:
            if not re.fullmatch(r'[0-9a-f]{40,64}', expected):
                raise ValueError('Expected Git SHA must be a full hexadecimal commit ID')
            if actual != expected:
                raise ValueError(f'{label} evidence commit does not match the supplied expected Git SHA')
    result = compare_reports(base, head)
    output_dir.mkdir(parents=True, exist_ok=True)
    core.write_json(output_dir / 'pr-diff.json', result)
    atomic_text(output_dir / 'pr-diff.md', diff_markdown(result))
    atomic_text(output_dir / 'pr-diff.html', diff_html(result))
    return result
