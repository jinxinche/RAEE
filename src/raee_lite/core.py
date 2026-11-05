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
from .safe_io import safe_read_json, write_json as atomic_json, read_bytes, write_text as atomic_text
from .safe_io import exclusive_lock, bounded_walk
from .evidence_binding import intent_digest, evaluate_binding, valid_execution
from .dependency_scope import snapshot as declared_dependency_snapshot
from .dependency_audit import audit_local_python_scope
from .safe_process import run as bounded_run, capture_bounded
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
MAX_SCAN_ENTRIES = 10_000
MAX_SCAN_DIRECTORIES = 5_000
MAX_RUNS = 2_000
MANIFEST = Path(".raee") / "manifest.json"
LEDGER = Path(".raee") / "ledger.json"
LEDGER_LOCK = Path(".raee") / "ledger.lock"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, default=None):
    result = safe_read_json(path, default)
    if path.name == 'ledger.json' and result is not None:
        if not isinstance(result, dict) or result.get('schema') != 1:
            raise ValueError('Invalid evidence ledger schema')
        entries = result.get('runs', [])
        if not isinstance(entries, list) or len(entries) > MAX_RUNS or any(not isinstance(x, dict) for x in entries):
            raise ValueError('Invalid or oversized local evidence ledger (max 2,000 runs)')
    return result


def write_json(path: Path, obj) -> None:
    atomic_json(path, obj)


def append_receipt(root: Path, entry: dict, *, lock_timeout: float = 5.0) -> dict:
    """Commit one receipt without overwriting another cooperating writer."""
    with exclusive_lock(root / LEDGER_LOCK, timeout=lock_timeout):
        ledger = read_json(root / LEDGER, {"schema": 1, "runs": []})
        runs = ledger.setdefault('runs', [])
        if len(runs) >= MAX_RUNS:
            raise ValueError('Evidence ledger limit reached; archive before recording another check')
        existing = {r['id'] for r in runs if isinstance(r.get('id'), str)}
        index = len(runs) + 1
        while f'E{index}' in existing:
            index += 1
        saved = {**entry, 'id': f'E{index}'}
        runs.append(saved)
        # The JSON byte cap is checked before atomically replacing the ledger.
        write_json(root / LEDGER, ledger)
        return saved


def paths(root: Path) -> list[Path]:
    """Bounded source enumeration: at most MAX_FILES+1 paths in memory.

    The extra real path marks the file-count limit. The list-compatible result
    separately records Git output truncation, independent of any disk filename.
    Git-ignored inputs are NOT inspected.
    """
    class Inventory(list):
        enumeration_truncated = False

    git = shutil.which('git')
    if git and (root / '.git').exists():
        try:
            code, raw, truncated = capture_bounded(
                [git, '--no-optional-locks', '-c', 'core.fsmonitor=false', 'ls-files',
                 '--cached', '--others', '--exclude-standard', '-z'], root, limit=8_000_000)
            if code == 0 or truncated:
                out = []
                start = 0
                while (end := raw.find(b'\x00', start)) >= 0:
                    name = raw[start:end]
                    start = end + 1
                    p = Path(os.fsdecode(name))
                    if (not name or p.is_absolute() or '..' in p.parts or
                            any(v in EXCLUDE_DIRS for v in p.parts) or p.suffix in EXCLUDE_SUFFIXES):
                        continue
                    out.append(root / p)
                    if len(out) > MAX_FILES:
                        break
                result = Inventory(sorted(out, key=lambda v: v.as_posix()))
                result.enumeration_truncated = truncated
                return result
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    out = []
    for folder, directories, filenames in bounded_walk(
            root, max_entries=MAX_SCAN_ENTRIES, max_directories=MAX_SCAN_DIRECTORIES,
            exclude_dirs=EXCLUDE_DIRS):
        for filename in filenames:
            if filename in EXCLUDE_DIRS and (folder / filename).is_symlink():
                continue
            p = Path(folder) / filename
            if p.suffix not in EXCLUDE_SUFFIXES:
                out.append(p)
                if len(out) > MAX_FILES:
                    return Inventory(sorted(out, key=lambda v: v.as_posix()))
    return Inventory(sorted(out, key=lambda v: v.as_posix()))


def fingerprint(root: Path) -> dict:
    """Aggregate content digests for eligible source files; mark skipped files explicitly."""
    digest = hashlib.sha256()
    skipped = []
    files = paths(root)
    if getattr(files, 'enumeration_truncated', False):
        skipped.append({'file': '.', 'reason': 'enumeration_truncated'})
    hashed_bytes = 0
    for i, file in enumerate(files):
        relative = file.relative_to(root).as_posix()
        if i >= MAX_FILES:
            skipped.append({"file": relative, "reason": "file_count_limit"})
            continue
        try:
            n = file.lstat().st_size
            if n > MAX_FILE_BYTES:
                skipped.append({"file": relative, "reason": "file_size_limit", "bytes": n})
                continue
            if hashed_bytes + n > MAX_HASH_BYTES:
                skipped.append({"file": relative, "reason": "total_hash_byte_budget", "bytes": n})
                continue
            contents = read_bytes(file, min(MAX_FILE_BYTES, MAX_HASH_BYTES - hashed_bytes))
            hashed_bytes += len(contents)
        except (OSError, ValueError):
            skipped.append({"file": relative, "reason": "unreadable"})
            continue
        digest.update(relative.encode("utf-8", errors="replace") + b"\x00")
        digest.update(hashlib.sha256(contents).digest())
    # Skip records participate in the digest; still report that full proof is unavailable.
    digest.update(json.dumps(skipped, sort_keys=True).encode())
    return {"sha256": digest.hexdigest(), "files": min(len(files), MAX_FILES), "skipped": skipped,
            "scope_note": "Git-ignored/externally supplied inputs and excluded folders are not fingerprinted."}


