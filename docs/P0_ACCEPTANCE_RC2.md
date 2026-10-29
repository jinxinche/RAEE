# RAEE-Lite RC2 — P0 Acceptance Ledger

Verified locally on 2026-10-29 (Linux, Python 3.13.5). The following **are not live production trust claims**.

| Gate | Local evidence | GitHub / independent evidence | Status |
|---|---|---|---|
| Dedicated public repository | Release archive prepared | GitHub `jinxinche/RAEE` returned 404 when checked in the connected account | BLOCKED — creation not supported by the connector |
| Protected main / required review | Protection policy and bootstrap script exist | No GitHub rules API confirmation | NOT VERIFIED |
| Real GitHub `actions/attest` | Verified workflow YAML and corrected exact artifact handoff | No GitHub signed bundle or run URL | NOT VERIFIED |
| Independent provenance verification | gh >=2.97 gate, exact workflow/ref/SHA flags, matching report digest, negative tests | No actual signed GitHub artifact to verify and no gh CLI in environment | NOT VERIFIED |
| Cross-platform Python | Linux local tests pass; Linux/Windows/macOS workflow defined | No actual six GitHub hosted job results | NOT VERIFIED |
| Fork PR safety | Five local adverse-boundary scenarios passed, workflow uses read-only token | No independently operated fork or GitHub run URL | NOT VERIFIED |
| Real Codex/Claude compatibility | Six labelled synthetic fixtures agree with parser; unknown exits retained | Zero consented user logs | NOT VERIFIED |
| Real requirement-test accuracy | Existing synthetic label examples only | No independently labelled held-out real set | NOT VERIFIED |
| Docker isolated execution | Local runner design and unit tests | Docker daemon absent; no rootless container end-to-end run | NOT VERIFIED |
| External penetration test | Unit tests and local threat-model review | No independent professional test | NOT VERIFIED |

## Local fixes confirmed in RC2

1. `ci-verify` refuses GitHub CLI versions older than 2.97.0 to mitigate CVE-2026-64655 (GitHub Security Advisory GHSA-mm27-mwq9-fr5g).
2. `trusted-evidence.yml` no longer tries to upload the hidden `.raee/` path, which `actions/upload-artifact` v4.4+ excludes by default. It moves only `ci-evidence.json` and `report.json` into the explicit non-hidden handoff.
3. Independent verification compares the original report bytes with the digest in the officially attested manifest; failed or absent report is not represented as verified.
4. New symlinks in an untrusted PR are flagged for review without following them; untrusted Python content was not executed by the scanner in local smoke tests.
5. Current output: 184/184 local automated tests passed; independent installation into a clean virtual environment succeeded; 5/5 local PR boundary scenarios behaved as expected.

## Exact external completion path

- Owner creates a new, empty **public** `jinxinche/RAEE` repository; reviews the release contents for secrets and license obligations before pushing.
- Invite an independent trusted reviewer; apply branch protection from `.github/branch-protection.json`, confirm with repository UI/API, require `pr-static-safety` and independent approval.
- After protection is effective, run `.github/workflows/tests.yml`; record actual job IDs and six conclusions (Linux/Windows/macOS × Python 3.10/3.13).
- Dispatch `.github/workflows/trusted-evidence.yml` from protected main; retain signed bundle, `ci-evidence.json`, `report.json`, run URL and full commit SHA.
- From a **separate** trusted environment with GitHub CLI **>=2.97.0**, run `bash scripts/verify_independent.sh ci-evidence.json report.json FULL_SHA`. Test tampering with report, wrong expected SHA and wrong signer (must reject).
- Open an unprivileged fork PR and attempt safe controlled changes (ordinary file, workflow file, new symlink). Confirm permissions and actual job results.
- Add version-stratified, consented redacted real logs with independently reviewed labels, publish uncertainty intervals and failure categories. Never upload raw private logs or tokens.

**Release gate: NO-GO for trusted-v1.0.** RC2 is a usable local preview, not a field-validated or security-certified product. A real signing chain, real-world data and independent reviewer are not substitutes for each other.
