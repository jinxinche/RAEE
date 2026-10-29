# Dependency-Scoped Evidence Ablation (experimental)

**Status:** stacked research branch on PR #11 (which depends on PR #10 and PR #9). Not released. **No completeness or semantic-correctness claim.**

## Hypothesis and prior observed failures

The first real hosted-runner evaluation produced **48 controlled comparisons** (Ubuntu/Windows/macOS 15 Intel × Python 3.10/3.13). The baseline global fingerprint yielded **TP=30, FP=6, TN=6, FN=6**, with FPR 0.50 and FNR 0.1667. The six false withdrawals came from adding an unrelated source-tree note; the six misses arose when an explicitly *untracked* external revision label changed.

This experiment attempts to correct those two failures with explicit **per-requirement dependency declarations**. They are supplied by a human or trusted orchestration layer, **not** automatically discovered or guaranteed complete.

## Three paired, operationally distinct arms

1. **Global source fingerprint:** the existing RAEE global digest. It conservatively revokes an unrelated note change, but cannot see an external state variable outside the source tree.
2. **Declared source file scope:** SHA-256 of specified project-relative regular files, unchanged from the check receipt to its review. Only declared file changes invalidate. An external revision change is deliberately ignored in this ablation arm.
3. **Declared source scope + explicitly supplied external revision metadata:** in addition to selected source files, bind publicly shareable, nonsecret external version labels (e.g. `bench-service-revision=v1`) into the receipt. A different revision label invalidates it.

Each arm uses the *same* six real runner environments and identical local no-op checks. The experiment compares **36 ordered OS/Python identity transfers** plus two mutation controls on each runner (**6 irrelevant-note changes, 6 external-revision changes**), 48 paired observations per arm. Six additional relevant-source edits per arm are **hard safety controls** and must all revoke; they are reported separately to preserve exact comparability with the original 48.

The external revision is an explicitly supplied **synthetic metadata label**, not a package-manager lockfile proof, live package upgrade, network dependency attestation or implicit environment scan. Calling the arm "environment-aware" means *declared labels are compared*, not that the tool automatically discovers the environment.

### Previously observed control baseline

| Policy | TP | FP | TN | FN | FPR | FNR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original global digest (Run #8) | 30 | 6 | 6 | 6 | 0.50 | 0.1667 |

**The expected direction** is a reduction in FP in arm 2 and FN in arm 3. Any numerical result for the new arms must come from successful [experimental scoped-ablation CI](../.github/workflows/experimental-dependency-ablation.yml) logs and its uploaded artifact, **not from this hypothesis**.

## Scope contract

An opted-in Python call can use:

```python
run_check(
    project_root, "R1", [sys.executable, "-c", "pass"], 15,
    kind="unit",
    dependency_files=["app.py", "test_app.py"],
    external_revisions={"bench-service-revision": "v1"},
)
```

The returned receipt carries `dependency_scope.before` and `dependency_scope.after` digests (not source contents or raw external revision values). In the later review, a trusted caller must provide the **current** declaration:

```python
assess_contracts(
    project_root, fingerprint(project_root),
    target_environment=current_environment(),
    dependency_context={
        "R1": {
            "paths": ["app.py", "test_app.py"],
            "external_revisions": {"bench-service-revision": "v2"},
        }
    },
)
```

A changed external version returns `EXTERNAL_STATE_CHANGED`. Changed relevant source returns `DEPENDENCY_SOURCE_CHANGED`. Without current scope context, `SCOPE_CONTEXT_REQUIRED` fails closed. Altering the declared set returns `SCOPE_DECLARATION_CHANGED`. Missing, oversized, directory or symlinked input fails conservatively. A failed command is never upgraded to evidence of requirement correctness.

For ablation **only**, a comparison option `check_external=False` disables external label comparison and represents arm 2. Do **not** treat that mode as a safe way to ignore a dependency that matters to the application.

## Threat model and unaddressed false negatives

- A malicious or mistaken declaration can omit an actual dependency: an undeclared relevant file can change without invalidating the scoped receipt.
- An omitted external revision remains invisible; a declared revision can itself be dishonest or stale.
- SHA-256 of short nonsecret revision labels is not safe storage for credentials. **Do not supply secrets, tokens or sensitive identifiers.**
- A global source digest was a conservative approximation, not dependency closure; replacing it with a scoped digest transfers responsibility to the scope author.
- These are **applicability** tests, not test-quality or bug-detection metrics. `python -c pass` is intentionally semantically irrelevant to the user requirement.
- Exact OS/Python identity matching remains conservative. No automated equivalence between machines, library ABIs, architectures or services is claimed.
- The original source tree may exclude ignored files. The scoped mechanism hashes only the declared paths and nonsecret labels; that is deliberate, not complete provenance.

## Reproduction and independent checks

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_dependency_scope_ablation.py' -v
PYTHONPATH=src python -m unittest discover -s tests -p 'test_real_cross_os_protocol.py' -v
```

A push to the isolated `experiment/dependency-scoped-ablation` branch triggers six **low-privilege** receipt jobs and a fail-closed aggregate in `experimental-dependency-ablation.yml`. The aggregate requires exactly six distinct runner identities with identical base fixture hashes. It also performs the above regression checks. An aggregate failure means **no ablation results accepted**; do not fill missing receipts with fake OS labels.

Prior successfully completed Run #8: https://github.com/jinxinche/RAEE/actions/runs/40972501262. Its artifact cannot be repurposed as proof that these new arms passed. The new result must be tied to its own commit SHA and artifacts.

## Why no independent performance claim follows

The 48 binary labels are hand-designed policy expectations over a highly structured corpus, not independently annotated user requirement correctness. The 36 identity pairs share six environments and are statistically dependent; standard binomial confidence intervals treating them as 48 independent clinical-like subjects would be misleading. A next phase needs independent real repositories, dependency closure audits, blinded human labels and controlled service/package upgrades.
