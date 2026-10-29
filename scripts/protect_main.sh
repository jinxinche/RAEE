#!/usr/bin/env bash
set -euo pipefail
REPO=jinxinche/RAEE
POLICY=.github/branch-protection.json
if [[ $# -lt 1 || "$1" != '--solo-maintainer' ]]; then
  echo 'Usage: bash scripts/protect_main.sh --solo-maintainer [--check|--apply]' >&2; exit 2
fi
ACTION=--check
if [[ $# -gt 1 ]]; then ACTION="$2"; fi
[[ "$ACTION" == '--check' || "$ACTION" == '--apply' ]] || exit 2
[[ -f "$POLICY" ]] || { echo 'Run from the reviewed repository checkout' >&2; exit 2; }
python3 - "$POLICY" <<'PY_POLICY'
import json,sys
with open(sys.argv[1],encoding='utf-8') as f:
 d=json.load(f)
r=d.get('required_pull_request_reviews') or {}; c=d.get('required_status_checks') or {}
ok=(r.get('required_approving_review_count')==0
  and r.get('require_code_owner_reviews') is False
  and c.get('strict') is True
  and c.get('contexts')==['pr-boundary-inspection']
  and d.get('enforce_admins') is True
  and d.get('required_conversation_resolution') is True
  and d.get('allow_force_pushes') is False
  and d.get('allow_deletions') is False)
if not ok: sys.exit('FAIL CLOSED: reviewed solo-maintainer policy mismatch')
print('Solo-maintainer policy file validated; not yet proof of GitHub settings')
PY_POLICY
command -v gh >/dev/null || { echo 'GitHub CLI required' >&2; exit 2; }
gh auth status >/dev/null
VISIBILITY="$(gh repo view "$REPO" --json visibility --jq .visibility)"
[[ "$VISIBILITY" == 'PUBLIC' ]] || { echo 'Expected public repository' >&2; exit 2; }
if [[ "$ACTION" == '--apply' ]]; then
  echo 'Applying the reviewed classic branch protection rule (no independent-approval claim)'
  gh api --method PUT "repos/$REPO/branches/main/protection" \
    -H 'Accept: application/vnd.github+json' --input "$POLICY" >/dev/null
fi
gh api "repos/$REPO/branches/main/protection" | python3 -c '
import json,sys
d=json.load(sys.stdin); c=d.get("required_status_checks") or {}; r=d.get("required_pull_request_reviews") or {}
def enabled(x): return (d.get(x) or {}).get("enabled") is True
def disabled(x): return (d.get(x) or {}).get("enabled") is False
ok=(enabled("enforce_admins") and enabled("required_conversation_resolution")
 and disabled("allow_force_pushes") and disabled("allow_deletions")
 and c.get("strict") is True and "pr-boundary-inspection" in (c.get("contexts") or [])
 and r.get("required_approving_review_count") == 0)
if not ok: sys.exit("FAIL CLOSED: GitHub has not confirmed expected branch protection")
print("GitHub classic main protection verified: inspection required, 0 approvals, force push/deletion blocked.")
print("Inspect repository Rulesets separately; this endpoint does not expose every effective rule.")
'
