#!/usr/bin/env python3
"""One-use G1 npm-prefix repair on the ORIGINAL durable job; no MCP or models.

Require the already-recorded 254/ENOENT phase evidence and read-only proof that
ddev exec starts at /var/www/html. Only then replace one scoped private tool
argv with an absolute npm prefix and execute that same bounded Node smoke once.
Never replay original setup, start/stop DDEV, allocate a job or reissue tokens.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

ROOT = Path.home() / ".pcp-g1-smoke"
REPO = Path(__file__).resolve().parents[1]
REPAIR_FILE = ROOT / "node-prefix-repair-evidence.json"
CONFIG = ROOT / "config/projects.yml"
OLD = ["ddev", "exec", "npm", "--prefix", "..", "run", "build"]
NEW = ["ddev", "exec", "npm", "--prefix", "/var/www/html", "run", "build"]
EXPECTED_CWD = "/var/www/html"
COMMIT = "6165d2e69dc1237deb6465962e523d57e8add1f3"


class Stop(RuntimeError):
    """Sanitized, stable blocker name; never emit stdout/stderr/credentials."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise Stop(code)


def prior_operator():
    script = REPO / "scripts/g1-existing-node-continuation.py"
    require(script.is_file() and not script.is_symlink(), "g1_previous_operator_missing")
    spec = importlib.util.spec_from_file_location("g1_previous_original_job", script)
    require(spec is not None and spec.loader is not None,
            "g1_previous_operator_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exact_origin(previous, expected_sha: str) -> tuple[str, Path, str]:
    require(re.fullmatch(r"[0-9a-f]{40}", expected_sha) is not None,
            "g1_expected_sha_invalid")
    require(previous.call(["git", "-C", str(REPO), "rev-parse", "HEAD"])
            == expected_sha and
            previous.call(["git", "-C", str(REPO), "branch", "--show-current"])
            == "main" and
            not previous.call(["git", "-C", str(REPO), "status", "--porcelain"]),
            "g1_pcp_source_not_exact_clean_main")
    require(not REPAIR_FILE.exists() and not REPAIR_FILE.is_symlink(),
            "g1_node_prefix_repair_already_attempted")
    journal_path = ROOT / "smoke-journal.json"
    prior_path = ROOT / "node-continuation-evidence.json"
    require(journal_path.is_file() and not journal_path.is_symlink()
            and prior_path.is_file() and not prior_path.is_symlink(),
            "g1_original_job_evidence_missing")
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        earlier = json.loads(prior_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Stop("g1_original_job_evidence_invalid") from exc
    job = journal.get("job_id")
    require(isinstance(job, str)
            and re.fullmatch(r"[0-9a-f]{32}", job) is not None
            and job.startswith("2c6db0aa6f19")
            and earlier.get("job_id") == job
            and earlier.get("state") == "completed"
            and earlier.get("phase") == "frontend_quality"
            and earlier.get("operator_command_only") is True
            and earlier.get("returncode") == 254
            and earlier.get("error_class") == "PACKAGE_OR_PATH_ERROR"
            and earlier.get("timed_out") is False
            and earlier.get("output_marker") is False
            and earlier.get("model_calls") == 0
            and earlier.get("mcp_replayed") is False
            and journal.get("state") == "workspace_pending"
            and journal.get("project_id") == previous.PROJECT
            and journal.get("source_sha") == previous.SOURCE
            and journal.get("model_calls") == 0,
            "g1_original_job_status_or_failure_drift")
    ws = ROOT / "workspaces" / job
    require(ws.is_dir() and not ws.is_symlink()
            and ws.parent == ROOT / "workspaces"
            and ws.resolve() == ws, "g1_exact_workspace_missing")
    require(
        previous.call(["git", "-C", str(ws), "rev-parse", "--show-toplevel"])
        == str(ws)
        and previous.call(["git", "-C", str(ws), "rev-parse", "HEAD"])
        == previous.SOURCE
        and previous.call(["git", "-C", str(ws), "branch", "--show-current"])
        == "ai/" + job[:12]
        and previous.call(["git", "-C", str(ws), "hash-object",
                           ".ddev/config.yaml"]) == previous.DDEV_BLOB
        and not previous.call(["git", "-C", str(ws), "ls-files",
                               "--others", "--exclude-standard", "--", ".ddev"]),
        "g1_workspace_source_or_ddev_drift")
    previous.attest_g1(ws)
    executor_id = previous.docker_identity(ws)
    return job, ws, executor_id


def read_config(previous, ws: Path) -> dict[str, Any]:
    require(CONFIG.is_file() and not CONFIG.is_symlink()
            and CONFIG.stat().st_uid == os.geteuid(),
            "g1_private_project_config_missing")
    try:
        contents = json.loads(CONFIG.read_text(encoding="utf-8"))
        require(set(contents) == {"version", "projects"} and
                contents["version"] == 1 and
                set(contents["projects"]) == {previous.PROJECT},
                "g1_project_registry_not_singleton")
        project = contents["projects"][previous.PROJECT]
        tools = project["trusted_codex_tools"]
        assert (tools["frontend_quality"] == [OLD]
                and set(tools) == {"targeted_tests", "static_analysis",
                                   "frontend_quality"})
        assert (project["path"] == str(ROOT / "source")
                and project["runtime"]["developer_permission_mode"] == "trusted_project"
                and project["runtime"]["workspace_mode"] == "isolated_clone"
                and project["runtime"]["exclusive_project_lease"] is False
                and project["autonomy"]["allow_auto_merge_low_risk"] is False
                and project["autonomy"]["allow_production_deploy"] is False
                and project["ddev"]["enabled"] is True)
        return contents
    except (KeyError, TypeError, ValueError, AssertionError, OSError) as exc:
        raise Stop("g1_trusted_phase_registry_drift") from exc


def executor_args(previous, executor_id: str, ws: Path, cmd: list[str]) -> list[str]:
    # No arbitrary shell/provider; env -i discards all Docker Executor secrets.
    args = previous.npm_argv(executor_id, ws)
    require(args[-7:] == OLD and cmd in (OLD, NEW),
            "g1_node_command_contract_changed")
    return args[:-7] + cmd


def observe_ddev_cwd(previous, executor_id: str, ws: Path) -> str:
    argv = executor_args(previous, executor_id, ws, OLD)[:-7] + [
        "ddev", "exec", "pwd",
    ]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, check=False,
            timeout=25, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("g1_readonly_ddev_cwd_probe_unavailable") from exc
    require(proc.returncode == 0,
            "g1_readonly_ddev_cwd_probe_failed")
    lines = [x.strip() for x in proc.stdout.splitlines() if x.strip()]
    require(bool(lines) and lines[-1].startswith("/"),
            "g1_ddev_cwd_not_identified")
    return lines[-1]


def exclusive_record(data: dict[str, Any]) -> None:
    os.umask(0o077)
    with REPAIR_FILE.open("x", encoding="utf-8") as file:
        json.dump(data, file, sort_keys=True)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())


def replace_record(data: dict[str, Any]) -> None:
    temp = ROOT / "node-prefix-repair-evidence.tmp"
    os.umask(0o077)
    with temp.open("x", encoding="utf-8") as file:
        json.dump(data, file, sort_keys=True)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    os.replace(temp, REPAIR_FILE)


def update_config(contents: dict[str, Any], project_id: str) -> None:
    # Exactly one local G1 singleton tool-argv correction; never source Git,
    # another project, Docker config, job/lease/DB, or shared credentials.
    contents["projects"][project_id]["trusted_codex_tools"][
        "frontend_quality"] = [NEW]
    temp = ROOT / "config/projects.g1-prefix-candidate.tmp"
    os.umask(0o077)
    with temp.open("x", encoding="utf-8") as f:
        json.dump(contents, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, CONFIG)


def one_node_attempt(previous, executor_id: str, ws: Path) -> dict[str, Any]:
    argv = executor_args(previous, executor_id, ws, NEW)
    return previous.run_bounded(argv)


def execute(expected_sha: str) -> dict[str, Any]:
    require(expected_sha == COMMIT, "g1_source_sha_not_reviewed")
    previous = prior_operator()
    job, ws, executor_id = exact_origin(previous, expected_sha)
    config = read_config(previous, ws)
    cwd = observe_ddev_cwd(previous, executor_id, ws)
    require(cwd == EXPECTED_CWD,
            "g1_cwd_not_expected_root_config_unchanged")
    exclusive_record({
        "state": "started", "job_id": job, "cwd": "PROJECT_ROOT",
        "model_calls": 0, "mcp_replayed": False, "config_changed": False,
    })
    update_config(config, previous.PROJECT)
    began = time.monotonic()
    result = one_node_attempt(previous, executor_id, ws)
    success = (
        result["returncode"] == 0
        and result["output_marker"] is True
        and result["timed_out"] is False
    )
    payload = {
        "state": "complete", "job_id": job,
        "cwd": "PROJECT_ROOT",
        "old_npm_prefix": "..",
        "corrected_npm_prefix": "/var/www/html",
        "config_changed": True,
        "model_calls": 0, "mcp_replayed": False,
        "ready_for_autonomous_e2e": False,
        **result,
    }
    replace_record(payload)
    return {
        "status": ("PASS_G1_CORRECTED_NODE_OPERATOR_NOT_MCP"
                   if success else "STOP_G1_CORRECTED_NODE_OPERATOR"),
        "job_prefix": job[:12], "cwd": "PROJECT_ROOT",
        "config_changed": True, "original_phase_exit_code": "NOT_PROVEN",
        "mcp_replayed": False, "model_calls": 0,
        "ready_for_autonomous_e2e": False,
        **result,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-pcp-sha", required=True)
    args = p.parse_args()
    try:
        result = execute(args.expected_pcp_sha)
        code = 0 if result["status"].startswith("PASS_") else 2
    except (Stop, OSError, FileExistsError, PermissionError) as exc:
        result = {
            "status": "STOP",
            "blocker": str(exc) if isinstance(exc, Stop)
                       else "g1_private_evidence_write_unavailable",
            "model_calls": 0, "mcp_replayed": False,
            "ready_for_autonomous_e2e": False,
            "no_automatic_retry": True,
        }
        code = 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
