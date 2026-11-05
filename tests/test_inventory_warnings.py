"""Git can emit an incomplete inventory with exit zero and a stderr warning."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from raee_lite import core


class InventoryWarningTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='raee-inventory-warning-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def test_warning_falls_back_to_bounded_scan_and_retains_failure(self):
        (self.root / '.git').mkdir()
        with patch.object(core.shutil, 'which', return_value='git'), \
                patch.object(core, 'capture_bounded', side_effect=ValueError('stderr observed')) as git, \
                patch.object(core, 'bounded_walk', side_effect=ValueError('unreadable directory')):
            with self.assertRaisesRegex(ValueError, 'unreadable directory'):
                core.fingerprint(self.root)
        self.assertTrue(git.call_args.kwargs['reject_stderr'])

    @unittest.skipIf(os.name == 'nt', 'POSIX directory permission semantics')
    def test_real_unreadable_directory_cannot_be_reported_as_complete(self):
        self.assertIsNotNone(shutil.which('git'), 'Git is required by the reviewed test environment')
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True)
        hidden = self.root / 'hidden'
        hidden.mkdir()
        (hidden / 'failure.py').write_text('assert False\n', encoding='utf-8')
        hidden.chmod(0)
        try:
            if os.access(hidden, os.R_OK | os.X_OK):
                # A privileged local runner can still enumerate it. Assert the
                # input is included instead of pretending permission denial ran.
                self.assertEqual(core.fingerprint(self.root)['files'], 1)
            else:
                with self.assertRaises(ValueError):
                    core.fingerprint(self.root)
        finally:
            hidden.chmod(0o700)

    def test_warning_does_not_hide_accessible_files_in_fallback(self):
        (self.root / '.git').mkdir()
        (self.root / 'source.py').write_text('value = 1\n', encoding='utf-8')
        with patch.object(core.shutil, 'which', return_value='git'), \
                patch.object(core, 'capture_bounded', side_effect=ValueError('stderr observed')):
            result = core.fingerprint(self.root)
        self.assertEqual(result['files'], 1)
        self.assertEqual(result['skipped'], [])

    def test_undecodable_filenames_cannot_share_a_source_binding(self):
        # Model paths supplied by a filesystem allowing arbitrary bytes. macOS
        # filesystems may refuse their creation; this checks the hashing boundary.
        hashes = []
        for filename in ('\udcff.py', '\udcfe.py', '?.py'):
            with patch.object(core, 'paths', return_value=[self.root / filename]), \
                    patch.object(Path, 'lstat', return_value=SimpleNamespace(st_size=4)), \
                    patch.object(core, 'read_bytes', return_value=b'same'):
                hashes.append(core.fingerprint(self.root)['sha256'])
        self.assertEqual(len(set(hashes)), 3)
