"""Independent adversarial fixtures for conservative omitted-import detection."""
import tempfile
import unittest
from pathlib import Path

from raee_lite.dependency_audit import audit_local_python_scope


class CompletenessAuditTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name).resolve()

    def write(self, path, content):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def audit(self, paths=None):
        return audit_local_python_scope(self.root, paths or ["app.py"])

    def test_direct_undeclared_import_detected(self):
        self.write("app.py", "import helper\n")
        self.write("helper.py", "VALUE = 1\n")
        result = self.audit()
        self.assertEqual(result["status"], "OMITTED_LOCAL_IMPORTS")
        self.assertIn("helper.py", result["missing_local_dependencies"])
        self.assertFalse(result["dependency_completeness_proven"])

    def test_transitive_dependency_detected(self):
        self.write("app.py", "import helper\n")
        self.write("helper.py", "import internal\n")
        self.write("internal.py", "VALUE = 1\n")
        self.assertEqual(self.audit()["missing_local_dependencies"], ["helper.py", "internal.py"])

    def test_declared_complete_remains_unproven(self):
        self.write("app.py", "from helper import VALUE\n")
        self.write("helper.py", "VALUE = 1\n")
        result = self.audit(["app.py", "helper.py"])
        self.assertEqual(result["status"], "NO_STATIC_OMISSIONS_FOUND_UNPROVEN")
        self.assertFalse(result["dependency_completeness_proven"])

    def test_unrelated_note_not_counted(self):
        self.write("app.py", "x = 1\n")
        self.write("NOTE.txt", "unrelated")
        self.assertEqual(self.audit()["missing_local_dependencies"], [])

    def test_dynamic_import_cannot_be_certified(self):
        self.write("app.py", "__import__('hidden')\n")
        self.write("hidden.py", "VALUE = 1\n")
        result = self.audit()
        self.assertIn("DYNAMIC_EXECUTION_OR_IMPORT:app.py", result["limitations"])
        self.assertFalse(result["dependency_completeness_proven"])

    def test_import_does_not_execute_side_effect(self):
        self.write("app.py", "import helper\n")
        self.write("helper.py", "raise RuntimeError('must not execute')\n")
        self.assertEqual(self.audit()["missing_local_dependencies"], ["helper.py"])

    def test_invalid_syntax_is_uncertain(self):
        self.write("app.py", "def broken(:\n")
        self.assertIn("INPUT_UNPARSEABLE:app.py", self.audit()["limitations"])

    def test_relative_package_import(self):
        self.write("pkg/__init__.py", "")
        self.write("pkg/app.py", "from . import helper\n")
        self.write("pkg/helper.py", "VALUE = 1\n")
        result = self.audit(["pkg/app.py"])
        self.assertIn("pkg/helper.py", result["missing_local_dependencies"])


if __name__ == "__main__":
    unittest.main()
