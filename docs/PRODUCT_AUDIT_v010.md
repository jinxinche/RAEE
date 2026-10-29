# RAEE-Lite Product Audit — v0.10.0rc1

**Audit date:** 2026-10-29  
**Scope:** v0.9.1 inherited source plus v0.10.0rc1 modifications.  
**Goal:** turn an interesting research-idea CLI into a reliable, usable open-source developer product.  
**Important:** A code review and local tests cannot certify that a system is secure or the best in its category.  

## Summary

- **New:** read-only `preflight` with JSON output and bounded inspection; 14 targeted tests.
- **New:** `scripts/run_reviewed_suite.py` requires at least 150 discovered tests before running the trusted-main regression suite.
- **New:** trust-critical PR file changes include `.gitattributes`, `.gitmodules`, `pyproject.toml`.
- **Updated:** first-screen README; changelog; release quality gates.
- **Measured:** 177 unittest tests pass in ~32.4s on this machine; tests are local, not multi-OS cloud outcomes.
- **Independent package verification:** a newly created Python virtualenv installs the produced wheel, `raee-lite --version` prints `0.10.0rc1`, and installed CLI `preflight --json` completes.
- **Current static preflight of source:** `NO_STATIC_BLOCKERS_FOUND`, 0 blockers, 0 reviews, 1 info (no local evidence ledger). This must **not** be interpreted as cloud CI, security or branch-protection validation.

## Severity-ranked audit and decisions

| Priority | Surface | Risk / user pain | Current action | Remaining acceptance evidence |
|---|---|---|---|---|
| P0 | True GitHub provenance | A fabricated CI environment variable or unsigned JSON could appear credible | Original provenance checks preserved | Real `actions/attest` issued on protected main + independent `gh attestation verify` |
| P0 | Privileged PR code | Fork PR could access tokens via checkout, script install, or `workflow_run` artifacts | Existing read-only PR workflow retained; protected-file diff expanded | Real hostile fork tests; token and secret scope inspected |
| P0 | CI test weakness | Empty/shrunken test directory may still produce green results | Minimum 150 discovered tests gate | Test this on all hosted OS runners; review deliberate test weakening separately |
| P0 | Signed false claim | Signatures authenticate claims, not truth of tests | Warning preserved, no false trust promotion | Signed artifact's true workload and permissions independently checked |
| P0 | Raw agent log privacy | Prompts/terminal output may contain sensitive data | Importer stores coarse metadata only | External security/privacy review with consented logs and leaked-secret fixtures |
| P0 | Runner isolation | Docker socket / container breakout / untrusted scripts can compromise host | Opt-in Docker replay, no-network controls retained | Real rootless disposable runner and penetration testing |
| P0 | Real parser validity | Synthetic corpus is not representative | Reproducible synthetic corpus kept explicitly labelled | Consent-based versioned Codex/Claude corpus, held-out test |
| P0 | Evidence relevance accuracy | Current weak hints may be wrong | Manual confirmation retained | Independent ground-truth TP/FP/FN/TN estimates with uncertainty |
| P1 | First-use confusion | Huge multi-version README hid the simplest command | Short README and 60-second start | Independent developer usability tests |
| P1 | CI static mistakes | Unpinned Actions and overbroad token permissions can be overlooked | New static preflight warnings and blockers | Actions security review and CodeQL/Scorecard outside this CLI |
| P1 | Source snapshot limits | Excluded or over-budget files could hide changes | Explicit partial coverage markers retained | Real large-repo snapshots and symlink/race stress tests |
| P1 | No cross-platform proof | Hosted macOS/Windows may behave differently | Existing matrix configuration retained | Links to six GitHub Actions jobs (3 OS × 2 Python) |
| P1 | Large real transcripts | Event variety and long sessions may overwhelm parsing | Bounded streaming parser retained | 100MB–1GB real/consented workload with CPU/RSS/disk limits |
| P1 | Race-to-write attacks | Local filesystem may be mutated during evidence generation | Atomic evidence outputs retained | adversarial concurrency and filesystem tests |
| P1 | PR evidence identity | Reports from arbitrary commits might be compared | Explicit Base/Head SHA matching retained | PR workflow revalidation against canonical PR refs |
| P1 | Test weakening | `skip` and assertion removal can create fake confidence | Existing heuristic diff hints + minimum test-count check | False-positive calibration, test-level semantic analysis |
| P1 | Supply chain | Optional signing dependency versions are broadly specified | Existing trusted-main workflow uses minimal privileges | Reproducible locked dependencies, SBOM, vulnerability/secret scans |
| P1 | UX accessibility | HTML evidence dashboard may be inaccessible | Report interface retained | Keyboard, screen-reader, high-contrast and mobile tests |
| P2 | Onboarding | Users may not know which command is safe | README now distinguishes inspect/execute | 10 new users: time-to-first-report and failure rate |
| P2 | Documentation debt | Old version notes mixed into front page | Archive docs preserved; front page rewritten | Reduce duplicated docs and dead links |
| P2 | Contributor onboarding | Few real issues or outside contributions | Contributing and changelog retained | Public project issues, maintainer responsiveness measures |
| P2 | Product differentiation | Competitors already check Agent claims | Focus on role-aware contracts + evidence freshness + signed CI provenance | Test real users' preference over existing claim-checkers |

