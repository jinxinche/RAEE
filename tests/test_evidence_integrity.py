"""Negative controls for public reports and ambiguous receipt inputs."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite import core, enhanced
from raee_lite.contracts import assess_contracts, set_expectation
from raee_lite.discovery import Check
from raee_lite.pr_diff import compare_reports


class EvidenceIntegrityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / 'app.py').write_text('pass\n')
        core.init(self.root)
        self.rid = core.add_requirement(self.root, 'Exact intent')
        core.run_check(self.root, self.rid, [sys.executable, '-c', 'pass'], 10)

    def mutate(self, change):
        ledger = core.read_json(self.root / core.LEDGER)
        change(ledger['runs'][-1])
        core.write_json(self.root / core.LEDGER, ledger)

    def test_uncontracted_intent_change_revokes_public_report(self):
        m = core.get_manifest(self.root)
        m['requirements'][0]['description'] = 'Changed intent'
        core.write_json(self.root / core.MANIFEST, m)
        self.assertEqual(core.audit(self.root)['requirements'][0]['state'], 'INTENT_CHANGED')
        self.assertFalse(enhanced.is_passing(enhanced.audit(self.root)))

    def test_default_environment_is_checked_without_explicit_target(self):
        self.mutate(lambda r: r['environment'].update(os='different OS'))
        self.assertEqual(core.audit(self.root)['requirements'][0]['state'], 'ENVIRONMENT_SHIFT_UNVERIFIED')
        self.assertFalse(enhanced.is_passing(enhanced.audit(self.root)))

    def test_missing_environment_is_not_an_implicit_match(self):
        self.mutate(lambda r: r.pop('environment'))
        self.assertEqual(core.audit(self.root)['requirements'][0]['state'], 'ENVIRONMENT_UNBOUND')

    def test_malformed_execution_metadata_cannot_pass(self):
        original = core.read_json(self.root / core.LEDGER)['runs'][-1]
        variants = [dict(command=[]), dict(command_sha256=None),
                    dict(observed_status='infrastructure_error', error='TimeoutExpired'),
                    dict(role='intent'), dict(origin='agent_log')]
        for fields in variants:
            with self.subTest(fields=fields):
                self.mutate(lambda r: (r.clear(), r.update(copy.deepcopy(original)), r.update(fields)))
                self.assertEqual(core.audit(self.root)['requirements'][0]['state'], 'INVALID_EVIDENCE')
                self.assertFalse(enhanced.is_passing(enhanced.audit(self.root), strict=True))

    def test_invalid_automatic_evidence_blocks_passing_manual_requirements(self):
        check = Check('auto:test', 'test', (sys.executable, '-c', 'raise SystemExit(1)'), 'fixture')
        enhanced.run_discovered(self.root, check)
        for fields in ({'observed_exit_code': None}, {'observed_exit_code': 1, 'environment': {}}):
            self.mutate(lambda r: r.update(fields))
            with patch('raee_lite.enhanced.discover', return_value=([check], [])):
                self.assertFalse(enhanced.is_passing(enhanced.audit(self.root), strict=True))

    def test_null_scope_never_falls_back_to_global_receipt(self):
        set_expectation(self.root, self.rid, 'unit')
        self.mutate(lambda r: r.update(dependency_scope=None, declared_kind='unit'))
        self.assertEqual(core.audit(self.root)['requirements'][0]['state'], 'SCOPE_UNBOUND')
        self.assertEqual(assess_contracts(self.root, core.fingerprint(self.root))[0]['evidence_by_kind'][0]['state'], 'SCOPE_UNBOUND')

    def test_changed_after_scope_declaration_is_retracted(self):
        set_expectation(self.root, self.rid, 'unit')
        core.run_check(self.root, self.rid, [sys.executable, '-c', 'pass'], 10,
                       kind='unit', dependency_files=['app.py'])
        for field, value in (('paths', ['different.py']), ('external_keys', ['new'])):
            with self.subTest(field=field):
                self.mutate(lambda r: r['dependency_scope']['after'].update({field: value}))
                report = assess_contracts(self.root, core.fingerprint(self.root),
                    dependency_context={self.rid: {'paths': ['app.py']}})
                self.assertEqual(report[0]['evidence_by_kind'][0]['state'], 'SCOPE_DECLARATION_CHANGED')
                self.mutate(lambda r: r['dependency_scope'].update(after=copy.deepcopy(r['dependency_scope']['before'])))

    def test_deleted_omitted_dependency_does_not_restore_old_pass(self):
        (self.root / 'app.py').write_text('import helper\nassert helper.VALUE == 1\n')
        (self.root / 'helper.py').write_text('VALUE = 1\n')
        set_expectation(self.root, self.rid, 'unit')
        receipt = core.run_check(self.root, self.rid, [sys.executable, 'app.py'], 10,
                                 kind='unit', dependency_files=['app.py'])
        self.assertEqual(receipt['observed_exit_code'], 0)
        (self.root / 'helper.py').unlink()
        report = assess_contracts(self.root, core.fingerprint(self.root),
            dependency_context={self.rid: {'paths': ['app.py']}})
        self.assertEqual(report[0]['evidence_by_kind'][0]['state'], 'SCOPE_INCOMPLETE')

    def test_legacy_scope_without_historical_audit_remains_uncertain(self):
        set_expectation(self.root, self.rid, 'unit')
        core.run_check(self.root, self.rid, [sys.executable, '-c', 'pass'], 10,
                       kind='unit', dependency_files=['app.py'])
        self.mutate(lambda r: r['dependency_scope'].pop('audit_before'))
        report = assess_contracts(self.root, core.fingerprint(self.root),
            dependency_context={self.rid: {'paths': ['app.py']}})
        self.assertEqual(report[0]['evidence_by_kind'][0]['state'], 'SCOPE_AUDIT_UNCERTAIN')

    def test_environment_values_require_strings(self):
        self.mutate(lambda r: r.update(environment={'os': {'fake': True}, 'python': 3.15}))
        self.assertEqual(core.audit(self.root)['requirements'][0]['state'], 'ENVIRONMENT_UNBOUND')

    def test_boolean_float_and_missing_exit_codes_never_pass(self):
        set_expectation(self.root, self.rid, 'unit')
        for value in (False, 0.0, '0', None):
            with self.subTest(value=value):
                self.mutate(lambda r: r.update(observed_exit_code=value, declared_kind='unit'))
                self.assertEqual(core.audit(self.root)['requirements'][0]['state'], 'INVALID_EVIDENCE')
                state = assess_contracts(self.root, core.fingerprint(self.root))[0]['evidence_by_kind'][0]['state']
                self.assertEqual(state, 'INVALID_EVIDENCE')

    def test_legacy_intent_absent_never_passes_public_report(self):
        self.mutate(lambda r: r.pop('requirement_digest'))
        self.assertFalse(enhanced.is_passing(enhanced.audit(self.root)))

    def test_scoped_receipt_cannot_fall_back_to_generic_global_pass(self):
        core.run_check(self.root, self.rid, [sys.executable, '-c', 'pass'], 10, dependency_files=['app.py'])
        self.assertEqual(core.audit(self.root)['requirements'][0]['state'], 'SCOPE_CONTEXT_REQUIRED')
        self.assertFalse(enhanced.is_passing(enhanced.audit(self.root)))

    def test_auto_discovered_role_cannot_impersonate_a_requirement(self):
        self.mutate(lambda r: r.update(origin='auto_discovered'))
        self.assertEqual(core.audit(self.root)['requirements'][0]['state'], 'UNTESTED')

    def test_auto_receipt_is_invalid_after_environment_change(self):
        check = Check('auto:test', 'test', (sys.executable, '-c', 'pass'), 'fixture')
        enhanced.run_discovered(self.root, check)
        self.mutate(lambda r: r['environment'].update(python='0.0.0'))
        with patch('raee_lite.enhanced.discover', return_value=([check], [])):
            row = enhanced.audit(self.root)['automatic_checks'][0]
        self.assertEqual(row['state'], 'ENVIRONMENT_SHIFT_UNVERIFIED')

    def test_duplicate_requirement_ids_are_rejected(self):
        m = core.get_manifest(self.root)
        m['requirements'].append(dict(m['requirements'][0]))
        core.write_json(self.root / core.MANIFEST, m)
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            core.get_manifest(self.root)

    def test_full_requirement_list_is_not_corrupted_by_append(self):
        m = core.get_manifest(self.root)
        m['requirements'] = [{'id': f'R{i}', 'description': 'bounded'} for i in range(500)]
        core.write_json(self.root / core.MANIFEST, m)
        before = (self.root / core.MANIFEST).read_bytes()
        with self.assertRaises(ValueError):
            core.add_requirement(self.root, 'one too many')
        self.assertEqual((self.root / core.MANIFEST).read_bytes(), before)

    def test_full_ledger_refuses_before_executing(self):
        core.write_json(self.root / core.LEDGER, {'schema': 1, 'runs': [{}] * 2000})
        with patch('raee_lite.core.bounded_run') as execute:
            with self.assertRaisesRegex(ValueError, 'limit'):
                core.run_check(self.root, self.rid, [sys.executable, '-c', 'pass'], 10)
            execute.assert_not_called()
        self.assertEqual(len(core.read_json(self.root / core.LEDGER)['runs']), 2000)

    def test_report_diff_preserves_case_sensitive_intent(self):
        base = {'requirements': [{'id': 'R1', 'requirement': 'Use API', 'state': 'OBSERVED_PASS'}]}
        head = copy.deepcopy(base)
        head['requirements'][0]['requirement'] = 'use api'
        self.assertEqual(compare_reports(base, head)['regressions'], 1)

    def test_duplicate_report_roles_cannot_hide_a_regression(self):
        base = {'requirements': [{'id': 'R1', 'requirement': 'same', 'state': 'OBSERVED_PASS'}]}
        head = copy.deepcopy(base)
        head['requirements'].insert(0, {'id': 'R2', 'requirement': 'same', 'state': 'FAILED'})
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            compare_reports(base, head)

    def test_report_markdown_cannot_overwrite_link_target(self):
        target = self.root / 'private.txt'
        target.write_text('preserve')
        (self.root / '.raee/report.md').symlink_to(target)
        with self.assertRaises(ValueError):
            core.save_report(self.root)
        self.assertEqual(target.read_text(), 'preserve')
