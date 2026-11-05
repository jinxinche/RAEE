"""Discovery must not manufacture passing commands or follow linked indicators."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from raee_lite.discovery import discover
from raee_lite.enhanced import audit, ensure_initialized, run_discovered


class DiscoveryIntegrityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base / 'project'
        self.root.mkdir()
        self.external = self.base / 'external'
        self.external.mkdir()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def test_suffix_unittest_file_cannot_pass_without_running_tests(self):
        self.write('tests/service_test.py',
                   'import unittest\nclass ServiceTests(unittest.TestCase):\n'
                   '    def test_failure(self):\n        self.fail("must run")\n')
        checks, _ = discover(self.root)
        self.assertEqual(len(checks), 1)
        result = subprocess.run(checks[0].command, cwd=self.root, timeout=15,
                                capture_output=True, text=True,
                                env={**os.environ, 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
                                     'PYTEST_ADDOPTS': ''})
        # Either pytest observes the failure, or its absence fails explicitly.
        # unittest's default pattern previously returned OK after zero tests.
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(checks[0].command, (sys.executable, '-m', 'pytest', '-q'))

    def test_suffix_function_test_cannot_produce_a_passing_audit(self):
        self.write('tests/service_test.py', 'def test_failure():\n    assert False\n')
        ensure_initialized(self.root)
        checks, _ = discover(self.root)
        self.assertEqual(len(checks), 1)
        with patch.dict(os.environ, {'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTEST_ADDOPTS': ''}):
            receipt = run_discovered(self.root, checks[0], timeout=15)
        self.assertNotEqual(receipt['observed_exit_code'], 0)
        self.assertEqual(audit(self.root)['overall'], 'FAILED_CHECK')

    def test_both_python_patterns_share_one_preview_without_importing(self):
        self.write('tests/test_prefix.py', 'raise RuntimeError("must not import")\n')
        self.write('tests/suffix_test.py', 'raise RuntimeError("must not import")\n')
        with patch('raee_lite.discovery.subprocess.Popen', side_effect=AssertionError('executed')):
            checks, _ = discover(self.root)
        self.assertEqual([check.id for check in checks], ['auto:python:test'])
        self.assertEqual(checks[0].command, (sys.executable, '-m', 'pytest', '-q'))

    def test_directories_named_like_tests_do_not_select_a_runner(self):
        (self.root / 'tests/test_directory.py').mkdir(parents=True)
        (self.root / 'tests/directory_test.py').mkdir()
        checks, notes = discover(self.root)
        self.assertEqual(checks, [])
        self.assertTrue(notes)

    def test_linked_test_directory_is_not_enumerated(self):
        (self.external / 'test_external.py').write_text('assert False\n', encoding='utf-8')
        (self.root / 'tests').symlink_to(self.external, target_is_directory=True)
        with patch.object(Path, 'glob', side_effect=AssertionError('followed linked tests')):
            checks, notes = discover(self.root)
        self.assertEqual(checks, [])
        self.assertTrue(any('symlinked' in note and 'tests' in note for note in notes))

    def test_linked_python_config_blocks_an_implicit_test_command(self):
        self.write('tests/test_local.py', 'def test_local():\n    pass\n')
        for name in ('pytest.ini', 'conftest.py', 'pyproject.toml', 'setup.cfg'):
            with self.subTest(name=name):
                target = self.external / name
                target.write_text('', encoding='utf-8')
                link = self.root / name
                link.symlink_to(target)
                try:
                    checks, notes = discover(self.root)
                    self.assertEqual(checks, [])
                    self.assertTrue(any('symlinked' in note and name in note for note in notes))
                finally:
                    link.unlink()

    def test_linked_test_file_does_not_select_a_runner(self):
        target = self.external / 'test_external.py'
        target.write_text('assert False\n', encoding='utf-8')
        (self.root / 'tests').mkdir()
        (self.root / 'tests/test_external.py').symlink_to(target)
        checks, _ = discover(self.root)
        self.assertEqual(checks, [])

    def test_unsupported_or_malformed_package_manager_is_not_replaced_by_npm(self):
        for manager in ('pnpm@9.0.0', 'yarn@4.0.0', 'bun@1.0.0', None, {}, '', 'npm'):
            with self.subTest(manager=manager):
                self.write('package.json', json.dumps({
                    'packageManager': manager, 'scripts': {'test': 'echo success'}}))
                with patch('raee_lite.discovery.shutil.which', return_value='/fake/npm') as which:
                    checks, notes = discover(self.root)
                self.assertEqual(checks, [])
                self.assertTrue(any('Unsupported' in note and 'packageManager' in note for note in notes))
                which.assert_not_called()

    def test_supported_npm_scripts_remain_preview_only(self):
        for declaration in ({}, {'packageManager': 'npm@10.0.0'}):
            with self.subTest(declaration=declaration):
                self.write('package.json', json.dumps({**declaration, 'scripts': {
                    'test': 'node test.js', 'typecheck': 'tsc --noEmit',
                    'lint': 'eslint .', 'build': 'tsc'}}))
                with patch('raee_lite.discovery.shutil.which', return_value='/fake/npm'), \
                        patch('raee_lite.discovery.subprocess.Popen', side_effect=AssertionError('executed')):
                    checks, notes = discover(self.root)
                self.assertEqual([check.kind for check in checks], ['test', 'typecheck', 'lint', 'build'])
                self.assertEqual([check.command for check in checks],
                                 [('/fake/npm', 'run', kind) for kind in ('test', 'typecheck', 'lint', 'build')])
                self.assertEqual(notes, [])

    def test_malformed_scripts_are_reported(self):
        self.write('package.json', json.dumps({'scripts': ['test']}))
        checks, notes = discover(self.root)
        self.assertEqual(checks, [])
        self.assertTrue(any('Could not parse package.json' in note for note in notes))

    def test_linked_package_json_is_reported_without_reading(self):
        target = self.external / 'package.json'
        target.write_text('{"scripts":{"test":"echo success"}}', encoding='utf-8')
        (self.root / 'package.json').symlink_to(target)
        with patch('raee_lite.discovery.read_bytes', side_effect=AssertionError('read linked config')):
            checks, notes = discover(self.root)
        self.assertEqual(checks, [])
        self.assertTrue(any('symlink' in note and 'package.json' in note for note in notes))

    def test_linked_ruff_config_does_not_select_an_implicit_command(self):
        for name in ('ruff.toml', '.ruff.toml'):
            with self.subTest(name=name):
                target = self.external / name
                target.write_text('', encoding='utf-8')
                link = self.root / name
                link.symlink_to(target)
                try:
                    with patch('raee_lite.discovery.shutil.which', return_value='/fake/ruff'):
                        checks, notes = discover(self.root)
                    self.assertEqual(checks, [])
                    self.assertTrue(any('symlinked' in note and 'Ruff' in note for note in notes))
                finally:
                    link.unlink()

    def test_regular_ruff_config_selects_the_resolved_command_once(self):
        self.write('ruff.toml', '')
        with patch('raee_lite.discovery.shutil.which', return_value='/fake/ruff') as which:
            checks, _ = discover(self.root)
        self.assertEqual([check.command for check in checks], [('/fake/ruff', 'check', '.')])
        which.assert_called_once_with('ruff')
