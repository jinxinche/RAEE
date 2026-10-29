# Real OS / Python evidence-transfer protocol

This experiment is stacked on PR #10 (which is stacked on PR #9); it is **not released**.

## Running and verifying the actual matrix

The branch has a deliberately branch-limited workflow:
[`experimental-real-os-matrix.yml`](../.github/workflows/experimental-real-os-matrix.yml).

It requests six **actual GitHub-hosted runners**:
`ubuntu-latest`, `windows-latest`, **`macos-15-intel`** × Python `3.10` and `3.13`.

The macOS label is now **fixed to macOS 15 Intel (x86-64)** rather than floating `macos-latest` (macOS 26 ARM64 in October 2026). The exact OS image release and architecture are printed at runtime and the interpreter version is asserted. This is a controlled change in experimental platform: a passing macOS 15 Intel run must **not** be described as a passing macOS 26 ARM64 run.

Each job must produce a distinct `receipt-<os>-py<version>` artifact from a temporary fixture directory. The final `aggregate` job refuses to run without all six successful jobs. It requires six unique real `platform/sys.version` pairs and a common source fingerprint. Download the `real-cross-os-metrics` artifact and examine `real-cross-os-metrics.json`.

**Current failure observation (reported 2026-10-30):** `macos-latest/3.10` failed after approximately 41 s; `macos-latest/3.13` failed after approximately 7 s; `windows-latest/3.13` succeeded after approximately 15 s. These are job-level statuses reported by the maintainer, not a downloaded failure log or an accepted six-job matrix. The precise macOS error/step was not accessible through the connected GitHub workflow-run list. The macOS migration is a plausible compatibility variable, **not a proven root cause**. Linux and Windows 3.10 results were not supplied; do not infer them.

**Follow-up fixes on this branch:** pinned macOS 15 Intel for repeatability; added runner image/architecture, actual Python version and 64-bit assertions; explicitly failed (without uploading a valid receipt) when setup/receipt fails; changed the fixture's `app.py` and `test_app.py` to **byte-exact LF** output using `write_bytes`. Python text-mode writes can otherwise change LF to CRLF on Windows, corrupting the cross-OS *same-source* comparison. Added fail-closed aggregator unit tests. All fixes still require actual GitHub Actions results.

**Completed real GitHub matrix evidence (2026-10-29 UTC):** [Run #8](https://github.com/jinxinche/RAEE/actions/runs/40972501262) on commit [`e7f2ee0`](https://github.com/jinxinche/RAEE/commit/e7f2ee0ed16bed8a1ccdf8345f143b06ebbf11bf) completed **six successful local execution receipt jobs plus one successful aggregate job**. The two macOS 15 Intel jobs (Python 3.10 and 3.13), two Windows jobs and two Ubuntu jobs all succeeded. Aggregated artifact [`real-cross-os-metrics`](https://github.com/jinxinche/RAEE/actions/runs/40972501262/artifacts/12941700067) reports `n_runners=6`, `n_cases=48`, `TP=30`, `FP=6`, `TN=6`, `FN=6`, precision/recall `0.8333`, FPR `0.50`, FNR `0.1667`.

**Root cause confirmed from actual failed macOS logs:** `safe_io._reject_links()` refused an OS-managed symlink in the **temporary directory parent chain** (e.g. macOS `/var` → `/private/var`) at `core.init(root)`. It was not a `setup-python` error. The benchmark was corrected to canonicalize its **owned, freshly created** temporary root using `Path(tmp).resolve(strict=True)`. `safe_io.py` was **not** weakened. A dedicated symlink-parent regression test was added. The separate Windows CRLF-vs-LF fixture inconsistency was prevented via byte-identical `write_bytes`.

**Scope:** The six-runner aggregation reports **macOS 15 Intel**; it does not include ARM64 observations in its 48-pair metrics. Separately, the [supplemental macOS 26 ARM64 Run](https://github.com/jinxinche/RAEE/actions/runs/40973047054) completed **2/2 successful native ARM64 receipt jobs**. Its actual runner logged macOS 26.6.2 ARM64, CPython 3.10.11 and 3.13.16, 64-bit, plus `same_runner_state: OBSERVED_PASS` in both cases. This directly retests the original macOS ARM64 failing configuration after the safe temporary-directory canonicalization fix, but the two new ARM receipts were **not** added to the six-runner aggregate. The metric definitions use synthetic relevance/transfer judgments; neither semantic test adequacy nor independent signed provenance is established.

A later [enhanced six-runner matrix](https://github.com/jinxinche/RAEE/actions/runs/40972861758) also passed all seven jobs, with the new protocol regression suite **7/7 PASS** inside the aggregate job.

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

## Retrieve specific failure evidence

With an authenticated GitHub CLI:

```bash
gh run list -R jinxinche/RAEE -w experimental-real-os-matrix.yml --limit 10
gh run view <RUN_ID> -R jinxinche/RAEE --log-failed
gh run view <RUN_ID> -R jinxinche/RAEE --json jobs,status,conclusion,headSha
```

For a successful completed run, download the `real-cross-os-metrics` artifact and verify `n_runners=6`, `n_cases=48`, source fingerprint identity and that failures were **not** silently filled with synthetic receipts. The individual job logs must show real runner image and actual interpreter details for both Python versions. If the pinned macOS 15 Intel jobs fail, preserve their step logs and diagnose the specific failing step rather than changing another OS label by guesswork.

Do not merge this experimental workflow into protected `main` as a substitute for production release CI or signed provenance.
