#!/usr/bin/env python3
"""One-shot *operator-only* G1 source -> durable job -> isolated DDEV -> MCP smoke.

It can CREATE G1-only Docker resources. No Codex model call/agent/deploy/merge.
Use once on the Owner's WSL, after source GitHub CI and fresh fixture clone.
On ambiguous failure STOP, preserve G1-only resources for diagnosis, no retries.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
COMPOSE = REPO / "deploy/g1/compose.no-model.yml"
ROOT = Path.home() / ".pcp-g1-smoke"
SOURCE = "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
PROJECT = "pcp-benchmark-g1-smoke"
DDEV = "pcp-g1-codex-smoke"
PRIVATE = "pcp-g1-codex-smoke-private"
CONTAINERS = ("ddev-" + DDEV + "-web", "ddev-" + DDEV + "-db")
BASELINE = "g1-smoke-v1-2026-10-14"


class Stop(RuntimeError):
    """Sanitized failure code, not raw stdout/stderr or credentials."""


def call(argv: list[str], env: dict[str, str], step: str, *,
         stdin: str | None = None, timeout: int = 100) -> str:
    try:
        result = subprocess.run(
            argv, input=stdin, text=True, capture_output=True, timeout=timeout,
            check=False, env=env, stdin=subprocess.DEVNULL if stdin is None else None,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop(step + "_unavailable_or_timeout") from exc
    if result.returncode != 0:
        raise Stop(step + "_failed")
    return result.stdout.strip()


def compose(env: dict[str, str], step: str, *args: str,
            stdin: str | None = None, timeout: int = 180) -> str:
    return call(
        ["docker", "compose", "--project-name", "pcp-g1-smoke",
         "--file", str(COMPOSE), "--profile", "g1-no-model", *args],
        env, step, stdin=stdin, timeout=timeout,
    )


def git(where: Path, env: dict[str, str], *args: str) -> str:
    return call(["git", "-C", str(where), *args], env, "git_read", timeout=20)


def required(check: bool, code: str) -> None:
    if not check:
        raise Stop(code)


def private_file(path: Path, data: str) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(data)
    path.chmod(0o600)


def inputs(expected: str) -> tuple[dict[str, str], str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GH_PROMPT_DISABLED": "1"}
    required(os.geteuid() != 0 and re.fullmatch(r"[0-9a-f]{40}", expected) is not None,
             "unprivileged_operator_and_sha_required")
    required(git(REPO, env, "branch", "--show-current") == "main",
             "pcp_main_required")
    required(git(REPO, env, "rev-parse", "HEAD") == expected,
             "pcp_source_head_stale")
    required(not git(REPO, env, "status", "--porcelain"),
             "pcp_source_dirty")
    required(ROOT.is_dir() and not ROOT.is_symlink()
             and ROOT.stat().st_uid == os.geteuid(),
             "existing_disposable_root_required")
    required((ROOT / "source").is_dir() and not (ROOT / "source").is_symlink(),
             "cloned_fixture_source_missing")
    required(git(ROOT / "source", env, "rev-parse", "HEAD") == SOURCE
             and git(ROOT / "source", env, "branch", "--show-current")
                 == "benchmark/g1-codex-smoke-v1"
             and not git(ROOT / "source", env, "status", "--porcelain"),
             "fixture_source_drift")
    required(git(ROOT / "source", env, "hash-object",
                 ".ddev/config.yaml") ==
             "7a3e97a2a35fc8e67b67021365e7e91c448b52c9",
             "fixture_ddev_config_drift")
    required(not any((ROOT / name).exists() or (ROOT / name).is_symlink()
                     for name in ("workspaces", "config", "xdg", "smoke-journal.json")),
             "fixture_setup_already_started")
    cli = call(["codex", "--version"], env, "codex_version")
    match = re.fullmatch(r"codex-cli\s+([0-9]+\.[0-9]+\.[0-9]+)", cli.strip())
    required(match is not None, "codex_version_unrecognized")
    socket = Path("/var/run/docker.sock")
    required(socket.is_socket(), "local_docker_socket_unavailable")
    context = call(["docker", "context", "inspect"], env, "docker_context")
    try:
        info = json.loads(context)
        endpoint = info[0]["Endpoints"]["docker"]["Host"]
        required(len(info) == 1 and endpoint.startswith("unix://"),
                 "remote_docker_context_denied")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise Stop("docker_context_invalid") from exc
    # No existing G1 setup resources may be adopted, reset or restarted.
    for kind, fmt in (
        ("container", ["container", "ls", "-a", "--format", "{{json .}}"]),
        ("volume", ["volume", "ls", "--format", "{{json .}}"]),
        ("network", ["network", "ls", "--format", "{{json .}}"]),
    ):
        raw = call(["docker", *fmt], env, "fixture_inventory")
        for line in raw.splitlines():
            try:
                obj = json.loads(line)
                text = " ".join(str(obj.get(key) or "")
                                for key in ("Name", "Names", "Labels"))
                if any(marker in text.lower() for marker in (
                    "pcp-g1-smoke", "pcp-g1-codex-smoke",
                    "pcp-benchmark-g1-smoke",
                )):
                    raise Stop("preexisting_g1_docker_resources")
            except json.JSONDecodeError as exc:
                raise Stop("fixture_inventory_invalid") from exc
    return env, match.group(1)


def files() -> None:
    for sub in ("workspaces", "config", "xdg", "xdg/ddev"):
        (ROOT / sub).mkdir(mode=0o700, parents=True, exist_ok=False)
    private_file(
        ROOT / "xdg/ddev/global_config.yaml",
        "omit_containers: [ddev-router, ddev-ssh-agent]\n"
        "instrumentation_opt_in: false\n",
    )
    path = str(ROOT)
    phases = {
        "targeted_tests": [[
            "ddev", "exec", "php", "../vendor/bin/phpunit",
            "-c", "core/phpunit.xml.dist",
            "modules/custom/pcp_f2_fixture/tests/src/Unit",
        ]],
        "static_analysis": [[
            "ddev", "exec", "php", "../vendor/bin/phpcs",
            "--standard=Drupal", "modules/custom/pcp_f2_fixture",
        ]],
        "frontend_quality": [[
            "ddev", "exec", "npm", "--prefix", "..", "run", "build",
        ]],
    }
    project = {
        "version": 1,
        "projects": {PROJECT: {
            "path": path + "/source",
            "base_branch": "benchmark/g1-codex-smoke-v1",
            "runtime": {
                "developer_permission_mode": "trusted_project",
                "workspace_mode": "isolated_clone",
                "exclusive_project_lease": False,
                "branch_prefix": "ai",
            },
            "autonomy": {
                "allow_commit": False,
                "allow_push_ai_branch": False,
                "allow_create_pr": False,
                "allow_auto_merge_low_risk": False,
                "allow_production_deploy": False,
            },
            "ddev": {"enabled": True, "preflight": []},
            "trusted_codex_tools": phases,
        }},
    }
    reference = [{"path": "docs/G1-SMOKE.md"}]
    baselines = {
        "version": 1, "projects": {PROJECT: {
            "active_revision": BASELINE,
            "revisions": {BASELINE: {
                "status": "approved", "source_commit": SOURCE,
                "references": {key: reference for key in (
                    "goals", "non_goals", "requirements",
                    "architecture_constraints", "quality_policy",
                    "security_policy", "budget_policy", "roadmap_frame",
                )},
            }},
        }},
    }
    private_file(ROOT / "config/projects.yml",
                 json.dumps(project, indent=2) + "\n")
    private_file(ROOT / "config/project-baselines.yml",
                 json.dumps(baselines, indent=2) + "\n")


def docker_json(env: dict[str, str], kind: str, name: str) -> dict:
    raw = call(["docker", kind, "inspect", name], env, "docker_inspect")
    try:
        obj = json.loads(raw)
        if isinstance(obj, list) and len(obj) == 1 and isinstance(obj[0], dict):
            return obj[0]
    except json.JSONDecodeError:
        pass
    raise Stop("docker_inspect_invalid")


def require_new_ddev(env: dict[str, str], workspace: Path) -> None:
    # Before touching network membership, verify the two containers are owned
    # by the exact fixture and belong to the same isolated job workspace.
    raw = call(
        ["docker", "container", "ls", "-a",
         "--filter", "label=com.ddev.site-name=" + DDEV,
         "--format", "{{.Names}}"],
        env, "fixture_container_inventory",
    )
    required(set(raw.splitlines()) == set(CONTAINERS),
             "unexpected_fixture_container_set")
    for name in CONTAINERS:
        doc = docker_json(env, "container", name)
        labels = (doc.get("Config") or {}).get("Labels") or {}
        required(doc.get("Name") == "/" + name
                 and labels.get("com.ddev.site-name") == DDEV
                 and labels.get("com.ddev.approot") == str(workspace)
                 and (doc.get("State") or {}).get("Running") is True
                 and (doc.get("HostConfig") or {}).get("Privileged") is False,
                 "fixture_runtime_identity_or_privilege_drift")
        for mount in doc.get("Mounts") or []:
            origin = str(mount.get("Source") or "").lower()
            target = str(mount.get("Destination") or "").lower()
            required(not any(word in origin or word in target for word in (
                "docker.sock", "ssh-agent", "/.ssh", "/run/secrets",
            )), "fixture_sensitive_mount_found")


def quarantine(env: dict[str, str], workspace: Path) -> None:
    require_new_ddev(env, workspace)
    call(["docker", "network", "create", "--internal", "--driver", "bridge",
          "--label", "pcp.scope=g1-disposable-no-model", PRIVATE],
         env, "g1_private_network_create")
    for name in CONTAINERS:
        call(["docker", "network", "connect", PRIVATE, name],
             env, "g1_private_network_connect")
    for name in CONTAINERS:
        doc = docker_json(env, "container", name)
        networks = (doc.get("NetworkSettings") or {}).get("Networks") or {}
        required(PRIVATE in networks, "g1_private_network_join_missing")
        for foreign in sorted(set(networks) - {PRIVATE}):
            # Disconnect ONLY our two attested new G1 containers, never modify
            # ddev_default, another project, shared Docker volume or router.
            call(["docker", "network", "disconnect", foreign, name],
                 env, "g1_shared_network_disconnect")
    sys.path.insert(0, str(REPO / "services/ddev-executor"))
    from app.g1_ddev_isolation import require_g1_isolated_ddev, G1IsolationStop
    try:
        require_g1_isolated_ddev(workspace)
    except G1IsolationStop as exc:
        raise Stop(str(exc)) from None


def no_model_mcp(env: dict[str, str]) -> None:
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "pcp_run_project_checks",
            "arguments": {"phase": "frontend_quality"},
        }},
    ]
    raw = compose(env, "g1_mcp_stdio_http_phase", "run", "--rm", "--no-deps",
                  "-T", "runtime", "python3", "/app/app/trusted_codex_mcp.py",
                  stdin="".join(json.dumps(r) + "\n" for r in requests),
                  timeout=230)
    try:
        messages = [json.loads(line) for line in raw.splitlines()
                    if line.strip().startswith('{"jsonrpc"')]
        result = {r["id"]: r["result"] for r in messages if "result" in r}
        required(set(result) == {1, 2, 3}, "g1_mcp_handshake_incomplete")
        required(result[1]["serverInfo"]["name"] == "pcp-fixture-dev",
                 "g1_mcp_server_identity_drift")
        required(result[2]["tools"][0]["name"] == "pcp_run_project_checks",
                 "g1_mcp_tools_not_scoped")
        tool = result[3]
        required(tool["isError"] is False and
                 "G1_NODE_BUILD_CHECK=PASS" in tool["content"][0]["text"],
                 "g1_real_executor_node_phase_failed")
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise Stop("g1_mcp_response_invalid") from exc


def execute(expected: str) -> dict:
    began = time.monotonic()
    env, codex_version = inputs(expected)
    files()
    env.update({
        "PCP_G1_ROOT": str(ROOT),
        "PCP_G1_UID": str(os.geteuid()),
        "PCP_G1_GID": str(os.getegid()),
        "PCP_G1_SOCKET_GID": str(Path("/var/run/docker.sock").stat().st_gid),
        "PCP_G1_CODEX_VERSION": codex_version,
        "PCP_G1_DB_PASSWORD": secrets.token_hex(24),
        "PCP_G1_RUNTIME_TOKEN": secrets.token_urlsafe(36),
        "PCP_G1_INTERNAL_TOKEN": secrets.token_urlsafe(36),
        "PCP_G1_BROKER_ENABLED": "",
        "PCP_G1_JOB_ID": "",
        "PCP_G1_DEV_TOKEN": "",
        "PCP_G1_DEADLINE": "",
    })
    compose(env, "g1_compose_contract", "config", "--quiet", timeout=40)
    compose(env, "g1_image_build", "build", "runtime", "pcp-dev-executor",
            timeout=1500)
    compose(env, "g1_postgres_start", "up", "-d", "--wait", "db", timeout=240)

    register = (
        "import json; from app.storage import Storage; "
        "from app.engine import RuntimeEngine; "
        "s=Storage(); s.init(); "
        "assert not s.list(limit=1), 'Dedicated G1 DB already has a job'; "
        "j=RuntimeEngine(s).create_job({"
        "'project_id':'pcp-benchmark-g1-smoke',"
        "'task':{'title':'G1 no-model readiness smoke',"
        "'description':'Operator-only MCP/Executor proof; no model.'},"
        "'source_commit':'" + SOURCE + "',"
        "'baseline_revision':'" + BASELINE + "',"
        "'auto_run':False}); "
        "print(json.dumps({'job_id':j}))"
    )
    raw = compose(env, "g1_durable_job_create", "run", "--rm", "--no-deps",
                  "-T", "runtime", "python3", "-c", register, timeout=120)
    try:
        job = json.loads(raw.splitlines()[-1])["job_id"]
        required(re.fullmatch("[0-9a-f]{32}", job) is not None,
                 "g1_durable_job_id_invalid")
    except (IndexError, KeyError, ValueError) as exc:
        raise Stop("g1_durable_job_response_invalid") from exc
    env["PCP_G1_JOB_ID"] = job
    private_file(ROOT / "smoke-journal.json", json.dumps({
        "job_id": job, "project_id": PROJECT, "source_sha": SOURCE,
        "state": "workspace_pending", "model_calls": 0,
    }, indent=2) + "\n")

    workspace_code = (
        "import json,os; from app.main import create_workspace,WorkspaceRequest; "
        "p=WorkspaceRequest(job_id=os.environ['PCP_TRUSTED_CODEX_JOB_ID'],"
        "project_id='" + PROJECT + "',ref='" + SOURCE + "',"
        "workspace_mode='isolated_clone'); "
        "print(json.dumps(create_workspace(p)))"
    )
    raw = compose(env, "g1_exact_workspace_create", "run", "--rm", "--no-deps",
                  "-T", "pcp-dev-executor", "python3", "-c", workspace_code,
                  timeout=330)
    try:
        result = json.loads(raw.splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise Stop("g1_workspace_response_invalid") from exc
    workspace = ROOT / "workspaces" / job
    required(result.get("workspace") == str(workspace)
             and result.get("source_commit") == SOURCE
             and result.get("branch") == "ai/" + job[:12],
             "g1_workspace_provenance_mismatch")

    # Operator-controlled start uses only reviewed fixture code, with isolated
    # global DDEV config (no router or SSH agent). No model runs before quarantine.
    compose(env, "g1_ddev_single_start", "run", "--rm", "--no-deps", "-T",
            "pcp-dev-executor", "sh", "-c",
            'cd "$CODING_WORKSPACES_ROOT/$PCP_TRUSTED_CODEX_JOB_ID" && '
            'exec ddev start -y', timeout=900)
    quarantine(env, workspace)

    # Issue a new, single-job capability *after* setup. Not included in argv,
    # prompt, logs, journal or source checkout.
    env["PCP_G1_DEV_TOKEN"] = secrets.token_urlsafe(48)
    env["PCP_G1_DEADLINE"] = str(int(time.time()) + 900)
    env["PCP_G1_BROKER_ENABLED"] = "owner-approved"
    compose(env, "g1_executor_start", "up", "-d", "pcp-dev-executor",
            timeout=120)
    no_model_mcp(env)
    return {
        "status": "PASS_G1_REAL_MCP_EXECUTOR_NO_MODEL",
        "pcp_source_sha": expected,
        "fixture_source_sha": SOURCE,
        "durable_job_id": job,
        "job_dispatched_to_model": False,
        "ddev_isolated_private_internal": True,
        "mcp_stdio_handshake": "PASS",
        "executor_frontend_quality": "PASS",
        "model_calls": 0,
        "elapsed_seconds": round(time.monotonic() - began, 1),
        "ready_for_autonomous_e2e": False,
        "g0": "HOLD_NOT_GO",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-pcp-sha", required=True)
    args = parser.parse_args()
    try:
        report = execute(args.expected_pcp_sha)
        code = 0
    except Stop as exc:
        report = {
            "status": "STOP", "blocker": str(exc),
            "scope": "G1_DISPOSABLE_ONLY",
            "no_automatic_retry_or_cleanup": True,
            "model_calls": 0,
            "ready_for_autonomous_e2e": False,
        }
        code = 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
