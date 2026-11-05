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
    if package_json.is_file() and not package_json.is_symlink():
        try:
            if package_json.stat().st_size > 1_000_000:
                raise ValueError('package.json exceeds discovery size limit')
            pkg = json.loads(package_json.read_text(encoding="utf-8"))
            if not isinstance(pkg, dict):
                raise ValueError('package.json must contain an object')
            scripts = pkg.get("scripts", {})
            if not isinstance(scripts, dict):
                scripts = {}
            npm = shutil.which("npm")
            if not npm:
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

    python_indicators = [root / "pyproject.toml", root / "pytest.ini", root / "setup.cfg"]
    has_pytest_tests = (root / "tests").is_dir() and any((root / "tests").glob("test_*.py"))
    has_pytest_cfg = (root / "pytest.ini").is_file() or (root / "conftest.py").is_file()
    if has_pytest_tests or has_pytest_cfg:
        # pytest is an explicit project test command. If it is absent, the failure is
        # reported instead of silently replacing it with a different test runner.
        checks.append(Check("auto:python:test", "test", (sys.executable, "-m", "pytest", "-q"),
                            "Python tests/ or pytest configuration found; pytest must be installed"))
    elif (root / "tests").is_dir() and any((root / "tests").glob("*_test.py")):
        checks.append(Check("auto:python:unittest", "test", (sys.executable, "-m", "unittest", "discover", "-s", "tests"),
                            "Python unittest-style tests detected"))

    if (root / "ruff.toml").is_file() or (root / ".ruff.toml").is_file():
        if shutil.which("ruff"):
            checks.append(Check("auto:python:lint", "lint", (shutil.which("ruff") or "ruff", "check", "."),
                                "Ruff configuration detected"))
        else:
            notes.append("Ruff configuration found, but ruff is not available in PATH")

    if not checks:
        notes.append("No supported checks detected; add requirements and explicit commands manually")
    return checks, notes


def risk_signals(root: Path) -> list[dict]:
    """Potential high-impact paths changed in git, not security verdicts."""
    from .core import git_context
    ctx = git_context(root)
    if not ctx.get("available"):
        return [{"level": "info", "reason": "No Git baseline available; changed-file risk scan unavailable", "paths": []}]
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
                diff = subprocess.run(
                    [git, "diff", "HEAD", "--no-ext-diff", "--unified=0", "--", *test_paths],
                    cwd=root, capture_output=True, check=False, timeout=15,
                )
                lines = diff.stdout[:250_000].decode("utf-8", errors="replace").splitlines()
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
                if len(diff.stdout) > 250_000:
                    found.append({"level": "info", "reason": "test_diff_truncated", "paths": []})
            except (OSError, subprocess.TimeoutExpired):
                found.append({"level": "info", "reason": "test_diff_scan_unavailable", "paths": []})
    if ctx.get("changed_paths_truncated"):
        found.append({"level": "info", "reason": "Changed path listing truncated", "paths": []})
    return found
