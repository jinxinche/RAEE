# RAEE-Lite v0.7.0 — release validation

Date: 2026-10-28

## Implemented

- DSSE envelope (Ed25519 PAE), in-toto Statement v1-shaped RAEE-specific predicate.
- Explicit local key generation with mode 0600 and refusal to place private keys in repository.
- Exact-byte SHA-256 binding of report, ledger and manifest; bounded source fingerprint and Git SHA binding.
- Re-audit ledger/manifest freshness before signing; no silent overwrite of signed artifacts.
- Independent trusted public key required for verification; offline reduced-policy mode is explicit.
- Optional enforcement of expected Git SHA, clean Git checkout, current source snapshot, and locally asserted isolated replay receipt.
- CLI does not execute repository scripts during signing or verification.

## Tested in this environment

- Python unittest suite: **113/113 passing**, including 91 previous tests and 22 new attestation-focused cases.
- Attack/negative tests: modified signed payload, modified signature, replaced trusted key, changed report bytes, changed ledger/manifest, stale source, dirty Git status, replay on a different expected Git SHA, private-key file permissions, symlinks, output overwrite, partial snapshots and reduced offline mode.
- Independent virtual environment: installed wheel without network using locally available dependencies, created a Git repository, ran a deliberate simple test, generated report, created test signing key, signed evidence and verified against explicitly pinned key/commit/current snapshot.
- Negative smoke: appending a space to the signed report caused verification failure, restoring report re-enabled verification.

## NOT tested or guaranteed

- No real Docker daemon execution, no independent privileged/unprivileged container security audit.
- No real GitHub Actions cloud runs on Linux/Windows/macOS; workflow configuration has been updated, not externally validated.
- No independent remote CI identity or Sigstore/SLSA attestation. A compromised signer can sign fabricated local ledger receipts.
- No hardware-backed key, KMS integration, revocation, transparency log, trusted timestamping or third-party penetration test.
- No proof that test assertions adequately cover requirements or that execution occurred in an uncompromised environment.

## Security takeaway

v0.7 provides **tamper-evident, signer-authenticated evidence claims**, not independent proof of software correctness or trusted execution. For production, a separate runner, signer identity and anchored CI policy remain necessary.
