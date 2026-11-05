"""Security and product quality regression tests for a read-only preflight."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from raee_lite.preflight import evaluate
from raee_lite.cli import main


class ReadOnlyPreflight(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_missing_project_metadata_is_review_not_pass(self):
        r = evaluate(self.root)
        self.assertEqual(r['result'], 'REVIEW_REQUIRED')
        self.assertGreater(r['counts']['review'], 0)
        self.assertTrue(any(x['id'] == 'NO_EVIDENCE' for x in r['findings']))

    def test_no_mutation_even_when_missing(self):
        before = sorted(x.relative_to(self.root) for x in self.root.rglob('*'))
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main(['--project', str(self.root), 'preflight'])
        after = sorted(x.relative_to(self.root) for x in self.root.rglob('*'))
        self.assertEqual(rc, 0)
        self.assertEqual(before, after)

    def test_json_is_machine_readable(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(['--project', str(self.root), 'preflight', '--json']), 0)
        self.assertEqual(json.loads(buf.getvalue())['schema'], 'raee-preflight-v1')

    def _workflow(self, text):
        p = self.root / '.github' / 'workflows' / 'example.yml'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf8')
        return p

    def test_unpinned_external_action(self):
        self._workflow('on: push\njobs:\n  x:\n    steps:\n      - uses: actions/checkout@v4\n')
        self.assertIn('UNPINNED_ACTION', {x['id'] for x in evaluate(self.root)['findings']})

    def test_pinned_action_does_not_raise_action_finding(self):
        self._workflow('on: push\njobs:\n  x:\n    steps:\n      - uses: actions/checkout@' + 'a' * 40 + '\n')
        self.assertNotIn('UNPINNED_ACTION', {x['id'] for x in evaluate(self.root)['findings']})

    def test_write_all_blocks(self):
        self._workflow('permissions: write-all\n')
        r = evaluate(self.root)
        self.assertEqual(r['result'], 'BLOCKED')
        self.assertIn('WRITE_ALL', {x['id'] for x in r['findings']})

    def test_fork_privileged_trigger_prompts_review(self):
        self._workflow('on:\n  pull_request_target:\n    types: [opened]\n')
        self.assertIn('PR_TARGET_TRIGGER', {x['id'] for x in evaluate(self.root)['findings']})

    def test_workflow_run_is_reviewed(self):
        self._workflow('on:\n  workflow_run:\n    workflows: [build]\n')
        self.assertIn('WORKFLOW_RUN_TRIGGER', {x['id'] for x in evaluate(self.root)['findings']})

    def test_oversized_workflow_fails_closed(self):
        self._workflow('#' + 'x' * 260_000)
        self.assertEqual(evaluate(self.root)['result'], 'BLOCKED')

    @unittest.skipUnless(hasattr(os, 'symlink'), 'requires symlink support')
    def test_symlink_workflow_rejected(self):
        other = self.root / 'external.yml'
        other.write_text('permissions: write-all\n')
        wf = self._workflow('on: push\n')
        wf.unlink()
        try:
            wf.symlink_to(other)
        except OSError:
            self.skipTest('symlink creation restricted')
        self.assertIn('WORKFLOW_UNREADABLE', {x['id'] for x in evaluate(self.root)['findings']})

    def test_no_execution_even_with_malicious_scripts(self):
        self._workflow('on: push\njobs:\n  x:\n    steps:\n      - run: echo hacked > exploited\n')
        (self.root / 'package.json').write_text(json.dumps({'scripts': {'test': 'touch exploited'}}))
        evaluate(self.root)
        self.assertFalse((self.root / 'exploited').exists())

    def test_js_lockfile_flagged(self):
        (self.root / 'package.json').write_text('{}')
        self.assertIn('LOCKFILE_MISSING', {x['id'] for x in evaluate(self.root)['findings']})

    def test_ci_run_script_requires_minimum_tests(self):
        path = Path(__file__).resolve().parent.parent / 'scripts' / 'run_reviewed_suite.py'
        folder = self.root / 'tests'
        folder.mkdir()
        (folder / 'test_ok.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n')
        proc = subprocess.run([sys.executable, str(path), '--min-tests', '3', '--start-dir', str(folder)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn('too few tests', proc.stderr)

    def test_ci_run_script_one_test_passes(self):
        path = Path(__file__).resolve().parent.parent / 'scripts' / 'run_reviewed_suite.py'
        folder = self.root / 'tests'
        folder.mkdir()
        (folder / 'test_ok.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n')
        proc = subprocess.run([sys.executable, str(path), '--min-tests', '1', '--start-dir', str(folder)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

if __name__ == '__main__':
    unittest.main()
