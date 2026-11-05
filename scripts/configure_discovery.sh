#!/usr/bin/env bash
# GitHub discoverability metadata (public repo). Never buy stars or send messages.
# Explicit --apply opt-in; --check is read-only. Requires authenticated gh CLI.
set -euo pipefail
REPO='jinxinche/RAEE'
DESC='Offline evidence firewall for AI-assisted coding. Track what was checked, what changed, and what remains unverified.'
HOMEPAGE='https://github.com/jinxinche/RAEE#readme'
if [[ "$#" -ne 1 || ( "$1" != '--check' && "$1" != '--apply' ) ]]; then
  echo 'Usage: bash scripts/configure_discovery.sh --check|--apply' >&2
  exit 2
fi
command -v gh >/dev/null || { echo 'GitHub CLI (gh) is required.' >&2; exit 2; }
gh auth status >/dev/null
if [[ "$1" == '--apply' ]]; then
  [[ "$(gh repo view "$REPO" --json visibility --jq .visibility)" == 'PUBLIC' ]] ||
    { echo 'Expected public GitHub repository.' >&2; exit 2; }
  gh repo edit "$REPO" --description "$DESC" --homepage "$HOMEPAGE"
  gh api --method PUT "repos/$REPO/topics" -H 'Accept: application/vnd.github+json' --input - <<'TOPICS'
{"names":["ai-coding","coding-agents","developer-tools","code-review","testing","verification","cli","python","reproducibility","trustworthy-ai"]}
TOPICS
fi
echo 'GitHub REST metadata returned by the service (not inferred from README):'
gh api "repos/$REPO" --jq '{name, description, homepage, private}'
gh api "repos/$REPO/topics" --jq '.names'
echo 'Note: GitHub Social preview still requires a reviewed image uploaded through repository Settings.'
