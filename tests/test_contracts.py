"""Executable evidence contract invariants; avoids simulated green tests."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from raee_lite.cli import main
from raee_lite.contracts import KINDS, assess_contracts, set_expectation, suggestions
from raee_lite.core import add_requirement, fingerprint, init, run_check
from raee_lite.discovery import risk_signals
from raee_lite.enhanced import audit, is_passing, save_report


class ContractTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        (self.root / "app.py").write_text("print('ready')\n", encoding="utf-8")
        init(self.root)

    def test_e2e_hint_is_not_automatically_enforced(self):
        req = add_requirement(self.root, "The login button works in the browser")
        run_check(self.root, req, [sys.executable, "-c", "print('ok')"], 15)
        rep = audit(self.root)
        self.assertEqual(rep["overall"], "CHECKS_PASSED_WITH_LIMITS")
        self.assertEqual(rep["evidence_contracts"][0]["status"], "NO_CONTRACT")
        self.assertIn("e2e", [s["kind"] for s in rep["evidence_contracts"][0]["suggestions"]])

    def test_explicit_contract_fails_closed_until_matching_receipt(self):
        req = add_requirement(self.root, "Login works")
        set_expectation(self.root, req, "e2e")
        self.assertFalse(is_passing(audit(self.root)))
        self.assertEqual(audit(self.root)["overall"], "EVIDENCE_GAPS")
        # A generic unit test exit-0 does not satisfy an e2e-labelled contract.
        run_check(self.root, req, [sys.executable, "-c", "pass"], 15, kind="unit")
        self.assertEqual(audit(self.root)["evidence_contracts"][0]["status"], "GAPS")
        run_check(self.root, req, [sys.executable, "-c", "pass"], 15, kind="e2e")
        self.assertEqual(audit(self.root)["evidence_contracts"][0]["status"], "RECORDED")
        self.assertTrue(is_passing(audit(self.root)))

    def test_stale_and_failed_contract_receipts(self):
        req = add_requirement(self.root, "API works")
        set_expectation(self.root, req, "integration")
        run_check(self.root, req, [sys.executable, "-c", "raise SystemExit(4)"], 15, kind="integration")
        self.assertEqual(audit(self.root)["evidence_contracts"][0]["gaps"][0]["kind"], "integration")
        self.assertEqual(audit(self.root)["overall"], "FAILED_CHECK")
        run_check(self.root, req, [sys.executable, "-c", "pass"], 15, kind="integration")
        self.assertTrue(is_passing(audit(self.root)))
        (self.root / "app.py").write_text("print('changed')\n", encoding="utf-8")
        self.assertEqual(audit(self.root)["evidence_contracts"][0]["evidence_by_kind"][0]["state"], "STALE")
        self.assertFalse(is_passing(audit(self.root)))

    def test_multiple_expected_scopes_and_no_false_auto_satisfaction(self):
        req = add_requirement(self.root, "Production signup works")
        set_expectation(self.root, req, "integration")
        set_expectation(self.root, req, "e2e")
        set_expectation(self.root, req, "e2e")
        self.assertEqual(len(audit(self.root)["evidence_contracts"][0]["expected_checks"]), 2)
        run_check(self.root, req, [sys.executable, "-c", "pass"], 15, kind="integration")
        self.assertFalse(is_passing(audit(self.root)))

    def test_invalid_expectation_does_not_corrupt_manifest(self):
        req = add_requirement(self.root, "Basic test")
        orig = (self.root / ".raee/manifest.json").read_text()
        with self.assertRaises(ValueError):
            set_expectation(self.root, req, "unspecified")
        self.assertEqual((self.root / ".raee/manifest.json").read_text(), orig)

    def test_plan_is_read_only_and_returns_hints(self):
        req = add_requirement(self.root, "Browser checkout completes")
        set_expectation(self.root, req, "e2e")
        ledger_before = (self.root / ".raee/ledger.json").read_bytes()
        self.assertEqual(main(["--project", str(self.root), "plan"]), 0)
        self.assertEqual((self.root / ".raee/ledger.json").read_bytes(), ledger_before)
        self.assertFalse((self.root / ".raee/report.html").exists())

    def test_sarif_machine_readable_and_escaped_html(self):
        req = add_requirement(self.root, '<script>alert("x")</script> login')
        set_expectation(self.root, req, "e2e")
        rep = save_report(self.root)
        sarif = json.loads((self.root / ".raee/report.sarif").read_text())
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertTrue(any(r["ruleId"] == "RAEE001" for r in sarif["runs"][0]["results"]))
        html = (self.root / ".raee/report.html").read_text()
        self.assertNotIn('<script>alert(', html)
        self.assertEqual(rep["overall"], "EVIDENCE_GAPS")

    def test_cli_enforces_contract_on_ci(self):
        req = add_requirement(self.root, "Feature works")
        self.assertEqual(main(["--project", str(self.root), "expect", "--for", req, "--kind", "unit"]), 0)
        self.assertEqual(main(["--project", str(self.root), "check", "--ci"]), 1)
        self.assertEqual(main(["--project", str(self.root), "run", "--allow-ci-execution", "--for", req, "--kind", "unit", "--", sys.executable, "-c", "pass"]), 0)
        self.assertEqual(main(["--project", str(self.root), "check", "--ci"]), 0)

    @unittest.skipUnless(shutil.which('git'), "git required")
    def test_test_weakening_diff_flags_are_heuristic(self):
        root = self.root
        (root / "tests").mkdir()
        test = root / "tests/test_sample.py"
        test.write_text("def test_thing():\n    assert 1 == 1\n")
        cmds = [["git", "init", "-q"], ["git", "add", "."],
                ["git", "-c", "user.name=Test", "-c", "user.email=t@example.com", "commit", "-qm", "base"]]
        for cmd in cmds:
            subprocess.run(cmd, cwd=root, check=True, capture_output=True)
        test.write_text("import pytest\n@pytest.mark.skip(reason='temp')\ndef test_thing():\n    pass\n")
        signals = risk_signals(root)
        reasons = {s["reason"] for s in signals}
        self.assertIn("new_test_skip_markers", reasons)
        self.assertIn("removed_test_assertions", reasons)


if __name__ == "__main__":
    unittest.main()
