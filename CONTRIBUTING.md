# Contributing

Thanks for improving RAEE-Lite. Start with a reproducible bug report, a specific enhancement proposal, or a small test.

1. Use Python 3.10+ in a virtual environment; install full test dependencies with `python -m pip install -e ".[attest]"` and run `python -m pip check`.
2. Run `python scripts/run_reviewed_suite.py --min-tests 268 --require-critical-modules --summary test-results/summary.json` before submitting a change. A skipped critical test or reduced critical module requires review; do not lower the gate to make it pass.
3. Add tests for any changes in evidence semantics, especially false-PASS and stale evidence.
4. Keep runtime dependencies minimal; prefer standard library when feasible.
5. Never add silent network access or project-script execution to `doctor` or default `check`.
6. Explain evidence-role assumptions and boundaries in your PR.

For installation changes, build a fresh wheel with `python -m pip wheel --no-deps . --wheel-dir wheelhouse`, then run `python scripts/smoke_installed_package.py --wheel-dir wheelhouse`. Keep exactly one RAEE wheel in that directory. The smoke uses a fresh environment outside the checkout, with no optional dependencies or project scripts.

CI covers Python 3.10–3.15 on Linux and the endpoint versions on Windows and both macOS architectures. Run links and summaries, rather than the workflow definition alone, establish the actual coverage. Main integration, independent evidence provenance, release dependency locking, real-log benchmarks and external review remain acceptance work.
