# Dependency Completeness Audit — Experimental Phase 2

This prototype performs bounded, read-only, static Python import traversal over declared project-relative files. It flags local imports reachable from declared Python entry files that are omitted from the declared scope. It **never proves closure**, executes user code, or observes package versions, runtime imports, data, services, build inputs or arbitrary external state.

## Integration and validation update — 2026-11-05

The earlier PR stack is merged into `main` at [`5a8cc702674a5e4005f0efe3891b39727c5f7897`](https://github.com/jinxinche/RAEE/commit/5a8cc702674a5e4005f0efe3891b39727c5f7897). [Main CI run 41978577201](https://github.com/jinxinche/RAEE/actions/runs/41978577201) passed all six OS/Python jobs, with 268 tests reported per job. Earlier experimental and ablation findings remain evidence for their original revisions; they do not validate the new candidate.

Candidate validation is tied to the exact PR head: consult its description and Checks tab for completed local and hosted results. The expanded matrix contains twelve jobs; workflow declarations alone do not establish success. Total and per-module minima live in [`scripts/run_reviewed_suite.py`](../scripts/run_reviewed_suite.py). See the [2026-11-05 engineering audit](ENGINEERING_AUDIT_2026-11-05.md) for changes and remaining acceptance work. A green matrix does not establish live branch protection, independent review or dependency closure.

## Evidence statuses
- `OMITTED_LOCAL_IMPORTS`: a resolved local Python import is outside the declared scope. The reported path is a candidate missing dependency, not proof that a given requirement behavior changed.
- `NO_STATIC_OMISSIONS_FOUND_UNPROVEN`: no omissions found under the bounded analyzer. **Not safe to interpret as complete**.
- `limitations`: dynamic import / execution, star imports, syntax failures, read restrictions, traversal cap, etc. require human review.

The standalone audit is advisory: it returns a report without changing or deleting receipts (`receipt_validity_changed=false`). Contract assessment now uses that report as a **negative gate** for otherwise passing, explicitly scoped receipts:

| Audit result | Current scoped evidence state |
|---|---|
| Visible omitted local dependency | `SCOPE_INCOMPLETE` |
| Dynamic imports, unresolved project imports, unreadable input, or a budget limit | `SCOPE_AUDIT_UNCERTAIN` |
| No Python entry files | `SCOPE_AUDIT_UNCERTAIN` |
| No detected omissions or limitations | Existing binding/intent/environment/execution checks still apply |

This changes current applicability, not the historical receipt. Failed checks and stale bindings retain their reasons. No automatic scope expansion or clean-audit promotion occurs; `dependency_completeness_proven` remains false. Earlier ablation results describe their original commit, not this revised policy.

## Example

```python
from pathlib import Path
from raee_lite.dependency_audit import audit_local_python_scope

report = audit_local_python_scope(Path("."), ["app.py", "test_app.py"])
print(report["status"], report["missing_local_dependencies"])
```

## Evaluation and next gates

The earlier evaluation recorded nineteen adversarial tests. The candidate expands coverage of direct/transitive omissions, package initializers and their imports, `src/` layouts, relative imports, attributes, aliased dynamic imports, non-execution, linked paths, and exhausted budgets; the central runner records the current module minimum. Traversal is limited to 128 files, 2 MB per file, 16 MB total and 100,000 AST nodes. Symlinked paths are rejected; this is not a general filesystem sandbox or a guarantee against hostile concurrent filesystem mutation.

Contract regressions verify that detected omissions/uncertainty block a scoped pass, malformed binding records fail closed, and scoped evidence is not drawn as a match against the whole repository. A separate inventory requires direct production third-party imports to remain declared in package metadata. Core-wheel smoke checks use a fresh environment outside the checkout without the optional `attest` dependency; the full suite installs `.[attest]`.

The candidate experiment defines twelve regression jobs: Linux Python 3.10–3.15; Windows and macOS Intel Python 3.10/3.15; macOS ARM64 Python 3.10/3.15. Each job is configured to check its actual interpreter/architecture, build and exercise a wheel, and use the central `MIN_TESTS` total derived from `REQUIRED_TEST_MODULES` with `--require-critical-modules`. A final `Dependency audit gate` requires every job to succeed. Each job is configured to preserve a JSON test summary for 14 days. These declarations are not completed hosted validation; candidate completion requires the actual run for the exact PR head. The separate historical receipt-ablation matrix remains Python 3.10/3.13 for reproducibility.

Windows exceptions are enumerated by exact test ID in `WINDOWS_CRITICAL_SKIPS`. The allowlist size is not an observed skip count: retain actual per-job summaries and logs. POSIX runners must execute the corresponding permission, FIFO and process-group coverage; the exception list does not authorize POSIX skips.

Next: independent real-repository labels; namespace packages, resource/data dependencies, setup/lock/build files; actual package upgrades and external service revisions. Quantify detected omissions against independently annotated closures, and track false alerts, unobserved dependencies, runtime cost and reviewer effort. Treat dynamic imports and unresolved cases as unknown. Do not use a clean static report to override an unsafe stale-evidence decision.
