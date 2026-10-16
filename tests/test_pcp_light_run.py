"""No-model tests for PCP-light GitHub -> native Codex handoff.

Every command, agent/provider, filesystem mutation and gh API is mocked unless
explicitly using a fresh temporary directory owned only by this test.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/pcp-light-run.py"


def module():
    spec = importlib.util.spec_from_file_location("pcp_light_runner", FILE)
    assert spec and spec.loader
    instance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(instance)
    return instance


M = module()
SOURCE = "a" * 40
GOOD_TASK = {
    "version": 1, "key": "simple-bounded-fix", "base_sha": SOURCE,
    "model": "gpt-6-luna", "reasoning": "medium",
    "goal": "Implement one bounded new PCP-light adapter behavior and its tests.",
    "allowed_paths": ["scripts/pcp-light-run.py", "tests/test_pcp_light_run.py"],
}


def issue(task=None, *, author=None):
    body = M.MARKER + "\n" + json.dumps(task or GOOD_TASK, sort_keys=True)
    doc = {
        "number": 593, "state": "open",
        "user": {"login": author or M.AUTHOR},
        "labels": [],
        "body": body,
    }
    digest = hashlib.sha256(body.encode()).hexdigest()
    return doc, digest


class PCPFastHandoffTests(unittest.TestCase):
    def test_owner_only_exact_comment_schema_and_sha(self):
        good, digest = issue()
        task = M.parse_issue(good, 593, digest)
        self.assertEqual(task["key"], GOOD_TASK["key"])
        self.assertEqual(task["base_sha"], SOURCE)
        for mutant, marker in (
            ({**good, "number": 592}, "github_issue_identity_denied"),
            ({**good, "user": {"login": "attacker"}}, "github_issue_identity_denied"),
            ({**good, "state": "closed"}, "github_issue_identity_denied"),
            ({**good, "pull_request": {}}, "github_issue_identity_denied"),
        ):
            with self.subTest(marker=marker):
                with self.assertRaisesRegex(M.Stop, marker):
                    M.parse_issue(mutant, 593, digest)
        with self.assertRaisesRegex(M.Stop, "github_issue_body_changed"):
            M.parse_issue(good, 593, "a" * 64)
        with self.assertRaisesRegex(M.Stop, "github_issue_body_changed"):
            M.parse_issue({**good, "body": good["body"] + " edited"}, 593, digest)

    def test_invalid_gh_shape_and_jsonl_do_not_escape_stop(self):
        _, digest = issue()
        with self.assertRaisesRegex(M.Stop, "github_issue_invalid_shape"):
            M.parse_issue([], 593, digest)
        self.assertEqual(M.summarize_codex('[]\n{"type":"turn.failed"}'),
                         {"terminal": "turn.failed", "input_tokens": None,
                          "cached_input_tokens": None, "output_tokens": None,
                          "uncached_input_tokens": None,
                          "cached_input_share_percent": None})

    def test_claimed_journal_is_exclusive_and_private_from_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = Path(folder) / "receipt.json"
            M.write_once(doc, {"state": "claimed", "model_calls": 0})
            self.assertEqual(doc.stat().st_mode & 0o077, 0)
            with self.assertRaises(FileExistsError):
                M.write_once(doc, {"state": "replacement"})
            self.assertEqual(json.loads(doc.read_text())["state"], "claimed")

    def test_no_arbitrary_paths_or_reserved_legacy_project(self):
        for path in [
            "../data.py", ".github/workflows/test.yml",
            "scripts/g1-pcp-t01-one-shot.py", "services/runtime/app/main.py",
            "docs/project/architecture.md", "scripts/pcp-light-../env.py",
            "tests/test_pcp_light_../../private.py",
            "/home/sonvh/chonhac/src.py",
        ]:
            with self.subTest(path=path):
                self.assertFalse(M.allowed_path(path))
        for path in (
            "scripts/pcp-light-notes.md", "tests/test_pcp_light_notes.md",
            "docs/pcp-light/tool.py", "scripts/nested/pcp-light-tool.py",
            "tests/nested/test_pcp_light_tool.py",
        ):
            with self.subTest(path=path):
                self.assertFalse(M.allowed_path(path))
        for path in (
            "scripts/pcp-light-tool.py", "tests/test_pcp_light_tool.py",
            "docs/pcp-light/guide.md", "docs/pcp-light/nested/guide.md",
        ):
            with self.subTest(path=path):
                self.assertTrue(M.allowed_path(path))
        doc, digest = issue({**GOOD_TASK, "allowed_paths": [
            "scripts/pcp-light-run.py", "tests/test_pcp_light_run.py",
            "docs/pcp-light/nested/guide.md",
        ]})
        self.assertEqual(
            M.parse_issue(doc, 593, digest)["allowed_paths"],
            ["scripts/pcp-light-run.py", "tests/test_pcp_light_run.py",
             "docs/pcp-light/nested/guide.md"],
        )
        for key in ("g1-retry", "f2-replay", "chonhac-ticket", "g0-recovery"):
            doc, digest = issue({**GOOD_TASK, "key": key})
            with self.assertRaisesRegex(M.Stop, "handoff_field_invalid"):
                M.parse_issue(doc, 593, digest)
        doc, digest = issue({
            **GOOD_TASK, "allowed_paths": ["scripts/pcp-light-run.py"],
        })
        with self.assertRaisesRegex(M.Stop, "handoff_allowed_files_invalid"):
            M.parse_issue(doc, 593, digest)

    def test_mixed_extensions_and_markdown_pseudo_test_fail_issue_admission(self):
        for paths in (
            ["scripts/pcp-light-run.py", "tests/test_pcp_light_fake.md"],
            ["scripts/pcp-light-notes.md", "tests/test_pcp_light_run.py"],
            ["docs/pcp-light/tool.py", "tests/test_pcp_light_run.py"],
            ["scripts/pcp-light-run.py", "docs/pcp-light/nested/guide.md"],
            ["scripts/pcp-light-run.py", "scripts/pcp-light-run.py"],
            ["scripts/pcp-light-run.py", "tests/test_pcp_light_../escape.py"],
        ):
            doc, digest = issue({**GOOD_TASK, "allowed_paths": paths})
            with self.subTest(paths=paths), self.assertRaisesRegex(
                    M.Stop, "handoff_allowed_files_invalid"):
                M.parse_issue(doc, 593, digest)

    def test_invalid_issue_stops_before_claim_worktree_or_codex_call(self):
        task = {**GOOD_TASK, "allowed_paths": [
            "scripts/pcp-light-run.py", "tests/test_pcp_light_fake.md",
        ]}
        doc, digest = issue(task)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "jobs"
            with patch.object(M, "ROOT", root), patch.object(
                M, "load_issue", side_effect=lambda _issue, _digest:
                M.parse_issue(doc, 593, digest)
            ), patch.object(M, "command") as commands, patch.object(
                M, "codex_turn"
            ) as model:
                with self.assertRaisesRegex(M.Stop, "handoff_allowed_files_invalid"):
                    M.run_task(Path(tmp), 593, digest, execute=True)
                commands.assert_not_called()
                model.assert_not_called()
            self.assertFalse(root.exists())

    def test_handoff_requires_supported_model_and_effort(self):
        for model in ("", "codex --danger", "gpt-6;rm -rf", "../../../cmd"):
            doc, digest = issue({**GOOD_TASK, "model": model})
            with self.subTest(model=model), self.assertRaises(M.Stop):
                M.parse_issue(doc, 593, digest)
        doc, digest = issue({**GOOD_TASK, "reasoning": "unbounded"})
        with self.assertRaisesRegex(M.Stop, "handoff_field_invalid"):
            M.parse_issue(doc, 593, digest)

    def test_pytest_argv_is_exactly_one_changed_allowlisted_test(self):
        self.assertEqual(M.pytest_argv(["tests/test_pcp_light_run.py"]), [
            "python3", "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "tests/test_pcp_light_run.py",
        ])

    def test_pytest_argv_sorts_multiple_changed_allowlisted_tests(self):
        self.assertEqual(M.pytest_argv([
            "tests/test_pcp_light_zeta.py", "tests/test_pcp_light_alpha.py",
        ]), [
            "python3", "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "tests/test_pcp_light_alpha.py", "tests/test_pcp_light_zeta.py",
        ])

    def test_pytest_argv_refuses_empty_or_nonallowlisted_selection(self):
        for paths in ([], ["tests"], ["tests/test_other.py"],
                      ["tests/test_pcp_light_notes.md"],
                      ["tests/test_pcp_light_run.py", "tests/test_pcp_light_run.py"]):
            with self.subTest(paths=paths), self.assertRaisesRegex(
                    M.Stop, "pcp_light_changed_tests_missing_or_invalid"):
                M.pytest_argv(paths)

    def test_generated_python_ast_does_not_execute_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for relative in GOOD_TASK["allowed_paths"]:
                file = base / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(
                    "raise RuntimeError('WOULD_RUN_IF_IMPORTED')\n"
                    "def safe(): return 42\n",
                    encoding="utf-8",
                )
            self.assertEqual(
                M.check_generated_sources(base, set(GOOD_TASK["allowed_paths"])),
                sorted(GOOD_TASK["allowed_paths"]),
            )
            test = base / "tests/test_pcp_light_run.py"
            test.write_text("def syntax_error(\n", encoding="utf-8")
            with self.assertRaisesRegex(
                M.Stop, "pcp_light_generated_python_syntax_invalid"
            ):
                M.check_generated_sources(base, set(GOOD_TASK["allowed_paths"]))

    def test_generated_source_guards_symlink_missing_oversized_and_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for relative in GOOD_TASK["allowed_paths"]:
                file = base / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("pass\n", encoding="utf-8")
            test = base / "tests/test_pcp_light_run.py"
            test.unlink()
            with self.assertRaisesRegex(M.Stop, "source_not_regular"):
                M.check_generated_sources(base, set(GOOD_TASK["allowed_paths"]))
            test.symlink_to(base / "scripts/pcp-light-run.py")
            with self.assertRaisesRegex(M.Stop, "source_not_regular"):
                M.check_generated_sources(base, set(GOOD_TASK["allowed_paths"]))
            test.unlink()
            test.write_text("x" * 262145, encoding="utf-8")
            with self.assertRaisesRegex(M.Stop, "source_not_regular"):
                M.check_generated_sources(base, set(GOOD_TASK["allowed_paths"]))
            with self.assertRaisesRegex(M.Stop, "pcp_light_source_scope_invalid"):
                M.check_generated_sources(base, {".github/workflows/tests.yml"})

    def test_ci_first_gate_keeps_untrusted_tests_off_owner_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for relative in GOOD_TASK["allowed_paths"]:
                file = base / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("pass\n", encoding="utf-8")
            sources = M.check_generated_sources(base, set(GOOD_TASK["allowed_paths"]))
            self.assertEqual(set(sources), set(GOOD_TASK["allowed_paths"]))
            self.assertEqual(M.pytest_argv(["tests/test_pcp_light_run.py"])[-1],
                             "tests/test_pcp_light_run.py")

    def test_missing_native_codex_fails_before_claim_without_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "jobs"
            with patch.object(M, "ROOT", root), patch.object(
                M, "load_issue", return_value=GOOD_TASK
            ), patch.object(M, "verify_checkout"), patch.object(
                M, "command", side_effect=M.Stop("command_unavailable_or_timeout_codex")
            ) as preflight, patch.object(M, "codex_turn") as model:
                with self.assertRaisesRegex(
                    M.Stop, "command_unavailable_or_timeout_codex"
                ):
                    M.run_task(Path(tmp), 593, "a" * 64, execute=True)
                model.assert_not_called()
                preflight.assert_called_once_with(["codex", "--version"], timeout=15)
            self.assertFalse(root.exists())

    def test_missing_or_expired_auth_stops_before_any_claim_or_model(self):
        for returncode in (1, 2):
            with self.subTest(returncode=returncode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "jobs"
                observed = []

                def fake_command(argv, **kwargs):
                    observed.append((argv, kwargs))
                    if argv == ["codex", "login", "status"]:
                        raise M.Stop("command_failed_codex_" + str(returncode))
                    return "codex 1.2.3"

                with patch.object(M, "ROOT", root), patch.object(
                    M, "load_issue", return_value=GOOD_TASK
                ), patch.object(M, "verify_checkout"), patch.object(
                    M, "command", side_effect=fake_command
                ), patch.object(M, "codex_turn") as model:
                    with self.assertRaisesRegex(M.Stop, "command_failed_codex"):
                        M.run_task(Path(tmp), 593, "a" * 64, execute=True)
                model.assert_not_called()
                self.assertFalse(root.exists())
                self.assertEqual([call[0] for call in observed], [
                    ["codex", "--version"], ["codex", "login", "status"],
                ])
                auth_env = observed[1][1]["env"]
                self.assertEqual(auth_env, M.codex_auth_env())
                for secret in ("GH_TOKEN", "GITHUB_TOKEN", "OPENAI_API_KEY",
                               "PLATFORM_INTERNAL_TOKEN"):
                    self.assertNotIn(secret, auth_env)

    def test_auth_preflight_uses_same_sanitized_environment_as_turn(self):
        with patch.dict(M.os.environ, {
            "HOME": "/tmp/pcp-auth-home", "CODEX_HOME": "/tmp/pcp-auth-home/.codex",
            "GH_TOKEN": "DO_NOT_FORWARD", "OPENAI_API_KEY": "DO_NOT_FORWARD",
            "PLATFORM_INTERNAL_TOKEN": "DO_NOT_FORWARD",
        }, clear=True):
            env = M.codex_auth_env()
            self.assertEqual(env["HOME"], "/tmp/pcp-auth-home")
            self.assertEqual(env["CODEX_HOME"], "/tmp/pcp-auth-home/.codex")
            self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
            self.assertNotIn("GH_TOKEN", env)
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn("PLATFORM_INTERNAL_TOKEN", env)

    def test_first_use_creates_each_parent_private_not_0755(self):
        with tempfile.TemporaryDirectory() as temp:
            jobs = Path(temp) / ".pcp-light" / "jobs"
            with patch.object(M, "ROOT", jobs):
                M.ensure_private_job_root()
            self.assertEqual(stat.S_IMODE(jobs.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(jobs.stat().st_mode), 0o700)
            self.assertEqual(jobs.parent.stat().st_uid, os.geteuid())
            self.assertEqual(jobs.stat().st_uid, os.geteuid())

    def test_owned_0755_parent_narrows_without_touching_existing_jobs(self):
        with tempfile.TemporaryDirectory() as temp:
            jobs = Path(temp) / ".pcp-light" / "jobs"
            jobs.mkdir(parents=True, mode=0o700)
            parent = jobs.parent
            parent.chmod(0o755)
            historical = jobs / "historic-725"
            historical.mkdir(mode=0o700)
            journal = historical / "journal.json"
            journal.write_text("UNCHANGED-ORIGINAL-JOURNAL", encoding="utf-8")
            before = journal.read_bytes()
            before_mode = stat.S_IMODE(historical.stat().st_mode)
            with patch.object(M, "ROOT", jobs):
                M.ensure_private_job_root()
            self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(jobs.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(historical.stat().st_mode), before_mode)
            self.assertEqual(journal.read_bytes(), before)

    def test_unexpected_permissions_or_symlink_stop_without_chmod(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            jobs = root / ".pcp-light" / "jobs"
            jobs.mkdir(parents=True, mode=0o700)
            parent = jobs.parent
            parent.chmod(0o750)
            with patch.object(M, "ROOT", jobs):
                with self.assertRaisesRegex(M.Stop, "parent_unsafe_mode"):
                    M.ensure_private_job_root()
            self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o750)
            parent.chmod(0o700)
            redirect = root / "linked-parent"
            redirect.symlink_to(parent, target_is_directory=True)
            with patch.object(M, "ROOT", redirect / "jobs"):
                with self.assertRaisesRegex(M.Stop, "root_symlink_denied"):
                    M.ensure_private_job_root()
            self.assertTrue(redirect.is_symlink())

    def test_foreign_owned_parent_refused_no_chmod(self):
        with tempfile.TemporaryDirectory() as temp:
            jobs = Path(temp) / ".pcp-light" / "jobs"
            jobs.mkdir(parents=True, mode=0o700)
            parent = jobs.parent
            parent.chmod(0o755)
            with patch.object(M, "ROOT", jobs), patch.object(
                M.os, "geteuid", return_value=os.geteuid() + 10000
            ):
                with self.assertRaisesRegex(M.Stop, "parent_not_owned"):
                    M.ensure_private_job_root()
            self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o755)

    def test_default_inspect_is_readonly_and_no_agent(self):
        with patch.object(M, "load_issue", return_value=GOOD_TASK), patch.object(
            M, "verify_checkout"
        ) as checkout, patch.object(M, "codex_turn") as agent, patch.object(
            M, "command"
        ) as run, patch.object(M, "ROOT") as root:
            response = M.run_task(Path("/some/pcp"), 593, "a" * 64)
        self.assertEqual(response["status"], "PCP_LIGHT_HANDOFF_VERIFIED_NO_MODEL")
        self.assertEqual(response["model_calls"], 0)
        self.assertIn("context_footprint", response)
        self.assertEqual(response["context_footprint"]["required_authority_files_expected"], 7)
        checkout.assert_called_once()
        agent.assert_not_called()
        run.assert_not_called()
        self.assertEqual(root.mkdir.call_count, 0)

    def test_checkout_identity_and_dirty_worktree_denied(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            def git_ok(_, *args):
                return {
                    ("rev-parse", "--show-toplevel"): str(repo),
                    ("branch", "--show-current"): "main",
                    ("rev-parse", "HEAD"): SOURCE,
                    ("status", "--porcelain"): "",
                    ("remote", "get-url", "origin"):
                        "git@github.com:sonvhse06072/personal-coding-platform.git",
                }.get(args, "unknown")
            with patch.object(M, "git", side_effect=git_ok):
                M.verify_checkout(repo, SOURCE)
            def git_bad(_, *args):
                if args == ("status", "--porcelain"):
                    return " M dangerous.py"
                return git_ok(_, *args)
            with patch.object(M, "git", side_effect=git_bad):
                with self.assertRaisesRegex(M.Stop, "pcp_light_main_sha_or_dirty"):
                    M.verify_checkout(repo, SOURCE)

    def test_token_evidence_uncached_and_cached_ratio_matches_actual_turn(self):
        # Owner's accepted #729 telemetry: reporting only, not billed cash.
        event = json.dumps({
            "type": "turn.completed",
            "usage": {"input_tokens": 628952,
                      "cached_input_tokens": 534016,
                      "output_tokens": 4029},
        })
        result = M.summarize_codex(event)
        self.assertEqual(result["uncached_input_tokens"], 94936)
        self.assertEqual(result["cached_input_share_percent"], 84.9)
        self.assertEqual(result["input_tokens"], 628952)
        self.assertEqual(result["output_tokens"], 4029)
        self.assertNotIn("price_usd", result)

    def test_missing_or_inconsistent_usage_is_unknown_not_zero(self):
        for usage in (
            {"input_tokens": 2, "cached_input_tokens": 3},
            {"input_tokens": 5, "cached_input_tokens": -1},
            {"input_tokens": 5},
            {"input_tokens": False, "cached_input_tokens": 0},
            ["not", "a", "usage", "dict"],
        ):
            with self.subTest(usage=usage):
                result = M.summarize_codex(json.dumps({
                    "type": "turn.completed", "usage": usage,
                }))
                self.assertIsNone(result["uncached_input_tokens"])
                self.assertIsNone(result["cached_input_share_percent"])

    def test_static_context_footprint_counts_bytes_without_following_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            for relative, data in (
                ("AGENTS.md", b"a" * 11),
                ("README.md", b"b" * 13),
                ("docs/project/constitution.md", b"c" * 17),
                ("scripts/pcp-light-run.py", b"x" * 19),
                ("tests/test_pcp_light_run.py", b"y" * 23),
            ):
                p = repo / relative
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            # A linked authority path must not be followed for context sizes.
            (repo / "docs/project/architecture.md").symlink_to(repo / "README.md")
            result = M.context_footprint(repo, GOOD_TASK)
            self.assertEqual(result["required_authority_files_present"], 3)
            self.assertEqual(result["required_authority_files_expected"], 7)
            self.assertEqual(result["required_authority_bytes"], 11 + 13 + 17)
            self.assertEqual(result["allowlisted_existing_files"], 2)
            self.assertEqual(result["allowlisted_existing_source_bytes"], 19 + 23)
            self.assertEqual(result["prompt_utf8_bytes"],
                             len(M.codex_prompt(GOOD_TASK).encode("utf-8")))

    def test_prompt_never_bypasses_mandatory_agent_reading(self):
        prompt = M.codex_prompt(GOOD_TASK)
        self.assertIn(GOOD_TASK["goal"], prompt)
        self.assertIn("AGENTS.md required reading order", prompt)
        self.assertIn("do not skip these reads", prompt)
        self.assertIn("avoid repeatedly dumping", prompt)
        self.assertIn("preserve required tests", prompt)
        self.assertIn("Do not commit, push", prompt)

    def test_git_quality_one_eof_warning_ast_preserved_and_snapshot_private(self):
        # Disposable git repo only; no Owner code or WSL job access.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "disposable"
            repo.mkdir()
            job = Path(tmp) / "new-job"
            job.mkdir(mode=0o700)
            subprocess.run(["git", "init", "-q", str(repo)],
                           check=True, capture_output=True)
            paths = set(GOOD_TASK["allowed_paths"])
            originals = {}
            for name in sorted(paths):
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                content = (
                    b"def safe():\n    return {'text': 'keep  spaces'}\n\n"
                    if name == "scripts/pcp-light-run.py"
                    else b"def test_safe():\n    assert True\n"
                )
                path.write_bytes(content)
                originals[name] = content
            subprocess.run(["git", "-C", str(repo), "add", "--", *sorted(paths)],
                           check=True, capture_output=True)
            initial = subprocess.run(
                ["git", "-C", str(repo), "diff", "--cached", "--check"],
                check=False, capture_output=True, text=True)
            self.assertEqual(initial.returncode, 2)
            self.assertEqual(len(initial.stdout.splitlines()), 1)
            fixed = M.staged_git_quality_gate(repo, paths, job)
            self.assertEqual(fixed, ["scripts/pcp-light-run.py"])
            changed = repo / "scripts/pcp-light-run.py"
            self.assertEqual(changed.read_bytes(),
                             originals["scripts/pcp-light-run.py"].rstrip(b"\n") + b"\n")
            self.assertEqual((repo / "tests/test_pcp_light_run.py").read_bytes(),
                             originals["tests/test_pcp_light_run.py"])
            snapshot = job / (
                "eof-original-" +
                hashlib.sha256(b"scripts/pcp-light-run.py").hexdigest() +
                ".snapshot"
            )
            self.assertEqual(snapshot.read_bytes(),
                             originals["scripts/pcp-light-run.py"])
            self.assertEqual(stat.S_IMODE(snapshot.stat().st_mode), 0o600)
            after = subprocess.run(
                ["git", "-C", str(repo), "diff", "--cached", "--check"],
                check=False, capture_output=True, text=True)
            self.assertEqual(after.returncode, 0)
            self.assertFalse(after.stdout or after.stderr)

    def test_staged_git_quality_accepts_clean_without_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "disposable"
            repo.mkdir()
            job = Path(tmp) / "job"
            job.mkdir(mode=0o700)
            subprocess.run(["git", "init", "-q", str(repo)],
                           check=True, capture_output=True)
            for name in GOOD_TASK["allowed_paths"]:
                target = repo / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"pass\n")
            subprocess.run(
                ["git", "-C", str(repo), "add", "--",
                 *GOOD_TASK["allowed_paths"]],
                check=True, capture_output=True)
            self.assertEqual(
                M.staged_git_quality_gate(
                    repo, set(GOOD_TASK["allowed_paths"]), job), [])
            self.assertEqual(list(job.iterdir()), [])

    def test_staged_git_quality_rejects_unsafe_warnings_without_repair(self):
        scenarios = (
            ("trailing", b"def f():\n    return 1   \n", b"pass\n"),
            ("two_eofs", b"def f():\n    return 1\n\n", b"pass\n\n"),
            ("syntax", b"def broken(:\n\n", b"pass\n"),
        )
        for name, a, b in scenarios:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                repo = Path(tmp) / "disposable"
                repo.mkdir()
                job = Path(tmp) / "job"
                job.mkdir(mode=0o700)
                subprocess.run(["git", "init", "-q", str(repo)],
                               check=True, capture_output=True)
                first, second = GOOD_TASK["allowed_paths"]
                for relative, content in ((first, a), (second, b)):
                    p = repo / relative
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(content)
                subprocess.run(
                    ["git", "-C", str(repo), "add", "--", first, second],
                    check=True, capture_output=True)
                with self.assertRaises(M.Stop):
                    M.staged_git_quality_gate(repo, {first, second}, job)
                self.assertEqual((repo / first).read_bytes(), a)
                self.assertEqual((repo / second).read_bytes(), b)
                self.assertEqual(list(job.iterdir()), [])

    def test_staged_git_quality_preexisting_snapshot_blocks_without_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "disposable"
            repo.mkdir()
            job = Path(tmp) / "job"
            job.mkdir(mode=0o700)
            subprocess.run(["git", "init", "-q", str(repo)],
                           check=True, capture_output=True)
            names = GOOD_TASK["allowed_paths"]
            for name in names:
                p = repo / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"pass\n\n" if name == names[0] else b"pass\n")
            subprocess.run(["git", "-C", str(repo), "add", "--", *names],
                           check=True, capture_output=True)
            snapshot = job / (
                "eof-original-" +
                hashlib.sha256(names[0].encode()).hexdigest() + ".snapshot"
            )
            snapshot.write_bytes(b"PRESERVE")
            original = (repo / names[0]).read_bytes()
            with self.assertRaises(FileExistsError):
                M.staged_git_quality_gate(repo, set(names), job)
            self.assertEqual((repo / names[0]).read_bytes(), original)
            self.assertEqual(snapshot.read_bytes(), b"PRESERVE")

    def test_draft_pr_evidence_carries_verified_numbers_not_raw_secrets(self):
        task = {
            **GOOD_TASK,
            "goal": "SECRET_GOAL_AND_UNTRUSTED_RAW_TASK_DETAILS",
        }
        report = {
            "terminal": "turn.completed",
            "input_tokens": 628952,
            "cached_input_tokens": 534016,
            "uncached_input_tokens": 94936,
            "output_tokens": 4029,
            "cached_input_share_percent": 84.9,
            "raw_agent_output": "SECRET_AGENT_LOG",
            "environment": {"GITHUB_TOKEN": "SECRET_TOKEN"},
        }
        footprint = {
            "required_authority_bytes": 177448,
            "required_authority_files_present": 7,
            "required_authority_files_expected": 7,
            "allowlisted_existing_source_bytes": 20000,
            "allowlisted_existing_files": 2,
            "prompt_utf8_bytes": 1090,
            "raw_document": "SECRET_CONTEXT_TEXT",
        }
        body = M.draft_pr_evidence_body(
            issue=730, digest="a" * 64, task=task, commit="b" * 40,
            changed=set(GOOD_TASK["allowed_paths"]),
            model_seconds=48.8, model_result=report,
            operator_pre_pr_elapsed_seconds=65.2,
            python_files=list(GOOD_TASK["allowed_paths"]),
            footprint=footprint,
        )
        data = json.loads(body.split(chr(96) * 3 + "json\n", 1)[1]
                          .split("\n" + chr(96) * 3, 1)[0])
        self.assertEqual(data["schema"], "pcp-light-pr-evidence-v1")
        self.assertEqual(data["task"]["issue"], 730)
        self.assertEqual(data["task"]["candidate_sha"], "b" * 40)
        self.assertEqual(data["task"]["base_sha"], SOURCE)
        self.assertEqual(data["coding"]["input_tokens"], 628952)
        self.assertEqual(data["coding"]["cached_input_tokens"], 534016)
        self.assertEqual(data["coding"]["uncached_input_tokens"], 94936)
        self.assertEqual(data["coding"]["cached_input_share_percent"], 84.9)
        self.assertEqual(data["coding"]["model_elapsed_seconds"], 48.8)
        self.assertEqual(data["coding"]["operator_pre_pr_elapsed_seconds"], 65.2)
        self.assertEqual(data["coding"]["provider_cash_cost"], "UNAVAILABLE")
        self.assertEqual(data["verification"]["hosted_full_ci"], "PENDING")
        self.assertEqual(data["verification"]["local_tests_executed"], 0)
        self.assertEqual(data["verification"]["git_staged_quality"], "PASS")
        self.assertEqual(data["verification"]["eof_normalized_paths"], [])
        self.assertEqual(data["verification"]["changed_paths"],
                         sorted(GOOD_TASK["allowed_paths"]))
        self.assertEqual(data["context_metadata"]["required_authority_bytes"], 177448)
        for leaked in (
            "SECRET_GOAL_AND_UNTRUSTED_RAW_TASK_DETAILS",
            "SECRET_AGENT_LOG", "SECRET_TOKEN", "SECRET_CONTEXT_TEXT",
        ):
            self.assertNotIn(leaked, body)
        self.assertIn("mandatory before merge", body)
        self.assertNotIn("pytest passed", body.lower())

    def test_missing_metrics_remain_null_and_do_not_block_draft(self):
        report = M.draft_pr_evidence_body(
            issue=594, digest="f" * 64, task=GOOD_TASK,
            commit="b" * 40, changed=set(GOOD_TASK["allowed_paths"]),
            model_seconds=0.1,
            model_result={"terminal": "turn.completed",
                          "input_tokens": False,
                          "cached_input_tokens": -1,
                          "cached_input_share_percent": float("nan"),
                          "raw_exception": "NEVER_PRINT"},
            python_files=["tests/test_pcp_light_run.py"],
            footprint={},
        )
        obj = json.loads(report.split(chr(96) * 3 + "json\n", 1)[1]
                         .split("\n" + chr(96) * 3, 1)[0])
        self.assertIsNone(obj["coding"]["input_tokens"])
        self.assertIsNone(obj["coding"]["cached_input_tokens"])
        self.assertIsNone(obj["coding"]["uncached_input_tokens"])
        self.assertIsNone(obj["coding"]["cached_input_share_percent"])
        self.assertIsNone(obj["coding"]["operator_pre_pr_elapsed_seconds"])
        self.assertIsNone(obj["context_metadata"]["required_authority_bytes"])
        self.assertNotIn("NEVER_PRINT", report)

    def test_pr_body_refuses_outside_scope_or_unpinned_candidate(self):
        def make(**changes):
            args = {
                "issue": 594, "digest": "f" * 64, "task": GOOD_TASK,
                "commit": "b" * 40,
                "changed": set(GOOD_TASK["allowed_paths"]),
                "model_seconds": 1.0, "model_result": {},
                "python_files": ["tests/test_pcp_light_run.py"],
                "footprint": {},
            }
            args.update(changes)
            return M.draft_pr_evidence_body(**args)
        for changed in (
            {"changed": {".github/workflows/unapproved.yml"}},
            {"changed": set()},
            {"commit": "UNPINNED"},
            {"digest": "not-sha256"},
            {"model_seconds": float("inf")},
            {"operator_pre_pr_elapsed_seconds": -1},
            {"operator_pre_pr_elapsed_seconds": float("nan")},
            {"operator_pre_pr_elapsed_seconds": False},
            {"operator_pre_pr_elapsed_seconds": 0.5},
        ):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(
                    M.Stop, "pcp_light_pr_evidence_not_scoped"
                ):
                    make(**changed)

    def test_model_invocation_uses_explicit_sandbox_and_no_host_tokens(self):
        with patch.object(M, "command", return_value=json.dumps({
            "type": "turn.completed", "usage": {
                "input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 15,
            }
        })) as runner, patch.dict(M.os.environ, {
            "GH_TOKEN": "SECRET_DO_NOT_FORWARD",
            "OPENAI_API_KEY": "SECRET_DO_NOT_FORWARD",
            "PLATFORM_INTERNAL_TOKEN": "SECRET_DO_NOT_FORWARD",
            "HOME": "/tmp/pcp-light-auth"
        }):
            response = M.codex_turn(Path("/tmp/pcp-task"), GOOD_TASK)
        argv = runner.call_args.args[0]
        env = runner.call_args.kwargs["env"]
        self.assertEqual(argv[:2], ["codex", "exec"])
        self.assertIn("workspace-write", argv)
        self.assertIn("sandbox_workspace_write.network_access=false", argv)
        self.assertIn('approval_policy="never"', argv)
        self.assertIn('model_reasoning_effort="medium"', argv)
        self.assertIn("gpt-6-luna", argv)
        self.assertEqual(response["terminal"], "turn.completed")
        self.assertEqual(response["cached_input_tokens"], 20)
        for key in ("GH_TOKEN", "OPENAI_API_KEY", "PLATFORM_INTERNAL_TOKEN"):
            self.assertNotIn(key, env)
        self.assertIn("Do not commit, push", argv[-1])

    def test_one_shot_claim_then_successful_scoped_draft_pr(self):
        with tempfile.TemporaryDirectory() as temp:
            jroot = Path(temp) / "pcp-light" / "jobs"
            jroot.parent.mkdir(mode=0o700)
            jroot.parent.chmod(0o700)
            state = {"committed": False}
            ticket_paths = set(GOOD_TASK["allowed_paths"])
            def fake_cmd(argv, **kwargs):
                if "commit" in argv:
                    state["committed"] = True
                if argv[:3] == ["gh", "pr", "create"]:
                    return f"https://github.com/{M.REPOSITORY}/pull/900"
                return ""
            def fake_git(workspace, *args):
                if args == ("rev-parse", "HEAD"):
                    return "b" * 40 if state["committed"] else SOURCE
                if args == ("rev-parse", "HEAD^"):
                    return SOURCE
                if args == ("branch", "--show-current"):
                    return "ai/pcp-light/simple-bounded-fix"
                if args in (("status", "--porcelain"),):
                    return ""
                if args[:2] == ("diff", "--name-only") and len(args) == 4:
                    return "\n".join(sorted(ticket_paths))
                return ""
            with patch.object(M, "ROOT", jroot), patch.object(
                M, "load_issue", return_value=GOOD_TASK
            ), patch.object(
                M, "verify_checkout"
            ), patch.object(M, "command", side_effect=fake_cmd) as commands, patch.object(
                M, "git", side_effect=fake_git
            ), patch.object(M, "codex_turn", return_value={
                "terminal": "turn.completed", "input_tokens": 20,
                "cached_input_tokens": 4, "output_tokens": 2,
            }) as codex, patch.object(
                M, "changed_paths", return_value=ticket_paths
            ), patch.object(
                M, "check_generated_sources", return_value=sorted(ticket_paths)
            ) as syntax, patch.object(
                M, "staged_git_quality_gate", return_value=[]
            ) as quality:
                result = M.run_task(
                    Path(temp), 593, "a" * 64, execute=True,
                )
                self.assertEqual(result["status"], "PCP_LIGHT_DRAFT_PR_PENDING_CI_PM")
                self.assertEqual(result["model_calls"], 1)
                self.assertGreaterEqual(result["operator_elapsed_seconds"],
                                        result["operator_pre_pr_elapsed_seconds"])
                self.assertGreaterEqual(result["operator_pre_pr_elapsed_seconds"],
                                        result["model_elapsed_seconds"])
                self.assertEqual(result["local_tests_executed"], 0)
                self.assertEqual(result["hosted_full_ci"], "PENDING")
                self.assertEqual(result["syntax_files_checked"], 2)
                self.assertEqual(result["context_footprint"]["required_authority_files_expected"], 7)
                self.assertIn("context_footprint", json.loads(
                    (jroot / GOOD_TASK["key"] / "journal.json").read_text()
                ))
                codex.assert_called_once()
                syntax.assert_called_once_with(
                    jroot / GOOD_TASK["key"] / "workspace", ticket_paths
                )
                quality.assert_called_once_with(
                    jroot / GOOD_TASK["key"] / "workspace",
                    ticket_paths, jroot / GOOD_TASK["key"],
                )
                self.assertEqual(result["git_staged_quality"], "PASS")
                self.assertEqual(result["eof_normalized_paths"], [])
                self.assertEqual(json.loads(
                    (jroot / GOOD_TASK["key"] / "journal.json").read_text()
                )["state"], "draft_pr_created")
                with self.assertRaises(FileExistsError):
                    M.run_task(Path(temp), 593, "a" * 64, execute=True)
                self.assertEqual(codex.call_count, 1)
            calls = [x.args[0] for x in commands.call_args_list]
            self.assertEqual(calls[:2], [
                ["codex", "--version"], ["codex", "login", "status"],
            ])
            self.assertEqual(commands.call_args_list[1].kwargs["timeout"], 15)
            self.assertEqual(commands.call_args_list[1].kwargs["env"],
                             codex.call_args.kwargs["env"])
            gh = [x for x in calls if x[:3] == ["gh", "pr", "create"]]
            self.assertEqual(len(gh), 1)
            body = gh[0][gh[0].index("--body") + 1]
            evidence = json.loads(body.split(chr(96) * 3 + "json\n", 1)[1]
                                  .split("\n" + chr(96) * 3, 1)[0])
            self.assertEqual(evidence["task"]["candidate_sha"], "b" * 40)
            self.assertEqual(evidence["coding"]["model_calls"], 1)
            self.assertEqual(evidence["coding"]["operator_pre_pr_elapsed_seconds"],
                             result["operator_pre_pr_elapsed_seconds"])
            self.assertEqual(evidence["coding"]["input_tokens"], 20)
            self.assertEqual(evidence["coding"]["output_tokens"], 2)
            self.assertEqual(evidence["verification"]["hosted_full_ci"], "PENDING")
            self.assertEqual(evidence["verification"]["local_tests_executed"], 0)
            self.assertTrue(any(x[:2] == ["codex", "--version"] for x in calls))
            self.assertFalse(any(x[:2] == ["python3", "-m"] for x in calls))
            self.assertTrue(any("worktree" in x for x in calls))

    def test_unapproved_diff_stops_before_commit_or_push(self):
        with tempfile.TemporaryDirectory() as temp:
            jroot = Path(temp) / "jobs"
            with patch.object(M, "ROOT", jroot), patch.object(
                M, "load_issue", return_value=GOOD_TASK
            ), patch.object(
                M, "verify_checkout"
            ), patch.object(M, "command", return_value="") as cmds, patch.object(
                M, "git", side_effect=lambda _, *a:
                SOURCE if a == ("rev-parse", "HEAD")
                else "ai/pcp-light/simple-bounded-fix"
                if a == ("branch", "--show-current") else ""
            ), patch.object(M, "codex_turn", return_value={
                "terminal": "turn.completed"
            }), patch.object(M, "changed_paths", return_value={
                ".github/workflows/unsafe.yml"
            }):
                with self.assertRaisesRegex(M.Stop, "diff_outside_scope"):
                    M.run_task(Path(temp), 593, "a" * 64, execute=True)
                record = json.loads((jroot / GOOD_TASK["key"] /
                                     "journal.json").read_text())
                self.assertEqual(record["state"], "model_finished")
                self.assertEqual(record["model_calls"], 1)
                self.assertFalse(any("commit" in x.args[0] or "push" in x.args[0]
                                     for x in cmds.call_args_list))


if __name__ == "__main__":
    unittest.main()
