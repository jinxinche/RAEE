"""Offline signature tests. These do NOT establish execution authenticity."""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from raee_lite import core
from raee_lite.attestation import keygen, create, verify
from raee_lite.cli import main
from raee_lite.enhanced import save_report


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


class AttestationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'repository'
        self.root.mkdir()
        (self.root / '.gitignore').write_text('.raee/\n')
        (self.root / 'main.py').write_text('print("hello")\n')
        git(self.root, 'init', '-q')
        git(self.root, 'add', '.')
        git(self.root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'source')
        self.head = git(self.root, 'rev-parse', 'HEAD')
        core.init(self.root)
        core.add_requirement(self.root, 'Main script runs')
        save_report(self.root)
        self.private = self.base / 'keys' / 'secret.pem'
        self.public = self.base / 'keys' / 'pub.pem'
        self.att = self.root / '.raee' / 'attestation.dsse.json'
        self.report = self.root / '.raee' / 'report.json'
        self.ledger = self.root / '.raee' / 'ledger.json'
        self.manifest = self.root / '.raee' / 'manifest.json'
        keygen(self.private, self.public, self.root)

    def sign(self, **kwargs):
        return create(self.root, self.private, self.att, **kwargs)

    def check(self, **kwargs):
        return verify(self.root, self.att, self.public, self.report, **kwargs)

    def test_signature_validates_offline_and_current(self):
        result = self.sign()
        self.assertEqual(result['git_commit'], self.head)
        found = self.check(expected_commit=self.head, check_current=True,
                           ledger_path=self.ledger, manifest_path=self.manifest, require_clean=True)
        self.assertEqual(found['signature'], 'VALID')
        self.assertFalse(found['code_correctness_proven'])
        self.assertEqual(found['isolated_receipts'], 0)

    def test_private_key_stored_outside_repository_and_mode(self):
        self.assertFalse(self.private.is_relative_to(self.root))
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(self.private.stat().st_mode), 0o600)
        with self.assertRaisesRegex(ValueError, 'outside'):
            keygen(self.root / 'oops.pem', self.base / 'oops.pub', self.root)

    def test_keygen_refuses_overwrite_or_symlink(self):
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            keygen(self.private, self.public, self.root)
        path = self.base / 'malicious.pem'
        path.symlink_to(self.private)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            keygen(path, self.base / 'newpub.pem', self.root)

    def test_source_change_refuses_signing_stale_report(self):
        (self.root / 'main.py').write_text('print("modified")\n')
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            self.sign(allow_dirty=True)

    def test_modified_source_invalidates_check_current(self):
        self.sign()
        (self.root / 'main.py').write_text('print("modified")\n')
        # Offline signature remains valid for the originally signed artifact.
        self.assertEqual(self.check()['signature'], 'VALID')
        with self.assertRaisesRegex(ValueError, 'Current project sources differ'):
            self.check(check_current=True)

    def test_git_dirty_requires_opt_in(self):
        (self.root / 'extra.txt').write_text('untracked')
        save_report(self.root)
        with self.assertRaisesRegex(ValueError, 'dirty'):
            self.sign()
        self.sign(allow_dirty=True)
        with self.assertRaisesRegex(ValueError, 'clean Git'):
            self.check(require_clean=True)
        self.assertEqual(self.check()['signature'], 'VALID')

    def test_expected_commit_must_match(self):
        self.sign()
        with self.assertRaisesRegex(ValueError, 'expected Git'):
            self.check(expected_commit='a'*40)
        self.assertEqual(self.check(expected_commit=self.head)['signature'], 'VALID')

    def test_report_byte_tampering_detected(self):
        self.sign()
        self.report.write_bytes(self.report.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'report changed'):
            self.check()

    def test_ledger_and_manifest_tampering_detected_when_pinned(self):
        self.sign()
        self.ledger.write_bytes(self.ledger.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'Ledger digest'):
            self.check(ledger_path=self.ledger)
        self.ledger.write_bytes(self.ledger.read_bytes()[:-1])
        self.manifest.write_bytes(self.manifest.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'Manifest digest'):
            self.check(manifest_path=self.manifest)

    def test_attestation_payload_tamper_detected(self):
        self.sign()
        env = json.loads(self.att.read_text())
        payload = json.loads(base64.b64decode(env['payload']))
        payload['predicate']['report_overall'] = 'CHECKS_PASSED_WITH_LIMITS'
        env['payload'] = base64.b64encode(json.dumps(payload).encode()).decode()
        self.att.write_text(json.dumps(env))
        with self.assertRaisesRegex(ValueError, 'signature'):
            self.check()

    def test_attestation_signature_tamper_detected(self):
        self.sign()
        env = json.loads(self.att.read_text())
        env['signatures'][0]['sig'] = base64.b64encode(b'\x00'*64).decode()
        self.att.write_text(json.dumps(env))
        with self.assertRaisesRegex(ValueError, 'signature'):
            self.check()

    def test_wrong_trust_anchor_rejected(self):
        self.sign()
        other = self.base / 'other'
        keygen(other / 'priv.pem', other / 'pub.pem', self.root)
        with self.assertRaisesRegex(ValueError, 'independently trusted'):
            verify(self.root, self.att, other / 'pub.pem', self.report)

    def test_payload_type_substitution_rejected(self):
        self.sign()
        env = json.loads(self.att.read_text())
        env['payloadType'] = 'application/other+json'
        self.att.write_text(json.dumps(env))
        with self.assertRaisesRegex(ValueError, 'DSSE envelope'):
            self.check()

    def test_require_isolated_refuses_empty_ledger(self):
        with self.assertRaisesRegex(ValueError, 'No matching'):
            self.sign(require_isolated=True)
        self.sign()
        with self.assertRaisesRegex(ValueError, 'No isolated'):
            self.check(require_isolated=True)

    def test_matching_locally_recorded_isolated_receipt_is_only_assertion(self):
        ledger = core.read_json(self.ledger)
        sha = core.fingerprint(self.root)['sha256']
        ledger['runs'].append({'id':'E1','origin':'isolated_replay','requirement':'R1',
            'source_fingerprint':sha,'source_fingerprint_after':sha,
            'observed_status':'pass','observed_exit_code':0,'command':['[isolated command redacted]'],
            'isolation':{'backend':'docker','resolved_image_id':'sha256:' + 'c'*64,
                         'snapshot_sha256': 'a'*64,'snapshot_excluded_total':0}})
        core.write_json(self.ledger, ledger)
        save_report(self.root)
        self.sign(require_isolated=True)
        self.assertEqual(self.check(require_isolated=True, ledger_path=self.ledger)['isolated_receipts'], 1)

    def test_private_key_world_readable_rejected(self):
        if os.name != 'posix':
            self.skipTest('POSIX mode test')
        os.chmod(self.private, 0o644)
        with self.assertRaisesRegex(ValueError, '0600'):
            self.sign()

    def test_existing_attestation_cannot_be_overwritten(self):
        self.sign()
        with self.assertRaisesRegex(ValueError, 'exists'):
            self.sign()

    def test_source_partial_requires_explicit_opt_in(self):
        (self.root / 'big.dat').write_bytes(b'X' * (core.MAX_FILE_BYTES + 1))
        save_report(self.root)
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.sign(allow_dirty=True)
        self.sign(allow_dirty=True, allow_partial=True)
        self.assertEqual(self.check()['signature'], 'VALID')

    def test_no_git_requires_explicit_override(self):
        nogit = self.base / 'nogit'
        nogit.mkdir()
        (nogit / 'source.py').write_text('a=1\n')
        core.init(nogit)
        save_report(nogit)
        with self.assertRaisesRegex(ValueError, 'Git repository'):
            create(nogit, self.private, nogit / '.raee' / 'attestation.dsse.json')
        create(nogit, self.private, nogit / '.raee' / 'attestation.dsse.json', allow_no_git=True)
        self.assertEqual(verify(nogit, nogit / '.raee' / 'attestation.dsse.json', self.public,
                                nogit / '.raee' / 'report.json')['signature'], 'VALID')

    def test_cli_default_rejects_modified_ledger(self):
        self.sign()
        self.ledger.write_bytes(self.ledger.read_bytes() + b' ')
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exc:
                main(['--project', str(self.root), 'verify-attestation', '--public-key', str(self.public)])
        self.assertEqual(exc.exception.code, 2)

    def test_offline_verification_skips_ledger_but_not_report(self):
        self.sign()
        self.ledger.write_bytes(self.ledger.read_bytes() + b' ')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--project', str(self.root), 'verify-attestation', '--public-key',
                                   str(self.public), '--offline']), 0)

    def test_attestation_cli_end_to_end(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--project', str(self.root), 'attest', '--private-key', str(self.private)]), 0)
            self.assertEqual(main(['--project', str(self.root), 'verify-attestation',
                                   '--public-key', str(self.public), '--expected-commit', self.head,
                                   '--check-current', '--require-clean', '--ledger', '.raee/ledger.json',
                                   '--manifest', '.raee/manifest.json']), 0)


if __name__ == '__main__':
    unittest.main()
