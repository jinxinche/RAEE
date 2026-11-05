"""Reject inconsistent audit joins before presenting role receipts as complete."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

from raee_lite import core, enhanced
from raee_lite.contracts import assess_contracts, set_expectation
from raee_lite.obligation_trace import trace


class TraceIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / 'app.py').write_text('pass\n')
            core.init(root)
            for description in ('Reject invalid input', 'Reject forbidden access'):
                rid = core.add_requirement(root, description)
                set_expectation(root, rid, 'unit')
                core.run_check(root, rid, [sys.executable, '-c', 'pass'], 10, kind='unit')
            cls.original = enhanced.audit(root)

    def setUp(self):
        self.report = copy.deepcopy(self.original)
        self.contract = self.report['evidence_contracts'][0]
        self.row = self.contract['evidence_by_kind'][0]

    def test_valid_report_preserves_graph_and_input(self):
        result = trace(self.report)
        self.assertEqual(self.report, self.original)
        for item in result['requirements']:
            self.assertEqual(item['claim_strength'], 'SELF_DECLARED_ROLE_RECEIPTS_ONLY')
            self.assertEqual(item['unresolved_obligations'], [])
            self.assertIn('SOURCE_FINGERPRINT_MATCHES_CURRENT',
                          [edge['relation'] for edge in item['edges']])
        self.assertFalse(result['semantic_coverage_proven'])

    def test_passing_role_requires_a_nonempty_string_receipt(self):
        for receipt in (None, '', False, 3, [], {}):
            with self.subTest(receipt=receipt):
                self.row['evidence_id'] = receipt
                with self.assertRaises(ValueError):
                    trace(self.report)

    def test_receipt_cannot_cross_requirements_even_when_filtered(self):
        self.row['evidence_id'] = self.report['evidence_contracts'][1]['evidence_by_kind'][0]['evidence_id']
        for selected in (None, self.contract['id']):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                trace(self.report, requirement_id=selected)

    def test_provenance_cannot_supply_another_requirement_or_role(self):
        for field, value in (('requirement', 'R999'), ('declared_kind', 'e2e'),
                             ('origin', 'auto_discovered')):
            with self.subTest(field=field):
                report = copy.deepcopy(self.original)
                report['verification_provenance'][0][field] = value
                with self.assertRaises(ValueError):
                    trace(report)

    def test_passing_role_cannot_hide_invalid_execution_provenance(self):
        for field, value in (('exit_code', False), ('exit_code', 0.0), ('exit_code', '0'),
                             ('exit_code', None), ('exit_code', 7), ('observed_status', 'fail')):
            with self.subTest(field=field, value=value):
                report = copy.deepcopy(self.original)
                report['verification_provenance'][0][field] = value
                with self.assertRaises(ValueError):
                    trace(report)

    def test_changed_requirement_text_cannot_borrow_old_contract(self):
        self.report['requirements'][0]['requirement'] = 'Permit invalid input'
        with self.assertRaises(ValueError):
            trace(self.report)

    def test_duplicate_requirement_contract_or_receipt_ids_are_rejected(self):
        for section in ('requirements', 'evidence_contracts', 'verification_provenance'):
            with self.subTest(section=section):
                report = copy.deepcopy(self.original)
                report[section].append(copy.deepcopy(report[section][0]))
                with self.assertRaises(ValueError):
                    trace(report)

    def test_unknown_contract_requirement_is_rejected(self):
        self.contract['id'] = 'R999'
        with self.assertRaises(ValueError):
            trace(self.report)

    def test_role_evidence_must_exactly_match_declared_roles(self):
        for roles in ([], [self.row, self.row], [{**self.row, 'kind': 'e2e'}]):
            with self.subTest(roles=roles):
                self.contract['evidence_by_kind'] = roles
                with self.assertRaises(ValueError):
                    trace(self.report)

    def test_receipt_cannot_satisfy_two_roles(self):
        self.contract['expected_checks'].append('e2e')
        self.contract['evidence_by_kind'].append({**self.row, 'kind': 'e2e'})
        self.report.pop('verification_provenance')
        with self.assertRaises(ValueError):
            trace(self.report)

    def test_summary_status_cannot_contradict_role_states(self):
        for status in ('GAPS', 'NO_CONTRACT', 'UNKNOWN', None):
            with self.subTest(status=status):
                self.contract['status'] = status
                with self.assertRaises(ValueError):
                    trace(self.report)
        self.contract['status'] = 'RECORDED'
        self.row['state'] = 'FAILED'
        with self.assertRaises(ValueError):
            trace(self.report)

    def test_malformed_role_and_state_shapes_raise_value_error(self):
        for field, values in (('expected_checks', (None, {}, ['unit', 'unit'], ['unknown'])),
                              ('evidence_by_kind', (None, {}, [None]))):
            for value in values:
                with self.subTest(field=field, value=value):
                    report = copy.deepcopy(self.original)
                    report['evidence_contracts'][0][field] = value
                    with self.assertRaises(ValueError):
                        trace(report)
        for state in (None, [], {}, ''):
            with self.subTest(state=state):
                self.row['state'] = state
                with self.assertRaises(ValueError):
                    trace(self.report)

    def test_missing_role_cannot_point_to_a_receipt(self):
        self.contract['status'] = 'GAPS'
        self.row['state'] = 'MISSING'
        with self.assertRaises(ValueError):
            trace(self.report)

    def test_unknown_binding_cannot_claim_global_freshness(self):
        for binding in ('unknown', None, {}):
            with self.subTest(binding=binding):
                self.row['binding_kind'] = binding
                with self.assertRaises(ValueError):
                    trace(self.report)

    def test_truncated_provenance_does_not_invalidate_older_receipts(self):
        self.report['verification_provenance'] = self.report['verification_provenance'][1:]
        self.assertEqual(trace(self.report)['requirements'][0]['unresolved_obligations'], [])

    def test_invalid_evidence_stays_visible_without_freshness_edge(self):
        self.contract['status'] = 'GAPS'
        self.row['state'] = 'INVALID_EVIDENCE'
        self.report['requirements'][0]['state'] = 'INVALID_EVIDENCE'
        self.report['verification_provenance'][0]['exit_code'] = False
        item = trace(self.report)['requirements'][0]
        self.assertEqual(item['claim_strength'], 'UNVERIFIED_REQUIREMENT')
        self.assertEqual(item['unresolved_obligations'][0]['state'], 'INVALID_EVIDENCE')
        self.assertNotIn('SOURCE_FINGERPRINT_MATCHES_CURRENT',
                         [edge['relation'] for edge in item['edges']])

    def test_malformed_ledger_receipt_id_cannot_generate_complete_trace(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            core.init(root)
            rid = core.add_requirement(root, 'Reject invalid input')
            set_expectation(root, rid, 'unit')
            core.run_check(root, rid, [sys.executable, '-c', 'pass'], 10, kind='unit')
            ledger = core.read_json(root / core.LEDGER)
            ledger['runs'][0]['id'] = None
            core.write_json(root / core.LEDGER, ledger)
            report = core.audit(root)
            report['evidence_contracts'] = assess_contracts(root, report['source'])
            with self.assertRaises(ValueError):
                trace(report)

    def test_scoped_receipt_keeps_declared_only_freshness(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / 'app.py').write_text('pass\n')
            core.init(root)
            rid = core.add_requirement(root, 'Reject invalid input')
            set_expectation(root, rid, 'unit')
            core.run_check(root, rid, [sys.executable, '-c', 'pass'], 10,
                           kind='unit', dependency_files=['app.py'])
            report = enhanced.audit(root)
            report['evidence_contracts'] = assess_contracts(
                root, report['source'], dependency_context={rid: {'paths': ['app.py']}})
            relations = [edge['relation'] for edge in trace(report)['requirements'][0]['edges']]
            self.assertIn('DECLARED_INPUTS_MATCH_CURRENT', relations)
            self.assertNotIn('SOURCE_FINGERPRINT_MATCHES_CURRENT', relations)


if __name__ == '__main__':
    unittest.main()
