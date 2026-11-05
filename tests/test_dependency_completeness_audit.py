"""Independent adversarial fixtures for conservative omitted-import detection."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_src_layout_absolute_import(self):
        self.write("src/pkg/__init__.py", "")
        self.write("src/pkg/app.py", "from pkg import helper\n")
        self.write("src/pkg/helper.py", "VALUE = 1\n")
        result = self.audit(["src/pkg/app.py"])
        self.assertIn("src/pkg/helper.py", result["missing_local_dependencies"])
        self.assertEqual(result["unresolved_project_imports"], [])

    def test_from_import_attribute_is_not_false_unresolved(self):
        self.write("src/pkg/__init__.py", "")
        self.write("src/pkg/app.py", "from pkg.helper import VALUE\n")
        self.write("src/pkg/helper.py", "VALUE = 1\n")
        result = self.audit(["src/pkg/app.py", "src/pkg/helper.py"])
        self.assertEqual(result["unresolved_project_imports"], [])

    def test_missing_project_module_is_unresolved(self):
        self.write("src/pkg/__init__.py", "")
        self.write("src/pkg/app.py", "import pkg.missing\n")
        result = self.audit(["src/pkg/app.py"])
        self.assertEqual(result["unresolved_project_imports"], ["pkg.missing"])

    def test_package_initializers_and_their_imports_are_dependencies(self):
        self.write("app.py", "import pkg.nested.helper\n")
        self.write("pkg/__init__.py", "import configuration\n")
        self.write("configuration.py", "VALUE = 1\n")
        self.write("pkg/nested/__init__.py", "")
        self.write("pkg/nested/helper.py", "VALUE = 1\n")
        self.assertEqual(self.audit()["missing_local_dependencies"], [
            "configuration.py", "pkg/__init__.py", "pkg/nested/__init__.py",
            "pkg/nested/helper.py"])
        self.assertEqual(self.audit(["pkg/nested/helper.py"])["missing_local_dependencies"], [
            "configuration.py", "pkg/__init__.py", "pkg/nested/__init__.py"])

    def test_declared_path_through_link_never_reads_external_file(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside).resolve()
            (target / "entry.py").write_text("import hidden\n", encoding="utf-8")
            try:
                (self.root / "linked").symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest("Symlink privilege unavailable")
            result = self.audit(["linked/entry.py"])
            self.assertIn("INPUT_UNAVAILABLE_OR_UNSAFE:linked/entry.py", result["limitations"])
            self.write("app.py", "import pkg.helper\n")
            self.write("pkg/helper.py", "VALUE = 1\n")
            (self.root / "pkg/__init__.py").symlink_to(target / "entry.py")
            result = self.audit()
            self.assertIn("pkg/__init__.py", result["missing_local_dependencies"])
            self.assertIn("INPUT_UNAVAILABLE_OR_UNSAFE:pkg/__init__.py", result["limitations"])
            self.assertNotIn("hidden", result["unresolved_project_imports"])
            self.write("app.py", "import broken\n")
            (self.root / "broken.py").symlink_to(target / "missing.py")
            result = self.audit()
            self.assertIn("broken.py", result["missing_local_dependencies"])
            self.assertIn("INPUT_UNAVAILABLE_OR_UNSAFE:broken.py", result["limitations"])
            (self.root / "src").symlink_to(target, target_is_directory=True)
            self.assertIn("SOURCE_ROOT_UNAVAILABLE_OR_UNSAFE:src", self.audit()["limitations"])

    def test_dynamic_import_alias_remains_uncertain(self):
        self.write("app.py", "from importlib import import_module as load\nload('hidden')\n")
        self.assertIn("DYNAMIC_EXECUTION_OR_IMPORT:app.py", self.audit()["limitations"])

    def test_dynamic_function_references_remain_uncertain(self):
        for source in (
            "import importlib\nload = importlib.import_module\nload('hidden')\n",
            "import importlib as imports\ncallback = imports.import_module\n",
            "load = __import__\nload('hidden')\n",
            "import builtins\ncallbacks = [builtins.exec, builtins.eval]\n",
            "def run(callback=eval):\n    return callback('1')\n",
        ):
            with self.subTest(source=source):
                self.write("app.py", source)
                result = self.audit()
                self.assertIn("DYNAMIC_EXECUTION_OR_IMPORT:app.py", result["limitations"])
                self.assertFalse(result["dependency_completeness_proven"])

    def test_dynamic_names_in_strings_and_assignment_targets_are_not_references(self):
        self.write("app.py", "import_module = '__import__'\ntext = 'exec eval'\n")
        self.assertEqual(self.audit()["limitations"], [])

    def test_script_sibling_and_transitive_imports_detected(self):
        self.write("scripts/app.py", "import helper\n")
        self.write("scripts/helper.py", "from nested import VALUE\n")
        self.write("scripts/nested.py", "VALUE = 1\n")
        result = self.audit(["scripts/app.py"])
        self.assertEqual(result["missing_local_dependencies"], [
            "scripts/helper.py", "scripts/nested.py"])
        self.assertEqual(result["unresolved_project_imports"], [])
        complete = self.audit(["scripts/app.py", "scripts/helper.py", "scripts/nested.py"])
        self.assertEqual(complete["missing_local_dependencies"], [])
        self.assertEqual(complete["limitations"], [])

    def test_script_sibling_roots_do_not_expand_to_transitive_directories(self):
        self.write("scripts/app.py", "import pkg.helper\n")
        self.write("scripts/pkg/helper.py", "import unrelated\n")
        self.write("scripts/pkg/unrelated.py", "raise RuntimeError('not on import path')\n")
        self.write("other/unrelated.py", "raise RuntimeError('not on import path')\n")
        result = self.audit(["scripts/app.py"])
        self.assertEqual(result["missing_local_dependencies"], ["scripts/pkg/helper.py"])
        self.assertEqual(result["visited_local_python_files"], [
            "scripts/app.py", "scripts/pkg/helper.py"])

    def test_linked_script_sibling_is_uncertain_without_reading_target(self):
        self.write("scripts/app.py", "import helper\n")
        self.write("hidden.py", "VALUE = 1\n")
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside).resolve() / "helper.py"
            target.write_text("import hidden\n", encoding="utf-8")
            try:
                (self.root / "scripts/helper.py").symlink_to(target)
            except OSError:
                self.skipTest("Symlink privilege unavailable")
            result = self.audit(["scripts/app.py"])
        self.assertIn("scripts/helper.py", result["missing_local_dependencies"])
        self.assertIn("INPUT_UNAVAILABLE_OR_UNSAFE:scripts/helper.py", result["limitations"])
        self.assertNotIn("hidden.py", result["visited_local_python_files"])

    def test_src_regular_package_initializer_and_transitive_imports_detected(self):
        self.write("app.py", "import src.worker\n")
        self.write("src/worker.py", "pass\n")
        self.write("src/__init__.py", "import hidden\n")
        self.write("hidden.py", "VALUE = 1\n")
        result = self.audit(["app.py", "src/worker.py"])
        self.assertEqual(result["missing_local_dependencies"], ["hidden.py", "src/__init__.py"])

    def test_src_regular_package_relative_imports(self):
        self.write("src/worker.py", "pass\n")
        self.write("src/__init__.py", "from . import helper\n")
        self.write("src/helper.py", "VALUE = 1\n")
        result = self.audit(["src/worker.py"])
        self.assertEqual(result["missing_local_dependencies"], ["src/__init__.py", "src/helper.py"])
        self.assertEqual(result["unresolved_project_imports"], [])
        self.assertEqual(result["limitations"], [])

    def test_src_namespace_package_child_import(self):
        self.write("src/pkg/app.py", "from . import helper\n")
        self.write("src/pkg/helper.py", "VALUE = 1\n")
        result = self.audit(["src/pkg/app.py"])
        self.assertEqual(result["missing_local_dependencies"], ["src/pkg/helper.py"])
        self.assertEqual(result["unresolved_project_imports"], [])
        self.assertEqual(result["limitations"], [])

    def test_relative_import_cannot_escape_source_root(self):
        self.write("src/pkg/app.py", "from .. import hidden\n")
        self.write("src/hidden.py", "VALUE = 1\n")
        result = self.audit(["src/pkg/app.py"])
        self.assertIn("RELATIVE_IMPORT_UNRESOLVED:src/pkg/app.py", result["limitations"])
        self.assertNotIn("src/hidden.py", result["missing_local_dependencies"])

    def test_duplicate_imports_do_not_exhaust_visit_budget(self):
        self.write("app.py", "import helper\nimport helper\n")
        self.write("helper.py", "pass\n")
        with patch("raee_lite.dependency_audit.MAX_VISITED", 2):
            self.assertNotIn("TRAVERSAL_BUDGET_EXCEEDED", self.audit()["limitations"])

    def test_total_read_budget_is_fail_visible(self):
        self.write("app.py", "import helper\n")
        self.write("helper.py", "VALUE = 1\n")
        with patch("raee_lite.dependency_audit.MAX_TOTAL_BYTES", 16):
            self.assertIn("TOTAL_BYTE_BUDGET_EXCEEDED", self.audit()["limitations"])

    def test_ast_budget_is_fail_visible(self):
        self.write("app.py", "x = 1\ny = 2\n")
        with patch("raee_lite.dependency_audit.MAX_AST_NODES", 2):
            self.assertIn("AST_BUDGET_EXCEEDED", self.audit()["limitations"])

    def test_no_python_entries_is_uncertain(self):
        self.write("data.json", "{}")
        self.assertIn("NO_PYTHON_ENTRY_FILES", self.audit(["data.json"])["limitations"])


if __name__ == "__main__":
    unittest.main()
