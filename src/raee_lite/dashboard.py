"""Accessible, static, self-contained dashboard. No CDNs, JS, or network."""
from __future__ import annotations

import html

STYLE = '''
:root{color-scheme:dark;--bg:#0b1220;--panel:#111c2f;--border:#293b53;--text:#edf3fb;--muted:#adbed2;--cyan:#6edbd0;--amber:#ffd18b;--red:#ff999e;--blue:#aabefd}
*{box-sizing:border-box}body{background:radial-gradient(ellipse at 80% -15%,#1f3550 0,transparent 45%),var(--bg);color:var(--text);font:15px/1.55 system-ui,-apple-system,sans-serif;margin:0}
main{max-width:1180px;padding:52px 25px 85px;margin:auto}.eyebrow{color:var(--cyan);letter-spacing:.12em;font-weight:800;font-size:12px;text-transform:uppercase}
h1{font-size:clamp(28px,5vw,46px);letter-spacing:-.04em;margin:8px 0 10px;line-height:1.12}.sub{color:var(--muted);max-width:780px;margin-bottom:27px}
h2{font-size:19px;margin:0 0 12px}.hero{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:20px 0}.kpi,.panel{background:var(--panel);border:1px solid var(--border);border-radius:16px;padding:20px;min-width:0;overflow-wrap:anywhere}.kpi small{display:block;color:var(--muted);font-size:11px;letter-spacing:.08em}.kpi strong{font-size:clamp(16px,2.4vw,25px);display:block;margin-top:6px;overflow-wrap:anywhere}.panel{margin:16px 0}.grid{display:grid;grid-template-columns:1.2fr .8fr;gap:16px}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:13px 12px;text-align:left;border-bottom:1px solid var(--border);vertical-align:top;overflow-wrap:anywhere}th{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}tr:last-child td{border-bottom:0}.chip{border:1px solid var(--border);border-radius:100px;padding:3px 9px;display:inline-block;font-size:11px;font-weight:750}.good{color:var(--cyan)}.bad{color:var(--red)}.warn{color:var(--amber)}.muted{color:var(--muted)}.foot{color:var(--muted);font-size:12px;line-height:1.7;margin-top:30px}.role{display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid var(--border);padding:12px 0}.role:last-child{border:0}.role small{color:var(--muted);max-width:70%}details{border-bottom:1px solid var(--border);padding:10px 0}summary{cursor:pointer;font-weight:600}summary:hover{color:var(--cyan)}.arrow{font-size:24px;align-self:center;color:var(--cyan)}a{color:var(--cyan)}:focus-visible{outline:2px solid var(--cyan);outline-offset:4px}
@media(max-width:780px){.hero{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}.kpi,.panel{padding:15px}main{padding:28px 14px}}
'''


# Bound accepted display data and its escaped expansion before building the page.
MAX_SECTION_ROWS = 2000
MAX_TEXT_CHARS = 10_000
MAX_RENDERED_TEXT_BYTES = 8_000_000
MAX_DISPLAY_ROWS = 10_000
MAX_IMPORTED_RECEIPTS = 25_000  # Matches the transcript importer; only 100 are displayed.
OUTCOMES = frozenset({
    'INSUFFICIENT_EVIDENCE', 'FAILED_CHECK', 'STALE_EVIDENCE', 'EVIDENCE_GAPS',
    'CHECKS_PASSED_WITH_LIMITS', 'AUTOCHECKS_PASSED_WITH_LIMITS',
})
# Make directional formatting visible rather than allowing identifiers to be
# visually reordered. Normal multilingual text remains intact.
BIDI_CONTROLS = str.maketrans({
    chr(code): f'\\u{code:04x}'
    for code in (0x061c, 0x200e, 0x200f, *range(0x202a, 0x202f), *range(0x2066, 0x206a))
})


def _text(value, *, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, str):
        raise ValueError('Invalid dashboard text field')
    if len(value) > MAX_TEXT_CHARS:
        raise ValueError('Dashboard text field exceeds character limit')
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise ValueError('Invalid dashboard Unicode text') from exc


