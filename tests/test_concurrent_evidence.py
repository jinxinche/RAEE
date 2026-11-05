"""Real local writers and bounded traversal; Docker and platform faults are mocked."""
from __future__ import annotations

import errno
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from raee_lite import core, enhanced, isolated, safe_io
from raee_lite.contracts import set_expectation
from raee_lite.discovery import Check


WAIT_COMMAND = '''from pathlib import Path
import sys, time
ready, release = map(Path, sys.argv[1:3])
ready.touch()
deadline = time.monotonic() + 30
while not release.exists():
    if time.monotonic() > deadline: raise SystemExit(99)
    time.sleep(.01)
raise SystemExit(int(sys.argv[3]))
'''

LOCK_HOLDER = '''from pathlib import Path
import sys, time
from raee_lite.safe_io import exclusive_lock
lock, ready, release = map(Path, sys.argv[1:])
with exclusive_lock(lock):
    ready.touch()
    deadline = time.monotonic() + 30
    while not release.exists():
        if time.monotonic() > deadline: raise SystemExit(99)
        time.sleep(.01)
'''


class OwnedFixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='raee-concurrent-')
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.root = self.base / 'project'
        self.root.mkdir()

    def initialize(self):
        core.init(self.root)
        return core.add_requirement(self.root, 'First requirement')

    def start(self, args):
        env = dict(os.environ, PYTHONPATH=str(Path(core.__file__).resolve().parents[1]),
                   PYTHONDONTWRITEBYTECODE='1')
        for key in ('CI', 'GITHUB_ACTIONS', 'GITHUB_STEP_SUMMARY'):
            env.pop(key, None)
        process = subprocess.Popen([sys.executable, '-B', *args], env=env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)

        def cleanup():
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)

        self.addCleanup(cleanup)
        return process

    def wait_ready(self, marker, process):
        deadline = time.monotonic() + 20
        while not marker.exists():
            if process.poll() is not None:
                self.fail(f'Worker exited before barrier: {process.communicate()}')
            if time.monotonic() >= deadline:
                self.fail('Worker did not reach barrier')
            time.sleep(.01)

    def finish(self, process, expected=0):
        out, err = process.communicate(timeout=20)
        self.assertEqual(process.returncode, expected, (out, err))
        return out

    def holder(self, lock):
        ready, release = self.base / 'lock-ready', self.base / 'lock-release'
        process = self.start(['-c', LOCK_HOLDER, str(lock), str(ready), str(release)])
        self.wait_ready(ready, process)
        return process, release


