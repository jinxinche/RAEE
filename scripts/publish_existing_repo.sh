#!/usr/bin/env bash
# Publish reviewed RC code to a PR branch in the user's existing repository.
# Requires locally authenticated GitHub CLI, Git, Python. Never merges or pushes main.
set -euo pipefail
REPO='jinxinche/RAEE'
BRANCH='release/raee-lite-v0.10.0rc2'
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for name in gh git python3; do command -v "$name" >/dev/null || { echo "Missing $name" >&2; exit 2; }; done
gh auth status >/dev/null
[[ "$(gh repo view "$REPO" --json visibility --jq .visibility)" == PUBLIC ]] || { echo 'Expected public repository' >&2; exit 2; }
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
gh repo clone "$REPO" "$WORK/repo"
cd "$WORK/repo"
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  git fetch origin "$BRANCH"
  git checkout -B "$BRANCH" "origin/$BRANCH"
else
  git checkout -b "$BRANCH" origin/main
fi
for item in src tests scripts benchmarks examples validation_corpus .github CHANGELOG.md CONTRIBUTING.md SECURITY.md ROADMAP.md pyproject.toml .gitignore; do
  [[ -e "$SOURCE/$item" ]] || { echo "Missing $item in release candidate" >&2; exit 2; }
  rm -rf -- "$item"
  cp -R -- "$SOURCE/$item" "$item"
done
mkdir -p docs
for file in "$SOURCE"/docs/*; do
  name="$(basename "$file")"
  case "$name" in README.zh-CN.md|README.de-DE.md|README.es-ES.md) continue;; esac
  cp -R -- "$file" docs/
done
# Preserve the existing repository's curated multilingual README, license,
# research citation and BibTeX. Change only the stale status wording.
python3 - <<'PY_RELEASE_README'
from pathlib import Path
p = Path('README.md')
s = p.read_text()
s = s.replace('**Publication status:** This newly created public repository is being prepared for its first source release. The CLI source and installable package are **not yet published in this repository**. The commands below document the development candidate\'s intended local workflow; do not treat them as an install-from-GitHub instruction yet.', '**Release status:** RAEE-Lite v0.10.0rc2 source is included in this release candidate. The security audit and GitHub CI provenance have not yet been independently completed.')
s = s.replace('After installing the release candidate from a reviewed local source package:', 'After installing this checked-out source candidate with `python -m pip install .`:')
s = s.replace('**Current status: documentation and first public release preparation.**', '**Current status: source release candidate; external acceptance testing pending.**')
p.write_text(s)
PY_RELEASE_README
python3 -m compileall -q src
PYTHONPATH=src python3 -c 'import raee_lite.cli; print("RAEE-Lite CLI import OK")'
git add -A
if git diff --cached --quiet; then echo 'No source changes to publish'; exit 0; fi
git commit -m 'feat: publish RAEE-Lite v0.10.0rc2 source and CI candidate'
git push -u origin "$BRANCH"
if gh pr view "$BRANCH" --repo "$REPO" >/dev/null 2>&1; then
  gh pr view "$BRANCH" --repo "$REPO" --json url --jq .url
else
  gh pr create --repo "$REPO" --head "$BRANCH" --base main \
    --title 'Release RAEE-Lite v0.10.0rc2 source, tests and CI' \
    --body 'Full source, smoke tests, and low-permission CI for human review. This is a release candidate, not a completed trusted CI attestation or external audit. Existing four-language README, CITATION.cff, and RAEE research preprint citation are preserved.'
fi
