"""Dashboard boundaries must not hide uncertainty or expand untrusted reports unboundedly."""
import copy
import html
from html.parser import HTMLParser
import unittest

from raee_lite.dashboard import render


def report_fixture():
    return {
        'version': '0.10.0rc2', 'overall': 'INSUFFICIENT_EVIDENCE',
        'source': {'sha256': 'a' * 64, 'files': 1, 'skipped': []},
        'requirements': [{'id': 'R1', 'requirement': 'Behavior', 'state': 'UNTESTED'}],
        'evidence_contracts': [{'id': 'R1', 'requirement': 'Behavior',
                                'evidence_by_kind': [], 'gaps': []}],
        'automatic_checks': [], 'agent_evidence': {'imported': [], 'explicit': []},
        'verification_provenance': [], 'boundary_notes': [], 'discovery_notes': [],
        'caveat': 'A process exit does not prove correctness.',
    }


class Markup(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.tags = []
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class DashboardIntegrityTests(unittest.TestCase):
    def test_uncontracted_requirement_is_counted_as_a_gap(self):
        page = render(report_fixture())
        self.assertIn('<small>LISTED EVIDENCE GAPS</small><strong class="warn">1</strong>', page)
        self.assertIn('R1: UNTESTED', page)

    def test_failed_automatic_check_is_an_actionable_gap(self):
        report = report_fixture()
        report['requirements'] = []
        report['evidence_contracts'] = []
        report['automatic_checks'] = [{'kind': 'test', 'state': 'FAILED', 'evidence_id': 'E1'}]
        report['overall'] = 'FAILED_CHECK'
        page = render(report)
        self.assertIn('<small>LISTED EVIDENCE GAPS</small><strong class="warn">1</strong>', page)
        self.assertIn('Automatic test: FAILED', page)
        self.assertNotIn('No listed contract gaps', page)

    def test_contract_nonpass_without_reason_remains_visible(self):
        report = report_fixture()
        report['requirements'] = []
        report['evidence_contracts'][0]['evidence_by_kind'] = [{'kind': 'unit', 'state': 'MISSING'}]
        page = render(report)
        self.assertIn('<small>LISTED EVIDENCE GAPS</small><strong class="warn">1</strong>', page)
        self.assertIn('R1: unit — MISSING', page)

    def test_imported_receipt_window_is_disclosed(self):
        report = report_fixture()
        report['agent_evidence']['imported'] = [
            {'id': f'A{i}', 'provider': 'codex', 'command_family': 'test', 'log_status': 'LOG_PASS'}
            for i in range(101)]
        page = render(report)
        self.assertNotIn('<td>A0</td>', page)
        self.assertIn('<td>A100</td>', page)
        self.assertIn('Showing the latest 100 of 101 imported receipts; 1 omitted.', page)

    def test_full_import_capacity_still_renders_a_bounded_window(self):
        report = report_fixture()
        report['agent_evidence']['imported'] = [
            {'id': f'A{i}', 'provider': 'codex', 'command_family': 'test', 'log_status': 'LOG_PASS'}
            for i in range(25_000)]
        page = render(report)
        self.assertIn('Showing the latest 100 of 25000 imported receipts; 24900 omitted.', page)
        self.assertIn('<td>A24999</td>', page)
        self.assertLess(len(page.encode('utf-8')), 30_000)

    def test_omitted_receipts_are_still_validated(self):
        report = report_fixture()
        report['agent_evidence']['imported'] = [
            {'id': f'A{i}', 'provider': 'codex', 'command_family': 'test', 'log_status': 'LOG_PASS'}
            for i in range(101)]
        report['agent_evidence']['imported'][0]['log_status'] = float('nan')
        with self.assertRaises(ValueError):
            render(report)

    def test_valid_success_keeps_manual_and_automatic_roles_distinct(self):
        report = report_fixture()
        report['requirements'][0]['state'] = 'OBSERVED_PASS'
        report['automatic_checks'] = [{'kind': 'test', 'state': 'NOT_RUN'}]
        report['overall'] = 'CHECKS_PASSED_WITH_LIMITS'
        self.assertIn('CHECKS_PASSED_WITH_LIMITS', render(report))
        report['requirements'] = []
        report['evidence_contracts'] = []
        report['automatic_checks'][0]['state'] = 'OBSERVED_PASS'
        report['overall'] = 'AUTOCHECKS_PASSED_WITH_LIMITS'
        self.assertIn('AUTOCHECKS_PASSED_WITH_LIMITS', render(report))

    def test_all_gap_reasons_are_retained_even_for_repeated_kinds(self):
        report = report_fixture()
        report['evidence_contracts'][0]['evidence_by_kind'] = [{'kind': 'unit', 'state': 'MISSING'}]
        report['evidence_contracts'][0]['gaps'] = [
            {'kind': 'unit', 'reason': 'First reason'}, {'kind': 'unit', 'reason': 'Second reason'}]
        page = render(report)
        self.assertIn('First reason', page)
        self.assertIn('Second reason', page)

    def test_partial_source_coverage_is_explicit(self):
        report = report_fixture()
        report['source']['skipped'] = [{'file': 'unreadable.py', 'reason': 'read_error'}]
        self.assertIn('Fingerprint coverage incomplete: 1 source entries skipped.', render(report))

    def test_historical_pass_is_not_presented_as_current_verification(self):
        report = report_fixture()
        report['verification_provenance'] = [{'id': 'E1', 'observed_status': 'pass'}]
        page = render(report)
        self.assertIn('Recorded process status', page)
        self.assertIn('Historical process outcomes do not establish current applicability.', page)

    def test_display_fields_are_text_not_active_markup(self):
        payload = '</style><script>alert("x")</script><img src=x onerror=alert(1)>&\''
        report = report_fixture()
        report['version'] = report['caveat'] = payload
        report['requirements'] = [{'id': payload, 'requirement': payload, 'state': payload}]
        report['evidence_contracts'] = [{'id': payload, 'requirement': payload,
            'evidence_by_kind': [{'kind': payload, 'state': payload}],
            'gaps': [{'kind': payload, 'reason': payload}]}]
        report['automatic_checks'] = [{'kind': payload, 'state': payload, 'evidence_id': payload}]
        report['agent_evidence'] = {
            'imported': [dict.fromkeys(('id', 'provider', 'command_family', 'log_status'), payload)],
            'explicit': [dict.fromkeys(('requirement', 'evidence_id', 'state', 'rationale'), payload)]}
        report['verification_provenance'] = [dict.fromkeys(
            ('id', 'origin', 'requirement', 'declared_kind', 'observed_status', 'isolation_policy'), payload)]
        report['boundary_notes'] = report['discovery_notes'] = [payload]
        page = render(report)
        self.assertNotIn(payload, page)
        self.assertIn(html.escape(payload, quote=True), page)
        for tag, attrs in Markup(page).tags:
            self.assertNotIn(tag, ('script', 'img', 'iframe', 'object', 'a'))
            self.assertFalse(any(name.startswith('on') for name in attrs))
        self.assertIn("default-src 'none'", page)

    def test_directional_controls_cannot_hide_identifier_text(self):
        report = report_fixture()
        report['requirements'][0]['id'] = 'R1\u202eLI AF\u202c'
        page = render(report)
        self.assertNotIn('\u202e', page)
        self.assertIn(r'R1\u202eLI AF\u202c', page)

    def test_invalid_top_level_and_containers_raise_value_error(self):
        for value in (None, [], 'report', 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                render(value)
        for key in ('source', 'agent_evidence', 'requirements', 'evidence_contracts',
                    'automatic_checks', 'verification_provenance', 'boundary_notes', 'discovery_notes'):
            for value in (None, 'bad', 7):
                report = report_fixture()
                report[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    render(report)

    def test_invalid_nested_records_raise_value_error(self):
        for path in (('requirements',), ('automatic_checks',), ('evidence_contracts',),
                     ('verification_provenance',), ('agent_evidence', 'imported'),
                     ('agent_evidence', 'explicit'), ('evidence_contracts', 0, 'evidence_by_kind'),
                     ('evidence_contracts', 0, 'gaps')):
            for value in (None, [], 'bad', False):
                report = report_fixture()
                target = report
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = [value]
                with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                    render(report)

    def test_nonfinite_counts_and_invalid_fingerprints_are_rejected(self):
        for count in (float('nan'), float('inf'), -float('inf'), True, -1, '1', 1.0):
            report = report_fixture()
            report['source']['files'] = count
            with self.subTest(count=count), self.assertRaises(ValueError):
                render(report)
        for digest in (None, 7, [], 'not-a-digest', 'g' * 64):
            report = report_fixture()
            report['source']['sha256'] = digest
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                render(report)

    def test_container_and_nonfinite_text_values_are_rejected(self):
        for key in ('version', 'caveat'):
            for value in ([], {}, float('nan'), float('inf')):
                report = report_fixture()
                report[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    render(report)
        report = report_fixture()
        report['requirements'][0]['id'] = {'untrusted': 'R1'}
        with self.assertRaises(ValueError):
            render(report)

    def test_invalid_unicode_raises_value_error_before_file_write(self):
        report = report_fixture()
        report['caveat'] = '\ud800'
        with self.assertRaises(ValueError):
            render(report)

    def test_contradictory_success_summary_is_rejected(self):
        report = report_fixture()
        report['overall'] = 'CHECKS_PASSED_WITH_LIMITS'
        with self.assertRaisesRegex(ValueError, 'passing'):
            render(report)
        report['requirements'][0]['state'] = 'OBSERVED_PASS'
        self.assertIn('CHECKS_PASSED_WITH_LIMITS', render(report))
        for fields in ({'automatic_checks': [{'kind': 'test', 'state': 'FAILED'}]},
                       {'source': {'sha256': 'a' * 64, 'files': 1, 'skipped': [{}]}},
                       {'requirements': []}):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, 'passing'):
                render({**report, **fields})

    def test_false_autocheck_success_and_unknown_outcome_are_rejected(self):
        report = report_fixture()
        report['overall'] = 'AUTOCHECKS_PASSED_WITH_LIMITS'
        with self.assertRaisesRegex(ValueError, 'passing'):
            render(report)
        report['overall'] = 'VERIFIED'
        with self.assertRaises(ValueError):
            render(report)

    def test_oversized_field_and_section_are_rejected(self):
        report = report_fixture()
        report['caveat'] = '&' * 100_000
        with self.assertRaisesRegex(ValueError, 'limit|budget'):
            render(report)
        report = report_fixture()
        report['boundary_notes'] = ['note'] * 10_001
        with self.assertRaisesRegex(ValueError, 'limit|budget'):
            render(report)

    def test_escaped_output_amplification_is_bounded(self):
        report = report_fixture()
        report['boundary_notes'] = ['&' * 5000] * 1000
        with self.assertRaisesRegex(ValueError, 'budget'):
            render(report)

    def test_render_does_not_mutate_report(self):
        report = report_fixture()
        before = copy.deepcopy(report)
        page = render(report)
        self.assertEqual(report, before)
        page.encode('utf-8')


if __name__ == '__main__':
    unittest.main()
