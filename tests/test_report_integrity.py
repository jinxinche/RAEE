"""Report consumers retain invalid evidence and reject malformed auxiliary data."""
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from raee_lite import core, enhanced
from raee_lite.agent_logs import import_log
from raee_lite.associations import available_evidence, build_associations, link_evidence
from raee_lite.cli import main
from raee_lite.contracts import set_expectation
from raee_lite.discovery import Check
from raee_lite.sarif import sarif_report


class ReportFixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / 'app.py').write_text('pass\n', encoding='utf-8')
        core.init(self.root)
        self.rid = core.add_requirement(self.root, 'Exact behavior')

    def execute(self, code=0, **kwargs):
        return core.run_check(self.root, self.rid,
                              [sys.executable, '-B', '-c', f'raise SystemExit({code})'], 10, **kwargs)

    def mutate(self, **fields):
        ledger = core.read_json(self.root / core.LEDGER)
        ledger['runs'][-1].update(fields)
        core.write_json(self.root / core.LEDGER, ledger)

    def write_aux(self, name, value):
        core.write_json(self.root / '.raee' / name, value)

    def link(self, receipt, requirement=None):
        return link_evidence(self.root, requirement or self.rid, receipt['id'],
                             'User asserts this receipt is relevant')


class LinkedReceiptTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.receipt = self.execute()
        self.link(self.receipt)

    def state(self):
        return enhanced.audit(self.root)['agent_evidence']['explicit'][0]['state']

    def test_valid_receipt_retains_self_linked_not_proof_semantics(self):
        report = enhanced.save_report(self.root)
        row = report['agent_evidence']['explicit'][0]
        self.assertEqual(row['state'], 'OBSERVED_PASS_SELF_LINKED')
        self.assertEqual(row['basis'], 'USER_ASSERTED_ASSOCIATION_NOT_COVERAGE_PROOF')
        self.assertEqual(report['evidence_contracts'][0]['status'], 'NO_CONTRACT')

    def test_boolean_float_string_and_missing_exit_codes_never_pass(self):
        for code in (False, 0.0, '0', None):
            with self.subTest(code=code):
                self.mutate(observed_exit_code=code)
                report = enhanced.save_report(self.root)
                self.assertEqual(report['agent_evidence']['explicit'][0]['state'], 'INVALID_EVIDENCE')
                for name in ('report.json', 'report.md', 'report.html'):
                    text = (self.root / '.raee' / name).read_text(encoding='utf-8')
                    self.assertNotIn('OBSERVED_PASS_SELF_LINKED', text)

    def test_all_execution_roles_are_checked(self):
        original = core.read_json(self.root / core.LEDGER)
        for fields in ({'role': 'intent'}, {'origin': 'agent_log'}, {'command': []},
                       {'command_sha256': None}, {'error': 'TimeoutExpired'},
                       {'observed_status': 'infrastructure_error'}):
            with self.subTest(fields=fields):
                core.write_json(self.root / core.LEDGER, original)
                self.mutate(**fields)
                self.assertEqual(self.state(), 'INVALID_EVIDENCE')

    def test_changed_or_missing_intent_binding_never_passes(self):
        manifest = core.get_manifest(self.root)
        manifest['requirements'][0]['description'] = 'Changed behavior'
        core.write_json(self.root / core.MANIFEST, manifest)
        self.assertEqual(self.state(), 'INTENT_CHANGED')
        self.mutate(requirement_digest=None)
        self.assertEqual(self.state(), 'INTENT_UNBOUND')

    def test_changed_or_missing_environment_never_passes(self):
        for env, state in (({}, 'ENVIRONMENT_UNBOUND'), (None, 'ENVIRONMENT_UNBOUND'),
                           ({'os': 'other', 'python': '0.0'}, 'ENVIRONMENT_SHIFT_UNVERIFIED')):
            with self.subTest(env=env):
                self.mutate(environment=env)
                self.assertEqual(self.state(), state)

    def test_source_changes_and_changes_during_execution_are_stale(self):
        self.mutate(source_fingerprint_after='0' * 64)
        self.assertEqual(self.state(), 'STALE')
        self.mutate(source_fingerprint_after=self.receipt['source_fingerprint'])
        (self.root / 'app.py').write_text('changed = True\n', encoding='utf-8')
        self.assertEqual(self.state(), 'STALE')

    def test_partial_receipt_and_partial_current_source_never_pass(self):
        omitted = [{'file': 'app.py', 'reason': 'unreadable'}]
        self.mutate(files_skipped=omitted)
        self.assertEqual(self.state(), 'PARTIAL_COVERAGE')
        self.mutate(files_skipped=[])
        source = core.fingerprint(self.root)
        source['skipped'] = omitted
        self.assertEqual(build_associations(self.root, source)['explicit'][0]['state'], 'PARTIAL_COVERAGE')

    def test_scoped_receipts_need_current_scope_context(self):
        for scope, state in ((None, 'SCOPE_UNBOUND'), ({}, 'SCOPE_CONTEXT_REQUIRED')):
            with self.subTest(scope=scope):
                self.mutate(dependency_scope=scope)
                self.assertEqual(self.state(), state)

    def test_cross_requirement_link_retains_original_intent_binding(self):
        other = core.add_requirement(self.root, 'Another behavior')
        self.link(self.receipt, other)
        report = enhanced.audit(self.root)
        self.assertEqual(report['requirements'][1]['state'], 'UNTESTED')
        self.assertEqual(report['agent_evidence']['explicit'][1]['state'], 'OBSERVED_PASS_SELF_LINKED')
        manifest = core.get_manifest(self.root)
        manifest['requirements'][0]['description'] = 'Changed original behavior'
        core.write_json(self.root / core.MANIFEST, manifest)
        self.assertEqual(enhanced.audit(self.root)['agent_evidence']['explicit'][1]['state'], 'INTENT_CHANGED')
        manifest['requirements'].pop(0)
        core.write_json(self.root / core.MANIFEST, manifest)
        # Removing a requirement leaves its old attribution dangling. Preserve
        # that error boundary, then examine the still-valid cross-requirement link.
        with self.assertRaisesRegex(ValueError, 'dangling requirement'):
            self.state()
        links = core.read_json(self.root / '.raee/links.json')
        links['links'] = [link for link in links['links'] if link['requirement'] == other]
        core.write_json(self.root / '.raee/links.json', links)
        self.assertEqual(self.state(), 'INTENT_UNBOUND')

    def test_automatic_receipt_checks_environment_without_inventing_intent(self):
        check = Check('auto:fixture', 'test', (sys.executable, '-B', '-c', 'pass'), 'fixture')
        receipt = enhanced.run_discovered(self.root, check)
        self.link(receipt)
        self.assertEqual(enhanced.audit(self.root)['agent_evidence']['explicit'][1]['state'],
                         'OBSERVED_PASS_SELF_LINKED')
        self.mutate(environment={})
        self.assertEqual(enhanced.audit(self.root)['agent_evidence']['explicit'][1]['state'],
                         'ENVIRONMENT_UNBOUND')

    def test_failed_receipt_is_still_reported_as_failed(self):
        receipt = self.execute(7)
        self.link(receipt)
        self.assertEqual(enhanced.audit(self.root)['agent_evidence']['explicit'][1]['state'],
                         'OBSERVED_FAILED_SELF_LINKED')


