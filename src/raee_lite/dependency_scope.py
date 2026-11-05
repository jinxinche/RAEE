"""Explicit, bounded requirement-specific evidence dependencies.

This is an experimental provenance mechanism, not dependency discovery or
semantic coverage validation. A maintainer must supply a complete scope; the
library cannot verify that the declaration is sufficient.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Mapping, Sequence
from .safe_io import read_bytes

MAX_DECLARED_FILES = 64
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 16_000_000
MAX_EXTERNAL_LABELS = 32
_PATH = re.compile(r"^[A-Za-z0-9_.@+/-]{1,240}$")
_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_REVISION = re.compile(r"^[A-Za-z0-9_.:@+/-]{1,128}$")


def _digest(parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("ascii")).hexdigest()


def _normal_paths(paths: Sequence[str]) -> list[str]:
    if isinstance(paths, (str, bytes)) or not isinstance(paths, (list, tuple)):
        raise ValueError("Explicit file dependencies must be a sequence")
    if not 1 <= len(paths) <= MAX_DECLARED_FILES:
        raise ValueError("Declare between 1 and 64 relevant project files")
    result = []
    for raw in paths:
        if not isinstance(raw, str) or not _PATH.fullmatch(raw):
            raise ValueError("Unsafe or malformed relative dependency path")
        p = Path(raw)
        if (p.is_absolute() or "\\" in raw or
                any(part in ("", ".", "..") for part in raw.split("/")) or raw.startswith("/")):
            raise ValueError("Dependency paths must be unambiguous project-relative files")
        result.append(raw)
    if len(set(result)) != len(result):
        raise ValueError("Duplicate dependency path")
    return sorted(result)


def _normal_revisions(revisions: Mapping[str, str] | None) -> dict[str, str]:
    if revisions is None:
        return {}
    if not isinstance(revisions, dict) or len(revisions) > MAX_EXTERNAL_LABELS:
        raise ValueError("At most 32 explicitly declared external revision labels")
    clean = {}
    for key, value in revisions.items():
        if not (isinstance(key, str) and _KEY.fullmatch(key) and
                isinstance(value, str) and _REVISION.fullmatch(value)):
            raise ValueError("External revisions must be nonsecret bounded identifiers, not credentials")
        clean[key] = value
    return dict(sorted(clean.items()))


def snapshot(root: Path, paths: Sequence[str],
             external_revisions: Mapping[str, str] | None = None) -> dict:
    """Hash declared files and public revision labels only; do not scan env/secrets.

    Fail closed on missing files, links, invalid paths, or size-budget violations.
    This is a bound on observed inputs, NOT a proof those inputs are sufficient.
    """
    root = Path(root)
    selected = _normal_paths(paths)
    ext = _normal_revisions(external_revisions)
    records = []
    total = 0
    for rel in selected:
        p = root / rel
        for parent in [p, *list(p.parents)]:
            if parent == root.parent:
                break
            if parent.is_symlink():
                raise ValueError("Declared dependency uses a symlink path")
        try:
            data = read_bytes(p, min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total))
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise ValueError("Declared dependency total exceeds byte budget")
            # Report no raw source contents.
            records.append([rel, hashlib.sha256(data).hexdigest()])
        except (FileNotFoundError, PermissionError, IsADirectoryError, OSError) as ex:
            raise ValueError("Declared dependency unavailable or unsafe") from ex
    files_digest = _digest(records)
    externals_digest = _digest(ext)
    return {
        "schema": "raee.declared_dependency_scope.v1",
        "paths": selected,
        "external_keys": list(ext),
        "files_sha256": files_digest,
        "external_sha256": externals_digest,
        "binding_sha256": _digest([files_digest, externals_digest]),
        "declared_scope_only": True,
        "dependency_completeness_proven": False,
    }


def compare(before: dict, after: dict, *, check_external: bool = True) -> str:
    """Compare two explicitly declared bindings without promoting them to proof."""
    for value in (before, after):
        if not isinstance(value, dict) or value.get("schema") != "raee.declared_dependency_scope.v1":
            return "SCOPE_UNBOUND"
        if (not isinstance(value.get("paths"), list) or not value["paths"] or
                not isinstance(value.get("external_keys"), list) or
                any(not isinstance(value.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", value[key])
                    for key in ("files_sha256", "external_sha256", "binding_sha256"))):
            return "SCOPE_UNBOUND"
        if value["binding_sha256"] != _digest([value["files_sha256"], value["external_sha256"]]):
            return "SCOPE_UNBOUND"
    if before.get("paths") != after.get("paths") or before.get("external_keys") != after.get("external_keys"):
        return "SCOPE_DECLARATION_CHANGED"
    if before.get("files_sha256") != after.get("files_sha256"):
        return "DEPENDENCY_SOURCE_CHANGED"
    if check_external and before.get("external_sha256") != after.get("external_sha256"):
        return "EXTERNAL_STATE_CHANGED"
    return "DECLARED_INPUTS_MATCHED"