## Competitive positioning (not an exclusivity claim)

`backcheck` already audits Claude Code transcripts, test integrity and stale-green claims. `claimcheck` also independently checks assistant claims. RAEE-Lite should **not** market basic claim-to-transcript parsing as novel. Its testable differentiators must instead be:

1. Evidence **roles that cannot substitute for each other** (a passing lint command is not E2E proof).
2. A portable **requirement-to-verification contract** with explicit human review.
3. Base/Head **evidence state deltas** tied to source versions.
4. A cryptographically authenticated **trusted-CI receipt** with independently pinned workflow/repo/SHA, once it has actually been proven in GitHub.
5. A local-first, privacy-conscious design that does not send user logs to a model or SaaS backend.

These are product hypotheses until independent users find them valuable.

## Suggested independent v1 acceptance targets (NOT achieved metrics)

- Across real, consented logs from multiple Codex/Claude versions: >=95% format compatibility with unknown statuses explicitly retained (no invented success).
- For requirement/evidence suggestions: >=90% precision and <=5% false-positive rate on a held-out, independently annotated set; publish denominators and confidence intervals.
- Cross-platform: all supported Python versions × Windows/macOS/Linux hosted CI jobs green on the same reviewed commit.
- External provenance: at least one genuinely signed, publicly verifiable GitHub artifact that passes strict identity/SHA checks on a separate machine.
- Security: no credential exposure or execution of untrusted PR scripts in a privileged job in tested abuse scenarios; independent security review must enumerate residual risk.
- Usability: 10 unaffiliated developers, target median time to first useful report <=3 minutes and <=10% critical onboarding failures.
- Performance: measure P50/P95 wall time, RSS, peak disk and resource-ceiling rejection for a real corpus; do not reuse synthetic-only results as field evidence.

## Go/no-go decision

**GO:** distribute as **release candidate for testing**. Its source, tests, CLI and wheel are usable locally.  
**NO-GO:** claim production-security certification, proven multi-OS CI, a verified GitHub cloud-signed attestation, high real-world parser accuracy, or guaranteed 10,000 stars. Those statements remain unsupported.

## Source references

- GitHub secure use: https://docs.github.com/en/actions/reference/security/secure-use
- GitHub artifact attestations: https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations
- Official GitHub CLI verifier: https://cli.github.com/manual/gh_attestation_verify
- OpenSSF Scorecard: https://scorecard.dev/
- Existing alternatives: https://github.com/VectorInstitute/backcheck and https://github.com/ojuschugh1/claimcheck
