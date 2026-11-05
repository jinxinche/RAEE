"""Malformed or mismatched scope evidence must not retain a passing contract."""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

from raee_lite import core
from raee_lite.contracts import assess_contracts, set_expectation
from raee_lite.dependency_audit import audit_local_python_scope
from raee_lite.dependency_scope import compare, snapshot


class ContractHistoryEdgesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / "app.py").write_text("pass\n", encoding="utf-8")
        (self.root / "other.py").write_text("pass\n", encoding="utf-8")
        core.init(self.root)
        self.rid = core.add_requirement(self.root, "App runs")
        set_expectation(self.root, self.rid, "unit")
        core.run_check(self.root, self.rid, [sys.executable, "-c", "pass"], 15,
                       kind="unit", dependency_files=["app.py"])
        self.ledger = core.read_json(self.root / core.LEDGER, {})

    def assess_with(self, side, audit):
        ledger = copy.deepcopy(self.ledger)
        ledger["runs"][-1]["dependency_scope"][side] = audit
        core.write_json(self.root / core.LEDGER, ledger)
        return assess_contracts(self.root, core.fingerprint(self.root),
                                dependency_context={self.rid: {"paths": ["app.py"]}})[0]

    def assert_uncertain(self, report):
        self.assertEqual(report["status"], "GAPS")
        self.assertEqual(report["evidence_by_kind"][0]["state"], "SCOPE_AUDIT_UNCERTAIN")

    def test_complete_matching_history_retains_pass(self):
        audit = self.ledger["runs"][-1]["dependency_scope"]["audit_before"]
        report = self.assess_with("audit_before", audit)
        self.assertEqual(report["status"], "RECORDED")
        self.assertEqual(report["evidence_by_kind"][0]["state"], "OBSERVED_PASS")

    def test_schema_only_history_is_not_a_clean_audit(self):
        for side in ("audit_before", "audit_after"):
            with self.subTest(side=side):
                self.assert_uncertain(self.assess_with(
                    side, {"schema": "raee.dependency_completeness_audit.v1"}))

    def test_real_clean_audit_for_other_files_cannot_satisfy_scope(self):
        unrelated = audit_local_python_scope(self.root, ["other.py"])
        self.assertEqual(unrelated["limitations"], [])
        for side in ("audit_before", "audit_after"):
            with self.subTest(side=side):
                self.assert_uncertain(self.assess_with(side, unrelated))

    def test_historical_scope_requires_exact_paths_and_case(self):
        original = self.ledger["runs"][-1]["dependency_scope"]["audit_before"]
        for paths in (["APP.py"], ["*.py"], ["nested/app.py"], ["./app.py"], None):
            for side in ("audit_before", "audit_after"):
                with self.subTest(paths=paths, side=side):
                    self.assert_uncertain(self.assess_with(side, dict(original, declared_paths=paths)))

    def test_missing_or_falsy_audit_findings_are_not_empty_lists(self):
        for side in ("audit_before", "audit_after"):
            original = self.ledger["runs"][-1]["dependency_scope"][side]
            for field in ("missing_local_dependencies", "limitations", "unresolved_project_imports"):
                for value in (None, False, 0, "", {}):
                    with self.subTest(side=side, field=field, value=value):
                        self.assert_uncertain(self.assess_with(side, dict(original, **{field: value})))
                with self.subTest(side=side, field=field, missing=True):
                    audit = dict(original)
                    del audit[field]
                    self.assert_uncertain(self.assess_with(side, audit))

    def test_contradictory_or_missing_audit_status_cannot_pass(self):
        original = self.ledger["runs"][-1]["dependency_scope"]["audit_before"]
        for side in ("audit_before", "audit_after"):
            for status in (None, "OMITTED_LOCAL_IMPORTS", "UNKNOWN"):
                with self.subTest(side=side, status=status):
                    self.assert_uncertain(self.assess_with(side, dict(original, status=status)))


class ScopeDeclarationEdgesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / "app.py").write_text("pass\n", encoding="utf-8")
        self.scope = snapshot(self.root, ["app.py"])

    def test_malformed_path_declarations_cannot_match_each_other(self):
        for paths in (["*.py"], ["../app.py"], ["./app.py"], ["pkg//app.py"],
                      ["pkg\\app.py"], ["app.py", "app.py"], [None],
                      [f"file{i}.py" for i in range(65)]):
            with self.subTest(paths=paths):
                malformed = dict(self.scope, paths=paths)
                self.assertEqual(compare(malformed, malformed), "SCOPE_UNBOUND")

    def test_malformed_external_labels_cannot_match_each_other(self):
        for labels in (["*"], [""], [None], ["service", "service"],
                       [f"service{i}" for i in range(33)]):
            with self.subTest(labels=labels):
                malformed = dict(self.scope, external_keys=labels)
                self.assertEqual(compare(malformed, malformed), "SCOPE_UNBOUND")

    def test_glob_paths_are_rejected_before_snapshot(self):
        for path in ("*.py", "**/app.py", "app?.py", "[a]pp.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                snapshot(self.root, [path])

    def test_path_and_external_label_case_changes_are_declaration_changes(self):
        (self.root / "APP.py").write_text("pass\n", encoding="utf-8")
        upper_path = snapshot(self.root, ["APP.py"])
        self.assertEqual(compare(self.scope, upper_path), "SCOPE_DECLARATION_CHANGED")
        upper_key = snapshot(self.root, ["app.py"], {"Service": "v1"})
        lower_key = snapshot(self.root, ["app.py"], {"service": "v1"})
        self.assertEqual(compare(upper_key, lower_key), "SCOPE_DECLARATION_CHANGED")


if __name__ == "__main__":
    unittest.main()
