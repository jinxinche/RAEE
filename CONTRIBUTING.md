# Contributing

Thanks for improving RAEE-Lite. Start with a reproducible bug report, a specific enhancement proposal, or a small test.

1. Use Python 3.10+; install with `python -m pip install -e .`.
2. Run `python -m unittest discover -s tests -v` before submitting a change.
3. Add tests for any changes in evidence semantics, especially false-PASS and stale evidence.
4. Keep runtime dependencies minimal; prefer standard library when feasible.
5. Never add silent network access or project-script execution to `doctor` or default `check`.
6. Explain evidence-role assumptions and boundaries in your PR.

Potential next issues: editable acceptance plan, Python unittest discovery, Windows-path tests, benchmarking Git file scaling, agent adapter privacy review, and package-publishing automation.
