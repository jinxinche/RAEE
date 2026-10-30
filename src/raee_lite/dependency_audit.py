"""Conservative local-Python dependency scope auditor (experimental, advisory).

This does not prove dependency closure: runtime imports, generated code, native
libraries, plugins, data files and network state may remain invisible.
No project code is executed and no environment variables are inspected.
"""
from __future__ import annotations

import ast
from collections import deque
from pathlib import Path
from .dependency_scope import _normal_paths, MAX_FILE_BYTES

MAX_VISITED = 128
_DYNAMIC = {"__import__", "import_module", "exec", "eval"}


def _module_path(root: Path, name: str) -> str | None:
    if not name or any(not x.isidentifier() for x in name.split(".")):
        return None
    stem = "/".join(name.split("."))
    for rel in (stem + ".py", stem + "/__init__.py"):
        p = root / rel
        if p.is_symlink() or any(parent.is_symlink() for parent in p.parents if parent != root and root in parent.parents):
            continue
        if p.is_file():
            return rel
    return None


def audit_local_python_scope(root: Path, declared_paths: list[str]) -> dict:
    """Detect statically visible local imports omitted from a declared file scope.

    A clean result means only 'no omissions found by this bounded analyzer'.
    It never certifies completeness or changes existing receipt validity.
    """
    root = Path(root).resolve(strict=True)
    declared = set(_normal_paths(declared_paths))
    discovered: set[str] = set()
    unresolved: set[str] = set()
    warnings: set[str] = set()
    queue = deque(sorted(p for p in declared if p.endswith(".py")))
    visited: set[str] = set()
    while queue:
        if len(visited) >= MAX_VISITED:
            warnings.add("TRAVERSAL_BUDGET_EXCEEDED")
            break
        rel = queue.popleft()
        if rel in visited:
            continue
        visited.add(rel)
        p = root / rel
        try:
            if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_FILE_BYTES:
                warnings.add("INPUT_UNAVAILABLE_OR_UNSAFE:" + rel)
                continue
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=rel)
        except (OSError, UnicodeError, SyntaxError, ValueError):
            warnings.add("INPUT_UNPARSEABLE:" + rel)
            continue
        package = rel[:-3].replace("/", ".")
        if package.endswith(".__init__"):
            package = package[:-9]
        else:
            package = package.rpartition(".")[0]
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = package.split(".") if package else []
                    up = node.level - 1
                    if up > len(parts):
                        warnings.add("RELATIVE_IMPORT_UNRESOLVED:" + rel)
                        continue
                    prefix = ".".join(parts[:len(parts)-up])
                    base = ".".join(filter(None, [prefix, node.module or ""]))
                else:
                    base = node.module or ""
                modules.append(base)
                modules.extend(".".join(filter(None, (base, a.name))) for a in node.names if a.name != "*")
                if any(a.name == "*" for a in node.names):
                    warnings.add("STAR_IMPORT:" + rel)
            elif isinstance(node, ast.Call):
                fn = node.func
                called = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
                if called in _DYNAMIC:
                    warnings.add("DYNAMIC_EXECUTION_OR_IMPORT:" + rel)
            for module in modules:
                target = _module_path(root, module)
                if target:
                    discovered.add(target)
                    if target not in visited:
                        queue.append(target)
                elif module and (module.startswith("src.") or module.startswith("tests.")):
                    unresolved.add(module)
    missing = sorted(discovered - declared)
    return {
        "schema": "raee.dependency_completeness_audit.v1",
        "status": "OMITTED_LOCAL_IMPORTS" if missing else "NO_STATIC_OMISSIONS_FOUND_UNPROVEN",
        "declared_paths": sorted(declared),
        "missing_local_dependencies": missing,
        "visited_local_python_files": sorted(visited),
        "unresolved_project_imports": sorted(unresolved),
        "limitations": sorted(warnings),
        "dependency_completeness_proven": False,
        "receipt_validity_changed": False,
        "note": "Advisory static analysis only; no execution or semantic closure proof.",
    }
