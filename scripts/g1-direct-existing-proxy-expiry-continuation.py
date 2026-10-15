#!/usr/bin/env python3
"""One G1-T01 same-workspace recovery from a verified EXPIRED direct proxy.

Do not rerun either previous one-shot script. Never recreate the old proxy,
model job or workspace. Reuse the exact existing STOPPED G1-only proxy container
only after proving its bounded 1200s lifetime expired, then one classified
pre-model auth/egress gate and at most one direct Codex attempt.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

PCP = Path(__file__).resolve().parents[1]
ROOT = Path.home() / ".pcp-g1-pilot"
OLD_JOURNAL = ROOT / "direct-t01-evidence.json"
BUILD_JOURNAL = ROOT / "direct-t01-build-continuation-evidence.json"
EVIDENCE = ROOT / "direct-t01-expired-proxy-evidence.json"
SEED = "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
PROXY_NAME = "pcp-g1-pilot-direct-proxy-operator"
PROXY_SERVICE = "g1-pilot-direct-proxy"
IMAGE = "pcp-g1-pilot-direct-codex"
EXPECTED_NETS = {
    "pcp-g1-pilot-direct-control",
    "pcp-g1-pilot-direct-provider-egress",
}
# Only observed ~1200s expiry is eligible; early crashes are NOT retried.
MIN_EXPIRED_SECONDS = 1140
MAX_EXPIRED_SECONDS = 1320
MAX_MODEL_SECONDS = 1080
ALLOWED_STAGES = (
    "AUTH_FILE", "CODEX_LOGIN_STATUS", "PROXY_DNS", "GITHUB_DENY",
    "CHATGPT_CONNECT", "TLS_HANDSHAKE", "PASS",
)
PREFLIGHT = r'''
import json,os,socket,ssl,subprocess,sys
from pathlib import Path

data = {
    "auth_file_readable": False,
    "codex_login_status_pass": False,
    "proxy_dns_pass": False,
    "github_connect_denied": False,
    "chatgpt_connect_allowed": False,
    "tls_verified": False,
}
stage = "AUTH_FILE"
try:
    home = Path(os.environ["CODEX_HOME"])
    data["auth_file_readable"] = (home / "auth.json").is_file() and os.access(
        home / "auth.json", os.R_OK)
    if not data["auth_file_readable"]:
        raise ValueError("auth unavailable")
    stage = "CODEX_LOGIN_STATUS"
    status = subprocess.run(["codex","login","status"],capture_output=True,
                            text=True,stdin=subprocess.DEVNULL,timeout=15)
    combined = (status.stdout + "\n" + status.stderr).lower()
    data["codex_login_status_pass"] = (
        status.returncode == 0 and "chatgpt" in combined and "logged in" in combined
    )
    if not data["codex_login_status_pass"]:
        raise ValueError("login status")
    stage = "PROXY_DNS"
    socket.getaddrinfo("g1-pilot-direct-proxy",3128)
    data["proxy_dns_pass"] = True
    stage = "GITHUB_DENY"
    with socket.create_connection(("g1-pilot-direct-proxy",3128),timeout=12) as s:
        s.settimeout(12)
        s.sendall(
            b"CONNECT api.github.com:443 HTTP/1.1\r\n"
            b"Host: api.github.com:443\r\n\r\n"
        )
        data["github_connect_denied"] = s.recv(256).startswith(b"HTTP/1.1 403")
    if not data["github_connect_denied"]:
        raise ValueError("github not denied")
    stage = "CHATGPT_CONNECT"
    with socket.create_connection(("g1-pilot-direct-proxy",3128),timeout=12) as s:
        s.settimeout(12)
        s.sendall(
            b"CONNECT chatgpt.com:443 HTTP/1.1\r\n"
            b"Host: chatgpt.com:443\r\n\r\n"
        )
        data["chatgpt_connect_allowed"] = s.recv(256).startswith(b"HTTP/1.1 200")
        if not data["chatgpt_connect_allowed"]:
            raise ValueError("provider connect denied")
        stage = "TLS_HANDSHAKE"
        with ssl.create_default_context().wrap_socket(
                s, server_hostname="chatgpt.com") as tls:
            data["tls_verified"] = tls.version() is not None
    stage = "PASS"
except Exception:
    pass
data["failed_at"] = stage if stage != "PASS" else "NONE"
print(json.dumps(data,sort_keys=True))
sys.exit(0 if stage == "PASS" else 2)
'''


class Stop(RuntimeError):
    """Only fixed error codes; never expose raw model/Compose/credential logs."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Stop(reason)


