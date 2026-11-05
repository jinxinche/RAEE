# v0.9 privacy & trust boundary

The new validation corpus reads **only selected local regular JSONL files**, with basename-only paths, bounded index and case counts, and a non-networked evaluation flow. Raw logs stay local. Summaries contain only opaque fixture identifiers, coarse tool types, aggregate matches and parser warnings. Only opt-in users should validate real private transcripts; remove secrets before sharing any files. This validation does not establish an independently trusted execution environment, test adequacy, model correctness, or field compatibility. Avoid uploading raw private logs to public GitHub Issues.

The regression matrix is trusted-branch only; do not add privileged GitHub tokens or OIDC attestation to an untrusted PR workflow. See `docs/REAL_WORLD_VALIDATION.md`.

# Security policy · RAEE-Lite v0.7.0

**New in v0.7:** DSSE/Ed25519 offline signatures can detect changed evidence and
bind source/report/ledger/manifest claims to a separately pinned public key.
They do not prove real Docker execution, adequate tests, code correctness,
a trusted build runner, or the reliability of a signer-controlled ledger.
Never include the signing private key in a repository, a PR checkout or an
untrusted test runner. Use `verify-attestation --expected-commit --require-clean
--check-current` with an external trusted key for higher assurance.
See [the attestation security guide](docs/ATTESTATION.md).

# Earlier security safeguards (v0.5–v0.6)

RAEE-Lite is an **evidence reporting tool, not a sandbox or security scanner**. All source trees, manifest fields, agent transcripts, and PR artifacts should be treated as untrusted. A passing check **never** proves that code is secure or requirements are satisfied.

## Defaults and key mitigations

- **No repository script execution by default**. `doctor`, `check` (without `--run`), imports and comparisons are designed as read-only inspections of project code; they may write local `.raee` reports. Project execution requires explicit `run --` or `check --run`.
- **CI execution gate**. If `CI=true`, running project scripts also requires `--allow-ci-execution`. This is an acknowledgement, **not** a sandbox. Never run untrusted PR scripts on credential-bearing/self-hosted runners.
- **Bounded transcript ingestion**. Explicit JSONL file only, with regular-file/no-follow check, 256 MB file, 512 KB line, 200k event, 2,048 pending-call and 25k observation caps. Oversized lines are skipped and counted; imported transcripts are not proofs.
- **Metadata minimization**. Raw command arguments, stdout/stderr, user messages, model reasoning and secrets are not persisted from agent logs. Local manually executed commands are stored as a redacted placeholder + SHA-256 argv digest; subprocess output is discarded instead of buffered.
- **Safe report outputs**. HTML escapes untrusted data and has a restrictive CSP without JS or external assets. Markdown escapes raw HTML and table controls. Atomic writes reject symlink destination paths; compare rejects symlinked input reports.
- **PR provenance**. Optional `--expected-base-sha`/`--expected-head-sha` rejects a mismatch between claimed Git commits and supplied expected commits. Standalone unsigned reports can still be forged. v0.7 signing requires separately controlled keys, and a compromised signer can forge claims.
- **Resource-bounded source fingerprint**. Up to 5,000 source files and 64 MB of source bytes per snapshot. Omitted files cause partial-coverage evidence status rather than false all-clear.

## Explicit execution remains risky

`run` and `check --run` can execute arbitrary project-owned code. Even with `shell=False` at the Python boundary, npm or other tools may launch shells, contact networks, read accessible secrets or spawn subprocesses. The CLI discards command output, sets a timeout, and attempts to kill process groups on POSIX, but **does not provide containment**. On Windows, descendant processes may survive a timeout. For hostile/untrusted code, use a disposable sandbox/VM with no ambient credentials, filesystem access or outbound network unless separately required and authorized.

**Never** use `pull_request_target` to check out forked PR code and run checks in a privileged job. Avoid `workflow_run` with untrusted artifacts. The included PR workflow is opt-in (`.yml.example`), checkout-only + inspection-only, with read-only GitHub token and pinned Actions. Do not add `--run` to it.

## Remaining risks / non-goals

