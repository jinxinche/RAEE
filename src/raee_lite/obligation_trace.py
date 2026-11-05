"""Non-executing, non-promotional trace of self-declared evidence obligations.

A trace explains why a check receipt is missing, stale, failed or partial. It
never determines behavioral test adequacy or upgrades a user declaration to proof.
"""
from __future__ import annotations

from typing import Any

from .contracts import KINDS


_REMEDY = {
    "MISSING": "Execute a relevant, explicitly labelled check in a trusted environment; review what it actually asserts.",
    "STALE": "Re-run the declared check against the current source snapshot and inspect its assertions.",
    "FAILED": "Investigate the nonzero check result; do not reuse an earlier passing receipt.",
    "PARTIAL": "Review unhashed inputs and fingerprint limits before relying on this receipt.",
    "SCOPE_CONTEXT_REQUIRED": "Provide the current declared dependency paths and nonsecret external revisions; cannot implicitly reuse old labels.",
    "SCOPE_UNBOUND": "Old receipt lacks a scoped binding; rerun a scoped, explicitly labelled check.",
    "INVALID_EVIDENCE": "Repair the malformed receipt and rerun the check; exit codes must be integers.",
    "SCOPE_INCOMPLETE": "Include the omitted local dependencies and rerun the check with the reviewed scope.",
    "SCOPE_AUDIT_UNCERTAIN": "Resolve dynamic imports, unreadable inputs or audit limits before reusing this receipt.",
    "SCOPE_DECLARATION_CHANGED": "Declared dependency set changed; review scope and rerun against the new set.",
    "DEPENDENCY_SOURCE_CHANGED": "A declared requirement-relevant file changed; rerun the check.",
    "EXTERNAL_STATE_CHANGED": "A declared external version changed; rerun the check in the new context.",
    "SCOPE_INPUT_UNAVAILABLE": "A declared input is missing, unsafe, or cannot be fingerprinted; review before rerunning.",
    "INTENT_UNBOUND": "Re-run check with explicit intent binding; legacy evidence cannot prove unchanged requirement text.",
    "INTENT_CHANGED": "Requirement text changed; re-declare target and rerun check.",
    "ENVIRONMENT_UNBOUND": "Execution environment metadata missing; rerun in a known target environment.",
    "ENVIRONMENT_SHIFT_UNVERIFIED": "Receipt is from another Python/OS environment; validate on target runner.",
    "OBSERVED_PASS": "Review whether the self-declared check actually exercises the requirement; exit zero alone is insufficient.",
}


def _rows(value: Any, label: str, limit: int) -> list[dict]:
    if (not isinstance(value, list) or len(value) > limit
            or any(not isinstance(row, dict) for row in value)):
        raise ValueError(f"Invalid or oversized trace {label}")
    return value


