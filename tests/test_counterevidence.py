"""Real local receipt execution with synthetic environment migration labels."""
import sys
import tempfile
import unittest
from pathlib import Path

from raee_lite.core import init, add_requirement, run_check, get_manifest, write_json, MANIFEST, LEDGER, read_json, fingerprint
from raee_lite.contracts import set_expectation, assess_contracts
from raee_lite.evidence_binding import current_environment


class CounterEvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'app.py').write_text('def check(x): return bool(x)\n')
        (self.root / 'test_app.py').write_text('assert 1 == 1\n')
        init(self.root)
        self.rid = add_requirement(self.root, 'Signup rejects invalid addresses')
        set_expectation(self.root, self.rid, 'unit')
        run_check(self.root, self.rid, [sys.executable, '-c', 'pass'], 15, kind='unit')

    def status(self, target=None):
        return assess_contracts(self.root, fingerprint(self.root),
                                target_environment=target)[0]['evidence_by_kind'][0]['state']

    def test_original_receipt_bound(self):
        self.assertEqual(self.status(), 'OBSERVED_PASS')

    def test_requirement_text_change_revokes(self):
        m = get_manifest(self.root)
        m['requirements'][0]['description'] = 'Signup validates internationalized domains'
        write_json(self.root / MANIFEST, m)
        self.assertEqual(self.status(), 'INTENT_CHANGED')

    def test_weakened_test_revokes(self):
        (self.root / 'test_app.py').write_text('assert True\n')
        self.assertEqual(self.status(), 'STALE')

    def test_same_source_retains(self):
        (self.root / 'test_app.py').write_text('assert 1 == 1\n')
        self.assertEqual(self.status(), 'OBSERVED_PASS')

    def test_other_os_requires_revalidation(self):
        env = current_environment()
        env['os'] = 'Windows-11-SYNTHETIC'
        self.assertEqual(self.status(env), 'ENVIRONMENT_SHIFT_UNVERIFIED')
        self.assertEqual(self.status(current_environment()), 'OBSERVED_PASS')

    def test_other_python_requires_revalidation(self):
        env = current_environment()
        env['python'] = '3.10.0-SYNTHETIC'
        self.assertEqual(self.status(env), 'ENVIRONMENT_SHIFT_UNVERIFIED')

    def test_legacy_receipt_unbound(self):
        ledger = read_json(self.root / LEDGER)
        ledger['runs'][-1].pop('requirement_digest')
        write_json(self.root / LEDGER, ledger)
        self.assertEqual(self.status(), 'INTENT_UNBOUND')

    def test_partial_source_does_not_pass(self):
        src = fingerprint(self.root)
        src['skipped'] = [{'file': 'hidden.bin', 'reason': 'file_size_limit'}]
        self.assertEqual(assess_contracts(self.root, src)[0]['evidence_by_kind'][0]['state'], 'PARTIAL')

    def test_new_failure_supersedes_earlier_pass(self):
        run_check(self.root, self.rid, [sys.executable, '-c', 'raise SystemExit(3)'], 15, kind='unit')
        self.assertEqual(self.status(), 'FAILED')

    def test_new_scope_remains_unverified(self):
        set_expectation(self.root, self.rid, 'e2e')
        value = assess_contracts(self.root, fingerprint(self.root))[0]
        self.assertEqual(value['status'], 'GAPS')
        self.assertIn('MISSING', [x['state'] for x in value['evidence_by_kind']])


if __name__ == '__main__':
    unittest.main()