class ConcurrentEvidenceTests(OwnedFixture):
    def check_failed_receipt_survives(self, discovered=False):
        rid = self.initialize()
        rid2 = core.add_requirement(self.root, 'Second requirement')
        for requirement in (rid, rid2):
            set_expectation(self.root, requirement, 'unit')
            core.run_check(self.root, requirement, [sys.executable, '-B', '-c', 'pass'], 10, kind='unit')
        workers = []
        for label, requirement, code in (('A', rid, 0), ('B', rid2, 1)):
            ready, release = self.base / (label + '-ready'), self.base / (label + '-release')
            command = [sys.executable, '-B', '-c', WAIT_COMMAND, str(ready), str(release), str(code)]
            if label == 'A' and discovered:
                program = ('from pathlib import Path\nimport sys,json\n'
                           'from raee_lite.enhanced import run_discovered\n'
                           'from raee_lite.discovery import Check\n'
                           'print(json.dumps(run_discovered(Path(sys.argv[1]), '
                           'Check("auto:fixture", "test", tuple(sys.argv[2:]), "fixture"), 35)))')
                process = self.start(['-c', program, str(self.root), *command])
            else:
                process = self.start(['-m', 'raee_lite', '--project', str(self.root),
                                      'run', '--for', requirement, '--kind', 'unit',
                                      '--timeout', '35', '--', *command])
            workers.append((process, ready, release))
        # Both commands have started, so both writers passed their initial ledger read.
        for process, ready, _ in workers:
            self.wait_ready(ready, process)
        workers[1][2].touch()
        self.finish(workers[1][0], 1)
        self.assertEqual(core.audit(self.root)['requirements'][1]['state'], 'FAILED_CHECK')
        workers[0][2].touch()
        self.finish(workers[0][0])
        runs = core.read_json(self.root / core.LEDGER)['runs']
        self.assertEqual([r['id'] for r in runs], ['E1', 'E2', 'E3', 'E4'])
        self.assertEqual((runs[2]['requirement'], runs[2]['observed_exit_code']), (rid2, 1))
        check = self.start(['-m', 'raee_lite', '--project', str(self.root),
                            'check', '--ci', '--strict', '--json'])
        report = json.loads(self.finish(check, 1))
        self.assertEqual(report['requirements'][1]['state'], 'FAILED_CHECK')
        self.assertFalse(enhanced.is_passing(report, strict=True))

    def test_separate_cli_writers_preserve_failed_receipt_and_ci_failure(self):
        self.check_failed_receipt_survives()

    def test_discovered_writer_preserves_concurrent_explicit_failure(self):
        self.check_failed_receipt_survives(discovered=True)

    def test_separate_append_processes_preserve_all_records_and_unique_ids(self):
        self.initialize()
        program = '''from pathlib import Path
import sys, time
from raee_lite import core
root, ready, release = map(Path, sys.argv[1:4])
original = core.read_json
def slow_read(*args, **kwargs):
    value = original(*args, **kwargs)
    time.sleep(.02)
    return value
core.read_json = slow_read
ready.touch()
deadline = time.monotonic() + 30
while not release.exists():
    if time.monotonic() > deadline: raise SystemExit(99)
    time.sleep(.01)
for index in range(4):
    core.append_receipt(root, {'worker': sys.argv[4], 'index': index})
'''
        release = self.base / 'append-release'
        workers = []
        for i in range(4):
            ready = self.base / f'append-{i}'
            process = self.start(['-c', program, str(self.root), str(ready), str(release), str(i)])
            workers.append((process, ready))
        for process, ready in workers:
            self.wait_ready(ready, process)
        release.touch()
        for process, _ in workers:
            self.finish(process)
        runs = core.read_json(self.root / core.LEDGER)['runs']
        self.assertEqual(len(runs), 16)
        self.assertEqual(len({r['id'] for r in runs}), 16)
        self.assertEqual({(r['worker'], r['index']) for r in runs},
                         {(str(w), i) for w in range(4) for i in range(4)})

    def test_append_obeys_other_process_lock_and_leaves_ledger_unchanged(self):
        self.initialize()
        before = (self.root / core.LEDGER).read_bytes()
        process, release = self.holder(self.root / core.LEDGER_LOCK)
        with self.assertRaises(TimeoutError):
            core.append_receipt(self.root, {'observed_exit_code': 1}, lock_timeout=.05)
        self.assertEqual((self.root / core.LEDGER).read_bytes(), before)
        release.touch()
        self.finish(process)
        self.assertEqual(core.append_receipt(self.root, {})['id'], 'E1')

    def test_every_writer_rechecks_capacity_after_execution(self):
        rid = self.initialize()
        for kind in ('explicit', 'discovered', 'isolated'):
            with self.subTest(kind=kind):
                core.write_json(self.root / core.LEDGER, {'schema': 1, 'runs': []})
                committed = []

                def consume_slot(*args, **kwargs):
                    core.append_receipt(self.root, {'requirement': rid, 'observed_exit_code': 1})
                    committed.append((self.root / core.LEDGER).read_bytes())
                    return 0, None, .1

                with patch.object(core, 'MAX_RUNS', 1):
                    if kind == 'explicit':
                        with patch.object(core, 'bounded_run', side_effect=consume_slot):
                            with self.assertRaisesRegex(ValueError, 'ledger limit'):
                                core.run_check(self.root, rid, [sys.executable, '-V'], 10)
                    elif kind == 'discovered':
                        check = Check('auto:fixture', 'test', (sys.executable, '-V'), 'fixture')
                        with patch.object(enhanced, 'bounded_run', side_effect=consume_slot):
                            with self.assertRaisesRegex(ValueError, 'ledger limit'):
                                enhanced.run_discovered(self.root, check)
                    else:
                        with patch.object(isolated.shutil, 'which', return_value=sys.executable), \
                             patch.object(isolated, '_require_local_daemon'), \
                             patch.object(isolated, '_docker_image_id', return_value='sha256:' + 'a' * 64), \
                             patch.object(isolated, 'bounded_run', side_effect=consume_slot), \
                             patch.object(isolated.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                             patch.object(isolated.tempfile, 'tempdir', str(self.base)):
                            with self.assertRaisesRegex(ValueError, 'ledger limit'):
                                isolated.replay(self.root, rid, 'unit', ['python', '-V'], image='python:3.11')
                self.assertEqual(len(committed), 1)
                self.assertEqual((self.root / core.LEDGER).read_bytes(), committed[0])

    def test_byte_capacity_failure_preserves_ledger_and_releases_lock(self):
        self.initialize()
        before = (self.root / core.LEDGER).read_bytes()
        with patch.object(safe_io, 'MAX_STORED_JSON', 128):
            with self.assertRaisesRegex(ValueError, 'byte limit'):
                core.append_receipt(self.root, {'payload': 'x' * 200})
        self.assertEqual((self.root / core.LEDGER).read_bytes(), before)
        self.assertEqual(core.append_receipt(self.root, {})['id'], 'E1')

    def test_id_allocation_does_not_reuse_retained_id_after_archiving(self):
        self.initialize()
        core.write_json(self.root / core.LEDGER, {'schema': 1, 'runs': [{'id': 'E2'}]})
        self.assertEqual(core.append_receipt(self.root, {})['id'], 'E3')


class EvidenceLockTests(OwnedFixture):
    def test_timeout_is_bounded_and_lock_inode_survives_release(self):
        lock = self.base / 'stable.lock'
        process, release = self.holder(lock)
        identity = lock.stat()
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            with safe_io.exclusive_lock(lock, timeout=.05):
                self.fail('Acquired another process lock')
        self.assertLess(time.monotonic() - started, 2)
        release.touch()
        self.finish(process)
        self.assertTrue(lock.exists())
        with safe_io.exclusive_lock(lock, timeout=.1):
            self.assertEqual((lock.stat().st_dev, lock.stat().st_ino),
                             (identity.st_dev, identity.st_ino))
        self.assertTrue(lock.exists())

    def test_exception_releases_lock_without_unlinking(self):
        lock = self.base / 'stable.lock'
        with self.assertRaisesRegex(RuntimeError, 'fixture'):
            with safe_io.exclusive_lock(lock):
                identity = lock.stat()
                raise RuntimeError('fixture')
        self.assertEqual(lock.stat().st_ino, identity.st_ino)
        with safe_io.exclusive_lock(lock, timeout=0):
            pass

    def test_process_exit_releases_lock_without_unlinking(self):
        lock = self.base / 'stable.lock'
        program = ('import os,sys\nfrom pathlib import Path\n'
                   'from raee_lite.safe_io import exclusive_lock\n'
                   'with exclusive_lock(Path(sys.argv[1])): os._exit(0)')
        self.finish(self.start(['-c', program, str(lock)]))
        identity = lock.stat()
        with safe_io.exclusive_lock(lock, timeout=.1):
            self.assertEqual(lock.stat().st_ino, identity.st_ino)

    def test_nonregular_lock_is_rejected_before_open(self):
        lock = self.base / 'stable.lock'
        lock.mkdir()
        with patch.object(safe_io.os, 'open') as opened:
            with self.assertRaisesRegex(ValueError, 'regular file'):
                with safe_io.exclusive_lock(lock):
                    pass
        opened.assert_not_called()

    def test_symlink_lock_or_parent_is_rejected_without_platform_symlink_privileges(self):
        lock = self.base / 'stable.lock'
        original = Path.is_symlink
        for forbidden in (lock, self.base):
            with self.subTest(forbidden=forbidden):
                with patch.object(Path, 'is_symlink', lambda p: p == forbidden or original(p)), \
                     patch.object(safe_io.os, 'open') as opened:
                    with self.assertRaisesRegex(ValueError, 'symlink'):
                        with safe_io.exclusive_lock(lock):
                            pass
                opened.assert_not_called()

    def test_opened_lock_identity_is_checked(self):
        lock, alternate = self.base / 'stable.lock', self.base / 'other.lock'
        lock.touch()
        alternate.touch()
        original = os.open
        with patch.object(safe_io.os, 'open', side_effect=lambda p, flags, mode: original(alternate, flags, mode)), \
             patch.object(safe_io, '_try_lock') as acquire:
            with self.assertRaisesRegex(ValueError, 'changed'):
                with safe_io.exclusive_lock(lock):
                    pass
        acquire.assert_not_called()
        self.assertTrue(lock.exists())

    def test_hardlinked_empty_lock_never_modifies_external_file(self):
        external, lock = self.base / 'external-empty', self.root / 'stable.lock'
        external.touch()
        os.link(external, lock)
        with patch.object(safe_io, '_try_lock') as acquire:
            with self.assertRaisesRegex(ValueError, 'single-link'):
                with safe_io.exclusive_lock(lock):
                    pass
        acquire.assert_not_called()
        self.assertEqual(external.read_bytes(), b'')
        self.assertTrue(lock.exists())

    def test_hardlink_added_during_open_is_rejected_before_initializing(self):
        lock, external = self.root / 'stable.lock', self.base / 'external-empty'
        lock.touch()
        original = os.open

        def add_link(path, flags, mode):
            os.link(lock, external)
            return original(path, flags, mode)

        with patch.object(safe_io.os, 'open', side_effect=add_link), \
             patch.object(safe_io, '_try_lock') as acquire:
            with self.assertRaisesRegex(ValueError, 'changed'):
                with safe_io.exclusive_lock(lock):
                    pass
        acquire.assert_not_called()
        self.assertEqual(external.read_bytes(), b'')
        self.assertTrue(lock.exists())

    def test_invalid_timeout_rejected_before_file_creation(self):
        for timeout in (-1, float('inf'), float('nan'), True, 61):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                with safe_io.exclusive_lock(self.base / 'stable.lock', timeout=timeout):
                    pass
        self.assertFalse((self.base / 'stable.lock').exists())

    def test_unsupported_lock_error_is_not_retried(self):
        with patch.object(safe_io, '_try_lock', side_effect=OSError(errno.ENOTSUP, 'fixture')) as acquire:
            with self.assertRaises(OSError):
                with safe_io.exclusive_lock(self.base / 'stable.lock'):
                    pass
        self.assertEqual(acquire.call_count, 1)

    def test_windows_backend_uses_nonblocking_fixed_byte_range(self):
        fake = SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0, locking=Mock())
        with patch.object(safe_io.os, 'name', 'nt'), \
             patch.dict(sys.modules, {'msvcrt': fake}), \
             patch.object(safe_io.os, 'lseek') as seek:
            safe_io._try_lock(42)
            safe_io._unlock(42)
        self.assertEqual(fake.locking.call_args_list, [unittest.mock.call(42, 2, 1),
                                                      unittest.mock.call(42, 0, 1)])
        self.assertEqual(seek.call_args_list, [unittest.mock.call(42, 0, os.SEEK_SET)] * 2)


