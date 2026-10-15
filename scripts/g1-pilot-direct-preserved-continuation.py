#!/usr/bin/env python3
"""G1 direct recovery: exactly ONE evidence-backed continuation on SAME workspace.

The first operator STOPPED in Docker Compose build before model launch.
Preserve the consumed original journal and worktree. A separate, exclusive
continuation marker enforces one build + <=one model turn without blind retry.
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

PCP = Path(__file__).resolve().parents[1]
ROOT = Path.home() / ".pcp-g1-pilot"
DIRECT = ROOT / "direct-workspace"
PREVIOUS = ROOT / "direct-t01-evidence.json"
NEW = ROOT / "direct-t01-build-continuation-evidence.json"
SMOKE_SOURCE = Path.home() / ".pcp-g1-smoke" / "source"
SEED = "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
DIRECT_IMAGE = "pcp-g1-pilot-direct-codex"
DISABLED_GITHUB = "DISABLED_FOR_DIRECT_CONTROL_ONLY\n"
MODEL_VERSION_LABEL = "org.opencontainers.image.pcp.codex-version"
SCOPE_LABEL = "org.opencontainers.image.pcp.g1-scope"
DOCKER_NAMES = (
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
)
COMPOSE_FILES = (
    "deploy/g1/compose.pilot.parked.yml",
    "deploy/g1/compose.pilot.egress.parked.yml",
    "deploy/g1/compose.pilot.direct-build.parked.yml",
)


class Stop(RuntimeError):
    """Error text is a stable category ONLY. Never include stderr/credentials."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise Stop(code)


