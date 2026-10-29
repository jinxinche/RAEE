# RAEE-Lite: GitHub live acceptance runbook (v0.10.0rc2)

## Observed state as of 2026-10-29

- The authenticated GitHub account was verified as `jinxinche`.
- The public `jinxinche/RAEE` repository now exists. Real cloud acceptance is still required.
- The connected GitHub API exposes repository file/branch/PR operations, but **not** new-repository creation or protection-rule management.
- The present development environment has no authenticated GitHub CLI or independent GitHub Actions runner.
- **No public repository, protected branch, live attestation, independent live verification, or live three-OS cloud run has been observed yet.**
- All example status badges or claims of production trust are prohibited until the acceptance evidence below exists.

## Step 0: Publication review

Unzip source. Review the full source and all workflow files; check for IP, personal or medical data, hard-coded credentials, and license obligations. Run a separate secret scanner (e.g., gitleaks) and inspect Git history. `preflight_public.py` is a **minimal** blocklist, not a comprehensive scanner.

## Step 1: Create a dedicated PUBLIC repository

Authenticate GitHub CLI from your OWN workstation with `gh auth login`. In an unpacked, reviewed source tree:

```bash
bash scripts/publish_existing_repo.sh
```

This creates `jinxinche/RAEE`, uploads the reviewed source and returns its repository URL. It refuses a previously initialized Git tree or already-existing repository. It does **not** silently change any other project.

> Do not upload the former research repositories or any transcripts. Only synthetic fixtures are included.

## Step 2: Enable main protection and external review

**First invite at least one trusted, independent collaborator with write/review permissions**. The author cannot approve their own PR. Requiring one approval before adding a reviewer can block changes even for the owner.

Then run:

```bash
bash scripts/protect_main.sh --independent-reviewer-ready
```

This submits `.github/branch-protection.json` (required PR, one reviewer, dismiss stale approvals, admins enforced, `pr-static-safety` check, no force push/delete). Inspect [Branch Settings](https://github.com/jinxinche/RAEE/settings/branches) and confirm the effective rule. If GitHub rejects a required-check context that has never run, first create a disposable fork PR to populate that status, then reapply the exact protection policy. Keep the branch protected before signing.

Also configure repository Settings > Actions > General with default `GITHUB_TOKEN` **read-only** permissions and no untrusted workflow approval bypass. Do not expose repository secrets to fork PRs.

## Step 3: Trusted Linux / Windows / macOS

`.github/workflows/tests.yml` runs six trusted checks (3 OS x 2 Python versions), only on `push` to `main` or manual dispatch. Before citing portability, open the workflow run and record **six job conclusions**, Git SHAs, run URL, and dates. The first push **before branch protection** does not qualify as protected-branch evidence; rerun the matrix on the protected main branch.

```bash
gh workflow run tests.yml --repo jinxinche/RAEE --ref main
# Find the new run in the Actions tab and inspect each job's conclusion.
```

## Step 4: Actual Artifact Attestation from protected main

**After the protection settings are confirmed**, run:

```bash
gh workflow run trusted-evidence.yml --repo jinxinche/RAEE --ref main
```

The `collect` job executes audited tests with `contents: read` only, and exports a bounded claim. The `sign` job has OIDC/attestation permissions and no checkout, using the official `actions/attest` action pinned to v4.2.2. Download the resulting `independently-verifiable-evidence` artifact and **never treat the JSON alone as authenticated**.

For user-accessible artifacts, find the run in Actions, download `independently-verifiable-evidence.zip`, extract it into a separate directory and inspect `ci-evidence.json`, `report.json` and the Sigstore bundle. The GitHub release candidate intentionally does not enable automatic deployment or publishing.

## Step 5: Independently verify (fresh workstation / container)

Install a trusted current `gh` CLI separately from the project. Determine a **full** Git commit SHA independently from GitHub's `main` branch, never copied from untrusted JSON. In the directory containing the extracted `ci-evidence.json`:

```bash
bash scripts/verify_independent.sh ci-evidence.json report.json FULL_40_CHAR_GIT_SHA
```

The verifier pins `--repo`, `--signer-workflow`, `--source-ref`, `--source-digest`, and `--deny-self-hosted-runners`. Optionally install the audited RAEE-Lite CLI independently for additional manifest semantic checks. Collect the CLI version, SHA, redacted verification output, and successful exit status. Verify negative controls by changing one byte of a copied manifest (must fail) and specifying a wrong full source SHA (must fail).

GitHub attestation says **what workflow signed which bytes**, not that the code, tests, or environment are mathematically guaranteed correct.

## Step 6: Fork PR security boundary experiment

Use an unprivileged fork account and propose a PR that changes a harmless file; verify `pr-static-safety` succeeds, there are no `id-token: write` or signing jobs, and no PR script executes. Submit a second PR changing `.github/workflows/` or `scripts/pr_boundary.py` and confirm it **fails closed**. Ensure the required reviewer and merge restrictions block unapproved merge. Use throwaway fixtures only, no real secrets or live attack payloads.

## Acceptance record (fill from ACTUAL GitHub data)

| Gate | Required evidence | Current |
|---|---|---|
| Public dedicated repo | real `https://github.com/jinxinche/RAEE` accessible | NOT VERIFIED |
| Main protected | repository-protection API/UI confirmation, required review/check | NOT VERIFIED |
| CI signer | Actions run URL, expected main SHA, attestation ID | NOT VERIFIED |
| Independent proof | `gh attestation verify` output from separate machine | NOT VERIFIED |
| Ubuntu / Windows / macOS | actual per-job conclusions for protected main | NOT VERIFIED |
| Fork boundary | actual low-privilege PR run, rejection of security-file edits | NOT VERIFIED |

Update this table only with linked run/PR evidence; never report synthetic tests as live successes.

## RC2 security acceptance details

- Use `gh version` **2.97.0 or newer**. Earlier versions have CVE-2026-64655 affecting `--signer-workflow` matching.
- Transfer ONLY handoff/ci-evidence.json and handoff/report.json between the low-privilege collector and signer; never upload all of `.raee/`.
- Verify both a wrong expected SHA (must fail) and a modified report.json (must fail) on an independent machine.
- If a live run fails, preserve its URL and issue, and do not mark its acceptance row as passed.
