# RAEE-Lite v0.8.0 — Local validation and open risks

The new module is a **GitHub Artifact Attestation integration**, not a custom
OIDC verifier. Cryptographic validation is deliberately delegated to the
supported `gh attestation verify` command. This avoids accepting self-issued
CI identity claims, but requires a separately trusted GitHub CLI installation.

## Implementation

- Strong policy gating at claim export (push / workflow_dispatch only, pinned
  `owner/repo`, `refs/heads/main`, workflow path and full commit).
- Fresh report/snapshot/clean Git checked before claim export; only bounded,
  redacted counts and hashes included in attested artifact.
- Independent third-party policy at verification: enforce expected repository,
  workflow, branch, commit and hosted runner, with optional full report digest.
- Explicit distinction between the untrusted receipt and official GitHub
  provenance verification; never conflates cryptographic attestation with
  behavioral correctness.
- Trusted Actions reference has distinct low-privilege evidence collector and
  privileged signer, with no repository checkout in signer.

## Confirmed local validation

- v0.8 focused unit suite: 16 tests passing, including reject paths.
- Full regression suite and wheel installation: see final release summary.
- GitHub official OIDC identity and Sigstore signature are **not locally
  testable without an actual GitHub-hosted workflow**; mock verification tests
  only ensure the correct CLI flags, failures and policy checks.

## Remaining serious security gaps

1. A compromised trusted runner or source-controlled tests can create false
   claims that GitHub will faithfully attest.
2. SHA pinning is not complete in the sample workflow until the user replaces
   all third-party action tags with reviewed immutable digests.
3. GitHub branch protection, self-hosted policy, retention and access control
   require external configuration and audit.
4. Authentic GitHub attestations, rate limits, keyless identity verification,
   Windows/macOS CI and external adversarial penetration tests are outstanding.
5. No guarantee that tests cover requirements, or that a signed claim proves
   absence of vulnerabilities.