def previous_operator():
    path = PCP / "scripts/g1-pilot-direct-first-turn.py"
    require(path.is_file() and not path.is_symlink(),
            "g1_direct_original_operator_source_missing")
    spec = importlib.util.spec_from_file_location("g1_first_direct_turn", path)
    require(spec is not None and spec.loader is not None,
            "g1_direct_original_operator_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(argv: list[str], *, env: dict[str, str] | None = None,
        timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, check=False,
            stdin=subprocess.DEVNULL, env=env, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("g1_direct_bounded_command_unavailable_or_timeout") from exc


def read(argv: list[str], *, timeout: int = 20) -> str:
    proc = run(argv, timeout=timeout)
    require(proc.returncode == 0, "g1_direct_readonly_probe_failed")
    return proc.stdout.strip()


def assert_original(expected_sha: str, old) -> tuple[str, Path]:
    require(re.fullmatch(r"[0-9a-f]{40}", expected_sha) is not None,
            "g1_direct_unpinned_pcp_main_sha")
    require(os.geteuid() != 0, "g1_direct_unprivileged_operator_required")
    require(
        read(["git", "-C", str(PCP), "rev-parse", "HEAD"]) == expected_sha
        and read(["git", "-C", str(PCP), "branch", "--show-current"]) == "main"
        and not read(["git", "-C", str(PCP), "status", "--porcelain"]),
        "g1_direct_pcp_main_not_exact_clean",
    )
    require(ROOT.is_dir() and not ROOT.is_symlink()
            and ROOT.stat().st_uid == os.geteuid(),
            "g1_direct_original_root_identity_changed")
    require(not NEW.exists() and not NEW.is_symlink(),
            "g1_direct_build_continuation_already_attempted")
    require(PREVIOUS.is_file() and not PREVIOUS.is_symlink()
            and PREVIOUS.stat().st_uid == os.geteuid(),
            "g1_direct_original_stop_journal_missing")
    try:
        row = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise Stop("g1_direct_original_stop_journal_invalid") from exc
    require(
        row.get("state") == "started"
        and row.get("lane") == "direct"
        and row.get("seed") == SEED
        and row.get("model") == old.MODEL
        and row.get("effort") == old.EFFORT
        and row.get("attempts") == 0
        and not (ROOT / "direct-t01-evidence.tmp").exists(),
        "g1_direct_not_exact_pre_model_stop",
    )
    require(
        DIRECT.is_dir() and not DIRECT.is_symlink()
        and DIRECT.resolve() == DIRECT
        and read(["git", "-C", str(DIRECT), "rev-parse", "--show-toplevel"])
            == str(DIRECT)
        and read(["git", "-C", str(DIRECT), "rev-parse", "HEAD"]) == SEED
        and read(["git", "-C", str(DIRECT), "branch", "--show-current"])
            == old.BRANCH
        and not read(["git", "-C", str(DIRECT), "status", "--porcelain"]),
        "g1_direct_preserved_workspace_dirty_or_wrong_seed",
    )
    require(
        SMOKE_SOURCE.is_dir() and not SMOKE_SOURCE.is_symlink()
        and read(["git", "-C", str(SMOKE_SOURCE), "rev-parse", "HEAD"]) == SEED,
        "g1_direct_old_smoke_source_not_immutable",
    )
    require(not (ROOT / "source").exists()
            and not (ROOT / "workspaces").exists(),
            "g1_direct_pcp_lane_was_modified",
    )
    for lane in ("pcp", "direct"):
        folder = ROOT / "auth" / lane
        token = folder / "auth.json"
        require(folder.is_dir() and not folder.is_symlink()
                and folder.stat().st_uid == os.geteuid()
                and token.is_file() and not token.is_symlink()
                and token.stat().st_uid == os.geteuid()
                and not (token.stat().st_mode & 0o077),
                "g1_direct_auth_root_missing_or_unsafe")
    require(
        (ROOT / "auth/pcp").resolve() != (ROOT / "auth/direct").resolve(),
        "g1_direct_codex_auth_must_be_separate",
    )
    disabled = ROOT / "inactive" / "github-disabled"
    require(
        disabled.is_file() and not disabled.is_symlink()
        and disabled.stat().st_uid == os.geteuid()
        and not (disabled.stat().st_mode & 0o077)
        and disabled.read_text(encoding="utf-8") == DISABLED_GITHUB,
        "g1_direct_disabled_github_marker_changed",
    )
    require(not run(["docker", "image", "inspect", DIRECT_IMAGE]).returncode == 0,
            "g1_direct_new_image_tag_already_exists")
    require(not run(["docker", "image", "inspect", old.APP_IMAGE]).returncode == 0,
            "g1_direct_old_runtime_image_not_absent")
    require(read([
        "docker", "ps", "-a", "--filter",
        "label=com.docker.compose.project=pcp-g1-pilot", "--format", "{{.ID}}",
    ]) == "", "g1_direct_foreign_pilot_container_already_exists")
    for kind, name in DOCKER_NAMES:
        require(run(["docker", kind, "inspect", name]).returncode != 0,
                "g1_direct_unexpected_existing_pilot_docker_resource")
    context = json.loads(read(["docker", "context", "inspect"]))
    try:
        host = context[0]["Endpoints"]["docker"]["Host"]
        require(len(context) == 1 and host.startswith("unix://")
                and Path(host[7:]).resolve() ==
                Path("/var/run/docker.sock").resolve()
                and not os.getenv("DOCKER_HOST", ""),
                "g1_direct_docker_daemon_not_local_reviewed",
        )
    except (KeyError, ValueError, IndexError, TypeError) as exc:
        raise Stop("g1_direct_docker_context_invalid") from exc
    version = read(["codex", "--version"])
    m = re.fullmatch(r"codex-cli\s+(\d+\.\d+\.\d+)", version)
    require(m is not None, "g1_direct_codex_cli_version_unavailable")
    checker = run(["python3", str(PCP / "scripts/g1-pilot-source-contract.py")],
                  timeout=25)
    require(checker.returncode == 0
            and '"PASS_G1_PILOT_SOURCE_PARKED"' in checker.stdout,
            "g1_direct_pilot_source_contract_changed")
    return m.group(1), DIRECT


def prepared_env(cli_version: str, old) -> dict[str, str]:
    # All interpolation-only bearers are fresh dummy values and never mounted
    # into the direct container. The one existing Github placeholder remains
    # disabled; do not create or replace any secrets.
    return {
        **os.environ,
        "PCP_G1_PILOT_ROOT": str(ROOT),
        "PCP_G1_PILOT_REPO_ROOT": str(PCP),
        "PCP_G1_PILOT_UID": str(os.geteuid()),
        "PCP_G1_PILOT_GID": str(os.getegid()),
        "PCP_G1_PILOT_SOCKET_GID": str(
            Path("/var/run/docker.sock").stat().st_gid),
        "PCP_G1_PILOT_CODEX_VERSION": cli_version,
        "PCP_G1_PILOT_DB_PASSWORD": secrets.token_hex(24),
        "PCP_G1_PILOT_ROUTER_TOKEN": secrets.token_urlsafe(36),
        "PCP_G1_PILOT_INTERNAL_TOKEN": secrets.token_urlsafe(36),
        "PCP_G1_PILOT_RUNTIME_TOKEN": secrets.token_urlsafe(36),
        "PCP_G1_PILOT_GITHUB_TOKEN_FILE": str(ROOT / "inactive/github-disabled"),
        "PCP_G1_PILOT_PCP_CODEX_AUTH_DIR": str(ROOT / "auth/pcp"),
        "PCP_G1_PILOT_DIRECT_CODEX_AUTH_DIR": str(ROOT / "auth/direct"),
        "PCP_G1_PILOT_DIRECT_WORKSPACE_DIR": str(DIRECT),
        "PCP_G1_PILOT_RUNTIME_IMAGE": DIRECT_IMAGE,
        "GIT_TERMINAL_PROMPT": "0",
    }


def compose(env: dict[str, str], *args: str,
            timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return run([
        "docker", "compose", "--project-name", "pcp-g1-pilot",
        *[element for path in COMPOSE_FILES
          for element in ("--file", str(PCP / path))],
        "--profile", "g1-pilot-parked", *args,
    ], timeout=timeout, env=env)


def failure_kind(proc: subprocess.CompletedProcess[str]) -> str:
    combined = (proc.stdout[-3000:] + "\n" + proc.stderr[-3000:]).lower()
    if any(x in combined for x in ("npm err", "npm error", "notarget")):
        return "CODEX_NPM_PACKAGE_OR_REGISTRY"
    if any(x in combined for x in ("apt-get", "temporary failure resolving",
                                   "failed to fetch", "release file")):
        return "BASE_IMAGE_OR_APT_CONNECTIVITY"
    if "dockerfile" in combined or "failed to parse" in combined:
        return "DOCKERFILE_OR_BUILD_CONTEXT"
    if any(x in combined for x in ("unauthorized", "denied", "forbidden")):
        return "IMAGE_REGISTRY_OR_PERMISSION"
    if any(x in combined for x in ("timeout", "i/o timeout", "connection refused")):
        return "BUILD_NETWORK_OR_DAEMON"
    return "UNCLASSIFIED_BUILD_OR_COMPOSE_FAILURE"


def record(value: dict[str, Any], *, initial: bool) -> None:
    os.umask(0o077)
    if initial:
        with NEW.open("x", encoding="utf-8") as f:
            json.dump(value, f, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        return
    tmp = ROOT / "direct-t01-build-continuation-evidence.tmp"
    with tmp.open("x", encoding="utf-8") as f:
        json.dump(value, f, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, NEW)


def model_already_launched() -> bool:
    try:
        return json.loads(NEW.read_text(encoding="utf-8")).get(
            "state") in {"model_launched", "completed"}
    except (ValueError, OSError):
        return False


def execute(expected_sha: str) -> dict[str, Any]:
    old = previous_operator()
    version, _ = assert_original(expected_sha, old)
    started = time.monotonic()
    record({
        "state": "continuation_started", "lane": "direct",
        "source_sha": SEED, "prior_state": "started",
        "original_attempts": 0, "model_calls": 0,
        "cause_evidence": "compose_pass_image_absent_no_network_proxy",
    }, initial=True)
    env = prepared_env(version, old)
    check = compose(env, "config", "--quiet", timeout=50)
    require(check.returncode == 0, "g1_direct_corrected_compose_config_invalid")
    built = compose(env, "build", "direct", timeout=1500)
    if built.returncode != 0:
        record({
            "state": "stopped_before_model", "phase": "build_direct_image",
            "lane": "direct", "source_sha": SEED, "model_calls": 0,
            "returncode": built.returncode,
            "build_error_class": failure_kind(built),
        }, initial=False)
        raise Stop("g1_direct_lean_image_build_failed")
    info = read([
        "docker", "image", "inspect", DIRECT_IMAGE,
        "--format", "{{json .Config.Labels}}",
    ])
    try:
        labels = json.loads(info)
    except (ValueError, TypeError) as exc:
        raise Stop("g1_direct_lean_image_labels_unreadable") from exc
    require(
        isinstance(labels, dict)
        and labels.get(SCOPE_LABEL) == "direct-control-only"
        and labels.get(MODEL_VERSION_LABEL) == version,
        "g1_direct_image_identity_or_version_mismatch",
    )
    from_proxy = compose(env, *old.proxy_argv(), timeout=90)
    require(from_proxy.returncode == 0,
            "g1_direct_proxy_start_failed_preserve_state")
    try:
        old.check_proxy_identity()
    except old.Stop as exc:
        raise Stop("g1_direct_proxy_identity_failed") from exc
    gate = compose(env, *old.direct_container_gate_argv(), timeout=75)
    require(gate.returncode == 0
            and "G1_DIRECT_CONTAINER_AUTH_AND_EGRESS=PASS" in gate.stdout,
            "g1_direct_inside_container_auth_or_egress_failed")
    # The first model call in the entire direct benchmark is here. Persist the
    # marker before starting; never issue this call again on uncertain outcome.
    record({
        "state": "model_launched", "lane": "direct",
        "source_sha": SEED, "model_calls": 1,
        "model": old.MODEL, "reasoning": old.EFFORT,
    }, initial=False)
    model_start = time.monotonic()
    response = compose(env, *old.codex_argv(),
                       timeout=old.LIMIT_SECONDS + 90)
    model_elapsed = round(time.monotonic() - model_start, 1)
    observed = old.summarise_codex(response)
    try:
        scoped, paths = old.code_scope()
    except old.Stop as exc:
        raise Stop("g1_direct_code_diff_uninspectable") from exc
    class_file = DIRECT / "web/modules/custom/pcp_f2_fixture/src/WindowOverlapDetector.php"
    unit_file = DIRECT / "web/modules/custom/pcp_f2_fixture/tests/src/Unit/WindowOverlapDetectorTest.php"
    material = (
        class_file.is_file() and unit_file.is_file()
        and "function intersectionMinutes(" in class_file.read_text(encoding="utf-8")
        and "intersectionMinutes(" in unit_file.read_text(encoding="utf-8")
    )
    accepted = bool(
        response.returncode == 0 and observed["terminal"] == "turn.completed"
        and scoped and material
        and run(["git", "-C", str(DIRECT), "diff", "--check"]).returncode == 0
        and run(["git", "-C", str(DIRECT), "diff", "--cached",
                 "--check"]).returncode == 0
    )
    commit = ""
    if accepted:
        result = run(["git", "-C", str(DIRECT), "add", "--", *sorted(old.ALLOW)])
        require(result.returncode == 0, "g1_direct_scoped_git_add_failed")
        result = run([
            "git", "-C", str(DIRECT),
            "-c", "user.name=PCP G1 Trial",
            "-c", "user.email=pcp-g1-trial@localhost",
            "commit", "-m", "feat(g1-t01): count same-day intersection minutes",
        ])
        require(result.returncode == 0, "g1_direct_local_commit_failed")
        commit = read(["git", "-C", str(DIRECT), "rev-parse", "HEAD"])
    outcome = {
        "state": "completed", "lane": "direct", "model": old.MODEL,
        "reasoning": old.EFFORT, "source_sha": SEED, "model_calls": 1,
        "model_elapsed_seconds": model_elapsed,
        "total_elapsed_seconds": round(time.monotonic() - started, 1),
        "setup_elapsed_seconds": round(model_start - started, 1),
        "returncode": observed["returncode"],
        "model_terminal": observed["terminal"], "token_usage": observed["usage"],
        "scope_ok": scoped, "material_change": material,
        "changed_paths": paths if set(paths).issubset(old.ALLOW) else ["UNAPPROVED_SCOPE"],
        "local_commit": commit, "github_pr": "NOT_CREATED",
        "hosted_ci": "NOT_CHECKED", "accepted_pr": False,
        "pcp_lane_model_calls": 0,
    }
    record(outcome, initial=False)
    return {
        "status": ("PASS_G1_DIRECT_CODE_READY_FOR_CI"
                   if accepted else "STOP_G1_DIRECT_TURN_UNACCEPTED"),
        "old_smoke_job_unchanged": True,
        "no_new_workspace": True,
        "no_automatic_retry": True,
        **{k: v for k, v in outcome.items() if k not in {
            "state", "source_sha",
        }},
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-pcp-sha", required=True)
    opts = p.parse_args()
    try:
        result = execute(opts.expected_pcp_sha)
        code = 0 if result["status"].startswith("PASS_") else 2
    except (Stop, OSError, FileExistsError, PermissionError, ValueError) as exc:
        is_model = model_already_launched()
        report = {
            "status": "STOP_G1_DIRECT_PRESERVED_CONTINUATION",
            "blocker": str(exc) if isinstance(exc, Stop)
                       else "g1_direct_continuation_evidence_unavailable",
            "model_calls": 1 if is_model else 0,
            "original_journal_unchanged": True,
            "no_new_workspace": True,
            "no_automatic_retry": True,
        }
        try:
            row = json.loads(NEW.read_text(encoding="utf-8"))
            if row.get("state") == "stopped_before_model":
                report["build_error_class"] = row.get("build_error_class")
                report["build_returncode"] = row.get("returncode")
        except (OSError, ValueError):
            pass
        result, code = report, 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
