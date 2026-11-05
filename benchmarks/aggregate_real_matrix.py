"""Aggregate six independently executed real runner receipts; no synthetic OS labels."""
import argparse
import json
import re
from pathlib import Path

from raee_lite.evidence_binding import evaluate_binding, intent_digest

EXPECTED_IDENTITIES = {(os_name, version) for os_name in ("linux", "win32", "darwin")
                       for version in ("3.10", "3.13")}
OBSERVED_STATES = {"OBSERVED_PASS", "STALE", "FAILED_CHECK", "PARTIAL_COVERAGE", "UNTESTED",
                   "FAILED", "DEPENDENCY_SOURCE_CHANGED", "EXTERNAL_STATE_CHANGED",
                   "SCOPE_CONTEXT_REQUIRED", "SCOPE_DECLARATION_CHANGED", "SCOPE_INPUT_UNAVAILABLE",
                   "SCOPE_UNBOUND", "SCOPE_INCOMPLETE", "SCOPE_AUDIT_UNCERTAIN",
                   "INTENT_CHANGED", "ENVIRONMENT_SHIFT_UNVERIFIED"}


def _validate_receipt(row):
    if not isinstance(row, dict) or row.get("schema") != "raee.real_runner_receipt.v1":
        raise ValueError("Invalid runner receipt schema")
    version = row.get("python")
    if not isinstance(version, str) or not re.fullmatch(r"3\.\d+\.\d+", version):
        raise ValueError("Invalid Python identity")
    environment = row.get("environment")
    if (not isinstance(environment, dict) or environment.get("python") != version or
            not isinstance(environment.get("os"), str) or not environment["os"] or
            row.get("receipt_environment") != environment):
        raise ValueError("Inconsistent runner and receipt environment")
    if (row.get("same_runner_state") != "OBSERVED_PASS" or row.get("intent_digest_present") is not True or
            type(row.get("observed_exit_code")) is not int or row["observed_exit_code"] != 0 or
            row.get("requirement_digest") != intent_digest("Signup rejects invalid addresses")):
        raise ValueError("Unusable source receipt in matrix")
    if not isinstance(row.get("receipt_source_fingerprint"), str) or not row["receipt_source_fingerprint"]:
        raise ValueError("Missing source fingerprint")
    for key, expected in (("hard_negative_harmless_tracked_change", False),
                          ("hard_positive_untracked_external_revision", True)):
        case = row.get(key)
        if (not isinstance(case, dict) or case.get("ground_truth_revoke") is not expected or
                case.get("observed_state") not in OBSERVED_STATES or
                type(case.get("predicted_revoke")) is not bool or
                case["predicted_revoke"] != (case["observed_state"] != "OBSERVED_PASS")):
            raise ValueError("Invalid control label or outcome")
    return row["platform"], ".".join(version.split(".")[:2])

def ratio(n, d):
    return n / d if d else None

