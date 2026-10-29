"""Role-aware v0.3 orchestration on top of the offline evidence ledger."""
from __future__ import annotations

import hashlib
import html
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from . import core
from .safe_io import write_text as atomic_text
from .safe_process import run as bounded_run
from .discovery import Check, discover, risk_signals
from .contracts import assess_contracts, has_contract_gaps
from .associations import build_associations

VERSION = "0.8.0"


def ensure_initialized(root: Path) -> bool:
    """Initialize on demand for zero-configuration flow; never overwrite existing data."""
    if (root / core.MANIFEST).exists():
        return False
    if (root / core.LEDGER).exists():
        raise ValueError("Existing ledger without manifest; refusing to overwrite")
    core.init(root)
    return True


def run_discovered(root: Path, check: Check, timeout: int = 120) -> dict:
    """Execute only after opt-in --run. Observed outcome is not a requirement proof."""
    core.get_manifest(root)
    if timeout <= 0:
        raise ValueError("Timeout must be positive")
    ledger = core.read_json(root / core.LEDGER, {"schema": 1, "runs": []})
    before = core.fingerprint(root)
    env = dict(os.environ)
    env["CI"] = "true"  # disable runner watch-mode; does NOT sandbox execution
    code, err, duration = bounded_run(check.command, root, timeout, env=env)
    stdout_hash = stderr_hash = None
    after = core.fingerprint(root)
    entry = {
        "id": f"E{len(ledger.get('runs', [])) + 1}",
        "role": "verification", "origin": "auto_discovered",
        "requirement": check.id, "check_kind": check.kind,
        "command": list(check.command), "observed_exit_code": code,
        "observed_status": "pass" if code == 0 else "fail",
        "timestamp": core.utcnow(),
        "duration_seconds": duration,
        "source_fingerprint": before["sha256"],
        "source_fingerprint_after": after["sha256"],
        "files_inspected": before["files"], "files_skipped": before["skipped"],
        "stdout_sha256": stdout_hash, "stderr_sha256": stderr_hash, "output_policy": "DISCARDED_NOT_STORED",
        "error": err,
        "environment": {"python": sys.version.split()[0], "os": platform.platform()},
        "change": core.git_context(root),
    }
    ledger.setdefault("runs", []).append(entry)
    core.write_json(root / core.LEDGER, ledger)
    return entry


