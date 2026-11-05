"""Real local filesystem and Git-hook negative controls; no project code run by inspection."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from raee_lite import core, safe_io
from raee_lite.attestation import keygen
from raee_lite.discovery import risk_signals
from raee_lite.dependency_scope import snapshot
from raee_lite.safe_process import capture_bounded


class ReadonlyIOTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)

    def repository(self):
        self.git('init', '-q')
        (self.root / 'tests').mkdir()
        (self.root / 'tests/test_app.py').write_text('assert True\n')
        (self.root / '.gitattributes').write_text('tests/*.py diff=probe\n')
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')
        hook = self.root / '.git/probe.py'
        marker = self.root / '.git/probe-fired'
        hook.write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("executed")\nprint("probe")\n')
        return f'"{sys.executable}" "{hook}"', marker

    def test_git_inventory_does_not_execute_fsmonitor_hook(self):
        command, marker = self.repository()
        self.git('config', 'core.fsmonitor', command)
        core.paths(self.root)
        core.git_context(self.root)
        self.assertFalse(marker.exists())

    def test_diff_review_does_not_execute_textconv_driver(self):
        command, marker = self.repository()
        self.git('config', 'diff.probe.textconv', command)
        (self.root / 'tests/test_app.py').write_text('assert False\n')
        risk_signals(self.root)
        self.assertFalse(marker.exists())

    def test_duplicate_and_nonfinite_json_are_rejected(self):
        path = self.root / 'data.json'
        for raw in ('{"exit":1,"exit":0}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}'):
            with self.subTest(raw=raw):
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    safe_io.safe_read_json(path)

    def test_linked_parent_is_not_followed(self):
        (self.root / 'actual').mkdir()
        (self.root / 'actual/data.json').write_text('{}')
        (self.root / 'alias').symlink_to(self.root / 'actual', target_is_directory=True)
        with self.assertRaises(ValueError):
            safe_io.safe_read_json(self.root / 'alias/data.json')

    def test_read_growth_is_bounded(self):
        path = self.root / 'grow.json'
        path.write_bytes(b'{}')
        original = os.open
        def grow(name, flags, *args, **kwargs):
            path.write_bytes(b'x' * 100)
            return original(name, flags, *args, **kwargs)
        with patch('raee_lite.safe_io.os.open', side_effect=grow), self.assertRaises(ValueError):
            safe_io.read_bytes(path, 8)

    def test_scoped_source_replacement_before_open_is_rejected(self):
        path = self.root / 'app.py'
        replacement = self.root / 'other.py'
        path.write_text('first')
        replacement.write_text('second')
        original = os.open
        def replace(name, flags, *args, **kwargs):
            os.replace(replacement, path)
            return original(name, flags, *args, **kwargs)
        with patch('raee_lite.safe_io.os.open', side_effect=replace), self.assertRaises(ValueError):
            snapshot(self.root, ['app.py'])

    def test_invalid_encoding_and_deep_json_are_bounded_errors(self):
        path = self.root / 'data.json'
        for value in (b'\xff', b'[' * 3000 + b']' * 3000,
                      b'{"x":"\xed\xa0\x80"}', b'{"x":"\\ud800"}', b'{"\\ud800":0}'):
            path.write_bytes(value)
            with self.assertRaises(ValueError):
                safe_io.safe_read_json(path)

    def test_json_byte_budget_roundtrips_at_exact_limit(self):
        path = self.root / 'exact.json'
        document = {'text': 'multiline\nvalue'}
        expected = (json.dumps(document, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
        with patch('raee_lite.safe_io.MAX_STORED_JSON', len(expected)):
            safe_io.write_json(path, document)
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(safe_io.safe_read_json(path), document)

    def test_oversized_write_preserves_previous_document(self):
        path = self.root / 'data.json'
        path.write_text('{}')
        with patch('raee_lite.safe_io.MAX_STORED_JSON', 16), self.assertRaises(ValueError):
            safe_io.write_json(path, {'too_big': 'x' * 20})
        self.assertEqual(path.read_text(), '{}')

    def test_source_links_are_partial_instead_of_silently_omitted(self):
        (self.root / 'actual.py').write_text('pass\n')
        (self.root / 'link.py').symlink_to(self.root / 'actual.py')
        report = core.fingerprint(self.root)
        self.assertIn('link.py', [x['file'] for x in report['skipped']])

    def test_tracked_path_through_link_never_reads_target(self):
        self.repository()
        folder = self.root / 'tests'
        folder.rename(self.root / 'saved-tests')
        folder.symlink_to(self.root / 'saved-tests', target_is_directory=True)
        report = core.fingerprint(self.root)
        self.assertIn('tests/test_app.py', [x['file'] for x in report['skipped']])

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO test')
    def test_fifo_inputs_return_without_blocking(self):
        fifo = self.root / 'blocked.jsonl'
        os.mkfifo(fifo)
        program = ('from pathlib import Path\nfrom raee_lite import safe_io, core\n'
                   'from raee_lite.agent_logs import import_log\np=Path(__import__("sys").argv[1])\n'
                   'for action in (lambda: safe_io.safe_read_json(p),lambda: import_log(p.parent,p)):\n'
                   ' try: action()\n except ValueError: pass\n else: raise AssertionError("FIFO accepted")\n'
                   'assert core.fingerprint(p.parent)["skipped"]\n')
        result = subprocess.run([sys.executable, '-c', program, str(fifo)], timeout=5, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_keygen_failure_does_not_delete_concurrent_public_file(self):
        project = self.root / 'project'
        project.mkdir()
        private, public = self.root / 'secret.pem', self.root / 'public.pem'
        original = os.open
        def insert(name, flags, *args, **kwargs):
            if Path(name) == public:
                public.write_text('belongs to another writer')
            return original(name, flags, *args, **kwargs)
        with patch('raee_lite.attestation.os.open', side_effect=insert), self.assertRaises(FileExistsError):
            keygen(private, public, project)
        self.assertEqual(public.read_text(), 'belongs to another writer')
        # Failed key-pair creation retains a partial private file rather than
        # racing another writer with a path-based cleanup unlink.
        self.assertTrue(private.exists())

    def test_command_output_is_limited_before_retaining_it(self):
        _, raw, truncated = capture_bounded([sys.executable, '-c', 'print("x" * 1000000)'], self.root, limit=1024)
        self.assertEqual(len(raw), 1024)
        self.assertTrue(truncated)
        code, raw, truncated = capture_bounded([sys.executable, '-c', 'print("small")'], self.root, limit=1024)
        self.assertEqual((code, raw.strip(), truncated), (0, b'small', False))

    def test_command_output_wait_has_a_timeout(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            capture_bounded([sys.executable, '-c', 'import time; time.sleep(10)'], self.root, limit=1024, timeout=0.2)
