# Contributing

Thanks for improving RAEE-Lite. Start with a reproducible bug report, a specific enhancement proposal, or a small test.

1. Use Python 3.10+ in a virtual environment; install full test dependencies with `python -m pip install -e ".[attest]"` and run `python -m pip check`.
2. Run `python scripts/run_reviewed_suite.py --require-critical-modules --summary test-results/summary.json` before submitting a change. Use the centralized total and per-module minima in [the regression runner](scripts/run_reviewed_suite.py), where `MIN_TESTS` is derived from `REQUIRED_TEST_MODULES`; omit an explicit `--min-tests` override. Review and update these minima when adding tests. A skipped critical test or reduced critical module requires review; do not lower the gate to make it pass.
3. Add tests for any changes in evidence semantics, especially false-PASS and stale evidence.
4. Keep runtime dependencies minimal; prefer standard library when feasible.
5. Never add silent network access or project-script execution to `doctor` or default `check`.
6. Explain evidence-role assumptions and boundaries in your PR.

For installation changes, build a fresh wheel with `python -m pip wheel --no-deps . --wheel-dir wheelhouse`, then run `python scripts/smoke_installed_package.py --wheel-dir wheelhouse`. Keep exactly one RAEE wheel in that directory. The smoke uses a fresh environment outside the checkout, with no optional dependencies or project scripts.

Run the synthetic corpus gate with `raee-lite validate-corpus --index validation_corpus/index.json --out validation_corpus/summary.json --require-exact`. Parser errors fail the command; `--require-exact` also rejects fixture mismatches and incomplete parsing. Synthetic fixtures do not establish real-world agent-log compatibility.

The earlier stack is merged into `main` at `5a8cc702674a5e4005f0efe3891b39727c5f7897`; [main CI run 41978577201](https://github.com/jinxinche/RAEE/actions/runs/41978577201) passed its six OS/Python jobs with 268 tests per job. The current candidate's latest full local suite passed, with tests still being added. Use the runner's centralized minima and retain the exact source revision and summary for each validation run instead of copying a fixed candidate test count into commands.

The candidate's [tests.yml](.github/workflows/tests.yml) defines twelve regression jobs: Ubuntu Python 3.10–3.15, Windows and macOS Intel 3.10/3.15, and macOS ARM64 3.10/3.15. The new Ubuntu 3.11–3.14 and ARM64 jobs, along with the rest of this candidate's matrix, await hosted verification. The final gate requires all matrix jobs to succeed; historical run results do not validate changed code.

See the [2026-11-05 engineering audit](docs/ENGINEERING_AUDIT_2026-11-05.md) for the current changes and remaining work. Branch-protection acceptance, independent evidence provenance, release dependency locking, real-log benchmarks and external review remain open acceptance work.
