"""Missing base/head outcome coverage and comparison identity edge cases."""
import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite.cli import main
from raee_lite.pr_diff import compare_reports


class DiffEdgeTests(unittest.TestCase):
    def report(self):
        return {
            'tool': 'RAEE-Lite',
            'source': {'sha256': 'a' * 64},
            'requirements': [],
            'automatic_checks': [{'id': 'auto:test', 'state': 'OBSERVED_PASS'}],
            'overall': 'AUTOCHECKS_PASSED_WITH_LIMITS',
        }

    def test_missing_head_overall_withdraws_verified_observation(self):
        for missing in ('absent', 'null'):
            with self.subTest(missing=missing):
                base = self.report()
                head = copy.deepcopy(base)
                if missing == 'absent':
                    del head['overall']
                else:
                    head['overall'] = None
                diff = compare_reports(base, head)
                self.assertEqual(diff['regressions'], 1)
                self.assertEqual(diff['changes'], [{
                    'requirement': 'Overall outcome', 'kind': 'overall',
                    'base': base['overall'], 'head': None,
                    'classification': 'REMOVED_VERIFIED_EVIDENCE',
                }])

    def test_missing_overall_fails_cli_gate_only_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            base = self.report()
            head = copy.deepcopy(base)
            del head['overall']
            paths = root / 'base.json', root / 'head.json'
            for path, report in zip(paths, (base, head)):
                path.write_text(json.dumps(report), encoding='utf-8')
            args = ['--project', str(root), 'compare', '--base', str(paths[0]),
                    '--head', str(paths[1]), '--out', str(root / 'delta')]
            with patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 0)
                self.assertEqual(main(args + ['--fail-on-regression']), 1)
            saved = json.loads((root / 'delta/pr-diff.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['regressions'], 1)
            self.assertIn('REMOVED_VERIFIED_EVIDENCE',
                          (root / 'delta/pr-diff.md').read_text(encoding='utf-8'))
            self.assertIn('REMOVED_VERIFIED_EVIDENCE',
                          (root / 'delta/pr-diff.html').read_text(encoding='utf-8'))

    def test_missing_head_unverified_overall_is_retained_for_review(self):
        base = self.report()
        base['overall'] = 'INSUFFICIENT_EVIDENCE'
        head = copy.deepcopy(base)
        del head['overall']
        diff = compare_reports(base, head)
        self.assertEqual(diff['regressions'], 0)
        self.assertEqual(len(diff['changes']), 1)
        self.assertEqual(diff['changes'][0]['classification'], 'REMOVED_UNVERIFIED')

    def test_missing_base_overall_is_an_addition_not_an_improvement(self):
        for state in ('AUTOCHECKS_PASSED_WITH_LIMITS', 'FAILED_CHECK'):
            with self.subTest(state=state):
                head = self.report()
                head['overall'] = state
                base = copy.deepcopy(head)
                del base['overall']
                diff = compare_reports(base, head)
                self.assertEqual(diff['regressions'], 0)
                self.assertEqual(diff['changes'], [{
                    'requirement': 'Overall outcome', 'kind': 'overall',
                    'base': None, 'head': state, 'classification': 'ADDED',
                }])

    def test_missing_both_overall_outcomes_is_unchanged(self):
        base = self.report()
        del base['overall']
        head = copy.deepcopy(base)
        head['overall'] = None
        diff = compare_reports(base, head)
        self.assertEqual(diff['changes'], [])
        self.assertEqual(diff['regressions'], 0)

    def test_removed_overall_does_not_double_count_removed_check(self):
        base = self.report()
        head = copy.deepcopy(base)
        del head['overall']
        del head['automatic_checks']
        diff = compare_reports(base, head)
        self.assertEqual(diff['regressions'], 1)
        self.assertEqual({row['kind']: row['classification'] for row in diff['changes']}, {
            'autocheck': 'REMOVED_VERIFIED_EVIDENCE', 'overall': 'CHANGED_REVIEW',
        })

    def test_duplicate_autocheck_id_and_kind_alias_is_rejected_on_either_side(self):
        clean = self.report()
        duplicate = copy.deepcopy(clean)
        duplicate['automatic_checks'] = [
            {'id': 'test', 'state': 'OBSERVED_PASS'},
            {'kind': 'test', 'state': 'FAILED'},
        ]
        for base, head in ((clean, duplicate), (duplicate, clean)):
            for rows in (duplicate['automatic_checks'], duplicate['automatic_checks'][::-1]):
                with self.subTest(duplicate_in_base=base is duplicate, rows=rows):
                    duplicate['automatic_checks'] = rows
                    with self.assertRaisesRegex(ValueError, 'duplicate'):
                        compare_reports(base, head)


if __name__ == '__main__':
    unittest.main()
