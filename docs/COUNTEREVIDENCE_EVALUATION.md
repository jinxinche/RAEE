# Counterevidence and environment-transfer boundary audit

**Status:** controlled experiment stacked on [Proof-Obligation Trace PR #9](https://github.com/jinxinche/RAEE/pull/9). Not part of the released RAEE-Lite binary and not evidence of real Windows/macOS validation.

## Purpose

Try to **falsify the continued applicability** of an earlier observed passing check when the project changes:

1. The test is weakened while its prior passing receipt remains.
2. The requested behavior is changed while the source files stay the same.
3. A new failed execution supersedes an old passing one.
4. An additional check obligation is introduced.
5. The old receipt lacks a binding to the exact requirement text.
6. A Linux/Python receipt is evaluated for a different stated OS or Python version.
7. Positive controls with unchanged source, intent and environment should **not** be revoked.

This is a *conservative applicability check*, not automatic correctness verification. The current source fingerprint has exclusions; unchanged fingerprint does not establish semantic equivalence.

## Design changes

- Explicit execution records now store `requirement_digest`, SHA-256 over the exact requirement text serialized deterministically. The description itself remains in the manifest; the digest prevents an old check from being reused after the user silently edits its wording.
- Legacy receipts without this field are marked `INTENT_UNBOUND` (not silently grandfathered in).
- The assessment can accept a **specified** `target_environment` with Python version and OS identity. Mismatches are marked `ENVIRONMENT_SHIFT_UNVERIFIED`; missing metadata becomes `ENVIRONMENT_UNBOUND`.
- `raee-lite trace --for R1 --target-os "..." --target-python "..." --json` displays such unresolved obligations without running code.
- Neither exact textual intent binding nor OS-string equality proves a test relevant, sufficient, or reproducible. Any mismatch fails conservatively, including potentially harmless differences in patch versions.

**Important distinction:** old `status` may still show that an earlier process had exit code zero; the contract/trace layer *withdraws the applicability of the receipt to the current intent or target environment*. This is not rewriting historical execution evidence.

## Reproduce

From a reviewed checkout of this PR with Python >=3.10:

```bash
PYTHONPATH=src python -m unittest tests.test_counterevidence -v
PYTHONPATH=src python benchmarks/counterevidence_eval.py > counterevidence-results.json
```

The evaluator runs actual harmless local Python subprocess checks for each case. It creates fresh temporary project files and intentionally weakens tests, modifies requirement text, changes source bytes, adds an E2E obligation, and changes target environment metadata.

### Observed local 12-scenario confusion matrix

| Actual expectation / predicted action | Revoke or downgrade | Retain |
| --- | ---: | ---: |
| Should revoke/downgrade | 8 (TP) | 0 (FN) |
| Should retain | 0 (FP) | 4 (TN) |

In this hand-authored controlled sample, precision and recall were 1.0, FPR 0.0, FNR 0.0.

**Do not generalize these rates.** Each case's ground truth was specified by the experiment designer using the intended implementation contract. There are only 12 synthetic cases, no independent labeling, no repetitions across real codebases, and no real cross-OS execution. The results are an initial falsification test, not a benchmark claim.

## Open research issues

- True **cross-OS testing** on GitHub-hosted Windows, Linux, macOS with Python versions pinned and receipts captured independently.
- Fine-grained changeset attribution: a global source fingerprint revokes on any tracked byte change (possible false positives) and excludes ignored/external state (possible false negatives).
- Coverage semantics: a self-declared check marked `unit` can run `python -c pass` and still receive an observed process pass. RAEE-Lite **cannot** establish that the check covers the requirement.
- An independent, blinded dataset with fixed inclusion criteria, nontrivial negative opportunities, human relevance labels and confidence intervals.
- Stronger environment identity beyond Python/OS strings: dependencies, architecture, services, hardware, filesystem behavior and resource limits.

## Safety and scope

No automatic agent action, model API, external network call or project-owned script execution is involved in `trace`. The explicit local evaluation executes small synthetic commands inside its temporary test projects. It does not establish production safety or cloud attestation.

This experimental PR must be reviewed **after** the base Proof-Obligation Trace PR. Neither should be merged into a release branch merely to improve public claims.
