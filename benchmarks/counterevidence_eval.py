"""Synthetic controlled counterevidence evaluation. Not real-world/OS generalization."""
import json
import sys
import tempfile
from pathlib import Path
from raee_lite.core import init, add_requirement, run_check, get_manifest, write_json, MANIFEST, LEDGER, read_json, fingerprint
from raee_lite.contracts import set_expectation, assess_contracts
from raee_lite.evidence_binding import current_environment

SCENARIOS = [
    ("same_environment", False), ("same_source", False),
    ("same_requirement", False), ("unrelated_ignored_file", False),
    ("test_weakened", True), ("application_modified", True),
    ("requirement_changed", True), ("environment_os_changed", True),
    ("environment_python_changed", True), ("missing_intent_binding", True),
    ("failed_new_receipt", True), ("additional_e2e_obligation", True),
]


def case(name):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "app.py").write_text("def validate(x): return bool(x)\n")
        (root / "test_app.py").write_text("assert 1 == 1\n")
        init(root)
        rid = add_requirement(root, "Signup rejects invalid addresses")
        set_expectation(root, rid, "unit")
        run_check(root, rid, [sys.executable, "-c", "pass"], 15, kind="unit")
        env = current_environment()
        if name == "test_weakened":
            (root / "test_app.py").write_text("assert True\n")
        elif name == "application_modified":
            (root / "app.py").write_text("def validate(x): return True\n")
        elif name == "requirement_changed":
            m = get_manifest(root)
            m["requirements"][0]["description"] = "Signup validates all domain names"
            write_json(root / MANIFEST, m)
        elif name == "environment_os_changed":
            env["os"] = "Windows-11-SYNTHETIC"
        elif name == "environment_python_changed":
            env["python"] = "3.10.0-SYNTHETIC"
        elif name == "missing_intent_binding":
            ledger = read_json(root / LEDGER)
            ledger["runs"][-1].pop("requirement_digest")
            write_json(root / LEDGER, ledger)
        elif name == "failed_new_receipt":
            run_check(root, rid, [sys.executable, "-c", "raise SystemExit(4)"], 15, kind="unit")
        elif name == "additional_e2e_obligation":
            set_expectation(root, rid, "e2e")
        elif name == "unrelated_ignored_file":
            (root / ".raee" / "ignored.txt").write_text("not application source")
        row = assess_contracts(root, fingerprint(root), target_environment=env)[0]
        return {"case": name, "contract_status": row["status"],
                "scope_states": [x["state"] for x in row["evidence_by_kind"]],
                "predicted_revoke": row["status"] != "RECORDED"}


def main():
    observations = []
    for name, truth in SCENARIOS:
        row = case(name)
        row["expected_revoke"] = truth
        observations.append(row)
    tp = sum(x["expected_revoke"] and x["predicted_revoke"] for x in observations)
    fp = sum(not x["expected_revoke"] and x["predicted_revoke"] for x in observations)
    tn = sum(not x["expected_revoke"] and not x["predicted_revoke"] for x in observations)
    fn = sum(x["expected_revoke"] and not x["predicted_revoke"] for x in observations)
    def div(a, b):
        return a / b if b else None
    result = {
        "dataset": "12 hand-authored synthetic controlled cases",
        "environment": "local Python execution; target OS/Python changes are simulated metadata",
        "TP": tp, "FP": fp, "TN": tn, "FN": fn,
        "precision": div(tp, tp + fp), "recall": div(tp, tp + fn),
        "false_positive_rate": div(fp, fp + tn),
        "false_negative_rate": div(fn, fn + tp),
        "scenarios": observations,
        "limitations": [
            "Scenario labels and expected outcomes are specified by test designer, not independent reviewers.",
            "No true Windows/macOS execution: target OS and Python shifts are metadata simulation only.",
            "Test weakening detection depends on a source fingerprint; it does not prove test adequacy.",
            "Ignored paths and external dependencies can remain outside the fingerprint.",
        ],
    }
    print(json.dumps(result, indent=2))
    return 0 if fp == 0 and fn == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
