"""Conservative local-Python dependency scope auditor (experimental, advisory).

This does not prove dependency closure: runtime imports, generated code, native
libraries, plugins, data files and network state may remain invisible.
No project code is executed and no environment variables are inspected.
"""
from __future__ import annotations

import ast
import os
import stat
from collections import deque
from pathlib import Path
from .dependency_scope import _normal_paths, MAX_FILE_BYTES, MAX_TOTAL_BYTES

MAX_VISITED = 128
MAX_AST_NODES = 100_000
_DYNAMIC = {"__import__", "import_module", "exec", "eval"}


def _search_roots(root: Path) -> tuple[Path, ...]:
    """Return bounded Python source roots without following a linked src tree."""
    roots = [root]
    src = root / "src"
    if not src.is_symlink() and src.is_dir():
        roots.append(src)
    return tuple(roots)


def _unsafe_path(root: Path, path: Path) -> bool:
    return path.is_symlink() or any(
        parent.is_symlink()
        for parent in path.parents
        if parent != root and root in parent.parents
    )


def _module_paths(root: Path, name: str) -> set[str]:
    if not name or any(not x.isidentifier() for x in name.split(".")):
        return set()
    stem = "/".join(name.split("."))
    found = set()
    for search_root in _search_roots(root):
        for rel in (stem + ".py", stem + "/__init__.py"):
            p = search_root / rel
            if _unsafe_path(root, p):
                found.add(p.relative_to(root).as_posix())
                continue
            if p.is_file():
                found.add(p.relative_to(root).as_posix())
                # Importing pkg.submodule also executes every regular parent
                # package initializer, including its transitive dependencies.
                found.update(_package_initializers(root, p))
    return found


def _package_initializers(root: Path, path: Path) -> set[str]:
    found = set()
    for parent in path.parents:
        if parent in (root, root / "src"):
            break
        initializer = parent / "__init__.py"
        # Queue linked initializers too; the reader must report the unsafe
        # dependency instead of silently omitting it.
        if initializer.is_symlink() or initializer.is_file():
            found.add(initializer.relative_to(root).as_posix())
    return found


def _read_source(root: Path, path: Path, remaining: int) -> bytes:
    if _unsafe_path(root, path):
        raise ValueError("Unsafe path")
    meta = path.lstat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_size > MAX_FILE_BYTES:
        raise ValueError("Input is not a bounded regular file")
    if meta.st_size > remaining:
        raise OverflowError("Read budget exhausted")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        current = os.fstat(fd)
        if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != (meta.st_dev, meta.st_ino):
            raise ValueError("Input changed while opening")
        with os.fdopen(fd, "rb", closefd=False) as source:
            data = source.read(min(MAX_FILE_BYTES, remaining) + 1)
        if len(data) > remaining:
            raise OverflowError("Read budget exhausted")
        if len(data) > MAX_FILE_BYTES or _unsafe_path(root, path):
            raise ValueError("Unsafe or oversized input")
        return data
    finally:
        os.close(fd)


def _looks_project_local(root: Path, name: str) -> bool:
    if not name:
        return False
    top = name.split(".", 1)[0]
    if top in {"src", "tests"}:
        return True
    return any((base / top).is_dir() or (base / f"{top}.py").is_file()
               for base in _search_roots(root))


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
    if (root / "src").is_symlink():
        warnings.add("SOURCE_ROOT_UNAVAILABLE_OR_UNSAFE:src")
    queue = deque(sorted(p for p in declared if p.endswith(".py")))
    scheduled = set(queue)
    if not queue:
        warnings.add("NO_PYTHON_ENTRY_FILES")
    visited: set[str] = set()
    total_bytes = 0
    ast_nodes = 0

    def enqueue(targets):
        discovered.update(targets)
        for target in sorted(targets - scheduled):
            queue.append(target)
            scheduled.add(target)
        return bool(targets)

    def discover(module):
        return enqueue(_module_paths(root, module))

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
            data = _read_source(root, p, MAX_TOTAL_BYTES - total_bytes)
            total_bytes += len(data)
        except OverflowError:
            warnings.add("TOTAL_BYTE_BUDGET_EXCEEDED")
            break
        except (OSError, ValueError):
            warnings.add("INPUT_UNAVAILABLE_OR_UNSAFE:" + rel)
            continue
        # A declared package entry can be imported or run with -m even when
        # its own body has no imports. Its parent initializers still matter.
        enqueue(_package_initializers(root, p))
        try:
            tree = ast.parse(data, filename=rel)
        except (UnicodeError, SyntaxError, ValueError, RecursionError):
            warnings.add("INPUT_UNPARSEABLE:" + rel)
            continue
        source_rel = rel[4:] if rel.startswith("src/") else rel
        package = source_rel[:-3].replace("/", ".")
        if package.endswith(".__init__"):
            package = package[:-9]
        else:
            package = package.rpartition(".")[0]
        for node in ast.walk(tree):
            ast_nodes += 1
            if ast_nodes > MAX_AST_NODES:
                warnings.add("AST_BUDGET_EXCEEDED")
                break
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not discover(alias.name) and _looks_project_local(root, alias.name):
                        unresolved.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = package.split(".") if package else []
                    up = node.level - 1
                    if up >= len(parts):
                        warnings.add("RELATIVE_IMPORT_UNRESOLVED:" + rel)
                        continue
                    prefix = ".".join(parts[:len(parts)-up])
                    base = ".".join(filter(None, [prefix, node.module or ""]))
                else:
                    base = node.module or ""
                candidates = [base]
                candidates.extend(".".join(filter(None, (base, a.name)))
                                  for a in node.names if a.name != "*")
                resolved = False
                for module in candidates:
                    resolved = discover(module) or resolved
                if any(a.name in _DYNAMIC for a in node.names):
                    warnings.add("DYNAMIC_EXECUTION_OR_IMPORT:" + rel)
                # A resolved base may export an attribute with the imported
                # name, so an unresolved base.name is not itself an omission.
                if not resolved and (node.level or _looks_project_local(root, base)):
                    unresolved.add(base or f"relative-from:{rel}")
                if any(a.name == "*" for a in node.names):
                    warnings.add("STAR_IMPORT:" + rel)
            elif isinstance(node, ast.Call):
                fn = node.func
                called = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
                if called in _DYNAMIC:
                    warnings.add("DYNAMIC_EXECUTION_OR_IMPORT:" + rel)
        if "AST_BUDGET_EXCEEDED" in warnings:
            break
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
        "bytes_read": total_bytes,
        "note": "Advisory static analysis only; no execution or semantic closure proof.",
    }
