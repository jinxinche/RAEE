# Real OS / Python evidence-transfer protocol

This experiment is stacked on PR #10 (which is stacked on PR #9); it is **not released**.

## Running and verifying the actual matrix

The branch has a deliberately branch-limited workflow:
[`experimental-real-os-matrix.yml`](../.github/workflows/experimental-real-os-matrix.yml).

It requests six **actual GitHub-hosted runners**:
`ubuntu-latest`, `windows-latest`, `macos-latest` × Python `3.10` and `3.13`.

Each job must produce a distinct `receipt-<os>-py<version>` artifact from a temporary fixture directory. The final `aggregate` job refuses to run without all six successful jobs. It requires six unique real `platform/sys.version` pairs and a common source fingerprint. Download the `real-cross-os-metrics` artifact and examine `real-cross-os-metrics.json`.

**IMPORTANT:** At authorship time, a real six-job run and its metrics have **not been observed** through the connected GitHub interface. The GitHub PR's **green boundary scanner** proves neither matrix execution nor acceptance.

## Expected 48 evaluation opportunities

There are 36 ordered source→target receipt comparisons: 6 same-runner comparisons (positive retention controls) and 30 cross-runner comparisons (expected conservative withdrawal). Plus 12 hard cases, two from each real runner: a harmless tracked note change (expected to reveal false withdrawal) and an out-of-fingerprint external dependency revision (expected to reveal missed withdrawal).

The predicted outcome for each case is **computed from execution evidence**. No confusion-matrix counts are hardcoded.

## Interpreting the hard cases

The `NOTE.txt` intervention changes an irrelevant tracked file. Since fingerprinting is global, the pre-existing check receipt will probably be marked `STALE`—a deliberate, measurable **false positive relative to the stated task relevance ground truth**. This is a limitation of whole-repository fingerprints, not a reason to ignore source changes in safety-sensitive cases.

The external state intervention changes an environment variable `RAEE_BENCH_EXTERNAL_REVISION` and keeps the tracked source unchanged. The default fingerprint does not cover environment variables, so evidence may be incorrectly retained—**a false negative for the stated external dependency criterion**. It is *not* a real package upgrade and must not be advertised as one.

The cross-platform label considers every OS/Python identity mismatch a reason to request revalidation. That is a conservative review policy, **not a scientific assertion that behavior necessarily differs**. Different Python patch versions and OS build strings can create unneeded withdrawals.

## Security limits

The workflow has only `contents: read`; it uses no OIDC, privileged events, CI caches, repository secrets, or private credentials. Its checks are self-authored and **not independently attested**. A PR-controlled workflow must not be mistaken for a trusted release gate. Run tests on a disposable hosted worker only, never supply production secrets.

## Reproduction commands

```bash
PYTHONPATH=src python benchmarks/real_runner_receipt.py --out receipt.json
# On each OS/Python worker separately, upload receipt.json under a distinct artifact name
PYTHONPATH=src python benchmarks/aggregate_real_matrix.py --input runner-receipts --output real-cross-os-metrics.json
```

The aggregate command **must fail** when only a local receipt is present. Do not fill missing windows/macOS outcomes with synthetic labels.
