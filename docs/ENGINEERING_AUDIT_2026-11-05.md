# Evidence integrity and regression audit — 2026-11-05

This audit records concrete engineering improvements and remaining verification
work. Passing tests are bounded evidence; they do not establish dependency closure,
hostile-host isolation, independent review, or production readiness.

## Baseline and execution

The earlier PR stack is merged at `5a8cc702674a5e4005f0efe3891b39727c5f7897`.
[Main run 41978577201](https://github.com/jinxinche/RAEE/actions/runs/41978577201)
passed its six OS/Python jobs with 268 tests each. This audit works from that
baseline. The new candidate is validated separately; historical runs do not prove
the new code.

Twenty focused agent tasks cover the areas below. The runtime permits six agents
at once, so tasks run in rolling batches. Their findings are reviewed and reproduced
before integration. All twenty review scopes completed. Agent review is not an independent security certification.

## Prioritized changes

| Priority | Area | Implemented behavior / acceptance criterion |
|---|---|---|
| P0 | Requirement identity | Changing requirement text invalidates the old receipt even without an explicit contract. |
| P0 | Environment binding | Missing or changed OS/Python environment cannot retain a passing interpretation; malformed environment fields are rejected. |
| P0 | Execution evidence | Boolean, float, string and missing exit codes cannot be treated as a successful integer exit code. |
| P0 | Scope and discovery | A scoped receipt requires its scope context and retains the execution-time audit; deleting an omitted dependency cannot restore a pass. Null scopes and changed declarations fail closed. An automatic check cannot satisfy a manual requirement through an identifier collision. |
| P0 | Negative evidence | A malformed or environment-invalidated automatic check blocks a passing aggregate even when a manual requirement still passes. |
| P0 | Concurrent receipts | Manual, automatic and isolated executions append under one bounded cross-process lock; IDs and capacity are checked after rereading the latest ledger, preserving other writers' failed checks. |
| P0 | Traversal | Unreadable directories are errors. Incremental traversal caps entries and directories before filtering; snapshot exclusion samples remain bounded while totals remain exact. |
| P0 | Missing imports | Dynamic-function aliases remain uncertain; declared script directories and regular `src` package initializers participate in the bounded graph. Dependency declarations are parsed as TOML, so commented requirements do not count. |
| P0 | File boundaries | JSON, key and report readers reject linked paths and nonregular files and enforce byte budgets; malformed JSON keys/constants fail closed. |
| P0 | Read-only Git | Inventory disables filesystem-monitor hooks; status/diff neutralize configured clean/process filters, and diff disables external diff and text conversion. Metadata output and wait time are bounded; truncated enumeration always marks coverage incomplete. |
| P0 | Test gate | Every test module has a minimum; duplicate identities, incomplete execution, collection errors and unexpected skips cannot produce a passing gate. |
| P1 | Corpus regression | Parser failures contribute false negatives and a failing exit status; `--require-exact` makes fixture mismatch a CI failure. |
| P1 | Report comparison | Requirement text keeps case-sensitive identity; duplicate roles and mismatched contract text are rejected. New failures and newly missing required checks remain regression signals. |
| P1 | Report formats | Associations validate execution/intent/environment binding; malformed auxiliary records fail closed; SARIF includes failed or unverified manual requirements. |
| P1 | Key creation | A failed key-pair write retains any partial file for inspection instead of unlinking a path that another writer might have replaced. Existing files remain protected by exclusive creation. |
| P1 | Matrix | Twelve hosted jobs cover Ubuntu Python 3.10–3.15, Windows and Intel macOS 3.10/3.15, and ARM macOS 3.10/3.15. |
| P1 | Packaging | Every matrix job builds and installs the core wheel outside the checkout; Ubuntu Python 3.10 checks setuptools 77.0.3 and cryptography 42.0.0 as lower-bound compatibility fixtures. Other jobs resolve current permitted versions. |
| P1 | Action runtime | Reviewed Node 24 action releases are pinned by full commit SHA, including workflow examples; artifact download fails on a digest mismatch by default. |
| P1 | Policy | Maintainer branch pushes provide PR-head test results. A checked-in policy alone does not enforce branch protection on GitHub. |
| P2 | Documentation | README, contribution steps and acceptance records distinguish completed integration from outstanding trust claims. |

## Twenty review scopes

1. Receipt intent and environment binding.
2. Contracts, negative evidence and withdrawal.
3. Dependency declaration completeness.
4. Dependency graphs and scope freshness.
5. Regular-file, path and JSON boundaries.
6. Agent-log parsing and incomplete calls.
7. Subprocess output, lifetime and platform behavior.
8. Signing, envelopes and key ownership.
9. CI provenance and trust-chain validation.
10. PR evidence comparison and association metrics.
11. Corpus evaluation and strict failure semantics.
12. Hosted OS/Python/architecture matrix.
13. Discovery and regression-gate integrity.
14. Package construction and isolated installation.
15. README, contributor instructions and changelog.
16. Historical audit and release acceptance records.
17. Branch-protection policy and its verifier.
18. CLI behavior and machine-readable errors.
19. Threat-model claims and practical boundaries.
20. Resource limits and concurrent updates.

## Validation record

The integrated candidate passed all 478 local tests on macOS ARM64 / Python
3.11.16 without skips. All 32 test modules have explicit minima. The PR description
and Checks tab record hosted outcomes for its exact head commit; a workflow
declaration is not a successful matrix run. Synthetic corpus validation covers
six cases, and the offline PR boundary smoke covers seven cases.

Local packaging built a core wheel and an sdist, rebuilt the wheel from that
sdist, and compared the unpacked wheel contents. Clean installation outside the
checkout exercises CLI entry points, the packaged template, `pip check`, and the
absence of the optional signing dependency. This does not establish bit-for-bit
archive reproducibility across independent hosts or toolchain versions.

The final check depends on every matrix job. Summary artifacts preserve discovered,
executed, skipped and failed counts. Platform-specific skip exceptions are named
in `scripts/run_reviewed_suite.py`; POSIX coverage must continue to execute.
The runner compares executed test identities with discovery, so repeating one
test cannot replace another while preserving the total count.

Action pins were resolved from official release tags and their `action.yml`
runtime declarations: [checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1),
[setup-python v7.1.0](https://github.com/actions/setup-python/releases/tag/v7.1.0),
[upload-artifact v7.0.2](https://github.com/actions/upload-artifact/releases/tag/v7.0.2),
and [download-artifact v8.0.2](https://github.com/actions/download-artifact/releases/tag/v8.0.2).
Their hosted execution must be checked against the candidate's actual run.

The historical failure was rechecked against actual job logs:
[41021206031](https://github.com/jinxinche/RAEE/actions/runs/41021206031)
had successful Ubuntu jobs, Windows `UnicodeEncodeError`, and macOS rejection of
symlinked temporary paths. UTF-8 streams and canonical runner-owned temporary
directories remain scoped to the regression step; no product path check was
weakened to hide the platform failure. Later invalid-workflow runs
`41235416141` and `41235417025` are historical failures, not new candidate results.

## Receipt compatibility

Older receipts lacking requirement/environment binding, consistent execution
metadata, or execution-time scope audits no longer inherit a passing verdict.
Rerun the relevant check and regenerate the report; do not edit a historical
receipt to manufacture the missing evidence. A declared scope with an omitted
dependency remains incomplete even if that dependency later disappears.

Ambiguous JSON and malformed imported-evidence shapes are errors. Duplicate log
call IDs cannot be paired reliably; retained incomplete calls remain unknown.
Imported transcripts still never satisfy verification contracts.

CI-origin verification checks the exact copied manifest bytes and exposes the
signed outcome and acceptance policy. It does not independently authenticate the
manifest's claimed run ID/attempt or establish that the latest run passed.

## Remaining strategies and their completion evidence

| Priority | Work | Evidence required before claiming completion |
|---|---|---|
| P0 | Enforce live main protection | Administrative application plus a readback of effective branch rules and required checks. Main was observed unprotected at the start of this audit. |
| P0 | Independently verify GitHub origin | Real signed artifact and bundle, pinned expected workflow/repository/ref identity, clean verifier output and matching full SHA. |
| P1 | Exercise actual isolation | A rootless/ephemeral Docker host running positive and adversarial cases, including process descendants and mount boundaries. Mocked Docker tests do not satisfy this. |
| P1 | Expand dependency evidence | Dynamic imports, runtime resources, build inputs, native libraries, transitive package identities and external state require distinct collection methods. Static audit remains advisory. |
| P1 | Bind richer environments | Explicit package/ABI/toolchain identities with defined portability policy; OS/Python binding alone cannot prove equivalent execution environments. |
| P1 | Broader concurrent editing | Ledger appends now serialize cooperating writers. Manifest, transcript-import and association edits still need an explicit multiwriter policy. Network-filesystem lock semantics and a hostile filesystem owner remain outside the validated boundary. Never delete the permanent ledger lockfile while a writer may be active. |
| P1 | Real-world parser and association evaluation | Consented, sanitized, versioned real sessions with independent labels and held-out cases; report errors and uncertainty, not only synthetic accuracy. |
| P2 | Release reproducibility | Compare independent wheel/sdist builds, verify archive contents and installation, retain hashes and provenance. Dependency bounds and a test matrix do not guarantee reproducibility. |
| P2 | Performance budgets | Measured large-repository/log fixtures, CPU/memory/latency baselines and meaningful regression thresholds before claiming speedups. |
| P2 | Independent usability/security review | External findings, fixes and reproduction records; self-review cannot satisfy independence. |

Further changes should target a reproducible failure or a measurable goal. Broad
rewrites, additional dependencies and reduced validation thresholds are not useful
substitutes for evidence.
