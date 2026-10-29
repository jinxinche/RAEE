"""Trusted CI artifact provenance policy tests; gh CLI mocked unless documented otherwise."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite import core
from raee_lite.enhanced import save_report
from raee_lite.ci_attestation import export, verify
from raee_lite.cli import main

REPO = 'example-org/evidence-project'
REF = 'refs/heads/main'
WORKFLOW = '.github/workflows/trusted-evidence.yml'


def git(root, *cmd):
    return subprocess.run(['git', *cmd], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


class CiAttestationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'repo'
        self.root.mkdir()
        (self.root / '.gitignore').write_text('.raee/\n')
        (self.root / 'sample.py').write_text('def answer(): return True\n')
        git(self.root, 'init', '-q')
        git(self.root, 'add', '.')
        git(self.root, '-c', 'user.name=Test', '-c', 'user.email=test@invalid.test', 'commit', '-qm', 'trusted')
        self.sha = git(self.root, 'rev-parse', 'HEAD')
        core.init(self.root)
        core.add_requirement(self.root, 'Unit tests execute')
        from raee_lite.contracts import set_expectation
        set_expectation(self.root, 'R1', 'unit')
        core.run_check(self.root, 'R1', ['python', '-c', 'import sys;sys.exit(0)'], 30, kind='unit')
        save_report(self.root)
        self.env = {'CI': 'true', 'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': REPO,
                    'GITHUB_REF': REF, 'GITHUB_SHA': self.sha, 'GITHUB_EVENT_NAME': 'push',
                    'GITHUB_RUN_ID': '123456', 'GITHUB_WORKFLOW_REF': f'{REPO}/{WORKFLOW}@{REF}'}

    def create(self, **kw):
        return export(self.root, expected_repo=REPO, trusted_ref=REF, workflow=WORKFLOW,
                      environ=self.env, **kw)

    def verify(self, **kw):
        # These tests exercise verifier policy with a mocked gh attestation result.
        # gh-version enforcement is tested separately against explicit version fixtures.
        with patch('raee_lite.ci_attestation.require_safe_gh', return_value=(2, 97, 0)):
            return verify(self.root / '.raee/ci-evidence.json',
                          expected_repo=REPO, expected_ref=REF, expected_sha=self.sha,
                          expected_workflow=WORKFLOW, **kw)

    def test_export_private_safe_fields_only(self):
        out = self.create()
        self.assertTrue(out['report']['strict_check_passed'])
        data = (self.root / '.raee/ci-evidence.json').read_text()
        self.assertNotIn('Unit tests execute', data)
        self.assertNotIn('python -c', data)
        self.assertEqual(out['source']['commit'], self.sha)
        self.assertIn('UNTRUSTED', out['assurance'])

    def test_not_a_pr_or_untrusted_branch(self):
        for key, value in [('GITHUB_EVENT_NAME', 'pull_request'), ('GITHUB_REF', 'refs/pull/1/merge'),
                           ('GITHUB_REPOSITORY', 'another/repo'), ('GITHUB_WORKFLOW_REF', 'attacker/workflow')]:
            with self.subTest(key=key):
                original = self.env[key]
                self.env[key] = value
                with self.assertRaises(ValueError):
                    self.create()
                self.env[key] = original

    def test_oidc_context_is_not_sufficient(self):
        # Even if all fields are forged, export is explicitly tagged UNTRUSTED.
        out = self.create()
        self.assertEqual(out['assurance'], 'UNTRUSTED_EXPORT_UNTIL_GITHUB_ATTESTATION_VERIFIED')

    def test_missing_or_invalid_context(self):
        old = self.env['GITHUB_ACTIONS']
        self.env['GITHUB_ACTIONS'] = 'false'
        with self.assertRaisesRegex(ValueError, 'GitHub Actions'):
            self.create()
        self.env['GITHUB_ACTIONS'] = old
        self.env['GITHUB_SHA'] = 'a' * 40
        with self.assertRaisesRegex(ValueError, 'Git HEAD'):
            self.create()

    def test_dirty_tree_rejected(self):
        (self.root / 'extra.py').write_text('x=5')
        with self.assertRaisesRegex(ValueError, 'Dirty'):
            self.create()

    def test_stale_report_rejected(self):
        (self.root / 'sample.py').write_text('raise AssertionError')
        with self.assertRaises(ValueError):
            self.create()

    def test_stale_ledger_is_rejected_even_if_source_unchanged(self):
        ledger_path = self.root / '.raee/ledger.json'
        ledger = json.loads(ledger_path.read_text())
        ledger['runs'][-1]['observed_exit_code'] = 1
        ledger['runs'][-1]['observed_status'] = 'fail'
        ledger_path.write_text(json.dumps(ledger))
        with self.assertRaisesRegex(ValueError, 'ledger/manifest'):
            self.create()

    def test_partial_source_rejected(self):
        from raee_lite import ci_attestation
        original = ci_attestation.core.fingerprint
        def fake(root):
            item = original(root)
            item['skipped'] = [{'file':'secret', 'reason':'size'}]
            return item
        with patch.object(ci_attestation.core, 'fingerprint', side_effect=fake):
            with self.assertRaisesRegex(ValueError, 'Partial'):
                self.create()

    def test_overall_failure_rejected(self):
        from raee_lite.contracts import set_expectation
        set_expectation(self.root, 'R1', 'e2e')
        save_report(self.root)
        with self.assertRaisesRegex(ValueError, 'not passing'):
            self.create()
        out = self.create(require_passed=False)
        self.assertFalse(out['report']['strict_check_passed'])

    def test_verifier_missing_gh_fails_closed(self):
        self.create()
        with patch('raee_lite.ci_attestation.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'gh'):
                self.verify()

    def test_verified_identity_is_pinned_in_gh_invocation(self):
        self.create()
        output = subprocess.CompletedProcess(['gh'], 0, b'[{"verificationResult":true}]', b'')
        with patch('raee_lite.ci_attestation.subprocess.run', return_value=output) as run:
            result = self.verify(gh_executable='/usr/bin/gh', report_path=self.root / '.raee/report.json')
        cmd = run.call_args.args[0]
        self.assertEqual(result['result'], 'GITHUB_ATTESTATION_VERIFIED')
        self.assertTrue(result['report_content_checked'])
        self.assertIn('--source-digest', cmd)
        self.assertEqual(cmd[cmd.index('--source-digest') + 1], self.sha)
        self.assertEqual(cmd[cmd.index('--signer-workflow') + 1], f'{REPO}/{WORKFLOW}')
        self.assertIn('--deny-self-hosted-runners', cmd)
        self.assertFalse(run.call_args.kwargs.get('shell', False))

    def test_wrong_expected_identity_fails_before_gh(self):
        self.create()
        with patch('raee_lite.ci_attestation.subprocess.run') as runner:
            with self.assertRaisesRegex(ValueError, 'does not match'):
                verify(self.root / '.raee/ci-evidence.json', expected_repo=REPO, expected_ref='refs/heads/dev', expected_sha=self.sha, expected_workflow=WORKFLOW, gh_executable='/usr/bin/gh')
            runner.assert_not_called()

    def test_ref_metadata_tampering_detected(self):
        self.create()
        path = self.root / '.raee/ci-evidence.json'
        data = json.loads(path.read_text())
        data['source']['ref'] = 'refs/heads/dev'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.verify(gh_executable='/usr/bin/gh')

    def test_report_tampering_detected_before_gh(self):
        self.create()
        path = self.root / '.raee/report.json'
        path.write_bytes(path.read_bytes() + b' ')
        with patch('raee_lite.ci_attestation.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'differs'):
                self.verify(gh_executable='/usr/bin/gh', report_path=path)
            run.assert_not_called()

    def test_verifier_nonzero_exit_and_empty_list_fail_closed(self):
        self.create()
        for rc, output in [(1, b''), (0, b'[]'), (0, b'not json')]:
            with self.subTest(rc=rc, output=output):
                with patch('raee_lite.ci_attestation.subprocess.run',
                           return_value=subprocess.CompletedProcess(['gh'], rc, output, b'')):
                    with self.assertRaises(ValueError):
                        self.verify(gh_executable='/usr/bin/gh')

    def test_timeout_and_malformed_args(self):
        self.create()
        with self.assertRaisesRegex(ValueError, 'timeout'):
            self.verify(timeout=0)
        with self.assertRaisesRegex(ValueError, 'Invalid'):
            verify(self.root / '.raee/ci-evidence.json', expected_repo='bad;touch /tmp/bad',
                   expected_ref=REF, expected_sha=self.sha, expected_workflow=WORKFLOW)
        with patch('raee_lite.ci_attestation.subprocess.run', side_effect=subprocess.TimeoutExpired('gh', 60)):
            with self.assertRaisesRegex(ValueError, 'timed out'):
                self.verify(gh_executable='/usr/bin/gh')

    def test_symlink_subject_rejected(self):
        self.create()
        target = self.root / '.raee/ci-evidence.json'
        link = self.root / 'fake.json'
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest('Symlinks unsupported')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            verify(link, expected_repo=REPO, expected_ref=REF, expected_sha=self.sha,
                   expected_workflow=WORKFLOW, gh_executable='/usr/bin/gh')


if __name__ == '__main__':
    unittest.main()
