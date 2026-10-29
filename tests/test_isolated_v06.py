"""Threat-focused tests use mocks for Docker; no host test ever launches a container."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite import core
from raee_lite.cli import main
from raee_lite.isolated import (stage_snapshot, build_docker_command, replay,
                                _docker_image_id, _require_local_daemon)

IMAGE_ID = 'sha256:' + 'a' * 64


class IsolatedV06Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        (self.root / 'test_example.py').write_text('import unittest\nclass Example(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n')
        core.init(self.root)
        core.add_requirement(self.root, 'Basic test')

    def tearDown(self):
        self.temp.cleanup()

    def test_snapshot_omits_secrets_and_symlinks_and_git(self):
        (self.root / '.env.production').write_text('API_KEY=SECRET')
        (self.root / '.aws').mkdir()
        (self.root / '.aws' / 'credentials').write_text('do-not-copy')
        (self.root / '.git').mkdir()
        (self.root / '.git' / 'config').write_text('do-not-copy')
        (self.root / 'linked').symlink_to(self.root / '.env.production')
        target = Path(self.temp.name) / 'copy'
        info = stage_snapshot(self.root, target)
        self.assertTrue((target / 'test_example.py').exists())
        self.assertFalse((target / '.env.production').exists())
        self.assertFalse((target / '.aws').exists())
        self.assertFalse((target / '.git').exists())
        self.assertFalse((target / 'linked').exists())
        self.assertGreaterEqual(info['unsafe_excluded_total'], 2)
        self.assertNotIn('SECRET', str(info))

    def test_snapshot_fail_closed_too_many_bytes(self):
        (self.root / 'huge.py').write_bytes(b'X' * (8 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, 'per-file limit'):
            stage_snapshot(self.root, Path(self.temp.name) / 'copy')

    def test_snapshot_is_deterministic(self):
        a = stage_snapshot(self.root, Path(self.temp.name) / 'a')
        b = stage_snapshot(self.root, Path(self.temp.name) / 'b')
        self.assertEqual(a['sha256'], b['sha256'])
        self.assertGreater(a['files'], 0)

    def test_dry_run_never_invokes_docker_or_writes_evidence(self):
        with patch('raee_lite.isolated._docker_image_id', side_effect=AssertionError('should not call Docker')):
            info = replay(self.root, 'R1', 'unit', ['python', '-m', 'unittest'], image='python:3.12-slim', dry_run=True)
        self.assertEqual(info['mode'], 'DRY_RUN_NOT_EXECUTED')
        self.assertEqual(core.read_json(self.root / core.LEDGER)['runs'], [])

    def test_dry_run_cli(self):
        with patch('raee_lite.isolated._docker_image_id', side_effect=AssertionError('should not call Docker')):
            self.assertEqual(main(['--project', str(self.root), 'isolate', '--for', 'R1', '--kind', 'unit',
                                   '--image', 'python:3.12-slim', '--dry-run', '--', 'python', '-m', 'unittest']), 0)

    def test_missing_docker_fails_closed(self):
        with patch('raee_lite.isolated.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'No local unsafe fallback'):
                replay(self.root, 'R1', 'unit', ['python'], image='python:3.12-slim')
        self.assertEqual(core.read_json(self.root / core.LEDGER)['runs'], [])

    def test_docker_run_minimal_permissions(self):
        cmd = build_docker_command('/usr/bin/docker', IMAGE_ID, Path('/tmp/snapshot'), 'raee-1234', ['python', '-V'])
        joined = ' '.join(cmd)
        for expected in ('--network=none', '--read-only', '--cap-drop=ALL',
                         '--security-opt=no-new-privileges:true', '--pull=never',
                         '--user 65532:65532', 'dst=/raee-input,readonly'):
            self.assertIn(expected, joined)
        for bad in ('--privileged', '--network=host', '/var/run/docker.sock', '--env-file'):
            self.assertNotIn(bad, joined)
        self.assertEqual(cmd[-2:], ['python', '-V'])
        self.assertEqual(cmd[cmd.index('--pull=never') + 1], '--network=none')

    def test_reject_invalid_image_resource_and_commands(self):
        for image in ('--privileged', 'x\nmalicious', ''):
            with self.assertRaises(ValueError):
                replay(self.root, 'R1', 'unit', ['python'], image=image, dry_run=True)
        with self.assertRaisesRegex(ValueError, 'Resource limits'):
            build_docker_command('docker', IMAGE_ID, Path('/tmp/s'), 'raee-x', ['python'], memory_mb=8192)
        with self.assertRaises(ValueError):
            build_docker_command('docker', IMAGE_ID, Path('/tmp/s'), 'raee-x', ['-v'])

    def test_refuses_remote_docker_host(self):
        with patch.dict(os.environ, {'DOCKER_HOST': 'tcp://example.com:2375'}):
            with self.assertRaisesRegex(ValueError, 'Remote Docker'):
                _require_local_daemon('docker')

    def test_refuses_remote_context(self):
        with patch.dict(os.environ, {'DOCKER_HOST': ''}):
            with patch('raee_lite.isolated.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '"ssh://remote"\n', '')):
                with self.assertRaisesRegex(ValueError, 'local Unix socket'):
                    _require_local_daemon('docker')

    def test_image_must_be_preinstalled(self):
        with patch('raee_lite.isolated.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', '')):
            with self.assertRaisesRegex(ValueError, 'not available locally'):
                _docker_image_id('docker', 'python:3.12-slim')

    def test_success_persists_environment_provenance(self):
        with patch('raee_lite.isolated.shutil.which', return_value=sys.executable), \
             patch('raee_lite.isolated._require_local_daemon'), \
             patch('raee_lite.isolated._docker_image_id', return_value=IMAGE_ID), \
             patch('raee_lite.isolated.bounded_run', return_value=(0, None, .4)) as runner, \
             patch('raee_lite.isolated.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            receipt = replay(self.root, 'R1', 'unit', ['python', '-m', 'unittest'], image='python:3.12-slim')
        self.assertEqual(receipt['observed_status'], 'pass')
        self.assertEqual(receipt['origin'], 'isolated_replay')
        self.assertEqual(receipt['isolation']['resolved_image_id'], IMAGE_ID)
        self.assertNotIn('python -m unittest', str(receipt))
        self.assertEqual(len(core.read_json(self.root / core.LEDGER)['runs']), 1)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(runner.call_args.kwargs['env'].get('CI'), None)

    def test_execution_failure_persists_failed_receipt(self):
        with patch('raee_lite.isolated.shutil.which', return_value=sys.executable), \
             patch('raee_lite.isolated._require_local_daemon'), \
             patch('raee_lite.isolated._docker_image_id', return_value=IMAGE_ID), \
             patch('raee_lite.isolated.bounded_run', return_value=(1, None, 0.1)), \
             patch('raee_lite.isolated.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            receipt = replay(self.root, 'R1', 'unit', ['python', '-m', 'unittest'], image='python:3.12-slim')
        self.assertEqual(receipt['observed_status'], 'fail')
        self.assertNotEqual(receipt['observed_exit_code'], 0)

    def test_timeout_not_passing(self):
        with patch('raee_lite.isolated.shutil.which', return_value=sys.executable), \
             patch('raee_lite.isolated._require_local_daemon'), \
             patch('raee_lite.isolated._docker_image_id', return_value=IMAGE_ID), \
             patch('raee_lite.isolated.bounded_run', return_value=(124, 'TimeoutExpired', 0.1)), \
             patch('raee_lite.isolated.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            receipt = replay(self.root, 'R1', 'unit', ['python', '-m', 'unittest'], image='python:3.12-slim')
        self.assertEqual(receipt['observed_status'], 'infrastructure_error')
        self.assertEqual(receipt['observed_exit_code'], 124)

    def test_require_declared_requirement(self):
        with self.assertRaisesRegex(ValueError, 'Unknown requirement'):
            replay(self.root, 'R999', 'unit', ['python'], image='python:3.12-slim', dry_run=True)

    def test_untrusted_metacharacters_are_argv_not_shell(self):
        marker = "'; touch /tmp/should-never-happen; #"
        args = build_docker_command('docker', IMAGE_ID, Path('/tmp/s'), 'raee-x',
                                    ['python', '-c', marker])
        self.assertEqual(args[-1], marker)
        self.assertEqual(args[args.index(IMAGE_ID) + 1], '-c')
        self.assertIn('exec "$@"', args[args.index(IMAGE_ID) + 2])

    def test_explicit_exclusions_make_receipt_partial(self):
        (self.root / '.env').write_text('SECRET=123')
        with patch('raee_lite.isolated.shutil.which', return_value=sys.executable), \
             patch('raee_lite.isolated._require_local_daemon'), \
             patch('raee_lite.isolated._docker_image_id', return_value=IMAGE_ID), \
             patch('raee_lite.isolated.bounded_run', return_value=(0, None, .1)), \
             patch('raee_lite.isolated.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            receipt = replay(self.root, 'R1', 'unit', ['python', '-V'], image='python:3.12-slim')
        self.assertTrue(receipt['files_skipped'])
        from raee_lite.enhanced import audit
        report = audit(self.root)
        self.assertEqual(report['requirements'][0]['state'], 'PARTIAL_COVERAGE')
        self.assertEqual(report['verification_provenance'][0]['origin'], 'isolated_replay')

    def test_dashboard_escapes_provenance_fields(self):
        from raee_lite.enhanced import audit, html_report
        report = audit(self.root)
        report['verification_provenance'] = [{
            'id': '<img src=x onerror=alert(1)>', 'origin': 'isolated_replay',
            'requirement': 'R1', 'declared_kind': 'unit',
            'observed_status': 'pass', 'isolation_policy': 'restricted_container_not_vm'}]
        page = html_report(report)
        self.assertNotIn('<img src=x onerror=alert(1)>', page)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', page)

    def test_ci_refuses_execution_without_opt_in(self):
        with patch.dict(os.environ, {'CI': 'true'}):
            with self.assertRaises(SystemExit) as x:
                main(['--project', str(self.root), 'isolate', '--for', 'R1', '--kind', 'unit',
                      '--image', 'python:3.12-slim', '--', 'python', '-V'])
        self.assertEqual(x.exception.code, 2)
        self.assertFalse(core.read_json(self.root / core.LEDGER)['runs'])


if __name__ == '__main__':
    unittest.main()