def audit(root: Path) -> dict:
    """Produce evidence matrix with strict role separation.

    Discovered test executions NEVER satisfy user-authored acceptance requirements.
    """
    report = core.audit(root)
    report["version"] = VERSION
    report["git"] = core.git_context(root)
    ledger = core.read_json(root / core.LEDGER, {"schema": 1, "runs": []})
    checks, notes = discover(root)
    current = report["source"]
    auto = []
    for check in checks:
        matching = [e for e in ledger.get("runs", []) if
                    e.get("origin") == "auto_discovered" and
                    e.get("requirement") == check.id and
                    e.get("command") == list(check.command)]
        last = matching[-1] if matching else None
        if not last:
            state = "NOT_RUN"
        elif last["source_fingerprint"] != current["sha256"] or last.get("source_fingerprint_after") != last["source_fingerprint"]:
            state = "STALE"
        elif last.get("files_skipped") or current["skipped"]:
            state = "PARTIAL_COVERAGE" if last["observed_exit_code"] == 0 else "FAILED"
        elif last["observed_exit_code"] == 0:
            state = "OBSERVED_PASS"
        else:
            state = "FAILED"
        auto.append({**check.as_dict(), "state": state,
                     "evidence_id": last["id"] if last else None,
                     "exit_code": last["observed_exit_code"] if last else None})
    report["automatic_checks"] = auto
    report["evidence_contracts"] = assess_contracts(root, current)
    report["discovery_notes"] = notes
    report["review_signals"] = risk_signals(root)
    report["agent_evidence"] = build_associations(root, current)
    # Explicit provenance: a historical Agent observation, an unsandboxed local check,
    # and an isolated replay MUST remain separate in every report and in CI reviews.
    report["verification_provenance"] = [{
        "id": e.get("id"), "origin": e.get("origin", "local_explicit"),
        "requirement": e.get("requirement"), "declared_kind": e.get("declared_kind"),
        "observed_status": e.get("observed_status"),
        "exit_code": e.get("observed_exit_code"),
        "image_id": e.get("isolation", {}).get("resolved_image_id") if isinstance(e.get("isolation"), dict) else None,
        "snapshot_sha256": e.get("isolation", {}).get("snapshot_sha256") if isinstance(e.get("isolation"), dict) else None,
        "isolation_policy": e.get("isolation", {}).get("policy") if isinstance(e.get("isolation"), dict) else "none",
    } for e in ledger.get("runs", [])[-100:]]
    report["scope_notice"] = (
        "Auto-detected checks report process outcomes, not task completion. "
        "Evidence roles cannot substitute for one another. High-impact changes require review."
    )
    states = [c["state"] for c in auto]
    if "FAILED" in states:
        report["overall"] = "FAILED_CHECK"
    elif report["requirements"]:
        # User-declared requirements determine coverage. A generic 'npm test' pass
        # cannot automatically prove a user requirement such as 'login works'.
        pass
    elif states:
        if "STALE" in states:
            report["overall"] = "STALE_EVIDENCE"
        elif all(s == "OBSERVED_PASS" for s in states):
            report["overall"] = "AUTOCHECKS_PASSED_WITH_LIMITS"
        else:
            report["overall"] = "INSUFFICIENT_EVIDENCE"
    # An explicit evidence contract takes precedence over a generic green check.
    if has_contract_gaps(report) and report["overall"] not in ("FAILED_CHECK", "STALE_EVIDENCE"):
        report["overall"] = "EVIDENCE_GAPS"
    return report


def is_passing(report: dict, strict: bool = False) -> bool:
    if has_contract_gaps(report):
        return False
    if strict:
        return bool(report["requirements"]) and report["overall"] == "CHECKS_PASSED_WITH_LIMITS"
    return report["overall"] in ("CHECKS_PASSED_WITH_LIMITS", "AUTOCHECKS_PASSED_WITH_LIMITS")


