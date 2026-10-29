"""Offline contract checks for the real runner matrix (not cloud execution)."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from raee_lite.evidence_binding import intent_digest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "real_matrix_aggregator", ROOT / "benchmarks" / "aggregate_real_matrix.py")
AGGREGATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AGGREGATOR)


def fake_receipt(os_name, py_version, *, fingerprint="same-fixture-sha"):
    environment = {"os": "os-identity-" + os_name,
                   "python": py_version}
    return {
        "schema": "raee.real_runner_receipt.v1",
        "platform": os_name,
        "python": py_version,
        "environment": environment,
        "receipt_environment": environment.copy(),
        "receipt_id": "E1",
        "receipt_source_fingerprint": fingerprint,
        "intent_digest_present": True,
        "requirement_digest": intent_digest("Signup rejects invalid addresses"),
        "observed_exit_code": 0,
        "same_runner_state": "OBSERVED_PASS",
        "hard_negative_harmless_tracked_change": {
            "ground_truth_revoke": False,
            "observed_state": "STALE",
            "predicted_revoke": True,
        },
        "hard_positive_untracked_external_revision": {
            "ground_truth_revoke": True,
            "observed_state": "OBSERVED_PASS",
            "predicted_revoke": False,
        }
    }


class RealMatrixContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def populate(self, *, missing=None, duplicate=False, bad_sha=False):
        identities = [(os_name, py) for os_name in ("linux", "win32", "darwin")
                      for py in ("3.10.16", "3.13.4")]
        for index, (os_name, py) in enumerate(identities):
            if index == missing:
                continue
            if duplicate and index == 5:
                os_name, py = identities[0]
            row = fake_receipt(os_name, py,
                               fingerprint="different" if bad_sha and index == 5 else "same-fixture-sha")
            folder = self.root / str(index)
            folder.mkdir()
            (folder / "receipt.json").write_text(json.dumps(row), encoding="utf-8")

    def test_six_unique_receipts_yield_48_expected_controls(self):
        self.populate()
        m = AGGREGATOR.summarize(self.root)
        self.assertEqual(m["n_runners"], 6)
        self.assertEqual(m["n_cases"], 48)
        self.assertEqual((m["TP"], m["FP"], m["TN"], m["FN"]), (30, 6, 6, 6))
        self.assertGreater(m["false_positive_rate"], 0)
        self.assertGreater(m["false_negative_rate"], 0)

    def test_missing_runner_is_not_silently_accepted(self):
        self.populate(missing=2)
        with self.assertRaisesRegex(ValueError, "exactly six"):
            AGGREGATOR.summarize(self.root)

    def test_duplicate_runner_identity_is_rejected(self):
        self.populate(duplicate=True)
        with self.assertRaisesRegex(ValueError, "Duplicate OS/Python"):
            AGGREGATOR.summarize(self.root)

    def test_nonidentical_source_snapshots_rejected(self):
        self.populate(bad_sha=True)
        with self.assertRaisesRegex(ValueError, "Different source snapshots"):
            AGGREGATOR.summarize(self.root)

    def test_runner_fixture_lf_bytes_are_explicit(self):
        source = (ROOT / "benchmarks" / "real_runner_receipt.py").read_text(encoding="utf-8")
        self.assertIn('write_bytes(b"def valid(x): return bool(x)\\n")', source)
        self.assertIn('write_bytes(b"assert 1 == 1\\n")', source)

    def test_workflow_mac_uses_stable_explicit_intel_image(self):
        workflow = (ROOT / ".github/workflows/experimental-real-os-matrix.yml").read_text(encoding="utf-8")
        self.assertIn("macos-15-intel", workflow)
        self.assertIn("architecture: x64", workflow)
        self.assertIn("fail-fast: false", workflow)
        self.assertNotIn("pull_request_target:", workflow)
        self.assertNotIn("id-token: write", workflow)
        self.assertNotIn("attestations: write", workflow)
        self.assertIn("Verify actual interpreter and architecture", workflow)
        self.assertIn("if: failure()", workflow)


if __name__ == "__main__":
    unittest.main()
