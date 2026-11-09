# See why a green test is not a verified requirement

**One command after installation. No AI API key or pytest required.**

The scenario is deliberately small: signup should reject an address without an `@` sign. An existing arithmetic test passes, but it never calls signup. The walkthrough adds a relevant test, exposes the bug, fixes the toy function, and then changes its source again.

## Run it

Use Python 3.10+ in an activated virtual environment. From a reviewed checkout of this repository:

```bash
python -m pip install --no-deps .
python examples/run_demo.py
```

See the [installation instructions](../README.md#try-the-public-release-candidate) to create the environment. The demo uses that same Python interpreter for the CLI and tests. It runs only the small synthetic fixtures defined in [run_demo.py](run_demo.py), inside a temporary directory that is removed afterward; it does not run your project's tests or upload data.

## Expected output

```text
1. Unrelated arithmetic test passes
  R1: UNTESTED
2. A requirement-linked test exposes the bug
  R1: FAILED_CHECK
3. The toy fix passes the two example tests
  R1: OBSERVED_PASS
4. Source changes after the recorded check
  R1: STALE

Demo passed; scratch files removed.
OBSERVED_PASS records a labelled command result, not complete coverage.
The toy '@' check is not a production email validator.
```

The runner checks each state and exits nonzero if the observed result differs. The intentionally failing test in step 2 is part of the demonstration; a completed walkthrough exits 0.

| Step | What happened | What the result supports |
| --- | --- | --- |
| 1 | A test of `1 + 1 == 2` passes outside RAEE-Lite | No requirement-linked check has been recorded. RAEE-Lite does not infer coverage from the green test. |
| 2 | A user-labelled unit check calls the buggy signup function | The observed command failed on this source state. |
| 3 | The toy fix rejects addresses without `@`; two example tests pass | This labelled command passed. The label and assertions still need human review. |
| 4 | A comment is added after the check | The source fingerprint changed, so the recorded result is stale. This does not imply the comment introduced a bug. |

## Use the same workflow on your own project

After reviewing the command you intend to run, associate it with a requirement:

```bash
raee-lite init
raee-lite add "Signup rejects addresses without an @ sign"
raee-lite expect --for R1 --kind unit
raee-lite run --for R1 --kind unit -- python -m unittest discover -s tests -v
raee-lite status
raee-lite check
```

This example assumes a fresh manifest and a real `unittest` suite under `tests/`; use the requirement ID returned by `add` and substitute your actual test command. `run` explicitly executes it. `status` returns 1 for missing, failed or stale evidence; the default `check` writes reports without running tests. Reports include `.raee/report.html`, `.raee/report.md`, `.raee/report.json` and `.raee/report.sarif`.

The toy `@` check is intentionally incomplete. This demo validates evidence bookkeeping, not comprehensive email validation, semantic coverage detection or software correctness.

[Project overview](../README.md) · [Evidence contracts](EVIDENCE_CONTRACTS.md) · [Share a reproduction](https://github.com/jinxinche/RAEE/issues/7)
