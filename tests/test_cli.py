from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from raee_lite.core import add_boundary, add_requirement, audit, init, run_check, save_report


class EvidenceRoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "main.py").write_text("print('hello')\n", encoding="utf-8")
        init(self.root)

    def test_empty_plan_is_not_proven(self):
        self.assertEqual(audit(self.root)["overall"], "INSUFFICIENT_EVIDENCE")

    def test_observed_pass_and_freshness(self):
        r = add_requirement(self.root, "Python can start")
        out = run_check(self.root, r, ["python", "-c", "print('ok')"], 30)
        self.assertEqual(out["observed_exit_code"], 0)
        self.assertEqual(audit(self.root)["overall"], "CHECKS_PASSED_WITH_LIMITS")
        (self.root / "main.py").write_text("print('different')\n", encoding="utf-8")
        self.assertEqual(audit(self.root)["overall"], "STALE_EVIDENCE")

    def test_failure_is_not_passed(self):
        r = add_requirement(self.root, "Command succeeds")
        run_check(self.root, r, ["python", "-c", "raise SystemExit(2)"], 30)
        self.assertEqual(audit(self.root)["requirements"][0]["state"], "FAILED_CHECK")

    def test_missing_requirement_does_not_count(self):
        a = add_requirement(self.root, "A")
        add_requirement(self.root, "B")
        run_check(self.root, a, ["python", "-c", "pass"], 30)
        self.assertEqual(audit(self.root)["overall"], "INSUFFICIENT_EVIDENCE")

    def test_boundaries_in_report(self):
        add_boundary(self.root, "Production database was not contacted")
        report = save_report(self.root)
        self.assertIn("Production database was not contacted", report["boundary_notes"])
        self.assertIn("Production database", (self.root / ".raee/report.md").read_text())

    def test_evidence_contains_roles(self):
        r = add_requirement(self.root, "Python can start")
        run_check(self.root, r, ["python", "-c", "pass"], 30)
        data = json.loads((self.root / ".raee/ledger.json").read_text())
        self.assertEqual(data["runs"][0]["role"], "verification")
        self.assertEqual(len(audit(self.root)["roles"]), 5)


if __name__ == "__main__":
    unittest.main()
