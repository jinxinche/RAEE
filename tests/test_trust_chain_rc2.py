"""Regression tests for published provenance-chain defects (all local mocks)."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite.ci_attestation import require_safe_gh

ROOT = Path(__file__).resolve().parents[1]


class GhVersionBoundaryTests(unittest.TestCase):
    def _check(self, version: bytes, rc: int = 0):
        with patch('raee_lite.ci_attestation.subprocess.run', return_value=(
            subprocess.CompletedProcess(['gh', 'version'], rc, version, b'')
        )) as called:
            value = require_safe_gh('gh')
            self.assertEqual(called.call_args.args[0], ['gh', 'version'])
            self.assertEqual(called.call_args.kwargs.get('timeout'), 10)
            return value

    def test_patched_cli_accepted(self):
        self.assertEqual(self._check(b'gh version 2.97.0 (2026-07-31)\n'), (2,97,0))
        self.assertEqual(self._check(b'gh version 2.110.1 (2027-01-01)\n'), (2,110,1))

    def test_vulnerable_cli_rejected(self):
        for value in (b'gh version 2.96.9 (2026-07-01)\n', b'gh version 2.1.0\n'):
            with self.subTest(value=value):
                with patch('raee_lite.ci_attestation.subprocess.run', return_value=(
                    subprocess.CompletedProcess(['gh','version'], 0, value, b'')
                )):
                    with self.assertRaisesRegex(ValueError, 'Outdated'):
                        require_safe_gh('gh')

    def test_malformed_cli_rejected(self):
        for value in (b'', b'other version 3.0.0\n', b'gh version 2.97.0-rc1\n'):
            with self.subTest(value=value):
                with patch('raee_lite.ci_attestation.subprocess.run', return_value=(
                    subprocess.CompletedProcess(['gh','version'], 0, value, b'')
                )):
                    with self.assertRaises(ValueError):
                        require_safe_gh('gh')

    def test_failure_or_timeout_fails_closed(self):
        with patch('raee_lite.ci_attestation.subprocess.run', return_value=(
            subprocess.CompletedProcess(['gh','version'], 1, b'', b'error')
        )):
            with self.assertRaises(ValueError):
                require_safe_gh('gh')
        with patch('raee_lite.ci_attestation.subprocess.run', side_effect=subprocess.TimeoutExpired('gh',10)):
            with self.assertRaises(ValueError):
                require_safe_gh('gh')


class AttestationHandoffTests(unittest.TestCase):
    def test_handoff_has_strict_allowlist_and_raw_report(self):
        workflow = (ROOT / '.github/workflows/trusted-evidence.yml').read_text()
        self.assertIn('cp .raee/ci-evidence.json handoff/ci-evidence.json', workflow)
        self.assertIn('cp .raee/report.json handoff/report.json', workflow)
        self.assertIn('handoff/ci-evidence.json', workflow)
        self.assertIn('handoff/report.json', workflow)
        self.assertNotIn('path: .raee/', workflow)
        self.assertIn('signed/report.json', workflow)
        self.assertNotIn('include-hidden-files: true', workflow)

    def test_independent_verifier_checks_version_report_and_identity(self):
        script = (ROOT / 'scripts/verify_independent.sh').read_text()
        for marker in ('2.97.0', '--source-digest "$SHA"', '--signer-workflow',
                       '--source-ref refs/heads/main', '--report "$REPORT"',
                       'hashlib.sha256(data).hexdigest()'):
            self.assertIn(marker, script)


if __name__ == '__main__':
    unittest.main()
