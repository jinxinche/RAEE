# RAEE-Lite v0.10.0rc2 — solo-maintainer review record

**Scope:** Preliminary AI-assisted technical inspection of PR #2 by ChatGPT using the maintainer's connected GitHub account, plus local release-candidate tests. **Not an independent human security review; not a maintainer's personal sign-off.** Prepared 2026-10-29.

**Decision:** CONDITIONAL / NOT YET RELEASE READY. PR #2 must remain unmerged until actual branch protection is confirmed and the maintainer explicitly accepts the 16 trust-boundary changes. A successful inspection job means **inventory completed**, not approval.

## Evidence actually inspected

1. GitHub [PR #2](https://github.com/jinxinche/RAEE/pull/2), its changed-file list, source in `release/raee-lite-v0.10.0rc2`, and the PR workflow.
2. [GitHub Actions run 40836793496](https://github.com/jinxinche/RAEE/actions/runs/40836793496): `pr-boundary-inspection` **success**, while explicitly warning `REVIEW REQUIRED` for 16 security-sensitive paths.
3. [PR #3](https://github.com/jinxinche/RAEE/pull/3) bootstrapped the trusted `main` inspector; the Git blob matched the PR #2 inspector.
4. Local RC2 source: all **184 tests across 14 unittest modules** passed when executed separately. A combined regression invocation in this environment exceeded the tool time limit, therefore a single complete uninterrupted runner pass is **not** claimed. These local results are not a substitute for the exact GitHub commit's cross-platform tests.
5. Checked: `.github/workflows/pr-boundary.yml`, `tests.yml`, `trusted-evidence.yml`, `pr-evidence-example.yml.example`, `CODEOWNERS`, `.github/branch-protection.json`, `pyproject.toml`, selected executable scripts, `ci_attestation.py`, and source tests. This was targeted review, not exhaustive formal verification or complete secret scanning.

## 16 sensitive paths requiring maintainer acknowledgement

- GitHub governance: `.github/CODEOWNERS`, `.github/branch-protection.json`
- GitHub workflows: `.github/workflows/pr-boundary.yml`, `.github/workflows/pr-evidence-example.yml.example`, `.github/workflows/tests.yml`, `.github/workflows/trusted-evidence.yml`, `.github/workflows/trusted-evidence.yml.example`
- Packaging: `pyproject.toml`
- Executable scripts: `scripts/create_public_repo.sh`, `scripts/local_pr_attack_smoke.py`, `scripts/preflight_public.py`, `scripts/protect_main.sh`, `scripts/publish_existing_repo.sh`, `scripts/run_reviewed_suite.py`, `scripts/verify_independent.sh`
- Provenance code: `src/raee_lite/ci_attestation.py`

`scripts/pr_boundary.py` no longer appears in the changed-path list since its exact content is already on trusted `main`.

## Findings

### Positive, but bounded observations
- The PR inventory executes the baseline inspector and treats the PR head as **data**; it does not install or execute PR-head Python files in the scanner step.
- No `pull_request_target` trigger, OIDC permission, or attestation write permission is present in the active PR inspection job.
- Cross-platform test jobs are scoped to trusted `main` push/manual dispatch and use `contents: read`.
- The attestation workflow separates a read-only collect job from an OIDC-enabled sign job; the sign job has no source checkout, and artifacts use an allowlisted handoff.
- A version floor and expected repository/workflow/commit/ref checks are implemented in the independent attestation verifier. Their real cloud behavior is not yet verified.
- The candidate protection policy specifies PR-based merging, `pr-boundary-inspection` as a required check, zero external approvals during solo maintenance, admin enforcement, discussion resolution, and no force push/deletion. **A JSON file is not an applied GitHub rule.**

### Material residual risks / limitations
- **P0, live enforcement unknown:** No accessible GitHub connector action returns effective branch protection or rulesets; the Browser extension is not connected in this chat. Do not claim `main` is protected.
- **P0, release acceptance pending:** CI job `pr-boundary-inspection` is **only a completed static inventory** and explicitly warns on the 16 paths. It is not a code safety or security quality gate.
- **P0, real CI missing:** No observed Linux/Windows/macOS matrix on protected `main`, no official cloud Artifact Attestation, and no independent `gh attestation verify` result.
- **P1, event model:** GitHub documents that `pull_request` workflows can be sourced from PR-controlled merge commits. Its read-only token limits damage, but a green check originating in a PR-controlled workflow must not be treated as proof of trusted workflow integrity. Consider a base-owned, read-only `pull_request_target` inventory in a future reviewed change, **never** executing PR code under privileged context.
- **P1, scan scope:** Basic file/path risk inventory is not a dependency review, comprehensive secret scan, or guarantee against hidden malicious behavior.
- **P1, human acceptance:** The owner has not yet confirmed the files or signed off this review. No independent reviewer has approved this PR.

## Applying solo-maintainer protection

After verifying the reviewed candidate script and policy in the repository checkout, an authenticated owner can run:

```bash
bash scripts/protect_main.sh --solo-maintainer --apply
bash scripts/protect_main.sh --solo-maintainer --check
```

The script validates the policy's safety-critical fields and reads back GitHub's classic protection response. This is a proposed operational step, **not an operation already performed**. Inspect Settings → Rules → Rulesets separately. Do not overwrite other active rules casually.

## Final disposition

**Pending:** owner review of flagged changes; effective rules confirmation; safe PR merge; six real cross-platform jobs; independent provenance verification; real Fork PR permission exercise. A green inventory alone does not authorize merging or establish production security.
