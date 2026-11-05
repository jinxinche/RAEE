"""Bounded, nonexecuting PR inspection across directory exclusions and IO errors."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('pr_boundary_edges', ROOT / 'scripts/pr_boundary.py')
INSPECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECTOR)
EXCLUDED_NAMES = ('.git', '.raee', '__pycache__', '.venv', '.tox')


class PRBoundaryEdgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='raee-pr-boundary-edges-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(strict=True)

    def pair(self, name):
        base, head = self.root / name / 'base', self.root / name / 'head'
        base.mkdir(parents=True)
        head.mkdir()
        return base, head

    def invoke(self, base, head):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['pr_boundary.py', '--base', str(base), '--head', str(head)]), \
                contextlib.redirect_stdout(output):
            code = INSPECTOR.main()
        return code, output.getvalue()

    def test_protected_nested_excluded_directories_require_review(self):
        for prefix in ('scripts', '.github/workflows'):
            for name in EXCLUDED_NAMES:
                with self.subTest(prefix=prefix, name=name):
                    base, head = self.pair(prefix.replace('/', '-') + '-' + name)
                    relative = f'{prefix}/{name}/check.py'
                    for root, body in ((base, 'before\n'), (head, 'after\n')):
                        path = root / relative
                        path.parent.mkdir(parents=True)
                        path.write_text(body, encoding='utf-8')
                    self.assertEqual(INSPECTOR.evaluate(base, head), (False, [relative]))

    def test_excluded_directory_symlinks_are_recorded_without_following(self):
        outside = self.root / 'outside'
        outside.mkdir()
        # Following the target would exceed the per-file limit below.
        (outside / 'private.txt').write_bytes(b'never read this target')
        for prefix in ('', 'scripts/'):
            for name in EXCLUDED_NAMES:
                with self.subTest(prefix=prefix, name=name):
                    base, head = self.pair(prefix.replace('/', '-') + name)
                    relative = prefix + name
                    link = head / relative
                    link.parent.mkdir(parents=True, exist_ok=True)
                    link.symlink_to(outside, target_is_directory=True)
                    with patch.object(INSPECTOR, 'MAX_FILE_BYTES', 1):
                        self.assertEqual(INSPECTOR.evaluate(base, head), (False, [relative]))
                        inventory = INSPECTOR.snapshot(head)
                    self.assertEqual(set(inventory), {relative})
                    self.assertTrue(inventory[relative].startswith('symlink:'))

    def test_retargeted_excluded_directory_link_requires_review(self):
        base, head = self.pair('retarget')
        for root, name in ((base, 'old'), (head, 'new')):
            target = self.root / name
            target.mkdir()
            (root / '.venv').symlink_to(target, target_is_directory=True)
        self.assertEqual(INSPECTOR.evaluate(base, head), (False, ['.venv']))

    def test_unchanged_excluded_directory_link_is_not_a_change(self):
        base, head = self.pair('unchanged')
        target = self.root / 'outside'
        target.mkdir()
        for root in (base, head):
            (root / '.venv').symlink_to(target, target_is_directory=True)
        self.assertEqual(INSPECTOR.evaluate(base, head), (True, []))

    def test_only_root_git_metadata_directory_is_exempt(self):
        metadata = self.root / '.git'
        metadata.mkdir()
        (metadata / 'large-object').write_bytes(b'outside snapshot scope')
        with patch.object(INSPECTOR, 'MAX_FILE_BYTES', 1):
            self.assertEqual(INSPECTOR.snapshot(self.root), {})

    def test_traversal_permission_errors_fail_closed_for_base_and_head(self):
        real_scandir = os.scandir
        for side in ('base', 'head'):
            with self.subTest(side=side):
                base, head = self.pair(side)
                restricted = (base if side == 'base' else head) / 'scripts'
                restricted.mkdir()

                def deny(path):
                    if Path(path) == restricted:
                        raise PermissionError('private diagnostic must not be exposed')
                    return real_scandir(path)

                with patch.object(INSPECTOR.os, 'scandir', side_effect=deny):
                    code, output = self.invoke(base, head)
                self.assertEqual(code, 2)
                self.assertIn('REJECTED:', output)
                self.assertNotIn('STATIC BOUNDARY PASS', output)
                self.assertNotIn('private diagnostic', output)

    def test_directory_iteration_errors_fail_closed(self):
        base, head = self.pair('iteration-error')
        real_scandir = os.scandir

        def broken_iterator():
            raise OSError('enumeration interrupted')
            yield  # Keep the exception at iteration time, not context entry.

        @contextlib.contextmanager
        def scan(path):
            if Path(path) == head:
                yield broken_iterator()
            else:
                with real_scandir(path) as children:
                    yield children

        with patch.object(INSPECTOR.os, 'scandir', side_effect=scan):
            code, output = self.invoke(base, head)
        self.assertEqual(code, 2)
        self.assertNotIn('STATIC BOUNDARY PASS', output)

    @unittest.skipIf(os.name == 'nt', 'POSIX directory permission semantics')
    def test_real_unreadable_directory_fails_closed(self):
        base, head = self.pair('real-permissions')
        restricted = head / 'scripts' / 'restricted'
        restricted.mkdir(parents=True)
        (restricted / 'check.py').write_text('unreviewed\n', encoding='utf-8')
        restricted.chmod(0)
        try:
            code, output = self.invoke(base, head)
            if os.access(restricted, os.R_OK | os.X_OK):
                # Privileged local runners can still read it: they must inventory
                # the protected file, never claim that nothing changed.
                self.assertEqual(code, 1)
                self.assertIn('scripts/restricted/check.py', output)
            else:
                self.assertEqual(code, 2)
                self.assertIn('REJECTED:', output)
            self.assertNotIn('STATIC BOUNDARY PASS', output)
        finally:
            restricted.chmod(0o700)

    def test_empty_directories_count_toward_traversal_limit(self):
        for name in ('first', 'second', 'third'):
            (self.root / name).mkdir()
        with patch.object(INSPECTOR, 'MAX_ENTRIES', 2):
            with self.assertRaisesRegex(ValueError, 'entry-count limit'):
                INSPECTOR.snapshot(self.root)

    def test_wide_directory_enumeration_stops_at_entry_limit(self):
        yielded = []

        def entries():
            for index in range(100):
                yielded.append(index)
                yield SimpleNamespace(
                    path=str(self.root / str(index)), name=str(index),
                    stat=lambda **kwargs: SimpleNamespace(st_mode=stat.S_IFDIR),
                )

        @contextlib.contextmanager
        def scan(path):
            self.assertEqual(Path(path), self.root)
            yield entries()

        with patch.object(INSPECTOR, 'MAX_ENTRIES', 2), \
                patch.object(INSPECTOR.os, 'scandir', side_effect=scan):
            with self.assertRaisesRegex(ValueError, 'entry-count limit'):
                INSPECTOR.snapshot(self.root)
        self.assertEqual(yielded, [0, 1, 2])

    def test_excluded_subtrees_obey_file_count_limit(self):
        directory = self.root / 'scripts' / '.venv'
        directory.mkdir(parents=True)
        for index in range(3):
            (directory / str(index)).write_bytes(b'x')
        with patch.object(INSPECTOR, 'MAX_FILES', 2):
            with self.assertRaisesRegex(ValueError, 'size limit'):
                INSPECTOR.snapshot(self.root)

    def test_excluded_subtrees_obey_per_file_byte_limit(self):
        directory = self.root / 'scripts' / '__pycache__'
        directory.mkdir(parents=True)
        (directory / 'large').write_bytes(b'12345')
        with patch.object(INSPECTOR, 'MAX_FILE_BYTES', 4):
            with self.assertRaisesRegex(ValueError, 'size limit'):
                INSPECTOR.snapshot(self.root)

    def test_excluded_subtrees_obey_total_byte_limit(self):
        directory = self.root / 'scripts' / '.tox'
        directory.mkdir(parents=True)
        for name in ('first', 'second'):
            (directory / name).write_bytes(b'123')
        with patch.object(INSPECTOR, 'MAX_TOTAL_BYTES', 5):
            with self.assertRaisesRegex(ValueError, 'size limit'):
                INSPECTOR.snapshot(self.root)

    def test_excluded_symlinks_obey_file_count_limit(self):
        outside = self.root / 'outside'
        outside.mkdir()
        head = self.root / 'head'
        head.mkdir()
        for name in ('.venv', '.tox'):
            (head / name).symlink_to(outside, target_is_directory=True)
        with patch.object(INSPECTOR, 'MAX_FILES', 1):
            with self.assertRaisesRegex(ValueError, 'file-count limit'):
                INSPECTOR.snapshot(head)

    def test_protected_python_content_remains_passive_data(self):
        base, head = self.pair('nonexecution')
        marker = self.root / 'executed.txt'
        script = head / 'scripts' / '.venv' / 'check.py'
        script.parent.mkdir(parents=True)
        script.write_text(
            f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\n',
            encoding='utf-8',
        )
        process = subprocess.run(
            [sys.executable, '-B', str(ROOT / 'scripts/pr_boundary.py'),
             '--base', str(base), '--head', str(head)],
            cwd=self.root, text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
        self.assertIn('scripts/.venv/check.py', process.stdout)
        self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main()
