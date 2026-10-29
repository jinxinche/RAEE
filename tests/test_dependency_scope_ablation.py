"""Negative controls for explicitly declared source and external dependency scope."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from raee_lite.core import init, add_requirement, run_check, fingerprint, get_manifest, MANIFEST, write_json
from raee_lite.contracts import set_expectation, assess_contracts
from raee_lite.dependency_scope import snapshot, compare
from raee_lite.evidence_binding import current_environment

ROOT = Path(__file__).resolve().parents[1]


class DependencyScopeAblationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(strict=True)
        (self.root / "app.py").write_bytes(b"def validate(x): return bool(x)\n")
        (self.root / "test_app.py").write_bytes(b"assert 1 == 1\n")
        init(self.root)
        self.rid = add_requirement(self.root, "Signup rejects invalid email")
        set_expectation(self.root, self.rid, "unit")
        self.rev = {"service-revision": "v1"}
        self.receipt = run_check(
            self.root, self.rid, [sys.executable, "-c", "pass"], 15, kind="unit",
            dependency_files=["app.py", "test_app.py"], external_revisions=self.rev,
        )

    def status(self, rev=None, *, ext=True, paths=None, context=True):
        values = {}
        if context:
            values[self.rid] = {
                "paths": paths if paths is not None else ["app.py", "test_app.py"],
                "external_revisions": rev if rev is not None else self.rev,
                "check_external": ext,
            }
        return assess_contracts(
            self.root, fingerprint(self.root), target_environment=current_environment(),
            dependency_context=values,
        )[0]["evidence_by_kind"][0]["state"]

    def test_matching_scope_returns_observed_process_only(self):
        self.assertEqual(self.status(), "OBSERVED_PASS")
        self.assertFalse(self.receipt["dependency_scope"]["before"]["dependency_completeness_proven"])

    def test_missing_current_scope_fails_closed(self):
        self.assertEqual(self.status(context=False), "SCOPE_CONTEXT_REQUIRED")

    def test_unrelated_note_preserves_declaration_not_global(self):
        (self.root / "NOTE.txt").write_bytes(b"unrelated note\n")
        self.assertEqual(self.status(), "OBSERVED_PASS")

    def test_declared_source_change_revokes(self):
        (self.root / "app.py").write_bytes(b"def validate(x): return True\n")
        self.assertEqual(self.status(), "DEPENDENCY_SOURCE_CHANGED")

    def test_declared_test_weakened_revokes(self):
        (self.root / "test_app.py").write_bytes(b"assert True\n")
        self.assertEqual(self.status(), "DEPENDENCY_SOURCE_CHANGED")

    def test_external_change_only_matters_when_bound(self):
        changed = {"service-revision": "v2"}
        self.assertEqual(self.status(changed, ext=False), "OBSERVED_PASS")
        self.assertEqual(self.status(changed), "EXTERNAL_STATE_CHANGED")

    def test_changed_declaration_revokes(self):
        (self.root / "another.py").write_bytes(b"pass\n")
        self.assertEqual(self.status(paths=["app.py", "another.py"]), "SCOPE_DECLARATION_CHANGED")

    def test_unavailable_declared_path_revokes(self):
        (self.root / "app.py").unlink()
        self.assertEqual(self.status(), "SCOPE_INPUT_UNAVAILABLE")

    def test_intent_change_still_revokes(self):
        manifest = get_manifest(self.root)
        manifest["requirements"][0]["description"] = "Different requirement"
        write_json(self.root / MANIFEST, manifest)
        self.assertEqual(self.status(), "INTENT_CHANGED")

    def test_no_attempt_to_auto_scan_user_environment(self):
        before = snapshot(self.root, ["app.py"], {"service-revision": "v1"})
        os.environ["RAEE_TEST_ENV_SHOULD_NOT_BE_READ"] = "v2"
        try:
            after = snapshot(self.root, ["app.py"], {"service-revision": "v1"})
        finally:
            os.environ.pop("RAEE_TEST_ENV_SHOULD_NOT_BE_READ", None)
        self.assertEqual(before["binding_sha256"], after["binding_sha256"])

    def test_invalid_or_sensitive_revision_rejected(self):
        for value in ("my secret with spaces", "a" * 129, ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    snapshot(self.root, ["app.py"], {"credential": value})

    def test_traversal_and_duplicate_paths_rejected(self):
        for paths in (["../etc/passwd"], ["/tmp/a"], ["app.py", "app.py"], []):
            with self.subTest(paths=paths):
                with self.assertRaises(ValueError):
                    snapshot(self.root, paths, self.rev)

    @unittest.skipIf(os.name == "nt", "Windows symlink creation requires developer privileges")
    def test_project_symlink_path_not_followed(self):
        (self.root / "link.py").symlink_to(self.root / "app.py")
        with self.assertRaises(ValueError):
            snapshot(self.root, ["link.py"], self.rev)

    def test_scope_omission_can_miss_important_change(self):
        (self.root / "other_important.py").write_bytes(b"validate = lambda x: True\n")
        # The system cannot know this undeclared file was relevant.
        self.assertEqual(self.status(), "OBSERVED_PASS")

    def test_excluded_external_label_can_miss_change(self):
        # No direct OS environment scanning is a privacy property AND a limit.
        self.assertEqual(self.status(), "OBSERVED_PASS")


if __name__ == "__main__":
    unittest.main()
