"""Explicit verification contracts and conservative heuristic gap suggestions.

Contract types are user-defined metadata, never automatically inferred as proof.
Heuristics only propose additional checks; they do not satisfy or block CI.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import core
from .evidence_binding import evaluate_binding, valid_execution
from .dependency_scope import snapshot as scoped_snapshot, compare as compare_scoped
from .dependency_audit import audit_local_python_scope

KINDS = ("unit", "integration", "e2e", "typecheck", "lint", "build", "smoke", "security")

# Deliberately broad, non-exhaustive hints. A hint is NOT evidence of a flaw.
HINTS = (
    ("e2e", re.compile(r"\b(browser|click|page|ui|checkout|signup|sign[ -]?up|log[ -]?in|login|visual|front[ -]?end)\b", re.I),
     "The requirement mentions user-facing behavior; consider a browser or end-to-end check."),
    ("integration", re.compile(r"\b(api|database|db|endpoint|migration|webhook|payment|oauth|token|auth|register)\b", re.I),
     "The requirement may cross a service or persistence boundary; consider integration checks."),
    ("smoke", re.compile(r"\b(deploy|production|startup|start up|docker|container|installation|install)\b", re.I),
     "The requirement mentions environment-dependent behavior; consider a smoke check."),
    ("security", re.compile(r"\b(permission|secret|security|injection|encrypt|authorization|access control)\b", re.I),
     "The requirement may need security-specific review; passing unit tests is not sufficient."),
)


def set_expectation(root: Path, requirement_id: str, kind: str) -> dict:
    if kind not in KINDS:
        raise ValueError(f"Unknown kind: {kind}; choose one of {', '.join(KINDS)}")
    m = core.get_manifest(root)
    for req in m.get("requirements", []):
        if req.get("id") == requirement_id:
            current = list(req.get("expected_checks", []))
            if kind not in current:
                current.append(kind)
                req["expected_checks"] = sorted(current)
                core.write_json(root / core.MANIFEST, m)
            return req
    raise ValueError(f"Unknown requirement: {requirement_id}")


def suggestions(description: str) -> list[dict]:
    return [{"kind": kind, "reason": reason} for kind, pattern, reason in HINTS if pattern.search(description)]


def assess_contracts(root: Path, source: dict, *, target_environment: dict | None = None,
                     dependency_context: dict | None = None) -> list[dict]:
    manifest = core.get_manifest(root)
    ledger = core.read_json(root / core.LEDGER, {"schema": 1, "runs": []})
    runs = ledger.get("runs", [])
    result = []
    for req in manifest.get("requirements", []):
        rid = req["id"]
        expectations = list(dict.fromkeys(req.get("expected_checks", [])))
        gaps = []
        evidence_by_kind = []
        for kind in expectations:
            scope_audit = None
            matches = [r for r in runs if r.get("requirement") == rid and
                       r.get("origin") != "auto_discovered" and r.get("declared_kind") == kind]
            last = matches[-1] if matches else None
            if not last:
                status = "MISSING"
                gaps.append({"kind": kind, "reason": "No explicitly labelled check was executed for this role."})
            elif not valid_execution(last):
                status = 'INVALID_EVIDENCE'
                gaps.append({'kind': kind, 'reason': 'Receipt has no valid integer process exit code.'})
            elif 'dependency_scope' in last:
                # Explicit scoped receipts do NOT fall back silently to the
                # global fingerprint or assume the previously declared external
                # revision still applies in a new review environment.
                context = (dependency_context or {}).get(rid)
                if not isinstance(last['dependency_scope'], dict):
                    status = 'SCOPE_UNBOUND'
                elif not isinstance(context, dict):
                    status = "SCOPE_CONTEXT_REQUIRED"
                else:
                    binding = last["dependency_scope"]
                    if not isinstance(binding, dict) or not isinstance(binding.get("before"), dict):
                        status = "SCOPE_UNBOUND"
                    elif compare_scoped(binding["before"], binding.get("after")) != "DECLARED_INPUTS_MATCHED":
                        mismatch = compare_scoped(binding["before"], binding.get("after"))
                        status = mismatch if mismatch in ('SCOPE_UNBOUND', 'SCOPE_DECLARATION_CHANGED') else 'STALE'
                    else:
                        try:
                            current = scoped_snapshot(root, context["paths"], context.get("external_revisions"))
                            status = compare_scoped(binding["before"], current,
                                                    check_external=context.get("check_external", True))
                        except (ValueError, KeyError, TypeError):
                            status = "SCOPE_INPUT_UNAVAILABLE"
                    if status == "DECLARED_INPUTS_MATCHED":
                        status = evaluate_binding(last, req["description"],
                                                  target_environment=target_environment)
                        if status == "BINDING_MATCHED":
                            status = ("FAILED" if last.get("observed_exit_code") != 0
                                      else "OBSERVED_PASS")
                    if status == "OBSERVED_PASS":
                        try:
                            scope_audit = audit_local_python_scope(root, context["paths"])
                            history = [binding.get('audit_before'), binding.get('audit_after')]
                            if any(isinstance(item, dict) and item.get('missing_local_dependencies') for item in history):
                                status = 'SCOPE_INCOMPLETE'
                            elif any(not isinstance(item, dict) or item.get('schema') != 'raee.dependency_completeness_audit.v1'
                                     or item.get('limitations') or item.get('unresolved_project_imports') for item in history):
                                status = 'SCOPE_AUDIT_UNCERTAIN'
                            elif scope_audit["missing_local_dependencies"]:
                                status = "SCOPE_INCOMPLETE"
                            elif scope_audit["limitations"] or scope_audit["unresolved_project_imports"]:
                                status = "SCOPE_AUDIT_UNCERTAIN"
                        except (OSError, ValueError, TypeError, RecursionError):
                            status = "SCOPE_AUDIT_UNCERTAIN"
                if status != "OBSERVED_PASS":
                    gaps.append({"kind": kind, "reason":
                                 "Declared dependency inputs, intent, execution, or destination environment are not currently verified."})
            elif last.get("source_fingerprint") != source["sha256"] or last.get("source_fingerprint_after") != last.get("source_fingerprint"):
                status = "STALE"
                gaps.append({"kind": kind, "reason": "The last check does not match the current source snapshot."})
            elif evaluate_binding(last, req["description"], target_environment=target_environment) != "BINDING_MATCHED":
                status = evaluate_binding(last, req["description"], target_environment=target_environment)
                gaps.append({"kind": kind, "reason": "Evidence binding is absent, the requirement changed, or target environment is unverified."})
            elif last.get("observed_exit_code") != 0:
                status = "FAILED"
                gaps.append({"kind": kind, "reason": "The last check returned a nonzero exit code."})
            elif last.get("files_skipped") or source["skipped"]:
                status = "PARTIAL"
                gaps.append({"kind": kind, "reason": "The source fingerprint excludes some files."})
            else:
                status = "OBSERVED_PASS"
            row = {"kind": kind, "state": status, "evidence_id": last.get("id") if last else None,
                   "binding_kind": "declared_scope" if last and 'dependency_scope' in last else "global"}
            if scope_audit is not None:
                row["dependency_audit"] = scope_audit
            evidence_by_kind.append(row)
        result.append({
            "id": rid,
            "requirement": req["description"],
            "expected_checks": expectations,
            "status": "NO_CONTRACT" if not expectations else ("GAPS" if gaps else "RECORDED"),
            "evidence_by_kind": evidence_by_kind,
            "gaps": gaps,
            "suggestions": [h for h in suggestions(req["description"]) if h["kind"] not in expectations],
            "interpretation": (
                "RECORDED means a user-labelled command exited 0 against the current fingerprint. "
                "RAEE-Lite cannot prove that the command genuinely exercises its declared scope or satisfies the requirement."
            ),
        })
    return result


def has_contract_gaps(report: dict) -> bool:
    return any(x["status"] == "GAPS" for x in report.get("evidence_contracts", []))


def plan_text(report: dict) -> str:
    lines = ["Evidence gap plan (hints are not test adequacy claims):"]
    if not report.get("evidence_contracts"):
        return "No user-authored requirements. Use `raee-lite add 'what should work'`."
    for item in report["evidence_contracts"]:
        lines.append(f"  {item['id']}: {item['requirement']}")
        if item["status"] == "NO_CONTRACT":
            lines.append("    No explicit evidence contract. Declare one with `raee-lite expect --for " + item['id'] + " --kind KIND`.")
        elif item["status"] == "RECORDED":
            lines.append("    All explicitly requested scopes have observed passing command receipts (scope is self-declared).")
        for gap in item["gaps"]:
            lines.append(f"    GAP [{gap['kind']}]: {gap['reason']}")
        for hint in item["suggestions"]:
            lines.append(f"    HINT [{hint['kind']}]: {hint['reason']}")
    return "\n".join(lines)
