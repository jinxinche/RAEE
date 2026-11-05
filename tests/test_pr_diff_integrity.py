"""Base/head negative controls for PR evidence comparison and its CLI gate."""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite import core, enhanced
from raee_lite.cli import main
from raee_lite.contracts import set_expectation
from raee_lite.pr_diff import compare_reports, load_report, save_diff


class PRDiffIntegrityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.project = self.root / 'project'
        self.project.mkdir()
        (self.project / 'app.py').write_text('pass\n', encoding='utf-8')
        core.init(self.project)
        self.rid = core.add_requirement(self.project, 'Login works')
        set_expectation(self.project, self.rid, 'unit')
        self.run_check('unit')
        self.base = enhanced.audit(self.project)
        self.assertTrue(enhanced.is_passing(self.base))

    def run_check(self, kind, code='pass'):
        return core.run_check(self.project, self.rid, [sys.executable, '-c', code], 10, kind=kind)

    def write_pair(self, base, head):
        paths = self.root / 'base.json', self.root / 'head.json'
        # Snapshots live outside the fixture's fingerprinted source directory.
        for path, report in zip(paths, (base, head)):
            path.write_text(json.dumps(report), encoding='utf-8')
        return paths

    def cli_compare(self, base, head, *, fail=True):
        bp, hp = self.write_pair(base, head)
        args = ['--project', str(self.project), 'compare', '--base', str(bp),
                '--head', str(hp), '--out', str(self.root / 'delta')]
        if fail:
            args.append('--fail-on-regression')
        with patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(args)

    def test_later_failure_outside_contract_fails_cli_gate(self):
        for kind in (None, 'security'):
            with self.subTest(kind=kind):
                self.run_check(kind, 'raise SystemExit(1)')
                head = enhanced.audit(self.project)
                self.assertEqual(head['overall'], 'FAILED_CHECK')
                self.assertEqual(head['evidence_contracts'][0]['status'], 'RECORDED')
                diff = compare_reports(self.base, head)
                self.assertEqual(diff['regressions'], 1)
                self.assertIn(('requirement', 'FAILED_CHECK', 'REGRESSION'),
                              [(x['kind'], x['head'], x['classification']) for x in diff['changes']])
                self.assertEqual(self.cli_compare(self.base, head), 1)
                self.assertEqual(self.cli_compare(self.base, head, fail=False), 0)

    def test_independent_failure_and_scoped_staleness_are_both_retained(self):
        (self.project / 'app.py').write_text('changed = True\n', encoding='utf-8')
        self.run_check('security', 'raise SystemExit(1)')
        diff = compare_reports(self.base, enhanced.audit(self.project))
        self.assertEqual(diff['regressions'], 2)
        self.assertEqual({(x['kind'], x['head']) for x in diff['changes']
                          if x['classification'] == 'REGRESSION'},
                         {('requirement', 'FAILED_CHECK'), ('unit', 'STALE')})

    def test_scoped_stale_is_counted_once(self):
        (self.project / 'app.py').write_text('changed = True\n', encoding='utf-8')
        head = enhanced.audit(self.project)
        bp, hp = self.write_pair(self.base, head)
        diff = save_diff(bp, hp, self.root / 'saved')
        self.assertEqual(diff['regressions'], 1)
        self.assertEqual([x['kind'] for x in diff['changes'] if x['classification'] == 'REGRESSION'], ['unit'])
        self.assertIn('STALE_EVIDENCE', (self.root / 'saved/pr-diff.md').read_text())
        self.assertTrue((self.root / 'saved/pr-diff.html').is_file())

    def test_scoped_failure_is_counted_once(self):
        self.run_check('unit', 'raise SystemExit(1)')
        diff = compare_reports(self.base, enhanced.audit(self.project))
        self.assertEqual(diff['regressions'], 1)
        self.assertEqual([x['kind'] for x in diff['changes'] if x['classification'] == 'REGRESSION'], ['unit'])

    def test_removed_verified_requirement_is_counted_once(self):
        manifest = core.get_manifest(self.project)
        manifest['requirements'] = []
        core.write_json(self.project / core.MANIFEST, manifest)
        diff = compare_reports(self.base, enhanced.audit(self.project))
        self.assertEqual(diff['regressions'], 1)
        self.assertEqual([x['kind'] for x in diff['changes']
                          if x['classification'] == 'REMOVED_VERIFIED_EVIDENCE'], ['unit'])

    def test_new_required_missing_check_fails_cli_gate(self):
        set_expectation(self.project, self.rid, 'security')
        head = enhanced.audit(self.project)
        self.assertEqual(head['overall'], 'EVIDENCE_GAPS')
        diff = compare_reports(self.base, head)
        self.assertEqual(diff['regressions'], 1)
        self.assertIn({'requirement': 'Login works', 'kind': 'security', 'base': None,
                       'head': 'MISSING', 'classification': 'REGRESSION'}, diff['changes'])
        self.assertEqual(self.cli_compare(self.base, head), 1)

    def test_new_required_failed_check_is_counted_once(self):
        set_expectation(self.project, self.rid, 'security')
        self.run_check('security', 'raise SystemExit(1)')
        diff = compare_reports(self.base, enhanced.audit(self.project))
        self.assertEqual(diff['regressions'], 1)
        self.assertEqual([x['kind'] for x in diff['changes'] if x['classification'] == 'REGRESSION'], ['security'])

    def test_new_verified_check_does_not_regress(self):
        set_expectation(self.project, self.rid, 'security')
        self.run_check('security')
        head = enhanced.audit(self.project)
        self.assertEqual(compare_reports(self.base, head)['regressions'], 0)
        self.assertEqual(self.cli_compare(self.base, head), 0)

    def test_new_gap_on_already_unverified_requirement_is_added(self):
        set_expectation(self.project, self.rid, 'security')
        base = enhanced.audit(self.project)
        set_expectation(self.project, self.rid, 'e2e')
        diff = compare_reports(base, enhanced.audit(self.project))
        self.assertEqual(diff['regressions'], 0)
        self.assertEqual(diff['changes'][0]['classification'], 'ADDED')

    def test_local_id_renumbering_does_not_hide_new_required_gap(self):
        set_expectation(self.project, self.rid, 'security')
        head = enhanced.audit(self.project)
        head['requirements'][0]['id'] = 'R9'
        head['evidence_contracts'][0]['id'] = 'R9'
        diff = compare_reports(self.base, head)
        self.assertEqual(diff['regressions'], 1)
        self.assertEqual(next(x for x in diff['changes'] if x['kind'] == 'security')['classification'], 'REGRESSION')

    def test_unrepresented_overall_downgrade_fails_cli_gate(self):
        head = copy.deepcopy(self.base)
        head['overall'] = 'FAILED_CHECK'
        diff = compare_reports(self.base, head)
        self.assertEqual(diff['regressions'], 1)
        self.assertEqual(diff['changes'][0]['kind'], 'overall')
        self.assertEqual(self.cli_compare(self.base, head), 1)

    def test_automatic_only_overall_downgrade_is_retained(self):
        base = copy.deepcopy(self.base)
        base.update(requirements=[], evidence_contracts=[], overall='AUTOCHECKS_PASSED_WITH_LIMITS')
        base['automatic_checks'] = [{'id': 'auto:test', 'state': 'OBSERVED_PASS'}]
        head = copy.deepcopy(base)
        head['overall'] = 'INSUFFICIENT_EVIDENCE'
        self.assertEqual(compare_reports(base, head)['regressions'], 1)

    def test_changed_intent_with_stale_contract_text_is_rejected(self):
        manifest = core.get_manifest(self.project)
        manifest['requirements'][0]['description'] = 'Login now requires MFA'
        core.write_json(self.project / core.MANIFEST, manifest)
        head = enhanced.audit(self.project)
        self.assertEqual(head['requirements'][0]['state'], 'INTENT_CHANGED')
        self.assertGreater(compare_reports(self.base, head)['regressions'], 0)
        # Reproduce a supplied report that retained the old passing contract.
        head['evidence_contracts'] = copy.deepcopy(self.base['evidence_contracts'])
        _, hp = self.write_pair(self.base, head)
        with self.assertRaisesRegex(ValueError, 'text does not match'):
            load_report(hp)
        with self.assertRaisesRegex(ValueError, 'text does not match'):
            compare_reports(self.base, head)
        with self.assertRaises(SystemExit) as error:
            self.cli_compare(self.base, head)
        self.assertEqual(error.exception.code, 2)
        self.assertFalse((self.root / 'delta').exists())

    def test_case_only_contract_identity_mismatch_is_rejected(self):
        head = copy.deepcopy(self.base)
        head['evidence_contracts'][0]['requirement'] = 'login works'
        with self.assertRaises(ValueError):
            compare_reports(self.base, head)

    def test_legacy_contract_without_repeated_text_uses_requirement_identity(self):
        head = copy.deepcopy(self.base)
        del head['evidence_contracts'][0]['requirement']
        self.assertEqual(compare_reports(self.base, head)['changes'], [])

    def test_duplicate_or_unknown_identity_is_rejected_before_lookup(self):
        for case in ('duplicate_requirement', 'duplicate_contract', 'unknown_contract'):
            with self.subTest(case=case):
                head = copy.deepcopy(self.base)
                if case == 'duplicate_requirement':
                    head['requirements'].append({'id': self.rid, 'requirement': 'Other intent', 'state': 'FAILED_CHECK'})
                elif case == 'duplicate_contract':
                    head['evidence_contracts'].append(copy.deepcopy(head['evidence_contracts'][0]))
                else:
                    head['evidence_contracts'][0]['id'] = 'R99'
                _, hp = self.write_pair(self.base, head)
                with self.assertRaises(ValueError):
                    load_report(hp)
                with self.assertRaises(ValueError):
                    compare_reports(self.base, head)

    def test_missing_duplicate_or_reserved_contract_role_is_rejected(self):
        for case in ('missing', 'duplicate', 'reserved'):
            with self.subTest(case=case):
                head = copy.deepcopy(self.base)
                contract = head['evidence_contracts'][0]
                if case == 'missing':
                    contract['evidence_by_kind'] = []
                elif case == 'duplicate':
                    contract['evidence_by_kind'] *= 2
                else:
                    contract['expected_checks'] = ['requirement']
                    contract['evidence_by_kind'][0]['kind'] = 'requirement'
                with self.assertRaises(ValueError):
                    compare_reports(self.base, head)

    def test_requirement_text_cannot_collide_through_string_coercion(self):
        head = copy.deepcopy(self.base)
        head['requirements'][0]['requirement'] = 123
        head['evidence_contracts'][0]['requirement'] = 123
        with self.assertRaises(ValueError):
            compare_reports(self.base, head)

    def test_malformed_overall_is_rejected_without_type_error(self):
        head = copy.deepcopy(self.base)
        head['overall'] = {'state': 'FAILED_CHECK'}
        _, hp = self.write_pair(self.base, head)
        with self.assertRaises(ValueError):
            load_report(hp)
        with self.assertRaises(ValueError):
            compare_reports(self.base, head)

    def test_strict_json_loading_is_preserved(self):
        for suffix in (', "overall": "FAILED_CHECK"', ', "extra": NaN'):
            with self.subTest(suffix=suffix):
                path = self.root / 'invalid.json'
                path.write_text(json.dumps(self.base)[:-1] + suffix + '}', encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_report(path)


if __name__ == '__main__':
    unittest.main()
