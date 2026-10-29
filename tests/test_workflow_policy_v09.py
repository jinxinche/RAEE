"""Policy regression checks on workflows. Not a substitute for live GitHub security review."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class WorkflowPolicy(unittest.TestCase):
    def test_trusted_issuance_is_main_only(self):
        text=(ROOT/'.github/workflows/trusted-evidence.yml.example').read_text()
        self.assertIn('branches: [main]',text)
        self.assertNotIn('pull_request_target:',text)
        self.assertNotIn('workflow_run:',text)
        self.assertIn('id-token: write',text)
        self.assertIn('attestations: write',text)
        self.assertIn('needs: collect',text)

    def test_signing_job_never_checks_out_source(self):
        s=(ROOT/'.github/workflows/trusted-evidence.yml.example').read_text().split('\n  sign:',1)[1]
        self.assertNotIn('actions/checkout@',s)
        self.assertNotIn('pip install',s)
        self.assertNotIn('raee-lite run',s)
        self.assertIn('actions/attest@',s)

    def test_pr_reader_is_not_privileged_and_never_runs_scripts(self):
        s=(ROOT/'.github/workflows/pr-evidence-example.yml.example').read_text()
        self.assertNotIn('pull_request_target:',s)
        self.assertNotIn('workflow_run:',s)
        self.assertNotIn('id-token: write',s)
        self.assertNotIn('attestations: write',s)
        self.assertNotIn('--allow-ci-execution',s)
        self.assertIn('contents: read',s)
        self.assertIn('--expected-head-sha',s)
        self.assertIn('pip install --no-deps ./base',s)

    def test_regression_matrix_not_on_untrusted_pull_request(self):
        s=(ROOT/'.github/workflows/tests.yml').read_text()
        self.assertNotIn('pull_request:',s)
        self.assertNotIn('pull_request_target:',s)
        self.assertIn('ubuntu-latest',s)
        self.assertIn('windows-latest',s)
        self.assertIn('macos-latest',s)
        self.assertIn('python scripts/run_reviewed_suite.py --min-tests 150',s)
        self.assertIn('validate-corpus',s)
        self.assertNotIn('raee-lite check --ci',s)

    def test_live_candidate_workflows_are_trust_scoped(self):
        # v0.9.1 explicitly enables LIVE-candidate workflows; they still require
        # real branch protection and cloud verification before claiming trust.
        trusted=(ROOT/'.github/workflows/trusted-evidence.yml').read_text()
        pr=(ROOT/'.github/workflows/pr-boundary.yml').read_text()
        self.assertIn('workflow_dispatch:',trusted)
        self.assertNotIn('pull_request:',trusted)
        self.assertIn("github.repository == 'jinxinche/RAEE'",trusted)
        self.assertIn('contents: read',pr)
        self.assertNotIn('id-token: write',pr)
        self.assertNotIn('attestations: write',pr)

if __name__=='__main__':unittest.main()
