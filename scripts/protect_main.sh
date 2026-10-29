#!/usr/bin/env bash
# REQUIRE an independent maintainer with write access before enforcing one approval.
set -euo pipefail
REPO=jinxinche/RAEE
if [[ "${1:-}" != '--independent-reviewer-ready' ]]; then
  echo 'Blocked: set up an independent reviewer/collaborator first.' >&2
  echo 'Usage: bash scripts/protect_main.sh --independent-reviewer-ready' >&2
  echo 'You cannot approve your own pull request. One required approval can otherwise lock you out.' >&2
  exit 2
fi
command -v gh >/dev/null || exit 2
gh auth status >/dev/null
REPO_VISIBILITY=$(gh repo view "$REPO" --json visibility --jq .visibility)
if [[ "$REPO_VISIBILITY" != PUBLIC ]]; then
  echo 'Repo must be PUBLIC for this plan and public-good attestation.' >&2; exit 2
fi
# No rewrite of repository files, only branch rules.
gh api --method PUT "repos/$REPO/branches/main/protection" \
  -H 'Accept: application/vnd.github+json' \
  --input .github/branch-protection.json > /dev/null
printf 'Branch protection policy submitted. Inspect settings at https://github.com/%s/settings/branches\n' "$REPO"
gh api "repos/$REPO/branches/main/protection" --jq '{enforce_admins,required_status_checks,required_pull_request_reviews}'
