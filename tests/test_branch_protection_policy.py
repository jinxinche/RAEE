"""Run the real protection helper with an in-process shell fake for gh.

These tests validate local decisions and read-only API handling, not live rules.
Every gh call is intercepted; unexpected commands (including writes) fail.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/protect_main.sh"
AUTH_CALL = "auth status"
VISIBILITY_CALL = "repo view jinxinche/RAEE --json visibility --jq .visibility"
READ_CALL = (
    "api --method GET repos/jinxinche/RAEE/branches/main/protection "
    "-H Accept: application/vnd.github+json"
)
HARNESS = r'''
gh() {
  printf '%s\n' "$*" >> "$FAKE_GH_LOG"
  case "$*" in
    'auth status') return "$FAKE_GH_AUTH_STATUS" ;;
    'repo view jinxinche/RAEE --json visibility --jq .visibility')
      printf '%s\n' "$FAKE_GH_VISIBILITY" ;;
    'api --method GET repos/jinxinche/RAEE/branches/main/protection -H Accept: application/vnd.github+json')
      printf '%s\n' "$FAKE_GH_PROTECTION"
      return "$FAKE_GH_API_STATUS" ;;
    *) printf 'Unexpected gh command: %s\n' "$*" >&2; return 97 ;;
  esac
}
source "$@"
'''


def bash_executable():
    # Prefer Git Bash to the Windows WSL launcher. Hosted Windows CI has Git.
    git = shutil.which("git")
    if os.name == "nt" and git:
        candidate = Path(git).resolve().parent.parent / "bin/bash.exe"
        if candidate.is_file():
            return str(candidate)
    bash = shutil.which("bash")
    if not bash:
        raise RuntimeError("Bash is required to exercise scripts/protect_main.sh")
    return bash


def live_policy():
    """A classic-protection response fixture, independent of the local policy."""
    return {
        "required_status_checks": {
            "strict": True,
            "contexts": ["pr-boundary-inspection", "Trusted regression gate"],
        },
        "required_pull_request_reviews": {
            "required_approving_review_count": 0,
            "dismiss_stale_reviews": False,
            "require_code_owner_reviews": False,
            "require_last_push_approval": False,
        },
        "enforce_admins": {"enabled": True},
        "required_conversation_resolution": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "restrictions": None,
    }


class BranchProtectionPolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="raee protection ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        # Windows checkouts may use CRLF; Bash needs LF in the script it sources.
        self.helper = self.root / "protect_main.sh"
        self.helper.write_text(HELPER.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        self.policy_path = self.root / ".github/branch-protection.json"
        self.policy_path.parent.mkdir()
        self.policy = json.loads((ROOT / ".github/branch-protection.json").read_text(encoding="utf-8"))
        self.write_policy(self.policy)
        self.log = self.root / "gh-calls.txt"

    def write_policy(self, value):
        self.policy_path.write_text(json.dumps(value), encoding="utf-8")

    def run_helper(self, *args, response=None, auth_status=0, visibility="PUBLIC", api_status=0):
        self.log.write_text("", encoding="utf-8")
        environment = os.environ.copy()
        environment.pop("BASH_ENV", None)
        environment.pop("ENV", None)
        environment.update({
            "PYTHON": Path(sys.executable).as_posix(),
            "FAKE_GH_LOG": self.log.as_posix(),
            "FAKE_GH_AUTH_STATUS": str(auth_status),
            "FAKE_GH_VISIBILITY": visibility,
            "FAKE_GH_PROTECTION": json.dumps(live_policy()) if response is None else response,
            "FAKE_GH_API_STATUS": str(api_status),
        })
        result = subprocess.run(
            [bash_executable(), "--noprofile", "--norc", "-c", HARNESS,
             "protection-test", self.helper.as_posix(), *args],
            cwd=self.root, env=environment, text=True, capture_output=True, timeout=20,
        )
        return result, self.log.read_text(encoding="utf-8").splitlines()

    def assert_rejected(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("GitHub classic main protection verified:", result.stdout)

    def test_validate_is_offline_even_without_authentication(self):
        result, calls = self.run_helper("--solo-maintainer", "--validate", auth_status=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        self.assertIn("Local validation only", result.stdout)
        self.assertNotIn("GitHub classic main protection verified:", result.stdout)

    def test_missing_local_check_blocks_apply_before_any_gh_call(self):
        for missing in ("pr-boundary-inspection", "Trusted regression gate"):
            with self.subTest(missing=missing):
                policy = copy.deepcopy(self.policy)
                policy["required_status_checks"]["contexts"].remove(missing)
                self.write_policy(policy)
                result, calls = self.run_helper("--solo-maintainer", "--apply")
                self.assert_rejected(result)
                self.assertEqual(calls, [])

    def test_local_solo_maintainer_and_safety_drift_blocks_apply(self):
        mutations = [
            ("required_status_checks", "strict", False),
            ("required_pull_request_reviews", "required_approving_review_count", 1),
            ("required_pull_request_reviews", "required_approving_review_count", False),
            ("required_pull_request_reviews", "require_code_owner_reviews", True),
            ("required_pull_request_reviews", "dismiss_stale_reviews", True),
            ("required_pull_request_reviews", "require_last_push_approval", True),
            (None, "enforce_admins", False),
            (None, "required_conversation_resolution", False),
            (None, "allow_force_pushes", True),
            (None, "allow_deletions", True),
            (None, "block_creations", True),
            (None, "restrictions", {"users": [], "teams": [], "apps": []}),
            (None, "required_pull_request_reviews", None),
        ]
        for section, field, value in mutations:
            with self.subTest(section=section, field=field, value=value):
                policy = copy.deepcopy(self.policy)
                (policy if section is None else policy[section])[field] = value
                self.write_policy(policy)
                result, calls = self.run_helper("--solo-maintainer", "--apply")
                self.assert_rejected(result)
                self.assertEqual(calls, [])

    def test_missing_or_malformed_local_policy_never_calls_gh(self):
        for raw in (None, "{", "null", "[]", "{}"):
            with self.subTest(raw=raw):
                if raw is None:
                    self.policy_path.unlink()
                else:
                    self.policy_path.write_text(raw, encoding="utf-8")
                result, calls = self.run_helper("--solo-maintainer", "--apply")
                self.assert_rejected(result)
                self.assertEqual(calls, [])

    def test_invalid_arguments_cannot_fall_through_to_apply(self):
        for args in ((), ("--apply",), ("--solo-maintainer", "--unknown"),
                     ("--solo-maintainer", ""),
                     ("--solo-maintainer", "--apply", "--validate"),
                     ("--solo-maintainer", "--check", "--apply")):
            with self.subTest(args=args):
                result, calls = self.run_helper(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(calls, [])

    def test_default_and_explicit_check_are_read_only(self):
        for args in (("--solo-maintainer",), ("--solo-maintainer", "--check")):
            with self.subTest(args=args):
                result, calls = self.run_helper(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [AUTH_CALL, VISIBILITY_CALL, READ_CALL])
                self.assertIn("GitHub classic main protection verified:", result.stdout)
                self.assertIn("Inspect repository Rulesets separately", result.stdout)

    def test_readback_accepts_reordered_and_additional_required_checks(self):
        response = live_policy()
        response["required_status_checks"]["contexts"] = [
            "additional-check", "Trusted regression gate", "pr-boundary-inspection",
        ]
        result, calls = self.run_helper("--solo-maintainer", "--check", response=json.dumps(response))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [AUTH_CALL, VISIBILITY_CALL, READ_CALL])

    def test_readback_rejects_either_missing_check_and_wrong_context_types(self):
        for contexts in (["pr-boundary-inspection"], ["Trusted regression gate"], [], None,
                         "pr-boundary-inspection, Trusted regression gate",
                         {"pr-boundary-inspection": True, "Trusted regression gate": True}):
            with self.subTest(contexts=contexts):
                response = live_policy()
                response["required_status_checks"]["contexts"] = contexts
                result, calls = self.run_helper("--solo-maintainer", "--check", response=json.dumps(response))
                self.assert_rejected(result)
                self.assertEqual(calls, [AUTH_CALL, VISIBILITY_CALL, READ_CALL])

    def test_readback_rejects_solo_maintainer_or_safety_drift(self):
        mutations = [
            ("required_status_checks", "strict", False),
            ("required_pull_request_reviews", "required_approving_review_count", 1),
            ("required_pull_request_reviews", "required_approving_review_count", False),
            ("required_pull_request_reviews", "dismiss_stale_reviews", True),
            ("required_pull_request_reviews", "require_code_owner_reviews", True),
            ("required_pull_request_reviews", "require_last_push_approval", True),
            ("enforce_admins", "enabled", False),
            ("required_conversation_resolution", "enabled", False),
            ("allow_force_pushes", "enabled", True),
            ("allow_deletions", "enabled", True),
            (None, "required_pull_request_reviews", None),
            (None, "restrictions", {"users": [], "teams": [], "apps": []}),
        ]
        for section, field, value in mutations:
            with self.subTest(section=section, field=field, value=value):
                response = live_policy()
                (response if section is None else response[section])[field] = value
                result, calls = self.run_helper("--solo-maintainer", "--check", response=json.dumps(response))
                self.assert_rejected(result)
                self.assertEqual(calls, [AUTH_CALL, VISIBILITY_CALL, READ_CALL])

    def test_unauthenticated_check_stops_without_login_or_api_calls(self):
        result, calls = self.run_helper("--solo-maintainer", "--check", auth_status=1)
        self.assert_rejected(result)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [AUTH_CALL])
        self.assertIn("authentication unavailable", result.stderr)

    def test_nonpublic_repository_stops_before_protection_api(self):
        result, calls = self.run_helper("--solo-maintainer", "--check", visibility="PRIVATE")
        self.assert_rejected(result)
        self.assertEqual(calls, [AUTH_CALL, VISIBILITY_CALL])

    def test_failed_or_invalid_api_response_never_claims_verification(self):
        for status, body in ((1, '{"message": "Branch not protected"}'),
                             (1, json.dumps(live_policy())), (0, ""), (0, "{"),
                             (0, "null"), (0, "[]"), (0, "{}")):
            with self.subTest(status=status, body=body):
                result, calls = self.run_helper(
                    "--solo-maintainer", "--check", response=body, api_status=status,
                )
                self.assert_rejected(result)
                self.assertEqual(calls, [AUTH_CALL, VISIBILITY_CALL, READ_CALL])


if __name__ == "__main__":
    unittest.main()