- Agent JSONL formats evolve. Import is **best effort**, with unknown/ambiguous statuses left unknown. No external real-user corpus has been tested in this environment.
- Source fingerprint is not a supply-chain trust root; Git-ignored files, exclusions, service state, external data, dependencies, and network conditions remain outside it.
- A malicious actor with write access to both reports can forge the JSON and Git SHA metadata. Use trusted CI collection and GitHub-provided expected SHA, not externally submitted reports, for higher assurance.
- The fixed topic vocabulary is an optional *relevance hint only*. Its synthetic-fixture accuracy does not establish production precision. Human confirmation and independent execution remain necessary.
- There is no full OS sandbox, kernel hardening, malware detection, trusted remote attestation, vulnerability scanning, dependency supply-chain validation or secure-by-construction claim.
- Reports may include requirement text, changed file paths, system metadata and source fingerprint. Review and redact before distributing sensitive project reports.
- File/ledger byte limits are best-effort safety guardrails, not guaranteed resource isolation for hostile OS processes.

## Responsible disclosure

Use a private GitHub security advisory after publishing. Do not include secrets or sensitive transcripts in public Issues. Until then, contact the maintainer privately via an appropriate channel.

See [threat model](docs/security/THREAT_MODEL.md) and [validation record](docs/VALIDATION.md).


## v0.6 Isolated Evidence Runner: threat and safety boundaries

- **Host privilege:** Docker access often grants host-root-equivalent capability.
  Prefer rootless Docker, a dedicated VM and a credential-free user. Docker
  containers are NOT a guarantee against container escape or kernel exploits.
- **Image trust:** no implicit image pulls. A chosen, locally installed image is
  resolved to its SHA-256 image ID and that ID is used to launch. Use reviewed,
  minimal images. Image entrypoints are overridden explicitly.
- **Execution restrictions:** `--network=none`, read-only root, read-only
  snapshot mount, non-root UID, dropped capabilities, no-new-privileges,
  limited memory/CPU/PIDs, ephemeral writable work/tmp mounts. No host Docker
  socket or arbitrary host directories are mounted by RAEE-Lite.
- **Source snapshot:** bounded copy of regular files with symlinks rejected.
  `.git`, `.raee`, dependency folders and common secret filenames are omitted.
  Excluded files are surfaced. **Contents of other files are not scanned for
  passwords or API keys:** review dry-run path listing; do not use on private
  repositories without inspecting what will be copied. Concurrent adversarial
  directory replacement is not fully ruled out.
- **Output and provenance:** terminal output is discarded, not persisted.
  Evidence logs image ID and source hash, but local ledger data can be
  modified by anyone with write access. This is not a signed attestation.
- **CI:** ordinary PR workflow stays read-only. Docker execution from forks
  must not be enabled on a privileged runner or using `pull_request_target`.
  `--allow-ci-execution` is an acknowledgement, not an isolation guarantee.
- **Absent Docker:** strictly fail closed. No host execution fallback.
- **Remote Docker:** nonlocal daemon endpoints are rejected. Socket paths and
  named pipes may still be forwarded/proxied; do not treat this as proof that a
  daemon is physically local.
- **Unverified:** actual container runtime behavior on Linux/Mac/Windows Docker,
  rootless integration, CI concurrency, daemon kill/cleanup reliability, and
  professional penetration tests have not been performed in this environment.

Report vulnerabilities privately; do not attach unredacted agent logs, tokens,
credentials, or private source code.

## v0.8 trusted CI provenance integration

- A self-reported `GITHUB_*` environment variable is **not authentication**.
- `ci-export` emits an expressly `UNTRUSTED` digest-bound receipt. It cannot
  sign itself or assert runner identity.
- `ci-verify` delegates actual signature and provenance verification to
  `gh attestation verify` and requires an independently pinned repository,
  workflow, ref and source SHA, rejecting self-hosted runners. Missing CLI,
  invalid artifact, mismatched report bytes, nonzero verifier exit and empty
  verification result fail closed.
- Recommended workflow uses no PR trigger and separates code execution from
  privileged OIDC attestation. Protect signing branch and pin all actions.
- Attestations certify origin and integrity of a claim, not test honesty,
  code security, deployment suitability or freedom from compromised CI.
- Live GitHub Actions / Sigstore integration has not been tested in this
  environment. See docs/TRUSTED_CI.md for operator prerequisites.


See [production trust boundary](docs/PRODUCTION_SECURITY.md) and [live acceptance runbook](docs/GITHUB_LIVE_ACCEPTANCE.md).