class BoundedTraversalTests(OwnedFixture):
    def actions(self):
        return (lambda: core.fingerprint(self.root),
                lambda: isolated.stage_snapshot(self.root, self.base / 'snapshot'))

    def test_unreadable_subdirectory_refuses_fingerprint_and_snapshot(self):
        private = self.root / 'private'
        private.mkdir()
        (private / 'source.py').write_text('VALUE = 1\n')
        original = os.scandir

        def denied(path):
            if Path(path) == private:
                raise PermissionError(errno.EACCES, 'fixture', str(path))
            return original(path)

        for action in self.actions():
            with patch.object(safe_io.os, 'scandir', side_effect=denied):
                with self.assertRaisesRegex(ValueError, 'unreadable directory'):
                    action()

    def test_scandir_iteration_error_cannot_return_partial_success(self):
        class BrokenScan:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def __iter__(self):
                yield SimpleNamespace(name='first.py', is_dir=lambda **kw: False)
                raise OSError(errno.EIO, 'fixture iteration failure')

        for action in self.actions():
            with patch.object(safe_io.os, 'scandir', return_value=BrokenScan()):
                with self.assertRaisesRegex(ValueError, 'unreadable directory'):
                    action()

    def test_unreadable_directory_blocks_execution_and_existing_passing_report(self):
        rid = self.initialize()
        core.run_check(self.root, rid, [sys.executable, '-B', '-c', 'pass'], 10)
        private = self.root / 'private'
        private.mkdir()
        original = os.scandir

        def denied(path):
            if Path(path) == private:
                raise PermissionError('fixture')
            return original(path)

        with patch.object(safe_io.os, 'scandir', side_effect=denied), \
             patch.object(core, 'bounded_run') as execute:
            with self.assertRaisesRegex(ValueError, 'unreadable directory'):
                core.run_check(self.root, rid, [sys.executable, '-V'], 10)
            with self.assertRaisesRegex(ValueError, 'unreadable directory'):
                enhanced.audit(self.root)
        execute.assert_not_called()

    def test_empty_directories_consume_budget_before_copying(self):
        for i in range(4):
            (self.root / f'empty-{i}').mkdir()
        with patch.object(core, 'MAX_SCAN_DIRECTORIES', 3), \
             patch.object(isolated, 'MAX_SCAN_DIRECTORIES', 3):
            for action in self.actions():
                with self.assertRaisesRegex(ValueError, 'directory budget'):
                    action()
        self.assertEqual(list((self.base / 'snapshot').iterdir()), [])

    def test_excluded_files_consume_budget_before_filtering(self):
        for i in range(4):
            (self.root / f'.env-{i}.pyc').touch()
        with patch.object(core, 'MAX_SCAN_ENTRIES', 3), \
             patch.object(isolated, 'MAX_SCAN_ENTRIES', 3):
            for action in self.actions():
                with self.assertRaisesRegex(ValueError, 'entry budget'):
                    action()

    def test_scan_stops_after_budget_plus_one_without_materializing_directory(self):
        seen, closed = [], []

        class LargeScan:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                closed.append(True)
            def __iter__(self):
                for i in range(1000):
                    seen.append(i)
                    yield SimpleNamespace(name=f'.env-{i}.pyc', is_dir=lambda **kw: False)

        with patch.object(safe_io.os, 'scandir', return_value=LargeScan()), \
             patch.object(core, 'MAX_SCAN_ENTRIES', 3):
            with self.assertRaisesRegex(ValueError, 'entry budget'):
                core.paths(self.root)
        self.assertEqual(seen, [0, 1, 2, 3])
        self.assertEqual(closed, [True])

    def test_excluded_directories_count_without_descending(self):
        for name in ('.git', '.raee', 'node_modules'):
            (self.root / name).mkdir()
        # Force the fallback even though this fixture contains a .git directory.
        with patch.object(core.shutil, 'which', return_value=None), \
             patch.object(core, 'MAX_SCAN_DIRECTORIES', 3), \
             patch.object(isolated, 'MAX_SCAN_DIRECTORIES', 3):
            for action in self.actions():
                with self.assertRaisesRegex(ValueError, 'directory budget'):
                    action()

    def test_exclusion_sample_is_bounded_while_totals_remain_exact(self):
        for i in range(250):
            (self.root / f'.env-{i:04d}').touch()
        (self.root / '.git').mkdir()
        (self.root / '.git' / 'never-read').write_bytes(b'secret')
        result = isolated.stage_snapshot(self.root, self.base / 'snapshot')
        self.assertEqual(result['files'], 0)
        self.assertEqual(result['bytes'], 0)
        self.assertEqual(result['excluded_total'], 251)
        self.assertEqual(result['unsafe_excluded_total'], 250)
        self.assertEqual(len(result['excluded_paths']), 100)

    def test_pending_directory_symlink_is_refused_without_following(self):
        private = self.root / 'private'
        private.mkdir()
        original = Path.is_symlink
        for action in self.actions():
            with patch.object(Path, 'is_symlink', lambda p: p == private or original(p)):
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    action()

    def test_nonregular_entries_are_not_copied(self):
        source = self.root / 'linked'
        source.write_bytes(b'not safe to copy')
        original = Path.lstat

        def pretend_link(path):
            return SimpleNamespace(st_mode=stat.S_IFLNK) if path == source else original(path)

        with patch.object(Path, 'lstat', pretend_link):
            result = isolated.stage_snapshot(self.root, self.base / 'snapshot')
        self.assertFalse((self.base / 'snapshot' / 'linked').exists())
        self.assertEqual(result['unsafe_excluded_total'], 1)

    def test_snapshot_preserves_binary_bytes(self):
        data = b'first\r\nsecond\x1a\x00\xff'
        (self.root / 'source.dat').write_bytes(data)
        result = isolated.stage_snapshot(self.root, self.base / 'snapshot')
        self.assertEqual((self.base / 'snapshot' / 'source.dat').read_bytes(), data)
        self.assertEqual(result['bytes'], len(data))

    def test_regular_file_named_like_excluded_directory_is_still_fingerprinted(self):
        (self.root / 'build').write_text('source')
        self.assertEqual(core.fingerprint(self.root)['files'], 1)


if __name__ == '__main__':
    unittest.main()
