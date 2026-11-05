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
from raee_lite.core import audit as global_audit


def create_receipt() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        # macOS's tempfile may return /var/folders/... where /var is a
        # system-managed symlink to /private/var. Resolve ONLY our own
        # unpredictable, already-created temporary directory before using
        # RAEE's intentionally strict no-symlink evidence writer.
        # Do not resolve user-selected repository paths or weaken safe_io.
        root = Path(tmp).resolve(strict=True)
        # Byte-exact LF fixtures are required: Python text-mode writes may
        # translate \n to CRLF on Windows, invalidating cross-OS SHA comparison.
        (root / "app.py").write_bytes(b"def valid(x): return bool(x)\n")
        (root / "test_app.py").write_bytes(b"assert 1 == 1\n")
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
        # Independent explicit scope receipt, generated on the *actual* runner.
        # This is a declaration of relevance, not a semantic test coverage proof.
        revisions_v1 = {"bench-service-revision": "v1"}
        scoped = run_check(root, rid, [sys.executable, "-c", "pass"], 15, kind="unit",
                           dependency_files=["app.py", "test_app.py"],
                           external_revisions=revisions_v1)
        def declared_state(revisions, *, check_external=True):
            context = {rid: {"paths": ["app.py", "test_app.py"],
                             "external_revisions": revisions,
                             "check_external": check_external}}
            return assess_contracts(root, fingerprint(root), target_environment=env,
                                    dependency_context=context)[0]["evidence_by_kind"][0]["state"]
        scoped_initial = declared_state(revisions_v1)
        if scoped_initial != "OBSERVED_PASS":
            raise RuntimeError("Actual scoped receipt failed local source and environment check")
        # Control A: irrelevant project note differs, but declared input files do not.
        (root / "NOTE.txt").write_bytes(b"unrelated note\\n")
        note_global = global_audit(root)["requirements"][0]["state"]
        note_scoped = declared_state(revisions_v1, check_external=False)
        note_combined = declared_state(revisions_v1)
        (root / "NOTE.txt").unlink()
        # Control B: a NONSECRET external revision label changed without
        # changing project files; no actual package installation is claimed.
        revisions_v2 = {"bench-service-revision": "v2"}
        external_global = global_audit(root)["requirements"][0]["state"]
        external_scoped = declared_state(revisions_v2, check_external=False)
        external_combined = declared_state(revisions_v2)
        # Hard safety control: modifying declared source MUST revoke.
        (root / "app.py").write_bytes(b"def valid(x): return True\\n")
        relevant_global = global_audit(root)["requirements"][0]["state"]
        relevant_scoped = declared_state(revisions_v1, check_external=False)
        relevant_combined = declared_state(revisions_v1)
        return {
            "schema": "raee.real_runner_receipt.v1",
            "platform": sys.platform,
            "python": platform.python_version(),
            "environment": env,
            "receipt_environment": receipt["environment"],
            "receipt_id": receipt["id"],
            "receipt_source_fingerprint": receipt["source_fingerprint"],
            "ablation": {
                "scope_receipt_id": scoped["id"],
                "scope_files": ["app.py", "test_app.py"],
                "external_revision_keys": ["bench-service-revision"],
                "initial_scoped_state": scoped_initial,
                "irrelevant_note_change": {
                    "ground_truth_revoke": False,
                    "global": note_global,
                    "scoped_files": note_scoped,
                    "scoped_plus_external": note_combined,
                },
                "external_revision_change": {
                    "ground_truth_revoke": True,
                    "global": external_global,
                    "scoped_files": external_scoped,
                    "scoped_plus_external": external_combined,
                },
                "relevant_source_change": {
                    "ground_truth_revoke": True,
                    "global": relevant_global,
                    "scoped_files": relevant_scoped,
                    "scoped_plus_external": relevant_combined,
                },
                "claim": "Completeness of declared dependency scope is not proven; a no-op is not a behavioral test.",
            },
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
