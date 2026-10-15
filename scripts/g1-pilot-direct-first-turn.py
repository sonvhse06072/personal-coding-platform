#!/usr/bin/env python3
"""ONE owner-invoked G1-T01 direct Codex turn, preserving every STOP.

This is the fair-control lane FIRST. The accepted G1 smoke job is never
modified. It runs Codex only in a new, isolated Docker container with a fresh
direct workspace, its already-authorized direct CODEX_HOME, and an independent
provider CONNECT proxy. There is NO GitHub credential, Executor or Docker
socket inside the Codex container. A successful code diff is committed locally;
GitHub CI/PR and PCP-lane parity remain separate, explicit acceptance gates.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import time
from typing import Any

ROOT = Path.home() / ".pcp-g1-pilot"
PCP = Path(__file__).resolve().parents[1]
OLD_SMOKE = Path.home() / ".pcp-g1-smoke"
SEED = "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
REPOSITORY = "sonvhse06072/pcp-g0-fullpath-fixture"
BRANCH = "ai/g1-direct-t01-20261015"
WS = ROOT / "direct-workspace"
EVIDENCE = ROOT / "direct-t01-evidence.json"
PROXY_NAME = "pcp-g1-pilot-direct-proxy-operator"
PROXY_SERV = "g1-pilot-direct-proxy"
APP_IMAGE = "pcp-g1-pilot-runtime"
MODEL = "gpt-6-luna"
EFFORT = "medium"
LIMIT_SECONDS = 1200
ALLOW = frozenset({
    "web/modules/custom/pcp_f2_fixture/src/WindowOverlapDetector.php",
    "web/modules/custom/pcp_f2_fixture/tests/src/Unit/WindowOverlapDetectorTest.php",
})
TASK = (
    "G1-T01 independent coding trial. Implement a public method "
    "intersectionMinutes(int $start, int $end, int $otherStart, int "
    "$otherEnd): int on WindowOverlapDetector. For valid nonempty same-day "
    "half-open minute ranges (0 <= start < end <= 1440), return the number "
    "of shared minutes. Return zero for disjoint or endpoint-touching "
    "ranges and for invalid, empty, out-of-day or overnight ranges. "
    "Preserve intersects() semantics exactly. Add focused PHPUnit unit "
    "tests for partial overlap, containment, equal intervals, symmetry, "
    "touching, disjoint, zero/1440 boundaries, invalid and overnight. "
    "Only edit the WindowOverlapDetector.php implementation and its "
    "tests/src/Unit/WindowOverlapDetectorTest.php file. No dependencies, "
    "schema, network, DDEV hooks or configuration. Do not commit or push; "
    "do not request privileges or use Docker, host services or GitHub. "
    "Finish this one coding turn with a concise implementation summary."
)


class Stop(RuntimeError):
    """Sanitized G1 code, never raw Docker/Codex/auth stderr."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise Stop(code)


