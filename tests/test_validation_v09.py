"""v0.9 parser benchmark, data minimization and adversarial corpus tests."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite.validation import evaluate, main
from raee_lite.cli import main as cli


class ValidationV09(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = Path(self.td.name)

    def fixture(self, *, file='case.jsonl', provider='claude', origin='synthetic', expected=None, consent=None, rows=None):
        if rows is None:
            rows = [
                {'type':'assistant','message':{'content':[{'type':'tool_use','id':'t','name':'Bash','input':{'command':'pytest tests/test_payment.py --secret=do_not_log'}}]}},
                {'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'t','content':'Exit code: 0\nHIDDEN_AUTHORIZATION_TOKEN'}]}}
            ]
        (self.root/file).write_text(''.join(json.dumps(x)+'\n' for x in rows))
        item = {'id':'case_1', 'file':file, 'provider':provider, 'provenance':origin,
                'expected': expected if expected is not None else [{'kind':'unit','exit_code':0}]}
        if consent is not None:
            item['consent_confirmed'] = consent
        (self.root/'index.json').write_text(json.dumps({'schema':'raee-corpus-v1','cases':[item]}))
        return self.root/'index.json'

    def test_exact_and_no_raw_secrets(self):
        x = evaluate(self.fixture())
        self.assertEqual(x['aggregate']['tp'], 1)
        self.assertEqual(x['aggregate']['session_exact_match_rate'],1.0)
        b = json.dumps(x)
        self.assertNotIn('HIDDEN_AUTHORIZATION_TOKEN',b)
        self.assertNotIn('do_not_log',b)
        self.assertNotIn('tests/test_payment.py',b)
        self.assertFalse(x['has_consent_based_real_logs'])

    def test_false_discovery_not_mislabelled_fpr(self):
        x = evaluate(self.fixture(expected=[]))
        self.assertEqual(x['aggregate']['fp'],1)
        self.assertEqual(x['aggregate']['false_discovery_rate'],1.0)
        self.assertNotIn('false_positive_rate', x['aggregate'])

    def test_false_negatives(self):
        x = evaluate(self.fixture(expected=[{'kind':'build','exit_code':0}]))
        self.assertEqual(x['aggregate']['fn'],1)
        self.assertEqual(x['aggregate']['fp'],1)

    def test_unknown_exit_not_faked_zero(self):
        rows=[{'type':'assistant','message':{'content':[{'type':'tool_use','name':'Bash','id':'t','input':{'command':'npm run build'}}]}},
              {'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'t','content':'done'}]}}]
        x = evaluate(self.fixture(rows=rows, expected=[{'kind':'build','exit_code':None}]))
        self.assertEqual(x['aggregate']['unknown_exit_rate'],1.0)
        self.assertEqual(x['aggregate']['tp'],1)

    def test_consent_required_for_real(self):
        with self.assertRaisesRegex(ValueError,'consent'):
            evaluate(self.fixture(origin='consented-real'))
        self.assertTrue(evaluate(self.fixture(origin='consented-real',consent=True))['has_consent_based_real_logs'])

    def test_path_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError,'simple'):
            evaluate(self.fixture(file='../outside.jsonl'))

    def test_symlink_rejected(self):
        index = self.fixture()
        (self.root/'link.jsonl').symlink_to(self.root/'case.jsonl')
        payload=json.loads(index.read_text());payload['cases'][0]['file']='link.jsonl';index.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError,'symbolic'):
            evaluate(index)

    def test_index_symlink_rejected(self):
        index=self.fixture()
        alias=self.root/'alias.json'
        alias.symlink_to(index)
        with self.assertRaisesRegex(ValueError,'non-symlink'):
            evaluate(alias)

    def test_duplicate_id_rejected(self):
        index=self.fixture();payload=json.loads(index.read_text());payload['cases'].append(payload['cases'][0]);index.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError,'duplicate'):
            evaluate(index)

    def test_empty_manifest_rejected(self):
        index=self.fixture();index.write_text(json.dumps({'schema':'raee-corpus-v1','cases':[]}))
        with self.assertRaisesRegex(ValueError,'1..250'):
            evaluate(index)

    def test_invalid_expected_code_type(self):
        with self.assertRaisesRegex(ValueError,'exit code'):
            evaluate(self.fixture(expected=[{'kind':'unit','exit_code':True}]))

    def test_parser_errors_are_fail_visible(self):
        x=evaluate(self.fixture(rows=[{'type':'nonsense','message':'text'}]))
        self.assertEqual(x['aggregate']['fn'],1)
        self.assertEqual(x['aggregate']['session_exact_match_rate'],0.0)

    def test_cli_emits_summary_only(self):
        idx = self.fixture()
        out = self.root/'summary.json'
        self.assertEqual(cli(['--project',str(self.root),'validate-corpus','--index','index.json','--out','summary.json']), 0)
        self.assertEqual(json.loads(out.read_text())['aggregate']['tp'],1)

    def test_missing_file_fails(self):
        idx=self.fixture(); (self.root/'case.jsonl').unlink()
        with self.assertRaises(ValueError):evaluate(idx)

    def test_manifest_max_size(self):
        idx=self.fixture();idx.write_text(' '*2_000_001)
        with self.assertRaises(ValueError):evaluate(idx)

    def test_error_no_private_path_logged(self):
        idx=self.fixture(file='bad;command.jsonl')
        self.assertEqual(main(['--index',str(idx),'--out',str(self.root/'summary.json')]),2)


if __name__ == '__main__':unittest.main()
