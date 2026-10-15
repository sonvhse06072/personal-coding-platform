"""No-model, no-GitHub, no-Docker regression tests for PCP-light #725.

Tests only the ORIGINAL state guards, static Python syntax check, one-time
claim, and a fully mocked host-delivery path. Never executes real Codex
output, invokes the Github API or creates a real worktree.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "scripts/pcp-light-existing-verification.py"
SPEC = importlib.util.spec_from_file_location("pcp_light_verify_original", SOURCE)
assert SPEC and SPEC.loader
V = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V)


class PCPExistingVerificationTests(unittest.TestCase):

    def good_journal(self):
        return {
            "issue": 725,
            "key": V.KEY,
            "branch": V.BRANCH,
            "base_sha": V.BASE,
            "body_sha256": V.ISSUE_SHA256,
            "state": "model_finished",
            "model_calls": 1,
            "usage": {
                "terminal": "turn.completed",
                "input_tokens": 100,
                "output_tokens": 25,
            },
        }

    def test_original_one_completed_turn_required(self):
        V.validate_journal(self.good_journal())
        for patch_fields in (
            {"model_calls": 0},
            {"model_calls": 2},
            {"state": "model_reserved"},
            {"state": "tests_passed"},
            {"usage": {"terminal": "turn.failed"}},
            {"issue": 596},
            {"key": "different-job"},
            {"base_sha": "0" * 40},
            {"body_sha256": "0" * 64},
        ):
            with self.subTest(patch_fields=patch_fields):
                with self.assertRaisesRegex(
                    V.Stop, "pcp_light_original_job_not_one_completed_codex_turn"
                ):
                    V.validate_journal({**self.good_journal(), **patch_fields})

    def test_exact_two_files_no_staged_deleted_or_symlinks(self):
        V.validate_scope(set(V.FILES), staged=False, deleted=False, symlinks=False)
        cases = [
            ({"scripts/pcp-light-run.py"}, False, False, False),
            (set(V.FILES) | {".github/workflows/tests.yml"}, False, False, False),
            (set(V.FILES), True, False, False),
            (set(V.FILES), False, True, False),
            (set(V.FILES), False, False, True),
        ]
        for changed, staged, deleted, symlinks in cases:
            with self.subTest(changed=changed, staged=staged,
                              deleted=deleted, symlinks=symlinks):
                with self.assertRaisesRegex(V.Stop, "exact_two_file_scope"):
                    V.validate_scope(changed, staged=staged,
                                     deleted=deleted, symlinks=symlinks)

    def test_static_check_parses_without_running_generated_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for relative in V.FILES:
                path = base / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "raise RuntimeError('MUST_NOT_RUN')\n"
                    "def enough(): return 42\n",
                    encoding="utf-8",
                )
            self.assertEqual(V.validate_python_syntax(base), 2)
            script = base / "scripts/pcp-light-run.py"
            script.write_text("def broken(\n", encoding="utf-8")
            with self.assertRaisesRegex(V.Stop, "generated_python_syntax_invalid"):
                V.validate_python_syntax(base)

    def test_private_claim_is_exclusive_without_original_journal_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "receipt.json"
            V.private_write_new(path, {"state": "claimed", "model_calls_added": 0})
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            with self.assertRaises(FileExistsError):
                V.private_write_new(path, {"state": "retry"})
            self.assertEqual(json.loads(path.read_text())["state"], "claimed")

    def test_readonly_preflight_preserves_original_worktree_and_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pcp-light" / "jobs" / V.KEY
            workspace = root / "workspace"
            repo = Path(tmp) / "repo"
            root.mkdir(parents=True, mode=0o700)
            workspace.mkdir(mode=0o700)
            repo.mkdir()
            (repo / ".git").mkdir()
            journal = root / "journal.json"
            V.private_write_new(journal, self.good_journal())
            for relative in V.FILES:
                file = workspace / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("pass\n")
            index = {
                ("rev-parse", "--show-toplevel", str(repo)): str(repo),
                ("rev-parse", "--show-toplevel", str(workspace)): str(workspace),
            }
            def fake_git(where, *args):
                if args == ("rev-parse", "--show-toplevel"):
                    return str(where)
                if args == ("branch", "--show-current"):
                    return "main" if where == repo else V.BRANCH
                if args == ("rev-parse", "HEAD"):
                    return "b" * 40 if where == repo else V.BASE
                if args == ("remote", "get-url", "origin"):
                    return "https://github.com/" + V.REPO + ".git"
                if args == ("rev-parse", "--git-common-dir"):
                    return str(repo / ".git")
                if args == ("diff", "--no-ext-diff", "--name-only", "HEAD"):
                    return "\n".join(sorted(V.FILES))
                return ""
            with patch.object(V, "ROOT", root), patch.object(
                V, "WORKSPACE", workspace
            ), patch.object(V, "JOURNAL", journal), patch.object(
                V, "EVIDENCE", root / "verification-continuation-v1.json"
            ), patch.object(V, "git", side_effect=fake_git), patch.object(
                V, "verify_original_issue"
            ) as gh:
                report = V.preflight(repo, "b" * 40)
                self.assertEqual(report["original_model_calls"], 1)
                self.assertEqual(report["changed_paths"], sorted(V.FILES))
                gh.assert_called_once()
                self.assertEqual(json.loads(journal.read_text())["state"],
                                 "model_finished")

    def test_mock_delivery_never_runs_codex_pytest_or_unittest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / "journal.json"
            V.private_write_new(journal, self.good_journal())
            outcome = root / "verification-continuation-v1.json"
            ws = root / "workspace"
            ws.mkdir()
            # Keep real changed-file safety guard in place: the mock job has
            # both actual regular allowed files (never symlinks).
            for relative in V.FILES:
                target = ws / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("pass\n", encoding="utf-8")
            repo = root / "pcp"
            repo.mkdir()
            history = []
            expected_commit = "c" * 40

            def fake_git(path, *args):
                if args == ("rev-parse", "HEAD"):
                    return expected_commit
                if args == ("rev-parse", "HEAD^"):
                    return V.BASE
                if args == ("diff", "--name-only", V.BASE, "HEAD"):
                    return "\n".join(sorted(V.FILES))
                return ""

            def fake_checked(argv, **kwargs):
                history.append(argv)
                if argv[:3] == ["gh", "pr", "create"]:
                    return "https://github.com/" + V.REPO + "/pull/900"
                return ""

            with patch.object(V, "ROOT", root), patch.object(
                V, "JOURNAL", journal
            ), patch.object(V, "EVIDENCE", outcome), patch.object(
                V, "WORKSPACE", ws
            ), patch.object(V, "preflight", return_value={
                "changed_paths": sorted(V.FILES)
            }), patch.object(V, "validate_python_syntax", return_value=2
            ), patch.object(V, "inspect_changed_paths", return_value=set(V.FILES)
            ), patch.object(V, "git", side_effect=fake_git
            ), patch.object(V, "checked", side_effect=fake_checked
            ), patch.object(V, "command") as raw:
                result = V.deliver(repo, "b" * 40)
                self.assertEqual(result["additional_model_calls"], 0)
                self.assertEqual(result["local_tests_executed"], 0)
                self.assertEqual(result["hosted_full_ci"], "PENDING")
                self.assertEqual(json.loads(journal.read_text())["state"],
                                 "model_finished")
                self.assertEqual(json.loads(outcome.read_text())["state"],
                                 "draft_pr_created")
                raw.assert_not_called()
                with self.assertRaises(FileExistsError):
                    V.deliver(repo, "b" * 40)
                self.assertEqual(result["candidate_sha"], expected_commit)
            flattened = repr(history)
            self.assertIn("'commit'", flattened)
            self.assertIn("'push'", flattened)
            self.assertIn("'--draft'", flattened)
            self.assertNotIn("'codex'", flattened)
            self.assertNotIn("'pytest'", flattened)
            self.assertNotIn("'docker'", flattened)

    def test_source_forbids_unrelated_scope_and_rerun(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("1dcb7696dba25695054bb4743967ae71fc38c896", text)
        self.assertIn("f9bbf88e12b01e0718bbd36d60e4bd591e0ba7ad8bf3eaf5b18a613a6258c04f", text)
        self.assertNotIn("subprocess.run(['codex'", text)
        self.assertNotIn("docker compose", text)
        self.assertNotIn("shutil.rmtree", text)
        self.assertNotIn("git reset", text)
        self.assertIn('"model_calls_added": 0', text)
        self.assertIn('O_CREAT | os.O_EXCL', text)


if __name__ == "__main__":
    unittest.main()
