"""No-model tests of the one-use, same-worktree PCP-light #734 recovery.

All actual Git mutations happen inside a disposable unittest temp directory;
Codex, Github, Docker, Owner worktrees and project services are never touched.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/pcp-light-pr734-delivery.py"
SPEC = importlib.util.spec_from_file_location("pcp_light_pr734_delivery", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
V = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V)


def original_journal():
    return {
        "issue": V.ISSUE, "key": V.KEY,
        "body_sha256": V.BODY_SHA256, "base_sha": V.BASE,
        "branch": V.BRANCH, "state": "source_checked",
        "model_calls": 1,
        "usage": {
            "terminal": "turn.completed", "input_tokens": 146000,
            "cached_input_tokens": 120000,
            "uncached_input_tokens": 26000, "output_tokens": 3000,
            "cached_input_share_percent": 82.2,
            "raw_agent_output": "DONT_PRINT_SECRET",
        },
        "changed_paths": sorted(V.FILES),
        "syntax_checked_paths": sorted(V.FILES),
        "local_tests_executed": 0,
        "hosted_full_ci": "PENDING",
        "elapsed_seconds": 90.8,
        "context_footprint": {"required_authority_bytes": 180000,
                              "raw_doc": "DONT_PRINT_DOC"},
    }


class PCP734DeliveryTests(unittest.TestCase):
    def test_only_original_completed_one_model_source_checked_is_eligible(self):
        V.validate_journal(original_journal())
        for change in (
            {"model_calls": 0}, {"model_calls": 2},
            {"issue": 729}, {"state": "claimed"},
            {"state": "model_finished"}, {"state": "committed"},
            {"base_sha": "a" * 40}, {"body_sha256": "f" * 64},
            {"usage": {"terminal": "turn.failed"}},
            {"changed_paths": []}, {"syntax_checked_paths": []},
            {"local_tests_executed": 1}, {"hosted_full_ci": "SUCCESS"},
        ):
            with self.subTest(change=change):
                with self.assertRaisesRegex(V.Stop, "original_journal_incompatible"):
                    V.validate_journal({**original_journal(), **change})

    def test_exact_new_staged_paths_only(self):
        values = sorted(V.FILES)
        sample = "".join("A\0" + path + "\0" for path in values)
        self.assertEqual(V.exact_staged_paths(sample), V.FILES)
        for bad in (
            "", "A\0" + values[0] + "\0", sample + "A\0bad.py\0",
            sample.replace("A\0", "D\0", 1),
            sample.replace(values[1], values[0]),
            sample.replace("A\0", "M\0", 1),
        ):
            with self.subTest(value=bad[:30]):
                with self.assertRaisesRegex(V.Stop, "staged_scope_mismatch"):
                    V.exact_staged_paths(bad)

    def test_accepts_only_one_new_blank_eof_diagnostic(self):
        path = sorted(V.FILES)[0]
        good = path + ":12: new blank line at EOF.\n"
        self.assertEqual(V.warning_target(2, good, ""), path)
        for rc, out, err in (
            (0, good, ""),
            (2, good + good, ""),
            (2, path + ":1: trailing whitespace.\n+a = 1   \n", ""),
            (2, ".github/workflows/tests.yml:1: new blank line at EOF.\n", ""),
            (2, good, "fatal: unexpected"),
            (2, path + ":1: conflict marker.\n", ""),
        ):
            with self.subTest(out=out[:50]):
                with self.assertRaisesRegex(V.Stop, "unrecognized_git_check"):
                    V.warning_target(rc, out, err)

    def test_eof_removal_keeps_identical_python_ast(self):
        original = b"def f():\n    return {'text': 'keep  spaces'}\n\n\n"
        self.assertEqual(
            V.corrected_eof(original),
            b"def f():\n    return {'text': 'keep  spaces'}\n",
        )
        for bad in (b"", b"x=1\n", b"def broken(:\n\n", b"a=1\r\n\r\n"):
            with self.subTest(value=bad[:14]):
                with self.assertRaises(V.Stop):
                    V.corrected_eof(bad)

    def test_actual_git_index_emits_exact_warning_and_passes_after_eof_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "disposable"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)],
                           capture_output=True, check=True)
            for path in sorted(V.FILES):
                target = repo / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(
                    b"def x():\n    return 1\n\n" if path.startswith("scripts/")
                    else b"def test_x():\n    assert True\n"
                )
            subprocess.run(["git", "-C", str(repo), "add", "--", *sorted(V.FILES)],
                           capture_output=True, check=True)
            with patch.object(V, "WS", repo):
                result = V.git("diff", "--cached", "--no-ext-diff", "--check")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(len(result.stdout.splitlines()), 1)
                target_name = V.warning_target(
                    result.returncode, result.stdout, result.stderr)
                self.assertEqual(target_name, "scripts/pcp-light-pr-review.py")
                target = repo / target_name
                target.write_bytes(V.corrected_eof(target.read_bytes()))
                subprocess.run(["git", "-C", str(repo), "add", "--", target_name],
                               capture_output=True, check=True)
                passed = V.git("diff", "--cached", "--no-ext-diff", "--check")
                self.assertEqual(passed.returncode, 0)
                self.assertEqual(passed.stdout, "")
                self.assertEqual(passed.stderr, "")

    def test_one_use_0600_and_nonleaking_pr_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "receipt.json"
            V.private_create(p, b'{"state":"claimed"}\n')
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                V.private_create(p, b'{"state":"retry"}\n')
            self.assertEqual(p.read_bytes(), b'{"state":"claimed"}\n')
        body = V.draft_pr_body({
            "model_elapsed_seconds": 90.8,
            "usage": original_journal()["usage"],
            "context_footprint": original_journal()["context_footprint"],
            "raw_secret": "DONT_PRINT_SOURCE",
        }, "c" * 40)
        obj = json.loads(body.split(chr(96) * 3 + "json\n", 1)[1]
                         .split("\n" + chr(96) * 3, 1)[0])
        self.assertEqual(obj["candidate_sha"], "c" * 40)
        self.assertEqual(obj["model_calls"], 1)
        self.assertEqual(obj["additional_model_calls"], 0)
        self.assertEqual(obj["model_elapsed_seconds"], 90.8)
        self.assertEqual(obj["uncached_input_tokens"], 26000)
        self.assertEqual(obj["hosted_full_ci"], "PENDING")
        self.assertEqual(obj["local_tests_executed"], 0)
        self.assertEqual(obj["provider_cash_cost"], "UNAVAILABLE")
        self.assertNotIn("DONT_PRINT_SECRET", body)
        self.assertNotIn("DONT_PRINT_DOC", body)
        self.assertNotIn("DONT_PRINT_SOURCE", body)
        with self.assertRaisesRegex(V.Stop, "candidate_sha_invalid"):
            V.draft_pr_body({}, "invalid")

    def test_mock_delivery_retains_original_evidence_without_codex(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "one-existing-job"
            root.mkdir(mode=0o700)
            ws = root / "workspace"
            ws.mkdir()
            jfile = root / "journal.json"
            V.private_create(jfile, (
                json.dumps(original_journal(), sort_keys=True) + "\n"
            ).encode())
            before_journal = jfile.read_bytes()
            target_name = "scripts/pcp-light-pr-review.py"
            target = ws / target_name
            target.parent.mkdir()
            original = b"def f():\n    return 12\n\n"
            target.write_bytes(original)
            other = ws / "tests/test_pcp_light_pr_review.py"
            other.parent.mkdir()
            other.write_text("def test_f(): assert True\n")
            staged = False
            commands = []
            def fake_checked(args, **kw):
                nonlocal staged
                commands.append(args)
                if "add" in args:
                    staged = True
                if args[:3] == ["gh", "pr", "create"]:
                    return "https://github.com/" + V.REPO + "/pull/900"
                return ""
            def fake_git_ok(*args):
                if args == ("diff", "--no-ext-diff", "--name-only"):
                    return "" if staged else target_name
                if args == ("diff", "--cached", "--no-ext-diff",
                            "--no-renames", "--name-status", "-z"):
                    return "".join("A\0" + n + "\0" for n in sorted(V.FILES))
                if args == ("rev-parse", "HEAD"):
                    return "c" * 40
                if args == ("rev-parse", "HEAD^"):
                    return V.BASE
                if args == ("diff", "--no-ext-diff", "--name-only",
                            V.BASE, "HEAD"):
                    return "\n".join(sorted(V.FILES))
                return ""
            with patch.object(V, "ROOT", root), patch.object(
                V, "WS", ws), patch.object(V, "JOURNAL", jfile), patch.object(
                V, "RECEIPT", root / "pr734-one-use-delivery.json"
            ), patch.object(V, "preflight", return_value={
                "warning_path": target_name,
                "usage": original_journal()["usage"],
                "context_footprint": original_journal()["context_footprint"],
                "model_elapsed_seconds": 90.8,
            }), patch.object(V, "git_ok", side_effect=fake_git_ok), patch.object(
                V, "checked", side_effect=fake_checked), patch.object(
                V, "git", return_value=subprocess.CompletedProcess(
                    ["git"], 0, "", ""
                )
            ):
                result = V.deliver(Path(tmp), V.BASE)
            self.assertEqual(result["additional_model_calls"], 0)
            self.assertEqual(result["hosted_full_ci"], "PENDING")
            self.assertEqual(result["candidate_sha"], "c" * 40)
            self.assertEqual(jfile.read_bytes(), before_journal)
            self.assertEqual(
                (root / "pr734-original-codex-staged.snapshot").read_bytes(),
                original,
            )
            self.assertEqual(json.loads(
                (root / "pr734-one-use-delivery.json").read_text()
            )["state"], "draft_pr_created")
            self.assertTrue(any("push" in c for c in commands))
            self.assertTrue(any(c[:3] == ["gh", "pr", "create"]
                                and "--draft" in c for c in commands))
            self.assertFalse(any("codex" in c for c in commands))


if __name__ == "__main__":
    unittest.main()
