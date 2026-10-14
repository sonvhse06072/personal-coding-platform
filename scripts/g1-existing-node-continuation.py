#!/usr/bin/env python3
"""Exactly one operator-authorized G1 Executor Node check on the EXISTING job.

This is a bounded, same-command diagnostic (not an MCP replay). It never
uses/renews the expired developer bearer or dispatches a Codex model. It never
starts/stops Docker/DDEV, allocates jobs, or reads unrelated project sources.
On any ambiguity STOP with sanitized evidence; never auto-retry or cleanup.
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

REPO = Path(__file__).resolve().parents[1]
ROOT = Path.home() / ".pcp-g1-smoke"
SOURCE = "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
DDEV_BLOB = "7a3e97a2a35fc8e67b67021365e7e91c448b52c9"
PROJECT = "pcp-benchmark-g1-smoke"
PFX = "2c6db0aa6f19"
OUTPUT = "G1_NODE_BUILD_CHECK=PASS"
EVIDENCE = ROOT / "node-continuation-evidence.json"
CONTROL = "pcp-g1-smoke-control"
DOCKER_RUN_TIME = 165


class Stop(RuntimeError):
    """Non-secret, stable reason code only."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Stop(reason)


def call(args: list[str], *, timeout: int = 15) -> str:
    try:
        result = subprocess.run(
            args, stdin=subprocess.DEVNULL, text=True,
            capture_output=True, timeout=timeout, check=False,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("g1_readonly_probe_unavailable") from exc
    if result.returncode != 0:
        raise Stop("g1_readonly_probe_failed")
    return result.stdout.strip()


def inspect(name: str) -> dict[str, Any]:
    raw = call(["docker", "container", "inspect", name])
    try:
        obj = json.loads(raw)
        if isinstance(obj, list) and len(obj) == 1 and isinstance(obj[0], dict):
            return obj[0]
    except (ValueError, TypeError):
        pass
    raise Stop("g1_executor_inspect_invalid")


def docker_identity(workspace: Path) -> str:
    # Constrain the operator's Docker CLI to the reviewed local socket. Never
    # allow a remote/alternate daemon merely because it also has G1 labels.
    try:
        contexts = json.loads(call(["docker", "context", "inspect"]))
        host = contexts[0]["Endpoints"]["docker"]["Host"]
        require(isinstance(contexts, list) and len(contexts) == 1
                and host == "unix:///var/run/docker.sock"
                and not os.getenv("DOCKER_HOST", "").strip(),
                "g1_docker_context_changed")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise Stop("g1_docker_context_unverifiable") from exc
    raw = call([
        "docker", "container", "ls", "--all",
        "--filter", "label=com.docker.compose.project=pcp-g1-smoke",
        "--filter", "label=com.docker.compose.service=pcp-dev-executor",
        "--format", "{{.ID}}",
    ])
    ids = raw.splitlines()
    require(len(ids) == 1 and re.fullmatch(r"[0-9a-f]{12,64}", ids[0]) is not None,
            "g1_executor_not_singleton")
    doc = inspect(ids[0])
    labels = (doc.get("Config") or {}).get("Labels") or {}
    require(
        labels.get("com.docker.compose.project") == "pcp-g1-smoke"
        and labels.get("com.docker.compose.service") == "pcp-dev-executor"
        and labels.get("pcp.scope") == "g1-disposable-no-model"
        and (doc.get("State") or {}).get("Running") is True
        and (doc.get("HostConfig") or {}).get("Privileged") is False
        and set((doc.get("NetworkSettings") or {}).get("Networks") or {}) == {CONTROL},
        "g1_executor_identity_drift",
    )
    mounts = doc.get("Mounts") or []
    approved = {
        str(workspace.parent): True,
        str(ROOT / "source"): False,
        str(ROOT / "xdg"): True,
        str(ROOT / "config/projects.yml"): False,
    }
    for source, writable in approved.items():
        matches = [m for m in mounts if m.get("Source") == source]
        require(
            len(matches) == 1
            and matches[0].get("RW") is writable
            and matches[0].get("Destination") in {
                source, "/g1/config/projects.yml",
            },
            "g1_executor_mount_drift",
        )
    return ids[0]


def attest_g1(workspace: Path) -> None:
    file = REPO / "services/ddev-executor/app/g1_ddev_isolation.py"
    require(file.is_file() and not file.is_symlink(),
            "g1_isolation_proof_source_missing")
    spec = importlib.util.spec_from_file_location("g1_existing_job_isolation", file)
    require(spec is not None and spec.loader is not None,
            "g1_isolation_proof_import_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.require_g1_isolated_ddev(workspace)
    except module.G1IsolationStop as exc:
        raise Stop(str(exc)) from None


def workspace_identity(pcp_sha: str) -> tuple[str, Path]:
    require(re.fullmatch(r"[0-9a-f]{40}", pcp_sha) is not None,
            "g1_expected_pcp_sha_invalid")
    require(os.geteuid() != 0, "g1_unprivileged_operator_required")
    require(call(["git", "-C", str(REPO), "rev-parse", "HEAD"]) == pcp_sha
            and call(["git", "-C", str(REPO), "branch", "--show-current"]) == "main"
            and not call(["git", "-C", str(REPO), "status", "--porcelain"]),
            "g1_pcp_checkout_not_exact_clean_main")
    require(ROOT.is_dir() and not ROOT.is_symlink()
            and ROOT.stat().st_uid == os.geteuid(),
            "g1_disposable_root_not_owned")
    require(not EVIDENCE.exists() and not EVIDENCE.is_symlink(),
            "g1_node_continuation_already_attempted")
    path = ROOT / "smoke-journal.json"
    require(path.is_file() and not path.is_symlink(),
            "g1_durable_journal_missing")
    try:
        journal = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise Stop("g1_durable_journal_invalid") from exc
    job = journal.get("job_id")
    require(
        isinstance(job, str) and re.fullmatch(r"[0-9a-f]{32}", job) is not None
        and job.startswith(PFX)
        and journal.get("project_id") == PROJECT
        and journal.get("source_sha") == SOURCE
        and journal.get("state") == "workspace_pending"
        and journal.get("model_calls") == 0,
        "g1_durable_job_identity_drift",
    )
    ws = ROOT / "workspaces" / job
    require(ws.is_dir() and not ws.is_symlink()
            and ws.resolve() == ws and ws.parent == ROOT / "workspaces",
            "g1_exact_workspace_missing")
    require(
        call(["git", "-C", str(ws), "rev-parse", "--show-toplevel"]) == str(ws)
        and call(["git", "-C", str(ws), "rev-parse", "HEAD"]) == SOURCE
        and call(["git", "-C", str(ws), "branch", "--show-current"])
        == "ai/" + job[:12]
        and call(["git", "-C", str(ws), "hash-object", ".ddev/config.yaml"])
        == DDEV_BLOB
        and not call(["git", "-C", str(ws), "ls-files", "--others",
                      "--exclude-standard", "--", ".ddev"]),
        "g1_workspace_source_or_ddev_drift",
    )
    attest_g1(ws)
    return job, ws


def npm_argv(container_id: str, ws: Path) -> list[str]:
    # Reproduce exact previously-approved argv, with the SAME scoped Executor
    # Docker identity. env -i prevents forwarding the Executor's secrets to
    # DDEV/Node. No shell, pipes, fallback or arbitrary command selection.
    return [
        "docker", "exec", "--workdir", str(ws), container_id,
        "env", "-i",
        "HOME=/home/coder",
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "DDEV_NO_TUI=true",
        "DDEV_XDG_CONFIG_HOME=" + str(ROOT / "xdg"),
        "GIT_TERMINAL_PROMPT=0",
        "ddev", "exec", "npm", "--prefix", "..", "run", "build",
    ]


def error_class(stderr: str, stdout: str, code: int | None) -> str:
    if code == 0 and OUTPUT not in stdout:
        return "ZERO_EXIT_WITHOUT_REQUIRED_MARKER"
    if code == 0:
        return "NONE"
    combined = (stderr + "\n" + stdout).lower()
    if "enoent" in combined or "package.json" in combined:
        return "PACKAGE_OR_PATH_ERROR"
    if "npm err" in combined or "npm error" in combined:
        return "NPM_SCRIPT_ERROR"
    if any(word in combined for word in (
        "ddev", "docker", "container not running", "cannot connect", "connection refused",
    )):
        return "DDEV_EXEC_ERROR"
    return "UNCLASSIFIED_NONZERO_EXIT"


def run_bounded(argv: list[str]) -> dict[str, Any]:
    began = time.monotonic()
    try:
        proc = subprocess.run(
            argv, stdin=subprocess.DEVNULL, text=True, capture_output=True,
            timeout=DOCKER_RUN_TIME, check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "returncode": None, "timed_out": True,
            "output_marker": False, "error_class": "EXEC_TIMEOUT",
            "elapsed_seconds": round(time.monotonic() - began, 1),
        }
    except OSError:
        return {
            "returncode": None, "timed_out": False,
            "output_marker": False, "error_class": "DOCKER_EXEC_UNAVAILABLE",
            "elapsed_seconds": round(time.monotonic() - began, 1),
        }
    marker = OUTPUT in proc.stdout
    return {
        "returncode": proc.returncode,
        "timed_out": False,
        "output_marker": marker,
        "error_class": error_class(proc.stderr[-4000:], proc.stdout[-4000:], proc.returncode),
        "elapsed_seconds": round(time.monotonic() - began, 1),
    }


def store(data: dict[str, Any]) -> None:
    # Exclusive creation before execution; one invocation only, including
    # timeouts/unknown status. Preserve the original smoke journal untouched.
    os.umask(0o077)
    with EVIDENCE.open("x", encoding="utf-8") as file:
        json.dump(data, file, sort_keys=True)
        file.write("\n")
    EVIDENCE.chmod(0o600)


def persist(data: dict[str, Any]) -> None:
    temp = ROOT / "node-continuation-evidence.tmp"
    os.umask(0o077)
    with temp.open("x", encoding="utf-8") as file:
        json.dump(data, file, sort_keys=True)
        file.write("\n")
    os.replace(temp, EVIDENCE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-pcp-sha", required=True)
    args = parser.parse_args()
    try:
        job, ws = workspace_identity(args.expected_pcp_sha)
        container = docker_identity(ws)
        store({
            "state": "started", "job_id": job,
            "model_calls": 0, "mcp_replayed": False,
        })
        result = run_bounded(npm_argv(container, ws))
        evidence = {
            "state": "completed", "job_id": job,
            "phase": "frontend_quality", "source_commit": SOURCE,
            "model_calls": 0, "mcp_replayed": False,
            "operator_command_only": True, **result,
        }
        persist(evidence)
        ok = result["returncode"] == 0 and result["output_marker"] \
            and not result["timed_out"]
        payload = {
            "status": ("PASS_G1_OPERATOR_NODE_PHASE_NOT_MCP"
                       if ok else "STOP_G1_OPERATOR_NODE_PHASE"),
            "job_prefix": job[:12],
            "model_calls": 0, "mcp_replayed": False,
            "ready_for_autonomous_e2e": False,
            "original_phase_exit_code": "NOT_PROVEN",
            **result,
        }
        code = 0 if ok else 2
    except (Stop, FileExistsError, PermissionError, OSError) as exc:
        payload = {
            "status": "STOP",
            "blocker": str(exc) if isinstance(exc, Stop)
                       else "g1_evidence_write_or_source_unavailable",
            "model_calls": 0, "mcp_replayed": False,
            "ready_for_autonomous_e2e": False,
            "no_automatic_retry": True,
        }
        code = 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
