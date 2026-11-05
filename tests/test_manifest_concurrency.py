"""Cooperating processes must not overwrite requirements or weaken contracts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from raee_lite import core


WORKER = '''import json, sys, time
from pathlib import Path
from raee_lite import core
from raee_lite.contracts import set_expectation
root, ready, release = map(Path, sys.argv[1:4])
operation, label = sys.argv[4:]
original = core.get_manifest
def slow_read(*args, **kwargs):
    value = original(*args, **kwargs)
    time.sleep(.04)
    return value
core.get_manifest = slow_read
ready.touch()
deadline = time.monotonic() + 20
while not release.exists():
    if time.monotonic() > deadline: raise SystemExit(99)
    time.sleep(.01)
try:
    if operation == 'init': core.init(root)
    elif operation == 'add': core.add_requirement(root, label)
    elif operation == 'boundary': core.add_boundary(root, label)
    elif operation == 'expect': set_expectation(root, 'R1', label)
    else: raise RuntimeError(operation)
except ValueError as exc:
    print(str(exc))
    raise SystemExit(2)
'''


class ManifestConcurrencyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='raee-manifest-')
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base / 'project'
        self.root.mkdir()

    def run_writers(self, operations):
        release = self.base / 'release'
        release.unlink(missing_ok=True)
        workers = []
        env = dict(os.environ, PYTHONPATH=str(Path(core.__file__).resolve().parents[1]),
                   PYTHONDONTWRITEBYTECODE='1')
        for i, (operation, label) in enumerate(operations):
            ready = self.base / f'ready-{i}'
            ready.unlink(missing_ok=True)
            process = subprocess.Popen(
                [sys.executable, '-B', '-c', WORKER, str(self.root), str(ready),
                 str(release), operation, label], env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            workers.append((process, ready))
        try:
            deadline = time.monotonic() + 20
            for process, ready in workers:
                while not ready.exists():
                    if process.poll() is not None:
                        self.fail(str(process.communicate()))
                    if time.monotonic() > deadline:
                        self.fail('Writer did not reach start barrier')
                    time.sleep(.01)
            release.touch()
            results = []
            for process, _ in workers:
                out, err = process.communicate(timeout=20)
                self.assertIn(process.returncode, (0, 2), (out, err))
                results.append((process.returncode, out))
            return results
        finally:
            for process, _ in workers:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=10)

    def test_concurrent_requirements_have_distinct_ids_and_preserve_all_text(self):
        core.init(self.root)
        labels = [f'Requirement {i}' for i in range(4)]
        self.assertEqual([code for code, _ in self.run_writers([('add', x) for x in labels])], [0] * 4)
        reqs = core.get_manifest(self.root)['requirements']
        self.assertEqual({r['id'] for r in reqs}, {'R1', 'R2', 'R3', 'R4'})
        self.assertEqual({r['description'] for r in reqs}, set(labels))

    def test_requirements_boundaries_and_expectations_share_one_lock(self):
        core.init(self.root)
        core.add_requirement(self.root, 'Original requirement')
        results = self.run_writers([('add', 'New requirement'), ('boundary', 'Network not verified'),
                                    ('expect', 'unit'), ('expect', 'integration')])
        self.assertEqual([code for code, _ in results], [0] * 4)
        manifest = core.get_manifest(self.root)
        self.assertEqual(len(manifest['requirements']), 2)
        self.assertEqual(manifest['requirements'][0]['expected_checks'], ['integration', 'unit'])
        self.assertIn('Network not verified', manifest['boundaries'])

    def test_capacity_is_rechecked_after_acquiring_manifest_lock(self):
        core.init(self.root)
        manifest = core.get_manifest(self.root)
        manifest['requirements'] = [{'id': f'R{i+1}', 'description': f'Existing {i}'} for i in range(499)]
        core.write_json(self.root / core.MANIFEST, manifest)
        results = self.run_writers([('add', 'Candidate A'), ('add', 'Candidate B')])
        self.assertEqual(sorted(code for code, _ in results), [0, 2])
        self.assertEqual(len(core.get_manifest(self.root)['requirements']), 500)

    def test_only_one_concurrent_initializer_succeeds(self):
        results = self.run_writers([('init', ''), ('init', '')])
        self.assertEqual(sorted(code for code, _ in results), [0, 2])
        self.assertEqual(core.get_manifest(self.root)['requirements'], [])
        self.assertEqual(core.read_json(self.root / core.LEDGER)['runs'], [])

    def test_reinitialization_retains_existing_receipts_and_manifest(self):
        core.init(self.root)
        core.add_requirement(self.root, 'Keep this requirement')
        core.append_receipt(self.root, {'observed_exit_code': 1})
        before = [(self.root / path).read_bytes() for path in (core.MANIFEST, core.LEDGER)]
        results = self.run_writers([('init', ''), ('init', '')])
        self.assertEqual([code for code, _ in results], [2, 2])
        self.assertEqual([(self.root / path).read_bytes() for path in (core.MANIFEST, core.LEDGER)], before)
