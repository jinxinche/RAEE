"""Real process checks for strict metadata capture and interrupted execution."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from raee_lite import safe_process


class ProcessEdgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.processes = []
        self.readers = []
        self.real_popen = subprocess.Popen
        self.real_thread = threading.Thread
        for patcher in (
                patch.object(safe_process.subprocess, 'Popen', side_effect=self.spawn),
                patch.object(safe_process.threading, 'Thread', side_effect=self.make_reader)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.cleanup_owned)

    def spawn(self, *args, **kwargs):
        process = self.real_popen(*args, **kwargs)
        self.processes.append(process)
        return process

    def make_reader(self, *args, **kwargs):
        reader = self.real_thread(*args, **kwargs)
        self.readers.append(reader)
        return reader

    def cleanup_owned(self):
        for process in self.processes:
            try:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGKILL)
                elif process.poll() is None:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait(timeout=3)
        for reader in self.readers:
            if reader.ident is not None:
                reader.join(timeout=3)
        if not any(reader.is_alive() for reader in self.readers):
            for process in self.processes:
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()

    def command(self, source):
        return [sys.executable, '-B', '-c', source]

    def capture(self, source, **kwargs):
        return safe_process.capture_bounded(self.command(source), self.root, **kwargs)

    def assert_cleaned(self):
        self.assertTrue(self.processes)
        for process in self.processes:
            self.assertIsNotNone(process.poll(), 'direct child still running')
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    self.assertTrue(stream.closed, 'owned pipe still open')
        self.assertFalse(any(reader.is_alive() for reader in self.readers))

    def test_default_still_discards_stderr_and_preserves_result(self):
        source = 'import os; os.write(2,b"warning" * 100000); os.write(1,b"ok"); exit(7)'
        for options in ({}, {'reject_stderr': False}):
            with self.subTest(options=options):
                self.assertEqual(self.capture(source, **options), (7, b'ok', False))
                self.assertIsNone(self.processes[-1].stderr)
        self.assert_cleaned()

    def test_strict_empty_stderr_preserves_stdout_and_exit_code(self):
        for code in (0, 7):
            with self.subTest(code=code):
                self.assertEqual(self.capture(f'import os; os.write(1,b"ok"); exit({code})',
                                              reject_stderr=True), (code, b'ok', False))
        self.assert_cleaned()

    def test_strict_rejects_warning_without_exposing_its_content(self):
        with self.assertRaisesRegex(ValueError, 'stderr') as caught:
            self.capture('import os; os.write(1,b"partial inventory"); '
                         'os.write(2,b"PRIVATE_WARNING_CONTENT")', reject_stderr=True)
        self.assertNotIn('PRIVATE_WARNING_CONTENT', str(caught.exception))
        self.assert_cleaned()

    def test_strict_rejects_any_stderr_byte(self):
        for data in (b'\x00', b' ', b'\n', b'\xff'):
            with self.subTest(data=data):
                with self.assertRaisesRegex(ValueError, 'stderr'):
                    self.capture(f'import os; os.write(2,{data!r})', reject_stderr=True)
        self.assert_cleaned()

    def test_git_filter_enumeration_rejects_warnings_with_accepted_exit_codes(self):
        for code, data in ((1, b''), (0, b'filter.probe.clean\x00')):
            with self.subTest(code=code):
                command = self.command(f'import os; os.write(1,{data!r}); '
                                       f'os.write(2,b"incomplete config"); exit({code})')
                self.assertIsNone(safe_process.git_metadata_command(command, self.root))
        self.assert_cleaned()

    def test_single_warning_aborts_without_waiting_for_eof(self):
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'stderr'):
            self.capture('import os,time; os.write(2,b"!"); time.sleep(30)',
                         reject_stderr=True, timeout=10)
        self.assertLess(time.monotonic() - started, 3)
        self.assert_cleaned()

    def test_stderr_flood_aborts_without_buffering_or_deadlock(self):
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'stderr'):
            self.capture('import os\nos.write(1,b"prefix")\n'
                         'while True: os.write(2,b"x" * 65536)\n',
                         limit=1024, reject_stderr=True, timeout=10)
        self.assertLess(time.monotonic() - started, 3)
        self.assert_cleaned()

    def test_strict_stdout_overflow_remains_bounded(self):
        _, raw, truncated = self.capture('import os; os.write(1,b"x" * 1000000)',
                                        limit=1024, reject_stderr=True, timeout=3)
        self.assertEqual(raw, b'x' * 1024)
        self.assertTrue(truncated)
        self.assert_cleaned()

    def test_strict_silent_timeout_closes_both_pipes(self):
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            self.capture('import time; time.sleep(30)', reject_stderr=True, timeout=0.2)
        self.assertLess(time.monotonic() - started, 3)
        self.assert_cleaned()

    def test_stderr_observed_during_timeout_cleanup_is_rejected(self):
        release_reader = threading.Event()
        self.addCleanup(release_reader.set)

        class DelayedRead:
            def __init__(self, stream):
                self.stream = stream

            def read(self, size):
                if not release_reader.wait(3):
                    raise RuntimeError('reader was not released')
                return self.stream.read(size)

            def close(self):
                self.stream.close()

            @property
            def closed(self):
                return self.stream.closed

        def spawn(*args, **kwargs):
            process = self.spawn(*args, **kwargs)
            process.stderr = DelayedRead(process.stderr)
            wait = process.wait

            def wait_and_release(*args, **kwargs):
                try:
                    return wait(*args, **kwargs)
                finally:
                    release_reader.set()

            process.wait = wait_and_release
            return process

        with patch.object(safe_process.subprocess, 'Popen', side_effect=spawn):
            with self.assertRaisesRegex(ValueError, 'stderr'):
                self.capture('import os,time; os.write(2,b"!"); time.sleep(30)',
                             reject_stderr=True, timeout=0.3)
        self.assert_cleaned()

    def test_stderr_after_stdout_eof_is_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'stderr'):
            self.capture('import os,time; os.close(1); time.sleep(0.05); os.write(2,b"!")',
                         reject_stderr=True)
        self.assert_cleaned()

    def test_stderr_eof_does_not_discard_later_stdout(self):
        result = self.capture('import os,time; os.close(2); time.sleep(0.05); os.write(1,b"ok")',
                              reject_stderr=True)
        self.assertEqual(result, (0, b'ok', False))
        self.assert_cleaned()

    def test_second_reader_start_failure_closes_both_pipes(self):
        def reader(*args, **kwargs):
            result = self.make_reader(*args, **kwargs)
            if len(self.readers) == 2:
                def fail_start():
                    raise RuntimeError('start failed')
                result.start = fail_start
            return result

        with patch.object(safe_process.threading, 'Thread', side_effect=reader):
            with self.assertRaisesRegex(RuntimeError, 'start failed'):
                self.capture('import time; time.sleep(30)', reject_stderr=True)
        self.assert_cleaned()

    def test_second_reader_constructor_failure_closes_unowned_pipe(self):
        def reader(*args, **kwargs):
            if self.readers:
                raise RuntimeError('constructor failed')
            return self.make_reader(*args, **kwargs)

        with patch.object(safe_process.threading, 'Thread', side_effect=reader):
            with self.assertRaisesRegex(RuntimeError, 'constructor failed'):
                self.capture('import time; time.sleep(30)', reject_stderr=True)
        self.assert_cleaned()

    def test_stderr_read_failure_is_not_a_successful_capture(self):
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
            process = self.spawn(*args, **kwargs)
            process.stderr = FailedRead(process.stderr)
            return process

        with patch.object(safe_process.subprocess, 'Popen', side_effect=spawn):
            with self.assertRaisesRegex(ValueError, 'bounded command output'):
                self.capture('import time; time.sleep(30)', reject_stderr=True)
        self.assert_cleaned()

    @unittest.skipUnless(os.name == 'posix' and hasattr(os, 'fork'), 'POSIX inherited stderr')
    def test_stderr_only_inherited_pipe_respects_deadline(self):
        source = ('import os,time\nif os.fork() == 0:\n'
                  '    os.close(1)\n    time.sleep(30)\n')
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            self.capture(source, reject_stderr=True, timeout=0.3)
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(self.processes[0].returncode, 0)
        self.assert_cleaned()

    def test_invalid_capture_limits_never_spawn(self):
        for limit in (None, '1', True, False, 0, -1, 8_000_001, 1.0, float('nan')):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    self.capture('pass', limit=limit)
        self.assertEqual(self.processes, [])

    def test_invalid_timeout_types_and_nonfinite_values_never_spawn(self):
        for execute in (safe_process.capture_bounded, safe_process.run):
            for timeout in (None, '1', True, False, 0, -1, 3601,
                            float('nan'), float('inf'), -float('inf')):
                with self.subTest(execute=execute.__name__, timeout=timeout):
                    with self.assertRaises(ValueError):
                        execute(self.command('pass'), self.root, timeout=timeout)
        self.assertEqual(self.processes, [])

    def failing_first_wait(self, exception):
        def spawn(*args, **kwargs):
            process = self.spawn(*args, **kwargs)
            wait = process.wait

            def fail(*args, **kwargs):
                process.wait = wait
                raise exception

            process.wait = fail
            return process
        return patch.object(safe_process.subprocess, 'Popen', side_effect=spawn)

    def test_strict_interrupted_wait_closes_both_pipes(self):
        with self.failing_first_wait(KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                self.capture('import time; time.sleep(30)', reject_stderr=True)
        self.assert_cleaned()

    def test_run_interrupted_wait_reaps_child(self):
        with self.failing_first_wait(KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                safe_process.run(self.command('import time; time.sleep(30)'), self.root, timeout=1)
        self.assert_cleaned()

    def test_run_failed_wait_reaps_child(self):
        with self.failing_first_wait(OSError('wait failed')):
            with self.assertRaisesRegex(OSError, 'wait failed'):
                safe_process.run(self.command('import time; time.sleep(30)'), self.root, timeout=1)
        self.assert_cleaned()

    def test_run_spawn_time_consumes_execution_budget(self):
        def delayed_spawn(*args, **kwargs):
            # Simulate slow process creation before starting a real child. The
            # remaining wait must not grant a second full execution budget.
            time.sleep(0.6)
            return self.spawn(*args, **kwargs)

        with patch.object(safe_process.subprocess, 'Popen', side_effect=delayed_spawn):
            code, error, _ = safe_process.run(
                self.command('import time; time.sleep(0.8)'), self.root, timeout=1)
        self.assertEqual((code, error), (124, 'TimeoutExpired'))
        self.assert_cleaned()


if __name__ == '__main__':
    unittest.main()
