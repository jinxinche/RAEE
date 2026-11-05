# Isolated Evidence Runner — design and operating notes

`raee-lite isolate --for R1 --kind unit --image python:3.12-slim -- python -m unittest discover -s tests`

## Mechanism

1. Verify the user-declared requirement exists; scope is user-labelled.
2. Fingerprint eligible source files; create a temporary, bounded snapshot of
   regular source files (not symlinks, known secrets or generated directories).
3. Validate source fingerprint stability while preparing the snapshot.
4. Resolve a **preinstalled** Docker image to an immutable local SHA-256 ID.
5. Copy from read-only snapshot mount into a writable tmpfs inside a restricted
   offline container, running the check as a non-root UID. No host project scripts
   are run by the tool itself.
6. Attempt to terminate and remove the container after execution/timeout.
7. Fingerprint original source again; append a non-signed evidence receipt with
   code/source snapshot digests, image ID and environment restrictions.
8. Show evidence role in report separately from unverified Agent transcript claims.

## Running safely

- Prefer rootless Docker under a disposable, credential-free VM.
- Use only reviewed images with expected interpreters/tools already installed.
- Preview with `--dry-run`, inspect paths copied, then run only on code you have
  permission to examine and execute. Never blindly install PR dependencies.
- Never enable Docker socket access or `--allow-ci-execution` on public fork PRs.
- Reports are local observations, not signed attestations. No test output retained.
- Docker is Linux-container oriented; images need `/bin/sh` and `cp` available.
- For sensitive projects, use an isolated machine. Default filters cannot find
  embedded secrets within source code or arbitrary private filenames.

## What the tool cannot guarantee

- Security against a malicious kernel, Docker daemon or container breakout.
- Complete secret detection, snapshot fidelity to every runtime dependency,
  protection against simultaneous directory changes by an active attacker.
- Correctness of a project, coverage of requirements, secure dependencies or
  comparability with a different environment.
- Cryptographic integrity of evidence ledger (a writable JSON file).

## Limits and failure semantics

- No Docker -> fail closed, no receipt.
- Missing local image -> fail closed, no receipt.
- Non-local Docker endpoint -> fail closed, no receipt.
- Snapshot too large / unsafe file -> fail closed, no receipt.
- Docker run exit 124/125/126/127 -> `infrastructure_error`, not pass.
- Non-zero command -> `fail` with exit code, not pass.
- Source changed after snapshot -> old evidence is stale.
- Suppressed stdout/stderr means developers may need a *separate trusted debug
  run* to diagnose a failure. Retaining untrusted output requires new security work.
