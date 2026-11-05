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
MAX_MODULE_RESOLUTIONS = 1_024
MAX_RESOLUTION_ROOTS = 8_192
_DYNAMIC = {"__import__", "import_module", "exec", "eval"}


def _search_roots(root: Path, entries: tuple[str, ...]) -> tuple[Path, ...]:
    """Include declared script parents, bounded by MAX_DECLARED_FILES.

    A directly executed script imports from its own directory. Do not add
    directories of subsequently discovered modules or recursively scan trees.
    """
    roots = [root]
    src = root / "src"
    if not src.is_symlink() and src.is_dir():
        roots.append(src)
    for rel in entries:
        parent = (root / rel).parent
        if parent not in roots and not _unsafe_path(root, parent) and parent.is_dir():
            roots.append(parent)
    return tuple(roots)


def _unsafe_path(root: Path, path: Path) -> bool:
    return path.is_symlink() or any(
        parent.is_symlink()
        for parent in path.parents
        if parent != root and root in parent.parents
    )


def _module_paths(root: Path, name: str, search_roots: tuple[Path, ...]) -> set[str]:
    if not name or any(not x.isidentifier() for x in name.split(".")):
        return set()
    stem = "/".join(name.split("."))
    found = set()
    for search_root in search_roots:
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
        if parent == root:
            break
        # A directory named src may itself be a regular imported package.
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


def _looks_project_local(name: str, search_roots: tuple[Path, ...]) -> bool:
    if not name:
        return False
    top = name.split(".", 1)[0]
    if top in {"src", "tests"}:
        return True
    return any((base / top).is_dir() or (base / f"{top}.py").is_file()
               for base in search_roots)


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
    entries = tuple(sorted(p for p in declared if p.endswith(".py")))
    search_roots = _search_roots(root, entries)
    src_initializer = root / "src" / "__init__.py"
    src_is_package = src_initializer.is_symlink() or src_initializer.is_file()
    queue = deque(entries)
    scheduled = set(queue)
    if not queue:
        warnings.add("NO_PYTHON_ENTRY_FILES")
    visited: set[str] = set()
    total_bytes = 0
    ast_nodes = 0
    # Search roots are fixed for this audit. Cache misses as well as hits, but
    # never retain filesystem conclusions across separate audits. Source reads
    # still perform their own no-follow and identity checks before parsing.
    resolutions: dict[str, tuple[frozenset[str], bool]] = {}
    resolution_roots = 0
    resolution_exhausted = False

    def resolve(module):
        nonlocal resolution_roots, resolution_exhausted
        if module not in resolutions:
            if (len(resolutions) >= MAX_MODULE_RESOLUTIONS or
                    resolution_roots + len(search_roots) > MAX_RESOLUTION_ROOTS):
                resolution_exhausted = True
                warnings.add("MODULE_RESOLUTION_BUDGET_EXCEEDED")
                return frozenset(), False
            resolution_roots += len(search_roots)
            resolutions[module] = (
                frozenset(_module_paths(root, module, search_roots)),
                _looks_project_local(module, search_roots),
            )
        return resolutions[module]

    def enqueue(targets):
        discovered.update(targets)
        for target in sorted(targets - scheduled):
            queue.append(target)
            scheduled.add(target)
        return bool(targets)

    def discover(module):
        return enqueue(resolve(module)[0])

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
        source_rel = rel[4:] if rel.startswith("src/") and not src_is_package else rel
        package = source_rel[:-3].replace("/", ".")
        if package.endswith(".__init__"):
            package = package[:-9]
        else:
            package = package.rpartition(".")[0]
        for node in ast.walk(tree):
            if resolution_exhausted:
                break
            ast_nodes += 1
            if ast_nodes > MAX_AST_NODES:
                warnings.add("AST_BUDGET_EXCEEDED")
                break
            if isinstance(node, ast.Import):
                for alias in node.names:
                    resolved = discover(alias.name)
                    if resolution_exhausted:
                        break
                    if not resolved and resolve(alias.name)[1]:
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
                base_resolved = discover(base)
                if resolution_exhausted:
                    break
                candidates = (".".join(filter(None, (base, a.name)))
                              for a in node.names if a.name != "*")
                resolved = base_resolved
                unresolved_members = set()
                for module in candidates:
                    member_resolved = discover(module)
                    if resolution_exhausted:
                        break
                    if member_resolved:
                        resolved = True
                    else:
                        unresolved_members.add(module)
                if resolution_exhausted:
                    break
                if any(a.name in _DYNAMIC for a in node.names):
                    warnings.add("DYNAMIC_EXECUTION_OR_IMPORT:" + rel)
                # A resolved base may export an attribute with the imported
                # name, so an unresolved base.name is not itself an omission.
                if node.level or resolve(base)[1]:
                    if not resolved:
                        unresolved.add(base or f"relative-from:{rel}")
                    elif not base_resolved:
                        # Namespace packages have no source exporting these
                        # attributes. One found child must not conceal other
                        # unresolved members in the same from-import.
                        unresolved.update(unresolved_members)
                if any(a.name == "*" for a in node.names):
                    warnings.add("STAR_IMPORT:" + rel)
            elif isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
                # References can escape through aliases, callbacks or defaults;
                # flag them without needing to prove where they are called.
                referenced = node.id if isinstance(node, ast.Name) else node.attr
                if referenced in _DYNAMIC:
                    warnings.add("DYNAMIC_EXECUTION_OR_IMPORT:" + rel)
        if resolution_exhausted or "AST_BUDGET_EXCEEDED" in warnings:
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
