"""Conservative evidence-binding checks; never infer semantic correctness."""
from __future__ import annotations
import hashlib
import json
import platform
import re
import sys


def intent_digest(description: str, kind: str | None = None) -> str:
    """Bind exactly the requirement text, not approximate semantic similarity."""
    raw = json.dumps({"description": description}, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def environment_key(env: dict) -> tuple[str, str]:
    """Conservative Python version and OS identity comparison."""
    return tuple(value if isinstance(value := env.get(key), str) and value.strip() else ''
                 for key in ('os', 'python'))


def current_environment() -> dict:
    return {"python": sys.version.split()[0], "os": platform.platform()}


def valid_execution(receipt: dict) -> bool:
    """Validate execution roles and internally consistent process metadata.

    This detects malformed evidence, not an attacker forging an unsigned ledger.
    """
    code = receipt.get('observed_exit_code')
    origin = receipt.get('origin', 'local_explicit')
    command = receipt.get('command')
    if (type(code) is not int or receipt.get('role') != 'verification' or
            origin not in ('local_explicit', 'isolated_replay', 'auto_discovered') or
            not isinstance(command, list) or not command or
            any(not isinstance(arg, str) or not arg or '\x00' in arg for arg in command)):
        return False
    # Automatic receipts retain argv and historically omit this digest. If a
    # digest is present, every origin must supply a string and honor its binding.
    if origin != 'auto_discovered' or 'command_sha256' in receipt:
        digest = receipt.get('command_sha256')
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            return False
        redacted = {'local_explicit': ['[explicit command redacted]'],
                    'isolated_replay': ['[isolated command redacted]']}
        # The original argv is intentionally unavailable for these exact,
        # origin-specific placeholders; only cleartext commands can be rehashed.
        if command != redacted.get(origin):
            expected = hashlib.sha256(json.dumps(command).encode('utf-8')).hexdigest()
            if digest != expected:
                return False
    if code == 0:
        return receipt.get('observed_status') == 'pass' and receipt.get('error') in (None, '')
    return receipt.get('observed_status') in ('fail', 'infrastructure_error')


def evaluate_environment(receipt: dict, target_environment: dict | None = None) -> str:
    recorded = receipt.get('environment')
    target = current_environment() if target_environment is None else target_environment
    if not isinstance(recorded, dict) or not all(environment_key(recorded)):
        return 'ENVIRONMENT_UNBOUND'
    if (not isinstance(target, dict) or not all(environment_key(target)) or
            environment_key(recorded) != environment_key(target)):
        return 'ENVIRONMENT_SHIFT_UNVERIFIED'
    return 'BINDING_MATCHED'


def evaluate_binding(receipt: dict, requirement_description: str, *, target_environment: dict | None = None) -> str:
    expected = intent_digest(requirement_description)
    bound = receipt.get("requirement_digest")
    if not isinstance(bound, str):
        return "INTENT_UNBOUND"
    if bound != expected:
        return "INTENT_CHANGED"
    return evaluate_environment(receipt, target_environment)
