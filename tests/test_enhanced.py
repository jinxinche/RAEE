from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raee_lite.cli import main
from raee_lite.core import add_requirement, init, run_check
from raee_lite.discovery import Check, discover
from raee_lite.enhanced import (audit, ensure_initialized, html_report,
                                is_passing, run_discovered, save_report)


class EnhancedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "app.py").write_text("print('hello')\n", encoding="utf-8")

    def test_check_auto_init_no_execution(self):
        self.assertEqual(main(["--project", str(self.root), "check"]), 0)
        self.assertTrue((self.root / ".raee" / "report.html").exists())
        self.assertEqual(audit(self.root)["overall"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(main(["--project", str(self.root), "check", "--ci"]), 1)

    def test_doctor_is_read_only(self):
        self.assertEqual(main(["--project", str(self.root), "doctor"]), 0)
        self.assertFalse((self.root / ".raee").exists())

    def test_detect_package_scripts_without_execution(self):
        (self.root / "package.json").write_text(json.dumps({"scripts": {
            "test": "echo ok", "build": "tsc", "lint": "eslint ."
        }}), encoding="utf-8")
        found, _ = discover(self.root)
        self.assertEqual([x.kind for x in found], ["test", "lint", "build"] if __import__('shutil').which('npm') else [])
        # Tool discovery has not executed any script.
        self.assertFalse((self.root / "dist").exists())

    def test_auto_check_pass_then_stale(self):
        ensure_initialized(self.root)
        check = Check("auto:smoke", "test", (sys.executable, "-c", "print('ok')"), "fixture")
        with patch("raee_lite.enhanced.discover", return_value=([check], [])):
            self.assertEqual(audit(self.root)["overall"], "INSUFFICIENT_EVIDENCE")
            result = run_discovered(self.root, check)
            self.assertEqual(result["observed_exit_code"], 0)
            self.assertEqual(audit(self.root)["overall"], "AUTOCHECKS_PASSED_WITH_LIMITS")
            self.assertTrue(is_passing(audit(self.root)))
            self.assertFalse(is_passing(audit(self.root), strict=True))
            (self.root / "app.py").write_text("print('later')\n", encoding="utf-8")
            self.assertEqual(audit(self.root)["overall"], "STALE_EVIDENCE")

    def test_failed_auto_check_is_failure(self):
        ensure_initialized(self.root)
        check = Check("auto:smoke", "test", (sys.executable, "-c", "raise SystemExit(3)"), "fixture")
        with patch("raee_lite.enhanced.discover", return_value=([check], [])):
            run_discovered(self.root, check)
            self.assertEqual(audit(self.root)["overall"], "FAILED_CHECK")

    def test_discovered_check_does_not_satisfy_user_requirement(self):
        ensure_initialized(self.root)
        add_requirement(self.root, "User sign-in works")
        check = Check("auto:smoke", "test", (sys.executable, "-c", "pass"), "fixture")
        with patch("raee_lite.enhanced.discover", return_value=([check], [])):
            run_discovered(self.root, check)
            result = audit(self.root)
            self.assertEqual(result["requirements"][0]["state"], "UNTESTED")
            self.assertEqual(result["overall"], "INSUFFICIENT_EVIDENCE")

    def test_user_requirement_check_still_works(self):
        init(self.root)
        r = add_requirement(self.root, "An explicit check ran")
        run_check(self.root, r, [sys.executable, "-c", "pass"], 30)
        self.assertEqual(audit(self.root)["overall"], "CHECKS_PASSED_WITH_LIMITS")
        self.assertTrue(is_passing(audit(self.root), strict=True))

    def test_html_escapes_untrusted_content(self):
        ensure_initialized(self.root)
        add_requirement(self.root, '<script>alert("XSS")</script>')
        page = html_report(audit(self.root))
        self.assertNotIn('<script>alert(', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertIn('default-src', page)

    def test_html_report_created(self):
        ensure_initialized(self.root)
        rep = save_report(self.root)
        self.assertIn("version", rep)
        for name in ("report.json", "report.md", "report.html"):
            self.assertTrue((self.root / ".raee" / name).is_file())

    def test_no_downloads_or_llm_calls_in_default(self):
        (self.root / "package.json").write_text('{"scripts": {"test":"node test.js"}}', encoding="utf-8")
        (self.root / "test.js").write_text("require('fs').writeFileSync('SHOULD_NOT_EXIST','bad')")
        main(["--project", str(self.root), "check"])
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())


if __name__ == "__main__":
    unittest.main()


class SkillInstallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_install_agent_skill_is_explicit_and_idempotent(self):
        from raee_lite.skills import install_skill
        installed = install_skill(self.root, "codex")
        self.assertTrue(installed)
        skill = self.root / ".agents/skills/raee-lite/SKILL.md"
        self.assertIn("name: raee-lite", skill.read_text(encoding="utf-8"))
        self.assertIn("already current", install_skill(self.root, "codex")[0])

    def test_skill_never_overwrites_user_content(self):
        from raee_lite.skills import install_skill
        path = self.root / ".cursor/skills/raee-lite/SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text("my custom skill", encoding="utf-8")
        with self.assertRaises(ValueError):
            install_skill(self.root, "cursor")
        self.assertEqual(path.read_text(encoding="utf-8"), "my custom skill")
