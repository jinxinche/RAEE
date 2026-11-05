"""Conservative evidence-binding checks; never infer semantic correctness."""
from __future__ import annotations
import hashlib
import json
import platform
import sys


def intent_digest(description: str, kind: str | None = None) -> str:
    """Bind exactly the requirement text, not approximate semantic similarity."""
    raw = json.dumps({"description": description}, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def environment_key(env: dict) -> tuple[str, str]:
    """Conservative Python version and OS identity comparison."""
    return (str(env.get("os", "")), str(env.get("python", "")))


def current_environment() -> dict:
    return {"python": sys.version.split()[0], "os": platform.platform()}


def evaluate_binding(receipt: dict, requirement_description: str, *, target_environment: dict | None = None) -> str:
    expected = intent_digest(requirement_description)
    bound = receipt.get("requirement_digest")
    if not isinstance(bound, str):
        return "INTENT_UNBOUND"
    if bound != expected:
        return "INTENT_CHANGED"
    if target_environment is not None:
        recorded = receipt.get("environment")
        if not isinstance(recorded, dict) or not all(environment_key(recorded)):
            return "ENVIRONMENT_UNBOUND"
        if environment_key(recorded) != environment_key(target_environment):
            return "ENVIRONMENT_SHIFT_UNVERIFIED"
    return "BINDING_MATCHED"
