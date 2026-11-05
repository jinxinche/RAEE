"""Association mutations use real competing processes, with controlled snapshots."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite import associations, core, enhanced, safe_io
from raee_lite.agent_logs import IMPORTS


WRITER = '''from pathlib import Path
import sys, time
from raee_lite import associations, safe_io
root, signals = map(Path, sys.argv[1:3])
label, requirement, evidence, reason = sys.argv[3:]
original_read = associations._read_links
original_lock = safe_io._try_lock
def read(root):
    value = original_read(root)
    (signals / (label + '-read')).touch()
    if label == 'first':
        deadline = time.monotonic() + 20
        while not (signals / 'release').exists():
            if time.monotonic() >= deadline: raise RuntimeError('Release not received')
            time.sleep(.01)
    return value
def try_lock(fd):
    try:
        original_lock(fd)
    except OSError:
        (signals / (label + '-blocked')).touch()
        raise
associations._read_links = read
safe_io._try_lock = try_lock
associations.link_evidence(root, requirement, evidence, reason)
'''


class AssociationConcurrencyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='raee-associations-')
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base / 'project'
        self.root.mkdir()
        (self.root / 'app.py').write_text('pass\n', encoding='utf-8')
        core.init(self.root)
        self.r1 = core.add_requirement(self.root, 'First behavior')
        self.r2 = core.add_requirement(self.root, 'Second behavior')
        self.e1 = core.run_check(self.root, self.r1,
                                 [sys.executable, '-B', '-c', 'pass'], 10)['id']
        self.e2 = core.run_check(self.root, self.r2,
                                 [sys.executable, '-B', '-c', 'raise SystemExit(1)'], 10)['id']
        core.write_json(self.root / IMPORTS, {'schema': 1, 'observations': [{
            'id': 'A1', 'provider': 'codex', 'command_family': 'pytest',
            'log_status': 'RECORDED_ZERO', 'provenance': 'UNVERIFIED_AGENT_TRANSCRIPT',
        }]})

    def start(self, label, mutation):
        env = dict(os.environ, PYTHONPATH=str(Path(core.__file__).resolve().parents[1]),
                   PYTHONDONTWRITEBYTECODE='1')
        for key in ('CI', 'GITHUB_ACTIONS', 'GITHUB_STEP_SUMMARY'):
            env.pop(key, None)
        process = subprocess.Popen(
            [sys.executable, '-B', '-c', WRITER, str(self.root), str(self.base), label, *mutation],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)

        def cleanup():
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)

        self.addCleanup(cleanup)
        return process

    def wait_signal(self, process, *names):
        deadline = time.monotonic() + 15
        while True:
            for name in names:
                if (self.base / name).exists():
                    return name
            if process.poll() is not None:
                self.fail(f'Writer exited before signaling: {process.communicate()}')
            if time.monotonic() >= deadline:
                self.fail(f'Writer did not signal {names}')
            time.sleep(.01)

    def finish(self, process):
        output = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 0, output)

    def race(self, first, second):
        source = core.fingerprint(self.root)
        immutable = {path: (self.root / path).read_bytes()
                     for path in (core.MANIFEST, core.LEDGER, IMPORTS)}
        first_process = self.start('first', first)
        self.wait_signal(first_process, 'first-read')
        second_process = self.start('second', second)
        signal = self.wait_signal(second_process, 'second-blocked', 'second-read')
        # Old code permits the second writer to commit a snapshot while the
        # first is paused. Correct code blocks the second before its read.
        # Both cases are coordinated by events, not a guessed scheduling delay.
        if signal == 'second-read':
            self.finish(second_process)
        (self.base / 'release').touch()
        self.finish(first_process)
        self.finish(second_process)
        self.assertEqual(core.fingerprint(self.root), source)
        for path, content in immutable.items():
            self.assertEqual((self.root / path).read_bytes(), content)
        return core.read_json(self.root / associations.LINKS)['links']

    def test_concurrent_inserts_preserve_both_pairs(self):
        rows = self.race((self.r1, self.e1, 'First relevant receipt'),
                         (self.r2, self.e2, 'Second relevant receipt'))
        self.assertEqual({(r['requirement'], r['evidence_id']) for r in rows},
                         {(self.r1, self.e1), (self.r2, self.e2)})
        self.assertEqual(len(rows), 2)

    def test_concurrent_rationale_updates_preserve_both_changes(self):
        for requirement, evidence in ((self.r1, self.e1), (self.r2, self.e2)):
            associations.link_evidence(self.root, requirement, evidence, 'Original rationale')
        untouched = associations.link_evidence(self.root, self.r1, 'A1', 'Historical log context')
        rows = self.race((self.r1, self.e1, 'First revised rationale'),
                         (self.r2, self.e2, 'Second revised rationale'))
        by_pair = {(r['requirement'], r['evidence_id']): r for r in rows}
        self.assertEqual(by_pair[(self.r1, self.e1)]['rationale'], 'First revised rationale')
        self.assertEqual(by_pair[(self.r2, self.e2)]['rationale'], 'Second revised rationale')
        self.assertEqual(by_pair[(self.r1, 'A1')], untouched)
        self.assertEqual(len(rows), 3)

    def test_same_pair_keeps_one_record_with_last_serialized_rationale(self):
        rows = self.race((self.r1, self.e1, 'First relevant rationale'),
                         (self.r1, self.e1, 'Second relevant rationale'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['rationale'], 'Second relevant rationale')
        self.assertTrue(rows[0]['self_declared'])

    def test_concurrent_manual_and_imported_links_do_not_rebind_receipts(self):
        associations.link_evidence(self.root, self.r2, self.e2, 'Existing failed check')
        rows = self.race((self.r2, self.e1, 'Cross requirement attribution'),
                         (self.r2, 'A1', 'Historical transcript attribution'))
        self.assertEqual(len(rows), 3)
        report = enhanced.audit(self.root)
        states = {r['evidence_id']: r['state'] for r in report['agent_evidence']['explicit']}
        self.assertEqual(states, {self.e1: 'OBSERVED_PASS_SELF_LINKED',
                                  self.e2: 'OBSERVED_FAILED_SELF_LINKED',
                                  'A1': 'LOG_ONLY_NOT_VALIDATED'})
        self.assertEqual(report['requirements'][1]['state'], 'FAILED_CHECK')
        self.assertTrue(all(r['basis'] == 'USER_ASSERTED_ASSOCIATION_NOT_COVERAGE_PROOF'
                            for r in report['agent_evidence']['explicit']))

    def test_failed_write_preserves_table_and_releases_permanent_lock(self):
        associations.link_evidence(self.root, self.r1, self.e1, 'Original relevant receipt')
        before = (self.root / associations.LINKS).read_bytes()
        lock = self.root / associations.LINKS_LOCK
        identity = (lock.stat().st_dev, lock.stat().st_ino)
        with patch.object(core, 'write_json', side_effect=OSError('write failed')):
            with self.assertRaisesRegex(OSError, 'write failed'):
                associations.link_evidence(self.root, self.r2, self.e2, 'Another relevant receipt')
        self.assertEqual((self.root / associations.LINKS).read_bytes(), before)
        self.finish(self.start('recovery', (self.r2, self.e2, 'Retry relevant receipt')))
        self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)
        self.assertEqual(len(core.read_json(self.root / associations.LINKS)['links']), 2)

    def test_malformed_table_is_preserved_and_lock_is_released(self):
        path = self.root / associations.LINKS
        core.write_json(path, {'schema': 1, 'links': ['malformed']})
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Invalid links.json'):
            associations.link_evidence(self.root, self.r1, self.e1, 'Relevant receipt rationale')
        self.assertEqual(path.read_bytes(), before)
        lock = self.root / associations.LINKS_LOCK
        self.assertTrue(lock.is_file())
        with safe_io.exclusive_lock(lock, timeout=0):
            pass

    def assert_invalid_links_preserved(self, rows, message):
        path = self.root / associations.LINKS
        core.write_json(path, {'schema': 1, 'links': rows})
        before = path.read_bytes()
        operations = {
            'report': lambda: enhanced.audit(self.root),
            'mutation': lambda: associations.link_evidence(
                self.root, self.r1, self.e1, 'Replacement relevant receipt'),
        }
        for name, operation in operations.items():
            with self.subTest(operation=name):
                with self.assertRaisesRegex(ValueError, message):
                    operation()
                self.assertEqual(path.read_bytes(), before)

    def test_duplicate_stored_pairs_are_rejected_before_report_or_update(self):
        row = associations.link_evidence(self.root, self.r1, self.e1, 'Original attribution')
        self.assert_invalid_links_preserved(
            [row, {**row, 'rationale': 'Conflicting attribution'}], 'duplicate.*pair')

    def test_dangling_evidence_is_not_silently_omitted_or_preserved_by_update(self):
        row = associations.link_evidence(self.root, self.r1, self.e1, 'Original attribution')
        self.assert_invalid_links_preserved(
            [row, {**row, 'evidence_id': 'E-missing'}], 'dangling evidence')

    def test_dangling_requirement_is_not_silently_omitted_or_preserved_by_update(self):
        row = associations.link_evidence(self.root, self.r1, self.e1, 'Original attribution')
        self.assert_invalid_links_preserved(
            [row, {**row, 'requirement': 'R-missing'}], 'dangling requirement')

    def test_valid_target_with_missing_original_intent_remains_unbound(self):
        associations.link_evidence(self.root, self.r2, self.e1, 'Cross requirement attribution')
        manifest = core.get_manifest(self.root)
        manifest['requirements'] = [r for r in manifest['requirements'] if r['id'] != self.r1]
        core.write_json(self.root / core.MANIFEST, manifest)
        report = enhanced.audit(self.root)
        self.assertEqual(report['agent_evidence']['explicit'][0]['state'], 'INTENT_UNBOUND')
        self.assertEqual(report['requirements'][0]['state'], 'FAILED_CHECK')


if __name__ == '__main__':
    unittest.main()
