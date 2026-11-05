"""Malformed claims remain invalid even with a genuinely trusted signature."""
from __future__ import annotations

import base64
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from raee_lite import attestation, core, enhanced


class EnvelopeEdgeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.root = self.base / 'project'
        self.root.mkdir()
        (self.root / 'app.py').write_text('pass\n', encoding='utf-8')
        core.init(self.root)
        enhanced.save_report(self.root)
        self.private, self.public = self.base / 'private.pem', self.base / 'public.pem'
        attestation.keygen(self.private, self.public, self.root)
        self.key = attestation._load_private(self.private)
        self.envelope = self.root / '.raee/attestation.dsse.json'
        self.report = self.root / '.raee/report.json'
        self.ledger = self.root / '.raee/ledger.json'
        self.manifest = self.root / '.raee/manifest.json'
        attestation.create(self.root, self.private, self.envelope, allow_no_git=True)
        self.env = json.loads(self.envelope.read_bytes())
        self.statement = json.loads(base64.b64decode(self.env['payload']))
        self.report_value = json.loads(self.report.read_bytes())

    def write_signed(self, statement):
        payload = attestation._canonical(statement)
        env = deepcopy(self.env)
        env['payload'] = base64.b64encode(payload).decode('ascii')
        env['signatures'][0]['sig'] = base64.b64encode(
            self.key.sign(attestation._pae(attestation.TYPE.encode(), payload))).decode('ascii')
        self.envelope.write_text(json.dumps(env), encoding='utf-8')

    def bind_report(self, statement, report):
        self.report.write_text(json.dumps(report), encoding='utf-8')
        digest = attestation._digest(self.report.read_bytes())
        statement['predicate']['report_sha256'] = digest
        statement['subject'][1]['digest']['sha256'] = digest

    def verify(self, **kwargs):
        return attestation.verify(self.root, self.envelope, self.public, self.report, **kwargs)

    def receipt(self):
        return {'id': 'E1', 'origin': 'isolated_replay', 'snapshot_sha256': 'a' * 64,
                'image_id': 'sha256:' + 'b' * 64, 'status': 'pass', 'snapshot_excluded_total': 0}

    def ledger_run(self):
        sha = self.statement['predicate']['source']['sha256']
        return {'id': 'E1', 'origin': 'isolated_replay', 'source_fingerprint': sha,
                'source_fingerprint_after': sha, 'observed_status': 'pass', 'observed_exit_code': 0,
                'isolation': {'backend': 'docker', 'resolved_image_id': 'sha256:' + 'b' * 64,
                              'snapshot_sha256': 'a' * 64, 'snapshot_excluded_total': 0}}

    def assert_replacement_rejected(self, path, unsigned, signed, error, **options):
        # Read unsigned bytes, then atomically replace the path before a second
        # read could see the signed bytes. No timing or live writer is needed.
        path.write_bytes(unsigned)
        replacement = path.with_name(path.name + '.replacement')
        replacement.write_bytes(signed)
        original_file = attestation._file
        reads = []

        def read_then_replace(read_path, *args, **kwargs):
            raw = original_file(read_path, *args, **kwargs)
            if read_path == path:
                reads.append(raw)
                if len(reads) == 1:
                    replacement.replace(path)
            return raw

        with patch.object(attestation, '_file', side_effect=read_then_replace):
            with self.assertRaisesRegex(ValueError, error):
                self.verify(**options)
        self.assertEqual(reads, [unsigned])
        self.assertEqual(path.read_bytes(), signed)

    def test_report_replacement_cannot_mix_unsigned_content_with_signed_digest(self):
        signed = self.report.read_bytes()
        statement = deepcopy(self.statement)
        statement['predicate']['report_overall'] = 'UNSIGNED_OUTCOME'
        self.write_signed(statement)
        unsigned = deepcopy(self.report_value)
        unsigned['overall'] = 'UNSIGNED_OUTCOME'
        self.assert_replacement_rejected(
            self.report, attestation._canonical(unsigned), signed, 'Evidence report changed')

    def test_ledger_replacement_cannot_invent_an_isolated_receipt(self):
        signed = self.ledger.read_bytes()
        statement = deepcopy(self.statement)
        statement['predicate']['isolated_receipts'] = [self.receipt()]
        self.write_signed(statement)
        unsigned = attestation._canonical({'schema': 1, 'runs': [self.ledger_run()]})
        self.assert_replacement_rejected(
            self.ledger, unsigned, signed, 'Ledger digest',
            ledger_path=self.ledger, require_isolated=True)

    def test_manifest_replacement_cannot_hide_signed_non_object(self):
        unsigned = self.manifest.read_bytes()
        signed = b'[]'
        statement = deepcopy(self.statement)
        statement['predicate']['manifest_sha256'] = attestation._digest(signed)
        self.write_signed(statement)
        self.assert_replacement_rejected(
            self.manifest, unsigned, signed, 'Manifest digest', manifest_path=self.manifest)

    def test_verification_authenticates_captured_bytes_not_later_path_contents(self):
        for path, options in ((self.report, {}), (self.ledger, {'ledger_path': self.ledger}),
                              (self.manifest, {'manifest_path': self.manifest})):
            with self.subTest(input=path.name):
                signed = path.read_bytes()
                replacement = path.with_name(path.name + '.replacement')
                replacement.write_bytes(b'not the signed JSON')
                original_file = attestation._file
                reads = []

                def read_then_replace(read_path, *args, **kwargs):
                    raw = original_file(read_path, *args, **kwargs)
                    if read_path == path:
                        reads.append(raw)
                        if len(reads) == 1:
                            replacement.replace(path)
                    return raw

                try:
                    with patch.object(attestation, '_file', side_effect=read_then_replace):
                        result = self.verify(**options)
                    self.assertEqual(result['signature'], 'VALID')
                    self.assertFalse(result['code_correctness_proven'])
                    self.assertFalse(result['current_snapshot_checked'])
                    self.assertEqual(reads, [signed])
                    self.assertEqual(path.read_bytes(), b'not the signed JSON')
                finally:
                    path.write_bytes(signed)

    def test_generated_envelope_and_valid_isolated_claim_still_verify(self):
        self.assertEqual(self.verify(check_current=True, ledger_path=self.ledger,
                                     manifest_path=self.manifest)['signature'], 'VALID')
        statement = deepcopy(self.statement)
        statement['predicate']['isolated_receipts'] = [self.receipt()]
        core.write_json(self.ledger, {'schema': 1, 'runs': [self.ledger_run()]})
        statement['predicate']['ledger_sha256'] = attestation._digest(self.ledger.read_bytes())
        self.write_signed(statement)
        for options in ({}, {'ledger_path': self.ledger, 'manifest_path': self.manifest}):
            with self.subTest(options=options):
                result = self.verify(require_isolated=True, **options)
                self.assertEqual(result['isolated_receipts'], 1)
                self.assertFalse(result['code_correctness_proven'])

    def test_schema_version_requires_integer(self):
        for value in (True, 1.0, '1', None):
            with self.subTest(value=value):
                statement = deepcopy(self.statement)
                statement['predicate']['schema_version'] = value
                self.write_signed(statement)
                with self.assertRaisesRegex(ValueError, 'predicate version'):
                    self.verify()

    def test_offline_verification_requires_ledger_and_manifest_sha256(self):
        for field in ('ledger_sha256', 'manifest_sha256'):
            for value in (None, '', 'a' * 128, int('1' * 64), 'A' * 64):
                with self.subTest(field=field, value=value):
                    statement = deepcopy(self.statement)
                    if value is None:
                        statement['predicate'].pop(field)
                    else:
                        statement['predicate'][field] = value
                    self.write_signed(statement)
                    with self.assertRaisesRegex(ValueError, 'digest'):
                        self.verify()

    def test_numeric_source_digest_is_not_a_sha256_string(self):
        statement = deepcopy(self.statement)
        report = deepcopy(self.report_value)
        numeric = int('1' * 64)
        statement['predicate']['source']['sha256'] = numeric
        statement['subject'][0]['digest']['sha256'] = numeric
        report['source']['sha256'] = numeric
        self.bind_report(statement, report)
        self.write_signed(statement)
        with self.assertRaisesRegex(ValueError, 'source'):
            self.verify()

    def test_signed_source_coverage_fields_are_mandatory_and_typed(self):
        for field in ('files', 'skipped_count', 'ignored_and_external_inputs_unverified'):
            values = (None, False, 0, 'true') if field.endswith('unverified') else (None, True, -1, 0.0, '0')
            for value in values:
                with self.subTest(field=field, value=value):
                    statement = deepcopy(self.statement)
                    if value is None:
                        statement['predicate']['source'].pop(field)
                    else:
                        statement['predicate']['source'][field] = value
                    self.write_signed(statement)
                    with self.assertRaisesRegex(ValueError, 'source'):
                        self.verify()

    def test_missing_git_fields_are_not_implicit_nulls(self):
        for field in ('available', 'head', 'dirty'):
            with self.subTest(field=field):
                statement = deepcopy(self.statement)
                statement['predicate']['git'].pop(field)
                self.write_signed(statement)
                with self.assertRaisesRegex(ValueError, 'Git'):
                    self.verify()

    def test_git_availability_cannot_satisfy_clean_policy_by_truthiness(self):
        for value in ('false', 'true', 1, [False], {'available': False}):
            with self.subTest(value=value):
                statement = deepcopy(self.statement)
                statement['predicate']['git'] = {'available': value, 'head': None, 'dirty': False}
                self.write_signed(statement)
                with self.assertRaisesRegex(ValueError, 'Git'):
                    self.verify(require_clean=True)

    def test_git_claim_must_have_consistent_availability_head_and_dirty(self):
        for git in ({'available': True, 'head': None, 'dirty': False},
                    {'available': False, 'head': None, 'dirty': False},
                    {'available': False, 'head': 'a' * 40, 'dirty': None},
                    {'available': True, 'head': 'a' * 40, 'dirty': 0}):
            with self.subTest(git=git):
                statement = deepcopy(self.statement)
                report = deepcopy(self.report_value)
                statement['predicate']['git'] = git
                report['git'] = {'available': git['available'], 'head': git['head'], 'changed_paths': []}
                self.bind_report(statement, report)
                self.write_signed(statement)
                with self.assertRaisesRegex(ValueError, 'Git'):
                    self.verify()

    def test_clean_claim_cannot_contradict_signed_report_git_context(self):
        for report_git in ({'available': True, 'head': 'a' * 40, 'changed_paths': [' M app.py']},
                           {'available': False, 'head': 'a' * 40, 'changed_paths': []}):
            with self.subTest(report_git=report_git):
                statement = deepcopy(self.statement)
                report = deepcopy(self.report_value)
                statement['predicate']['git'] = {'available': True, 'head': 'a' * 40, 'dirty': False}
                report['git'] = report_git
                self.bind_report(statement, report)
                self.write_signed(statement)
                with self.assertRaisesRegex(ValueError, 'Git'):
                    self.verify(require_clean=True)

    def test_non_receipts_cannot_satisfy_isolated_policy(self):
        for value in (None, True, 'E1', [], {}):
            for require_isolated in (False, True):
                with self.subTest(value=value, require_isolated=require_isolated):
                    statement = deepcopy(self.statement)
                    statement['predicate']['isolated_receipts'] = [value]
                    self.write_signed(statement)
                    with self.assertRaisesRegex(ValueError, 'receipt'):
                        self.verify(require_isolated=require_isolated)

    def test_isolated_receipt_fields_are_mandatory_and_typed(self):
        malformed = {'id': ('', 1), 'origin': ('manual', None), 'status': ('fail', None),
                     'snapshot_sha256': ('a' * 128, int('1' * 64)),
                     'image_id': ('python:latest', 'sha512:' + 'a' * 128),
                     'snapshot_excluded_total': (True, 0.0, -1, '0')}
        for field, values in malformed.items():
            for value in (None, *values):
                with self.subTest(field=field, value=value):
                    receipt = self.receipt()
                    if value is None:
                        receipt.pop(field)
                    else:
                        receipt[field] = value
                    statement = deepcopy(self.statement)
                    statement['predicate']['isolated_receipts'] = [receipt]
                    self.write_signed(statement)
                    with self.assertRaisesRegex(ValueError, 'receipt'):
                        self.verify(require_isolated=True)

    def test_duplicate_isolated_identity_is_rejected(self):
        statement = deepcopy(self.statement)
        statement['predicate']['isolated_receipts'] = [self.receipt(), self.receipt()]
        self.write_signed(statement)
        with self.assertRaisesRegex(ValueError, 'receipt'):
            self.verify(require_isolated=True)

    def test_signed_receipt_count_boundary(self):
        statement = deepcopy(self.statement)
        statement['predicate']['isolated_receipts'] = [
            {**self.receipt(), 'id': f'E{index}'} for index in range(100)]
        self.write_signed(statement)
        result = self.verify(require_isolated=True)
        self.assertEqual(result['isolated_receipts'], 100)
        self.assertFalse(result['code_correctness_proven'])
        statement['predicate']['isolated_receipts'].append({**self.receipt(), 'id': 'E100'})
        self.write_signed(statement)
        with self.assertRaisesRegex(ValueError, 'receipt list'):
            self.verify(require_isolated=True)

    def test_ledger_summary_and_input_count_boundaries(self):
        rows = [{**self.ledger_run(), 'id': f'E{index}'} for index in range(2001)]
        statement = deepcopy(self.statement)
        statement['predicate']['isolated_receipts'] = [
            {**self.receipt(), 'id': row['id']} for row in rows[:100]]
        for count in (2000, 2001):
            with self.subTest(rows=count):
                core.write_json(self.ledger, {'schema': 1, 'runs': rows[:count]})
                statement['predicate']['ledger_sha256'] = attestation._digest(self.ledger.read_bytes())
                self.write_signed(statement)
                if count == 2000:
                    result = self.verify(ledger_path=self.ledger, require_isolated=True)
                    self.assertEqual(result['isolated_receipts'], 100)
                    self.assertFalse(result['code_correctness_proven'])
                else:
                    with self.assertRaisesRegex(ValueError, 'Invalid evidence ledger'):
                        self.verify(ledger_path=self.ledger)

    def test_summary_limit_does_not_hide_invalid_or_duplicate_ledger_rows(self):
        rows = [{**self.ledger_run(), 'id': f'E{index}'} for index in range(100)]
        statement = deepcopy(self.statement)
        statement['predicate']['isolated_receipts'] = [
            {**self.receipt(), 'id': row['id']} for row in rows]
        for tail in (rows[0], None, {'id': 101}):
            with self.subTest(tail=tail):
                core.write_json(self.ledger, {'schema': 1, 'runs': [*rows, tail]})
                statement['predicate']['ledger_sha256'] = attestation._digest(self.ledger.read_bytes())
                self.write_signed(statement)
                with self.assertRaisesRegex(ValueError, 'Invalid or duplicate evidence receipt'):
                    self.verify(ledger_path=self.ledger, require_isolated=True)

    def test_signer_does_not_promote_boolean_or_float_exit_code(self):
        for index, code in enumerate((False, 0.0)):
            with self.subTest(code=code):
                run = self.ledger_run()
                run['observed_exit_code'] = code
                core.write_json(self.ledger, {'schema': 1, 'runs': [run]})
                enhanced.save_report(self.root)
                out = self.root / '.raee' / f'invalid-exit-{index}.json'
                with self.assertRaisesRegex(ValueError, 'No matching successful isolated'):
                    attestation.create(self.root, self.private, out, allow_no_git=True, require_isolated=True)
                self.assertFalse(out.exists())

    def test_signer_does_not_promote_incomplete_isolation_metadata(self):
        for index, field in enumerate(('resolved_image_id', 'snapshot_sha256', 'snapshot_excluded_total')):
            with self.subTest(field=field):
                run = self.ledger_run()
                run['isolation'].pop(field)
                core.write_json(self.ledger, {'schema': 1, 'runs': [run]})
                enhanced.save_report(self.root)
                out = self.root / '.raee' / f'invalid-isolation-{index}.json'
                with self.assertRaisesRegex(ValueError, 'No matching successful isolated'):
                    attestation.create(self.root, self.private, out, allow_no_git=True, require_isolated=True)
                self.assertFalse(out.exists())

    def test_malformed_bound_report_source_raises_validation_error(self):
        for value in (None, [], True, 'source'):
            with self.subTest(value=value):
                statement = deepcopy(self.statement)
                report = deepcopy(self.report_value)
                report['source'] = value
                self.bind_report(statement, report)
                self.write_signed(statement)
                with self.assertRaisesRegex(ValueError, 'Report content'):
                    self.verify()


if __name__ == '__main__':
    unittest.main()
