"""Produce a real, local OS/Python execution receipt and controlled hard negatives.

Invoked ONLY in a low-privilege, secret-free Actions job; no project-owned
scripts are executed except this reviewed benchmark code in disposable dirs.
"""
from __future__ import annotations
import argparse
import json
import os
import platform
import sys
import tempfile
from pathlib import Path

from raee_lite.core import init, add_requirement, run_check, get_manifest, write_json, MANIFEST, fingerprint
from raee_lite.contracts import set_expectation, assess_contracts
from raee_lite.evidence_binding import current_environment


def create_receipt() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app.py").write_text("def valid(x): return bool(x)\n", encoding="utf-8")
        (root / "test_app.py").write_text("assert 1 == 1\n", encoding="utf-8")
        init(root)
        rid = add_requirement(root, "Signup rejects invalid addresses")
        set_expectation(root, rid, "unit")
        receipt = run_check(root, rid, [sys.executable, "-c", "pass"], 15, kind="unit")
        env = current_environment()
        state = assess_contracts(root, fingerprint(root), target_environment=env)[0]["evidence_by_kind"][0]["state"]
        if state != "OBSERVED_PASS":
            raise RuntimeError("Local receipt was not bound to its actual OS/Python execution environment")
        # False positive: harmless, tracked note change triggers global source fingerprint revocation.
        (root / "NOTE.txt").write_text("An unrelated documentation note\n", encoding="utf-8")
        harmless = assess_contracts(root, fingerprint(root), target_environment=env)[0]["evidence_by_kind"][0]["state"]
        # False negative: an external dependency changes, but it was not fingerprinted.
        (root / "NOTE.txt").unlink()
        os.environ["RAEE_BENCH_EXTERNAL_REVISION"] = "changed-dependency-v2"
        external = assess_contracts(root, fingerprint(root), target_environment=env)[0]["evidence_by_kind"][0]["state"]
        os.environ.pop("RAEE_BENCH_EXTERNAL_REVISION", None)
        return {
            "schema": "raee.real_runner_receipt.v1",
            "platform": sys.platform,
            "python": platform.python_version(),
            "environment": env,
            "receipt_environment": receipt["environment"],
            "receipt_id": receipt["id"],
            "receipt_source_fingerprint": receipt["source_fingerprint"],
            "intent_digest_present": isinstance(receipt.get("requirement_digest"), str),
            "requirement_digest": receipt.get("requirement_digest"),
            "observed_exit_code": receipt["observed_exit_code"],
            "same_runner_state": state,
            "hard_negative_harmless_tracked_change": {
                "ground_truth_revoke": False,
                "observed_state": harmless,
                "predicted_revoke": harmless != "OBSERVED_PASS",
                "expected_note": "Potential false positive from coarse global source fingerprint",
            },
            "hard_positive_untracked_external_revision": {
                "ground_truth_revoke": True,
                "observed_state": external,
                "predicted_revoke": external != "OBSERVED_PASS",
                "expected_note": "Potential false negative because external state is outside fingerprint",
            },
            "limitations": [
                "A no-op passing check is not semantic validation.",
                "External dependency revision is a controlled environment-variable mutation, not a real package upgrade.",
                "Only the current job's OS/Python identity is authenticated by this workflow job metadata, not by the receipt itself.",
            ],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    value = create_receipt()
    output.write_text(json.dumps(value, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in value.items() if k not in ("limitations",)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
