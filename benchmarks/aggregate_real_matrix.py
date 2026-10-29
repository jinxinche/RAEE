"""Aggregate six independently executed real runner receipts; no synthetic OS labels."""
import argparse
import json
from pathlib import Path

from raee_lite.evidence_binding import evaluate_binding

def ratio(n, d):
    return n / d if d else None

def summarize(root: Path) -> dict:
    paths = sorted(root.rglob("receipt.json"))
    if len(paths) != 6:
        raise ValueError(f"Required exactly six real runner receipts, found {len(paths)}")
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    identities = {(r["platform"], r["python"]) for r in rows}
    if len(identities) != 6:
        raise ValueError("Duplicate OS/Python identities: expected 3 OS x 2 Python versions")
    if any(r.get("same_runner_state") != "OBSERVED_PASS" or not r.get("intent_digest_present")
           or r.get("observed_exit_code") != 0 for r in rows):
        raise ValueError("Unusable source receipt in matrix")
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
    return {"schema": "raee.real_cross_os_eval.v1",
            "n_runners": len(rows), "n_cases": len(checks),
            "TP": tp, "FP": fp, "TN": tn, "FN": fn,
            "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
            "false_positive_rate": ratio(fp, fp + tn),
            "false_negative_rate": ratio(fn, fn + tp),
            "cases": checks,
            "limitations": [
                "OS/Python are real GitHub runner observations, but not an independently signed supply-chain attestation.",
                "Cross-platform transfers compare receipt applicability, not behavioral correctness.",
                "The two hard controls are synthetic file/ambient-environment interventions on real OS runners.",
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