def summarize(root: Path) -> dict:
    paths = sorted(root.rglob("receipt.json"))
    if len(paths) != 6:
        raise ValueError(f"Required exactly six real runner receipts, found {len(paths)}")
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    identities = {_validate_receipt(r) for r in rows}
    if len(identities) != 6:
        raise ValueError("Duplicate OS/Python identities: expected 3 OS x 2 Python versions")
    if identities != EXPECTED_IDENTITIES:
        raise ValueError("Runner identities do not match the expected 3 OS x Python 3.10/3.13 matrix")
    if len({r["receipt_source_fingerprint"] for r in rows}) != 1:
        raise ValueError("Different source snapshots; cannot attribute environment transfer")
    checks = []
    for source in rows:
        for target in rows:
            actual = (source["platform"], source["python"]) != (target["platform"], target["python"])
            # Uses real recorded receipt environment from source and real executed target environment.
            state = evaluate_binding(
                {"requirement_digest": source["requirement_digest"],
                 "environment": source["receipt_environment"]},
                "Signup rejects invalid addresses", target_environment=target["environment"])
            predicted = state != "BINDING_MATCHED"
            checks.append({"source": source["platform"] + "/" + source["python"],
                           "target": target["platform"] + "/" + target["python"],
                           "state": state, "ground_truth_revoke": actual,
                           "predicted_revoke": predicted})
    for row in rows:
        for key in ("hard_negative_harmless_tracked_change", "hard_positive_untracked_external_revision"):
            observed = row[key]
            checks.append({"source": row["platform"] + "/" + row["python"], "target": key,
                           "state": observed["observed_state"],
                           "ground_truth_revoke": observed["ground_truth_revoke"],
                           "predicted_revoke": observed["predicted_revoke"]})
    tp = sum(x["ground_truth_revoke"] and x["predicted_revoke"] for x in checks)
    fp = sum(not x["ground_truth_revoke"] and x["predicted_revoke"] for x in checks)
    tn = sum(not x["ground_truth_revoke"] and not x["predicted_revoke"] for x in checks)
    fn = sum(x["ground_truth_revoke"] and not x["predicted_revoke"] for x in checks)
    # The same observed 48 comparisons under three policies, computed from
    # actual runner-local self-labelled receipts. No hard-coded classification.
    ablation = {}
    for mode in ("global", "scoped_files", "scoped_plus_external"):
        observations = [dict(case, policy=mode) for case in checks[:36]]
        safety_cases = []
        for row in rows:
            witness = row.get("ablation")
            if not isinstance(witness, dict) or witness.get("initial_scoped_state") != "OBSERVED_PASS":
                raise ValueError("Missing or invalid real-runner scoped ablation witness")
            for case_name in ("irrelevant_note_change", "external_revision_change",
                              "relevant_source_change"):
                case = witness.get(case_name)
                if not isinstance(case, dict) or mode not in case or type(case.get("ground_truth_revoke")) is not bool:
                    raise ValueError("Missing case outcome in a real-runner ablation receipt")
                if case["ground_truth_revoke"] != (case_name != "irrelevant_note_change"):
                    raise ValueError("Unexpected ground truth for controlled intervention")
                status = case[mode]
                if not isinstance(status, str) or status not in OBSERVED_STATES:
                    raise ValueError("Invalid scoped ablation status")
                entry = {"source": row["platform"] + "/" + row["python"],
                         "target": case_name, "state": status, "policy": mode,
                         "ground_truth_revoke": case["ground_truth_revoke"],
                         "predicted_revoke": status != "OBSERVED_PASS"}
                if case_name == "relevant_source_change":
                    safety_cases.append(entry)
                else:
                    observations.append(entry)
        if len(observations) != 48 or len(safety_cases) != 6:
            raise ValueError("Expected 48 matched ablation cases plus 6 safety controls")
        tp2 = sum(q["ground_truth_revoke"] and q["predicted_revoke"] for q in observations)
        fp2 = sum(not q["ground_truth_revoke"] and q["predicted_revoke"] for q in observations)
        tn2 = sum(not q["ground_truth_revoke"] and not q["predicted_revoke"] for q in observations)
        fn2 = sum(q["ground_truth_revoke"] and not q["predicted_revoke"] for q in observations)
        if any(not q["predicted_revoke"] for q in safety_cases):
            raise ValueError("Relevant source change was silently accepted by " + mode)
        ablation[mode] = {
            "n_matched_cases": 48, "TP": tp2, "FP": fp2, "TN": tn2, "FN": fn2,
            "precision": ratio(tp2, tp2+fp2),
            "recall": ratio(tp2, tp2+fn2),
            "false_positive_rate": ratio(fp2, fp2+tn2),
            "false_negative_rate": ratio(fn2, fn2+tp2),
            "relevant_source_safety_controls": len(safety_cases),
            "relevant_source_revoked": sum(q["predicted_revoke"] for q in safety_cases),
            "cases": observations,
        }
    return {"schema": "raee.real_cross_os_eval.v1",
            "n_runners": len(rows), "n_cases": len(checks),
            "ablation": ablation,
            "TP": tp, "FP": fp, "TN": tn, "FN": fn,
            "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
            "false_positive_rate": ratio(fp, fp + tn),
            "false_negative_rate": ratio(fn, fn + tp),
            "cases": checks,
            "limitations": [
                "OS/Python are real GitHub runner observations, but not an independently signed supply-chain attestation.",
                "Cross-platform transfers compare receipt applicability, not behavioral correctness.",
                "The two hard controls are synthetic file/ambient-environment interventions on real OS runners.",
                "Scoped dependency completeness is user-declared, not detected or proven by the tool.",
                "External versions are explicitly supplied nonsecret labels, not independently observed package identities.",
                "A no-op process receipt is not behavioral evidence of requirement satisfaction.",
                "Ground truth for migration is based on exact OS/Python identity, not adjudicated semantic equivalence.",
            ]}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = summarize(Path(args.input))
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2))

if __name__ == "__main__":
    main()
