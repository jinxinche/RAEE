"""v0.4 agent import, link provenance, PR delta and local dashboard regression tests."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite.agent_logs import import_log, parse_exit
from raee_lite.associations import build_associations, link_evidence
from raee_lite.cli import main
from raee_lite.contracts import set_expectation
from raee_lite.core import add_requirement, fingerprint, init, read_json, run_check
from raee_lite.enhanced import audit, html_report, is_passing, save_report
from raee_lite.pr_diff import compare_reports, save_diff


def write_lines(path, lines):
    path.write_text(''.join(json.dumps(x) + '\n' for x in lines), encoding='utf-8')


CLAUDE = [
    {'type':'assistant','message':{'content':[
        {'type':'tool_use','id':'t1','name':'Bash','input':{'command':'pytest tests/test_login.py --token=secretvalue'}},
        {'type':'text','text':'this user text must not be retained'}]}},
    {'type':'user','message':{'content':[
        {'type':'tool_result','tool_use_id':'t1','content':'Exit code: 0\nSECRET_RAW_STDOUT=veryprivate'}]}},
    {'type':'assistant','message':{'content':[
        {'type':'tool_use','id':'t2','name':'Bash','input':{'command':'npm run build'}}]}},
    {'type':'user','message':{'content':[
        {'type':'tool_result','tool_use_id':'t2','content':[{'type':'text','text':'build done'}]}]}},
]

CODEX = [
    {'type':'session_meta','payload':{'cwd':'secret'}},
    {'type':'response_item','payload':{'type':'function_call','name':'exec_command','call_id':'c1',
                                        'arguments':json.dumps({'cmd':'python -m pytest -q'})}},
    {'type':'response_item','payload':{'type':'function_call_output','call_id':'c1',
                                        'output':'Process exited with code 1\nFinal output:\nfailure'}},
    {'type':'event_msg','payload':{'type':'item_completed','item':{
        'type':'CommandExecution','command':'npm run build','exit_code':0,
        'stdout':'Private payload that must not be persisted'}}},
]


class V04Tests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        (self.root / 'app.py').write_text('print("hello")\n')
        init(self.root)

    def log(self, name, rows):
        p = self.root / name
        write_lines(p, rows)
        return p

    def test_claude_import_exit_and_unknown_distinction(self):
        f = self.log('claude.jsonl', CLAUDE)
        result = import_log(self.root, f)
        self.assertEqual(result['provider'], 'claude')
        self.assertEqual(result['new_observations'], 2)
        data = read_json(self.root / '.raee/imports.json')
        self.assertEqual([x['log_status'] for x in data['observations']], ['RECORDED_ZERO','UNKNOWN'])
        self.assertIn('pytest', data['observations'][0]['command_family'])
        written = (self.root / '.raee/imports.json').read_text()
        for secret in ('secretvalue', 'SECRET_RAW_STDOUT', 'veryprivate', 'this user text'):
            self.assertNotIn(secret, written)

    def test_codex_legacy_and_modern_observations(self):
        result = import_log(self.root, self.log('codex.jsonl', CODEX))
        self.assertEqual(result['provider'], 'codex')
        entries = read_json(self.root / '.raee/imports.json')['observations']
        self.assertEqual([x['log_status'] for x in entries], ['RECORDED_FAILURE','RECORDED_ZERO'])
        self.assertEqual([x['check_kind_hint'] for x in entries], ['unit','build'])

    def test_import_idempotent(self):
        f = self.log('codex.jsonl', CODEX)
        import_log(self.root, f, 'codex')
        self.assertEqual(import_log(self.root, f, 'codex')['new_observations'], 0)

    def test_no_auto_scan_and_no_execution(self):
        f = self.log('claude.jsonl', CLAUDE)
        (self.root / 'danger.py').write_text('open("EXECUTED","w").write("yes")')
        import_log(self.root, f)
        self.assertFalse((self.root / 'EXECUTED').exists())

    def test_import_does_not_satisfy_contract_even_when_logged_success(self):
        rid = add_requirement(self.root,'Browser login succeeds')
        set_expectation(self.root, rid, 'unit')
        import_log(self.root, self.log('claude.jsonl', CLAUDE))
        rep = audit(self.root)
        self.assertEqual(rep['evidence_contracts'][0]['status'], 'GAPS')
        self.assertFalse(is_passing(rep))
        self.assertGreater(len(rep['agent_evidence']['suggestions']), 0)

    def test_manual_link_is_not_proof(self):
        rid = add_requirement(self.root, 'Login API works')
        set_expectation(self.root, rid, 'unit')
        import_log(self.root, self.log('claude.jsonl', CLAUDE))
        evid = read_json(self.root / '.raee/imports.json')['observations'][0]['id']
        row = link_evidence(self.root, rid, evid, 'Relevant unit test command for login')
        self.assertEqual(row['requirement'], rid)
        rep = audit(self.root)
        self.assertEqual(rep['agent_evidence']['explicit'][0]['state'], 'LOG_ONLY_NOT_VALIDATED')
        self.assertEqual(rep['overall'], 'EVIDENCE_GAPS')

    def test_manual_local_link_receipt_is_self_declared(self):
        rid = add_requirement(self.root, 'Smoke check')
        entry = run_check(self.root, rid, [__import__('sys').executable,'-c','pass'], 10, kind='smoke')
        link_evidence(self.root, rid, entry['id'], 'The command is the declared smoke test')
        self.assertEqual(audit(self.root)['agent_evidence']['explicit'][0]['state'], 'OBSERVED_PASS_SELF_LINKED')

    def test_link_requires_real_receipt_and_reason(self):
        rid = add_requirement(self.root,'Feature')
        with self.assertRaises(ValueError):
            link_evidence(self.root, rid, 'Awrong', 'testing is relevant')
        with self.assertRaises(ValueError):
            link_evidence(self.root, rid, 'Awrong', 'short')

    def test_import_symlink_refused(self):
        target = self.log('claude.jsonl', CLAUDE)
        link = self.root / 'alias.jsonl'
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest('No symlink support')
        with self.assertRaises(ValueError):
            import_log(self.root, link)

    def test_invalid_provider_and_unknown_auto(self):
        p = self.log('random.jsonl',[{'type':'text','message':'no tools'}])
        with self.assertRaises(ValueError):
            import_log(self.root, p)
        with self.assertRaises(ValueError):
            import_log(self.root, p, 'toolx')

    def test_status_parser_is_conservative(self):
        self.assertEqual(parse_exit('Exit code: 0\ntext'),0)
        self.assertEqual(parse_exit('Process exited with code 7\n'),7)
        self.assertEqual(parse_exit('0'),0)
        self.assertIsNone(parse_exit('All tests passed'))
        self.assertIsNone(parse_exit('json output: exit code 0 in text'))

    def test_html_dashboard_escapes_log_metadata_and_user_content(self):
        add_requirement(self.root, '<img src=x onerror=alert(1)>')
        import_log(self.root, self.log('claude.jsonl',CLAUDE))
        page = html_report(audit(self.root))
        self.assertIn('Evidence Dashboard',page)
        self.assertIn('Agent transcript receipts',page)
        self.assertNotIn('<img src=x',page)
        self.assertNotIn('veryprivate',page)
        self.assertIn('Content-Security-Policy',page)

    def test_pr_diff_detects_state_regression(self):
        rid = add_requirement(self.root,'Signup works')
        set_expectation(self.root,rid,'unit')
        run_check(self.root, rid, [__import__('sys').executable,'-c','pass'],10,kind='unit')
        before = audit(self.root)
        (self.root/'app.py').write_text('print("changed")')
        after = audit(self.root)
        diff = compare_reports(before,after)
        self.assertEqual(diff['regressions'],1)
        self.assertIn('REGRESSION',[x['classification'] for x in diff['changes']])

    def test_pr_diff_resolved_observation_and_added(self):
        rid = add_requirement(self.root,'Login API works')
        set_expectation(self.root,rid,'integration')
        before = audit(self.root)
        run_check(self.root,rid,[__import__('sys').executable,'-c','pass'],10,kind='integration')
        after = audit(self.root)
        diff = compare_reports(before,after)
        self.assertEqual(diff['regressions'],0)
        self.assertIn('IMPROVED_OBSERVATION',[x['classification'] for x in diff['changes']])

    def test_diff_outputs_escape_html(self):
        rid = add_requirement(self.root,'<script>evil()</script> works')
        before=save_report(self.root)
        b=self.root/'base.json'
        b.write_text(json.dumps(before))
        run_check(self.root,rid,[__import__('sys').executable,'-c','pass'],10)
        h=self.root/'head.json'
        h.write_text(json.dumps(audit(self.root)))
        out=self.root/'delta'
        save_diff(b,h,out)
        page=(out/'pr-diff.html').read_text()
        self.assertIn('&lt;script&gt;',page)
        self.assertNotIn('<script>evil()',page)
        self.assertTrue((out/'pr-diff.md').is_file())

    def test_diff_invalid_report_rejected(self):
        bad=self.root/'bad.json'
        bad.write_text('{"whatever":1}')
        with self.assertRaises(ValueError):
            save_diff(bad,bad,self.root/'x')

    def test_cli_import_and_link(self):
        rid=add_requirement(self.root,'Pytest runs')
        f=self.log('claude.jsonl',CLAUDE)
        self.assertEqual(main(['--project',str(self.root),'import-agent','--file',str(f)]),0)
        evid=read_json(self.root/'.raee/imports.json')['observations'][0]['id']
        self.assertEqual(main(['--project',str(self.root),'link','--for',rid,'--evidence',evid,'--reason','Observed test potentially relevant']),0)
        self.assertTrue((self.root/'.raee/report.html').is_file())

    def test_cli_compare_fails_on_regression_only_with_flag(self):
        rid=add_requirement(self.root,'Unit verification')
        set_expectation(self.root,rid,'unit')
        run_check(self.root,rid,[__import__('sys').executable,'-c','pass'],10,kind='unit')
        b=self.root/'b.json';b.write_text(json.dumps(audit(self.root)))
        (self.root/'app.py').write_text('print(2)')
        h=self.root/'h.json';h.write_text(json.dumps(audit(self.root)))
        args=['--project',str(self.root),'compare','--base',str(b),'--head',str(h)]
        self.assertEqual(main(args),0)
        self.assertEqual(main(args+['--fail-on-regression']),1)

    def test_pr_diff_removed_passing_requirement_counts_as_regression(self):
        base = {'tool':'RAEE-Lite','source':{'sha256':'base'},'requirements':[
            {'id':'R1','requirement':'Account login works','state':'OBSERVED_PASS'}]}
        head = {'tool':'RAEE-Lite','source':{'sha256':'head'},'requirements':[]}
        result = compare_reports(base, head)
        self.assertEqual(result['regressions'], 1)
        self.assertEqual(result['changes'][0]['classification'], 'REMOVED_VERIFIED_EVIDENCE')

    def test_pr_diff_autocheck_regression(self):
        base = {'tool':'RAEE-Lite','requirements':[],
                'automatic_checks':[{'id':'auto:test','kind':'test','state':'OBSERVED_PASS'}]}
        head = {'tool':'RAEE-Lite','requirements':[],
                'automatic_checks':[{'id':'auto:test','kind':'test','state':'FAILED'}]}
        self.assertEqual(compare_reports(base, head)['regressions'], 1)

    def test_log_malformed_and_oversized_skipped(self):
        f = self.root/'claude.jsonl'
        with f.open('w') as out:
            out.write('not-json\n')
            out.write('{"type":"assistant","message":' + ' ' * 2_000_001 + '}\n')
            out.write(json.dumps(CLAUDE[0])+'\n')
            out.write(json.dumps(CLAUDE[1])+'\n')
        result=import_log(self.root,f,'claude')
        self.assertEqual(result['new_observations'],1)
        self.assertEqual(result['skipped_malformed_lines'],1)
        self.assertEqual(result['skipped_oversize_lines'],1)

if __name__ == '__main__':
    unittest.main()