def invoke(argv: list[str], *, timeout: int = 30,
           env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv, input=None, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=timeout,
            env=env, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("g1_direct_command_unavailable_or_timeout") from exc


def read(argv: list[str], *, timeout: int = 20,
         env: dict[str, str] | None = None) -> str:
    result = invoke(argv, timeout=timeout, env=env)
    require(result.returncode == 0, "g1_direct_readonly_command_failed")
    return result.stdout.strip()


def identity(expected: str) -> tuple[str, Path, Path]:
    # Caller pins the reviewed MERGE SHA, which is unknown when source PR
    # is authored. Require exact clean main and a 40-hex argument.
    require(re.fullmatch(r"[0-9a-f]{40}", expected) is not None,
            "g1_direct_unreviewed_pcp_sha")
    require(os.geteuid() != 0, "g1_direct_no_root_operator")
    require(
        read(["git", "-C", str(PCP), "rev-parse", "HEAD"]) == expected
        and read(["git", "-C", str(PCP), "branch", "--show-current"]) == "main"
        and not read(["git", "-C", str(PCP), "status", "--porcelain"]),
        "g1_direct_pcp_checkout_not_clean_exact_main",
    )
    require(ROOT.is_dir() and not ROOT.is_symlink()
            and ROOT.stat().st_uid == os.geteuid(),
            "g1_direct_original_auth_root_missing")
    require(not EVIDENCE.exists() and not EVIDENCE.is_symlink()
            and not WS.exists() and not WS.is_symlink(),
            "g1_direct_already_started_or_workspace_not_fresh")
    for lane in ("pcp", "direct"):
        auth = ROOT / "auth" / lane
        credential = auth / "auth.json"
        require(
            auth.is_dir() and not auth.is_symlink()
            and auth.stat().st_uid == os.geteuid()
            and credential.is_file() and not credential.is_symlink()
            and credential.stat().st_uid == os.geteuid()
            and (credential.stat().st_mode & 0o077) == 0,
            "g1_direct_isolated_auth_missing_or_unsafe",
        )
    require(
        (ROOT / "auth" / "pcp").resolve()
        != (ROOT / "auth" / "direct").resolve(),
        "g1_direct_shared_auth_denied",
    )
    seed = OLD_SMOKE / "source"
    require(seed.is_dir() and not seed.is_symlink()
            and read(["git", "-C", str(seed), "rev-parse", "HEAD"]) == SEED
            and not read(["git", "-C", str(seed), "status", "--porcelain"]),
            "g1_direct_immutable_fixture_source_not_available",
    )
    require(not (ROOT / "source").exists()
            and not (ROOT / "workspaces").exists(),
            "g1_direct_pcp_lane_untouched_required")
    version = read(["codex", "--version"])
    match = re.fullmatch(r"codex-cli (\d+\.\d+\.\d+)", version)
    require(match is not None, "g1_direct_codex_cli_version_unverifiable")
    docker = read(["docker", "context", "inspect"])
    try:
        contexts = json.loads(docker)
        host = contexts[0]["Endpoints"]["docker"]["Host"]
        require(len(contexts) == 1 and host.startswith("unix://")
                and Path(host[7:]).resolve() == Path("/var/run/docker.sock").resolve(),
                "g1_direct_docker_context_not_local")
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise Stop("g1_direct_docker_context_invalid") from exc
    require(read(["docker", "ps", "-a", "--filter",
                  "label=com.docker.compose.project=pcp-g1-pilot",
                  "--format", "{{.ID}}"]) == "",
            "g1_direct_existing_pilot_container_denied")
    for kind, name in (
        ("network", "pcp-g1-pilot-control"),
        ("network", "pcp-g1-pilot-provider-egress"),
        ("network", "pcp-g1-pilot-github-egress"),
        ("network", "pcp-g1-pilot-direct-control"),
        ("network", "pcp-g1-pilot-direct-provider-egress"),
        ("volume", "pcp-g1-pilot-postgres"),
        ("volume", "pcp-g1-pilot-cache"),
        ("container", "ddev-pcp-g1-codex-pilot-web"),
        ("container", "ddev-pcp-g1-codex-pilot-db"),
        ("container", "ddev-pcp-g1-codex-direct-web"),
        ("container", "ddev-pcp-g1-codex-direct-db"),
    ):
        existing = invoke(["docker", kind, "inspect", name], timeout=15)
        require(existing.returncode != 0,
                "g1_direct_disposable_resource_name_in_use")
    return match.group(1), seed, ROOT / "auth" / "direct"


def compose_env(version: str) -> dict[str, str]:
    # Placeholder values serve Compose variable interpolation only for the
    # PARKED services that this direct-only operator NEVER starts. They are
    # NOT functional broker or GitHub credentials.
    secrets_dir = ROOT / "inactive"
    secrets_dir.mkdir(mode=0o700, exist_ok=False)
    token_file = secrets_dir / "github-disabled"
    token_file.write_text("DISABLED_FOR_DIRECT_CONTROL_ONLY\n", encoding="utf-8")
    os.chmod(token_file, 0o600)
    return {
        **os.environ,
        "PCP_G1_PILOT_ROOT": str(ROOT),
        "PCP_G1_PILOT_REPO_ROOT": str(PCP),
        "PCP_G1_PILOT_UID": str(os.geteuid()),
        "PCP_G1_PILOT_GID": str(os.getegid()),
        "PCP_G1_PILOT_SOCKET_GID": str(Path("/var/run/docker.sock").stat().st_gid),
        "PCP_G1_PILOT_CODEX_VERSION": version,
        "PCP_G1_PILOT_DB_PASSWORD": secrets.token_hex(24),
        "PCP_G1_PILOT_ROUTER_TOKEN": secrets.token_urlsafe(32),
        "PCP_G1_PILOT_INTERNAL_TOKEN": secrets.token_urlsafe(32),
        "PCP_G1_PILOT_RUNTIME_TOKEN": secrets.token_urlsafe(32),
        "PCP_G1_PILOT_GITHUB_TOKEN_FILE": str(token_file),
        "PCP_G1_PILOT_PCP_CODEX_AUTH_DIR": str(ROOT / "auth" / "pcp"),
        "PCP_G1_PILOT_DIRECT_CODEX_AUTH_DIR": str(ROOT / "auth" / "direct"),
        "PCP_G1_PILOT_DIRECT_WORKSPACE_DIR": str(WS),
        "PCP_G1_PILOT_RUNTIME_IMAGE": APP_IMAGE,
        "GIT_TERMINAL_PROMPT": "0",
    }


def compose(env: dict[str, str], *args: str,
            timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return invoke([
        "docker", "compose",
        "--project-name", "pcp-g1-pilot",
        "--file", str(PCP / "deploy/g1/compose.pilot.parked.yml"),
        "--file", str(PCP / "deploy/g1/compose.pilot.egress.parked.yml"),
        "--profile", "g1-pilot-parked",
        *args,
    ], env=env, timeout=timeout)


def checked_compose(env: dict[str, str], *args: str, timeout: int = 120) -> str:
    result = compose(env, *args, timeout=timeout)
    require(result.returncode == 0, "g1_direct_compose_operation_failed")
    return result.stdout.strip()


def create_workspace(seed: Path) -> None:
    result = invoke(["git", "clone", "--no-local", "--no-checkout",
                     str(seed), str(WS)], timeout=180)
    require(result.returncode == 0, "g1_direct_clone_failed_preserve_workspace")
    require(read(["git", "-C", str(WS), "rev-parse", "HEAD"]) == SEED,
            "g1_direct_seed_commit_drift")
    require(invoke(["git", "-C", str(WS), "checkout", "-b", BRANCH, SEED]).returncode == 0,
            "g1_direct_branch_checkout_failed")
    require(invoke(["git", "-C", str(WS), "remote", "set-url", "origin",
                    f"https://github.com/{REPOSITORY}.git"]).returncode == 0,
            "g1_direct_origin_assignment_failed")
    require(read(["git", "-C", str(WS), "branch", "--show-current"]) == BRANCH
            and not read(["git", "-C", str(WS), "status", "--porcelain"]),
            "g1_direct_workspace_not_clean")


def save(data: dict[str, Any], *, initial: bool) -> None:
    os.umask(0o077)
    if initial:
        with EVIDENCE.open("x", encoding="utf-8") as file:
            json.dump(data, file, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
    else:
        temp = ROOT / "direct-t01-evidence.tmp"
        with temp.open("x", encoding="utf-8") as file:
            json.dump(data, file, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, EVIDENCE)


def proxy_argv() -> tuple[str, ...]:
    # Direct provider proxy runs for <= one model window. Only fixed source,
    # single service, fixed aliases, and unique new exact container identity.
    startup = (
        "import asyncio,importlib.util;"
        "p='/g1/egress_connect_proxy.py';"
        "s=importlib.util.spec_from_file_location('g1_ep',p);"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        "asyncio.run(asyncio.wait_for(m.serve('provider'),timeout=1200))"
    )
    return (
        "run", "-d", "--no-deps", "--use-aliases",
        "--name", PROXY_NAME, "--entrypoint", "python3",
        PROXY_SERV, "-c", startup,
    )


def direct_container_gate_argv() -> tuple[str, ...]:
    """Check mounted auth and live proxy in the exact direct Docker network.

    No model call; does not expose token contents or send HTTP payloads.
    """
    probe = (
        "import socket,ssl,subprocess;"
        "p=subprocess.run(['codex','login','status'],capture_output=True,"
        "text=True,timeout=15,check=False);"
        "assert p.returncode==0 and 'Logged in using ChatGPT' in p.stdout;"
        "connect=lambda h: socket.create_connection(('g1-pilot-direct-proxy',"
        "3128),timeout=12);"
        "s=connect('api.github.com');s.sendall(b'CONNECT api.github.com:443 "
        "HTTP/1.1\\r\\nHost: api.github.com:443\\r\\n\\r\\n');"
        "response=s.recv(256);assert response.startswith(b'HTTP/1.1 403');s.close();"
        "s=connect('chatgpt.com');s.sendall(b'CONNECT chatgpt.com:443 "
        "HTTP/1.1\\r\\nHost: chatgpt.com:443\\r\\n\\r\\n');"
        "response=s.recv(256);assert response.startswith(b'HTTP/1.1 200');"
        "s=ssl.create_default_context().wrap_socket(s,server_hostname='chatgpt.com');"
        "assert s.version() is not None;s.close();"
        "print('G1_DIRECT_CONTAINER_AUTH_AND_EGRESS=PASS')"
    )
    return (
        "run", "--rm", "--no-deps", "-T",
        "--entrypoint", "python3", "direct", "-c", probe,
    )


def codex_argv() -> tuple[str, ...]:
    return (
        "run", "--rm", "--no-deps", "-T", "--entrypoint", "codex",
        "direct", "exec", "--json",
        "--sandbox", "workspace-write",
        "--config", 'approval_policy="never"',
        "--config", "features.memories=false",
        "--config", "memories.use_memories=false",
        "--config", "memories.generate_memories=false",
        "--config", "sandbox_workspace_write.network_access=false",
        "--cd", "/pilot/direct-workspace",
        "--model", MODEL, "--config", 'model_reasoning_effort="medium"',
        "--output-last-message", "/tmp/g1-direct-message",
        TASK,
    )


def check_proxy_identity() -> None:
    raw = read(["docker", "container", "inspect", PROXY_NAME])
    try:
        data = json.loads(raw)
        require(len(data) == 1, "g1_direct_proxy_inspect_invalid")
        doc = data[0]
        label = (doc.get("Config") or {}).get("Labels") or {}
        nets = (doc.get("NetworkSettings") or {}).get("Networks") or {}
        require(
            label.get("com.docker.compose.project") == "pcp-g1-pilot"
            and label.get("com.docker.compose.service") == PROXY_SERV
            and label.get("pcp.scope") == "g1-pilot-parked"
            and (doc.get("State") or {}).get("Running") is True
            and (doc.get("HostConfig") or {}).get("Privileged") is False
            and set(nets) == {
                "pcp-g1-pilot-direct-control",
                "pcp-g1-pilot-direct-provider-egress",
            },
            "g1_direct_proxy_identity_or_network_drift",
        )
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        raise Stop("g1_direct_proxy_inspect_unavailable") from exc


def summarise_codex(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    usage: dict[str, int] = {}
    terminal = "UNOBSERVED"
    for line in result.stdout.splitlines():
        if len(line) > 32768 or not line.startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except ValueError:
            continue
        if evt.get("type") == "turn.completed":
            terminal = "turn.completed"
            raw_usage = evt.get("usage") or {}
            for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
                value = raw_usage.get(key)
                if isinstance(value, int) and 0 <= value <= 10000000:
                    usage[key] = value
        elif evt.get("type") == "turn.failed":
            terminal = "turn.failed"
    return {"returncode": result.returncode, "terminal": terminal, "usage": usage}


def code_scope() -> tuple[bool, list[str]]:
    require(read(["git", "-C", str(WS), "branch", "--show-current"]) == BRANCH
            and read(["git", "-C", str(WS), "rev-parse", "HEAD"]) == SEED,
            "g1_direct_source_or_branch_changed")
    changed = set(read(["git", "-C", str(WS), "diff", "--name-only"]).splitlines())
    changed.update(read(["git", "-C", str(WS), "diff", "--cached",
                         "--name-only"]).splitlines())
    changed.update(read(["git", "-C", str(WS), "ls-files", "--others",
                         "--exclude-standard"]).splitlines())
    # Git status normally omits files listed in .gitignore. An agent must not
    # hide unexpected new files inside ignored directories.
    changed.update(read(["git", "-C", str(WS), "ls-files", "--others",
                         "--ignored", "--exclude-standard"]).splitlines())
    # The task requires both a new method AND focused tests, not just an
    # apparently successful Codex turn with zero or one changed file.
    return changed == ALLOW, sorted(changed)


def execute(expected: str) -> dict[str, Any]:
    version, seed, _auth = identity(expected)
    # The pure checker includes BOTH PARKED manifest(s) and the exact model
    # registry, safe networks, diff budget, private auth scope.
    script = PCP / "scripts/g1-pilot-source-contract.py"
    result = invoke(["python3", str(script)], timeout=20)
    require(result.returncode == 0 and
            '"PASS_G1_PILOT_SOURCE_PARKED"' in result.stdout,
            "g1_direct_pilot_source_contract_not_parked")
    started = time.monotonic()
    save({
        "state": "started", "lane": "direct", "seed": SEED,
        "model": MODEL, "effort": EFFORT, "attempts": 0,
    }, initial=True)
    create_workspace(seed)
    env = compose_env(version)
    checked_compose(env, "config", "--quiet", timeout=50)
    # Building the image is an operator-only codepath: no model execution.
    checked_compose(env, "build", "runtime", timeout=1500)
    require(read(["docker", "image", "inspect", APP_IMAGE, "--format",
                  "{{.Id}}"]).startswith("sha256:"),
            "g1_direct_pinned_runtime_image_not_available")
    # The role-scoped proxy has no OAuth/GitHub secrets and no published ports.
    checked_compose(env, *proxy_argv(), timeout=90)
    check_proxy_identity()
    # The same private direct container must see its independent Codex auth,
    # refuse an unapproved GitHub CONNECT, and complete an authenticated TLS
    # handshake to the exact approved ChatGPT hostname through the proxy.
    # This gate makes NO Codex model call and does not disclose credentials.
    gate = compose(env, *direct_container_gate_argv(), timeout=65)
    require(gate.returncode == 0 and
            "G1_DIRECT_CONTAINER_AUTH_AND_EGRESS=PASS" in gate.stdout,
            "g1_direct_container_auth_or_proxy_gate_failed")
    # ONE model call, no automatic retries even for auth/provider failures.
    save({
        "state": "model_launched", "lane": "direct", "seed": SEED,
        "model": MODEL, "effort": EFFORT, "attempts": 1,
    }, initial=False)
    model_started = time.monotonic()
    launched = compose(env, *codex_argv(), timeout=LIMIT_SECONDS + 90)
    model_elapsed = round(time.monotonic() - model_started, 1)
    observed = summarise_codex(launched)
    scope_ok, changed = code_scope()
    class_file = WS / "web/modules/custom/pcp_f2_fixture/src/WindowOverlapDetector.php"
    unit_file = WS / "web/modules/custom/pcp_f2_fixture/tests/src/Unit/WindowOverlapDetectorTest.php"
    material = (
        class_file.is_file() and unit_file.is_file()
        and "function intersectionMinutes(" in class_file.read_text(encoding="utf-8")
        and "intersectionMinutes(" in unit_file.read_text(encoding="utf-8")
    )
    approved = (
        observed["returncode"] == 0
        and observed["terminal"] == "turn.completed"
        and scope_ok and material
        and invoke(["git", "-C", str(WS), "diff", "--check"]).returncode == 0
        and invoke(["git", "-C", str(WS), "diff", "--cached", "--check"]).returncode == 0
    )
    commit = ""
    if approved:
        require(invoke(["git", "-C", str(WS), "add", "--", *sorted(ALLOW)]).returncode == 0,
                "g1_direct_scoped_git_add_failed")
        commit_proc = invoke([
            "git", "-C", str(WS), "-c", "user.name=PCP G1 Trial",
            "-c", "user.email=pcp-g1-trial@localhost",
            "commit", "-m", "feat(g1-t01): count same-day intersection minutes",
        ])
        require(commit_proc.returncode == 0, "g1_direct_local_commit_failed")
        commit = read(["git", "-C", str(WS), "rev-parse", "HEAD"])
    evidence = {
        "state": "completed", "lane": "direct", "model": MODEL,
        "effort": EFFORT, "seed": SEED, "attempts": 1,
        "model_calls": 1, "elapsed_seconds": round(time.monotonic() - started, 1),
        "model_elapsed_seconds": model_elapsed,
        "setup_elapsed_seconds": round(model_started - started, 1),
        "returncode": observed["returncode"],
        "terminal": observed["terminal"],
        "token_usage": observed["usage"],
        "scope_ok": scope_ok,
        "changed_paths": changed if set(changed).issubset(ALLOW) else ["UNAPPROVED_SCOPE"],
        "local_commit": commit,
        "github_pr": "NOT_CREATED",
        "hosted_ci": "NOT_CHECKED",
        "accepted": False,
        "pcp_lane_model_calls": 0,
        "old_smoke_job_unchanged": True,
        "ready_for_autonomous_e2e": False,
    }
    save(evidence, initial=False)
    return {
        "status": ("PASS_G1_DIRECT_CODE_READY_FOR_CI"
                   if approved else "STOP_G1_DIRECT_TURN_UNACCEPTED"),
        **{key: evidence[key] for key in (
            "lane", "model_calls", "elapsed_seconds",
            "model_elapsed_seconds", "setup_elapsed_seconds", "returncode",
            "terminal", "token_usage", "scope_ok", "changed_paths",
            "local_commit", "github_pr", "hosted_ci", "accepted",
            "pcp_lane_model_calls", "ready_for_autonomous_e2e",
        )},
        "no_automatic_retry": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-pcp-sha", required=True)
    args = parser.parse_args()
    try:
        result = execute(args.expected_pcp_sha)
        code = 0 if result["status"].startswith("PASS_") else 2
    except (Stop, PermissionError, FileExistsError, OSError) as exc:
        result = {
            "status": "STOP_G1_DIRECT_ONE_SHOT",
            "blocker": str(exc) if isinstance(exc, Stop)
                       else "g1_direct_workspace_or_evidence_unavailable",
            "model_calls": "UNDETERMINED_CHECK_PRIVATE_EVIDENCE",
            "old_smoke_job_unchanged": True,
            "no_automatic_retry": True,
        }
        code = 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
