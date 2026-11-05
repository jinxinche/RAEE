"""Behavioral negative controls for the reviewed-test acceptance gate."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('reviewed_runner', ROOT / 'scripts/run_reviewed_suite.py')
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class ReviewedSuiteTests(unittest.TestCase):
    def invoke(self, body, *, minima=None, errors=None, windows=False, transform=None):
        # Create real unittest cases, then exercise collection and execution
        # independently of the repository's full suite.
        namespace = {'unittest': unittest, '__name__': 'test_critical'}
        exec('class Check(unittest.TestCase):\n' + body, namespace)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(namespace['Check'])
        if transform:
            suite = transform(suite)
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / 'summary.json'
            with patch.object(RUNNER.unittest, 'TestLoader') as loader, \
                    patch.object(RUNNER, 'REQUIRED_TEST_MODULES', minima or {'test_critical': 1}), \
                    patch.object(RUNNER, 'os', SimpleNamespace(name='nt' if windows else 'posix')), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                loader.return_value.discover.return_value = suite
                loader.return_value.errors = errors or []
                code = RUNNER.main(['--min-tests', '1', '--require-critical-modules', '--summary', str(summary)])
            return code, json.loads(summary.read_text(encoding='utf-8'))

    def test_real_success_is_recorded(self):
        code, receipt = self.invoke(' def test_ok(self): self.assertEqual(2 + 2, 4)\n')
        self.assertEqual(code, 0)
        self.assertTrue(receipt['gate_passed'])
        self.assertEqual(receipt['tests_run'], 1)

    def test_runtime_skip_cannot_satisfy_critical_gate(self):
        code, receipt = self.invoke(' def test_ok(self): self.skipTest("disabled")\n')
        self.assertEqual(code, 1)
        self.assertFalse(receipt['gate_passed'])
        self.assertEqual(receipt['skipped'], 1)

    def test_class_teardown_skip_cannot_escape_critical_gate(self):
        code, receipt = self.invoke(
            ' def test_ok(self): pass\n'
            ' @classmethod\n def tearDownClass(cls): raise unittest.SkipTest("teardown skipped")\n')
        self.assertEqual(code, 1)
        self.assertEqual(receipt['tests_run'], 1)
        self.assertEqual(receipt['skipped'], 1)
        self.assertFalse(receipt['gate_passed'])

    def test_class_cleanup_skip_cannot_escape_critical_gate(self):
        code, receipt = self.invoke(
            ' def test_ok(self):\n'
            '  def cleanup(): raise unittest.SkipTest("cleanup skipped")\n'
            '  self.addClassCleanup(cleanup)\n')
        self.assertEqual(code, 1)
        self.assertEqual(receipt['skipped'], 1)
        self.assertFalse(receipt['gate_passed'])

    def test_discovery_exception_replaces_prior_successful_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            summary = Path(folder) / 'summary.json'
            summary.write_text(json.dumps({'gate_passed': True}), encoding='utf-8')
            with patch.object(RUNNER.unittest, 'TestLoader') as loader, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                loader.return_value.discover.side_effect = ImportError('missing start directory')
                code = RUNNER.main(['--min-tests', '1', '--summary', str(summary)])
            result = json.loads(summary.read_text(encoding='utf-8'))
            self.assertEqual(code, 2)
            self.assertFalse(result['gate_passed'])
            self.assertEqual(result['errors'], 1)
            self.assertEqual(result['tests_run'], 0)

    def test_expected_failure_cannot_satisfy_critical_gate(self):
        for windows in (False, True):
            with self.subTest(windows=windows), patch.object(
                    RUNNER, 'WINDOWS_CRITICAL_SKIPS', {'test_critical.Check.test_ok'}):
                code, receipt = self.invoke(
                    ' @unittest.expectedFailure\n def test_ok(self): self.fail("known bug")\n', windows=windows)
                self.assertEqual(code, 1)
                self.assertEqual(receipt['expected_failures'], 1)

    def test_padding_other_modules_does_not_replace_critical_coverage(self):
        code, receipt = self.invoke(' def test_ok(self): pass\n', minima={'missing_module': 1})
        self.assertEqual(code, 2)
        self.assertEqual(receipt['tests_run'], 0)

    def test_reduced_critical_module_is_rejected(self):
        code, _ = self.invoke(' def test_ok(self): pass\n', minima={'test_critical': 2})
        self.assertEqual(code, 2)

    def test_new_modules_require_explicit_minima_before_execution(self):
        def add_unregistered(suite):
            extra = unittest.FunctionTestCase(lambda: None)
            extra.id = lambda: 'test_unregistered.Extra.test_case'
            suite.addTest(extra)
            return suite

        code, receipt = self.invoke(' def test_ok(self): pass\n', transform=add_unregistered)
        self.assertEqual(code, 2)
        self.assertEqual(receipt['discovered'], 2)
        self.assertEqual(receipt['tests_run'], 0)

    def test_collection_errors_are_fail_visible(self):
        code, receipt = self.invoke(' def test_ok(self): pass\n', errors=['Import failed'])
        self.assertEqual(code, 2)
        self.assertEqual(receipt['errors'], 1)

    def test_duplicate_test_ids_cannot_pad_counts(self):
        code, receipt = self.invoke(' def test_ok(self): pass\n',
                                    transform=lambda suite: unittest.TestSuite([*suite, *suite]))
        self.assertEqual(code, 2)
        self.assertEqual(receipt['tests_run'], 0)

    def test_suite_cannot_silently_run_fewer_than_discovered(self):
        class ShortSuite(unittest.TestSuite):
            def run(self, result, debug=False):
                next(iter(self))(result)
                return result
        code, receipt = self.invoke(' def test_one(self): pass\n def test_two(self): pass\n', transform=ShortSuite)
        self.assertEqual(code, 1)
        self.assertEqual(receipt['discovered'], 2)
        self.assertEqual(receipt['tests_run'], 1)

    def test_narrow_windows_skip_exception_is_platform_specific(self):
        with patch.object(RUNNER, 'WINDOWS_CRITICAL_SKIPS', {'test_critical.Check.test_ok'}):
            for windows, expected in ((True, 0), (False, 1)):
                with self.subTest(windows=windows):
                    code, _ = self.invoke(' def test_ok(self): self.skipTest("platform")\n', windows=windows)
                    self.assertEqual(code, expected)

    def test_repeated_execution_cannot_replace_a_discovered_test(self):
        class RepeatSuite(unittest.TestSuite):
            def run(self, result, debug=False):
                first = next(iter(self))
                for _ in range(self.countTestCases()):
                    first(result)
                return result
        code, receipt = self.invoke(' def test_one(self): pass\n def test_two(self): pass\n', transform=RepeatSuite)
        self.assertEqual(code, 1)
        self.assertEqual(receipt['discovered'], 2)
        self.assertEqual(receipt['tests_run'], 2)
        self.assertFalse(receipt['gate_passed'])
