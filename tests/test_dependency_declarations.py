"""Guard direct third-party imports against undeclared runtime dependencies."""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "raee_lite"


class DependencyDeclarationTests(unittest.TestCase):
    def test_direct_third_party_imports_are_declared(self):
        imported = set()
        for path in SOURCE.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.add(node.module.split(".", 1)[0])
        third_party = imported - sys.stdlib_module_names - {"raee_lite", "__future__"}

        # Updating this explicit direct-import inventory forces a reviewer to
        # check pyproject metadata whenever production code gains a dependency.
        self.assertEqual(third_party, {"cryptography"})
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        optional = pyproject.split("[project.optional-dependencies]", 1)[1].split("\n[", 1)[0]
        self.assertRegex(optional, re.compile(r'^attest\s*=\s*\[[^\]]*"cryptography>=42"', re.M))


if __name__ == "__main__":
    unittest.main()
