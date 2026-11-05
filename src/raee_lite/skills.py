"""Explicit, non-overwriting installer for a portable Agent Skill."""
from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from .safe_io import write_text as atomic_text

SKILL_PATHS = {
    "codex": ".agents/skills/raee-lite/SKILL.md",
    "claude": ".claude/skills/raee-lite/SKILL.md",
    "cursor": ".cursor/skills/raee-lite/SKILL.md",
}


def install_skill(root: Path, target: str) -> list[str]:
    if target not in set(SKILL_PATHS) | {"all"}:
        raise ValueError(f"Unsupported agent: {target}")
    agents = list(SKILL_PATHS) if target == "all" else [target]
    template = files("raee_lite").joinpath("skill_template.md").read_text(encoding="utf-8")
    results = []
    # Validate first so an existing conflicting file cannot cause partial installation.
    destinations = [(agent, root / SKILL_PATHS[agent]) for agent in agents]
    for agent, target_path in destinations:
        if target_path.is_symlink():
            raise ValueError("Refusing to follow symlink skill path")
        if target_path.exists() and target_path.read_text(encoding="utf-8") != template:
            raise ValueError(f"Existing skill differs; refusing to overwrite: {target_path}")
    for agent, target_path in destinations:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            atomic_text(target_path, template)
            results.append(f"{agent}: installed {target_path}")
        else:
            results.append(f"{agent}: already current {target_path}")
    return results