class AuxiliaryShapeTests(ReportFixture):
    def test_invalid_containers_and_entries_raise_value_error(self):
        for name, field in (('imports.json', 'observations'), ('links.json', 'links')):
            for value in (None, [], 'bad', 3, {}, {field: None}, {field: {}},
                          {field: 'bad'}, {field: [None]}, {field: [[]]}, {field: [False]}):
                with self.subTest(name=name, value=value):
                    self.write_aux(name, value)
                    with self.assertRaises(ValueError):
                        enhanced.audit(self.root)
            (self.root / '.raee' / name).unlink()

    def test_import_fields_are_validated_before_rendering_and_suggestions(self):
        row = {'id': 'A1', 'provider': 'codex', 'command_family': 'pytest',
               'log_status': 'RECORDED_ZERO', 'provenance': 'UNVERIFIED_AGENT_TRANSCRIPT',
               'check_kind_hint': 'unit', 'topic_tags': ['login']}
        for field, value in (('id', []), ('provider', None), ('command_family', {}),
                             ('log_status', 0), ('provenance', 'local_explicit'),
                             ('check_kind_hint', []), ('topic_tags', None), ('topic_tags', [{}])):
            with self.subTest(field=field):
                self.write_aux('imports.json', {'observations': [{**row, field: value}]})
                with self.assertRaises(ValueError):
                    enhanced.save_report(self.root)

    def test_link_fields_are_validated_before_reading_or_updating(self):
        receipt = self.execute()
        original = self.link(receipt)
        for field in ('requirement', 'evidence_id', 'rationale'):
            for value in (None, [], {}, '', 7):
                with self.subTest(field=field, value=value):
                    self.write_aux('links.json', {'links': [{**original, field: value}]})
                    with self.assertRaises(ValueError):
                        enhanced.audit(self.root)
                    with self.assertRaises(ValueError):
                        self.link(receipt)

    def test_duplicate_ids_do_not_silently_replace_receipts(self):
        self.execute()
        ledger = core.read_json(self.root / core.LEDGER)
        ledger['runs'].append(copy.deepcopy(ledger['runs'][0]))
        core.write_json(self.root / core.LEDGER, ledger)
        with self.assertRaises(ValueError):
            available_evidence(self.root)

    def test_preflight_malformed_auxiliary_files_produce_blocked_json(self):
        for name, field in (('imports.json', 'observations'), ('links.json', 'links')):
            for value in ([], {field: None}, {field: [None]}, {field: [{}]}):
                with self.subTest(name=name, value=value):
                    self.write_aux(name, value)
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        code = main(['--project', str(self.root), 'preflight', '--json'])
                    report = json.loads(out.getvalue())
                    self.assertEqual(code, 2)
                    self.assertEqual(report['result'], 'BLOCKED')
                    self.assertIn('INVALID_EVIDENCE', {f['id'] for f in report['findings']})
                    self.assertEqual(err.getvalue(), '')
            (self.root / '.raee' / name).unlink()

    def test_check_and_trace_return_input_error_without_traceback(self):
        for name in ('imports.json', 'links.json'):
            self.write_aux(name, [])
            for action in ('check', 'trace'):
                with self.subTest(name=name, action=action):
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        with self.assertRaises(SystemExit) as raised:
                            main(['--project', str(self.root), action, '--json'])
                    self.assertEqual(raised.exception.code, 2)
                    self.assertEqual(out.getvalue(), '')
                    self.assertIn('Error: Invalid', err.getvalue())
                    self.assertNotIn('Traceback', err.getvalue())
            (self.root / '.raee' / name).unlink()

    def test_real_import_is_log_only_with_optional_and_extra_metadata(self):
        path = self.root / '.raee' / 'fixture.jsonl'
        path.write_text(json.dumps({'type': 'item.completed', 'item': {
            'type': 'command_execution', 'command': 'pytest', 'exit_code': 0}}) + '\n', encoding='utf-8')
        import_log(self.root, path, 'codex')
        store = core.read_json(self.root / '.raee/imports.json')
        row = store['observations'][0]
        row.pop('topic_tags')
        row.pop('check_kind_hint')
        row['future_metadata'] = {'version': 2}
        self.write_aux('imports.json', store)
        self.link(row)
        report = enhanced.save_report(self.root)
        self.assertEqual(report['agent_evidence']['explicit'][0]['state'], 'LOG_ONLY_NOT_VALIDATED')
        self.assertEqual(report['requirements'][0]['state'], 'UNTESTED')


