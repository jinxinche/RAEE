"""Run a synthetic evidence walkthrough in an automatically cleaned scratch folder.

Install RAEE-Lite into this Python environment first. This explicitly executes
the tiny unittest fixtures below; it does not execute the surrounding project's
tests, contact an AI service, or modify the source checkout.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


SMOKE_TEST = '''import unittest

class SmokeTest(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(1 + 1, 2)
'''

REQUIREMENT_TEST = '''import unittest
from app import signup

class SignupTest(unittest.TestCase):
    def test_rejects_address_without_at(self):
        self.assertFalse(signup("not-an-email"))

    def test_accepts_example_address(self):
        self.assertTrue(signup("person@example.com"))
'''


def main() -> int:
    try:
        import raee_lite  # noqa: F401 - check the selected Python environment
    except ImportError:
        print("Install RAEE-Lite first: python -m pip install --no-deps .", file=sys.stderr)
        return 2

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    with tempfile.TemporaryDirectory(prefix="raee-showcase-") as directory:
        root = Path(directory).resolve()
        (root / "tests").mkdir()
        app = root / "app.py"
        test = root / "tests" / "test_app.py"
        app.write_text("def signup(email):\n    return True\n", encoding="utf-8")
        test.write_text(SMOKE_TEST, encoding="utf-8")
        cli = [sys.executable, "-X", "utf8", "-m", "raee_lite", "--project", str(root)]
        unit = [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-v"]

        def run(command: list[str], expected: int = 0) -> str:
            result = subprocess.run(command, cwd=root, env=env, capture_output=True,
                                    text=True, encoding="utf-8", timeout=30)
            if result.returncode != expected:
                raise RuntimeError(f"Expected exit {expected}, got {result.returncode}:\n"
                                   f"{result.stdout}\n{result.stderr}")
            return result.stdout

        def show(title: str, expected: str) -> None:
            report = json.loads(run(cli + ["check", "--json"]))
            state = report["requirements"][0]["state"]
            if state != expected:
                raise RuntimeError(f"{title}: expected {expected}, got {state}")
            print(f"{title}\n  R1: {state}", flush=True)

        run(cli + ["init"])
        run(cli + ["add", "Signup rejects addresses without an @ sign"])
        run(cli + ["expect", "--for", "R1", "--kind", "unit"])

        run(unit)
        show("1. Unrelated arithmetic test passes", "UNTESTED")

        test.write_text(REQUIREMENT_TEST, encoding="utf-8")
        run(cli + ["run", "--for", "R1", "--kind", "unit", "--"] + unit, expected=1)
        show("2. A requirement-linked test exposes the bug", "FAILED_CHECK")

        app.write_text("def signup(email):\n    return '@' in email\n", encoding="utf-8")
        run(cli + ["run", "--for", "R1", "--kind", "unit", "--"] + unit)
        show("3. The toy fix passes the two example tests", "OBSERVED_PASS")

        app.write_text(app.read_text(encoding="utf-8") + "\n# A later source edit.\n",
                       encoding="utf-8")
        show("4. Source changes after the recorded check", "STALE")

    print("\nDemo passed; scratch files removed.\n"
          "OBSERVED_PASS records a labelled command result, not complete coverage.\n"
          "The toy '@' check is not a production email validator.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"Demo failed: {error}", file=sys.stderr)
        raise SystemExit(1)
