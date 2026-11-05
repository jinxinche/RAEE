"""CLI input failures must stay on stderr with the existing error exit code."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from raee_lite.cli import main
from raee_lite.core import add_requirement, init


class CliEdgesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def assert_input_error(self, args, message):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as raised:
                main(args)
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('Error:', err.getvalue())
        self.assertIn(message, err.getvalue())
        self.assertNotIn('Traceback', err.getvalue())

    def test_project_symlink_resolution_error_is_input_error(self):
        # Python 3.10-3.12 raises RuntimeError for a symlink loop. Inject it
        # so this regression also runs without Windows symlink privileges.
        with patch('raee_lite.cli.Path.resolve', side_effect=RuntimeError('Symlink loop')):
            self.assert_input_error(['--project', 'loop', 'doctor'], 'Symlink loop')

    def test_project_os_resolution_errors_are_input_errors(self):
        for error in (PermissionError('Permission denied'),
                      FileNotFoundError('Working directory disappeared'),
                      OSError('Path is too long')):
            with self.subTest(error=type(error).__name__):
                with patch('raee_lite.cli.Path.resolve', side_effect=error):
                    self.assert_input_error(['doctor'], str(error))

    def test_nul_project_path_is_input_error(self):
        self.assert_input_error(['--project', '\x00', 'doctor'], '')

    def test_missing_and_file_projects_remain_input_errors(self):
        ordinary_file = self.root / 'file.txt'
        ordinary_file.write_text('ordinary file', encoding='utf-8')
        for project in (self.root / 'missing', ordinary_file):
            with self.subTest(project=project.name):
                self.assert_input_error(['--project', str(project), 'doctor'],
                                        'Project folder does not exist')

    def isolated_args(self, memory, *, dry_run=True):
        return ['--project', str(self.root), 'isolate', '--for', 'R1',
                '--kind', 'unit', '--image', 'python:3.11',
                '--memory-mb', str(memory), '--allow-ci-execution',
                *(['--dry-run'] if dry_run else []), '--', 'python', '-c', 'pass']

    def run_cli(self, args):
        return subprocess.run([sys.executable, '-m', 'raee_lite', *args],
                              capture_output=True, text=True, encoding='utf-8',
                              env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, timeout=20)

    def prepare_requirement(self):
        init(self.root)
        add_requirement(self.root, 'A smoke check can run')

    def test_dry_run_rejects_out_of_range_memory(self):
        self.prepare_requirement()
        for memory in (-1, 0, 127, 4097):
            with self.subTest(memory=memory):
                result = self.run_cli(self.isolated_args(memory))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertIn('Error:', result.stderr)
                self.assertIn('128', result.stderr)
                self.assertIn('4096', result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    def test_invalid_memory_is_rejected_before_docker_access(self):
        self.prepare_requirement()
        real_which = shutil.which

        def refuse_docker(command, *args, **kwargs):
            if command == 'docker':
                raise AssertionError('Invalid input must not access Docker')
            return real_which(command, *args, **kwargs)

        with patch('raee_lite.isolated.shutil.which',
                   side_effect=refuse_docker):
            self.assert_input_error(self.isolated_args(4097, dry_run=False), '4096')

    def test_valid_memory_boundaries_still_produce_read_only_json_preview(self):
        self.prepare_requirement()
        before = {p.relative_to(self.root): p.read_bytes()
                  for p in self.root.rglob('*') if p.is_file()}
        for memory in (128, 4096):
            with self.subTest(memory=memory):
                result = self.run_cli(self.isolated_args(memory))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, '')
                self.assertEqual(json.loads(result.stdout)['mode'], 'DRY_RUN_NOT_EXECUTED')
        after = {p.relative_to(self.root): p.read_bytes()
                 for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
