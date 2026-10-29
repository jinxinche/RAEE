# v0.9 real-world validation, not feature inflation

- Reproducible, redacted compatibility corpus and provider-specific metrics: implemented with synthetic fixtures.
- Independent GitHub verification and published attestation: pending dedicated repository and cloud runs.
- Low-privilege PR fork threat test in disposable public GitHub repo: pending.
- GitHub Actions Windows/macOS/Linux run links: pending.
- Real user-session and requirement-pair annotations: pending consenting participants.
- Independent security audit of Actions and runner boundary: pending.

See `docs/REAL_WORLD_VALIDATION.md` for pass/fail gates.

# RAEE-Lite roadmap

## v0.7.0 — Offline Evidence Attestation (implemented as security preview)
- Ed25519 signing, DSSE envelope and in-toto Statement v1-shaped claims
- Independent pinned public key, no trust from self-identified envelope signer
- SHA-256 binding to exact report bytes, ledger, manifest, bounded source fingerprint and Git HEAD
- Signed isolated-run receipt inventory, expressly not independent execution proof
- Safe key generation, fail-closed freshness checks, offline and strict verification policies
- Attack-focused tests for tampering, replay, key substitution, stale reports and key permissions
- **Not** a Sigstore/SLSA attestation, remote CI identity proof or secure execution attestation

# RAEE-Lite roadmap

## v0.6.0 — Isolated Evidence Runner (implemented as pre-release)
- Explicit Docker-only, offline replay; never silently executes on host
- Copy-only, bounded source snapshot, with known sensitive names excluded
- Local trusted image resolved to image ID; restricted execution profile
- Evidence provenance in HTML/Markdown/JSON; visible exclusion/limits
- 91 test suite checks, including mocked runtime and hostile input tests

## Release gates for v0.8 / v1.0
1. Real rootless Docker smoke and failure demonstrations on Linux and Docker Desktop.
2. Cross-platform worker integration, locked-down images, Windows path cases.
3. Source-snapshot directory-race and credential leak adversarial audit.
4. Trusted CI signing identities / key rotation / audit logging (local signed ledgers can still be forged).
5. Fixture corpus from real opt-in sanitized Agent logs and blind evidence association evaluation.
6. True resource benchmarking and cleanup verification under failures/interrupts.
7. Test image preparation, secure dependency strategy and permissioned attestations.

**Target:** reliable developer value and transparent evidence boundaries; no claim
that 10,000 GitHub Stars or production security is guaranteed.

## v0.8 implemented (preview)

- Trusted-CI metadata receipt export with explicit protected-ref policy and immutable source/Git digest binding.
- Official GitHub CLI attestation verification with explicit repo / signer-workflow / source ref / source commit policy.
- Two-job GitHub Actions reference architecture: nonprivileged checks, privileged attestation job with no checkout or project scripts.
- Added negative tests for forged context, PR events, stale/dirty source, report tampering, missing gh, identity mismatch and failed verifier.

## v0.9 validation priorities

- Run real artifact attestations on GitHub-hosted ephemeral Ubuntu runners, verify end to end with a pinned CLI version.
- Independently audit the GitHub Actions workflow, supply chain pinning and repository settings.
- Test authentic Codex/Claude logs with consent, benchmark drift and association precision/recall.
- Validate branch protection, artifact retention, identity revocation and PR/fork safety with cross-platform integration tests.
- Introduce a fixed trusted evaluator to reduce reliance on project-controlled tests.
