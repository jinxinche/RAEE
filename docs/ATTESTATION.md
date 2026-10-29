# Evidence Attestation (v0.7) — verification guide

**Security preview; not certified software.** A valid signature says that the holder
of the *trusted* Ed25519 signing key signed specific bytes and claims about a
specific source fingerprint. It **does not** prove that the signing host was
trusted, that the test really ran, that the claimed Docker isolation was real,
or that the test adequately covers the user request.

## Installation

```sh
python -m pip install '.[attest]'
```

The normal RAEE-Lite CLI continues to have no third-party runtime dependency.
The attestation commands use the `cryptography` package (>=42) for Ed25519.

## Create a key outside the project

```sh
raee-lite attest-keygen \
  --private "$HOME/.config/raee-lite/private.pem" \
  --public "$HOME/.config/raee-lite/trusted-public.pem"
```

The private key is an **unencrypted**, permission-0600 Ed25519 PEM file and must
be treated as a secret. The generator never overwrites keys and refuses to
create a private key within the project. Prefer a purpose-specific ephemeral
CI signing identity or hardware-backed/managed signer over a long-lived local
key for serious production use. **Never commit the private key.**

## Sign the current evidence report

```sh
cd project
raee-lite report  # Can exit nonzero when requirements are not satisfied; the report is still written.
raee-lite attest --private-key "$HOME/.config/raee-lite/private.pem"
```

Default signing **fails closed** when:
- the report does not match the current source snapshot;
- the report no longer agrees with the current local evidence ledger and manifest;
- the Git checkout is dirty or Git HEAD changed since the report;
- Git is absent;
- the source fingerprint skipped eligible files; or
- the attestation destination already exists.

Explicitly weaker modes exist for special uses (`--allow-dirty`, `--allow-no-git`,
`--allow-partial`). Such attestations retain signed limitations and can be
rejected by verification policy (`--require-clean`).

For an *observed isolated replay* in the same source snapshot, optionally require:

```sh
raee-lite attest --private-key "$HOME/.config/raee-lite/private.pem" \
  --require-isolated
```

This checks the **locally recorded receipt**. It is not independent proof of Docker
execution: someone who controls the ledger and signing key can make a false
receipt and sign it. The isolated runner has not been tested with a real Docker
host in this development environment.

## Verify with a separately trusted public key

```sh
# Public key must come through a separately trusted channel, NOT from the PR.
raee-lite verify-attestation \
  --public-key "$HOME/.config/raee-lite/trusted-public.pem" \
  --expected-commit '<full Git commit SHA>' \
  --require-clean --check-current
```

By default verification checks the DSSE Ed25519 signature, the *exact bytes*
of `.raee/report.json`, the separately signed hashes of `.raee/ledger.json`
and `.raee/manifest.json`, the fingerprint recorded in the statement, and
policy flags. `--check-current` additionally recomputes current source state.
Use `--expected-commit` in CI, using the commit SHA from GitHub's trusted
event metadata — never from PR-authored text.

For verifying a standalone saved report without a working tree and ledger:

```sh
raee-lite verify-attestation \
  --attestation evidence.dsse.json --report evidence-report.json \
  --public-key /trusted/path/public.pem --offline
```

`--offline` reduces verification: it cannot check the local ledger, manifest,
or current source unless those files are available and explicitly requested.
Never infer that a fresh checkout was verified from an offline-only check.

## Format and trust model

v0.7 uses an **in-toto Statement v1-style object** wrapped in a **DSSE** envelope
(`payloadType=application/vnd.in-toto+json`), with domain-separated PAE signing.
The statement is an RAEE-Lite-specific predicate (`urn:raee-lite:evidence-attestation:v1`),
**not SLSA provenance** and **not a Sigstore identity-backed attestation**.

The signed predicate binds:
- SHA-256 of the current bounded source fingerprint and of the exact report bytes;
- SHA-256 of the ledger and manifest files;
- current Git commit, available/dirty claim and source-coverage caveat;
- IDs, local snapshot hashes and image IDs of matching *locally asserted*
  isolated-replay receipts (if any).

Verifier accepts **only one signature**, pins the independently supplied
public key, validates its key fingerprint, checks the DSSE signature over
`payloadType + payload` via PAE, validates schema/predicate/subject and applies
explicit policy. It does not use an embedded public key as a trust anchor.

## Threats and limitations

| Threat | v0.7 policy / remaining risk |
|---|---|
| Report or signature modified | Detected against the pinned public key |
| Wrong signing identity | Rejected if the pinned public key does not match |
| Valid old signature replayed on a different commit | Use `--expected-commit` and `--check-current` |
| Ledger or manifest changed | Detected by default local verifier; standalone offline mode omits this |
| Source changed after report | Rejected when signing; `--check-current` rejects changed worktree at verification |
| Signing key compromised | **Not solved.** Attacker can sign false claims. Rotate pinned keys outside PR control |
| Malicious CI execution / forged local receipt | **Not solved.** Use independent, credential-free, locked-down CI identities |
| Git-ignored/excluded/external data | Not included; recorded as a scope limitation; use separate provenance for inputs |
| Racing file replacements or malicious privileged host | Not fully protected against TOCTOU or host compromise |
| Untrusted repo replaces public key | Never read a trust anchor from the untrusted PR checkout |
| Fake test passes / incomplete requirement coverage | **Not solved.** Signature authenticates a claim, not its truth |
| Timestamp freshness | No trusted timestamp service or revocation/logging in v0.7 |

**Important:** Do not expose a private key to code from untrusted PRs, and never
run the agent's project scripts in a privileged verification job. Prefer a
separate job that only verifies already-produced artifacts against a public key
pinned outside the PR. Hosted CI, remote signer identities, real Docker
execution, revocation and transparency log verification are **future work**.
