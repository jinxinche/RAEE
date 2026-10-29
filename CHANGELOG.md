# Changelog

## 0.10.0rc2 — Provenance verification and evidence handoff hardening

- Reject GitHub CLI versions earlier than 2.97.0 during attestation verification (CVE-2026-64655).
- Ensure official signing uses an explicit, non-hidden allowlisted handoff: `ci-evidence.json` plus original `report.json`.
- Independent verification requires the raw report and cross-checks its SHA-256; absent RAEE CLI, use a bounded local fallback.
- Changed/new symlink files and symlinked directories now require review on untrusted PRs.
- Added negative version, file handoff and local adversarial PR smoke tests; no real cloud attestation or fork-run claim.

## 0.10.0rc1 — Quality & developer experience release candidate

- Added zero-execution `preflight` with optional JSON report and explicit limits.
- Added fail-closed minimum-test-count runner used on trusted-main CI.
- Expanded protected PR changes to include `.gitattributes`, `.gitmodules`, `pyproject.toml`.
- Restructured README for rapid onboarding; published explicit P0/P1/P2 release gates.
- Added adversarial and negative tests for preflight and test discovery.
- No new claims of independently verified cloud provenance, real-world compatibility or production security.

## 0.9.1

- GitHub-deployment candidate, signed CI template and read-only fork-PR boundary.
- Verified local regression suite, not real GitHub attestation.

## Earlier preview versions

See `docs/RELEASE_VALIDATION_v06.md` through `docs/RELEASE_VALIDATION_v09.md`, and the original version notes.
