# RAEE-Lite v0.9.0 — Release validation record

Date: 2026-10-29 · Build: local Linux / Python 3.13.5

## Verified now

- **156 / 156 individual tests passed**, run in separate modules: legacy v0.8 regression = 130; `test_validation_v09` = 16; `test_workflow_policy_v09` = 5; `test_association_metrics_v09` = 5. This is locally executed, not a GitHub-hosted matrix.
- Wheel built locally from v0.9.0 sources, installed offline in a clean Python virtual environment, and `raee-lite validate-corpus` executed successfully from the Wheel. Build was re-run after the final association module addition.
- Synthetic parser corpus: **6/6** exact labelled cases (3 Codex and 3 Claude Code examples); **0 real authorized sessions**. One unknown exit preserved as unknown. These examples do not establish external compatibility.
- Synthetic association labels: 24 candidate pairs; TP 8, FP 2, FN 5, TN 9; precision 0.8000 (Wilson 95% 0.4902–0.9433), recall 0.6154 (0.3552–0.8229), FPR 0.1818 (0.0514–0.4770). These are not real-world estimates.
- Streaming event parser synthetic benchmark: 5,000 events / 0.745 MB: 1.142 seconds, peak Python tracemalloc 10.31 MB. 20,000 events / 2.980 MB: 3.767 seconds, peak Python tracemalloc 41.32 MB. Reported runtime/allocations reflect this test machine only.
- Source tree benchmark: 2,000 files hashed 2,000; 0.214 seconds. 6,000 files caused intended partial coverage (5,000 processed, 1 skipped entry indicating truncation), 0.614 seconds. **Partial ≠ fully audited**.
- GitHub connector used to inspect owned repositories: **no dedicated RAEE-Lite repository**. Not possible to generate real OIDC/Sigstore artifact or enforce branch protection until it exists and applicable GitHub permissions are available.

## Not verified (must remain pending)

1. GitHub `actions/attest` successful signing of a real `ci-evidence.json` artifact from protected branch.
2. Independent `gh attestation verify` against that real artifact and pinned workflow/source SHA.
3. Real fork-PR abuse scenarios, PR status checks and real Windows/macOS cloud matrix runs.
4. Any representative authorized real Codex and Claude Code corpus.
5. Real requirement/test association labels and external annotation agreement.
6. Third-party security audit, Docker end-to-end isolation, and production readiness.

## Release naming

Call this package **v0.9 Validation Preview** rather than a security-certified release. Never use 6/6 synthetic format cases as a marketing claim of 100% real Codex/Claude compatibility. Never use a mocked `gh` CLI success as a real attestation.
