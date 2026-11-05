"""Guard direct third-party imports against undeclared runtime dependencies."""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "raee_lite"
MAX_PYPROJECT_BYTES = 64_000


def _optional_dependencies(path: Path) -> dict:
    """Parse actual TOML entries with a bounded read; no runtime dependency.

    Python 3.10 uses the TOML parser bundled with pip, already used by the
    repository's test/install workflow. Newer interpreters use the stdlib.
    """
    try:
        import tomllib
    except ModuleNotFoundError:
        from pip._vendor import tomli as tomllib
    with path.open("rb") as source:
        data = source.read(MAX_PYPROJECT_BYTES + 1)
    if len(data) > MAX_PYPROJECT_BYTES:
        raise ValueError("pyproject.toml exceeds declaration-test read bound")
    return tomllib.loads(data.decode("utf-8"))["project"]["optional-dependencies"]


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
        optional = _optional_dependencies(ROOT / "pyproject.toml")
        self.assertIsInstance(optional, dict)
        attest = optional.get("attest")
        self.assertIsInstance(attest, list)
        self.assertTrue(all(isinstance(entry, str) for entry in attest))
        self.assertIn("cryptography>=42", attest)

    def check_fixture(self, metadata):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            source = root / "src" / "raee_lite"
            source.mkdir(parents=True)
            (source / "signing.py").write_text("import cryptography\n", encoding="utf-8")
            (root / "pyproject.toml").write_text(metadata, encoding="utf-8")
            with patch.dict(globals(), ROOT=root, SOURCE=source):
                self.test_direct_third_party_imports_are_declared()

    def test_dependency_mentioned_only_in_comment_is_rejected(self):
        with self.assertRaises(AssertionError):
            self.check_fixture('[project.optional-dependencies]\nattest = [ # "cryptography>=42"\n]\n')

    def test_other_extra_and_non_array_declarations_are_rejected(self):
        for declaration in (
            'attest = []\nother = ["cryptography>=42"]',
            'attest = "cryptography>=42"',
            'attest = {"cryptography>=42" = true}',
            'attest = ["cryptography>=42", 42]',
        ):
            with self.subTest(declaration=declaration), self.assertRaises(AssertionError):
                self.check_fixture('[project.optional-dependencies]\n' + declaration + '\n')

    def test_real_multiline_and_literal_string_declarations_are_accepted(self):
        self.check_fixture("[project.optional-dependencies]\nattest = [\n  # signing extra\n  'cryptography>=42',\n]\n")

    def test_python310_parser_fallback_rejects_comment_evasion(self):
        with patch.dict(sys.modules, {"tomllib": None}):
            self.check_fixture('[project.optional-dependencies]\nattest = ["cryptography>=42"]\n')
            with self.assertRaises(AssertionError):
                self.check_fixture('[project.optional-dependencies]\nattest = [ # "cryptography>=42"\n]\n')

    def test_malformed_or_oversized_toml_is_rejected(self):
        for metadata in (
            '[project.optional-dependencies]\nattest = ["cryptography>=42"\n',
            '[project.optional-dependencies]\nattest = ["cryptography>=42"]\n' + '#' * MAX_PYPROJECT_BYTES,
        ):
            with self.subTest(length=len(metadata)), self.assertRaises(ValueError):
                self.check_fixture(metadata)


if __name__ == "__main__":
    unittest.main()