def _rows(container, key, required=(), optional=(), *, limit=MAX_SECTION_ROWS):
    rows = container.get(key, [])
    if not isinstance(rows, list):
        raise ValueError('Invalid dashboard section')
    if len(rows) > limit:
        raise ValueError('Dashboard section exceeds row limit')
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid dashboard row')
        for field in required:
            _text(row.get(field))
        for field in optional:
            _text(row.get(field), nullable=True)
    return rows


def _validate(report):
    """Validate the displayed projection, not the authenticity of its evidence."""
    if not isinstance(report, dict):
        raise ValueError('Invalid dashboard report')
    overall = report.get('overall')
    if not isinstance(overall, str) or overall not in OUTCOMES:
        raise ValueError('Invalid dashboard overall outcome')
    for key in ('version', 'caveat'):
        _text(report.get(key), nullable=True)
    source = report.get('source')
    if not isinstance(source, dict):
        raise ValueError('Invalid dashboard source')
    digest, count = source.get('sha256'), source.get('files')
    if (not isinstance(digest, str) or len(digest) != 64 or
            any(c not in '0123456789abcdef' for c in digest)):
        raise ValueError('Invalid dashboard source fingerprint')
    if type(count) is not int or not 0 <= count <= 2**63 - 1:
        raise ValueError('Invalid dashboard source file count')
    skipped = source.get('skipped', [])
    if (not isinstance(skipped, list) or len(skipped) > MAX_DISPLAY_ROWS or
            any(not isinstance(row, dict) for row in skipped)):
        raise ValueError('Invalid or over-limit dashboard source exclusions')
    requirements = _rows(report, 'requirements', ('id', 'requirement', 'state'))
    automatic = _rows(report, 'automatic_checks', ('kind', 'state'), ('evidence_id',))
    contracts = _rows(report, 'evidence_contracts', ('id', 'requirement'))
    total_rows = len(requirements) + len(automatic) + len(contracts)
    contract_gaps = False
    for contract in contracts:
        checks = _rows(contract, 'evidence_by_kind', ('kind', 'state'))
        gaps = _rows(contract, 'gaps', ('kind', 'reason'))
        total_rows += len(checks) + len(gaps)
        if total_rows > MAX_DISPLAY_ROWS:
            raise ValueError('Dashboard exceeds row budget')
        contract_gaps |= bool(gaps) or any(row['state'] != 'OBSERVED_PASS' for row in checks)
        contract_gaps |= contract.get('status') == 'GAPS'
    agent = report.get('agent_evidence', {})
    if not isinstance(agent, dict):
        raise ValueError('Invalid dashboard agent evidence')
    imported = _rows(agent, 'imported', ('id', 'provider', 'command_family', 'log_status'),
                     limit=MAX_IMPORTED_RECEIPTS)
    total_rows += min(len(imported), 100)
    total_rows += len(_rows(agent, 'explicit', ('requirement', 'evidence_id', 'state', 'rationale')))
    total_rows += len(_rows(report, 'verification_provenance', optional=(
        'id', 'origin', 'requirement', 'declared_kind', 'observed_status', 'isolation_policy')))
    for key in ('boundary_notes', 'discovery_notes'):
        notes = report.get(key, [])
        if not isinstance(notes, list):
            raise ValueError('Invalid dashboard notes')
        if len(notes) > MAX_SECTION_ROWS:
            raise ValueError('Dashboard notes exceed row limit')
        total_rows += len(notes)
        for note in notes:
            _text(note)
    if total_rows > MAX_DISPLAY_ROWS:
        raise ValueError('Dashboard exceeds row budget')
    if overall in ('CHECKS_PASSED_WITH_LIMITS', 'AUTOCHECKS_PASSED_WITH_LIMITS'):
        invalid = bool(skipped) or contract_gaps
        if overall == 'CHECKS_PASSED_WITH_LIMITS':
            invalid |= not requirements or any(r['state'] != 'OBSERVED_PASS' for r in requirements)
            # Discovered but unexecuted checks are advisory when manual evidence
            # passes; this matches the report producer's existing policy.
            invalid |= any(r['state'] not in ('OBSERVED_PASS', 'NOT_RUN') for r in automatic)
        else:
            invalid |= bool(requirements) or not automatic
            invalid |= any(r['state'] != 'OBSERVED_PASS' for r in automatic)
        if invalid:
            raise ValueError('Contradictory passing dashboard outcome')


