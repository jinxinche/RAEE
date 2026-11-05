"""Deterministic local verifier regressions; no hosted signing or live gh calls."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite import ci_attestation as ci


class CiVerificationIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.manifest_path = self.root / 'manifest.json'
        self.report_path = self.root / 'report.json'
        self.policy = {
            'expected_repo': 'example-org/evidence-project',
            'expected_ref': 'refs/heads/main',
            'expected_sha': 'a' * 40,
            'expected_workflow': '.github/workflows/trusted-evidence.yml',
            'gh_executable': 'gh',
        }
        self.manifest = {
            'schema': ci.SCHEMA,
            'source': {
                'repository': self.policy['expected_repo'],
                'ref': self.policy['expected_ref'],
                'commit': self.policy['expected_sha'],
                'fingerprint_sha256': 'b' * 64,
            },
            'workflow': {
                'path': self.policy['expected_workflow'],
                'event': 'workflow_dispatch',
                'run_id': '123',
            },
        }
        self.set_outcome('CHECKS_PASSED_WITH_LIMITS', True)
        self.subjects = []
        self.verified_bytes = []

    def set_outcome(self, outcome, passed):
        raw = json.dumps({'overall': outcome}).encode()
        self.report_path.write_bytes(raw)
        self.manifest['report'] = {
            'sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw),
            'outcome': outcome,
            'strict_check_passed': passed,
        }
        # Deliberately preserve noncanonical whitespace in the signed subject.
        self.manifest_path.write_bytes(
            b' \n' + json.dumps(self.manifest, indent=2).encode() + b'\n')

    def gh(self, args, **kwargs):
        if args[1:] == ['version']:
            return subprocess.CompletedProcess(args, 0, b'gh version 2.97.0\n', b'')
        self.assertEqual(args[1:3], ['attestation', 'verify'])
        subject = Path(args[3])
        self.subjects.append(subject)
        raw = subject.read_bytes()
        self.verified_bytes.append(raw)
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(subject.stat().st_mode), 0o400)
            self.assertEqual(stat.S_IMODE(subject.parent.stat().st_mode), 0o700)
        # gh's cryptographic work is mocked. This fixture only records the
        # bytes it was given and deliberately claims a different run identity.
        rows = [{'verificationResult': {
            'statement': {
                '_type': 'https://in-toto.io/Statement/v1',
                'predicateType': 'https://slsa.dev/provenance/v1',
                'subject': [{'name': subject.name,
                             'digest': {'sha256': hashlib.sha256(raw).hexdigest()}}],
            },
            'signature': {'certificate': {
                'runInvocationURI': 'https://github.com/example-org/evidence-project/actions/runs/456/attempts/2',
            }},
        }}]
        return subprocess.CompletedProcess(args, 0, json.dumps(rows).encode(), b'')

    def verify(self, **kwargs):
        return ci.verify(self.manifest_path, **self.policy, **kwargs)

    def assert_cleaned(self):
        self.assertTrue(self.subjects)
        for subject in self.subjects:
            self.assertFalse(subject.exists())
            self.assertFalse(subject.parent.exists())

    def test_replacement_after_parse_cannot_change_verified_subject(self):
        original = self.manifest_path.read_bytes()
        original_report = self.manifest['report']['sha256']

        def replace_before_verification(args, **kwargs):
            if args[1:] == ['version']:
                # Deterministic replacement after document/report validation,
                # before gh opens its subject. No threads or timing dependency.
                self.set_outcome('FAILED_CHECK', False)
            return self.gh(args, **kwargs)

        with patch.object(ci.subprocess, 'run', side_effect=replace_before_verification):
            result = self.verify(report_path=self.report_path)
        self.assertNotEqual(self.manifest_path.read_bytes(), original)
        self.assertEqual(self.verified_bytes, [original])
        self.assertNotEqual(self.subjects[0], self.manifest_path)
        self.assertEqual(result['manifest_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(result['report_sha256'], original_report)
        self.assertTrue(result['report_content_checked'])
        self.assertEqual(result['report_outcome'], 'CHECKS_PASSED_WITH_LIMITS')
        self.assertTrue(result['strict_check_passed'])
        self.assertTrue(result['require_passed'])
        self.assert_cleaned()

    def test_failed_claim_retains_outcome_and_relaxed_policy(self):
        self.set_outcome('FAILED_CHECK', False)
        with patch.object(ci.subprocess, 'run', side_effect=self.gh):
            result = self.verify(report_path=self.report_path, require_passed=False)
        self.assertEqual(result['result'], 'GITHUB_ATTESTATION_VERIFIED')
        self.assertEqual(result['report_outcome'], 'FAILED_CHECK')
        self.assertIs(result['strict_check_passed'], False)
        self.assertIs(result['require_passed'], False)
        self.assertFalse(result['code_correctness_proven'])
        self.assert_cleaned()

    def test_failed_claim_still_rejected_by_default_before_gh(self):
        self.set_outcome('FAILED_CHECK', False)
        with patch.object(ci.subprocess, 'run') as runner:
            with self.assertRaisesRegex(ValueError, 'does not claim passing'):
                self.verify()
            runner.assert_not_called()

    def test_passing_claim_still_discloses_relaxed_policy(self):
        with patch.object(ci.subprocess, 'run', side_effect=self.gh):
            result = self.verify(require_passed=False)
        self.assertEqual(result['report_outcome'], 'CHECKS_PASSED_WITH_LIMITS')
        self.assertIs(result['strict_check_passed'], True)
        self.assertIs(result['require_passed'], False)
        self.assertFalse(result['report_content_checked'])

    def test_missing_status_is_preserved_as_unknown_in_relaxed_mode(self):
        del self.manifest['report']['outcome']
        del self.manifest['report']['strict_check_passed']
        self.manifest_path.write_text(json.dumps(self.manifest))
        with patch.object(ci.subprocess, 'run', side_effect=self.gh):
            result = self.verify(require_passed=False)
        self.assertIsNone(result['report_outcome'])
        self.assertIsNone(result['strict_check_passed'])
        self.assertIs(result['require_passed'], False)

    def test_optional_certificate_run_identity_is_not_promoted_to_trust(self):
        with patch.object(ci.subprocess, 'run', side_effect=self.gh):
            result = self.verify()
        self.assertEqual(result['claimed_run_id'], '123')
        self.assertIs(result['run_identity_verified'], False)
        self.assertIn('Run ID/attempt and event identity are not independently verified', result['notice'])

    def test_private_subject_cleaned_on_verifier_failure(self):
        for failure in ('nonzero', 'timeout', 'invalid_json', 'empty'):
            with self.subTest(failure=failure):
                self.subjects.clear()

                def fail(args, **kwargs):
                    completed = self.gh(args, **kwargs)
                    if args[1:] == ['version']:
                        return completed
                    if failure == 'timeout':
                        raise subprocess.TimeoutExpired(args, 60)
                    return subprocess.CompletedProcess(
                        args, 1 if failure == 'nonzero' else 0,
                        b'[]' if failure == 'empty' else b'not json', b'')

                with patch.object(ci.subprocess, 'run', side_effect=fail):
                    with self.assertRaises(ValueError):
                        self.verify()
                self.assert_cleaned()

    def test_manifest_uses_strict_json_before_gh(self):
        original = self.manifest_path.read_bytes()
        invalid = [
            original.replace(b'"run_id": "123"', b'"run_id": "456", "run_id": "123"'),
            original.replace(b'"strict_check_passed": true', b'"strict_check_passed": NaN'),
            original.replace(b'"strict_check_passed": true', b'"strict_check_passed": 1e999'),
        ]
        for raw in invalid:
            with self.subTest(raw=raw):
                self.manifest_path.write_bytes(raw)
                with patch.object(ci.subprocess, 'run') as runner:
                    with self.assertRaisesRegex(ValueError, 'Invalid evidence JSON'):
                        self.verify(require_passed=False)
                    runner.assert_not_called()

    def test_report_uses_strict_json_even_with_matching_digest(self):
        for raw in (b'{"overall":"FAILED_CHECK","overall":"CHECKS_PASSED_WITH_LIMITS"}',
                    b'{"value":Infinity}', b'{"value":1e999}'):
            with self.subTest(raw=raw):
                self.report_path.write_bytes(raw)
                self.manifest['report'].update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
                self.manifest_path.write_text(json.dumps(self.manifest))
                with patch.object(ci.subprocess, 'run') as runner:
                    with self.assertRaisesRegex(ValueError, 'Invalid evidence JSON'):
                        self.verify(report_path=self.report_path)
                    runner.assert_not_called()

    def test_verifier_response_uses_strict_json(self):
        for raw in (b'[{"verificationResult":{},"verificationResult":true}]',
                    b'[{"verificationResult":{"value":NaN}}]',
                    b'[{"verificationResult":{"value":1e999}}]'):
            with self.subTest(raw=raw):
                self.subjects.clear()

                def invalid(args, **kwargs):
                    completed = self.gh(args, **kwargs)
                    if args[1:] == ['version']:
                        return completed
                    return subprocess.CompletedProcess(args, 0, raw, b'')

                with patch.object(ci.subprocess, 'run', side_effect=invalid):
                    with self.assertRaisesRegex(ValueError, 'Invalid GitHub verification response'):
                        self.verify()
                self.assert_cleaned()


if __name__ == '__main__':
    unittest.main()
