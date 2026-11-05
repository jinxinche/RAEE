#!/usr/bin/env bash
set -euo pipefail
REPO=jinxinche/RAEE
POLICY=.github/branch-protection.json
PYTHON_BIN="${PYTHON:-python3}"
if [[ $# -lt 1 || $# -gt 2 || "$1" != '--solo-maintainer' ]]; then
  echo 'Usage: bash scripts/protect_main.sh --solo-maintainer [--validate|--check|--apply]' >&2; exit 2
fi
ACTION=--check
if [[ $# -eq 2 ]]; then ACTION="$2"; fi
[[ "$ACTION" == '--validate' || "$ACTION" == '--check' || "$ACTION" == '--apply' ]] || exit 2
[[ -f "$POLICY" ]] || { echo 'Run from the reviewed repository checkout' >&2; exit 2; }
"$PYTHON_BIN" - "$POLICY" <<'PY_POLICY'
import json,sys
with open(sys.argv[1],encoding='utf-8') as f:
 d=json.load(f)
r=d.get('required_pull_request_reviews') or {}; c=d.get('required_status_checks') or {}
ok=(type(r.get('required_approving_review_count')) is int
  and r.get('required_approving_review_count')==0
  and r.get('dismiss_stale_reviews') is False
  and r.get('require_code_owner_reviews') is False
  and r.get('require_last_push_approval', False) is False
  and c.get('strict') is True
  and c.get('contexts')==['pr-boundary-inspection', 'Trusted regression gate']
  and d.get('enforce_admins') is True
  and d.get('required_conversation_resolution') is True
  and d.get('allow_force_pushes') is False
  and d.get('allow_deletions') is False
  and d.get('restrictions') is None
  and d.get('block_creations') is False)
if not ok: sys.exit('FAIL CLOSED: reviewed solo-maintainer policy mismatch')
print('Solo-maintainer policy file validated; not yet proof of GitHub settings')
PY_POLICY
echo 'Required checks: pr-boundary-inspection; Trusted regression gate.'
# tests.yml runs on main and maintenance/** pushes. The maintainer must review
# PR code before pushing its head to a maintenance/** branch for regression CI.
echo 'Before merging, obtain both required checks on the reviewed PR head; use a maintenance/** push for regression CI.'
if [[ "$ACTION" == '--validate' ]]; then
  echo 'Local validation only; no GitHub calls made and no protection applied.'
  exit 0
fi
command -v gh >/dev/null || { echo 'GitHub CLI required' >&2; exit 2; }
gh auth status >/dev/null 2>&1 || {
  echo 'GitHub authentication unavailable; stopped without changes. Use --validate for local-only validation.' >&2
  exit 2
}
VISIBILITY="$(gh repo view "$REPO" --json visibility --jq .visibility)"
[[ "$VISIBILITY" == 'PUBLIC' ]] || { echo 'Expected public repository' >&2; exit 2; }
if [[ "$ACTION" == '--apply' ]]; then
  echo 'Applying the reviewed classic branch protection rule (no independent-approval claim)'
  gh api --method PUT "repos/$REPO/branches/main/protection" \
    -H 'Accept: application/vnd.github+json' --input "$POLICY" >/dev/null
fi
PROTECTION_RESPONSE="$(gh api --method GET "repos/$REPO/branches/main/protection" \
  -H 'Accept: application/vnd.github+json')"
"$PYTHON_BIN" -c '
import json,sys
d=json.load(sys.stdin); c=d.get("required_status_checks") or {}; r=d.get("required_pull_request_reviews") or {}
def enabled(x): return (d.get(x) or {}).get("enabled") is True
def disabled(x): return (d.get(x) or {}).get("enabled") is False
contexts=c.get("contexts")
ok=(enabled("enforce_admins") and enabled("required_conversation_resolution")
 and disabled("allow_force_pushes") and disabled("allow_deletions")
 and c.get("strict") is True and isinstance(contexts, list)
 and all(context in contexts for context in ("pr-boundary-inspection", "Trusted regression gate"))
 and type(r.get("required_approving_review_count")) is int
 and r.get("required_approving_review_count") == 0
 and r.get("dismiss_stale_reviews") is False
 and r.get("require_code_owner_reviews") is False
 and r.get("require_last_push_approval", False) is False
 and d.get("restrictions") is None)
if not ok: sys.exit("FAIL CLOSED: GitHub has not confirmed expected branch protection")
print("GitHub classic main protection verified: pr-boundary-inspection and Trusted regression gate required, 0 approvals, force push/deletion blocked.")
print("Inspect repository Rulesets separately; this endpoint does not expose every effective rule.")
' <<<"$PROTECTION_RESPONSE"
