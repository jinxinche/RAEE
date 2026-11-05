# Changelog

## 2026-11-06 — Concurrent editing and evidence-validation follow-up

- Serialize manifest, transcript and association updates; reject reports spanning
  observed input changes. Unchanged transcript imports no longer grow the store.
- Reject Git warning omissions, malformed historical scope audits, contradictory
  receipt/report joins and withdrawn PR outcomes. Tighten exact signer identity,
  verified-result shape and captured-byte offline verification.
- Guard every test module, cleanup-phase skips and failed-discovery summaries.
  Inspect previously excluded PR paths, propagate traversal errors, and verify
  supplemental x64 guards. Installed-wheel smoke now exercises both CLI forms.
- Size safe reads against the opened file instead of reserving the configured
  cap for small documents. See the [follow-up audit](docs/ENGINEERING_FOLLOWUP_2026-11-06.md)
  for measured scope, compatibility and remaining acceptance work.

## 2026-11-05 engineering audit candidate (not separately released)

- Baseline: the earlier PR stack is merged into `main` at `5a8cc702674a5e4005f0efe3891b39727c5f7897`. [Main CI run 41978577201](https://github.com/jinxinche/RAEE/actions/runs/41978577201) passed all six OS/Python jobs with 268 tests per job; that result does not validate the new working candidate.
- Add regression tests for the reproduced evidence, parsing, signing, process and concurrency failures. Total and per-module minima are maintained centrally in `scripts/run_reviewed_suite.py`; contributor and workflow commands use the default minimum with `--require-critical-modules`, without a fixed `--min-tests` override.
- Expand `tests.yml` to twelve regression jobs by adding Ubuntu Python 3.11–3.14 and macOS ARM64 Python 3.10/3.15. The final matrix gate requires every job to pass; completed runs are recorded against the PR head in its Checks tab. Add the corpus CLI's `--require-exact` gate for mismatches and incomplete parsing.
- Keep dynamic-import function aliases uncertain, include declared script directories when resolving sibling imports, and retain execution-time scope audits so removing an omitted dependency cannot erase the historical incomplete-scope finding.
- Reject ambiguous JSON, including duplicate keys and non-finite values. Tighten agent-log provider selection and running-session handling so incomplete calls remain explicit.
- Serialize receipt appends across processes so a successful concurrent run cannot erase failed evidence. Reject unreadable traversal, bound empty directories and excluded entries, and retain only a bounded exclusion sample.
- Validate linked receipt states consistently and include unmet manual requirements in SARIF. PR comparisons preserve newly failed or newly missing required checks; the regression gate compares actual executed test identities with discovery.
- Pin reviewed Node 24 Action releases and exercise the declared signing/build lower bounds on Ubuntu Python 3.10.
- Parse and hash the same captured bytes for signing and reject input changes detected before signing. Pass a private read-only copy of the captured subject to the provenance verifier so replacement of the original path cannot change the verified input; this does not isolate the verifier from a hostile process with the same privileges.
- Retain partial key files after failed key generation for inspection; exclusive creation protects existing files and private files use restrictive permissions. Avoid cleanup by path that could delete another writer's replacement.
- See the [engineering audit](docs/ENGINEERING_AUDIT_2026-11-05.md) for scope and remaining acceptance work. This entry does not establish a merged PR, independently verified cloud provenance or production readiness.

## Candidate method addition (not separately released)

- Scoped evidence now rejects visible omitted imports (`SCOPE_INCOMPLETE`), uncertain audits (`SCOPE_AUDIT_UNCERTAIN`) and malformed digest records; traces label declared-input matches without implying a whole-repository match.
- Bound static traversal by file count, bytes and AST nodes; include package initializers, refuse linked inputs and retain explicit limitations. Standalone reports do not mutate receipts or prove closure.
- Validate real-runner receipt identities, labels and status values before aggregation; historical ablation measurements remain tied to their original commit.
- Use centralized total and per-module minima plus skip/expected-failure checks; define twelve OS/Python/architecture regression jobs, a final matrix gate, test summaries and isolated wheel smoke checks. Fix optional test dependency installation and the setuptools build lower bound. See the dated entry above for the distinction between baseline CI results and revision-specific candidate verification.
- Added offline, read-only `raee-lite trace` with typed proof-obligation nodes/edges, explicit missing/stale/failed/partial causes, and no automatic promotion of self-declared checks into correctness proofs.
- New JSON trace schema `raee.proof_obligation_trace.v1` and focused negative-control tests. Candidate cross-platform CI and independent audit remain release gates.

## 0.10.0rc2 — Provenance verification and evidence handoff hardening

- Reject GitHub CLI versions earlier than 2.97.0 during attestation verification (CVE-2026-64655).
- Ensure official signing uses an explicit, non-hidden allowlisted handoff: `ci-evidence.json` plus original `report.json`.
- Independent verification requires the raw report and cross-checks its SHA-256; absent RAEE CLI, use a bounded local fallback.
- Changed/new symlink files and symlinked directories now require review on untrusted PRs.
- The trusted PR inspector fingerprints symlink **target text** so changing an existing file/directory link cannot pass as unchanged; directory symlinks also count toward the bounded inventory limit. Regression tests cover these cases; current integration and validation status is recorded in the dated entry above.
- Added negative version, file handoff and local adversarial PR smoke tests; no real cloud attestation or fork-run claim.

## 0.10.0rc1 — Quality & developer experience release candidate

- Added zero-execution `preflight` with optional JSON report and explicit limits.
- Added fail-closed minimum-test-count runner used on trusted-main CI.
- Expanded protected PR changes to include `.gitattributes`, `.gitmodules`, `pyproject.toml`.
- Restructured README for rapid onboarding; published explicit P0/P1/P2 release gates.
- Added adversarial and negative tests for preflight and test discovery.
- No new claims of independently verified cloud provenance, real-world compatibility or production security.

## 0.9.1

- GitHub-deployment candidate, signed CI template and read-only fork-PR boundary.
- Verified local regression suite, not real GitHub attestation.

## Earlier preview versions

See `docs/RELEASE_VALIDATION_v06.md` through `docs/RELEASE_VALIDATION_v09.md`, and the original version notes.