class SarifIntegrityTests(ReportFixture):
    def results(self):
        return sarif_report(enhanced.audit(self.root))['runs'][0]['results']

    def test_manual_failure_without_scope_is_an_error_in_saved_sarif(self):
        self.execute(7)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--project', str(self.root), 'report']), 1)
        report = core.read_json(self.root / '.raee/report.json')
        results = core.read_json(self.root / '.raee/report.sarif')['runs'][0]['results']
        self.assertEqual(report['overall'], 'FAILED_CHECK')
        self.assertEqual(len(results), 1)
        self.assertEqual((results[0]['ruleId'], results[0]['level']), ('RAEE003', 'error'))
        self.assertIn(self.rid, results[0]['message']['text'])

    def test_untested_manual_requirement_is_visible(self):
        results = self.results()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['ruleId'], 'RAEE001')
        self.assertIn('UNTESTED', results[0]['message']['text'])

    def test_invalid_and_unbound_manual_requirements_are_visible(self):
        self.execute()
        original = core.read_json(self.root / core.LEDGER)
        for fields in ({'observed_exit_code': False}, {'environment': {}}, {'requirement_digest': '0' * 64}):
            with self.subTest(fields=fields):
                core.write_json(self.root / core.LEDGER, original)
                self.mutate(**fields)
                results = self.results()
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]['ruleId'], 'RAEE001')

    def test_stale_manual_requirement_is_visible(self):
        self.execute()
        (self.root / 'app.py').write_text('changed = True\n', encoding='utf-8')
        self.assertEqual(self.results()[0]['ruleId'], 'RAEE002')

    def test_scoped_failure_and_manual_failure_are_not_duplicated(self):
        set_expectation(self.root, self.rid, 'unit')
        self.execute(7, kind='unit')
        results = self.results()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['ruleId'], 'RAEE003')

    def test_scoped_missing_receipt_and_untested_requirement_are_not_duplicated(self):
        set_expectation(self.root, self.rid, 'unit')
        self.assertEqual(len(self.results()), 1)

    def test_missing_scope_does_not_hide_a_different_invalid_manual_receipt(self):
        set_expectation(self.root, self.rid, 'unit')
        self.execute()
        self.mutate(observed_exit_code=False)
        results = self.results()
        self.assertEqual(len(results), 2)
        self.assertEqual([row['ruleId'] for row in results], ['RAEE001', 'RAEE001'])
        self.assertTrue(any('INVALID_EVIDENCE' in row['message']['text'] for row in results))

    def test_distinct_failed_scopes_are_preserved_without_manual_duplicate(self):
        for kind in ('unit', 'integration'):
            set_expectation(self.root, self.rid, kind)
            self.execute(7, kind=kind)
        results = self.results()
        self.assertEqual(len(results), 2)
        self.assertTrue(all(row['ruleId'] == 'RAEE003' for row in results))

    def test_passing_manual_requirement_has_no_findings(self):
        self.execute()
        self.assertEqual(self.results(), [])

    def test_invalid_automatic_evidence_is_not_silently_omitted(self):
        self.execute()
        report = enhanced.audit(self.root)
        report['automatic_checks'] = [{'id': 'auto:fixture', 'state': 'INVALID_EVIDENCE'}]
        results = sarif_report(report)['runs'][0]['results']
        self.assertEqual(len(results), 1)
        self.assertIn('INVALID_EVIDENCE', results[0]['message']['text'])


if __name__ == '__main__':
    unittest.main()
