import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('pr_boundary', ROOT / 'scripts/pr_boundary.py')
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class PRBoundaryTests(unittest.TestCase):
    def test_ordinary_source_change_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'base').mkdir(); (root/'head').mkdir()
            for sub,text in [('base','before'),('head','after')]:
                (root/sub/'src').mkdir(); (root/sub/'src'/'x.py').write_text(text)
            allowed, flagged=MOD.evaluate(root/'base',root/'head')
            self.assertTrue(allowed); self.assertEqual(flagged,[])
    def test_ci_file_modification_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'base').mkdir();(root/'head').mkdir()
            (root/'head'/'.github/workflows').mkdir(parents=True)
            (root/'head'/'.github/workflows'/'trust.yml').write_text('on: pull_request_target')
            allowed, flagged=MOD.evaluate(root/'base',root/'head')
            self.assertFalse(allowed); self.assertIn('.github/workflows/trust.yml',flagged)
    def test_repo_script_change_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'base').mkdir();(root/'head').mkdir()
            (root/'head'/'scripts').mkdir();(root/'head'/'scripts'/'run.sh').write_text('echo dangerous')
            self.assertFalse(MOD.evaluate(root/'base',root/'head')[0])
    def test_symlinks_not_followed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'base').mkdir();(root/'head').mkdir()
            (root/'head'/'leak').symlink_to('/etc/passwd')
            s=MOD.snapshot(root/'head'); self.assertEqual(s['leak'],'symlink')
    def test_new_symlink_files_and_directories_require_review(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root/'base').mkdir(); (root/'head').mkdir()
            (root/'head'/'asset').symlink_to('/etc/passwd')
            allowed, risky = MOD.evaluate(root/'base', root/'head')
            self.assertFalse(allowed); self.assertIn('asset', risky)
            (root/'head'/'asset').unlink()
            (root/'head'/'external').symlink_to('/tmp', target_is_directory=True)
            allowed, risky = MOD.evaluate(root/'base', root/'head')
            self.assertFalse(allowed); self.assertIn('external', risky)
    def test_large_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'x').mkdir(); (root/'x'/'large').write_bytes(b'x'*(MOD.MAX_FILE_BYTES+1))
            with self.assertRaises(ValueError): MOD.snapshot(root/'x')
    def test_trust_file_modification_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'base').mkdir();(root/'head').mkdir()
            path=root/'head'/'src'/'raee_lite';path.mkdir(parents=True)
            (path/'ci_attestation.py').write_text('modified')
            self.assertFalse(MOD.evaluate(root/'base',root/'head')[0])

class WorkflowPolicyTests(unittest.TestCase):
    def test_workflow_boundaries(self):
        pr=(ROOT/'.github/workflows/pr-boundary.yml').read_text()
        trusted=(ROOT/'.github/workflows/trusted-evidence.yml').read_text()
        tests=(ROOT/'.github/workflows/tests.yml').read_text()
        self.assertIn('pull_request:',pr)
        self.assertNotIn('pull_request_target:',pr)
        self.assertIn('contents: read',pr)
        self.assertNotIn('attestations: write',pr)
        self.assertNotIn('id-token: write',pr)
        self.assertNotIn('pip install',pr)
        self.assertIn('python base/scripts/pr_boundary.py',pr)
        self.assertIn('id-token: write',trusted)
        self.assertIn('needs: collect',trusted)
        self.assertNotIn('pull_request:',trusted)
        self.assertNotIn('pull_request:',tests)
        self.assertIn('windows-latest',tests)
        self.assertIn('macos-latest',tests)

if __name__=='__main__': unittest.main()
