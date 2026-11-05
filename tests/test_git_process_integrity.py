"""Owned-process and disposable-Git regression checks for inspection boundaries."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from raee_lite import core, discovery, safe_process


class CaptureIntegrityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.processes = []
        self.readers = []
        original_popen = subprocess.Popen
        original_thread = threading.Thread

        def spawn(*args, **kwargs):
            proc = original_popen(*args, **kwargs)
            self.processes.append(proc)
            return proc

        def make_thread(*args, **kwargs):
            reader = original_thread(*args, **kwargs)
            self.readers.append(reader)
            return reader

        self.addCleanup(self.cleanup_owned)
        self.enter_patch(patch.object(safe_process.subprocess, 'Popen', side_effect=spawn))
        self.enter_patch(patch.object(safe_process.threading, 'Thread', side_effect=make_thread))

    def enter_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def cleanup_owned(self):
        for proc in self.processes:
            try:
                if os.name == 'posix':
                    os.killpg(proc.pid, signal.SIGKILL)
                elif proc.poll() is None:
                    proc.kill()
            except ProcessLookupError:
                pass
            proc.wait(timeout=3)
        for reader in self.readers:
            if reader.ident is not None:
                reader.join(timeout=3)
        for proc in self.processes:
            if all(not reader.is_alive() for reader in self.readers):
                proc.stdout.close()

    def capture(self, source, **kwargs):
        return safe_process.capture_bounded(
            [sys.executable, '-B', '-c', source], self.root, **kwargs)

    def assert_cleaned(self):
        self.assertTrue(self.processes)
        for proc in self.processes:
            self.assertIsNotNone(proc.poll())
            self.assertTrue(proc.stdout.closed)
        self.assertFalse(any(reader.is_alive() for reader in self.readers))

    def test_exact_output_budget_and_overflow(self):
        for count in (0, 1023, 1024, 1025, 1_000_000):
            with self.subTest(count=count):
                _, raw, truncated = self.capture(
                    f'import os; os.write(1, b"x" * {count})', limit=1024, timeout=3)
                self.assertEqual(raw, b'x' * min(count, 1024))
                self.assertEqual(truncated, count > 1024)
        self.assert_cleaned()

    def test_timeout_reaps_direct_child_and_closes_pipe(self):
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            self.capture('import time; time.sleep(30)', timeout=0.2)
        self.assertLess(time.monotonic() - start, 3)
        self.assert_cleaned()

    def test_interrupted_wait_cleans_up_owned_process(self):
        # Patch an owned instance, retaining its real wait for cleanup.
        original_spawn = safe_process.subprocess.Popen.side_effect

        def spawn(*args, **kwargs):
            proc = original_spawn(*args, **kwargs)
            wait = proc.wait
            calls = 0

            def interrupt_once(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise KeyboardInterrupt()
                return wait(*args, **kwargs)

            proc.wait = interrupt_once
            return proc

        with patch.object(safe_process.subprocess, 'Popen', side_effect=spawn):
            with self.assertRaises(KeyboardInterrupt):
                self.capture('import time; time.sleep(30)', timeout=3)
        self.assert_cleaned()

    def test_reader_start_failure_cleans_up_owned_process(self):
        real_thread = threading.Thread.side_effect

        def fail_start(*args, **kwargs):
            reader = real_thread(*args, **kwargs)
            def start():
                raise RuntimeError('start failed')
            reader.start = start
            return reader

        with patch.object(safe_process.threading, 'Thread', side_effect=fail_start):
            with self.assertRaisesRegex(RuntimeError, 'start failed'):
                self.capture('import time; time.sleep(30)', timeout=3)
        self.assert_cleaned()

    def test_reader_failure_cleans_up_owned_process(self):
        original_spawn = safe_process.subprocess.Popen.side_effect

        class FailedRead:
            def __init__(self, stream):
                self.stream = stream

            def read(self, size):
                raise OSError('read failed')

            def close(self):
                self.stream.close()

            @property
            def closed(self):
                return self.stream.closed

        def spawn(*args, **kwargs):
            proc = original_spawn(*args, **kwargs)
            proc.stdout = FailedRead(proc.stdout)
            return proc

        with patch.object(safe_process.subprocess, 'Popen', side_effect=spawn):
            with self.assertRaisesRegex(ValueError, 'bounded command output'):
                self.capture('import time; time.sleep(30)', timeout=3)
        self.assert_cleaned()

    @unittest.skipUnless(os.name == 'posix' and hasattr(os, 'fork'), 'POSIX process-group cleanup')
    def test_parent_exit_with_inherited_stdout_cleans_process_group(self):
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            self.capture('import os,time; pid=os.fork(); time.sleep(30) if pid==0 else None',
                         timeout=0.3)
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual(self.processes[0].returncode, 0)
        # The sleeping descendant retains stdout: EOF proves its pipe was closed.
        self.assert_cleaned()


@unittest.skipUnless(shutil.which('git'), 'Git unavailable')
class GitInspectionIntegrityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        env_patch = patch.dict(os.environ, env, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.git('init', '-q')
        (self.root / 'tests').mkdir()
        self.source = self.root / 'tests/test_probe.py'
        self.source.write_text('def test_probe():\n    assert True\n', encoding='utf-8')
        self.git('add', 'tests/test_probe.py')
        # Fixture history is confined to this disposable repository.
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
        self.marker = self.root / '.git/helper-fired'
        script = self.root / '.git/helper.py'
        script.write_text(
            'import pathlib,sys\npathlib.Path(' + repr(str(self.marker)) +
            ').write_text("must not execute")\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n',
            encoding='utf-8')
        self.helper = f'"{Path(sys.executable).as_posix()}" -B "{script.as_posix()}"'

    def git(self, *args, data=None):
        return subprocess.run(['git', '--no-optional-locks', *args], cwd=self.root,
                              input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              check=True, timeout=15).stdout

    def attributes(self, driver='probe'):
        (self.root / '.gitattributes').write_text(f'tests/*.py filter={driver}\n', encoding='utf-8')

    def configure_filter(self, driver='probe', prefix=()):
        for setting in ('clean', 'process'):
            self.git('config', *prefix, f'filter.{driver}.{setting}', self.helper)
        self.git('config', *prefix, f'filter.{driver}.required', 'true')

    def assert_context_usable_without_helper(self):
        context = core.git_context(self.root)
        self.assertTrue(context['available'], context)
        self.assertFalse(self.marker.exists())

    def test_applicable_clean_process_and_required_filters_are_suppressed(self):
        self.attributes()
        self.configure_filter()
        self.source.write_text('assert False\n', encoding='utf-8')
        self.assert_context_usable_without_helper()

    def test_global_lfs_without_attributes_preserves_availability(self):
        global_config = self.root / '.git/global.cfg'
        self.configure_filter('lfs', ('--file', str(global_config)))
        with patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': str(global_config)}):
            self.assert_context_usable_without_helper()
            self.assertEqual(discovery.risk_signals(self.root), [])

    def test_included_config_filters_are_suppressed(self):
        self.attributes()
        included = self.root / '.git/included.cfg'
        self.configure_filter(prefix=('--file', str(included)))
        self.git('config', 'include.path', str(included))
        self.assert_context_usable_without_helper()

    def test_environment_config_filters_are_suppressed(self):
        self.attributes()
        env = {'GIT_CONFIG_COUNT': '3'}
        for index, (setting, value) in enumerate((('clean', self.helper),
                                                  ('process', self.helper), ('required', 'true'))):
            env[f'GIT_CONFIG_KEY_{index}'] = f'filter.probe.{setting}'
            env[f'GIT_CONFIG_VALUE_{index}'] = value
        with patch.dict(os.environ, env):
            self.assert_context_usable_without_helper()

    def test_diff_suppresses_helpers_and_preserves_risk_signals(self):
        self.attributes()
        self.configure_filter()
        self.source.write_text('import pytest\n@pytest.mark.skip(reason="probe")\n'
                               'def test_probe():\n    pass\n', encoding='utf-8')
        reasons = {item['reason'] for item in discovery.risk_signals(self.root)}
        self.assertIn('new_test_skip_markers', reasons)
        self.assertIn('removed_test_assertions', reasons)
        self.assertFalse(self.marker.exists())

    def test_driver_name_that_cannot_be_overridden_is_refused(self):
        self.attributes('probe=unsafe')
        self.configure_filter('probe=unsafe')
        self.assertEqual(core.git_context(self.root),
                         {'available': False, 'reason': 'git_filter_config_unavailable'})
        self.assertFalse(self.marker.exists())

    def test_incomplete_or_failed_config_refuses_status(self):
        responses = [(0, b'filter.probe.clean\x00', True),
                     (2, b'', False), (0, b'filter.probe.clean', False),
                     (0, b'not-a-filter\x00', False), (0, b'filter.\xff.clean\x00', False),
                     (1, b'unexpected', False), (0, b'', False)]
        for response in responses:
            with self.subTest(response=response):
                with patch.object(safe_process, 'capture_bounded', return_value=response):
                    with patch.object(core, 'capture_bounded') as execute:
                        self.assertEqual(core.git_context(self.root),
                                         {'available': False, 'reason': 'git_filter_config_unavailable'})
                        execute.assert_not_called()
        with patch.object(safe_process, 'capture_bounded',
                          side_effect=subprocess.TimeoutExpired(['git', 'config'], 15)):
            self.assertEqual(core.git_context(self.root)['reason'], 'git_filter_config_unavailable')
        self.assertFalse(self.marker.exists())

    def test_diff_refuses_incomplete_config_after_context_scan(self):
        context = {'available': True, 'changed_paths': [' M tests/test_probe.py']}
        with patch.object(core, 'git_context', return_value=context):
            with patch.object(safe_process, 'capture_bounded', return_value=(0, b'', True)):
                with patch.object(discovery, 'capture_bounded') as execute:
                    reasons = {item['reason'] for item in discovery.risk_signals(self.root)}
                    self.assertIn('git_filter_config_unavailable', reasons)
                    execute.assert_not_called()

    def test_truncated_inventory_cannot_collide_with_disk_filename(self):
        blob = self.git('hash-object', '-w', '--stdin', data=b'pass\n').decode().strip()
        prefix = '.venv/' + '/'.join(['d' * 200] * 4) + '/'
        names = [prefix + f'{index:05d}.py' for index in range(10_000)] + ['z.py']
        self.git('update-index', '--index-info',
                 data=''.join(f'100644 {blob}\t{name}\n' for name in names).encode())
        collision = self.root / '.raee-enumeration-overflow'
        collision.write_text('ordinary source\n', encoding='utf-8')
        omitted = self.root / 'z.py'
        omitted.write_text('assert True\n', encoding='utf-8')
        files = core.paths(self.root)
        self.assertIsInstance(files, list)
        self.assertTrue(files.enumeration_truncated)
        self.assertEqual(files.count(collision), 1)
        self.assertNotIn(omitted, files)
        before = core.fingerprint(self.root)
        self.assertIn({'file': '.', 'reason': 'enumeration_truncated'}, before['skipped'])
        omitted.write_text('raise RuntimeError("changed")\n', encoding='utf-8')
        after = core.fingerprint(self.root)
        self.assertTrue(after['skipped'])
        self.assertEqual(before['sha256'], after['sha256'])

    def test_old_sentinel_name_is_ordinary_source_when_not_truncated(self):
        collision = self.root / '.raee-enumeration-overflow'
        collision.write_text('before\n', encoding='utf-8')
        files = core.paths(self.root)
        self.assertIsInstance(files, list)
        self.assertFalse(files.enumeration_truncated)
        self.assertEqual(files.count(collision), 1)
        before = core.fingerprint(self.root)
        self.assertEqual(before['skipped'], [])
        collision.write_text('after\n', encoding='utf-8')
        self.assertNotEqual(before['sha256'], core.fingerprint(self.root)['sha256'])

    def test_truncation_metadata_participates_in_fingerprint(self):
        raw = b'tests/test_probe.py\x00'
        with patch.object(core, 'capture_bounded', return_value=(0, raw, False)):
            complete = core.fingerprint(self.root)
        with patch.object(core, 'capture_bounded', return_value=(-9, raw, True)):
            incomplete = core.fingerprint(self.root)
        self.assertEqual(complete['files'], incomplete['files'])
        self.assertNotEqual(complete['sha256'], incomplete['sha256'])
        self.assertTrue(incomplete['skipped'])


if __name__ == '__main__':
    unittest.main()
