"""Focused source-only contract tests for the one-use G1-T01 PCP pilot.

No Docker, Codex, network, DDEV, GitHub API, persistent job or credentials.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g1-pcp-t01-one-shot.py"
DIRECT = ROOT / "scripts/g1-pilot-direct-first-turn.py"
OVERLAY = ROOT / "deploy/g1/compose.pilot.t01-operator.yml"
DOCKERFILE = ROOT / "deploy/g1/Dockerfile.pilot-runtime"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class PilotOneShotContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pilot = load("g1_pcp_once", SCRIPT)
        cls.direct = load("g1_direct_spec", DIRECT)

    def test_python_syntax_and_single_main_entry(self) -> None:
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        self.assertEqual(
            sum(isinstance(node, ast.FunctionDef) and node.name == "main"
                for node in tree.body), 1)
        self.assertIn("no_automatic_retry", SCRIPT.read_text())

    def test_same_task_criteria_as_direct_without_solution(self) -> None:
        self.assertEqual(self.pilot.TASK, self.direct.TASK)
        self.assertEqual(self.pilot.SEED, self.direct.SEED)
        self.assertEqual(self.pilot.ALLOWED, self.direct.ALLOW)
        self.assertNotIn(self.direct.BRANCH, self.pilot.TASK)
        self.assertNotIn("78f2beeb4604659b95893bfd8f1e019a9b4e094e",
                         SCRIPT.read_text())

    def test_new_pcp_not_smoke_direct_f2_or_chonhac(self) -> None:
        self.assertEqual(self.pilot.PROJECT, "pcp-benchmark-g1-pilot")
        self.assertEqual(self.pilot.ROOT.name, "pcp-t01")
        self.assertEqual(self.pilot.PRIVATE_NETWORK,
                         "pcp-g1-codex-pilot-private")
        body = SCRIPT.read_text()
        for forbidden in (
            "docker compose down", "docker volume rm", "git reset --hard",
            "git clean -fd", "docker system prune",
            "/opt/chonhac", "/home/sonvh/chonhac",
        ):
            self.assertNotIn(forbidden, body)
        self.assertNotIn("ai/g1-direct-t01-20261015", body)
        self.assertNotIn("2c6db0aa6f19", body)
        self.assertNotIn("88b9e0d85001", body)

    def test_source_isolation_fetches_only_one_seed_branch(self) -> None:
        env = {"GIT_TERMINAL_PROMPT": "0"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "pilot"
            with patch.object(self.pilot, "ROOT", root), patch.object(
                    self.pilot, "private") as output, patch.object(
                        self.pilot, "run") as execute, patch.object(
                            self.pilot, "git") as git:
                git.side_effect = (
                    lambda _, __, *args:
                    self.pilot.SEED if args[-2:] == ("rev-parse", "HEAD")
                    else self.pilot.BRANCH if args[-2:] == (
                        "branch", "--show-current")
                    else "refs/remotes/origin/" + self.pilot.BRANCH
                    if args[0] == "for-each-ref" else ""
                )
                self.pilot.bootstrap(env)
                arguments = execute.call_args_list[0].args[0]
                self.assertEqual(arguments[0:2], ["git", "clone"])
                self.assertIn("--single-branch", arguments)
                self.assertIn("--depth", arguments)
                self.assertIn(self.pilot.BRANCH, arguments)
                self.assertNotIn("ai/g1-direct-t01-20261015",
                                 " ".join(arguments))
                self.assertGreaterEqual(output.call_count, 5)

    def test_unexpected_changed_file_refuses_commit(self) -> None:
        def fake_git(_, __, *args):
            if args[0:2] == ("diff", "--name-only"):
                return "scripts/unsanctioned.py"
            return self.pilot.SEED
        with patch.object(self.pilot, "git", side_effect=fake_git), \
                patch.object(self.pilot, "run") as runner:
            with self.assertRaisesRegex(self.pilot.Stop,
                                        "g1_pcp_code_or_tests_missing_or_out_of_scope"):
                self.pilot.verify_commit({}, Path("/example"))
            runner.assert_not_called()

    def test_existing_journal_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(self.pilot, "ROOT", root), patch.object(
                    self.pilot, "JOURNAL", root / "job-evidence.json"):
                self.pilot.journal("started", model_calls=0)
                with self.assertRaises(FileExistsError):
                    self.pilot.journal("started", model_calls=0)
                data = (root / "job-evidence.json").read_text()
                self.assertIn('"state": "started"', data)

    def test_overlay_keeps_direct_off_and_broker_job_pinned(self) -> None:
        text = OVERLAY.read_text(encoding="utf-8")
        self.assertIn("g1-pilot-control:", text)
        self.assertIn("aliases: [pcp-dev-executor]", text)
        self.assertIn("http://pcp-dev-executor:8790", text)
        self.assertIn("PCP_TRUSTED_CODEX_JOB_ID", text)
        self.assertIn("PCP_TRUSTED_CODEX_DEV_TOKEN", text)
        self.assertIn("direct-service-started: false", text)
        self.assertNotIn("\n  direct:\n", text)
        self.assertIn("wait_for", text)
        self.assertIn("timeout=1800", text)

    def test_only_private_postgres_gets_bootstrap_permissions(self) -> None:
        doc = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
        services = doc["services"]
        self.assertFalse(services["db"]["read_only"])
        self.assertIn("CHOWN", services["db"]["cap_add"])
        self.assertIn("SETUID", services["db"]["cap_add"])
        self.assertIn("pg_isready", str(services["db"]["healthcheck"]))
        self.assertIn("8090/health", str(services["router"]["healthcheck"]))
        self.assertIn("8790/health", str(services["executor"]["healthcheck"]))
        for name in ("router", "executor", "runtime"):
            self.assertNotIn("read_only", services[name])
            self.assertNotIn("privileged", services[name])
        self.assertNotIn("direct", services)

    def test_runtime_image_excludes_legacy_opencode(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("@openai/codex@", text)
        self.assertNotIn("opencode-ai", text)
        self.assertIn("pcp-t01-runtime-only", text)
        self.assertIn("COPY services/runtime/app /app/app", text)


if __name__ == "__main__":
    unittest.main()
