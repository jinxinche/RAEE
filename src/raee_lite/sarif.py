"""SARIF v2.1.0 for opt-in CI consumption; no external services needed."""
from __future__ import annotations


def sarif_report(report: dict) -> dict:
    rules = {
        "RAEE001": ("Missing scoped evidence", "A user-declared evidence contract has a gap."),
        "RAEE002": ("Stale verification", "Evidence no longer matches the source snapshot."),
        "RAEE003": ("Failed verification", "An observed command failed."),
        "RAEE004": ("Suggested verification scope", "Heuristic suggestion, not a known defect."),
    }
    results = []

    def append(rule: str, message: str, level: str = "warning") -> None:
        results.append({"ruleId": rule, "level": level, "message": {"text": message}})

    for item in report.get("evidence_contracts", []):
        for gap in item["gaps"]:
            reason = gap["reason"]
            rule = "RAEE002" if "snapshot" in reason else "RAEE003" if "nonzero" in reason else "RAEE001"
            append(rule, f"{item['id']} expects {gap['kind']}: {reason}", "error" if rule == "RAEE003" else "warning")
        for hint in item["suggestions"]:
            append("RAEE004", f"{item['id']}: {hint['reason']}", "note")
    for check in report.get("automatic_checks", []):
        if check["state"] == "FAILED":
            append("RAEE003", f"Discovered check '{check['id']}' failed.", "error")
        elif check["state"] == "STALE":
            append("RAEE002", f"Discovered check '{check['id']}' is stale.")
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{
            "tool": {"driver": {"name": "RAEE-Lite", "version": report["version"],
                "rules": [
                    {"id": rid, "name": name, "shortDescription": {"text": name},
                     "fullDescription": {"text": description}}
                    for rid, (name, description) in rules.items()
                ]}},
            "results": results,
        }],
    }
