# CI trust boundaries, not marketing claims

- The `pull_request` workflow executes only checked-in BASE branch scanner; PR files are **untrusted passive data**, never imported or executed. It cannot prove proposed source changes are correct.
- The base-workflow scanner does not cover every malicious GitHub feature or attack: privileged repository administrators, third-party dependency compromise, malicious GitHub runner images, Action bugs and weak review processes remain potential attack vectors.
- `main` must be protected before running the trusted signer; a GitHub attestation without protected provenance is not sufficient evidence for this deployment claim.
- `collect` executes repository scripts **only on protected main**, with read-only permissions. `sign` receives one artifact from the same workflow run, does not check out code, and uses GitHub's OIDC/Sigstore identity.
- Protect against dependency/supply-chain compromise: use pinned GitHub Actions SHAs, review the pinned versions periodically, lock software dependencies where possible, protect release workflows from silent modifications, and review any generated dependency metadata.
- Do not accept self-attested source identity, arbitrary private keys, transient environment variables, or unsigned JSON as independent proof.
- The independent verifier must pin the source commit, branch, repository and signing workflow from outside the supplied manifest.
- Existing code contains an opt-in local runner and Docker runner; neither is invoked by the PR workflow.
- Any externally supplied agent logs must be treated as untrusted and possibly sensitive; do not upload real logs to public issue trackers.
- The static PR scanner bounds file counts and byte reads and refuses changes to workflow and trust-boundary files. A benign PR may require maintainer-controlled integration if it needs to modify those paths.
- Single-maintainer GitHub repositories cannot effectively meet a 1-independent-review rule until a second collaborator is onboarded.
- Success of a cryptographic provenance check is **not a security audit or proof of program correctness**.
