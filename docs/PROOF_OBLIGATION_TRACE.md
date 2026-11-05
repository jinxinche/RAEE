# Proof-obligation trace: explain why green is not a proof

RAEE-Lite's read-only `trace` command addresses a specific problem: a terminal exit code, a self-declared test category and actual fulfillment of a user requirement are **different kinds of evidence**. The command builds an auditable, role-typed graph without executing project scripts, calling a model or changing project files.

## Example

In a disposable project, after installing the reviewed RC source:

```bash
raee-lite init
raee-lite add "Signup rejects invalid email addresses"
raee-lite run --for R1 -- python -c "pass"  # Explicit opt-in: demo runs a harmless no-op
raee-lite trace --for R1
raee-lite trace --for R1 --json
```

A passing no-op command is not semantic validation. With no declared evidence contract, `trace` reports `UNVERIFIED_REQUIREMENT`, shows `NO_CONTRACT` and the diagnostic `OBSERVED_PASS_WITHOUT_COMPLETE_ROLE_CONTRACT`. In contrast, regular `status` may report the command's `OBSERVED_PASS` (process outcome). These are not contradictions: they answer different questions.

Next declare a scope:

```bash
raee-lite expect --for R1 --kind unit
raee-lite trace --for R1 --json
```

Now `unit` remains `MISSING` because the earlier no-op receipt had no self-declared kind. Explicitly labeling and rerunning a command can change the result to `SELF_DECLARED_ROLE_RECEIPTS_ONLY`; it **still does not prove** the command asserts the required behavior.

## Graph semantics

- `requirement:R#` — intent, not implementation.
- `scope:R#:KIND` — a **user-declared** obligation. Edge `EXPECTED_ROLE_AS_DECLARED` carries declaration strength only.
- `receipt:E#` — a **self-labelled execution receipt**. Edge `MATCHED_BY_SELF_DECLARED_KIND` records a process-level association, not semantic relevance.
- `source:current` — current content fingerprint and count of skipped files. Edge `SOURCE_FINGERPRINT_MATCHES_CURRENT` is created only for a fresh `OBSERVED_PASS` scope. A stale, failed, partial or missing receipt **never** gets a current-source edge.

Unresolved obligations carry deterministic reason codes (`NO_CONTRACT`, `MISSING`, `STALE`, `FAILED`, `PARTIAL`) and a next action. These are workflow suggestions, not automated repair guarantees.

`trace` never scans for secrets, executes project code, or independently validates coverage. It intentionally has no `PROVEN` state. Imported agent transcripts and automatically discovered checks do not satisfy a user's explicitly declared check-kind contract.

## Method contribution and limits

This is a **proof-obligation trace** rather than a leaderboard accuracy claim. It separates (1) user intent, (2) declared verification roles, (3) observed execution, and (4) source-state relevance, while preserving the possibility that a green command is unrelated to the requirement. The novelty claim is specific to this implementation's explainable evidence graph; **no claim of being the first such idea** is made.

The structured `raee.proof_obligation_trace.v1` JSON supports downstream review and comparisons. It is an interpretation of the local evidence ledger and source fingerprint, not a cryptographic signature or official CI attestation. The tool is still an early RC; it has not completed independent security audit or the GitHub multi-platform signed-provenance acceptance flow.
