"""Proof obligation trace tests: only declared roles count, no automatic proofs."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from raee_lite.cli import main
from raee_lite.core import init, add_requirement, run_check
from raee_lite.contracts import set_expectation
from raee_lite.enhanced import audit
from raee_lite.obligation_trace import trace


class TraceTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)
        (self.root / 'app.py').write_text('print("original")\n')
        init(self.root)
        self.rid = add_requirement(self.root, 'Signup rejects invalid addresses')

    def test_no_contract_is_not_proven_even_after_green_exit(self):
        run_check(self.root, self.rid, [sys.executable, '-c', 'pass'], 15)
        v = trace(audit(self.root))['requirements'][0]
        self.assertEqual(v['observed_state'], 'OBSERVED_PASS')
        self.assertEqual(v['claim_strength'], 'UNVERIFIED_REQUIREMENT')
        self.assertEqual(v['unresolved_obligations'][0]['state'], 'NO_CONTRACT')
        self.assertIn('WITHOUT_COMPLETE', v['warnings'][1])

    def test_missing_contract_is_explicit_obligation_not_completeness(self):
        set_expectation(self.root, self.rid, 'unit')
        v = trace(audit(self.root))['requirements'][0]
        self.assertEqual(v['unresolved_obligations'][0]['state'], 'MISSING')
        self.assertFalse(any(n['role'] == 'verification_receipt' for n in v['nodes']))
        self.assertFalse(v['claim_strength'].startswith('PROVEN'))

    def test_matching_green_receipt_has_no_semantic_proof(self):
        set_expectation(self.root, self.rid, 'unit')
        run_check(self.root, self.rid, [sys.executable, '-c', 'pass'], 15, kind='unit')
        report = trace(audit(self.root))
        v = report['requirements'][0]
        self.assertEqual(v['contract_status'], 'RECORDED')
        self.assertEqual(v['claim_strength'], 'SELF_DECLARED_ROLE_RECEIPTS_ONLY')
        self.assertEqual(v['unresolved_obligations'], [])
        self.assertFalse(report['semantic_coverage_proven'])
        self.assertEqual([e['relation'] for e in v['edges']],
                         ['EXPECTED_ROLE_AS_DECLARED', 'MATCHED_BY_SELF_DECLARED_KIND', 'SOURCE_FINGERPRINT_MATCHES_CURRENT'])

    def test_failed_last_check_not_earlier_green(self):
        set_expectation(self.root, self.rid, 'integration')
        run_check(self.root, self.rid, [sys.executable, '-c', 'pass'], 15, kind='integration')
        run_check(self.root, self.rid, [sys.executable, '-c', 'raise SystemExit(3)'], 15, kind='integration')
        v = trace(audit(self.root))['requirements'][0]
        self.assertEqual(v['unresolved_obligations'][0]['state'], 'FAILED')
        self.assertNotIn('SOURCE_FINGERPRINT_MATCHES_CURRENT', [e['relation'] for e in v['edges']])

    def test_stale_not_mislabeled_as_current_proof(self):
        set_expectation(self.root, self.rid, 'unit')
        run_check(self.root, self.rid, [sys.executable, '-c', 'pass'], 15, kind='unit')
        (self.root / 'app.py').write_text('print("modified")\n')
        v = trace(audit(self.root))['requirements'][0]
        self.assertEqual(v['unresolved_obligations'][0]['state'], 'STALE')
        self.assertNotIn('SOURCE_FINGERPRINT_MATCHES_CURRENT', [e['relation'] for e in v['edges']])

    def test_missing_independent_scope_blocks_claim(self):
        set_expectation(self.root, self.rid, 'unit')
        set_expectation(self.root, self.rid, 'e2e')
        run_check(self.root, self.rid, [sys.executable, '-c', 'pass'], 15, kind='unit')
        v = trace(audit(self.root))['requirements'][0]
        self.assertEqual(v['claim_strength'], 'UNVERIFIED_REQUIREMENT')
        self.assertEqual([x['scope'] for x in v['unresolved_obligations']], ['e2e'])

    def test_cli_json_and_unknown_requirement(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status = main(['--project', str(self.root), 'trace', '--for', self.rid, '--json'])
        data = json.loads(buf.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(data['requirements'][0]['requirement_id'], self.rid)
        self.assertFalse(data['semantic_coverage_proven'])
        with self.assertRaises(SystemExit) as ex:
            main(['--project', str(self.root), 'trace', '--for', 'R404'])
        self.assertEqual(ex.exception.code, 2)

    def test_read_only_and_no_project_execution(self):
        files_before = {p.relative_to(self.root).as_posix(): p.read_bytes()
                        for p in self.root.rglob('*') if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--project', str(self.root), 'trace']), 0)
        files_after = {p.relative_to(self.root).as_posix(): p.read_bytes()
                       for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(files_before, files_after)
        self.assertFalse((self.root / '.raee' / 'report.html').exists())


if __name__ == '__main__':
    unittest.main()
