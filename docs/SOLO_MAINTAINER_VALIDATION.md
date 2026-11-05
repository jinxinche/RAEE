# RAEE-Lite v0.10.0rc2 — solo-maintainer review record

**Historical scope:** Preliminary AI-assisted technical inspection of PR #2 by ChatGPT using the maintainer's connected GitHub account, plus local release-candidate tests. **Not an independent human security review; not a maintainer's personal sign-off.** Prepared 2026-10-29; integration status updated 2026-11-05.

**Original decision (2026-10-29):** CONDITIONAL / NOT YET RELEASE READY. The recommendation then was to keep PR #2 unmerged until actual branch protection was confirmed and the maintainer explicitly accepted the 16 trust-boundary changes. A successful inspection job meant **inventory completed**, not approval. The merge-pending status is superseded by the update below; this record does not establish that the original acceptance conditions were met.

## Integration and validation update — 2026-11-05

The earlier PR stack, including PR #2, is merged into `main` at [`5a8cc702674a5e4005f0efe3891b39727c5f7897`](https://github.com/jinxinche/RAEE/commit/5a8cc702674a5e4005f0efe3891b39727c5f7897). [Main CI run 41978577201](https://github.com/jinxinche/RAEE/actions/runs/41978577201) passed all six OS/Python jobs, with 268 tests reported per job. Main integration and this baseline matrix are therefore completed historical milestones.

Candidate validation is tied to the exact PR head: consult its description and Checks tab for completed local and hosted results. The expanded matrix contains twelve jobs; workflow declarations alone do not establish success. Total and per-module minima live in [`scripts/run_reviewed_suite.py`](../scripts/run_reviewed_suite.py). See the [2026-11-05 engineering audit](ENGINEERING_AUDIT_2026-11-05.md) for changes and remaining acceptance work. A green matrix does not establish live branch protection, independent review or dependency closure.

Windows exceptions are enumerated by exact test ID in `WINDOWS_CRITICAL_SKIPS`. The allowlist size is not an observed skip count: retain actual per-job summaries and logs. POSIX runners must execute the corresponding permission, FIFO and process-group coverage; the exception list does not authorize POSIX skips.

**Current disposition:** The merged baseline has hosted regression evidence; trusted production release acceptance remains unverified. Neither a merge nor a green matrix proves live branch protection, enforced required checks, independent review, real GitHub provenance verification, or an actual fork-permission exercise. The bounded static dependency audit remains advisory and does not prove dependency closure or rewrite historical receipts.

## Evidence actually inspected in the original review

1. GitHub [PR #2](https://github.com/jinxinche/RAEE/pull/2), its changed-file list, source in `release/raee-lite-v0.10.0rc2`, and the PR workflow.
2. [GitHub Actions run 40836793496](https://github.com/jinxinche/RAEE/actions/runs/40836793496): `pr-boundary-inspection` **success**, while explicitly warning `REVIEW REQUIRED` for 16 security-sensitive paths.
3. [PR #3](https://github.com/jinxinche/RAEE/pull/3) bootstrapped the trusted `main` inspector; the Git blob matched the PR #2 inspector.
4. Local RC2 source: all **184 tests across 14 unittest modules** passed when executed separately. A combined regression invocation in this environment exceeded the tool time limit, therefore a single complete uninterrupted runner pass is **not** claimed. These local results are not a substitute for the exact GitHub commit's cross-platform tests.
5. Checked: `.github/workflows/pr-boundary.yml`, `tests.yml`, `trusted-evidence.yml`, `pr-evidence-example.yml.example`, `CODEOWNERS`, `.github/branch-protection.json`, `pyproject.toml`, selected executable scripts, `ci_attestation.py`, and source tests. This was targeted review, not exhaustive formal verification or complete secret scanning.

## 16 sensitive paths flagged in the original review

- GitHub governance: `.github/CODEOWNERS`, `.github/branch-protection.json`
- GitHub workflows: `.github/workflows/pr-boundary.yml`, `.github/workflows/pr-evidence-example.yml.example`, `.github/workflows/tests.yml`, `.github/workflows/trusted-evidence.yml`, `.github/workflows/trusted-evidence.yml.example`
- Packaging: `pyproject.toml`
- Executable scripts: `scripts/create_public_repo.sh`, `scripts/local_pr_attack_smoke.py`, `scripts/preflight_public.py`, `scripts/protect_main.sh`, `scripts/publish_existing_repo.sh`, `scripts/run_reviewed_suite.py`, `scripts/verify_independent.sh`
- Provenance code: `src/raee_lite/ci_attestation.py`

At the original review, `scripts/pr_boundary.py` no longer appeared in the changed-path list because its exact content was already on `main`; that description did not verify effective branch protection.

## Historical findings — 2026-10-29

The observations below retain their original review scope. Statements about missing runs, workflow triggers, connector access or owner acceptance describe that inspection, not a fresh check of the current candidate. The update above supersedes the missing baseline-matrix and pending-integration status.

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

## Original disposition and outstanding acceptance

**Originally pending (2026-10-29):** owner review of flagged changes; effective rules confirmation; safe PR merge; six real cross-platform jobs; independent provenance verification; real fork PR permission exercise.

**Updated (2026-11-05):** The earlier stack is merged and the six-job main baseline passed. Candidate run outcomes are recorded against the exact PR head in its Checks tab. Owner acceptance and independent review, effective rules and required-check enforcement, independent provenance verification, and an actual fork PR permission exercise still require their own evidence. A green inventory or baseline matrix does not establish production security.
