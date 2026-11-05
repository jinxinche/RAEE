"""Local gh-output/policy regressions; signatures and network calls are mocked."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite import ci_attestation as ci


class OriginEdgesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.path = self.root / 'manifest.json'
        self.policy = {
            'expected_repo': 'example-org/evidence-project',
            'expected_ref': 'refs/heads/main',
            'expected_sha': 'a' * 40,
            'expected_workflow': '.github/workflows/trusted-evidence.yml',
            'gh_executable': 'gh',
        }
        self.identity = ('https://github.com/example-org/evidence-project/'
                         '.github/workflows/trusted-evidence.yml@refs/heads/main')
        self.manifest = {
            'schema': ci.SCHEMA,
            'source': {'repository': self.policy['expected_repo'],
                       'ref': self.policy['expected_ref'],
                       'commit': self.policy['expected_sha'],
                       'fingerprint_sha256': 'b' * 64},
            'workflow': {'path': self.policy['expected_workflow'],
                         'event': 'push', 'run_id': '123'},
            'report': {'sha256': 'c' * 64, 'bytes': 100,
                       'outcome': 'CHECKS_PASSED_WITH_LIMITS',
                       'strict_check_passed': True},
        }
        self.path.write_text(json.dumps(self.manifest))
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.row = {'verificationResult': {
            'statement': {
                '_type': 'https://in-toto.io/Statement/v1',
                'predicateType': 'https://slsa.dev/provenance/v1',
                'subject': [{'name': 'ci-evidence.json',
                             'digest': {'sha256': self.digest}}],
            },
            'signature': {'certificate': {
                'subjectAlternativeName': self.identity,
                'issuer': 'https://token.actions.githubusercontent.com',
                'sourceRepositoryURI': 'https://github.com/example-org/evidence-project',
                'sourceRepositoryDigest': self.policy['expected_sha'],
                'sourceRepositoryRef': self.policy['expected_ref'],
                'buildSignerDigest': self.policy['expected_sha'],
                'runnerEnvironment': 'github-hosted',
            }},
        }}

    def verify_rows(self, rows, *, returncode=0):
        def gh(args, **kwargs):
            if args[1:] == ['version']:
                return subprocess.CompletedProcess(args, 0, b'gh version 2.97.0\n', b'')
            return subprocess.CompletedProcess(args, returncode, json.dumps(rows).encode(), b'')

        with patch.object(ci.subprocess, 'run', side_effect=gh):
            return ci.verify(self.path, **self.policy)

    def test_valid_result_keeps_bounded_claims(self):
        result = self.verify_rows([self.row])
        self.assertEqual(result['result'], 'GITHUB_ATTESTATION_VERIFIED')
        self.assertEqual(result['verified_attestations'], 1)
        self.assertEqual(result['manifest_sha256'], self.digest)
        self.assertEqual(result['report_outcome'], 'CHECKS_PASSED_WITH_LIMITS')
        self.assertIs(result['run_identity_verified'], False)
        self.assertIs(result['code_correctness_proven'], False)

    def test_multiple_valid_results_are_counted(self):
        self.assertEqual(self.verify_rows([self.row, copy.deepcopy(self.row)])['verified_attestations'], 2)

    def test_empty_or_nonarray_envelope_fails_closed(self):
        for rows in (None, False, True, 1, 'verified', {}, self.row, []):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.verify_rows(rows)

    def test_nonobject_rows_fail_closed(self):
        for row in (None, False, True, 1, 'verified', []):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.verify_rows([row])

    def test_missing_verification_result_fails_closed(self):
        for row in ({}, {'attestation': {}}, {'error': 'verification failed'}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.verify_rows([row])

    def test_boolean_or_scalar_verification_result_fails_closed(self):
        for result in (False, True, None, 0, 1, 'verified', []):
            with self.subTest(result=result), self.assertRaises(ValueError):
                self.verify_rows([{'verificationResult': result}])

    def test_empty_verification_result_fails_closed(self):
        with self.assertRaises(ValueError):
            self.verify_rows([{'verificationResult': {}}])

    def test_invalid_statement_fails_closed(self):
        for statement in (None, False, [], 'verified', {}):
            row = copy.deepcopy(self.row)
            row['verificationResult']['statement'] = statement
            with self.subTest(statement=statement), self.assertRaises(ValueError):
                self.verify_rows([row])

    def test_wrong_statement_or_predicate_type_fails_closed(self):
        for key in ('_type', 'predicateType'):
            for value in (None, '', 'https://example.invalid/other'):
                row = copy.deepcopy(self.row)
                row['verificationResult']['statement'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.verify_rows([row])

    def test_optional_predicate_must_be_an_object(self):
        for predicate in (None, False, True, 1, [], 'verified'):
            row = copy.deepcopy(self.row)
            row['verificationResult']['statement']['predicate'] = predicate
            with self.subTest(predicate=predicate), self.assertRaises(ValueError):
                self.verify_rows([row])

    def test_predicate_claims_do_not_promote_assurance(self):
        row = copy.deepcopy(self.row)
        row['verificationResult']['statement']['predicate'] = {
            'run_identity_verified': True, 'code_correctness_proven': True,
        }
        result = self.verify_rows([row])
        self.assertIs(result['run_identity_verified'], False)
        self.assertIs(result['code_correctness_proven'], False)

    def test_invalid_signature_fails_closed(self):
        for signature in (None, False, [], {}, 'verified'):
            row = copy.deepcopy(self.row)
            row['verificationResult']['signature'] = signature
            with self.subTest(signature=signature), self.assertRaises(ValueError):
                self.verify_rows([row])

    def test_invalid_certificate_fails_closed(self):
        for certificate in (None, False, [], {}, 'verified'):
            row = copy.deepcopy(self.row)
            row['verificationResult']['signature']['certificate'] = certificate
            with self.subTest(certificate=certificate), self.assertRaises(ValueError):
                self.verify_rows([row])

    def test_missing_subject_fails_closed(self):
        for subject in (None, False, {}, [], 'verified'):
            row = copy.deepcopy(self.row)
            row['verificationResult']['statement']['subject'] = subject
            with self.subTest(subject=subject), self.assertRaises(ValueError):
                self.verify_rows([row])

    def test_invalid_subject_entry_fails_closed(self):
        for subject in (None, False, [], {}, {'digest': None},
                        {'digest': []}, {'digest': {'sha256': False}}):
            row = copy.deepcopy(self.row)
            row['verificationResult']['statement']['subject'] = [subject]
            with self.subTest(subject=subject), self.assertRaises(ValueError):
                self.verify_rows([row])

    def test_subject_digest_must_bind_exact_manifest(self):
        row = copy.deepcopy(self.row)
        row['verificationResult']['statement']['subject'][0]['digest']['sha256'] = 'd' * 64
        with self.assertRaises(ValueError):
            self.verify_rows([row])

    def test_matching_digest_in_unsigned_extra_field_is_insufficient(self):
        row = copy.deepcopy(self.row)
        row['manifest_sha256'] = self.digest
        row['verificationResult']['statement']['subject'][0]['digest']['sha256'] = 'd' * 64
        with self.assertRaises(ValueError):
            self.verify_rows([row])

    def test_matching_statement_outside_verification_result_is_insufficient(self):
        row = copy.deepcopy(self.row)
        row['attestation'] = {'statement': row['verificationResult'].pop('statement')}
        with self.assertRaises(ValueError):
            self.verify_rows([row])

    def test_digest_under_another_algorithm_cannot_match(self):
        for algorithm in ('sha512', 'SHA256', 'customDigest'):
            row = copy.deepcopy(self.row)
            row['verificationResult']['statement']['subject'][0]['digest'] = {algorithm: self.digest}
            with self.subTest(algorithm=algorithm), self.assertRaises(ValueError):
                self.verify_rows([row])

    def test_subject_name_is_optional_and_does_not_bind_artifact(self):
        for name in (None, 'renamed.json'):
            row = copy.deepcopy(self.row)
            subject = row['verificationResult']['statement']['subject'][0]
            if name is None:
                del subject['name']
            else:
                subject['name'] = name
            with self.subTest(name=name):
                self.assertEqual(self.verify_rows([row])['manifest_sha256'], self.digest)

    def test_unknown_digest_algorithm_can_coexist_with_matching_sha256(self):
        row = copy.deepcopy(self.row)
        row['verificationResult']['statement']['subject'][0]['digest']['customDigest'] = 'opaque-reference'
        self.assertEqual(self.verify_rows([row])['verified_attestations'], 1)

    def test_multi_subject_attestation_can_match_one_artifact(self):
        row = copy.deepcopy(self.row)
        row['verificationResult']['statement']['subject'].insert(
            0, {'name': 'another.json', 'digest': {'sha256': 'd' * 64}})
        self.assertEqual(self.verify_rows([row])['verified_attestations'], 1)

    def test_matching_subject_does_not_hide_malformed_other_subjects(self):
        for malformed in (None, {}, {'digest': {}}, {'digest': {'sha256': ''}},
                          {'digest': {'sha256': 'd' * 64, 'sha512': False}}):
            for position in (0, 1):
                row = copy.deepcopy(self.row)
                row['verificationResult']['statement']['subject'].insert(position, malformed)
                with self.subTest(malformed=malformed, position=position), self.assertRaises(ValueError):
                    self.verify_rows([row])

    def test_mixed_valid_and_invalid_rows_fail_closed(self):
        for invalid in ({}, None, {'verificationResult': False}):
            for rows in ([self.row, invalid], [invalid, self.row]):
                with self.subTest(rows=rows), self.assertRaises(ValueError):
                    self.verify_rows(rows)

    def test_nonzero_exit_cannot_be_overridden_by_valid_json(self):
        with self.assertRaises(ValueError):
            self.verify_rows([self.row], returncode=1)

    def verify_identity(self, identity, *, signer_digest=None):
        """Model gh v2.97.0's documented SAN policy, without signing anything.

        validateSignerWorkflow constructs an escaped prefix without an end
        anchor; --cert-identity uses an exact SAN matcher. Source:
        https://github.com/cli/cli/blob/v2.97.0/pkg/cmd/attestation/verify/policy.go
        """
        row = copy.deepcopy(self.row)
        certificate = row['verificationResult']['signature']['certificate']
        certificate['subjectAlternativeName'] = identity
        certificate['buildSignerDigest'] = signer_digest or self.policy['expected_sha']

        def gh(args, **kwargs):
            if args[1:] == ['version']:
                return subprocess.CompletedProcess(args, 0, b'gh version 2.97.0\n', b'')
            if '--cert-identity' in args:
                accepted = identity == args[args.index('--cert-identity') + 1]
            else:
                workflow = args[args.index('--signer-workflow') + 1]
                accepted = re.match('^' + re.escape('https://github.com/' + workflow), identity) is not None
            if '--signer-digest' in args:
                accepted = accepted and certificate['buildSignerDigest'] == args[args.index('--signer-digest') + 1]
            return subprocess.CompletedProcess(args, 0 if accepted else 1, json.dumps([row]).encode(), b'')

        with patch.object(ci.subprocess, 'run', side_effect=gh) as runner:
            result = ci.verify(self.path, **self.policy)
        return result, runner.call_args.args[0]

    def test_workflow_filename_prefix_collision_is_rejected(self):
        identity = self.identity.replace('trusted-evidence.yml@', 'trusted-evidence.yml.evil.yml@')
        with self.assertRaises(ValueError):
            self.verify_identity(identity)

    def test_workflow_ref_prefix_collision_is_rejected(self):
        with self.assertRaises(ValueError):
            self.verify_identity(self.identity + '-untrusted')

    def test_reusable_signer_on_another_ref_is_rejected(self):
        with self.assertRaises(ValueError):
            self.verify_identity(self.identity.replace('refs/heads/main', 'refs/heads/untrusted'))

    def test_reusable_signer_at_another_commit_is_rejected(self):
        with self.assertRaises(ValueError):
            self.verify_identity(self.identity, signer_digest='d' * 40)

    def test_exact_signer_identity_uses_compatible_explicit_policy_flags(self):
        result, args = self.verify_identity(self.identity)
        self.assertEqual(result['result'], 'GITHUB_ATTESTATION_VERIFIED')
        expected = {'--cert-identity': self.identity,
                    '--hostname': 'github.com',
                    '--signer-digest': self.policy['expected_sha'],
                    '--source-digest': self.policy['expected_sha'],
                    '--source-ref': self.policy['expected_ref'],
                    '--repo': self.policy['expected_repo'],
                    '--cert-oidc-issuer': 'https://token.actions.githubusercontent.com',
                    '--predicate-type': 'https://slsa.dev/provenance/v1',
                    '--digest-alg': 'sha256'}
        for flag, value in expected.items():
            self.assertIn(flag, args)
            self.assertEqual(args[args.index(flag) + 1], value)
        # gh rejects these when combined with --cert-identity.
        for flag in ('--signer-workflow', '--cert-identity-regex', '--signer-repo'):
            self.assertNotIn(flag, args)
        self.assertIn('--deny-self-hosted-runners', args)


if __name__ == '__main__':
    unittest.main()
