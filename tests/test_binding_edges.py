"""Bounded negative controls for command identity and binding metadata."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite import core, enhanced
from raee_lite.associations import link_evidence
from raee_lite.contracts import set_expectation
from raee_lite.discovery import Check
from raee_lite.evidence_binding import evaluate_binding, evaluate_environment, valid_execution


class BindingEdgesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / 'app.py').write_text('pass\n', encoding='utf-8')
        core.init(self.root)
        self.rid = core.add_requirement(self.root, 'Exact behavior')
        set_expectation(self.root, self.rid, 'unit')
        self.command = [sys.executable, '-c', 'pass', 'café']
        self.receipt = core.run_check(self.root, self.rid, self.command, 10, kind='unit')
        link_evidence(self.root, self.rid, self.receipt['id'], 'Explicit binding test fixture')

    def replace_receipt(self, **fields):
        receipt = {**copy.deepcopy(self.receipt), **fields}
        core.write_json(self.root / core.LEDGER, {'schema': 1, 'runs': [receipt]})
        return receipt

    def assert_invalid_public_views(self):
        report = enhanced.audit(self.root)
        self.assertEqual(report['requirements'][0]['state'], 'INVALID_EVIDENCE')
        self.assertEqual(report['evidence_contracts'][0]['evidence_by_kind'][0]['state'],
                         'INVALID_EVIDENCE')
        self.assertEqual(report['agent_evidence']['explicit'][0]['state'], 'INVALID_EVIDENCE')
        self.assertFalse(enhanced.is_passing(report))

    def test_numeric_command_fingerprint_revokes_public_passes(self):
        self.replace_receipt(command_sha256=int('1' * 64))
        self.assert_invalid_public_views()

    def test_changed_cleartext_command_revokes_public_passes(self):
        self.replace_receipt(command=[sys.executable, '-c', 'raise SystemExit(7)'])
        self.assert_invalid_public_views()

    def test_wrong_origin_or_extended_redaction_cannot_bypass_command_binding(self):
        for fields in (
            {'command': ['[isolated command redacted]']},
            {'origin': 'isolated_replay'},
            {'command': ['[explicit command redacted]', 'extra']},
        ):
            with self.subTest(fields=fields):
                self.replace_receipt(**fields)
                self.assert_invalid_public_views()

    def test_matching_cleartext_command_preserves_public_passes(self):
        self.replace_receipt(command=self.command)
        report = enhanced.audit(self.root)
        self.assertEqual(report['requirements'][0]['state'], 'OBSERVED_PASS')
        self.assertEqual(report['evidence_contracts'][0]['status'], 'RECORDED')
        self.assertEqual(report['agent_evidence']['explicit'][0]['state'],
                         'OBSERVED_PASS_SELF_LINKED')
        self.assertTrue(enhanced.is_passing(report))

    def test_current_redacted_receipt_formats_remain_valid(self):
        self.assertTrue(valid_execution(self.receipt))
        for origin, marker in (('local_explicit', '[explicit command redacted]'),
                               ('isolated_replay', '[isolated command redacted]')):
            with self.subTest(origin=origin):
                receipt = {**self.receipt, 'origin': origin, 'command': [marker]}
                self.assertTrue(valid_execution(receipt))
                receipt.update(observed_exit_code=7, observed_status='fail')
                self.assertTrue(valid_execution(receipt))

    def test_command_fingerprint_requires_a_hex_string(self):
        for digest in (None, False, 1.0, int('1' * 64), [], {}, '', 'f' * 63,
                       'f' * 65, 'g' * 64, 'F' * 64, 'f' * 64 + '\n'):
            with self.subTest(digest=digest):
                self.assertFalse(valid_execution({**self.receipt, 'command_sha256': digest}))

    def test_automatic_receipts_allow_absent_but_not_inconsistent_fingerprints(self):
        check = Check('auto:binding', 'test', tuple(self.command), 'fixture')
        receipt = enhanced.run_discovered(self.root, check)
        self.assertNotIn('command_sha256', receipt)
        self.assertTrue(valid_execution(receipt))
        digest = hashlib.sha256(json.dumps(self.command).encode('utf-8')).hexdigest()
        self.assertTrue(valid_execution({**receipt, 'command_sha256': digest}))
        for malformed in (None, int('1' * 64), '0' * 64):
            with self.subTest(digest=malformed):
                ledger = core.read_json(self.root / core.LEDGER)
                ledger['runs'][-1]['command_sha256'] = malformed
                core.write_json(self.root / core.LEDGER, ledger)
                with patch('raee_lite.enhanced.discover', return_value=([check], [])):
                    report = enhanced.audit(self.root)
                self.assertEqual(report['automatic_checks'][0]['state'], 'INVALID_EVIDENCE')
                self.assertFalse(enhanced.is_passing(report))

    def test_nul_argv_is_invalid_even_with_matching_fingerprint(self):
        for command in (['python\x00'], ['python', 'bad\x00argument']):
            with self.subTest(command=command):
                digest = hashlib.sha256(json.dumps(command).encode('utf-8')).hexdigest()
                self.assertFalse(valid_execution({**self.receipt, 'command': command,
                                                  'command_sha256': digest}))

    def test_malformed_environments_never_match_even_when_identical(self):
        valid = self.receipt['environment']
        malformed = (None, [], {}, True, 3, 'environment',
                     {'os': {}, 'python': []}, {'os': valid['os'], 'python': 3.11},
                     {'os': ' ', 'python': valid['python']})
        for env in malformed:
            with self.subTest(environment=env):
                self.assertEqual(evaluate_environment({'environment': env}, env),
                                 'ENVIRONMENT_UNBOUND')
                if env is not None:  # None deliberately selects the current environment.
                    self.assertEqual(evaluate_environment(self.receipt, env),
                                     'ENVIRONMENT_SHIFT_UNVERIFIED')

    def test_requirement_identity_remains_exact(self):
        self.assertEqual(evaluate_binding(self.receipt, 'Exact behavior'), 'BINDING_MATCHED')
        for description in ('exact behavior', 'Exact behavior ', ' Exact behavior'):
            with self.subTest(description=description):
                self.assertEqual(evaluate_binding(self.receipt, description), 'INTENT_CHANGED')
        for digest in (None, False, [], {}, int('1' * 64)):
            with self.subTest(digest=digest):
                self.assertEqual(evaluate_binding({**self.receipt, 'requirement_digest': digest},
                                                  'Exact behavior'), 'INTENT_UNBOUND')


if __name__ == '__main__':
    unittest.main()
