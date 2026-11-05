# RAEE-Lite v0.10.0rc1 — Release Candidate Quality Gate

This is a **local engineering gate**, not an exhaustive security proof or a promise of 10,000 GitHub stars. Each claim requires reproducible evidence. Where the evidence is unavailable, record **NOT VERIFIED**, not PASS.

## Status update — 2026-11-05

The earlier PR stack is merged into `main` at [`5a8cc702674a5e4005f0efe3891b39727c5f7897`](https://github.com/jinxinche/RAEE/commit/5a8cc702674a5e4005f0efe3891b39727c5f7897). [Main CI run 41978577201](https://github.com/jinxinche/RAEE/actions/runs/41978577201) passed all six OS/Python jobs, with 268 tests reported per job. This supersedes the earlier main-integration-pending status. The earlier [experimental six-job run 41235479143](https://github.com/jinxinche/RAEE/actions/runs/41235479143) remains historical evidence for its own revision.

Candidate validation is tied to the exact PR head: consult its description and Checks tab for completed local and hosted results. The expanded matrix contains twelve jobs; workflow declarations alone do not establish success. Total and per-module minima live in [`scripts/run_reviewed_suite.py`](../scripts/run_reviewed_suite.py). See the [2026-11-05 engineering audit](ENGINEERING_AUDIT_2026-11-05.md) for changes and remaining acceptance work. A green matrix does not establish live branch protection, independent review or dependency closure.

## P0: must pass before announcing a trusted production release

| Area | Gate | Evidence to retain | Current RC status |
|---|---|---|---|
| Real trusted GitHub CI | Protected main, independent reviewer, required checks | Repo ruleset/branch protection + run URLs | **NOT VERIFIED** (earlier stack merged and baseline main CI passed; effective protection, required-check enforcement and independent review remain unverified) |
| GitHub origin proof | Real GitHub `actions/attest` on trusted workflow | Original artifact, verified bundle, run ID, signer workflow, full SHA | **NOT VERIFIED** |
| External verification | `gh attestation verify` with independently pinned expected identity | Clean environment, verifier version, output summary | **NOT VERIFIED** |
| Fork PR privilege boundary | Malicious fork attempts at workflow/symlink/CI artifacts, without secrets | Real failed/denied job URLs | **NOT VERIFIED** (local tests only) |
| Cross-platform testing | Linux/Windows/macOS, supported Python versions | Hosted CI matrix run URLs | Merged baseline: [six main jobs passed](https://github.com/jinxinche/RAEE/actions/runs/41978577201); candidate completion is recorded against the exact PR head in its Checks tab |
| Real agent log compatibility | Consent, versioned schema fixtures, blinded labels | Count of real sessions, success/fail/unknown, confidence intervals | **NOT VERIFIED** (synthetic fixtures only) |
| Real association accuracy | Independent labelling and held-out test set | TP/FP/FN/TN, Precision/Recall/FPR with CI | **NOT VERIFIED** (synthetic small sample only) |
| Isolated execution | Rootless/ephemeral Docker integration and negative tests | Actual Docker daemon results | **NOT VERIFIED** |
| Security review | Secret scan, PR-injection, path/permission and supply-chain audits | Independent security report and remediation record | **NOT VERIFIED** |

## P1: local checks and candidate gate policy

Local passing snapshots are bounded evidence for the code tested at that time. The final candidate needs its own completed run; workflow declarations alone do not verify hosted execution.

- Source tree is distributable as a Python package; test via a new virtual environment.
- Read-only `preflight` provides local heuristic CI configuration findings; it does not run scripts.
- Full-suite workflows use the central `MIN_TESTS` total, derived from `REQUIRED_TEST_MODULES` in [`scripts/run_reviewed_suite.py`](../scripts/run_reviewed_suite.py), and `--require-critical-modules` to enforce per-module minima. Collection errors, duplicate identities, incomplete execution, unapproved critical skips and critical expected failures fail the gate.
- Windows exceptions are enumerated by exact test ID in `WINDOWS_CRITICAL_SKIPS`. The allowlist size is not an observed skip count: retain actual per-job summaries and logs. POSIX runners must execute the corresponding permission, FIFO and process-group coverage; the exception list does not authorize POSIX skips.
- Candidate matrix workflows preserve discovered/executed/skipped/failed counts. A stable final check requires all matrix jobs to succeed; making it an enforced required check still needs GitHub configuration and readback. Counts and module minima cannot prove test quality or resist a malicious reviewer changing both tests and policy.
- Clean core-wheel installs are exercised outside the checkout without `cryptography`; full regression/signing collection installs the `attest` extra and runs `pip check`. The SPDX license metadata requires `setuptools>=77.0.3`. Ubuntu Python 3.10 runs the full suite with setuptools 77.0.3 and cryptography 42.0.0 as lower-bound compatibility fixtures; other jobs resolve current permitted versions.
- High-impact PR file guard also routes `.gitmodules`, `.gitattributes`, and `pyproject.toml` changes to review.
- `preflight` and the minimum-test runner have dedicated negative tests.
- No claims of live branch protection or GitHub OIDC trust arise from local mocks.

## P2: product adoption / UX

- First screen: setup under a minute, no account or cloud dependency.
- No red/green verdict without showing source, scope and limitations.
- Provide realistic sanitized fixtures and one copy-pasteable CLI demonstration per feature.
- Test usability with at least 10 **unaffiliated** developers; record time to first report and confusion points.
- Publish versioned changelog, compatibility table and open issues; no self-reported 100% field accuracy.
- Market only after real-user reproduction, with community-rule compliant announcements.

## Threat-review checklist

1. Input: symlinks, hardlinks, traversal, corrupt JSONL, oversized files, log nesting, Unicode, escape sequences.
2. Execution: untrusted hooks, postinstall scripts, `subprocess`, subprocess descendants, environment secrets, path races.
3. CI: `pull_request_target`, `workflow_run`, action pinning, write token, cache poisoning, unsafe artifacts, dependency substitution.
4. Integrity: stale source snapshots, cherry-pick/ref mismatch, signing key compromise, unsigned data, false green after test deletion.
5. Data privacy: raw prompts, logs, API keys, personal paths and telemetry; ensure no automatic upload.
6. Stability: 10k/100k/1m events, large repositories, Windows paths, interrupted writes, disk exhaustion.
7. User experience: false certainty, confusing state names, new-user setup, error messages, contrast and keyboard navigation.

## Release go/no-go

A local release candidate may be shared for review **only if** tests, packaging and reproducibility pass; it must be labelled RC. A **trusted CI product claim** is a separate milestone requiring all P0 cloud-provenance and security gates above. Never infer this status from local test totals.
