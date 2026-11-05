"""Malformed candidate metadata cannot become favourable relevance statistics."""
import json
import unittest
from pathlib import Path

from raee_lite.association_metrics import evaluate


def pair(**overrides):
    return {
        'requirement': 'Login works',
        'observed_target': 'login test',
        'observed_kind': 'unit',
        'expected_kinds': ['unit'],
        'relevant': True,
        **overrides,
    }


class MetricIntegrityTests(unittest.TestCase):
    def test_blank_matching_kinds_cannot_be_true_positives(self):
        for kind in ('', ' ', '\t\n'):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                evaluate([pair(observed_kind=kind, expected_kinds=[kind])])

    def test_malformed_observed_kinds_cannot_be_true_negatives(self):
        for kind in ([], {}, False, 0, 1.5, '', ' '):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                evaluate([pair(observed_kind=kind, relevant=False)])

    def test_missing_observed_kind_requires_explicit_unknown(self):
        row = pair(relevant=False)
        del row['observed_kind']
        with self.assertRaises(ValueError):
            evaluate([row])

    def test_malformed_expected_kinds_reject_entire_evaluation(self):
        for kinds in (None, {}, 'unit', [None], [0], [''], ['unit', ' ']):
            with self.subTest(kinds=kinds), self.assertRaises(ValueError):
                evaluate([pair(), pair(expected_kinds=kinds, relevant=False)])

    def test_explicit_unknown_kind_preserves_positive_and_negative_denominators(self):
        result = evaluate([
            pair(), pair(relevant=False),
            pair(observed_kind=None), pair(observed_kind=None, relevant=False),
        ])
        self.assertEqual(result['n_pairs'], 4)
        self.assertEqual([result[key] for key in ('TP', 'FP', 'FN', 'TN')], [1, 1, 1, 1])
        self.assertEqual(result['precision'], .5)
        self.assertEqual(result['recall'], .5)
        self.assertEqual(result['false_positive_rate'], .5)

    def test_unknown_relevance_is_not_assumed_negative_or_dropped(self):
        for relevant in (None, 0, 1, '', 'false', [], {}):
            with self.subTest(relevant=relevant), self.assertRaises(ValueError):
                evaluate([pair(), pair(relevant=relevant)])
        row = pair()
        del row['relevant']
        with self.assertRaises(ValueError):
            evaluate([pair(), row])

    def test_no_proposals_preserves_pairs_and_undefined_precision(self):
        result = evaluate([pair(observed_kind=None), pair(expected_kinds=[], relevant=False)])
        self.assertEqual(result['n_pairs'], 2)
        self.assertEqual([result[key] for key in ('TP', 'FP', 'FN', 'TN')], [0, 0, 1, 1])
        self.assertIsNone(result['precision'])
        self.assertIsNone(result['precision_wilson95'])
        self.assertEqual(result['recall'], 0)
        self.assertEqual(result['false_positive_rate'], 0)

    def test_repeated_expected_kinds_do_not_multiply_pairs(self):
        self.assertEqual(evaluate([pair(expected_kinds=['unit', 'unit', 'integration'])]),
                         evaluate([pair()]))

    def test_real_provenance_requires_boolean_true_consent(self):
        for consent in (None, False, 0, 1, 'false', 'true', [True], {'approved': True}):
            with self.subTest(consent=consent), self.assertRaises(ValueError):
                evaluate([pair()], provenance='consented-real', consent=consent)
        self.assertEqual(evaluate([pair()], provenance='consented-real', consent=True)['n_pairs'], 1)

    def test_labelled_synthetic_fixture_metrics_remain_unchanged(self):
        root = Path(__file__).resolve().parents[1]
        rows = json.loads((root / 'benchmarks/labelled_hints.json').read_text(encoding='utf-8'))
        expected = json.loads((root / 'validation_corpus/association-synthetic.json').read_text(encoding='utf-8'))
        self.assertEqual(evaluate(rows), expected)


if __name__ == '__main__':
    unittest.main()
