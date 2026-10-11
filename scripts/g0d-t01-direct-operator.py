#!/usr/bin/env python3
"""One authorized G0D-T01 Direct coding arm on the isolated Drupal fixture.

prepare --expected-sha SHA: claim once, clone frozen fixture into G0-only path
status --expected-sha SHA: read-only inspection of the original journal
execute --expected-sha SHA: claim once, ONE direct Codex CLI coding attempt

No host/global Codex, Docker lifecycle, DDEV, GitHub tokens, PR/push, PCP retry,
legacy PCP, or Chợ Nhạc access. Do not rerun after a STOP/timeout.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
PCP_OPERATOR = ROOT / "scripts/g0d-t01-pcp-operator.py"
G0_RUNTIME_SOURCE = ROOT / "services/runtime/app/g0_fixture_execution.py"
JOURNAL_NAME = "g0d-t01-direct-attempt.json"
SEED = "39ef13c25b24c4a1b43a720ae53419f479996ed2"
ORIGINAL_PCP_SOURCE = "8608c51f7513fe9f814eb56eb94fc68522b68bff"
PCP_JOB = "d361d1d9b4d54858bbbe6939fcf0cba9"
PCP_COMMIT = "d7ff88183e2ccea298f5eadded7ae84f7d88c7c5"
BRANCH = "ai/g0d-t01-direct"
MODEL = "gpt-6-luna"
EFFORT = "medium"
CLI_VERSION = "0.160.0"
DIRECT_CONTAINER = "pcp-g0d01-direct-g0d-t01-once"
TIMEOUT_SECONDS = 1860
ALLOWED_FILES = (
    "web/modules/custom/pcp_g0_fixture/src/EventLabelNormalizer.php",
    "web/modules/custom/pcp_g0_fixture/tests/src/Unit/EventLabelNormalizerTest.php",
    "web/modules/custom/pcp_g0_fixture/tests/src/Kernel/EventLabelServiceTest.php",
)


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("g0_pcp_for_direct", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("G0 PCP fixture operator unavailable")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pcp = _load(PCP_OPERATOR)
live = pcp.live
g0 = pcp.g0
auth = live.activation.auth


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _journal_path() -> Path:
    root = Path.home() / ".pcp-g0d01"
    auth._check_private_existing(root, directory=True)
    if root.is_symlink():
        raise g0.GateError("g0_direct_private_root_symlink")
    return root / JOURNAL_NAME


def _read_journal() -> dict:
    return auth.upgrader._read_json_secure(_journal_path())


def _claim(data: dict) -> None:
    path = _journal_path()
    if path.exists() or path.is_symlink():
        raise g0.GateError("g0_direct_trial_already_claimed_no_retry")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise g0.GateError("g0_direct_concurrent_claim") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def _save(record: dict) -> None:
    path = _journal_path()
    auth._check_private_existing(path, directory=False)
    auth.upgrader._private_write(path, record)


def _git_env() -> dict[str, str]:
    allowed = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "SSH_AUTH_SOCK")
    env = {k: v for k in allowed if (v := os.environ.get(k))}
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
    })
    # Never let the fixture Git transport inherit host GitHub/SSH credentials.
    env.pop("SSH_AUTH_SOCK", None)
    return env


def _git(repo: Path, *args: str, timeout: int = 40) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "-c", "core.hooksPath=/dev/null", *args],
            env=_git_env(), capture_output=True, text=True,
            check=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise g0.GateError("g0_direct_scoped_git_unavailable") from exc
    if result.returncode:
        raise g0.GateError("g0_direct_scoped_git_failed")
    return result.stdout.strip()


def _workspace() -> Path:
    root = Path.home() / ".pcp-g0d01" / "arms"
    auth._check_private_existing(root, directory=True)
    direct = root / "direct"
    auth._check_private_existing(direct, directory=True)
    workspace = auth._direct_workspace()
    auth._check_private_existing(workspace, directory=True)
    if any(p.is_symlink() for p in (root, direct, workspace)):
        raise g0.GateError("g0_direct_workspace_symlink")
    return workspace


def _fixed_prompt() -> str:
    """Extract the identical, literal PCP G0 task prompt without loading Runtime."""
    if G0_RUNTIME_SOURCE.is_symlink() or not G0_RUNTIME_SOURCE.is_file():
        raise g0.GateError("g0_direct_task_source_missing")
    try:
        doc = ast.parse(G0_RUNTIME_SOURCE.read_text(encoding="utf-8"))
        choices = [
            node.value.value for node in doc.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "G0_PROMPT"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ]
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise g0.GateError("g0_direct_prompt_parse_invalid") from exc
    if len(choices) != 1 or not choices[0].startswith(
        "Implement G0D-T01 on this isolated Drupal fixture"
    ) or "Do not push, open a pull request" not in choices[0]:
        raise g0.GateError("g0_direct_task_prompt_not_frozen")
    return choices[0]


def _verify_pcp_completed() -> None:
    state = pcp._existing()
    if (
        state.get("phase") != "pcp"
        or state.get("state") != "executed"
        or state.get("source_sha") != ORIGINAL_PCP_SOURCE
        or state.get("job_id") != PCP_JOB
        or state.get("commit") != PCP_COMMIT
        or state.get("execute_attempted") is not True
    ):
        raise g0.GateError("g0_pcp_original_trial_not_completed")
    row = pcp._http("GET", "/v1/g0-fixture/jobs/" + PCP_JOB, 30)
    pcp._valid_job(row, require_result=True)
    if row.get("job_status") != "waiting_human" or (
        row.get("result") or {}
    ).get("commit") != PCP_COMMIT:
        raise g0.GateError("g0_pcp_original_job_not_reviewable")


def _identity(repo: Path, fixture: Path, sha: str) -> None:
    if not g0.SOURCE_SHA.fullmatch(sha):
        raise g0.GateError("g0_direct_exact_source_required")
    g0.require_local_docker_context()
    g0.require_exact_repo(repo, g0.EXPECTED_REPO, "main", sha)
    g0.require_exact_repo(fixture, g0.EXPECTED_FIXTURE, "benchmark/pcp", SEED)
    auth._validate_overlay()
    live._activated_state()
    live._docker_boundary(repo)
    _verify_pcp_completed()
    if not auth._check_config("direct"):
        raise g0.GateError("g0_direct_auth_not_prepared")
    if g0.exists("container", DIRECT_CONTAINER):
        raise g0.GateError("g0_direct_trial_container_exists")
    network = g0.inspect("network", auth.G0_AUTH_NETWORKS["direct"])
    if (
        (network.get("Labels") or {}).get("com.docker.compose.project") != g0.PROJECT
        or network.get("Internal") is not False
        or bool(network.get("Containers"))
    ):
        raise g0.GateError("g0_direct_provider_network_ownership_or_busy")
    image = g0.inspect(
        "image", g0.resource_names(auth.DEPLOYED_SHA)["runtime"]
    )
    labels = (image.get("Config") or {}).get("Labels") or {}
    if (
        labels.get("org.opencontainers.image.pcp.codex-version") != CLI_VERSION
        or not str(image.get("Id") or "").startswith("sha256:")
    ):
        raise g0.GateError("g0_direct_codex_image_version_unverified")
    _fixed_prompt()


def _assert_frozen_workspace(workspace: Path) -> None:
    if (
        _git(workspace, "rev-parse", "HEAD") != SEED
        or _git(workspace, "branch", "--show-current") != BRANCH
        or _git(workspace, "remote")
        or _git(workspace, "status", "--porcelain=v1")
    ):
        raise g0.GateError("g0_direct_workspace_not_clean_seed")


def prepare(repo: Path, fixture: Path, sha: str) -> dict:
    _identity(repo, fixture, sha)
    g0.require_headroom(repo)
    workspace = _workspace()
    if any(workspace.iterdir()):
        raise g0.GateError("g0_direct_workspace_occupied")
    record = {
        "arm": "direct", "task_id": "G0D-T01",
        "state": "prepare_claimed", "source_sha": sha, "seed": SEED,
        "branch": BRANCH, "model": MODEL, "reasoning_effort": EFFORT,
        "codex_cli_version": CLI_VERSION,
        "prepare_started_at": _now(), "execute_attempted": False,
        "github_delivery_enabled": False,
    }
    _claim(record)
    # Local clone only; source/seed was already identity checked. Never fetch.
    _git(
        fixture, "clone", "--no-local", "--no-checkout",
        "--branch", "benchmark/pcp", str(fixture), str(workspace),
        timeout=300,
    )
    _git(workspace, "remote", "remove", "origin")
    _git(workspace, "checkout", "-b", BRANCH, SEED)
    _assert_frozen_workspace(workspace)
    record.update({"state": "prepared", "prepare_completed_at": _now()})
    _save(record)
    return {
        "status": "PASS", "phase": "g0d_t01_direct_prepared",
        "seed": SEED, "branch": BRANCH, "source_sha": sha,
        "model": MODEL, "reasoning_effort": EFFORT,
        "codex_cli_version": CLI_VERSION,
        "codex_cli_invocations_attempted": 0,
        "github_delivery_enabled": False,
        "ready_for_one_execute": True,
    }


def _compose_env(repo: Path, fixture: Path) -> dict[str, str]:
    deployed, password, workspaces = g0.read_private_state(Path.home())
    if deployed != auth.DEPLOYED_SHA:
        raise g0.GateError("g0_direct_image_source_changed")
    env = g0.compose_env(repo, fixture, workspaces, deployed, password)
    env.update({
        "PCP_G0_AUTH_PCP_DIR": str(auth._auth_dir("pcp")),
        "PCP_G0_AUTH_DIRECT_DIR": str(auth._auth_dir("direct")),
        "PCP_G0_DIRECT_WORKSPACE_DIR": str(_workspace()),
    })
    auth._verify_rendered_tmpfs_mounts(repo, env)
    return env


def _direct_one_call(repo: Path, fixture: Path) -> dict:
    argv = auth._compose(repo) + [
        "--profile", "owner-gated-g0-direct",
        "run", "--rm", "--no-deps", "-T",
        "--name", DIRECT_CONTAINER, "direct",
        "exec", "--json",
        "--sandbox", "workspace-write",
        "--config", 'approval_policy="never"',
        "--config", "features.memories=false",
        "--config", "memories.use_memories=false",
        "--config", "memories.generate_memories=false",
        "--config", "sandbox_workspace_write.network_access=false",
        "--cd", "/g0/direct-workspace",
        "--model", MODEL,
        "--config", 'model_reasoning_effort="medium"',
        "--output-last-message", "/tmp/g0d-t01-final.txt",
        _fixed_prompt(),
    ]
    start = time.monotonic()
    try:
        p = subprocess.run(
            argv, capture_output=True, text=True, check=False,
            env=_compose_env(repo, fixture), timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise g0.GateError("g0_direct_coding_wrapper_timeout_no_retry") from exc
    except OSError as exc:
        raise g0.GateError("g0_direct_coding_docker_unavailable") from exc
    if p.returncode != 0 or len(p.stdout) > 4_000_000:
        raise g0.GateError("g0_direct_coding_cli_failed_no_retry")
    ended, errors, usage = 0, False, {}
    for line in p.stdout.splitlines():
        try:
            event = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        typ = event.get("type")
        if typ in {"error", "turn.failed", "item.failed"}:
            errors = True
        if typ == "turn.completed":
            ended += 1
            values = event.get("usage")
            if isinstance(values, dict):
                usage = {
                    k: v for k, v in values.items()
                    if k in {"input_tokens", "cached_input_tokens", "output_tokens"}
                    and type(v) is int and 0 <= v <= 5_000_000
                }
    if ended != 1 or errors:
        raise g0.GateError("g0_direct_coding_terminal_unverified_no_retry")
    return {
        "terminal_verified": True, "elapsed_seconds": round(time.monotonic()-start, 2),
        "usage": usage,
    }


def _commit_scope(workspace: Path) -> str:
    if _git(workspace, "remote"):
        raise g0.GateError("g0_direct_workspace_remote_reintroduced")
    if _git(workspace, "branch", "--show-current") != BRANCH:
        raise g0.GateError("g0_direct_workspace_branch_changed")
    untracked = _git(workspace, "ls-files", "--others", "--exclude-standard")
    if untracked:
        raise g0.GateError("g0_direct_untracked_files_present")
    changed = set(_git(workspace, "diff", "--name-only", SEED).splitlines())
    if changed != set(ALLOWED_FILES):
        raise g0.GateError("g0_direct_diff_not_three_frozen_files")
    _git(workspace, "diff", "--check", SEED)
    _git(workspace, "add", "--", *ALLOWED_FILES)
    if _git(workspace, "diff", "--cached", "--name-only"):
        _git(
            workspace,
            "-c", "user.name=G0 Direct Fixture Developer",
            "-c", "user.email=g0-direct-fixture@localhost",
            "commit", "-m", "test(g0d-t01): direct ASCII whitespace normalization",
        )
    if _git(workspace, "status", "--porcelain=v1"):
        raise g0.GateError("g0_direct_workspace_dirty_after_commit")
    commit = _git(workspace, "rev-parse", "HEAD")
    if commit == SEED or not re.fullmatch("[0-9a-f]{40}", commit):
        raise g0.GateError("g0_direct_missing_derived_commit")
    _git(workspace, "merge-base", "--is-ancestor", SEED, commit)
    return commit


def execute(repo: Path, fixture: Path, sha: str) -> dict:
    _identity(repo, fixture, sha)
    record = _read_journal()
    if (
        record.get("arm") != "direct" or record.get("state") != "prepared"
        or record.get("source_sha") != sha
        or record.get("seed") != SEED or record.get("branch") != BRANCH
        or record.get("model") != MODEL
        or record.get("reasoning_effort") != EFFORT
        or record.get("codex_cli_version") != CLI_VERSION
        or record.get("execute_attempted") is not False
    ):
        raise g0.GateError("g0_direct_attempt_not_prepared_or_already_used")
    workspace = _workspace()
    _assert_frozen_workspace(workspace)
    record.update({
        "state": "execute_claimed", "execute_attempted": True,
        "execute_started_at": _now(),
    })
    _save(record)
    # No retry, even if container wraps a completed model turn as timeout.
    result = _direct_one_call(repo, fixture)
    commit = _commit_scope(workspace)
    record.update({
        "state": "executed", "execute_completed_at": _now(),
        "commit": commit, "terminal_verified": result["terminal_verified"],
        "usage": result["usage"],
        "elapsed_seconds": result["elapsed_seconds"],
    })
    _save(record)
    return {
        "status": "PASS", "phase": "g0d_t01_direct_executed",
        "branch": BRANCH, "source_sha": sha, "seed": SEED,
        "commit": commit, "changed_files": sorted(ALLOWED_FILES),
        "codex_cli_invocations_attempted": 1,
        "model_api_calls_observed": None,
        "usage": result["usage"], "elapsed_seconds": result["elapsed_seconds"],
        "github_delivery_enabled": False,
        "needs_independent_ci_review": True,
    }


def status(repo: Path, fixture: Path, sha: str) -> dict:
    g0.require_local_docker_context()
    g0.require_exact_repo(repo, g0.EXPECTED_REPO, "main", sha)
    g0.require_exact_repo(fixture, g0.EXPECTED_FIXTURE, "benchmark/pcp", SEED)
    record = _read_journal()
    if record.get("arm") != "direct" or record.get("source_sha") != sha:
        raise g0.GateError("g0_direct_status_identity_drift")
    workspace = _workspace()
    return {
        "status": "PASS", "phase": "g0d_t01_direct_status",
        "journal_state": record.get("state"),
        "execute_attempted": record.get("execute_attempted"),
        "branch": record.get("branch"), "commit": record.get("commit"),
        "workspace_occupied": any(workspace.iterdir()),
        "model_calls_this_command": 0, "retry_authorized": False,
        "github_delivery_enabled": False,
        "ready_to_dispatch_g0d_t01": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "status", "execute"))
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    repo = Path.home() / "personal-coding-platform-v1"
    fixture = Path.home() / "pcp-g0-fixtures/pcp-g0-drupal-fixture"
    try:
        report = {
            "prepare": prepare, "status": status, "execute": execute
        }[args.mode](repo, fixture, args.expected_sha)
    except (g0.GateError, OSError, ValueError, TypeError, KeyError) as exc:
        report = {
            "status": "STOP", "phase": "g0d_t01_direct_" + args.mode,
            "reason": str(exc) if isinstance(exc, g0.GateError)
                      else "g0_direct_operator_validation_error",
            "do_not_retry_blindly": True,
            "ready_to_dispatch_g0d_t01": False,
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
