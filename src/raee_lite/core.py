"""Offline evidence ledger. No LLM, network, or auto-executed tests."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from .safe_io import safe_read_json, write_json as atomic_json
from .evidence_binding import intent_digest
from .safe_process import run as bounded_run
from datetime import datetime, timezone
from pathlib import Path

EXCLUDE_DIRS = {
    ".git", ".raee", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next", "dist", "build",
    ".tox", ".idea", ".vscode", ".DS_Store",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
MAX_FILE_BYTES = 5_000_000
MAX_FILES = 5_000
MAX_HASH_BYTES = 64_000_000
MANIFEST = Path(".raee") / "manifest.json"
LEDGER = Path(".raee") / "ledger.json"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, default=None):
    result = safe_read_json(path, default)
    if path.name == 'ledger.json' and isinstance(result, dict):
        entries = result.get('runs', [])
        if not isinstance(entries, list) or len(entries) > 2000 or any(not isinstance(x, dict) for x in entries):
            raise ValueError('Invalid or oversized local evidence ledger (max 2,000 runs)')
    return result


def write_json(path: Path, obj) -> None:
    atomic_json(path, obj)


def paths(root: Path) -> list[Path]:
    """Bounded source enumeration: at most MAX_FILES+1 paths in memory.

    The extra sentinel marks incomplete enumeration instead of silently claiming
    all source files were fingerprinted. Git-ignored inputs are NOT inspected.
    """
    git = shutil.which('git')
    if git and (root / '.git').exists():
        proc = None
        out = []
        partial = bytearray()
        try:
            proc = subprocess.Popen([git, 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                                    cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            assert proc.stdout is not None
            while len(out) <= MAX_FILES:
                data = proc.stdout.read(65536)
                if not data:
                    break
                partial.extend(data)
                while b'\x00' in partial:
                    raw, _, tail = partial.partition(b'\x00')
                    partial = bytearray(tail)
                    if not raw:
                        continue
                    p = Path(os.fsdecode(bytes(raw)))
                    if (p.is_absolute() or '..' in p.parts or any(v in EXCLUDE_DIRS for v in p.parts)
                        or p.suffix in EXCLUDE_SUFFIXES):
                        continue
                    path = root / p
                    if path.is_file() and not path.is_symlink():
                        out.append(path)
                        if len(out) > MAX_FILES:
                            break
                if len(partial) > 1_000_000:
                    out.append(root / '.raee-enumeration-overflow')
                    break
            if len(out) > MAX_FILES:
                proc.kill()
                proc.wait(timeout=10)
                return sorted(out, key=lambda v: v.as_posix())
            return_code = proc.wait(timeout=15)
            if return_code == 0:
                return sorted(out, key=lambda v: v.as_posix())
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            if proc is not None:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
                if proc.stdout is not None:
                    proc.stdout.close()
    out = []
    for folder, directories, filenames in os.walk(root, followlinks=False):
        directories[:] = [d for d in directories if d not in EXCLUDE_DIRS and not (Path(folder) / d).is_symlink()]
        for filename in filenames:
            p = Path(folder) / filename
            if p.suffix not in EXCLUDE_SUFFIXES and not p.is_symlink():
                out.append(p)
                if len(out) > MAX_FILES:
                    return sorted(out, key=lambda v: v.as_posix())
    return sorted(out, key=lambda v: v.as_posix())


def fingerprint(root: Path) -> dict:
    """Aggregate content digests for eligible source files; mark skipped files explicitly."""
    digest = hashlib.sha256()
    skipped = []
    files = paths(root)
    hashed_bytes = 0
    for i, file in enumerate(files):
        relative = file.relative_to(root).as_posix()
        if i >= MAX_FILES:
            skipped.append({"file": relative, "reason": "file_count_limit"})
            continue
        try:
            n = file.stat().st_size
            if n > MAX_FILE_BYTES:
                skipped.append({"file": relative, "reason": "file_size_limit", "bytes": n})
                continue
            if hashed_bytes + n > MAX_HASH_BYTES:
                skipped.append({"file": relative, "reason": "total_hash_byte_budget", "bytes": n})
                continue
            contents = file.read_bytes()
            hashed_bytes += len(contents)
        except OSError:
            skipped.append({"file": relative, "reason": "unreadable"})
            continue
        digest.update(relative.encode("utf-8", errors="replace") + b"\x00")
        digest.update(hashlib.sha256(contents).digest())
    # Skip records participate in the digest; still report that full proof is unavailable.
    digest.update(json.dumps(skipped, sort_keys=True).encode())
    return {"sha256": digest.hexdigest(), "files": min(len(files), MAX_FILES), "skipped": skipped,
            "scope_note": "Git-ignored/externally supplied inputs and excluded folders are not fingerprinted."}


def git_context(root: Path) -> dict:
    git = shutil.which("git")
    if not git or not (root / ".git").exists():
        return {"available": False}
    head = subprocess.run([git, "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False, timeout=15)
    status = subprocess.run([git, "status", "--porcelain", "--untracked-files=normal"], cwd=root, capture_output=True, text=True, check=False, timeout=15)
    return {"available": head.returncode == 0 and status.returncode == 0,
            "head": head.stdout.strip() if head.returncode == 0 else None,
            "changed_paths": status.stdout.splitlines()[:200] if status.returncode == 0 else [],
            "changed_paths_truncated": len(status.stdout.splitlines()) > 200}


def get_manifest(root: Path) -> dict:
    m = read_json(root / MANIFEST)
    if not isinstance(m, dict):
        raise ValueError("Not initialized: run `raee-lite init` first")
    reqs = m.get('requirements', [])
    bounds = m.get('boundaries', [])
    if (not isinstance(reqs, list) or len(reqs) > 500 or
            not isinstance(bounds, list) or len(bounds) > 2000 or
            any(not isinstance(r, dict) or not isinstance(r.get('id'), str)
                or not isinstance(r.get('description'), str) or len(r['description']) > 5000
                or not isinstance(r.get('expected_checks', []), list)
                or len(r.get('expected_checks', [])) > 8 for r in reqs)):
        raise ValueError('Malformed or oversized manifest (max 500 requirements)')
    return m


def init(root: Path) -> str:
    if (root / MANIFEST).exists() or (root / LEDGER).exists():
        raise ValueError(".raee already initialized (files left unchanged)")
    write_json(root / MANIFEST, {
        "schema": 1,
        "goal": "Describe the coding task and intended behavior here",
        "requirements": [],
        "boundaries": [
            "A passing command does not prove overall behavioral correctness.",
            "Unexecuted paths, dependency vulnerabilities, and production behavior remain unverified.",
        ],
    })
    write_json(root / LEDGER, {"schema": 1, "runs": []})
    return str(root / MANIFEST)


def add_requirement(root: Path, description: str) -> str:
    m = get_manifest(root)
    if not description.strip():
        raise ValueError("Requirement cannot be empty")
    existing = {r["id"] for r in m.get("requirements", [])}
    idx = 1
    while f"R{idx}" in existing:
        idx += 1
    rid = f"R{idx}"
    m.setdefault("requirements", []).append({"id": rid, "description": description.strip()})
    write_json(root / MANIFEST, m)
    return rid


def add_boundary(root: Path, description: str) -> None:
    m = get_manifest(root)
    if not description.strip():
        raise ValueError("Boundary cannot be empty")
    m.setdefault("boundaries", []).append(description.strip())
    write_json(root / MANIFEST, m)


def run_check(root: Path, requirement: str, command: list[str], timeout: int, kind: str | None = None) -> dict:
    if kind is not None:
        from .contracts import KINDS
        if kind not in KINDS:
            raise ValueError(f"Invalid declared check kind: {kind}")
    m = get_manifest(root)
    known = {r["id"] for r in m.get("requirements", [])}
    if requirement not in known:
        raise ValueError(f"Unknown requirement: {requirement}; add one using `raee-lite add` first")
    if not command:
        raise ValueError("Missing command; example: raee-lite run --for R1 -- python -m unittest")
    if timeout <= 0:
        raise ValueError("Timeout must be positive")
    ledger = read_json(root / LEDGER, {"schema": 1, "runs": []})
    before = fingerprint(root)
    code, exception_text, duration = bounded_run(command, root, timeout)
    out_hash, err_hash = None, None  # no raw terminal output read, even transiently
    after = fingerprint(root)
    entry = {
        "id": f"E{len(ledger['runs']) + 1}", "role": "verification",
        "requirement": requirement, "requirement_digest": intent_digest(next(r["description"] for r in m["requirements"] if r["id"] == requirement)), "command": ["[explicit command redacted]"],
        "command_sha256": hashlib.sha256(json.dumps(command).encode('utf-8')).hexdigest(),
        "declared_kind": kind,
        "observed_exit_code": code,
        "observed_status": "pass" if code == 0 else "fail",
        "timestamp": utcnow(), "duration_seconds": duration,
        "source_fingerprint": before["sha256"],
        "source_fingerprint_after": after["sha256"],
        "files_inspected": before["files"], "files_skipped": before["skipped"],
        "stdout_sha256": out_hash, "stderr_sha256": err_hash, "output_policy": "DISCARDED_NOT_STORED",
        "error": exception_text,
        "environment": {"python": sys.version.split()[0], "os": platform.platform()},
        "change": git_context(root),
    }
    ledger["runs"].append(entry)
    write_json(root / LEDGER, ledger)
    return entry


def audit(root: Path) -> dict:
    m = get_manifest(root)
    ledger = read_json(root / LEDGER, {"schema": 1, "runs": []})
    current = fingerprint(root)
    results = []
    for r in m.get("requirements", []):
        matching = [e for e in ledger["runs"] if e.get("requirement") == r["id"]]
        if not matching:
            state, evidence = "UNTESTED", None
        else:
            evidence = matching[-1]
            if (evidence["source_fingerprint"] != current["sha256"] or
                    evidence.get("source_fingerprint_after") != evidence["source_fingerprint"]):
                state = "STALE"
            elif evidence.get("files_skipped") or current["skipped"]:
                state = "PARTIAL_COVERAGE" if evidence["observed_exit_code"] == 0 else "FAILED_CHECK"
            elif evidence["observed_exit_code"] == 0:
                state = "OBSERVED_PASS"
            else:
                state = "FAILED_CHECK"
        results.append({"id": r["id"], "requirement": r["description"], "state": state,
                        "evidence_id": evidence["id"] if evidence else None,
                        "command": evidence["command"] if evidence else None,
                        "exit_code": evidence["observed_exit_code"] if evidence else None})
    states = [r["state"] for r in results]
    if not results:
        overall = "INSUFFICIENT_EVIDENCE"
    elif "FAILED_CHECK" in states:
        overall = "FAILED_CHECK"
    elif "STALE" in states:
        overall = "STALE_EVIDENCE"
    elif "UNTESTED" in states or "PARTIAL_COVERAGE" in states:
        overall = "INSUFFICIENT_EVIDENCE"
    else:
        overall = "CHECKS_PASSED_WITH_LIMITS"
    return {
        "tool": "RAEE-Lite", "version": "0.1.0", "timestamp": utcnow(),
        "overall": overall,
        "roles": {
            "intent": "User-authored requirements, not generated test assertions",
            "change": "Source fingerprint and optional Git state; not a correctness proof",
            "verification": "Observed command exit codes, tied to source fingerprint",
            "environment": "Local Python and OS metadata captured on each check",
            "boundary": "Explicit conditions and unknowns; retained in the report",
        },
        "goal": m.get("goal", ""), "requirements": results,
        "boundary_notes": m.get("boundaries", []),
        "source": current,
        "caveat": "A passing command supports only the stated check. It does not validate that the check covers the requirement or establish software correctness.",
    }


def markdown(report: dict) -> str:
    lines = ["# RAEE-Lite Evidence Report", "", f"**Outcome:** `{report['overall']}`", "",
             f"**Goal:** {report['goal']}", "", "## Evidence by role", ""]
    for role, description in report["roles"].items():
        lines.append(f"- **{role}:** {description}")
    lines += ["", "## Requirements and observed checks", "",
              "| ID | Requirement | State | Evidence | Exit |",
              "|---|---|---|---|---|"]
    for r in report["requirements"]:
        safe = r["requirement"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r['id']} | {safe} | `{r['state']}` | {r['evidence_id'] or '—'} | {r['exit_code'] if r['exit_code'] is not None else '—'} |")
    if not report["requirements"]:
        lines.append("| — | No requirements declared | `UNTESTED` | — | — |")
    lines += ["", "## Applicability boundaries and unknowns", ""]
    for b in report["boundary_notes"]:
        lines.append(f"- {b}")
    if report["source"]["skipped"]:
        lines.append(f"- **Coverage limitation:** {len(report['source']['skipped'])} files were not hashed in full.")
    lines += ["", "## Important interpretation", "", report["caveat"], ""]
    return "\n".join(lines)


def save_report(root: Path) -> dict:
    report = audit(root)
    write_json(root / ".raee" / "report.json", report)
    (root / ".raee" / "report.md").write_text(markdown(report), encoding="utf-8")
    return report
