"""Snapshot permission and input-budget regressions; no Docker daemon required."""
from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from raee_lite import isolated


class SnapshotEdgesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base / 'project'
        self.root.mkdir()

    def test_snapshot_directories_remain_readable_under_restrictive_umask(self):
        nested = self.root / 'package' / 'empty'
        nested.mkdir(parents=True)
        source = self.root / 'package' / 'data.txt'
        source.write_bytes(b'data')
        script = self.root / 'run.sh'
        script.write_bytes(b'#!/bin/sh\nexit 0\n')
        source.chmod(0o600)
        script.chmod(0o700)
        original_modes = {p: stat.S_IMODE(p.stat().st_mode)
                          for p in (self.base, self.root, nested, source, script)}

        for mask in (0o077, 0o027, 0o000):
            with self.subTest(umask=oct(mask)):
                target = self.base / f'snapshot-{mask}'
                old_mask = os.umask(mask)
                try:
                    info = isolated.stage_snapshot(self.root, target)
                finally:
                    os.umask(old_mask)
                self.assertEqual(info['files'], 2)
                self.assertEqual((target / 'package' / 'data.txt').read_bytes(), b'data')
                self.assertEqual((target / 'run.sh').read_bytes(), script.read_bytes())
                self.assertTrue((target / 'package' / 'empty').is_dir())
                # Windows chmod does not implement POSIX directory access bits.
                if os.name == 'posix':
                    for directory in (target, target / 'package', target / 'package' / 'empty'):
                        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o755)
                    self.assertEqual(stat.S_IMODE((target / 'package' / 'data.txt').stat().st_mode), 0o644)
                    self.assertEqual(stat.S_IMODE((target / 'run.sh').stat().st_mode), 0o755)
                for path, mode in original_modes.items():
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)

    def test_exact_file_and_byte_budgets_are_accepted(self):
        (self.root / 'a').write_bytes(b'1234')
        (self.root / 'b').write_bytes(b'5678')
        with patch.multiple(isolated, MAX_FILES=2, MAX_FILE_SIZE=4, MAX_TOTAL_BYTES=8):
            info = isolated.stage_snapshot(self.root, self.base / 'snapshot')
        self.assertEqual((info['files'], info['bytes']), (2, 8))

    def test_aggregate_byte_overflow_is_rejected(self):
        (self.root / 'a').write_bytes(b'1234')
        (self.root / 'b').write_bytes(b'5678')
        with patch.multiple(isolated, MAX_FILE_SIZE=4, MAX_TOTAL_BYTES=7):
            with self.assertRaisesRegex(ValueError, 'budget'):
                isolated.stage_snapshot(self.root, self.base / 'snapshot')

    def test_file_growth_cannot_overrun_remaining_copy_budget(self):
        (self.root / 'a').write_bytes(b'1234')
        source = self.root / 'b'
        source.write_bytes(b'5678')
        original_open = os.open

        def grow(path, flags, *args, **kwargs):
            if Path(path) == source:
                source.write_bytes(b'56789')
            return original_open(path, flags, *args, **kwargs)

        target = self.base / 'snapshot'
        with patch.multiple(isolated, MAX_FILE_SIZE=8, MAX_TOTAL_BYTES=8), \
             patch.object(isolated.os, 'open', side_effect=grow):
            with self.assertRaisesRegex(ValueError, 'byte budget'):
                isolated.stage_snapshot(self.root, target)
        self.assertLessEqual(sum(p.stat().st_size for p in target.iterdir()), 8)

    def test_sensitive_inputs_are_excluded_before_copy_byte_limits(self):
        (self.root / '.env.production').write_bytes(b'secret' * 100)
        (self.root / '.ssh').mkdir()
        (self.root / '.ssh' / 'private').write_bytes(b'secret' * 100)
        (self.root / 'a').write_bytes(b'1234')
        target = self.base / 'snapshot'
        with patch.multiple(isolated, MAX_FILES=1, MAX_FILE_SIZE=4, MAX_TOTAL_BYTES=4):
            info = isolated.stage_snapshot(self.root, target)
        self.assertEqual((info['files'], info['bytes']), (1, 4))
        self.assertEqual(info['excluded_total'], 2)
        self.assertEqual(info['unsafe_excluded_total'], 1)
        self.assertEqual([p.name for p in target.iterdir()], ['a'])

    def test_special_file_types_are_excluded_without_opening(self):
        source = self.root / 'special'
        source.touch()
        original_lstat = Path.lstat
        for kind in (stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK):
            with self.subTest(kind=kind):
                def special_lstat(path):
                    return SimpleNamespace(st_mode=kind) if path == source else original_lstat(path)

                target = self.base / f'snapshot-{kind}'
                with patch.object(Path, 'lstat', special_lstat), \
                     patch.object(isolated.os, 'open') as open_file:
                    info = isolated.stage_snapshot(self.root, target)
                open_file.assert_not_called()
                self.assertEqual(info['files'], 0)
                self.assertEqual(info['unsafe_excluded_total'], 1)
                self.assertFalse((target / 'special').exists())


if __name__ == '__main__':
    unittest.main()
