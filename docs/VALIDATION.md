# v0.5.0 validation record

**Environment:** local Linux / Python 3.13.5, date 2026-10-28. Synthetic fixtures, not a real-provider transcript corpus. Performance depends on machine and IO. Values are illustrative, not universal SLAs.

## Reproducible tests and benchmarks

| Validation | Command | Observed result |
|---|---|---|
| Core regression and adversarial testing | `PYTHONPATH=src python -m unittest discover -s tests -q` | 72 tests passed |
| Agent log throughput | `PYTHONPATH=src python benchmarks/log_benchmark.py --lines 50000` | 50,000 lines, 6.46 MB, 4.71 s, 54.38 MB Python tracemalloc peak, 25,000 receipts |
| Repository fingerprint | `PYTHONPATH=src python benchmarks/repo_benchmark.py --files 2000` | 2,000 files, 0.193 s, 1.00 MB Python tracemalloc peak |
| Labelled relevance hints | `PYTHONPATH=src python benchmarks/evaluate_hints.py` | 24 *synthetic* labels: TP=8, FP=2, FN=5, TN=9; precision=0.80, recall=0.6154, FPR=0.1818 |
| Local Git Base/Head comparison | `test_pr_base_head_attestation_local_repo` | Correct expected commits accepted; swapped commits rejected |

`tracemalloc` tracks Python-managed allocations; it is **not** process peak RSS. For a meaningful production benchmark, record peak RSS on each target OS and use a standardized hardware profile.

## Provider compatibility matrix (synthetic, not externally certified)

| Provider | Shape covered | Unsupported or unverified |
|---|---|---|
| Claude Code | `assistant` `tool_use` Bash → `user` `tool_result`, string/list output; some `toolUseResult.exitCode` | Non-Bash execution, subagent cross-file linking, real-version corpus, truncated spilled results |
| Codex | `response_item` function call + output, `event_msg.item_completed`, `codex exec --json` `item.started`/`item.completed` command execution | Provider-version exhaustive testing, other tool types, subagent records, partial event streams |

The importer does **not** store raw text or automatically promote exit 0 to trusted evidence. Its observable status is a **transcript assertion**, not a re-executed check.

## Link-hint metrics: why they are limited

The 24-example fixture was constructed for testing and includes deliberate same-scope but irrelevant examples. The updated strategy requires both the declared check kind and one overlapping allowlisted topic (such as `login`), trading recall for fewer obvious false suggestions. A real-data benchmark needs at least hundreds of independently annotated requirement–test pairs from consenting users, across languages/project types. Track per-category precision/recall/FPR and confidence intervals; use a held-out set and evaluate the raw suggestions, not the satisfaction of contracts.

## GitHub Actions and platforms

The repository includes a GitHub Actions OS/Python matrix definition (Ubuntu, Windows, macOS; 3.10, 3.13), but **no cloud run is claimed here**. Actual compatibility requires pushing this version and checking that job histories and artifacts show successful runs. The PR workflow example defaults to read-only and is not enabled until renamed. Avoid executing PR code in a privileged context.

## Unresolved before v1.0

- Collect consented, redacted **real** Codex/Claude sample corpus (version-stamped) and measure parse coverage and unsupported-event rate.
- Obtain independent human labels for requirement-to-test relevance and compare against baselines.
- Run cross-platform GitHub matrix on a public repo; observe Windows subprocess and encoding behavior.
- Test real 100k-file repositories with CI and cold-cache measurements, not only synthetic file trees.
- Perform third-party security review and isolated-runner evaluation before handling hostile scripts.
- Review and pin release dependencies/actions; add CI provenance signing only with a defined trust model.
