# Evidence integrity follow-up — 2026-11-06

This round builds on PR #14's first tested head,
`5d7662e61e2ccb75f2c0ae0e2a944bf8f85e0d67`. That revision passed 478 local
tests and its twelve hosted matrix jobs; those results do not validate later
changes. The [PR description and checks](https://github.com/jinxinche/RAEE/pull/14)
record validation for the current head.

Twenty focused tasks used a rolling queue with at most six agents at once.
Five unfinished tasks were restarted after a session interruption; their local
edits were preserved and reviewed. “Slurm” referred to this scheduling approach:
no cluster was configured, accessed or charged. Agent review is not independent
security certification.

## Priority repairs

| Priority | Reproduced problem | Resulting behavior |
|---|---|---|
| P0 | Concurrent edits replaced requirements, expected checks, imports or evidence links. | Cooperating writers share permanent per-store locks, reread inside the lock, and recheck identities/capacity. Initializers also coordinate with receipt writers. |
| P0 | A report could span different manifest/ledger/association versions and miss a newly appended failure. | Audits compare bounded input digests before and after construction and reject observed changes. Rendering errors occur before report replacement; report writers serialize. |
| P0 | Git returned success with an unreadable-directory warning, hiding a coverage gap. | Metadata capture can reject stderr without retaining its content. Inventory falls back to a bounded traversal that propagates unreadable-directory failures. |
| P0 | Incomplete or mismatched historical scope audits retained a scoped pass. | Before/after/current audits must explicitly match the declared paths and clean schema/status/fields. Missing imports and uncertainty retract applicability without rewriting historical receipts. |
| P0 | GitHub workflow-prefix matching admitted similar workflow names or refs. | Verification pins the exact certificate identity, issuer, signer/source digests, source ref and public GitHub host; returned statements must bind the exact manifest digest. |
| P1 | Offline verification parsed one file version and hashed another. | Reports, ledgers and manifests are parsed and hashed from the same captured bytes. Signed source/Git/receipt types and mandatory hashes are validated. |
| P1 | `*_test.py` could run zero unittest tests and return success. | Discovery uses the explicit pytest command for both common patterns; missing pytest fails. Unsupported package-manager declarations and linked indicators are not guessed into commands. |
| P1 | Trace/dashboard joins could imply completion despite contradictory or absent evidence. | Invalid identities, role/status conflicts, malformed display data and dangling links are rejected. Display truncation is explicit and expansion is bounded. |
| P1 | A missing PR-head outcome hid withdrawal of an earlier pass. | Missing/null outcomes count as withdrawal; existing underlying regressions are not double-counted. |
| P1 | New modules and teardown skips escaped parts of the regression policy; discovery errors left old successful summaries. | Every module needs an explicit minimum. Only exact platform-allowlisted skips are accepted, including cleanup holders. Summary success is invalidated before discovery. |
| P1 | PR scanner exclusions hid scripts/symlinks; unreadable directories silently disappeared. | Incremental traversal includes former cache/environment exclusions, counts directory entries, records link targets without traversing them, and propagates errors. Only the checkout's root real `.git` directory is exempt. |
| P2 | A passing module invocation concealed a broken installed console command. | Clean-wheel smoke exercises both entry points, their nonzero status exits, the packaged template and missing optional dependency behavior. |
| P2 | Small-file reads allocated against a much larger configured cap; identical log imports grew metadata. | Safe reads size allocation against the opened regular file and reject growth/metadata changes. Unchanged imports neither duplicate source metadata nor rewrite the store. |
| P2 | Repeated import resolution multiplied filesystem probes by every search root. | Per-audit positive/negative caches are bounded by 1,024 module names and 8,192 search-root units; exhaustion explicitly reports uncertainty. Cached paths are still checked before source reads. |
| P2 | Supplemental x64 workflows checked only version and pointer width. | Both supplemental guards reject ARM64 and wrong-width interpreters; executable guard regressions cover these cases. |

## Twenty task scopes

1. Association transactions and dangling references.
2. Transcript-import transactions and capacity races.
3. Dashboard escaping, bounded rendering and outcome consistency.
4. Obligation-trace identities, receipt roles and joins.
5. Discovery command selection and passive path boundaries.
6. Association-metric denominators and consent/input types.
7. Dependency namespace members, relative imports and aliases.
8. Process deadlines, interruption cleanup and stderr warnings.
9. Snapshot permissions, copy budgets and exclusions.
10. JSON writer ambiguity, encoding budgets and lock errors.
11. Command-digest and origin-specific receipt binding.
12. Declared scope and historical audit validation.
13. Offline envelopes, captured-byte verification and bounded receipt inventories.
14. GitHub verifier output and exact signer policy.
15. PR evidence comparison and withdrawn outcomes.
16. CLI input-error behavior and preview validation.
17. Wheel contents and installed module/console entry points.
18. Independent regression/PR-boundary/workflow-policy review.
19. Bounded resource and latency measurements.
20. Documentation claims, dependencies and validation attribution.

The coordinator integrated manifest transactions, optimistic audit consistency,
Git warning handling, regression controls and the final validation/publishing.

## Local validation and measurements

The integrated follow-up passed **741/741 tests across 54 registered modules**
on macOS ARM64 / Python 3.11.16, with no failures, errors or skips. This adds
263 tests to the first PR head. Synthetic corpus validation passed 6/6 cases;
the offline PR risk smoke passed 7/7. The final PR records hosted outcomes for
its exact commit, including actual platform-specific skip counts.

The resource fixtures below were measured locally before and after the focused
fixes. They are small synthetic observations, not independent benchmarks or
general speedup claims; the test gate asserts bounded operations and correctness,
not machine-specific latency thresholds.

| Fixture | Before | After |
|---|---:|---:|
| 64 declared script directories, repeated helper imports, median wall time | 8.910 s | 0.0136 s |
| 13-byte safe read with a 16 MB cap, traced Python allocation peak | 16.01 MB | 0.0101 MB |
| Duplicate 5,000-command log import, median wall time | 0.1374 s | 0.0775 s |

Repeated imports retain one identical source record and leave unchanged store
bytes/inode/mtime intact. No runtime dependency was added; the production import
inventory still matches the optional `cryptography>=42` signing extra.

## Compatibility and remaining boundaries

Keep permanent `.raee/*.lock` files while writers may be active. Locks coordinate
local CLI writers; manual edits, network-filesystem lock semantics and a hostile
filesystem owner are not validated. Before/after digest checks are optimistic
consistency checks, not atomic filesystem snapshots. Separate report formats are
not a transactional bundle for readers.

Old malformed receipts or dangling links may now require repair or rerunning the
original check. Do not manufacture missing evidence by editing historical
receipts. Self-declared links and imported transcripts never fulfill contracts.
Static dependency results remain advisory and do not establish dynamic/resource,
native-library, package or external-state closure.

The GitHub verifier policy follows the official
[CLI v2.97.0 policy implementation](https://github.com/cli/cli/blob/v2.97.0/pkg/cmd/attestation/verify/policy.go)
and [in-toto statement specification](https://github.com/in-toto/attestation/blob/v1.2.0/spec/v1/statement.md).
These tests use local simulated verifier responses. Real independent cloud
attestation verification, live main-branch protection, actual Docker isolation,
consented held-out transcripts and external review remain separate acceptance
work. Windows cleanup still terminates only the direct child.

Resource measurements use synthetic local fixtures and identify engineering
bottlenecks; they are not a general performance guarantee. AST limits apply
after parsing and are not hard process-memory isolation. Python 3.10 grammar
checks and dependency inventories complement, rather than replace, actual
per-platform test runs.
