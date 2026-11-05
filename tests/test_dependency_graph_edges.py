"""Import graph regressions for namespace members and bounded traversal."""
import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite.dependency_audit import audit_local_python_scope


class DependencyGraphEdgeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()

    def write(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def audit(self, *paths):
        result = audit_local_python_scope(self.root, list(paths))
        self.assertFalse(result["dependency_completeness_proven"])
        self.assertFalse(result["receipt_validity_changed"])
        return result

    def test_namespace_member_does_not_hide_unresolved_sibling(self):
        self.write("app.py", "from ns import present, absent\n")
        self.write("ns/present.py", "VALUE = 1\n")
        result = self.audit("app.py", "ns/present.py")
        self.assertEqual(result["missing_local_dependencies"], [])
        self.assertEqual(result["unresolved_project_imports"], ["ns.absent"])

    def test_namespace_import_aliases_do_not_hide_unresolved_sibling(self):
        self.write("app.py", "from ns import absent as missing, present as good\n")
        self.write("ns/present.py", "VALUE = 1\n")
        result = self.audit("app.py", "ns/present.py")
        self.assertEqual(result["unresolved_project_imports"], ["ns.absent"])

    def test_relative_namespace_members_are_checked_individually(self):
        self.write("src/ns/app.py", "from . import present, absent\n")
        self.write("src/ns/present.py", "VALUE = 1\n")
        result = self.audit("src/ns/app.py", "src/ns/present.py")
        self.assertEqual(result["missing_local_dependencies"], [])
        self.assertEqual(result["unresolved_project_imports"], ["ns.absent"])

    def test_conditional_namespace_import_still_reports_uncertainty(self):
        self.write("app.py", "try:\n    from ns import present, absent\nexcept ImportError:\n    pass\n")
        self.write("ns/present.py", "VALUE = 1\n")
        result = self.audit("app.py", "ns/present.py")
        self.assertEqual(result["unresolved_project_imports"], ["ns.absent"])

    def test_namespace_members_across_search_roots_are_resolved(self):
        self.write("app.py", "from ns import first, second\n")
        self.write("ns/first.py", "VALUE = 1\n")
        self.write("src/ns/second.py", "VALUE = 2\n")
        result = self.audit("app.py", "ns/first.py", "src/ns/second.py")
        self.assertEqual(result["missing_local_dependencies"], [])
        self.assertEqual(result["unresolved_project_imports"], [])
        self.assertEqual(result["limitations"], [])

    def test_regular_package_attributes_are_not_missing_submodules(self):
        self.write("app.py", "from pkg import helper as local, VALUE as constant\n")
        self.write("pkg/__init__.py", "VALUE = 1\n")
        self.write("pkg/helper.py", "VALUE = 2\n")
        result = self.audit("app.py", "pkg/__init__.py", "pkg/helper.py")
        self.assertEqual(result["unresolved_project_imports"], [])
        self.assertEqual(result["limitations"], [])

    def test_conditional_imports_cover_both_branches_and_aliases(self):
        self.write("app.py", "if enabled:\n    import first as chosen\nelse:\n    import second as chosen\n")
        self.write("first.py", "VALUE = 1\n")
        self.write("second.py", "VALUE = 2\n")
        result = self.audit("app.py")
        self.assertEqual(result["missing_local_dependencies"], ["first.py", "second.py"])

    def test_visit_budget_boundary_preserves_uncertainty(self):
        self.write("app.py", "import helper\n")
        self.write("helper.py", "import hidden\n")
        self.write("hidden.py", "pass\n")
        for limit, exhausted in ((1, True), (2, True), (3, False)):
            with self.subTest(limit=limit), patch("raee_lite.dependency_audit.MAX_VISITED", limit):
                result = self.audit("app.py")
                self.assertEqual("TRAVERSAL_BUDGET_EXCEEDED" in result["limitations"], exhausted)
                self.assertEqual(len(result["visited_local_python_files"]), limit)

    def test_ast_budget_boundary_is_cumulative_across_modules(self):
        sources = {"app.py": "import helper\n", "helper.py": "VALUE = 1\n"}
        for name, source in sources.items():
            self.write(name, source)
        count = sum(sum(1 for _ in ast.walk(ast.parse(source))) for source in sources.values())
        for limit, exhausted in ((count - 1, True), (count, False)):
            with self.subTest(limit=limit), patch("raee_lite.dependency_audit.MAX_AST_NODES", limit):
                result = self.audit(*sources)
                self.assertEqual("AST_BUDGET_EXCEEDED" in result["limitations"], exhausted)

    def test_total_byte_budget_boundary_is_cumulative(self):
        sources = {"app.py": "import helper\n", "helper.py": "VALUE = 1\n"}
        for name, source in sources.items():
            self.write(name, source)
        count = sum(len(source.encode("utf-8")) for source in sources.values())
        for limit, exhausted in ((count - 1, True), (count, False)):
            with self.subTest(limit=limit), patch("raee_lite.dependency_audit.MAX_TOTAL_BYTES", limit):
                result = self.audit(*sources)
                self.assertEqual("TOTAL_BYTE_BUDGET_EXCEEDED" in result["limitations"], exhausted)
                self.assertLessEqual(result["bytes_read"], limit)


if __name__ == "__main__":
    unittest.main()
