"""Security regression tests for the base-owned PR inventory inspector."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('trusted_pr_inspector', ROOT / 'scripts/pr_boundary.py')
INSPECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECTOR)


class TrustedInspectorBootstrap(unittest.TestCase):
    def test_retargeted_existing_file_link_is_flagged(self):
        with tempfile.TemporaryDirectory() as temp:
            base, head = Path(temp) / 'base', Path(temp) / 'head'
            base.mkdir(); head.mkdir()
            (base / 'asset').symlink_to('/tmp/ordinary')
            (head / 'asset').symlink_to('/etc/passwd')
            self.assertEqual(INSPECTOR.evaluate(base, head), (False, ['asset']))

    def test_retargeted_existing_directory_link_is_flagged(self):
        with tempfile.TemporaryDirectory() as temp:
            base, head = Path(temp) / 'base', Path(temp) / 'head'
            base.mkdir(); head.mkdir()
            (base / 'external').symlink_to('/tmp/old', target_is_directory=True)
            (head / 'external').symlink_to('/tmp/new', target_is_directory=True)
            self.assertEqual(INSPECTOR.evaluate(base, head), (False, ['external']))

    def test_unchanged_symlink_is_not_new_change(self):
        with tempfile.TemporaryDirectory() as temp:
            base, head = Path(temp) / 'base', Path(temp) / 'head'
            base.mkdir(); head.mkdir()
            (base / 'reference').symlink_to('/etc/passwd')
            (head / 'reference').symlink_to('/etc/passwd')
            self.assertEqual(INSPECTOR.evaluate(base, head), (True, []))

    def test_directory_symlinks_count_toward_file_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for i in range(3):
                (root / f'link-{i}').symlink_to('/tmp', target_is_directory=True)
            with patch.object(INSPECTOR, 'MAX_FILES', 2):
                with self.assertRaises(ValueError):
                    INSPECTOR.snapshot(root)


if __name__ == '__main__':
    unittest.main()
