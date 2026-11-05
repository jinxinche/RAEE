"""Deterministic signing races and malformed, genuinely signed payloads."""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

from raee_lite import attestation, core, enhanced


class SigningIntegrityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.root = self.base / 'project'
        self.root.mkdir()
        (self.root / 'app.py').write_text('pass\n', encoding='utf-8')
        core.init(self.root)
        core.add_requirement(self.root, 'Original requirement')
        enhanced.save_report(self.root)
        self.private, self.public = self.base / 'secret.pem', self.base / 'public.pem'
        attestation.keygen(self.private, self.public, self.root)
        self.envelope = self.root / '.raee/attestation.dsse.json'
        self.report = self.root / '.raee/report.json'
        self.ledger = self.root / '.raee/ledger.json'
        self.manifest = self.root / '.raee/manifest.json'
        self.inputs = (self.report, self.ledger, self.manifest)

    def sign(self):
        return attestation.create(self.root, self.private, self.envelope, allow_no_git=True)

    def verify(self):
        return attestation.verify(
            self.root, self.envelope, self.public, self.report,
            check_current=True, ledger_path=self.ledger, manifest_path=self.manifest)

    def resign_payload(self, payload):
        env = json.loads(self.envelope.read_bytes())
        key = attestation._load_private(self.private)
        env['payload'] = base64.b64encode(payload).decode('ascii')
        env['signatures'][0]['sig'] = base64.b64encode(
            key.sign(attestation._pae(attestation.TYPE.encode(), payload))).decode('ascii')
        self.envelope.write_text(json.dumps(env), encoding='utf-8')

    def test_signs_exact_captured_input_bytes(self):
        captured = {path: path.read_bytes() for path in self.inputs}
        self.sign()
        self.assertEqual(self.verify()['signature'], 'VALID')
        env = json.loads(self.envelope.read_bytes())
        predicate = json.loads(base64.b64decode(env['payload']))['predicate']
        for path in self.inputs:
            with self.subTest(input=path.name):
                self.assertEqual(predicate[path.stem + '_sha256'],
                                 hashlib.sha256(captured[path]).hexdigest())

    def test_input_change_before_audit_is_rejected(self):
        original_snapshot = attestation._valid_snapshot
        for path in self.inputs:
            with self.subTest(input=path.name):
                original = path.read_bytes()

                def snapshot_then_change(*args, **kwargs):
                    result = original_snapshot(*args, **kwargs)
                    path.write_bytes(original + b' ')
                    return result

                try:
                    with patch.object(attestation, '_valid_snapshot', side_effect=snapshot_then_change):
                        with self.assertRaisesRegex(ValueError, 'Evidence input changed during signing'):
                            self.sign()
                    self.assertFalse(self.envelope.exists())
                finally:
                    path.write_bytes(original)

    def test_input_change_after_audit_is_rejected(self):
        original_audit = enhanced.audit
        for path in self.inputs:
            with self.subTest(input=path.name):
                original = path.read_bytes()

                def audit_then_change(root):
                    result = original_audit(root)
                    path.write_bytes(original + b' ')
                    return result

                try:
                    with patch.object(enhanced, 'audit', side_effect=audit_then_change):
                        with self.assertRaisesRegex(ValueError, 'Evidence input changed during signing'):
                            self.sign()
                    self.assertFalse(self.envelope.exists())
                finally:
                    path.write_bytes(original)

    def test_manifest_requirement_added_during_audit_is_rejected(self):
        original_audit = enhanced.audit

        def audit_then_add_requirement(root):
            result = original_audit(root)
            core.add_requirement(root, 'Concurrent requirement absent from report')
            return result

        with patch.object(enhanced, 'audit', side_effect=audit_then_add_requirement):
            with self.assertRaisesRegex(ValueError, 'Evidence input changed during signing: manifest.json'):
                self.sign()
        self.assertFalse(self.envelope.exists())
        self.assertEqual(len(json.loads(self.report.read_bytes())['requirements']), 1)
        self.assertEqual(len(enhanced.audit(self.root)['requirements']), 2)

    def test_input_change_while_loading_key_is_rejected(self):
        original_load = attestation._load_private
        for path in self.inputs:
            with self.subTest(input=path.name):
                original = path.read_bytes()

                def load_then_change(key_path):
                    key = original_load(key_path)
                    path.write_bytes(original + b' ')
                    return key

                try:
                    with patch.object(attestation, '_load_private', side_effect=load_then_change):
                        with self.assertRaisesRegex(ValueError, 'Evidence input changed during signing'):
                            self.sign()
                    self.assertFalse(self.envelope.exists())
                finally:
                    path.write_bytes(original)

    def test_signed_duplicate_report_outcome_is_rejected(self):
        self.sign()
        env = json.loads(self.envelope.read_bytes())
        payload = base64.b64decode(env['payload'])
        duplicate = payload.replace(
            b'"report_overall":', b'"report_overall":"CONFLICTING_OUTCOME","report_overall":', 1)
        self.assertNotEqual(duplicate, payload)
        self.resign_payload(duplicate)
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON field'):
            self.verify()

    def test_signed_duplicate_predicate_is_rejected(self):
        self.sign()
        env = json.loads(self.envelope.read_bytes())
        payload = base64.b64decode(env['payload'])
        duplicate = payload.replace(b'"predicate":', b'"predicate":{},"predicate":', 1)
        self.assertNotEqual(duplicate, payload)
        self.resign_payload(duplicate)
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON field'):
            self.verify()

    def test_public_creation_collision_retains_private_and_other_public_file(self):
        private, public = self.base / 'new-secret.pem', self.base / 'new-public.pem'
        original_open = os.open

        def insert_public(path, flags, *args, **kwargs):
            if Path(path) == public:
                public.write_bytes(b'concurrent public file')
            return original_open(path, flags, *args, **kwargs)

        with patch.object(attestation.os, 'open', side_effect=insert_public):
            with self.assertRaises(FileExistsError):
                attestation.keygen(private, public, self.root)
        self.assertEqual(public.read_bytes(), b'concurrent public file')
        self.assertTrue(private.read_bytes().startswith(b'-----BEGIN PRIVATE KEY-----'))
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(private.stat().st_mode) & 0o077, 0)

    def test_partial_private_write_is_retained_with_secure_permissions(self):
        private, public = self.base / 'partial-secret.pem', self.base / 'partial-public.pem'
        original_fdopen = os.fdopen

        @contextmanager
        def partial_fdopen(fd, *args, **kwargs):
            with original_fdopen(fd, *args, **kwargs) as stream:
                writer = Mock(wraps=stream)

                def partial_write(data):
                    stream.write(data[:12])
                    raise OSError('simulated partial private-key write')

                writer.write.side_effect = partial_write
                yield writer

        with patch.object(attestation.os, 'fdopen', side_effect=partial_fdopen):
            with self.assertRaisesRegex(OSError, 'simulated partial private-key write'):
                attestation.keygen(private, public, self.root)
        self.assertEqual(private.read_bytes(), b'-----BEGIN P')
        self.assertFalse(public.exists())
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(private.stat().st_mode) & 0o077, 0)

    def test_failure_never_unlinks_a_path_after_checking_its_inode(self):
        private, public = self.base / 'race-secret.pem', self.base / 'race-public.pem'
        replacement = self.base / 'replacement.pem'
        replacement.write_bytes(b'concurrent replacement')
        original_open, original_lstat = os.open, Path.lstat
        state = {'failed': False, 'replaced': False}

        def fail_public(path, flags, *args, **kwargs):
            if Path(path) == public:
                state['failed'] = True
                raise OSError('simulated public-key creation failure')
            return original_open(path, flags, *args, **kwargs)

        def replace_after_cleanup_stat(path, *args, **kwargs):
            result = original_lstat(path, *args, **kwargs)
            if path == private and state['failed'] and not state['replaced']:
                os.replace(replacement, private)
                state['replaced'] = True
            return result

        with patch.object(attestation.os, 'open', side_effect=fail_public), \
                patch.object(Path, 'lstat', replace_after_cleanup_stat):
            with self.assertRaisesRegex(OSError, 'simulated public-key creation failure'):
                attestation.keygen(private, public, self.root)
        self.assertTrue(state['failed'])
        self.assertTrue(private.exists(), 'failure cleanup deleted the concurrent replacement')
        if state['replaced']:
            self.assertEqual(private.read_bytes(), b'concurrent replacement')
        else:
            self.assertTrue(private.read_bytes().startswith(b'-----BEGIN PRIVATE KEY-----'))


if __name__ == '__main__':
    unittest.main()