def markdown(report: dict) -> str:
    def c(v) -> str:
        return html.escape(str(v), quote=True).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
    lines = ["# RAEE-Lite Evidence Report", "", f"**Outcome:** `{report['overall']}`", "",
             "The five roles are intent, change, verification, environment, and boundaries.", "",
             "## User-declared acceptance requirements", "",
             "| ID | Requirement | State | Evidence |", "|---|---|---|---|"]
    for r in report["requirements"]:
        lines.append(f"| {c(r['id'])} | {c(r['requirement'])} | `{c(r['state'])}` | {c(r['evidence_id'] or '—')} |")
    if not report["requirements"]:
        lines.append("| — | No user-authored requirements | `NOT_DECLARED` | — |")
    lines += ["", "## Explicit evidence contracts (self-declared scope)", "",
              "| Requirement | Expected scope | Observed state | Receipt |", "|---|---|---|---|"]
    for item in report.get("evidence_contracts", []):
        for entry in item["evidence_by_kind"]:
            lines.append(f"| {c(item['id'])} | {c(entry['kind'])} | `{c(entry['state'])}` | {c(entry['evidence_id'] or '—')} |")
        if not item["expected_checks"]:
            lines.append(f"| {c(item['id'])} | (none declared) | `NO_CONTRACT` | — |")
    if not report.get("evidence_contracts"):
        lines.append("| — | No requirements | `NOT_APPLICABLE` | — |")
    lines += ["", "**Important:** A scope label such as 'e2e' is user-provided metadata, not verified test coverage.", "",
              "## Suggested evidence gaps (heuristic only)", ""]
    for item in report.get("evidence_contracts", []):
        for gap in item["gaps"]:
            lines.append(f"- {c(item['id'])}: **{c(gap['kind'])}** — {c(gap['reason'])}")
        for hint in item["suggestions"]:
            lines.append(f"- {c(item['id'])} HINT {c(hint['kind'])}: {c(hint['reason'])}")
    lines += ["", "## Discovered checks (not acceptance proof)", "",
              "| Check | Command | State | Evidence |", "|---|---|---|---|"]
    for a in report["automatic_checks"]:
        lines.append(f"| {c(a['kind'])} | `{c(' '.join(a['command']))}` | `{c(a['state'])}` | {c(a['evidence_id'] or '—')} |")
    if not report["automatic_checks"]:
        lines.append("| — | No supported checks detected | `NOT_RUN` | — |")
    lines += ["", "## Agent transcript observations (unverified, unbound to current source)", "",
              "| ID | Provider | Command family | Exit-status recorded |", "|---|---|---|---|"]
    for obs in report.get("agent_evidence", {}).get("imported", []):
        lines.append(f"| {c(obs['id'])} | {c(obs['provider'])} | {c(obs['command_family'])} | {c(obs['log_status'])} |")
    if not report.get("agent_evidence", {}).get("imported"):
        lines.append("| — | No imported agent logs | — | — |")
    lines += ["", "## Verification provenance (last 100 checks)", "",
              "| Receipt | Origin | Requirement | Kind | Status | Isolation |",
              "|---|---|---|---|---|---|"]
    for rec in report.get("verification_provenance", []):
        lines.append(f"| {c(rec['id'])} | {c(rec['origin'])} | {c(rec['requirement'])} | "
                     f"{c(rec['declared_kind'])} | {c(rec['observed_status'])} | {c(rec['isolation_policy'])} |")
    if not report.get("verification_provenance"):
        lines.append("| — | No executed check receipts | — | — | — | — |")
    lines += ["", "## User-authored evidence associations (not coverage proof)", ""]
    for row in report.get("agent_evidence", {}).get("explicit", []):
        lines.append(f"- {c(row['requirement'])} ↔ {c(row['evidence_id'])}: {c(row['state'])} — {c(row['rationale'])}")
    for row in report.get("agent_evidence", {}).get("suggestions", []):
        lines.append(f"- HINT {c(row['requirement'])} ↔ {c(row['evidence_id'])}: {c(row['reason'])}")
    lines += ["", "## Review signals (heuristics, not security findings)", ""]
    for r in report["review_signals"]:
        lines.append(f"- **{c(r['reason'])}**: {c(', '.join(r['paths']) or '—')}")
    if not report["review_signals"]:
        lines.append("- No high-impact changed paths detected. This does not prove safety.")
    lines += ["", "## Limits and unverified conditions", ""]
    for note in report["boundary_notes"] + report["discovery_notes"]:
        lines.append(f"- {c(note)}")
    if report["source"]["skipped"]:
        lines.append(f"- Fingerprint coverage incomplete: {len(report['source']['skipped'])} files skipped.")
    lines += ["", report["caveat"], "", report["scope_notice"], ""]
    return "\n".join(lines)


def html_report(report: dict) -> str:
    from .dashboard import render
    return render(report)


def save_report(root: Path, report: dict | None = None) -> dict:
    if report is None:
        report = audit(root)
    out = root / ".raee"
    out.mkdir(exist_ok=True)
    core.write_json(out / "report.json", report)
    atomic_text(out / "report.md", markdown(report))
    atomic_text(out / "report.html", html_report(report))
    from .sarif import sarif_report
    core.write_json(out / "report.sarif", sarif_report(report))
    return report


def github_step_summary(report: dict) -> None:
    """Append only when GitHub Actions supplies a local summary file path."""
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as fp:
            fp.write(markdown(report))
            fp.write("\n")