def import_script(path: str, name: str):
    file = PCP / path
    require(file.is_file() and not file.is_symlink(), "g1_direct_source_missing")
    spec = importlib.util.spec_from_file_location(name, file)
    require(spec is not None and spec.loader is not None,
            "g1_direct_source_import_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command(argv: list[str], *, timeout: int = 20,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, check=False,
            stdin=subprocess.DEVNULL, timeout=timeout, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("g1_direct_bounded_command_unavailable_or_timeout") from exc


def output(argv: list[str], *, timeout: int = 20) -> str:
    r = command(argv, timeout=timeout)
    require(r.returncode == 0, "g1_direct_readonly_command_failed")
    return r.stdout.strip()


def inspect(kind: str, name: str) -> dict[str, Any]:
    raw = output(["docker", kind, "inspect", name])
    try:
        parsed = json.loads(raw)
        require(isinstance(parsed, list) and len(parsed) == 1
                and isinstance(parsed[0], dict),
                "g1_direct_docker_inspect_invalid")
        return parsed[0]
    except (ValueError, TypeError, IndexError) as exc:
        raise Stop("g1_direct_docker_inspect_invalid") from exc


def safe_read_journal(path: Path, state: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink()
            and path.stat().st_uid == os.geteuid(),
            "g1_direct_prior_journal_missing_or_foreign")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise Stop("g1_direct_prior_journal_invalid") from exc
    require(record.get("state") == state and record.get("lane") == "direct"
            and record.get("seed", record.get("source_sha")) == SEED,
            "g1_direct_prior_journal_state_drift")
    return record


def lifespan_seconds(state: dict[str, Any]) -> float:
    started, stopped = state.get("StartedAt"), state.get("FinishedAt")
    require(isinstance(started, str) and isinstance(stopped, str),
            "g1_direct_proxy_lifetime_missing")
    try:
        start = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end = datetime.fromisoformat(stopped.replace("Z", "+00:00"))
        return (end - start).total_seconds()
    except ValueError as exc:
        raise Stop("g1_direct_proxy_lifetime_unparseable") from exc


def require_expired_window(state: dict[str, Any]) -> float:
    require(
        state.get("Running") is False
        and state.get("ExitCode") == 1
        and state.get("OOMKilled") is False
        and not state.get("Error"),
        "g1_direct_proxy_not_cleanly_expired",
    )
    elapsed = lifespan_seconds(state)
    require(MIN_EXPIRED_SECONDS <= elapsed <= MAX_EXPIRED_SECONDS,
            "g1_direct_proxy_did_not_exit_by_20m_window")
    return elapsed


def attest_existing(expected_sha: str, old, recovery) -> tuple[str, str, str]:
    require(re.fullmatch(r"[a-f0-9]{40}", expected_sha) is not None
            and os.geteuid() != 0,
            "g1_direct_unprivileged_exact_merge_sha_required")
    require(
        output(["git", "-C", str(PCP), "rev-parse", "HEAD"]) == expected_sha
        and output(["git", "-C", str(PCP), "branch", "--show-current"]) == "main"
        and not output(["git", "-C", str(PCP), "status", "--porcelain"]),
        "g1_direct_pcp_checkout_not_exact_clean_main",
    )
    require(ROOT.is_dir() and not ROOT.is_symlink()
            and ROOT.stat().st_uid == os.geteuid()
            and not EVIDENCE.exists() and not EVIDENCE.is_symlink(),
            "g1_direct_root_or_exclusive_evidence_drift")
    old_row = safe_read_journal(OLD_JOURNAL, "started")
    new_row = safe_read_journal(BUILD_JOURNAL, "continuation_started")
    require(
        old_row.get("attempts") == 0
        and old_row.get("model") == old.MODEL
        and old_row.get("effort") == old.EFFORT
        and new_row.get("original_attempts") == 0
        and new_row.get("model_calls") == 0
        and not any((ROOT / file).exists() for file in (
            "direct-t01-evidence.tmp",
            "direct-t01-build-continuation-evidence.tmp",
            "direct-t01-expired-proxy-evidence.tmp",
            "source", "workspaces",
        )),
        "g1_direct_model_already_attempted_or_pcp_lane_changed",
    )
    ws = ROOT / "direct-workspace"
    require(ws.is_dir() and not ws.is_symlink() and ws.resolve() == ws
            and output(["git", "-C", str(ws), "rev-parse", "--show-toplevel"])
                == str(ws)
            and output(["git", "-C", str(ws), "rev-parse", "HEAD"]) == SEED
            and output(["git", "-C", str(ws), "branch", "--show-current"])
                == old.BRANCH
            and not output(["git", "-C", str(ws), "status", "--porcelain"])
            and not output(["git", "-C", str(ws), "ls-files", "--others",
                            "--ignored", "--exclude-standard"]),
            "g1_direct_original_workspace_not_clean_seed",
    )
    for lane in ("pcp", "direct"):
        folder = ROOT / "auth" / lane
        auth = folder / "auth.json"
        require(folder.is_dir() and not folder.is_symlink()
                and folder.stat().st_uid == os.geteuid()
                and auth.is_file() and not auth.is_symlink()
                and auth.stat().st_uid == os.geteuid()
                and not (auth.stat().st_mode & 0o077),
                "g1_direct_existing_auth_not_private")
    require((ROOT / "auth/pcp").resolve() !=
            (ROOT / "auth/direct").resolve(), "g1_direct_auth_lanes_mixed")
    marker = ROOT / "inactive/github-disabled"
    require(marker.is_file() and not marker.is_symlink()
            and marker.read_text(encoding="utf-8") ==
                recovery.DISABLED_GITHUB
            and not (marker.stat().st_mode & 0o077),
            "g1_direct_disabled_github_marker_changed")
    version = output(["codex", "--version"])
    match = re.fullmatch(r"codex-cli\s+(\d+\.\d+\.\d+)", version)
    require(match is not None, "g1_direct_cli_version_invalid")
    image = inspect("image", recovery.DIRECT_IMAGE)
    labels = (image.get("Config") or {}).get("Labels") or {}
    require(labels.get(recovery.SCOPE_LABEL) == "direct-control-only"
            and labels.get(recovery.MODEL_VERSION_LABEL) == match.group(1),
            "g1_direct_existing_image_identity_changed")
    require(command(["docker", "image", "inspect", old.APP_IMAGE]).returncode != 0,
            "g1_direct_full_runtime_image_unexpected")
    host = json.loads(output(["docker", "context", "inspect"]))
    try:
        addr = host[0]["Endpoints"]["docker"]["Host"]
        require(len(host) == 1 and isinstance(addr, str)
                and addr.startswith("unix://")
                and Path(addr[7:]).resolve() ==
                    Path("/var/run/docker.sock").resolve()
                and not os.getenv("DOCKER_HOST", ""),
                "g1_direct_unreviewed_docker_daemon")
    except (KeyError, ValueError, IndexError, TypeError) as exc:
        raise Stop("g1_direct_docker_context_unverifiable") from exc
    # Require EXACTLY the one stopped, previously attested direct proxy.
    proxy = inspect("container", PROXY_NAME)
    container_id = proxy.get("Id")
    require(isinstance(container_id, str) and
            re.fullmatch(r"[a-f0-9]{64}", container_id) is not None,
            "g1_direct_proxy_full_id_invalid")
    config = proxy.get("Config") or {}
    labels = config.get("Labels") or {}
    cmd = old.proxy_argv()
    mounts = proxy.get("Mounts") or []
    net = (proxy.get("NetworkSettings") or {}).get("Networks") or {}
    state = proxy.get("State") or {}
    host_config = proxy.get("HostConfig") or {}
    require(
        proxy.get("Name") == "/" + PROXY_NAME
        and labels.get("com.docker.compose.project") == "pcp-g1-pilot"
        and labels.get("com.docker.compose.service") == PROXY_SERVICE
        and labels.get("pcp.scope") == "g1-pilot-parked"
        and config.get("User") == "65534:65534"
        and config.get("Entrypoint") == ["python3"]
        and config.get("Cmd") == ["-c", cmd[-1]]
        and (config.get("Env") or []).count("G1_EGRESS_ROLE=provider") == 1
        and config.get("Image") == "python:3.13-alpine"
        and state.get("Running") is False
        and state.get("OOMKilled") is False
        and not state.get("Error")
        and state.get("ExitCode") == 1
        and host_config.get("Privileged") is False
        and host_config.get("ReadonlyRootfs") is True
        and set(net) == EXPECTED_NETS
        and len(mounts) == 1
        and mounts[0].get("Source") ==
            str(PCP / "deploy/g1/egress_connect_proxy.py")
        and mounts[0].get("Destination") == "/g1/egress_connect_proxy.py"
        and mounts[0].get("RW") is False,
        "g1_direct_existing_stopped_proxy_identity_or_scope_changed",
    )
    elapsed = require_expired_window(state)
    # An unrelated source branch/container/network/volume may never be adopted.
    listings = output([
        "docker", "ps", "--all", "--filter",
        "label=com.docker.compose.project=pcp-g1-pilot",
        "--format", "{{.ID}}",
    ]).splitlines()
    require(len(listings) == 1 and container_id.startswith(listings[0]),
            "g1_direct_unexpected_pilot_containers_present")
    for kind, name in recovery.DOCKER_NAMES:
        if kind == "network" and name in EXPECTED_NETS:
            continue
        require(command(["docker", kind, "inspect", name]).returncode != 0,
                "g1_direct_other_pilot_resources_unexpected")
    for name in EXPECTED_NETS:
        network = inspect("network", name)
        peers = network.get("Containers") or {}
        connected = {value.get("Name") for value in peers.values()
                     if isinstance(value, dict)}
        # Docker releases a stopped container's network endpoints. Require
        # zero peers or ONLY this exact previously-attested proxy; accepting
        # another project/DDEV container here would be a scope escape.
        require(network.get("Name") == name and
                network.get("Internal") is
                    (name == "pcp-g1-pilot-direct-control")
                and connected.issubset({PROXY_NAME}),
                "g1_direct_existing_network_peer_or_scope_drift")
    return match.group(1), container_id, str(round(elapsed, 1))


def persist(value: dict[str, Any], *, first: bool) -> None:
    os.umask(0o077)
    if first:
        with EVIDENCE.open("x", encoding="utf-8") as file:
            json.dump(value, file, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        return
    tmp = ROOT / "direct-t01-expired-proxy-evidence.tmp"
    with tmp.open("x", encoding="utf-8") as file:
        json.dump(value, file, sort_keys=True)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, EVIDENCE)


def parse_gate(response: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        items = [
            json.loads(line) for line in response.stdout.splitlines()
            if line.strip().startswith("{") and len(line) < 10000
        ]
        require(len(items) == 1 and isinstance(items[0], dict),
                "g1_direct_preflight_response_invalid")
        data = items[0]
        allowed_keys = {
            "auth_file_readable", "codex_login_status_pass", "proxy_dns_pass",
            "github_connect_denied", "chatgpt_connect_allowed",
            "tls_verified", "failed_at",
        }
        require(set(data) == allowed_keys
                and data["failed_at"] in set(ALLOWED_STAGES) | {"NONE"}
                and all(isinstance(data[k], bool) for k in allowed_keys - {"failed_at"}),
                "g1_direct_preflight_unexpected_schema")
        data["pass"] = (
            response.returncode == 0 and data["failed_at"] == "NONE"
            and all(data[k] for k in allowed_keys - {"failed_at"})
        )
        return data
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise Stop("g1_direct_preflight_response_invalid") from exc


def execute(expected_sha: str) -> dict[str, Any]:
    old = import_script("scripts/g1-pilot-direct-first-turn.py", "g1_original")
    recovery = import_script(
        "scripts/g1-pilot-direct-preserved-continuation.py", "g1_second")
    version, proxy_id, lifetime = attest_existing(expected_sha, old, recovery)
    contract = command(["python3", str(PCP / "scripts/g1-pilot-source-contract.py")],
                       timeout=25)
    require(contract.returncode == 0
            and '"PASS_G1_PILOT_SOURCE_PARKED"' in contract.stdout,
            "g1_direct_source_contract_not_parked")
    persist({
        "state": "started", "lane": "direct", "model_calls": 0,
        "job_reused": True, "proxy_reused": True, "prior_proxy_lifetime_seconds": lifetime,
    }, first=True)
    # START the SAME stopped exact container (not docker run/up/recreate).
    start = command(["docker", "container", "start", PROXY_NAME], timeout=25)
    require(start.returncode == 0, "g1_direct_same_proxy_start_failed")
    after = inspect("container", PROXY_NAME)
    require(after.get("Id") == proxy_id
            and (after.get("State") or {}).get("Running") is True
            and set((after.get("NetworkSettings") or {}).get("Networks") or {}) ==
                EXPECTED_NETS,
            "g1_direct_same_proxy_not_running_on_exact_network")
    for name in EXPECTED_NETS:
        network = inspect("network", name)
        peers = network.get("Containers") or {}
        require(
            {v.get("Name") for v in peers.values() if isinstance(v, dict)}
                == {PROXY_NAME},
            "g1_direct_restarted_proxy_foreign_network_peer",
        )
    env = recovery.prepared_env(version, old)
    gate = recovery.compose(
        env, "run", "--rm", "--no-deps", "-T", "--entrypoint", "python3",
        "direct", "-c", PREFLIGHT, timeout=75,
    )
    parsed = parse_gate(gate)
    if not parsed["pass"]:
        persist({
            "state": "preflight_stopped", "lane": "direct", "model_calls": 0,
            "failed_at": parsed["failed_at"],
            "auth_file_readable": parsed["auth_file_readable"],
            "codex_login_status_pass": parsed["codex_login_status_pass"],
            "proxy_dns_pass": parsed["proxy_dns_pass"],
            "github_connect_denied": parsed["github_connect_denied"],
            "chatgpt_connect_allowed": parsed["chatgpt_connect_allowed"],
            "tls_verified": parsed["tls_verified"],
            "proxy_reused": True,
        }, first=False)
        raise Stop("g1_direct_classified_container_preflight_failed")
    # A model call is permitted only after real positive-and-negative live
    # network + device auth proof in the SAME direct Codex service.
    persist({
        "state": "model_launched", "lane": "direct", "model_calls": 1,
        "model": old.MODEL, "reasoning": old.EFFORT, "proxy_reused": True,
    }, first=False)
    started = time.monotonic()
    response = recovery.compose(
        env, *old.codex_argv(), timeout=MAX_MODEL_SECONDS,
    )
    elapsed = round(time.monotonic() - started, 1)
    observed = old.summarise_codex(response)
    scoped, paths = old.code_scope()
    class_file = recovery.DIRECT / (
        "web/modules/custom/pcp_f2_fixture/src/WindowOverlapDetector.php"
    )
    unit_file = recovery.DIRECT / (
        "web/modules/custom/pcp_f2_fixture/tests/src/Unit/WindowOverlapDetectorTest.php"
    )
    material = (
        class_file.is_file() and unit_file.is_file()
        and "function intersectionMinutes(" in class_file.read_text(encoding="utf-8")
        and "intersectionMinutes(" in unit_file.read_text(encoding="utf-8")
    )
    accepted = (
        response.returncode == 0 and observed["terminal"] == "turn.completed"
        and scoped and material
        and command(["git", "-C", str(recovery.DIRECT), "diff", "--check"]).returncode == 0
        and command(["git", "-C", str(recovery.DIRECT), "diff", "--cached",
                     "--check"]).returncode == 0
    )
    commit_sha = ""
    if accepted:
        require(command([
            "git", "-C", str(recovery.DIRECT), "add", "--",
            *sorted(old.ALLOW)
        ]).returncode == 0, "g1_direct_approved_git_stage_failed")
        commit = command([
            "git", "-C", str(recovery.DIRECT),
            "-c", "user.name=PCP G1 Trial",
            "-c", "user.email=pcp-g1-trial@localhost",
            "commit", "-m", "feat(g1-t01): count same-day intersection minutes",
        ])
        require(commit.returncode == 0, "g1_direct_approved_local_commit_failed")
        commit_sha = output(["git", "-C", str(recovery.DIRECT), "rev-parse", "HEAD"])
    evidence = {
        "state": "completed", "lane": "direct", "proxy_reused": True,
        "model_calls": 1, "model": old.MODEL, "reasoning": old.EFFORT,
        "model_elapsed_seconds": elapsed,
        "model_returncode": observed["returncode"],
        "model_terminal": observed["terminal"],
        "token_usage": observed["usage"], "source_sha": SEED,
        "scope_ok": scoped, "material_change": material,
        "changed_paths": paths if set(paths).issubset(old.ALLOW)
                         else ["UNAPPROVED_SCOPE"],
        "local_commit": commit_sha,
        "github_pr": "NOT_CREATED", "hosted_ci": "NOT_CHECKED",
        "accepted_pr": False, "pcp_lane_model_calls": 0,
    }
    persist(evidence, first=False)
    return {
        "status": ("PASS_G1_DIRECT_CODE_READY_FOR_CI"
                   if accepted else "STOP_G1_DIRECT_CODING_UNACCEPTED"),
        **{k: v for k, v in evidence.items()
           if k not in {"state", "source_sha"}},
        "no_new_workspace": True, "no_new_job": True,
        "no_automatic_retry": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-pcp-sha", required=True)
    args = parser.parse_args()
    try:
        result = execute(args.expected_pcp_sha)
        code = 0 if result["status"].startswith("PASS_") else 2
    except (Stop, OSError, PermissionError, FileExistsError) as exc:
        result = {
            "status": "STOP_G1_DIRECT_EXISTING_PROXY_CONTINUATION",
            "blocker": str(exc) if isinstance(exc, Stop)
                       else "g1_direct_evidence_or_container_unavailable",
            "no_new_workspace": True, "no_new_job": True,
            "original_journals_preserved": True,
            "no_automatic_retry": True,
            "model_calls": 0,
        }
        try:
            row = json.loads(EVIDENCE.read_text(encoding="utf-8"))
            if row.get("state") in {"model_launched", "completed"}:
                result["model_calls"] = 1
            if row.get("state") == "preflight_stopped":
                result["failed_at"] = row.get("failed_at")
                for key in (
                    "auth_file_readable", "codex_login_status_pass",
                    "proxy_dns_pass", "github_connect_denied",
                    "chatgpt_connect_allowed", "tls_verified",
                ):
                    result[key] = row.get(key)
        except (ValueError, OSError):
            pass
        code = 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
