# Dependency Completeness Audit — Experimental Phase 2

This prototype performs bounded, read-only, static Python import traversal over declared project-relative files. It flags local imports reachable from declared Python entry files that are omitted from the declared scope. It **never proves closure**, executes user code, or observes package versions, runtime imports, data, services, build inputs or arbitrary external state.

## Evidence statuses
- `OMITTED_LOCAL_IMPORTS`: a resolved local Python import is outside the declared scope. The reported path is a candidate missing dependency, not proof that a given requirement behavior changed.
- `NO_STATIC_OMISSIONS_FOUND_UNPROVEN`: no omissions found under the bounded analyzer. **Not safe to interpret as complete**.
- `limitations`: dynamic import / execution, star imports, syntax failures, read restrictions, traversal cap, etc. require human review.

The audit is advisory and does not alter contract assessment or evidence validity in this iteration. It does not reinterpret prior zero-FP/FN results. Never promote a 'clean' audit to independent safety certification.

## Example

```python
from pathlib import Path
from raee_lite.dependency_audit import audit_local_python_scope

report = audit_local_python_scope(Path("."), ["app.py", "test_app.py"])
print(report["status"], report["missing_local_dependencies"])
```

## Evaluation and next gates

Eight initial adversarial fixtures check direct omission, transitive omission, declared imports, unrelated changes, dynamic import uncertainty, non-execution of side effects, malformed source and relative package imports. The isolated six OS/Python jobs run both these fixtures and the full unmodified reviewed regression suite. Results must be inspected before claiming they passed.

Next: independent real-repository labels; imports via `src/` layouts, namespace packages, resource/data dependencies, setup/lock/build files; actual package upgrades and external service revisions. Quantify detected omissions against independently annotated closures, and track false alerts, unobserved dependencies, runtime cost and reviewer effort. Treat dynamic imports and unresolved cases as unknown. Do not use a clean static report to override an unsafe stale-evidence decision.
