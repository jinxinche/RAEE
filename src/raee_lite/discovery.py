"""Conservative deterministic check discovery. Never executes what it discovers."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from .safe_io import read_bytes, strict_json_loads
from .safe_process import capture_bounded


@dataclass(frozen=True)
class Check:
    id: str
    kind: str
    command: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "command": list(self.command), "reason": self.reason}


def discover(root: Path) -> tuple[list[Check], list[str]]:
    """Discover likely checks; not statements about their adequacy for user intent."""
    checks: list[Check] = []
    notes: list[str] = []
    package_json = root / "package.json"
    if package_json.is_symlink():
        notes.append("package.json is a symlink; package script discovery skipped")
    elif package_json.is_file():
        try:
            if package_json.stat().st_size > 1_000_000:
                raise ValueError('package.json exceeds discovery size limit')
            pkg = strict_json_loads(read_bytes(package_json, 1_000_000))
            if not isinstance(pkg, dict):
                raise ValueError('package.json must contain an object')
            scripts = pkg.get("scripts", {})
            if not isinstance(scripts, dict):
                raise ValueError('package.json scripts must contain an object')
            manager = pkg.get("packageManager")
            supported_manager = ("packageManager" not in pkg or
                                 isinstance(manager, str) and
                                 re.fullmatch(r"npm@[^\s]+", manager) is not None)
            npm = shutil.which("npm") if supported_manager else None
            if not supported_manager:
                notes.append("Unsupported package.json packageManager; package script discovery "
                             "skipped; add explicit commands for the declared package manager")
            elif not npm:
                notes.append("package.json found but npm is unavailable in PATH")
            else:
                for kind in ("test", "typecheck", "lint", "build"):
                    script = scripts.get(kind)
                    if not isinstance(script, str) or not script.strip():
                        continue
                    if kind == "test" and re.search(r"no test specified", script, re.I):
                        notes.append("package.json test script is a placeholder; skipped")
                        continue
                    checks.append(Check(f"auto:npm:{kind}", kind, (npm, "run", kind),
                                        f"package.json scripts.{kind} (user-controlled script; may run arbitrary code)"))
        except (OSError, UnicodeError, ValueError, TypeError) as ex:
            notes.append(f"Could not parse package.json: {type(ex).__name__}")

    python_indicators = [root / name for name in
                         ("tests", "pytest.ini", "conftest.py", "pyproject.toml", "setup.cfg")]
    linked_python = [path.name for path in python_indicators if path.is_symlink()]
    if linked_python:
        notes.append("Python test discovery skipped for symlinked paths: " +
                     ", ".join(linked_python) + "; add explicit commands")
    else:
        tests = root / "tests"
        has_pytest_tests = tests.is_dir() and any(
            not path.is_symlink() and path.is_file()
            for pattern in ("test_*.py", "*_test.py") for path in tests.glob(pattern)
        )
        has_pytest_cfg = (root / "pytest.ini").is_file() or (root / "conftest.py").is_file()
        if has_pytest_tests or has_pytest_cfg:
            # Both filename patterns are pytest defaults; neither identifies the
            # test framework. unittest can silently pass without collecting them.
            # A missing pytest must fail instead of selecting another runner.
            checks.append(Check("auto:python:test", "test", (sys.executable, "-m", "pytest", "-q"),
                                "Python tests/ or pytest configuration found; pytest must be installed"))

    ruff_configs = [root / "ruff.toml", root / ".ruff.toml"]
    if any(path.is_symlink() for path in ruff_configs):
        notes.append("Ruff discovery skipped for symlinked configuration; add explicit commands")
    elif any(path.is_file() for path in ruff_configs):
        ruff = shutil.which("ruff")
        if ruff:
            checks.append(Check("auto:python:lint", "lint", (ruff, "check", "."),
                                "Ruff configuration detected"))
        else:
            notes.append("Ruff configuration found, but ruff is not available in PATH")

    if not checks:
        notes.append("No supported checks detected; add requirements and explicit commands manually")
    return checks, notes


def risk_signals(root: Path) -> list[dict]:
    """Potential high-impact paths changed in git, not security verdicts."""
    from .core import git_context
    from .safe_process import git_metadata_command
    ctx = git_context(root)
    if not ctx.get("available"):
        return [{"level": "info", "reason": ctx.get('reason') or "No Git baseline available; changed-file risk scan unavailable", "paths": []}]
    patterns = {
        "modified_tests": re.compile(r"(^|/)(tests?/|__tests__/|[^/]*\.test\.|[^/]*_test\.)", re.I),
        "auth_or_permissions": re.compile(r"(^|/)(auth|login|session|permission|access|roles?)(/|\.|$)", re.I),
        "billing": re.compile(r"(billing|payments?|checkout|stripe)", re.I),
        "migration_or_schema": re.compile(r"(migrations?/|schema\.|prisma/|alembic/)", re.I),
        "deployment_or_secrets": re.compile(r"(^|/)(\.env|\.github/workflows/|dockerfile|terraform|k8s/)", re.I),
    }
    found = []
    changed = [p[3:].strip() if len(p) >= 3 else p for p in ctx.get("changed_paths", [])]
    for label, rgx in patterns.items():
        selected = [p for p in changed if rgx.search(p)]
        if selected:
            found.append({"level": "review", "reason": label, "paths": selected[:20]})
    # Conservative git diff review. Flags need human inspection, not a finding.
    # Only tracked test changes relative to HEAD are visible; untracked tests are outside scope.
    git = shutil.which("git")
    if git and changed:
        test_paths = [p for p in changed if patterns["modified_tests"].search(p)
                      and not p.startswith("-") and not p.startswith(".raee/")][:40]
        if test_paths:
            try:
                command = [git, '--no-optional-locks', '-c', 'core.fsmonitor=false']
                command = git_metadata_command(command, root)
                if command is None:
                    found.append({'level': 'info', 'reason': 'git_filter_config_unavailable', 'paths': []})
                    return found
                code, raw, truncated = capture_bounded(
                    [*command, "diff", "HEAD", "--no-ext-diff", "--no-textconv", "--unified=0", "--", *test_paths],
                    root,
                )
                if code and not truncated:
                    raise ValueError('Git diff unavailable')
                lines = raw.decode("utf-8", errors="replace").splitlines()
                added_skips = []
                removed_asserts = []
                for line in lines:
                    if line.startswith("+++") or line.startswith("---"):
                        continue
                    if line.startswith("+") and re.search(
                        r"(@pytest\.mark\.skip|\b(?:it|test|describe)\.skip\s*\(|\bxit\s*\(|unittest\.skip\s*\()", line, re.I):
                        added_skips.append(line[1:130])
                    if line.startswith("-") and re.search(r"\b(assert|expect\s*\(|assertEqual\s*\()", line):
                        removed_asserts.append(line[1:130])
                if added_skips:
                    found.append({"level": "review", "reason": "new_test_skip_markers", "paths": test_paths[:20],
                                  "note": "Possible weakening: newly added skip markers in tracked tests."})
                if removed_asserts:
                    found.append({"level": "review", "reason": "removed_test_assertions", "paths": test_paths[:20],
                                  "note": "Possible weakening: assertion lines removed in tracked tests."})
                if truncated:
                    found.append({"level": "info", "reason": "test_diff_truncated", "paths": []})
            except (OSError, ValueError, subprocess.TimeoutExpired):
                found.append({"level": "info", "reason": "test_diff_scan_unavailable", "paths": []})
    if ctx.get("changed_paths_truncated"):
        found.append({"level": "info", "reason": "Changed path listing truncated", "paths": []})
    return found
