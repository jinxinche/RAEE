"""Transcript-store transactions exercised by independent local processes."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite import agent_logs, core, safe_io


IMPORT_WORKER = '''from pathlib import Path
import json, sys, time
from raee_lite import agent_logs, core
root, ready, release = map(Path, sys.argv[1:4])
agent_logs.MAX_OBSERVATIONS = int(sys.argv[4])
original = core.read_json
def slow_read(*args, **kwargs):
    value = original(*args, **kwargs)
    # Widen the vulnerable read/replace interval in an unlocked importer.
    time.sleep(.05)
    return value
core.read_json = slow_read
ready.touch()
deadline = time.monotonic() + 30
while not release.exists():
    if time.monotonic() >= deadline: raise SystemExit(99)
    time.sleep(.01)
results = []
for source in sys.argv[5:]:
    try:
        results.append(agent_logs.import_log(root, Path(source)))
    except ValueError as exc:
        results.append({'error': str(exc)})
print(json.dumps(results))
'''

LOCK_HOLDER = '''from pathlib import Path
import sys, time
from raee_lite.safe_io import exclusive_lock
lock, ready, release = map(Path, sys.argv[1:])
with exclusive_lock(lock):
    ready.touch()
    deadline = time.monotonic() + 30
    while not release.exists():
        if time.monotonic() >= deadline: raise SystemExit(99)
        time.sleep(.01)
'''


class ImportConcurrencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='raee-import-concurrency-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / 'project'
        self.root.mkdir()

    def source(self, name, code=0):
        path = self.base / (name + '.jsonl')
        path.write_text(json.dumps({'type': 'item.completed', 'item': {
            'type': 'command_execution', 'id': name,
            'command': 'pytest -q', 'exit_code': code}}) + '\n', encoding='utf-8')
        return path

    def start(self, program, *args):
        env = dict(os.environ, PYTHONPATH=str(Path(core.__file__).resolve().parents[1]),
                   PYTHONDONTWRITEBYTECODE='1')
        process = subprocess.Popen([sys.executable, '-B', '-c', program, *map(str, args)],
                                   env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        def cleanup():
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)

        self.addCleanup(cleanup)
        return process

    def wait_ready(self, process, marker):
        deadline = time.monotonic() + 20
        while not marker.exists():
            if process.poll() is not None:
                self.fail(f'Worker exited before barrier: {process.communicate()}')
            if time.monotonic() >= deadline:
                self.fail('Worker did not reach barrier')
            time.sleep(.01)

    def finish(self, process):
        out, err = process.communicate(timeout=20)
        self.assertEqual(process.returncode, 0, (out, err))
        return out

    def import_concurrently(self, groups, capacity=25_000):
        release = self.base / 'import-release'
        workers = []
        for index, sources in enumerate(groups):
            ready = self.base / f'import-ready-{index}'
            worker = self.start(IMPORT_WORKER, self.root, ready, release, capacity, *sources)
            workers.append((worker, ready))
        for worker, ready in workers:
            self.wait_ready(worker, ready)
        release.touch()
        return [result for worker, _ in workers for result in json.loads(self.finish(worker))]

    def saved(self):
        return core.read_json(self.root / agent_logs.IMPORTS)

    def test_distinct_process_imports_preserve_all_records_and_sources(self):
        seed = self.source('existing-failure', 7)
        agent_logs.import_log(self.root, seed)
        groups = [[self.source(f'worker-{worker}-{index}', index)
                   for index in range(3)] for worker in range(4)]
        results = self.import_concurrently(groups)
        self.assertEqual([result['new_observations'] for result in results], [1] * 12)
        saved = self.saved()
        self.assertEqual(len(saved['observations']), 13)
        self.assertEqual(len({row['id'] for row in saved['observations']}), 13)
        expected = {hashlib.sha256(source.read_bytes()).hexdigest()
                    for source in [seed, *(source for group in groups for source in group)]}
        self.assertEqual({row['source_digest'] for row in saved['observations']}, expected)
        self.assertEqual({row['sha256'] for row in saved['sources']}, expected)
        self.assertEqual(saved['observations'][0]['log_exit_code'], 7)
        self.assertEqual(sorted(result['total_observations'] for result in results),
                         list(range(2, 14)))

    def test_same_source_is_reported_as_new_only_once_across_processes(self):
        source = self.source('shared')
        results = self.import_concurrently([[source] for _ in range(4)])
        self.assertEqual(sorted(result['new_observations'] for result in results), [0, 0, 0, 1])
        self.assertEqual([result['total_observations'] for result in results], [1] * 4)
        self.assertEqual(len(self.saved()['observations']), 1)
        self.assertEqual(len(self.saved()['sources']), 1)

    def test_repeated_unchanged_import_does_not_grow_or_rewrite_store(self):
        source = self.source('repeated')
        agent_logs.import_log(self.root, source)
        path = self.root / agent_logs.IMPORTS
        original = path.read_bytes()
        with patch.object(core, 'write_json', side_effect=AssertionError('unnecessary rewrite')):
            result = agent_logs.import_log(self.root, source)
        self.assertEqual(result['new_observations'], 0)
        self.assertEqual(path.read_bytes(), original)

    def test_invalid_sources_are_rejected_without_overwriting_store(self):
        source = self.source('malformed-sources')
        agent_logs.import_log(self.root, source)
        saved = self.saved()
        saved['sources'] = None
        path = self.root / agent_logs.IMPORTS
        core.write_json(path, saved)
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'sources'):
            agent_logs.import_log(self.root, source)
        self.assertEqual(path.read_bytes(), original)

    def test_capacity_is_rechecked_against_other_process_commits(self):
        sources = [self.source(f'candidate-{index}') for index in range(4)]
        results = self.import_concurrently([[source] for source in sources], capacity=1)
        accepted = [result for result in results if 'error' not in result]
        rejected = [result for result in results if 'error' in result]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 3)
        self.assertTrue(all('record limit' in result['error'] for result in rejected))
        saved = self.saved()
        self.assertEqual(len(saved['observations']), 1)
        self.assertEqual(len(saved['sources']), 1)
        self.assertEqual(saved['observations'][0]['source_digest'], saved['sources'][0]['sha256'])

    def test_other_process_lock_times_out_without_mutating_store(self):
        agent_logs.import_log(self.root, self.source('existing'))
        before = (self.root / agent_logs.IMPORTS).read_bytes()
        lock = self.root / agent_logs.IMPORTS_LOCK
        ready, release = self.base / 'lock-ready', self.base / 'lock-release'
        holder = self.start(LOCK_HOLDER, lock, ready, release)
        self.wait_ready(holder, ready)
        identity = lock.stat()
        source = self.source('next')
        with self.assertRaises(TimeoutError):
            agent_logs.import_log(self.root, source, lock_timeout=.05)
        self.assertEqual((self.root / agent_logs.IMPORTS).read_bytes(), before)
        release.touch()
        self.finish(holder)
        self.assertEqual(agent_logs.import_log(self.root, source)['new_observations'], 1)
        self.assertEqual((lock.stat().st_dev, lock.stat().st_ino),
                         (identity.st_dev, identity.st_ino))

    def test_byte_limit_failure_preserves_store_and_releases_lock(self):
        agent_logs.import_log(self.root, self.source('existing'))
        before = (self.root / agent_logs.IMPORTS).read_bytes()
        source = self.source('next')
        with patch.object(safe_io, 'MAX_STORED_JSON', len(before) + 10):
            with self.assertRaisesRegex(ValueError, 'byte limit'):
                agent_logs.import_log(self.root, source)
        self.assertEqual((self.root / agent_logs.IMPORTS).read_bytes(), before)
        self.assertEqual(agent_logs.import_log(self.root, source)['new_observations'], 1)

    def test_duplicate_import_at_capacity_succeeds_and_failure_releases_lock(self):
        source = self.source('existing')
        agent_logs.import_log(self.root, source)
        with patch.object(agent_logs, 'MAX_OBSERVATIONS', 1):
            before = (self.root / agent_logs.IMPORTS).read_bytes()
            with self.assertRaisesRegex(ValueError, 'record limit'):
                agent_logs.import_log(self.root, self.source('too-many'))
            self.assertEqual((self.root / agent_logs.IMPORTS).read_bytes(), before)
            self.assertEqual(agent_logs.import_log(self.root, source)['new_observations'], 0)
        self.assertEqual(len(self.saved()['observations']), 1)


if __name__ == '__main__':
    unittest.main()