def _validate_joins(report: dict) -> tuple[list[dict], dict[str, dict]]:
    """Reject ambiguous joins instead of drawing a complete-looking graph."""
    if not isinstance(report, dict):
        raise ValueError("Invalid trace report")
    requirements = _rows(report.get("requirements", []), "requirements", 500)
    by_id = {}
    owners = {}
    for req in requirements:
        rid = req.get("id")
        if (not isinstance(rid, str) or not rid or rid in by_id
                or not isinstance(req.get("requirement"), str)
                or not isinstance(req.get("state"), str) or not req["state"]):
            raise ValueError("Invalid or duplicate trace requirement identity")
        by_id[rid] = req

    provenance = {}
    for entry in _rows(report.get("verification_provenance", []), "provenance", 2000):
        receipt_id = entry.get("id")
        if not isinstance(receipt_id, str) or not receipt_id or receipt_id in provenance:
            raise ValueError("Invalid or duplicate trace receipt identity")
        provenance[receipt_id] = entry

    def join_receipt(receipt_id, rid, state, kind=None):
        if not isinstance(receipt_id, str) or not receipt_id:
            raise ValueError("Invalid trace receipt reference")
        if receipt_id in owners and owners[receipt_id] != rid:
            raise ValueError("Trace receipt belongs to another requirement")
        owners[receipt_id] = rid
        # Enhanced audits retain only the last 100 provenance rows. Absence
        # there cannot invalidate an older receipt; a conflicting row can.
        entry = provenance.get(receipt_id)
        if entry is not None:
            if (entry.get("requirement") != rid or entry.get("origin") == "auto_discovered"
                    or (kind is not None and entry.get("declared_kind") != kind)):
                raise ValueError("Trace receipt provenance does not match its declared role")
            if state == "OBSERVED_PASS" and (type(entry.get("exit_code")) is not int
                    or entry["exit_code"] != 0 or entry.get("observed_status") != "pass"):
                raise ValueError("Passing trace receipt contradicts execution provenance")

    for req in requirements:
        if req.get("evidence_id") is not None:
            join_receipt(req["evidence_id"], req["id"], req["state"])

    contracts = {}
    receipt_roles = {}
    for contract in _rows(report.get("evidence_contracts", []), "contracts", 500):
        rid = contract.get("id")
        if not isinstance(rid, str) or rid not in by_id or rid in contracts:
            raise ValueError("Unknown or duplicate trace contract requirement")
        if contract.get("requirement", by_id[rid]["requirement"]) != by_id[rid]["requirement"]:
            raise ValueError("Trace contract requirement text does not match its ID")
        expected = contract.get("expected_checks", [])
        if (not isinstance(expected, list) or len(expected) > len(KINDS)
                or any(not isinstance(kind, str) or kind not in KINDS for kind in expected)
                or len(set(expected)) != len(expected)):
            raise ValueError("Invalid trace contract roles")
        evidence = _rows(contract.get("evidence_by_kind", []), "role evidence", len(KINDS))
        kinds = [row.get("kind") for row in evidence]
        if (any(not isinstance(kind, str) for kind in kinds)
                or len(set(kinds)) != len(kinds) or set(kinds) != set(expected)):
            raise ValueError("Trace evidence roles do not match declared checks")
        for row in evidence:
            state, receipt_id = row.get("state"), row.get("evidence_id")
            if not isinstance(state, str) or not state:
                raise ValueError("Invalid trace evidence state")
            if row.get("binding_kind", "global") not in ("global", "declared_scope"):
                raise ValueError("Invalid trace evidence binding kind")
            if state == "MISSING":
                if receipt_id is not None:
                    raise ValueError("Missing trace evidence cannot reference a receipt")
            else:
                join_receipt(receipt_id, rid, state, row["kind"])
                if receipt_id in receipt_roles:
                    raise ValueError("Trace receipt cannot satisfy multiple declared roles")
                receipt_roles[receipt_id] = (rid, row["kind"])
        status = ("NO_CONTRACT" if not expected else
                  "RECORDED" if all(row["state"] == "OBSERVED_PASS" for row in evidence) else "GAPS")
        if contract.get("status") != status:
            raise ValueError("Trace contract status contradicts role evidence")
        contracts[rid] = contract
    return requirements, contracts


def trace(report: dict[str, Any], *, requirement_id: str | None = None) -> dict[str, Any]:
    """Build a bounded role-typed evidence graph from an existing read-only audit.

    Supports a maximum of the manifest's 500 requirements and 8 expected scopes
    each. All edges carry an explicit evidence-strength qualifier. The function
    has no filesystem, network, shell or model access.
    """
    requirements, contracts = _validate_joins(report)
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
                    if row.get("binding_kind") == "declared_scope":
                        scoped_node = f"source:declared:{rid}:{kind}"
                        nodes.append({"id": scoped_node, "role": "change",
                                      "declared_scope_only": True, "dependency_completeness_proven": False})
                        edges.append({"from": receipt, "to": scoped_node,
                                      "relation": "DECLARED_INPUTS_MATCH_CURRENT", "strength": "DECLARED_CONTENT_FRESHNESS_ONLY"})
                    else:
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
