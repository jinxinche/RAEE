"""SARIF v2.1.0 for opt-in CI consumption; no external services needed."""
from __future__ import annotations


def sarif_report(report: dict) -> dict:
    rules = {
        "RAEE001": ("Missing scoped evidence", "A user-declared requirement or evidence contract has a gap."),
        "RAEE002": ("Stale verification", "Evidence no longer matches the source snapshot."),
        "RAEE003": ("Failed verification", "An observed command failed."),
        "RAEE004": ("Suggested verification scope", "Heuristic suggestion, not a known defect."),
    }
    results = []
    covered = set()

    def append(rule: str, message: str, level: str = "warning") -> None:
        results.append({"ruleId": rule, "level": level, "message": {"text": message}})

    for item in report.get("evidence_contracts", []):
        receipts = {entry['kind']: entry.get('evidence_id') for entry in item.get('evidence_by_kind', [])}
        for gap in item["gaps"]:
            reason = gap["reason"]
            rule = "RAEE002" if "snapshot" in reason else "RAEE003" if "nonzero" in reason else "RAEE001"
            append(rule, f"{item['id']} expects {gap['kind']}: {reason}", "error" if rule == "RAEE003" else "warning")
            covered.add((item['id'], rule, receipts.get(gap['kind'])))
        for hint in item["suggestions"]:
            append("RAEE004", f"{item['id']}: {hint['reason']}", "note")
    for requirement in report.get('requirements', []):
        state = requirement['state']
        if state == 'OBSERVED_PASS':
            continue
        rule = 'RAEE003' if state == 'FAILED_CHECK' else 'RAEE002' if state == 'STALE' else 'RAEE001'
        key = (requirement['id'], rule, requirement.get('evidence_id'))
        if key not in covered:
            append(rule, f"Requirement '{requirement['id']}': {state} — {requirement['requirement']}",
                   'error' if rule == 'RAEE003' else 'warning')
            covered.add(key)
    for check in report.get("automatic_checks", []):
        if check["state"] == "FAILED":
            append("RAEE003", f"Discovered check '{check['id']}' failed.", "error")
        elif check["state"] == "STALE":
            append("RAEE002", f"Discovered check '{check['id']}' is stale.")
        elif check['state'] not in ('OBSERVED_PASS', 'NOT_RUN'):
            append('RAEE001', f"Discovered check '{check['id']}': {check['state']}.")
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
