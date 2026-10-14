#!/usr/bin/env python3
"""One-shot G1 corrected MCP phase check on the EXISTING disposable job.

Recreate ONLY pcp-g1-smoke's Executor to refresh its short-lived scoped
process env. Do NOT restart DDEV web/db, replay setup, create a job, use a model,
read foreign projects, or expose Docker/Executor bearer tokens in output.
An exclusive attempt record prevents automatic retry on ambiguous failures.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ROOT = Path.home() / ".pcp-g1-smoke"
COMPOSE = REPO / "deploy/g1/compose.no-model.yml"
ATTEMPT = ROOT / "mcp-corrected-recheck-evidence.json"
PINNED_SOURCE = "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
PROJECT = "pcp-benchmark-g1-smoke"
EXPECT_CMD = ["ddev", "exec", "npm", "--prefix", "/var/www/html", "run", "build"]
MARKER = "G1_NODE_BUILD_CHECK=PASS"
CONTROL = "pcp-g1-smoke-control"
JOB_PREFIX = "2c6db0aa6f19"


class Stop(RuntimeError):
    """Only predefined reason codes, never raw stdout, stderr or credentials."""


def check(ok: bool, code: str) -> None:
    if not ok:
        raise Stop(code)


def run(argv: list[str], *, env: dict[str, str] | None = None,
        stdin: str | None = None, timeout: int = 20,
        step: str = "g1_command") -> str:
    options: dict[str, Any] = {
        "text": True, "capture_output": True,
        "check": False, "timeout": timeout,
    }
    if env is not None:
        options["env"] = env
    if stdin is None:
        options["stdin"] = subprocess.DEVNULL
    else:
        options["input"] = stdin
    try:
        response = subprocess.run(argv, **options)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop(step + "_unavailable_or_timeout") from exc
    if response.returncode != 0:
        raise Stop(step + "_failed")
    return response.stdout.strip()


def compose(env: dict[str, str], *args: str,
            stdin: str | None = None, timeout: int = 60,
            step: str = "g1_compose") -> str:
    return run([
        "docker", "compose", "--project-name", "pcp-g1-smoke",
        "--file", str(COMPOSE), "--profile", "g1-no-model", *args,
    ], env=env, stdin=stdin, timeout=timeout, step=step)


def prior_operator():
    file = REPO / "scripts/g1-existing-node-continuation.py"
    check(file.is_file() and not file.is_symlink(),
          "g1_prior_attestation_module_missing")
    spec = importlib.util.spec_from_file_location("g1_prior_attestation", file)
    check(spec is not None and spec.loader is not None,
          "g1_prior_attestation_module_invalid")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect(kind: str, identifier: str) -> dict[str, Any]:
    try:
        document = json.loads(run(
            ["docker", kind, "inspect", identifier],
            step="g1_inspect",
        ))
        check(isinstance(document, list) and len(document) == 1
              and isinstance(document[0], dict), "g1_inspect_invalid")
        return document[0]
    except (ValueError, IndexError, TypeError) as exc:
        raise Stop("g1_inspect_invalid") from exc


def service_id(name: str) -> str:
    ids = run([
        "docker", "container", "ls", "--all",
        "--filter", "label=com.docker.compose.project=pcp-g1-smoke",
        "--filter", "label=com.docker.compose.service=" + name,
        "--format", "{{.ID}}",
    ], step="g1_service_inventory").splitlines()
    check(len(ids) == 1 and re.fullmatch(r"[a-f0-9]{12,64}", ids[0]) is not None,
          "g1_service_not_singleton")
    return ids[0]


def env_mapping(container: dict[str, Any]) -> dict[str, str]:
    values = (container.get("Config") or {}).get("Env") or []
    check(isinstance(values, list)
          and all(isinstance(v, str) and "=" in v for v in values),
          "g1_container_env_unavailable")
    return dict(v.split("=", 1) for v in values)


def identity(expected_sha: str):
    check(re.fullmatch(r"[a-f0-9]{40}", expected_sha) is not None,
          "g1_expected_main_sha_invalid")
    check(os.geteuid() != 0, "g1_unprivileged_operator_required")
    check(REPO.is_dir() and COMPOSE.is_file(), "g1_source_files_missing")
    check(
        run(["git", "-C", str(REPO), "rev-parse", "HEAD"]) == expected_sha
        and run(["git", "-C", str(REPO), "branch", "--show-current"]) == "main"
        and not run(["git", "-C", str(REPO), "status", "--porcelain"]),
        "g1_pcp_main_not_exact_clean",
    )
    check(ROOT.is_dir() and not ROOT.is_symlink()
          and ROOT.stat().st_uid == os.geteuid(), "g1_original_root_invalid")
    check(not ATTEMPT.exists() and not ATTEMPT.is_symlink(),
          "g1_mcp_recheck_already_attempted")
    journal = ROOT / "smoke-journal.json"
    repaired = ROOT / "node-prefix-repair-evidence.json"
    config = ROOT / "config/projects.yml"
    check(all(f.is_file() and not f.is_symlink()
              for f in (journal, repaired, config)), "g1_original_evidence_missing")
    try:
        record = json.loads(journal.read_text(encoding="utf-8"))
        proof = json.loads(repaired.read_text(encoding="utf-8"))
        cfg = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Stop("g1_original_evidence_invalid") from exc
    job = record.get("job_id")
    check(
        isinstance(job, str) and re.fullmatch(r"[a-f0-9]{32}", job) is not None
        and job.startswith(JOB_PREFIX)
        and record.get("state") == "workspace_pending"
        and record.get("model_calls") == 0
        and record.get("source_sha") == PINNED_SOURCE
        and record.get("project_id") == PROJECT
        and proof.get("state") == "complete"
        and proof.get("job_id") == job
        and proof.get("returncode") == 0
        and proof.get("output_marker") is True
        and proof.get("timed_out") is False
        and proof.get("config_changed") is True
        and proof.get("mcp_replayed") is False
        and proof.get("model_calls") == 0,
        "g1_original_job_or_node_proof_drift",
    )
    ws = ROOT / "workspaces" / job
    check(ws.is_dir() and not ws.is_symlink()
          and ws.resolve() == ws and ws.parent == ROOT / "workspaces",
          "g1_workspace_missing_or_alias")
    check(
        run(["git", "-C", str(ws), "rev-parse", "--show-toplevel"]) == str(ws)
        and run(["git", "-C", str(ws), "rev-parse", "HEAD"]) == PINNED_SOURCE
        and run(["git", "-C", str(ws), "branch", "--show-current"])
            == "ai/" + job[:12]
        and not run(["git", "-C", str(ws), "status", "--porcelain"]),
        "g1_workspace_source_drift",
    )
    try:
        projects = cfg["projects"]
        project = projects[PROJECT]
        check(
            set(projects) == {PROJECT}
            and project["path"] == str(ROOT / "source")
            and project["runtime"]["developer_permission_mode"] == "trusted_project"
            and project["runtime"]["workspace_mode"] == "isolated_clone"
            and project["runtime"]["exclusive_project_lease"] is False
            and project["autonomy"]["allow_auto_merge_low_risk"] is False
            and project["autonomy"]["allow_production_deploy"] is False
            and project["trusted_codex_tools"]["frontend_quality"] == [EXPECT_CMD]
            and project["ddev"]["enabled"] is True,
            "g1_broker_registry_changed",
        )
    except (KeyError, TypeError) as exc:
        raise Stop("g1_broker_registry_invalid") from exc
    previous = prior_operator()
    previous.attest_g1(ws)
    executor_id = previous.docker_identity(ws)
    old = inspect("container", executor_id)
    values = env_mapping(old)
    check(
        values.get("PCP_TRUSTED_CODEX_JOB_ID") == job
        and values.get("PCP_TRUSTED_CODEX_PROJECT_ID") == PROJECT
        and values.get("PCP_TRUSTED_CODEX_SOURCE_SHA") == PINNED_SOURCE
        and values.get("PCP_TRUSTED_CODEX_BROKER_ENABLED") == "owner-approved"
        and re.fullmatch(r"[0-9]{9,12}",
                         values.get("PCP_TRUSTED_CODEX_DEADLINE_EPOCH", "")) is not None
        and int(values["PCP_TRUSTED_CODEX_DEADLINE_EPOCH"]) < int(time.time()),
        "g1_old_broker_capability_not_expired",
    )
    check((old.get("Config") or {}).get("User") ==
          f"{os.geteuid()}:{os.getegid()}", "g1_executor_uid_changed")
    dbid = service_id("db")
    db = inspect("container", dbid)
    labels = (db.get("Config") or {}).get("Labels") or {}
    check(
        (db.get("State") or {}).get("Running") is True
        and labels.get("com.docker.compose.project") == "pcp-g1-smoke"
        and labels.get("com.docker.compose.service") == "db"
        and set((db.get("NetworkSettings") or {}).get("Networks") or {}) == {CONTROL}
        and any(x.get("Name") == "pcp-g1-smoke-postgres"
                for x in db.get("Mounts") or []),
        "g1_existing_postgres_identity_changed",
    )
    password = env_mapping(db).get("POSTGRES_PASSWORD", "")
    check(bool(password), "g1_disposable_db_password_missing")
    db_full_id = db.get("Id")
    check(isinstance(db_full_id, str) and len(db_full_id) == 64,
          "g1_existing_postgres_container_id_invalid")
    web_id = inspect("container", "ddev-pcp-g1-codex-smoke-web").get("Id")
    ddev_db_id = inspect("container", "ddev-pcp-g1-codex-smoke-db").get("Id")
    check(bool(web_id) and bool(ddev_db_id), "g1_ddev_container_ids_missing")
    return previous, job, ws, executor_id, dbid, db_full_id, web_id, ddev_db_id, password, old


def configure(job: str, password: str) -> dict[str, str]:
    cli = run(["codex", "--version"], step="g1_codex_cli_version")
    version = re.fullmatch(r"codex-cli\s+(\d+\.\d+\.\d+)", cli)
    check(version is not None, "g1_codex_cli_version_invalid")
    sock = Path("/var/run/docker.sock")
    check(sock.is_socket(), "g1_docker_socket_missing")
    return {
        **os.environ,
        "PCP_G1_ROOT": str(ROOT),
        "PCP_G1_UID": str(os.geteuid()),
        "PCP_G1_GID": str(os.getegid()),
        "PCP_G1_SOCKET_GID": str(sock.stat().st_gid),
        "PCP_G1_CODEX_VERSION": version.group(1),
        "PCP_G1_DB_PASSWORD": password,
        "PCP_G1_RUNTIME_TOKEN": secrets.token_urlsafe(48),
        "PCP_G1_INTERNAL_TOKEN": secrets.token_urlsafe(48),
        "PCP_G1_BROKER_ENABLED": "owner-approved",
        "PCP_G1_JOB_ID": job,
        "PCP_G1_DEV_TOKEN": secrets.token_urlsafe(48),
        "PCP_G1_DEADLINE": str(int(time.time()) + 900),
        "GIT_TERMINAL_PROMPT": "0",
    }


def save(record: dict[str, Any], *, first: bool) -> None:
    os.umask(0o077)
    if first:
        with ATTEMPT.open("x", encoding="utf-8") as f:
            json.dump(record, f, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
    else:
        temp = ROOT / "mcp-corrected-recheck-evidence.tmp"
        with temp.open("x", encoding="utf-8") as f:
            json.dump(record, f, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, ATTEMPT)


def rpc_request() -> str:
    calls = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "pcp_run_project_checks",
            "arguments": {"phase": "frontend_quality"},
        }},
    ]
    return "".join(json.dumps(x) + "\n" for x in calls)


def parse_phase(raw: str, job: str) -> dict[str, Any]:
    try:
        messages = [json.loads(x) for x in raw.splitlines()
                    if x.strip().startswith('{"jsonrpc"')]
        payload = {x["id"]: x for x in messages if "id" in x}
        check(set(payload) == {1, 2, 3} and
              payload[1]["result"]["serverInfo"]["name"] == "pcp-fixture-dev"
              and [t["name"] for t in payload[2]["result"]["tools"]]
                  == ["pcp_run_project_checks"],
              "g1_mcp_handshake_invalid")
        tool = payload[3]["result"]
        body = json.loads(tool["content"][0]["text"])
        commands = body["commands"]
        check(body["job_id"] == job and
              body["project_id"] == PROJECT and
              body["phase"] == "frontend_quality" and
              isinstance(commands, list) and len(commands) == 1,
              "g1_mcp_phase_response_invalid")
        cmd = commands[0]
        result = {
            "phase_http_200": True,
            "phase_passed": body["passed"] is True and tool["isError"] is False,
            "returncode": cmd.get("returncode"),
            "timed_out": cmd.get("timed_out"),
            "output_marker": MARKER in str(cmd.get("stdout") or ""),
            "tool_calls_used": body.get("tool_calls_used"),
            "tool_calls_max": body.get("tool_calls_max"),
            "model_calls": 0,
        }
        result["accepted"] = (
            result["phase_passed"] and result["returncode"] == 0
            and result["timed_out"] is False
            and result["output_marker"] is True
            and result["tool_calls_used"] == 1
        )
        return result
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        raise Stop("g1_mcp_jsonrpc_response_invalid") from exc


def execute(expected_sha: str) -> dict[str, Any]:
    previous, job, ws, old_executor, dbid, db_full_id, webid, ddevdbid, password, old = identity(expected_sha)
    env = configure(job, password)
    started = time.monotonic()
    save({
        "state": "started", "job_id": job, "project_id": PROJECT,
        "model_calls": 0, "mcp_recheck_attempts": 0,
        "executor_only_refresh": True,
    }, first=True)
    # Only the opted-in G1 Executor can be replaced; never touch DDEV, DB, F2.
    compose(
        env, "up", "-d", "--no-deps", "--no-build", "--force-recreate",
        "pcp-dev-executor", step="g1_executor_only_capability_refresh",
        timeout=120,
    )
    executor = service_id("pcp-dev-executor")
    check(executor != old_executor, "g1_executor_was_not_refreshed")
    new = inspect("container", executor)
    check(new.get("Image") == old.get("Image"),
          "g1_executor_image_changed")
    check(
        (new.get("State") or {}).get("Running") is True
        and set((new.get("NetworkSettings") or {}).get("Networks") or {}) == {CONTROL}
        and previous.docker_identity(ws) == executor,
        "g1_refreshed_executor_not_isolated",
    )
    fresh_env = env_mapping(new)
    check(
        fresh_env.get("PCP_TRUSTED_CODEX_BROKER_ENABLED") == "owner-approved"
        and fresh_env.get("PCP_TRUSTED_CODEX_DEV_TOKEN") == env["PCP_G1_DEV_TOKEN"]
        and fresh_env.get("PCP_TRUSTED_CODEX_JOB_ID") == job
        and fresh_env.get("PCP_TRUSTED_CODEX_SOURCE_SHA") == PINNED_SOURCE
        and fresh_env.get("PCP_TRUSTED_CODEX_DEADLINE_EPOCH") == env["PCP_G1_DEADLINE"],
        "g1_new_capability_identity_invalid",
    )
    check(inspect("container", dbid).get("Id") == db_full_id
          and inspect("container", "ddev-pcp-g1-codex-smoke-web").get("Id") == webid
          and inspect("container", "ddev-pcp-g1-codex-smoke-db").get("Id") == ddevdbid,
          "g1_other_containers_changed")
    previous.attest_g1(ws)
    # HTTP readiness is a GET only; never retry a build or a tool call.
    ready = False
    for _ in range(10):
        try:
            probe = run([
                "docker", "exec", executor, "python3", "-c",
                "import urllib.request; "
                "r=urllib.request.urlopen('http://127.0.0.1:8790/health',"
                "timeout=2); assert r.status==200",
            ], timeout=5, step="g1_executor_health")
            ready = True
            break
        except Stop:
            time.sleep(0.5)
    check(ready, "g1_executor_health_not_ready")
    raw = compose(
        env, "run", "--rm", "--no-deps", "-T", "runtime",
        "python3", "/app/app/trusted_codex_mcp.py",
        stdin=rpc_request(), timeout=220, step="g1_mcp_single_corrected_phase",
    )
    result = parse_phase(raw, job)
    save({
        "state": "completed",
        "job_id": job,
        "source_sha": PINNED_SOURCE,
        "phase": "frontend_quality",
        "time_seconds": round(time.monotonic() - started, 1),
        "executor_only_refreshed": True,
        "mcp_recheck_attempts": 1,
        "ready_for_autonomous_e2e": False,
        **result,
    }, first=False)
    return {
        "status": ("PASS_G1_CORRECTED_MCP_HTTP_EXECUTOR_NO_MODEL"
                   if result["accepted"] else "STOP_G1_CORRECTED_MCP_PHASE"),
        "job_prefix": job[:12],
        "executor_only_refreshed": True,
        "ddev_web_db_restarted": False,
        "no_new_job": True,
        "ready_for_autonomous_e2e": False,
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-pcp-sha", required=True)
    args = parser.parse_args()
    try:
        result = execute(args.expected_pcp_sha)
        status = 0 if result["status"].startswith("PASS_") else 2
    except (Stop, PermissionError, FileExistsError, OSError) as exc:
        result = {
            "status": "STOP",
            "blocker": str(exc) if isinstance(exc, Stop)
                       else "g1_evidence_or_docker_unavailable",
            "model_calls": 0,
            "mcp_phase_passed": False,
            "ready_for_autonomous_e2e": False,
            "no_automatic_retry": True,
        }
        status = 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
