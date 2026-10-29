"""Privacy-constrained, reproducible agent-transcript compatibility evaluation.

Only explicitly selected local JSONL files are parsed. Raw logs, prompts, commands,
filenames, session IDs and excerpts are never placed in the output summary.
The output is an *aggregated parser benchmark*, NOT a software test attestation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import argparse
import json
import os
import re
import stat
import tempfile

from .agent_logs import import_log, IMPORTS
from . import core
from .safe_io import write_json

MAX_INDEX = 2_000_000
MAX_CASES = 250
ID = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
KINDS = frozenset(('unit', 'e2e', 'build', 'lint', 'typecheck', 'unknown'))
PROVIDERS = frozenset(('claude', 'codex'))
PROVENANCE = frozenset(('synthetic', 'public-documentation', 'consented-real'))


def _read_index(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INDEX:
        raise ValueError('Corpus index must be a regular, non-symlink JSON file <=2 MB')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_INDEX:
            raise ValueError('Invalid corpus index')
        with os.fdopen(fd, 'rb') as f:
            data = json.load(f)
    except BaseException:
        try: os.close(fd)
        except OSError: pass
        raise
    if not isinstance(data, dict) or data.get('schema') != 'raee-corpus-v1':
        raise ValueError('Unsupported corpus schema')
    cases = data.get('cases')
    if not isinstance(cases, list) or not 0 < len(cases) <= MAX_CASES:
        raise ValueError('Corpus requires 1..250 cases')
    return data


def _case_file(index: Path, relative: str) -> Path:
    # Restrict all filenames to simple local fixture names to avoid path traversal.
    if not isinstance(relative, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}\.jsonl', relative):
        raise ValueError('A case path must be a simple .jsonl filename within the corpus')
    source = index.parent / relative
    if source.is_symlink() or not source.is_file() or source.parent.resolve() != index.parent.resolve():
        raise ValueError('Corpus log is unavailable or is a symbolic link')
    return source


def _div(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def evaluate(index: Path) -> dict:
    index = Path(index)
    cases = _read_index(index)['cases']
    totals = Counter()
    by_provider = defaultdict(Counter)
    by_origin = defaultdict(Counter)
    diagnostics = []
    seen_ids = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError('Each corpus case must be an object')
        cid = case.get('id')
        provider, provenance = case.get('provider'), case.get('provenance')
        if not isinstance(cid, str) or not ID.fullmatch(cid) or cid in seen_ids:
            raise ValueError('Invalid or duplicate opaque case id')
        seen_ids.add(cid)
        if provider not in PROVIDERS or provenance not in PROVENANCE:
            raise ValueError('Unsupported provider or provenance')
        if provenance == 'consented-real' and case.get('consent_confirmed') is not True:
            raise ValueError('Real logs require explicit collection/processing consent')
        expected = case.get('expected')
        if not isinstance(expected, list) or len(expected) > 1000:
            raise ValueError('Expected observations must be a bounded list')
        expected_pairs = []
        for row in expected:
            if not isinstance(row, dict) or row.get('kind') not in KINDS:
                raise ValueError('Invalid expected check kind')
            code = row.get('exit_code')
            if code is not None and (type(code) is not int or not -100000 <= code <= 100000):
                raise ValueError('Invalid expected exit code')
            expected_pairs.append((row['kind'], code))
        src = _case_file(index, case.get('file'))
        key = (provider, provenance)
        with tempfile.TemporaryDirectory(prefix='raee-corpus-') as d:
            try:
                outcome = import_log(Path(d), src, provider)
                data = core.read_json(Path(d) / IMPORTS, {'observations': []})
                observed_pairs = [(e.get('check_kind_hint'), e.get('log_exit_code')) for e in data.get('observations', [])]
            except (ValueError, OSError, TypeError, KeyError, RecursionError):
                totals['parser_errors'] += 1
                by_provider[provider]['parser_errors'] += 1
                by_origin[provenance]['parser_errors'] += 1
                diagnostics.append({'id': cid, 'provider': provider, 'provenance': provenance,
                                    'status': 'PARSER_ERROR', 'expected_count': len(expected_pairs)})
                continue
        correct = sum((Counter(expected_pairs) & Counter(observed_pairs)).values())
        fp, fn = len(observed_pairs) - correct, len(expected_pairs) - correct
        metrics = {'exact_sessions': int(Counter(expected_pairs) == Counter(observed_pairs)),
                   'parsed_sessions': 1, 'expected_events': len(expected_pairs),
                   'parsed_events': len(observed_pairs), 'tp': correct, 'fp': fp, 'fn': fn,
                   'unknown_exit_events': sum(x[1] is None for x in observed_pairs),
                   'malformed_lines': outcome['skipped_malformed_lines'],
                   'oversize_lines': outcome['skipped_oversize_lines'],
                   'unmatched_calls': outcome['unmatched_pending_calls']}
        for k, value in metrics.items():
            totals[k] += value
            by_provider[provider][k] += value
            by_origin[provenance][k] += value
        diagnostics.append({'id': cid, 'provider': provider, 'provenance': provenance,
                            'status': 'EXACT' if metrics['exact_sessions'] else 'MISMATCH',
                            'expected_count': len(expected_pairs), 'observed_count': len(observed_pairs),
                            'matched': correct, 'extra': fp, 'missed': fn})
    totals['cases'] = len(cases)
    for provenance in PROVENANCE:
        by_origin[provenance]['cases'] = sum(c.get('provenance') == provenance for c in cases)
    for provider in PROVIDERS:
        by_provider[provider]['cases'] = sum(c.get('provider') == provider for c in cases)

    def finish(m):
        m = dict(m)
        m['session_exact_match_rate'] = _div(m.get('exact_sessions', 0), m.get('cases', 0))
        m['event_precision'] = _div(m.get('tp', 0), m.get('tp', 0) + m.get('fp', 0))
        m['event_recall'] = _div(m.get('tp', 0), m.get('tp', 0) + m.get('fn', 0))
        m['false_discovery_rate'] = _div(m.get('fp', 0), m.get('tp', 0) + m.get('fp', 0))
        m['unknown_exit_rate'] = _div(m.get('unknown_exit_events', 0), m.get('parsed_events', 0))
        return m

    return {'schema': 'raee-validation-summary-v1', 'aggregate': finish(totals),
            'by_provider': {k: finish(v) for k, v in sorted(by_provider.items())},
            'by_provenance': {k: finish(v) for k, v in sorted(by_origin.items()) if v.get('cases')},
            'case_diagnostics': diagnostics,
            'has_consent_based_real_logs': any(c.get('provenance') == 'consented-real' for c in cases),
            'note': 'Synthetic/documentation fixtures never establish field performance. This parser benchmark does not verify software tests. No raw transcripts or commands are included.'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Evaluate explicitly supplied, annotated local agent log cases')
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    # Never print raw source paths or transcript content.
    try:
        result = evaluate(args.index)
        write_json(args.out, result)
        print(json.dumps({'cases': result['aggregate']['cases'], 'exact_rate': result['aggregate']['session_exact_match_rate'],
                          'event_precision': result['aggregate']['event_precision'], 'event_recall': result['aggregate']['event_recall'],
                          'real_logs': result['has_consent_based_real_logs']}))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print('Corpus evaluation rejected: ' + type(exc).__name__)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
