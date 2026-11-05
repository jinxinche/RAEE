"""Real offline installations must expose broken wheel entry points."""
import base64
import csv
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / 'scripts' / 'smoke_installed_package.py'


class PackagingEdgesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='raee-packaging-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.wheel_dir = self.root / 'wheels'
        self.wheel_dir.mkdir()

    def make_wheel(self, *, entry_point='raee_lite.cli:main', overrides=None):
        # Use the real package in a minimal wheel so negative controls need no
        # network or build-backend dependency. Release builds are tested separately.
        source = ROOT / 'src'
        contents = {
            path.relative_to(source).as_posix(): path.read_bytes()
            for path in (source / 'raee_lite').rglob('*')
            if path.is_file() and path.suffix in {'.py', '.md'}
        }
        for name, value in (overrides or {}).items():
            if value is None:
                contents.pop(name)
            else:
                contents[name] = value
        dist = 'raee_lite-0.0.0.dist-info'
        contents[f'{dist}/METADATA'] = (
            b'Metadata-Version: 2.1\nName: raee-lite\nVersion: 0.0.0\n')
        contents[f'{dist}/WHEEL'] = (
            b'Wheel-Version: 1.0\nGenerator: packaging-edge-fixture\n'
            b'Root-Is-Purelib: true\nTag: py3-none-any\n')
        if entry_point is not None:
            contents[f'{dist}/entry_points.txt'] = (
                f'[console_scripts]\nraee-lite = {entry_point}\n'.encode('utf-8'))
        record = io.StringIO(newline='')
        writer = csv.writer(record)
        for name, value in sorted(contents.items()):
            digest = base64.urlsafe_b64encode(hashlib.sha256(value).digest()).rstrip(b'=')
            writer.writerow((name, 'sha256=' + digest.decode('ascii'), len(value)))
        writer.writerow((f'{dist}/RECORD', '', ''))
        contents[f'{dist}/RECORD'] = record.getvalue().encode('utf-8')
        wheel = self.wheel_dir / 'raee_lite-0.0.0-py3-none-any.whl'
        with zipfile.ZipFile(wheel, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, value in contents.items():
                archive.writestr(name, value)
        return wheel

    def run_smoke(self, extra_env=None):
        env = dict(os.environ, TMPDIR=str(self.root), TMP=str(self.root),
                   TEMP=str(self.root), PYTHONIOENCODING='utf-8',
                   PIP_DISABLE_PIP_VERSION_CHECK='1')
        env.update(extra_env or {})
        result = subprocess.run(
            [sys.executable, '-I', '-X', 'utf8', str(SMOKE), '--wheel-dir', str(self.wheel_dir)],
            cwd=self.root, env=env, text=True, encoding='utf-8',
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        return result

    def test_valid_wheel_works_without_checkout_pythonpath(self):
        self.make_wheel()
        poison = self.root / 'poison' / 'raee_lite'
        poison.mkdir(parents=True)
        (poison / '__init__.py').write_text("raise RuntimeError('PYTHONPATH leaked')\n")
        result = self.run_smoke({'PYTHONPATH': str(poison.parent),
                                 'PYTHONIOENCODING': 'ascii', 'PYTHONUTF8': '0'})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.count('Added requirement: R1'), 2, result.stdout)
        self.assertIn('Installed wheel:', result.stdout)

    def test_missing_console_entry_point_is_rejected(self):
        self.make_wheel(entry_point=None)
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('raee-lite', result.stdout)
        self.assertNotIn('Installed wheel:', result.stdout)

    def test_broken_console_entry_point_is_rejected(self):
        self.make_wheel(entry_point='raee_lite.missing_entry:main')
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('missing_entry', result.stdout)
        self.assertNotIn('Installed wheel:', result.stdout)

    def test_console_entry_point_must_preserve_status_exit(self):
        self.make_wheel(entry_point='raee_lite._packaging_fixture:main', overrides={
            'raee_lite/_packaging_fixture.py': (
                b'from .cli import main as cli_main\n'
                b'def main():\n    cli_main()\n'),
        })
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('exit 0', result.stdout)
        self.assertNotIn('Installed wheel:', result.stdout)

    def test_module_entry_point_must_preserve_status_exit(self):
        self.make_wheel(overrides={
            'raee_lite/__main__.py': b'from .cli import main\nmain()\n',
        })
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('exit 0', result.stdout)
        self.assertNotIn('Installed wheel:', result.stdout)

    def test_missing_packaged_template_is_rejected(self):
        self.make_wheel(overrides={'raee_lite/skill_template.md': None})
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('skill_template.md', result.stdout)
        self.assertNotIn('Installed wheel:', result.stdout)

    def test_missing_or_ambiguous_wheels_are_rejected(self):
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('exactly one', result.stdout)
        wheel = self.make_wheel()
        (self.wheel_dir / 'raee_lite-0.0.1-py3-none-any.whl').write_bytes(wheel.read_bytes())
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('exactly one', result.stdout)


if __name__ == '__main__':
    unittest.main()
