# RAEE-Lite v0.10.0rc1 — Release Candidate Quality Gate

This is a **local engineering gate**, not an exhaustive security proof or a promise of 10,000 GitHub stars. Each claim requires reproducible evidence. Where the evidence is unavailable, record **NOT VERIFIED**, not PASS.

## P0: must pass before announcing a trusted production release

| Area | Gate | Evidence to retain | Current RC status |
|---|---|---|---|
| Real trusted GitHub CI | Protected main, independent reviewer, required checks | Repo ruleset/branch protection + run URLs | **NOT VERIFIED** (public candidate PRs; reviewed main integration pending) |
| GitHub origin proof | Real GitHub `actions/attest` on trusted workflow | Original artifact, verified bundle, run ID, signer workflow, full SHA | **NOT VERIFIED** |
| External verification | `gh attestation verify` with independently pinned expected identity | Clean environment, verifier version, output summary | **NOT VERIFIED** |
| Fork PR privilege boundary | Malicious fork attempts at workflow/symlink/CI artifacts, without secrets | Real failed/denied job URLs | **NOT VERIFIED** (local tests only) |
| Cross-platform testing | Linux/Windows/macOS, supported Python versions | Hosted CI matrix run URLs | Experimental baseline: [six jobs passed](https://github.com/jinxinche/RAEE/actions/runs/41235479143); expanded candidate matrix and protected-main acceptance require their own runs |
| Real agent log compatibility | Consent, versioned schema fixtures, blinded labels | Count of real sessions, success/fail/unknown, confidence intervals | **NOT VERIFIED** (synthetic fixtures only) |
| Real association accuracy | Independent labelling and held-out test set | TP/FP/FN/TN, Precision/Recall/FPR with CI | **NOT VERIFIED** (synthetic small sample only) |
| Isolated execution | Rootless/ephemeral Docker integration and negative tests | Actual Docker daemon results | **NOT VERIFIED** |
| Security review | Secret scan, PR-injection, path/permission and supply-chain audits | Independent security report and remediation record | **NOT VERIFIED** |

## P1: verified locally for this candidate

- Source tree is distributable as a Python package; test via a new virtual environment.
- Read-only `preflight` provides local heuristic CI configuration findings; it does not run scripts.
- Full-suite workflows refuse fewer than 268 discovered tests and use `--require-critical-modules` to enforce per-module minima for counterevidence, dependency, cross-OS, security, workflow policy and the gate's own negative controls. Collection errors, critical skips and critical expected failures fail the gate. Only four named symlink-privilege skips are allowed on Windows; their coverage must remain on POSIX runners.
- Experimental matrix summaries record discovered/executed/skipped/failed counts. A stable final check requires all matrix jobs to succeed; it can become a required check after reviewed integration. Counts and module minima cannot prove test quality or resist a malicious reviewer changing both tests and policy.
- Clean core-wheel installs are exercised outside the checkout without `cryptography`; full regression/signing collection installs the `attest` extra and runs `pip check`. The SPDX license metadata requires `setuptools>=77.0.3`, and the experiment checks this minimum build backend on Python 3.10.
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
