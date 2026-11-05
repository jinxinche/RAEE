"""Deterministic resolution-work bounds; no wall-clock performance assertions."""
from collections import Counter
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from raee_lite import dependency_audit as audit


class DependencyPerformanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='raee-dependency-performance-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def write(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')
        return path

    def analyze(self, *entries):
        result = audit.audit_local_python_scope(self.root, list(entries))
        self.assertFalse(result['dependency_completeness_proven'])
        self.assertFalse(result['receipt_validity_changed'])
        return result

    def test_repeated_positive_and_negative_resolutions_are_shared_across_entries(self):
        entries = [f'scripts_{i}/entry.py' for i in range(4)]
        for entry in entries:
            self.write(entry, 'import helper\nimport external_package\n' * 32)
        self.write('helper.py', 'VALUE = 1\n')
        with patch.object(audit, '_module_paths', wraps=audit._module_paths) as modules, \
                patch.object(audit, '_looks_project_local', wraps=audit._looks_project_local) as local:
            result = self.analyze(*entries)
        self.assertEqual(Counter(call.args[1] for call in modules.call_args_list),
                         {'helper': 1, 'external_package': 1})
        self.assertEqual(Counter(call.args[0] for call in local.call_args_list),
                         {'helper': 1, 'external_package': 1})
        self.assertEqual(result['missing_local_dependencies'], ['helper.py'])
        self.assertEqual(len(result['visited_local_python_files']), 5)
        self.assertEqual(result['limitations'], [])

    def test_positive_and_negative_cache_entries_do_not_survive_an_audit(self):
        self.write('entry.py', 'import helper\n' * 3)
        with patch.object(audit, '_module_paths', wraps=audit._module_paths) as modules:
            absent = self.analyze('entry.py')
            helper = self.write('helper.py', 'VALUE = 1\n')
            present = self.analyze('entry.py')
            helper.unlink()
            removed = self.analyze('entry.py')
        self.assertEqual(modules.call_count, 3)
        self.assertEqual(absent['missing_local_dependencies'], [])
        self.assertEqual(present['missing_local_dependencies'], ['helper.py'])
        self.assertEqual(removed['missing_local_dependencies'], [])

    def test_cached_path_still_rechecks_symlinks_before_reading(self):
        self.write('entry.py', 'import helper\n' * 3)
        helper = self.write('helper.py', 'VALUE = 1\n')
        outside = self.root.parent / (self.root.name + '-outside.py')
        outside.write_text('import must_never_be_read\n', encoding='utf-8')
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        original = audit._module_paths

        def replace_after_lookup(root, module, search_roots):
            targets = original(root, module, search_roots)
            if module == 'helper':
                helper.unlink()
                try:
                    helper.symlink_to(outside)
                except OSError:
                    self.skipTest('Symlink privilege unavailable')
            return targets

        with patch.object(audit, '_module_paths', side_effect=replace_after_lookup) as modules:
            result = self.analyze('entry.py')
        self.assertEqual(modules.call_count, 1)
        self.assertIn('INPUT_UNAVAILABLE_OR_UNSAFE:helper.py', result['limitations'])
        self.assertEqual(result['missing_local_dependencies'], ['helper.py'])
        self.assertNotIn('must_never_be_read', result['unresolved_project_imports'])

    def test_duplicate_names_use_one_budget_slot(self):
        self.write('entry.py', 'import helper\n' * 128)
        self.write('helper.py', 'VALUE = 1\n')
        with patch.object(audit, 'MAX_MODULE_RESOLUTIONS', 1), \
                patch.object(audit, 'MAX_RESOLUTION_ROOTS', 1):
            result = self.analyze('entry.py')
        self.assertEqual(result['limitations'], [])
        self.assertEqual(result['missing_local_dependencies'], ['helper.py'])

    def test_unique_name_budget_stops_inside_one_import_statement(self):
        self.write('entry.py', 'import first, second, third\n')
        for name in ('first', 'second', 'third'):
            self.write(name + '.py', 'VALUE = 1\n')
        with patch.object(audit, 'MAX_MODULE_RESOLUTIONS', 2), \
                patch.object(audit, '_module_paths', wraps=audit._module_paths) as modules:
            result = self.analyze('entry.py')
        self.assertEqual([call.args[1] for call in modules.call_args_list], ['first', 'second'])
        self.assertEqual(result['limitations'], ['MODULE_RESOLUTION_BUDGET_EXCEEDED'])
        self.assertEqual(result['missing_local_dependencies'], ['first.py', 'second.py'])
        self.assertEqual(result['unresolved_project_imports'], [])

    def test_from_import_budget_keeps_known_namespace_dependencies(self):
        self.write('entry.py', 'from ns import present, absent\n')
        self.write('ns/present.py', 'VALUE = 1\n')
        with patch.object(audit, 'MAX_MODULE_RESOLUTIONS', 2), \
                patch.object(audit, '_module_paths', wraps=audit._module_paths) as modules:
            result = self.analyze('entry.py')
        self.assertEqual([call.args[1] for call in modules.call_args_list], ['ns', 'ns.present'])
        self.assertEqual(result['missing_local_dependencies'], ['ns/present.py'])
        self.assertEqual(result['limitations'], ['MODULE_RESOLUTION_BUDGET_EXCEEDED'])
        # The unexamined member is unknown, not a confirmed unresolved import.
        self.assertEqual(result['unresolved_project_imports'], [])

    def test_root_work_budget_exact_boundary_and_no_cross_audit_accumulation(self):
        entries = [f'scripts_{i}/entry.py' for i in range(3)]
        for entry in entries:
            self.write(entry, 'import helper\n' * 8)
        self.write('helper.py', 'VALUE = 1\n')
        for limit, exhausted in ((3, True), (4, False), (4, False)):
            with self.subTest(limit=limit, exhausted=exhausted), \
                    patch.object(audit, 'MAX_RESOLUTION_ROOTS', limit), \
                    patch.object(audit, '_module_paths', wraps=audit._module_paths) as modules:
                result = self.analyze(*entries)
                self.assertEqual(modules.call_count, 0 if exhausted else 1)
                self.assertEqual('MODULE_RESOLUTION_BUDGET_EXCEEDED' in result['limitations'], exhausted)

    def test_zero_resolution_budget_is_explicit_even_for_from_import_base(self):
        self.write('entry.py', 'from pkg import helper\n')
        self.write('pkg/helper.py', 'VALUE = 1\n')
        with patch.object(audit, 'MAX_MODULE_RESOLUTIONS', 0), \
                patch.object(audit, '_module_paths', wraps=audit._module_paths) as modules:
            result = self.analyze('entry.py')
        modules.assert_not_called()
        self.assertEqual(result['limitations'], ['MODULE_RESOLUTION_BUDGET_EXCEEDED'])
        self.assertEqual(result['unresolved_project_imports'], [])


if __name__ == '__main__':
    unittest.main()
