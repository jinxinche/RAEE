# RAEE-Lite v0.6 release validation

- Baseline: v0.5.0 source archive in this conversation.
- Release version: 0.6.0; 72 previous regression tests + 19 new isolated-runner tests.
- Testing: Python unittest suite, all pass in development environment.
- New tests use mocks to validate Docker argv, security flags, version provenance,
  timeout/nonzero status handling, local daemon checks, missing images and no Docker
  fail-closed behavior. Real container execution was NOT available in environment.
- Packaging: wheel via setuptools and a source archive, checked independently.
- Evidence: `--dry-run` produces no ledger receipt, installation and report
  generation smoke test intended for demonstration.
- Known limits: see SECURITY.md and docs/ISOLATED_RUNNER.md.
