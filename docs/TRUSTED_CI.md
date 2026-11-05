# RAEE-Lite v0.8: Verified GitHub CI provenance

## Security boundary

`ci-export` produces a **self-asserted, untrusted claim**. Any process can forge
its GitHub environment variables. Only a cryptographic attestation made with
GitHub's official `actions/attest`, verified through GitHub CLI / Sigstore, can
provide independently checkable workflow provenance and artifact integrity.
Attestation alone **does not prove a test was honestly run, was safe, or was
sufficient**. Signed statement contents can be malicious if a trusted workflow
executes attacker-controlled code.

## Trusted workflow pattern

1. Protect `main` and require reviews; keep automation logic on the trusted branch.
2. The legacy [v0.8 reference example](../.github/workflows/trusted-evidence.yml.example)
   is an opt-in template for installation only after review. This repository
   already has a separate [enabled workflow](../.github/workflows/trusted-evidence.yml),
   triggered only by manual `workflow_dispatch`; review it directly rather than
   replacing it with the legacy template. Review every action's pinned SHA before use.
3. `collect` job: no OIDC token permissions, GitHub contents read-only, no PR
   trigger; executes deliberately approved regression suite on protected `main`.
4. `collect` job exports **bounded, redacted metadata** in `.raee/ci-evidence.json`.
5. `sign` job: downloads the handoff artifact from the same workflow run, uses
   `id-token:write` and `attestations:write`, **never runs repository code**.
6. The independent reviewer downloads the attested artifact and calls
   `raee-lite ci-verify` with an out-of-band pinned repository, ref, workflow,
   and full source commit. Local strings from the file cannot establish trust.

Neither workflow automatically attests PR heads. Use a separate
`pull_request` workflow with read-only permissions for optional untrusted
source inspection; do not add `pull_request_target` + checkout of PR code,
workflows that sign user-submitted reports, write tokens, or developer secrets.

## Create and attest a claim

The workflow runs `raee-lite report`, then:

```bash
raee-lite ci-export \
  --expected-repo "$GITHUB_REPOSITORY" \
  --trusted-ref refs/heads/main \
  --workflow .github/workflows/trusted-evidence.yml
```

The output is not trustworthy until GitHub Actions creates an artifact
attestation for the **exact** `.raee/ci-evidence.json` bytes. The claim binds the
report through its SHA-256 digest.

The legacy `.yml.example` specifies an upload of only `.raee/ci-evidence.json`,
without the full report. The enabled manual workflow instead uploads **both
the claim and the full `report.json`** in its `ci-evidence-claim` handoff and
publishes both with the attestation bundle in `independently-verifiable-evidence`.
Only `ci-evidence.json` is the direct attestation subject; report integrity is
checked through the digest it contains.

The full report can contain requirement text, project goals, boundary notes,
paths and environment metadata. Claim metadata minimization does not redact
the separately uploaded report. Review sensitive inputs before generating,
exporting and uploading evidence. If report bytes change, regenerate the report
from consistent source evidence, re-export its claim and obtain a new attestation;
do not redact an already attested report and retain the old digest.

## Independent verification (requires installed, trusted GitHub CLI)

Supply the expected identity from your policy, never copy it blindly out of
an untrusted artifact. Use the exact full SHA of the trusted build:

```bash
raee-lite ci-verify \
  --manifest ./download/ci-evidence.json \
  --expected-repo OWNER/REPO \
  --expected-ref refs/heads/main \
  --expected-sha <40-character-commit-SHA> \
  --expected-workflow .github/workflows/trusted-evidence.yml
```

Internally, v0.8 invokes `gh attestation verify` with repository, signing
workflow identity, source digest/ref, self-hosted runner exclusion and JSON
output. The GitHub CLI verifies the cryptographic certificate/provenance. If
`gh` is missing, exits nonzero, times out or has no verified attestations,
verification **fails closed**. Do not install `gh` from the project under test
or put untrusted project directories first on `PATH`.

Optionally add `--report report.json` to require its bytes to match the
attested report SHA-256 in the manifest. Without this argument, the verifier
checks the authenticated **claim** about the report, not access to the original
report. By default, explicit acceptance evidence must be recorded as passing;
`--allow-incomplete` permits viewing a verified failing/incomplete claim,
without marking it green.

The current verification result preserves `report_outcome`,
`strict_check_passed` and the applied `require_passed` policy. The first two
are signed claims, not independently re-executed test results.
`--allow-incomplete` sets `require_passed` to `false`; a successful
`GITHUB_ATTESTATION_VERIFIED` result alone must not be interpreted as passing
acceptance evidence. The output also includes `claimed_run_id` and
`run_identity_verified: false`: run ID, run attempt and event identity are not
independently verified. Pinned repository/ref/commit/workflow provenance does
not establish which particular workflow invocation produced the claimed tests.

## Known limitations

- No live GitHub Actions artifact attestation was generated or verified in the
  local development environment. CLI verification tests use mocks.
- SHA/ref/workflow restrictions are enforced through the **GitHub CLI**, whose
  trusted installation, authentication and version are operational assumptions.
- Protection of the trusted branch and CI runner are external prerequisites.
- A compromised trusted builder or manipulated tests can still produce signed
  but misleading claims. A separate fixed evaluator / stronger trust boundaries
  are needed for higher assurance.
- External tools, dynamically fetched dependencies, action pinning, GitHub
  repository settings, access controls and real cloud CI remain outside this
  package's control.
- This is not a SLSA certification, vulnerability scan, or proof of correctness.

## References

- https://docs.github.com/en/actions/concepts/security/artifact-attestations
- https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations
- https://cli.github.com/manual/gh_attestation_verify
- https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions
