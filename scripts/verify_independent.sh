#!/usr/bin/env bash
# Run on a different machine/account from the CI execution environment.
# Usage: bash scripts/verify_independent.sh <ci-evidence.json> <report.json> <full-commit-sha>
set -euo pipefail
REPO=jinxinche/RAEE
MANIFEST=${1:?Pass the downloaded evidence file}
REPORT=${2:?Pass the matching raw report.json}
SHA=${3:?Pass the independently confirmed full Git commit SHA}
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ && ! "$SHA" =~ ^[0-9a-f]{64}$ ]]; then
  echo 'Expected a FULL git SHA from a trusted source.' >&2; exit 2
fi
command -v gh >/dev/null || { echo 'GitHub CLI required.' >&2; exit 2; }
# CVE-2026-64655: `--signer-workflow` policies can be bypassed with gh <2.97.0.
python3 - <<'PY_GH'
import re,subprocess,sys
try:
    p=subprocess.run(['gh','version'],capture_output=True,text=True,timeout=10,check=True)
    m=re.fullmatch(r'gh version (\d+)\.(\d+)\.(\d+)(?: \(.*\))?',p.stdout.splitlines()[0])
    if not m or tuple(map(int,m.groups()[:3])) < (2,97,0):
        raise RuntimeError('gh 2.97.0 or newer required (CVE-2026-64655)')
except (IndexError,RuntimeError,OSError,subprocess.SubprocessError) as exc:
    sys.exit('FAIL CLOSED: '+str(exc))
PY_GH
[[ -f "$MANIFEST" && -f "$REPORT" ]] || { echo 'Expected manifest and report files.' >&2; exit 2; }
# Do not infer identity or SHA from the untrusted evidence itself.
gh attestation verify "$MANIFEST" \
  --repo "$REPO" \
  --signer-workflow "$REPO/.github/workflows/trusted-evidence.yml" \
  --source-ref refs/heads/main \
  --source-digest "$SHA" \
  --deny-self-hosted-runners
# If the exact published RAEE-Lite version has been installed independently,
# also enforce the embedded bounded claim and optional report hash:
if command -v raee-lite >/dev/null; then
  raee-lite ci-verify \
    --manifest "$MANIFEST" \
    --expected-repo "$REPO" \
    --expected-ref refs/heads/main \
    --expected-sha "$SHA" \
    --expected-workflow .github/workflows/trusted-evidence.yml \
    --report "$REPORT"
else
  # Do not silently skip a necessary hash check. Use an independent bounded
  # JSON parser even when RAEE-Lite is not installed.
  python3 - "$MANIFEST" "$REPORT" <<'PY_REPORT'
import json, hashlib,sys
from pathlib import Path
m=Path(sys.argv[1]); r=Path(sys.argv[2])
if m.is_symlink() or r.is_symlink() or m.stat().st_size>65536 or r.stat().st_size>8000000:
    sys.exit('Rejected unsafe manifest/report file')
obj=json.loads(m.read_bytes()); data=r.read_bytes()
expected=obj['report']
if hashlib.sha256(data).hexdigest()!=expected['sha256'] or len(data)!=expected['bytes']:
    sys.exit('Raw report is not bound to signed evidence!')
print('REPORT_HASH_BINDING_VERIFIED (RAEE semantic checks not installed)')
PY_REPORT
fi
