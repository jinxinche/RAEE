"""Non-executing, non-promotional trace of self-declared evidence obligations.

A trace explains why a check receipt is missing, stale, failed or partial. It
never determines behavioral test adequacy or upgrades a user declaration to proof.
"""
from __future__ import annotations

from typing import Any


_REMEDY = {
    "MISSING": "Execute a relevant, explicitly labelled check in a trusted environment; review what it actually asserts.",
    "STALE": "Re-run the declared check against the current source snapshot and inspect its assertions.",
    "FAILED": "Investigate the nonzero check result; do not reuse an earlier passing receipt.",
    "PARTIAL": "Review unhashed inputs and fingerprint limits before relying on this receipt.",
    "INTENT_UNBOUND": "Re-run check with explicit intent binding; legacy evidence cannot prove unchanged requirement text.",
    "INTENT_CHANGED": "Requirement text changed; re-declare target and rerun check.",
    "ENVIRONMENT_UNBOUND": "Execution environment metadata missing; rerun in a known target environment.",
    "ENVIRONMENT_SHIFT_UNVERIFIED": "Receipt is from another Python/OS environment; validate on target runner.",
    "OBSERVED_PASS": "Review whether the self-declared check actually exercises the requirement; exit zero alone is insufficient.",
}


def trace(report: dict[str, Any], *, requirement_id: str | None = None) -> dict[str, Any]:
    """Build a bounded role-typed evidence graph from an existing read-only audit.

    Supports a maximum of the manifest's 500 requirements and 8 expected scopes
    each. All edges carry an explicit evidence-strength qualifier. The function
    has no filesystem, network, shell or model access.
    """
    requirements = report.get("requirements", [])
    contracts = {x["id"]: x for x in report.get("evidence_contracts", [])}
    if requirement_id and not any(r["id"] == requirement_id for r in requirements):
        raise ValueError(f"Unknown requirement: {requirement_id}")
    source = report.get("source", {})
    digest = source.get("sha256")
    snapshot_node = "source:current"
    result = []
    for req in requirements:
        rid = req["id"]
        if requirement_id and rid != requirement_id:
            continue
        contract = contracts.get(rid, {"status": "NO_CONTRACT", "evidence_by_kind": [], "gaps": []})
        observed = req["state"]
        nodes = [{"id": f"requirement:{rid}", "role": "intent", "label": req["requirement"],
                  "observed_check_state": observed},
                 {"id": snapshot_node, "role": "change", "sha256": digest,
                  "skipped_count": len(source.get("skipped", []))}]
        edges = []
        blockers = []
        for row in contract.get("evidence_by_kind", []):
            kind = row["kind"]
            state = row["state"]
            obligation = f"scope:{rid}:{kind}"
            nodes.append({"id": obligation, "role": "verification_obligation",
                          "kind": kind, "status": state, "authority": "USER_DECLARED_ONLY"})
            edges.append({"from": f"requirement:{rid}", "to": obligation,
                          "relation": "EXPECTED_ROLE_AS_DECLARED", "strength": "DECLARATION"})
            receipt_id = row.get("evidence_id")
            if receipt_id:
                receipt = f"receipt:{receipt_id}"
                nodes.append({"id": receipt, "role": "verification_receipt", "state": state,
                              "id_ref": receipt_id, "authority": "SELF_LABELLED_EXECUTION"})
                edges.append({"from": obligation, "to": receipt,
                              "relation": "MATCHED_BY_SELF_DECLARED_KIND", "strength": "PROCESS_OBSERVATION_ONLY"})
                if state == "OBSERVED_PASS":
                    edges.append({"from": receipt, "to": snapshot_node,
                                  "relation": "SOURCE_FINGERPRINT_MATCHES_CURRENT", "strength": "CONTENT_FRESHNESS_ONLY"})
            if state != "OBSERVED_PASS":
                blockers.append({"scope": kind, "state": state,
                                 "receipt_id": receipt_id,
                                 "next_step": _REMEDY.get(state, "Inspect the evidence record manually.")})
        if contract["status"] == "NO_CONTRACT":
            blockers.append({"scope": None, "state": "NO_CONTRACT", "receipt_id": None,
                             "next_step": f"Declare required evidence with `raee-lite expect --for {rid} --kind KIND`."})
        claim = "SELF_DECLARED_ROLE_RECEIPTS_ONLY" if contract["status"] == "RECORDED" else "UNVERIFIED_REQUIREMENT"
        warnings = ["A passing command, agent claim or user-labelled scope cannot establish semantic coverage."]
        if observed == "OBSERVED_PASS" and contract["status"] != "RECORDED":
            warnings.append("OBSERVED_PASS_WITHOUT_COMPLETE_ROLE_CONTRACT: an exit-zero receipt exists but obligations remain unresolved.")
        result.append({"requirement_id": rid, "requirement": req["requirement"],
                       "observed_state": observed, "contract_status": contract["status"],
                       "claim_strength": claim, "nodes": nodes, "edges": edges,
                       "unresolved_obligations": blockers, "warnings": warnings})
    return {"schema": "raee.proof_obligation_trace.v1", "source_fingerprint": digest,
            "read_only": True, "executed_project_code": False, "semantic_coverage_proven": False,
            "requirements": result,
            "interpretation": "The graph explains declared obligations and recorded process outcomes; it is not a proof of program correctness or test adequacy."}


def format_text(value: dict[str, Any]) -> str:
    lines = ["Proof-obligation trace (read-only; declarations are NOT coverage proofs)"]
    if not value["requirements"]:
        lines.append("No user requirements declared. Run `raee-lite add 'behavior'` first.")
    for item in value["requirements"]:
        lines.append(f"{item['requirement_id']}: {item['requirement']}")
        lines.append(f"  Claim strength: {item['claim_strength']} | Check state: {item['observed_state']}")
        for block in item["unresolved_obligations"]:
            lines.append(f"  GAP [{block['scope'] or 'contract'} / {block['state']}]: {block['next_step']}")
        if not item["unresolved_obligations"]:
            lines.append("  No missing declared role receipts. Their relevance and coverage still require human validation.")
        for warning in item["warnings"][1:]:
            lines.append("  WARNING: " + warning)
    lines.append("Never treat a green process exit or declared test scope as semantic proof.")
    return "\n".join(lines)