def git_context(root: Path) -> dict:
    from .safe_process import git_metadata_command

    git = shutil.which("git")
    if not git or not (root / ".git").exists():
        return {"available": False}
    command = [git, '--no-optional-locks', '-c', 'core.fsmonitor=false']
    try:
        command = git_metadata_command(command, root)
        if command is None:
            return {'available': False, 'reason': 'git_filter_config_unavailable'}
        head_code, head, _ = capture_bounded([*command, "rev-parse", "HEAD"], root, limit=128)
        status_code, status, truncated = capture_bounded([*command, "status", "--porcelain", "--untracked-files=normal"], root)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"available": False}
    lines = status.decode('utf-8', errors='replace').splitlines()
    return {"available": head_code == 0 and (status_code == 0 or truncated),
            "head": head.decode('ascii', errors='replace').strip() if head_code == 0 else None,
            "changed_paths": lines[:200] if status_code == 0 or truncated else [],
            "changed_paths_truncated": truncated or len(lines) > 200}


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
    if len({r['id'] for r in reqs}) != len(reqs) or any(
            not r['id'] or any(not isinstance(kind, str) for kind in r.get('expected_checks', [])) for r in reqs):
        raise ValueError('Ambiguous requirement IDs or invalid check roles')
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
    if not isinstance(description, str) or not description.strip() or len(description) > 5000:
        raise ValueError("Requirement must contain 1..5000 characters")
    if len(m.get('requirements', [])) >= 500:
        raise ValueError('Requirement limit reached (500)')
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
    if not isinstance(description, str) or not description.strip() or len(description) > 5000:
        raise ValueError("Boundary must contain 1..5000 characters")
    if len(m.get('boundaries', [])) >= 2000:
        raise ValueError('Boundary limit reached (2000)')
    m.setdefault("boundaries", []).append(description.strip())
    write_json(root / MANIFEST, m)


def run_check(root: Path, requirement: str, command: list[str], timeout: int, kind: str | None = None,
              *, dependency_files: list[str] | None = None,
              external_revisions: dict[str, str] | None = None) -> dict:
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
    if len(ledger['runs']) >= MAX_RUNS:
        raise ValueError('Evidence ledger limit reached; archive it before executing another check')
    if external_revisions is not None and dependency_files is None:
        raise ValueError("External revisions require explicit dependency files")
    before = fingerprint(root)
    scoped_before = (declared_dependency_snapshot(root, dependency_files, external_revisions)
                     if dependency_files is not None else None)
    audit_before = audit_local_python_scope(root, dependency_files) if scoped_before is not None else None
    code, exception_text, duration = bounded_run(command, root, timeout)
    out_hash, err_hash = None, None  # no raw terminal output read, even transiently
    after = fingerprint(root)
    scoped_after = None
    if scoped_before is not None:
        try:
            scoped_after = declared_dependency_snapshot(root, dependency_files, external_revisions)
        except ValueError:
            # An executed command may remove or invalidate a scoped input.
            # Retain its process receipt but refuse to carry over the binding.
            scoped_after = {"state": "UNAVAILABLE_AFTER_EXECUTION"}
    entry = {
        "role": "verification",
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
    if scoped_before is not None:
        try:
            audit_after = audit_local_python_scope(root, dependency_files)
        except (OSError, ValueError, TypeError, RecursionError):
            audit_after = {'limitations': ['UNAVAILABLE_AFTER_EXECUTION']}
        entry["dependency_scope"] = {"before": scoped_before, "after": scoped_after,
                                     "audit_before": audit_before, "audit_after": audit_after}
    return append_receipt(root, entry)


def audit(root: Path) -> dict:
    m = get_manifest(root)
    ledger = read_json(root / LEDGER, {"schema": 1, "runs": []})
    current = fingerprint(root)
    results = []
    for r in m.get("requirements", []):
        matching = [e for e in ledger["runs"] if e.get("requirement") == r["id"] and e.get('origin') != 'auto_discovered']
        if not matching:
            state, evidence = "UNTESTED", None
        else:
            evidence = matching[-1]
            binding = evaluate_binding(evidence, r['description'])
            if not valid_execution(evidence):
                state = 'INVALID_EVIDENCE'
            elif 'dependency_scope' in evidence:
                state = 'SCOPE_CONTEXT_REQUIRED' if isinstance(evidence['dependency_scope'], dict) else 'SCOPE_UNBOUND'
            elif (evidence.get("source_fingerprint") != current["sha256"] or
                    evidence.get("source_fingerprint_after") != evidence["source_fingerprint"]):
                state = "STALE"
            elif evidence.get("files_skipped") or current["skipped"]:
                state = "PARTIAL_COVERAGE" if evidence["observed_exit_code"] == 0 else "FAILED_CHECK"
            elif binding != 'BINDING_MATCHED':
                state = binding
            elif evidence["observed_exit_code"] == 0:
                state = "OBSERVED_PASS"
            else:
                state = "FAILED_CHECK"
        results.append({"id": r["id"], "requirement": r["description"], "state": state,
                        "evidence_id": evidence.get("id") if evidence else None,
                        "command": evidence.get("command") if evidence else None,
                        "exit_code": evidence.get("observed_exit_code") if evidence else None})
    states = [r["state"] for r in results]
    if not results:
        overall = "INSUFFICIENT_EVIDENCE"
    elif "FAILED_CHECK" in states:
        overall = "FAILED_CHECK"
    elif "STALE" in states:
        overall = "STALE_EVIDENCE"
    elif any(state != 'OBSERVED_PASS' for state in states):
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
    atomic_text(root / ".raee" / "report.md", markdown(report))
    return report