def render(report: dict) -> str:
    _validate(report)
    rendered_bytes = 0

    def esc(value):
        nonlocal rendered_bytes
        text = str(value if value is not None else '—').translate(BIDI_CONTROLS)
        escaped = html.escape(text, quote=True)
        rendered_bytes += len(escaped.encode('utf-8'))
        if rendered_bytes > MAX_RENDERED_TEXT_BYTES:
            raise ValueError('Dashboard exceeds escaped text byte budget')
        return escaped

    contracts = report.get('evidence_contracts', [])
    entries = [(item['id'], item['requirement'], e['kind'], e['state']) for item in contracts for e in item.get('evidence_by_kind', [])]
    counts = {'pass': sum(x[3] == 'OBSERVED_PASS' for x in entries),
              'imported': len(report.get('agent_evidence', {}).get('imported', []))}
    row_html = ''.join('<tr>' + ''.join(f'<td>{esc(v)}</td>' for v in row) + '</tr>' for row in entries)
    auto = ''.join('<tr>' + ''.join(f'<td>{esc(v)}</td>' for v in (r['kind'], r['state'], r.get('evidence_id'))) + '</tr>' for r in report.get('automatic_checks', []))
    imp = ''.join('<tr>' + ''.join(f'<td>{esc(v)}</td>' for v in (e['id'], e['provider'], e['command_family'], e['log_status'])) + '</tr>' for e in report.get('agent_evidence', {}).get('imported', [])[-100:])
    provenance = ''.join('<tr>' + ''.join(f'<td>{esc(v)}</td>' for v in (e.get('id'), e.get('origin'), e.get('requirement'), e.get('declared_kind'), e.get('observed_status'), e.get('isolation_policy'))) + '</tr>' for e in report.get('verification_provenance', []))
    associations = ''.join('<tr>' + ''.join(f'<td>{esc(v)}</td>' for v in (x['requirement'], x['evidence_id'], x['state'], x['rationale'])) + '</tr>' for x in report.get('agent_evidence', {}).get('explicit', []))
    notes = report.get('boundary_notes', []) + report.get('discovery_notes', [])
    gaps = []
    for item in contracts:
        represented = {gap['kind'] for gap in item.get('gaps', [])}
        for gap in item.get('gaps', []):
            gaps.append(f"{item['id']}: {gap['kind']} — {gap['reason']}")
        for check in item.get('evidence_by_kind', []):
            if check['state'] != 'OBSERVED_PASS' and check['kind'] not in represented:
                gaps.append(f"{item['id']}: {check['kind']} — {check['state']} — No current passing evidence.")
    for r in report.get('requirements', []):
        if r['state'] != 'OBSERVED_PASS':
            gaps.append(f"{r['id']}: {r['state']} — {r['requirement']}")
    for check in report.get('automatic_checks', []):
        if check['state'] != 'OBSERVED_PASS':
            gaps.append(f"Automatic {check['kind']}: {check['state']}")
    counts['gaps'] = len(gaps)
    imported_notice = ''
    if counts['imported'] > 100:
        imported_notice = (f'<p class="warn">Showing the latest 100 of {counts["imported"]} '
                           f'imported receipts; {counts["imported"] - 100} omitted.</p>')
    coverage_notice = ''
    if report['source'].get('skipped'):
        coverage_notice = (f'<p class="warn">Fingerprint coverage incomplete: '
                           f'{len(report["source"]["skipped"])} source entries skipped.</p>')
    issues = ''.join(f'<details><summary>{esc(note)}</summary><p class="muted">Requires independent investigation or an explicitly executed check.</p></details>' for note in gaps)
    caveat = esc(report.get('caveat', ''))
    roles = [('INTENT', 'User-authored requirements and expectations'), ('CHANGE', 'Content fingerprint, not functional correctness'),
             ('VERIFICATION', 'Local receipts and separately identified imported transcript claims'),
             ('ENVIRONMENT', 'Environment context; imports do not prove current environment'),
             ('BOUNDARY', 'Unknown, missing and stale evidence remain visible')]
    role_html = ''.join(f'<div class="role"><strong>{esc(k)}</strong><small>{esc(v)}</small></div>' for k,v in roles)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>RAEE-Lite · Evidence Dashboard</title><style>{STYLE}</style></head><body><main><div class="eyebrow">RAEE-Lite v{esc(report.get('version'))} / Local Evidence Dashboard</div><h1>Did the checks actually prove it?</h1><p class="sub">Role-aware evidence for AI-assisted coding. A green process exit is not a guarantee that requirements are satisfied.</p><section class="hero"><div class="kpi"><small>OVERALL OBSERVATION</small><strong>{esc(report['overall'])}</strong></div><div class="kpi"><small>OBSERVED CONTRACT CHECKS</small><strong class="good">{counts['pass']}</strong></div><div class="kpi"><small>LISTED EVIDENCE GAPS</small><strong class="warn">{counts['gaps']}</strong></div><div class="kpi"><small>IMPORTED AGENT LOG RECEIPTS</small><strong>{counts['imported']}</strong></div></section><section class="grid"><div class="panel"><h2>Verification matrix</h2><p class="muted">Evidence scopes are self-declared; unbound agent logs cannot satisfy a contract.</p><div class="scroll"><table><thead><tr><th>ID</th><th>Requirement</th><th>Expected kind</th><th>Observed state</th></tr></thead><tbody>{row_html or '<tr><td colspan="4">No explicit contracts yet. Add a requirement and expect a check scope.</td></tr>'}</tbody></table></div></div><div class="panel"><h2>Five evidence roles</h2>{role_html}</div></section><section class="panel"><h2>Evidence gaps requiring action</h2>{issues or '<p class="muted">No listed evidence gaps; this is not a software correctness guarantee.</p>'}</section><section class="panel"><h2>Discovered check results</h2><div class="scroll"><table><thead><tr><th>Type</th><th>State</th><th>Receipt</th></tr></thead><tbody>{auto or '<tr><td colspan="3">No discovered checks</td></tr>'}</tbody></table></div></section><section class="panel"><h2>Agent transcript receipts</h2><p class="muted">These are historical log claims, not independent proof of execution or current source applicability. Only safe command families and exit metadata are stored.</p>{imported_notice}<div class="scroll"><table><thead><tr><th>Evidence ID</th><th>Provider</th><th>Check family</th><th>Log status</th></tr></thead><tbody>{imp or '<tr><td colspan="4">No agent logs imported</td></tr>'}</tbody></table></div></section><section class="panel"><h2>Verification provenance</h2><p class="muted">LOCAL, ISOLATED REPLAY and AGENT HISTORICAL LOGS are different trust roles. Docker limits are not a VM safety guarantee. This display is local evidence, not a signed attestation. Historical process outcomes do not establish current applicability.</p><div class="scroll"><table><thead><tr><th>ID</th><th>Origin</th><th>Requirement</th><th>Kind</th><th>Recorded process status</th><th>Isolation</th></tr></thead><tbody>{provenance or '<tr><td colspan="6">No locally executed evidence</td></tr>'}</tbody></table></div></section><section class="panel"><h2>User-associated evidence</h2><p class="muted">Associations explain relevance, but never confer verification by themselves.</p><div class="scroll"><table><thead><tr><th>Requirement</th><th>Receipt</th><th>State</th><th>Rationale</th></tr></thead><tbody>{associations or '<tr><td colspan="4">No user associations yet</td></tr>'}</tbody></table></div></section><section class="panel"><h2>Applicability limits</h2>{coverage_notice}{''.join(f'<details><summary>{esc(s)}</summary></details>' for s in notes) or '<p class="muted">No additional notes</p>'}</section><p class="foot">Source fingerprint: {esc(report['source']['sha256'][:18])} · {esc(report['source']['files'])} source files hashed.<br>{caveat}<br>Offline report; no scripts, trackers or remote dependencies. Do not share evidence artifacts if requirement descriptions contain private information.</p></main></body></html>'''
