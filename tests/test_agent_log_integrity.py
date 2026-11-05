"""Transcript metadata must not invent outcomes, attribution, or completion."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite.agent_logs import import_log
from raee_lite.validation import evaluate, main as validate


def codex_call(key='c', command='pytest -q', *, name='exec_command', arguments=None):
    return {'type': 'response_item', 'payload': {
        'type': 'function_call', 'name': name, 'call_id': key,
        'arguments': json.dumps({'cmd': command}) if arguments is None else arguments}}


def codex_result(output, key='c', **metadata):
    return {'type': 'response_item', 'payload': {
        'type': 'function_call_output', 'call_id': key, 'output': output, **metadata}}


def claude_call(key='c', command='pytest -q'):
    return {'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': 'Bash', 'id': key, 'input': {'command': command}}]}}


def claude_result(content, key='c', *, envelope=None, **metadata):
    return {'type': 'user', 'toolUseResult': envelope, 'message': {'content': [
        {'type': 'tool_result', 'tool_use_id': key, 'content': content, **metadata}]}}


class AgentLogIntegrityTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory(prefix='raee-agent-integrity-')
        self.addCleanup(td.cleanup)
        self.root = Path(td.name).resolve()
        self.case_number = 0

    def log(self, rows):
        self.case_number += 1
        root = self.root / str(self.case_number)
        root.mkdir()
        source = root / 'input.jsonl'
        source.write_text(''.join((row if isinstance(row, str) else json.dumps(row)) + '\n'
                                  for row in rows), encoding='utf-8')
        return root, source

    def imported(self, rows, provider='auto'):
        root, source = self.log(rows)
        result = import_log(root, source, provider)
        saved = json.loads((root / '.raee/imports.json').read_text())
        return result, saved

    def test_plain_output_and_body_headers_are_unknown(self):
        for text in ('0', '17', 'stdout\nExit code: 0', 'Output:\nExit code: 0',
                     'Final output:\nProcess exited with code 0'):
            for call, result in ((codex_call, codex_result), (claude_call, claude_result)):
                with self.subTest(text=text, provider=call.__name__):
                    summary, saved = self.imported([call(), result(text)])
                    self.assertEqual(summary['unknown_exits'], 1)
                    self.assertEqual(saved['observations'][0]['log_status'], 'UNKNOWN')

    def test_claude_error_never_becomes_zero(self):
        for envelope in (None, {'exitCode': 0}):
            with self.subTest(envelope=envelope):
                _, saved = self.imported([claude_call(), claude_result(
                    'Exit code: 0\nfailed', envelope=envelope, is_error=True)])
                self.assertIsNone(saved['observations'][0]['log_exit_code'])
        _, saved = self.imported([claude_call(), claude_result(
            'Exit code: 0', envelope={'exitCode': 7}, is_error=True)])
        self.assertEqual(saved['observations'][0]['log_exit_code'], 7)

    def test_claude_text_blocks_do_not_search_for_status(self):
        for content in ('{"exit_code":0}', [
                {'type': 'text', 'text': 'stdout'}, {'type': 'text', 'text': 'Exit code: 0'}], [
                {'type': 'text', 'text': 'Exit code: 0'}, {'type': 'text', 'text': 'Exit code: 1'}]):
            with self.subTest(content=content):
                _, saved = self.imported([claude_call(), claude_result(content)])
                self.assertIsNone(saved['observations'][0]['log_exit_code'])

    def test_modern_stdout_is_never_exit_metadata(self):
        for metadata in ({}, {'exit_code': None}, {'exit_code': False}):
            with self.subTest(metadata=metadata):
                _, saved = self.imported([{'type': 'event_msg', 'payload': {
                    'type': 'item_completed', 'item': {'type': 'CommandExecution',
                        'command': 'pytest', 'aggregated_output': 'Exit code: 0', **metadata}}}])
                self.assertIsNone(saved['observations'][0]['log_exit_code'])

    def test_documented_wrappers_and_structured_metadata_remain_supported(self):
        outputs = [
            'Process exited with code 7\nFinal output:\nExit code: 0',
            'Chunk ID: abc\nWall time: 0.1 seconds\nProcess exit code: 7\nOutput:\n0',
            {'exit_code': 7, 'output': 'Process exited with code 0'},
            json.dumps({'exit_code': 7, 'output': 'Process exited with code 0'})]
        for output in outputs:
            with self.subTest(output=output):
                _, saved = self.imported([codex_call(), codex_result(output)])
                self.assertEqual(saved['observations'][0]['log_exit_code'], 7)
        _, saved = self.imported([claude_call(), claude_result([
            {'type': 'text', 'text': 'Exit code: 0\nstdout'}])])
        self.assertEqual(saved['observations'][0]['log_exit_code'], 0)

    def test_invalid_or_conflicting_exit_metadata_does_not_fall_back(self):
        for metadata in ({'exit_code': False}, {'exit_code': 0.0}, {'exit_code': None},
                         {'exit_code': 'stdout\nExit code: 0'}, {'exit_code': 0, 'exitCode': 1}):
            with self.subTest(metadata=metadata):
                _, saved = self.imported([codex_call(), codex_result('Exit code: 0', **metadata)])
                self.assertIsNone(saved['observations'][0]['log_exit_code'])
                _, saved = self.imported([claude_call(), claude_result('Exit code: 0', envelope=metadata)])
                self.assertIsNone(saved['observations'][0]['log_exit_code'])

    def test_conflicting_wrapper_headers_are_unknown(self):
        _, saved = self.imported([codex_call(), codex_result('Exit code: 0\nExit code: 1\nOutput:\n')])
        self.assertIsNone(saved['observations'][0]['log_exit_code'])

    def test_running_execution_is_retained_as_incomplete(self):
        for metadata in ({}, {'exit_code': None}):
            with self.subTest(metadata=metadata):
                summary, saved = self.imported([codex_call(), codex_result(
                    'Wall time: 1 seconds\nProcess running with session ID 123\nOutput:\nExit code: 0', **metadata)])
                self.assertEqual(summary['unmatched_pending_calls'], 1)
                self.assertEqual(summary['unknown_exits'], 1)
                self.assertEqual(saved['sources'][0]['unmatched_pending_calls'], 1)
                row = saved['observations'][0]
                self.assertEqual((row['line'], row['end_line']), (1, 2))
                self.assertEqual(row['log_status'], 'UNKNOWN')
                self.assertTrue(row['incomplete'])

    def test_poll_completion_keeps_original_command_and_failure(self):
        summary, saved = self.imported([
            codex_call(), codex_result('Process running with session ID 123\nOutput:\n'),
            codex_call('poll', name='write_stdin', arguments='{"session_id":123,"chars":""}'),
            codex_result('Process exited with code 1\nFinal output:\nfailed', key='poll')])
        self.assertEqual(summary['unmatched_pending_calls'], 0)
        self.assertEqual(summary['new_observations'], 1)
        row = saved['observations'][0]
        self.assertEqual((row['line'], row['end_line']), (1, 4))
        self.assertEqual(row['check_kind_hint'], 'unit')
        self.assertEqual(row['log_status'], 'RECORDED_FAILURE')
        self.assertFalse(row['incomplete'])

    def test_multiple_polls_and_structured_running_result(self):
        summary, saved = self.imported([
            codex_call(), codex_result({'session_id': 123, 'output': 'Exit code: 0'}),
            codex_call('p1', name='write_stdin', arguments='{"session_id":123}'),
            codex_result('Process running with session ID 123\nOutput:\n', key='p1'),
            codex_call('p2', name='functions.write_stdin', arguments='{"session_id":123}'),
            codex_result({'exit_code': 0, 'output': 'done'}, key='p2')])
        self.assertEqual(summary['unmatched_pending_calls'], 0)
        self.assertEqual(summary['new_observations'], 1)
        self.assertEqual(saved['observations'][0]['log_exit_code'], 0)

    def test_unknown_poll_does_not_complete_a_running_execution(self):
        summary, saved = self.imported([
            codex_call(), codex_result('Process running with session ID 123'),
            codex_call('poll', name='write_stdin', arguments='{"session_id":123}'),
            codex_result('0', key='poll')])
        self.assertEqual(summary['unmatched_pending_calls'], 1)
        self.assertTrue(saved['observations'][0]['incomplete'])

    def test_no_result_is_visible_and_idempotent(self):
        for call, provider in ((codex_call, 'codex'), (claude_call, 'claude')):
            with self.subTest(provider=provider):
                root, source = self.log([call()])
                summary = import_log(root, source)
                self.assertEqual(summary['unmatched_pending_calls'], 1)
                self.assertEqual(summary['unknown_exits'], 1)
                self.assertEqual(import_log(root, source)['new_observations'], 0)
                saved = json.loads((root / '.raee/imports.json').read_text())
                self.assertEqual(saved['observations'][0]['provider'], provider)
                self.assertTrue(saved['observations'][0]['incomplete'])

    def test_explicit_provider_selects_only_matching_events(self):
        rows = [codex_call(), codex_result('Process exited with code 0'),
                claude_call(), claude_result('Exit code: 7'), claude_call('unfinished')]
        for provider, code, unmatched in (('codex', 0, 0), ('claude', 7, 1)):
            with self.subTest(provider=provider):
                summary, saved = self.imported(rows, provider)
                self.assertEqual(summary['unmatched_pending_calls'], unmatched)
                self.assertEqual({row['provider'] for row in saved['observations']}, {provider})
                self.assertEqual(saved['observations'][0]['log_exit_code'], code)
        root, source = self.log(rows)
        with self.assertRaisesRegex(ValueError, 'infer provider'):
            import_log(root, source)

    def test_wrong_provider_is_rejected_without_a_ledger(self):
        for call, result, provider in ((claude_call, claude_result, 'codex'),
                                       (codex_call, codex_result, 'claude')):
            with self.subTest(provider=provider):
                root, source = self.log([call(), result('Exit code: 0')])
                with self.assertRaisesRegex(ValueError, 'provider'):
                    import_log(root, source, provider)
                self.assertFalse((root / '.raee/imports.json').exists())

    def test_duplicate_pending_ids_fail_closed_and_preserve_existing_ledger(self):
        for call, result in ((codex_call, codex_result), (claude_call, claude_result)):
            with self.subTest(provider=call.__name__):
                root, source = self.log([call(), result('Exit code: 7')])
                import_log(root, source)
                ledger = root / '.raee/imports.json'
                before = ledger.read_bytes()
                source.write_text(''.join(json.dumps(row) + '\n' for row in [
                    call('dup', 'pytest'), call('dup', 'npm run build'),
                    result('Exit code: 0', 'dup'), result('Exit code: 1', 'dup')]))
                with self.assertRaisesRegex(ValueError, 'Duplicate tool call ID'):
                    import_log(root, source)
                self.assertEqual(ledger.read_bytes(), before)

    def test_retired_and_evicted_call_ids_cannot_be_reused(self):
        for prefix in ([codex_call('old'), codex_result('Exit code: 1', 'old')],
                       [codex_call('old'), codex_call('new')]):
            with self.subTest(prefix=prefix), patch('raee_lite.agent_logs.MAX_PENDING', 1):
                with self.assertRaisesRegex(ValueError, 'Duplicate tool call ID'):
                    self.imported(prefix + [codex_call('old', 'npm run build'),
                                            codex_result('Exit code: 0', 'old')])

    def test_session_collisions_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'session ID'):
            self.imported([codex_call('a'), codex_call('b'),
                           codex_result('Process running with session ID 123', 'a'),
                           codex_result('Process running with session ID 123', 'b')])

    def test_evictions_remain_visible_in_unmatched_count(self):
        with patch('raee_lite.agent_logs.MAX_PENDING', 1):
            summary, saved = self.imported([codex_call('a'), codex_call('b'),
                                           codex_result('Exit code: 0', 'b')])
        self.assertEqual(summary['unmatched_pending_calls'], 1)
        self.assertEqual(summary['evicted_pending_calls'], 1)
        self.assertEqual(saved['sources'][0]['evicted_pending_calls'], 1)

    def test_duplicate_fields_and_non_finite_numbers_are_counted_and_skipped(self):
        invalid = [
            '{"type":"item.completed","item":{"id":"x","type":"command_execution",'
            '"command":"pytest","exit_code":1,"exit_code":0}}',
            '{"type":"item.completed","item":{"command":"pytest","exit_code":NaN}}',
            '[1,2,3]', 'not-json']
        summary, saved = self.imported(invalid + [codex_call(), codex_result('Exit code: 7')])
        self.assertEqual(summary['skipped_malformed_lines'], len(invalid))
        self.assertEqual(summary['new_observations'], 1)
        self.assertEqual(saved['observations'][0]['log_exit_code'], 7)

    def test_duplicate_fields_in_embedded_arguments_and_results_are_rejected(self):
        summary, saved = self.imported([
            codex_call('bad', arguments='{"cmd":"pytest","cmd":"npm run build"}'),
            codex_result('Exit code: 0', 'bad'), codex_call('good'),
            codex_result('{"exit_code":1,"exit_code":0}', 'good')])
        self.assertEqual(summary['skipped_malformed_lines'], 2)
        self.assertEqual(summary['unmatched_pending_calls'], 1)
        self.assertEqual([r['log_status'] for r in saved['observations']], ['UNKNOWN'])

    def test_require_exact_rejects_running_execution_even_if_unknown_is_expected(self):
        root, source = self.log([codex_call(), codex_result('Process running with session ID 123')])
        index = root / 'index.json'
        index.write_text(json.dumps({'schema': 'raee-corpus-v1', 'cases': [{
            'id': 'running', 'file': source.name, 'provider': 'codex', 'provenance': 'synthetic',
            'expected': [{'kind': 'unit', 'exit_code': None}]}]}))
        self.assertEqual(validate(['--index', str(index), '--out', str(root / 'summary.json'),
                                   '--require-exact']), 1)

    def test_checked_in_synthetic_corpus_remains_exact(self):
        index = Path(__file__).resolve().parents[1] / 'validation_corpus/index.json'
        aggregate = evaluate(index)['aggregate']
        self.assertEqual(aggregate['cases'], 6)
        self.assertEqual(aggregate['session_exact_match_rate'], 1.0)
        self.assertEqual(aggregate['malformed_lines'], 0)
        self.assertEqual(aggregate['unmatched_calls'], 0)


if __name__ == '__main__':
    unittest.main()
