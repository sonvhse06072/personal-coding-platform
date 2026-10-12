#!/usr/bin/env python3
"""Read-only forensic for one timed-out G0D-T01 Direct coding attempt.

The original private execute_claimed journal is immutable. Inspect ONLY that
existing G0 Direct container, its isolated network, its Codex rollout metadata,
and read-only Git state in the previously prepared Direct fixture workspace.

A completed Codex turn + valid three-file worktree is NOT clean wrapper exit.
No model calls, Docker lifecycle, Git mutations, token reads or new journal.
Usage: inspect --expected-sha EXACT_CLEAN_PCP_MAIN_SHA
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DIRECT_SOURCE = ROOT / "scripts/g0d-t01-direct-operator.py"
ATTEMPT_SOURCE_SHA = "90ce1f3d7b2831a05f055e6641c8334310e419cc"
SESSION_MAX_BYTES = 8_000_000
SESSION_MAX_EVENTS = 15_000
SESSION_MAX_LINE = 300_000
MAX_CANDIDATES = 24


def _load():
    spec = importlib.util.spec_from_file_location(
        "g0_direct_original_coding_attempt", DIRECT_SOURCE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Original Direct execution source not available")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


direct = _load()
g0 = direct.g0
auth = direct.auth
live = direct.live


def _parse_date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _attempt() -> tuple[dict, datetime]:
    record = direct._read_journal()
    started = _parse_date(record.get("execute_started_at"))
    prepared = _parse_date(record.get("prepare_started_at"))
    if (
        record.get("arm") != "direct"
        or record.get("task_id") != "G0D-T01"
        or record.get("source_sha") != ATTEMPT_SOURCE_SHA
        or record.get("seed") != direct.SEED
        or record.get("branch") != direct.BRANCH
        or record.get("model") != direct.MODEL
        or record.get("reasoning_effort") != direct.EFFORT
        or record.get("codex_cli_version") != direct.CLI_VERSION
        or record.get("state") != "execute_claimed"
        or record.get("execute_attempted") is not True
        or record.get("github_delivery_enabled") is not False
        or record.get("commit") is not None
        or started is None or prepared is None or started < prepared
        or started > datetime.now(timezone.utc)
    ):
        raise g0.GateError("g0_direct_original_claim_not_exact")
    path = direct._journal_path()
    if path.stat().st_uid != os.getuid():
        raise g0.GateError("g0_direct_original_claim_owner_changed")
    return record, started


def _container() -> str:
    name = direct.DIRECT_CONTAINER
    net_name = auth.G0_AUTH_NETWORKS["direct"]
    provider = g0.inspect("network", net_name)
    if (
        provider.get("Internal") is not False
        or (provider.get("Labels") or {}).get(
            "com.docker.compose.project"
        ) != g0.PROJECT
    ):
        raise g0.GateError("g0_direct_provider_network_not_owned")
    network_members = {
        v.get("Name") for v in (provider.get("Containers") or {}).values()
        if isinstance(v, dict)
    }
    if network_members - {name}:
        raise g0.GateError("g0_direct_provider_has_foreign_container")
    if not g0.exists("container", name):
        if network_members:
            raise g0.GateError("g0_direct_provider_orphan_membership")
        return "absent"
    item = g0.inspect("container", name)
    labels = (item.get("Config") or {}).get("Labels") or {}
    host = item.get("HostConfig") or {}
    mounts = item.get("Mounts") or []
    networks = (item.get("NetworkSettings") or {}).get("Networks") or {}
    state = item.get("State") or {}
    images = g0.inspect(
        "image", g0.resource_names(auth.DEPLOYED_SHA)["runtime"]
    )
    if (
        item.get("Name") != "/" + name
        or labels.get("com.docker.compose.project") != g0.PROJECT
        or labels.get("com.docker.compose.service") != "direct"
        or item.get("Image") != images.get("Id")
        or set(networks) != {net_name}
        or host.get("ReadonlyRootfs") is not True
        or host.get("Privileged") is not False
        or bool(host.get("PortBindings"))
        or not isinstance(state.get("Running"), bool)
    ):
        raise g0.GateError("g0_direct_coding_container_identity_invalid")
    expected = {
        "/home/coder/.codex-direct": str(auth._auth_dir("direct")),
        "/g0/direct-workspace": str(direct._workspace()),
        "/tmp": None,
    }
    by_target = {
        item.get("Destination"): item
        for item in mounts if isinstance(item, dict)
    }
    if len(by_target) != len(mounts) or set(by_target) != set(expected):
        raise g0.GateError("g0_direct_coding_container_mounts_changed")
    for target, source in expected.items():
        mount = by_target[target]
        if source is None:
            if mount.get("Type") != "tmpfs":
                raise g0.GateError("g0_direct_tmpfs_missing")
        elif (
            mount.get("Type") != "bind" or mount.get("Source") != source
            or mount.get("RW") is not True
        ):
            raise g0.GateError("g0_direct_bind_identity_changed")
    if state["Running"] and network_members != {name}:
        raise g0.GateError("g0_direct_container_running_network_drift")
    return "running" if state["Running"] else "not_running"


def _user_text(payload: dict) -> str | None:
    item = payload.get("item", payload)
    if not isinstance(item, dict) or item.get("type") != "message" or (
        item.get("role") != "user"
    ):
        return None
    content = item.get("content")
    if not isinstance(content, list):
        return None
    chunks = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") in {"text", "input_text"}:
            if not isinstance(part.get("text"), str):
                return None
            chunks.append(part["text"])
    return "".join(chunks) if chunks else None


def _rollout(path: Path, started: datetime) -> dict:
    before = path.stat()
    prompt = direct._fixed_prompt()
    seen_cli, contexts, user, terminals = False, [], [], []
    token_count = False
    error_or_abort = False
    count = 0
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for index, line in enumerate(stream):
            if index >= SESSION_MAX_EVENTS or len(line) > SESSION_MAX_LINE:
                raise g0.GateError("g0_direct_coding_session_bounded_read_exceeded")
            count += 1
            try:
                event = json.loads(line)
            except (TypeError, ValueError) as exc:
                raise g0.GateError("g0_direct_coding_session_unreadable") from exc
            if not isinstance(event, dict) or not isinstance(event.get("payload"), dict):
                continue
            kind, payload = event.get("type"), event["payload"]
            if kind == "session_meta":
                seen_cli = seen_cli or payload.get("cli_version") in (
                    direct.CLI_VERSION, "codex-cli " + direct.CLI_VERSION
                )
            elif kind == "turn_context":
                contexts.append(
                    (payload.get("model") == direct.MODEL,
                     payload.get("effort") == direct.EFFORT)
                )
            elif kind == "response_item":
                message = _user_text(payload)
                if message is not None:
                    user.append((index, message == prompt))
            elif kind == "event_msg":
                typ = payload.get("type")
                if typ in {"turn_aborted", "stream_error", "error"}:
                    error_or_abort = True
                if typ == "token_count":
                    token_count = True
                if typ == "task_complete":
                    terminals.append((
                        index,
                        _parse_date(payload.get("completed_at"))
                        or _parse_date(event.get("timestamp")),
                    ))
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (
        after.st_size, after.st_mtime_ns
    ):
        raise g0.GateError("g0_direct_coding_session_changed_during_read")
    matching = [i for i, exact in user if exact]
    completed = (
        terminals[0][1] if len(terminals) == 1 else None
    )
    now = datetime.now(timezone.utc)
    gates = {
        "cli_match": seen_cli,
        "model_effort_match": len(contexts) == 1
            and contexts[0] == (True, True),
        "one_exact_original_prompt": len(matching) == 1,
        "no_other_user_after_prompt": len(matching) == 1
            and not any(i > matching[0] for i, exact in user if not exact),
        "one_terminal_after_prompt": len(matching) == 1
            and len(terminals) == 1 and matching[0] < terminals[0][0],
        "completion_after_attempt": completed is not None
            and started.timestamp() - 120 <= completed.timestamp()
            <= now.timestamp() + 60,
        "token_count_seen": token_count,
        "no_error_abort": not error_or_abort,
    }
    return {
        "session_events_examined": count,
        "canonical_user_item_count": len(user),
        "gates": gates,
        "completed_turn_attributed": all(gates.values()),
    }


def _session_evidence(started: datetime) -> dict:
    profile = auth._auth_dir("direct")
    for root in (
        Path.home() / ".pcp-g0d01",
        Path.home() / ".pcp-g0d01" / "provider",
        profile,
    ):
        auth._check_private_existing(root, directory=True)
        if root.stat().st_uid != os.getuid():
            raise g0.GateError("g0_direct_session_owner_mismatch")
    sessions = profile / "sessions"
    if sessions.is_symlink() or not sessions.is_dir():
        return {"candidate_count": 0, "reconciled": False,
                "reason": "g0_direct_coding_session_directory_missing"}
    files = []
    for item in sessions.glob("*/*/*/rollout-*.jsonl"):
        if item.is_symlink() or not item.is_file():
            continue
        stat = item.stat()
        if (
            stat.st_uid == os.getuid()
            and not stat.st_mode & 0o022
            and 0 < stat.st_size <= SESSION_MAX_BYTES
            and started.timestamp() - 120 <= stat.st_mtime
            <= datetime.now(timezone.utc).timestamp() + 60
            and item.resolve().is_relative_to(profile.resolve())
            and not any(
                parent.is_symlink() for parent in item.parents
                if parent != profile and parent.is_relative_to(profile)
            )
        ):
            files.append(item)
            if len(files) > MAX_CANDIDATES:
                raise g0.GateError("g0_direct_coding_session_candidate_limit")
    if len(files) != 1:
        return {
            "candidate_count": len(files), "reconciled": False,
            "reason": "g0_direct_coding_session_not_unique",
        }
    evidence = _rollout(files[0], started)
    return {
        "candidate_count": 1,
        "reconciled": evidence["completed_turn_attributed"],
        **evidence,
    }


def _git(workspace: Path, *args: str, accept_fail: bool = False) -> tuple[int, str]:
    env = {
        **direct._git_env(),
        "GIT_OPTIONAL_LOCKS": "0",
    }
    argv = [
        "git", "-C", str(workspace),
        "-c", "core.hooksPath=/dev/null",
        "-c", "diff.external=",
        *args,
    ]
    try:
        proc = subprocess.run(
            argv, env=env, capture_output=True, text=True,
            timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise g0.GateError("g0_direct_coding_git_read_unavailable") from exc
    if proc.returncode and not accept_fail:
        raise g0.GateError("g0_direct_coding_git_read_failed")
    if len(proc.stdout) > 200_000:
        raise g0.GateError("g0_direct_coding_git_output_oversize")
    return proc.returncode, proc.stdout.strip()


def _workspace_evidence() -> dict:
    workspace = direct._workspace()
    status_before = _git(workspace, "status", "--porcelain=v1", "-uall")[1]
    head = _git(workspace, "rev-parse", "HEAD")[1]
    root = _git(workspace, "rev-parse", "--show-toplevel")[1]
    branch = _git(workspace, "branch", "--show-current")[1]
    remote = _git(workspace, "remote")[1]
    ancestor_code, _ = _git(
        workspace, "merge-base", "--is-ancestor", direct.SEED, "HEAD",
        accept_fail=True,
    )
    changed = _git(
        workspace, "diff", "--no-ext-diff", "--no-textconv",
        "--name-only", direct.SEED, "HEAD",
    )[1].splitlines()
    unstaged = _git(
        workspace, "diff", "--no-ext-diff", "--no-textconv",
        "--name-only",
    )[1].splitlines()
    staged = _git(
        workspace, "diff", "--cached", "--no-ext-diff", "--no-textconv",
        "--name-only",
    )[1].splitlines()
    union = set(changed) | set(unstaged) | set(staged)
    # Includes ignored/untracked without revealing their paths. New nontrivial
    # untracked files must not be silently accepted as a valid three-file diff.
    untracked = _git(
        workspace, "ls-files", "--others", "--exclude-standard",
    )[1].splitlines()
    diff_code, _ = _git(
        workspace, "diff", "--no-ext-diff", "--no-textconv",
        "--check", direct.SEED,
        accept_fail=True,
    )
    status_after = _git(workspace, "status", "--porcelain=v1", "-uall")[1]
    if status_after != status_before:
        raise g0.GateError("g0_direct_coding_workspace_changed_during_read")
    if (
        root != str(workspace.resolve()) or branch != direct.BRANCH
        or remote or ancestor_code != 0 or head == ""
    ):
        raise g0.GateError("g0_direct_coding_workspace_identity_failed")
    # All expected changes must be present (tracked, staged or unstaged).
    files_ok = (
        union == set(direct.ALLOWED_FILES)
        and not untracked
        and status_after != ""
    )
    foreign = bool(union - set(direct.ALLOWED_FILES) or untracked)
    hashes = {}
    if files_ok:
        for relative in direct.ALLOWED_FILES:
            file = workspace / relative
            if file.is_symlink() or not file.is_file() or file.stat().st_size > 100_000:
                raise g0.GateError("g0_direct_coding_file_identity_invalid")
            hashes[relative.rsplit("/", 1)[-1]] = _git(
                workspace, "hash-object", "--", relative
            )[1]
    return {
        "head": head,
        "branch": branch,
        "same_frozen_seed_ancestor": ancestor_code == 0,
        "tracked_changed_count": len(union),
        "within_three_file_contract": files_ok,
        "untracked_or_out_of_scope": foreign,
        "diff_check_pass": diff_code == 0,
        "git_blob_hashes": hashes,
    }


def inspect(repo: Path, fixture: Path, sha: str) -> dict:
    g0.require_local_docker_context()
    g0.require_exact_repo(repo, g0.EXPECTED_REPO, "main", sha)
    g0.require_exact_repo(fixture, g0.EXPECTED_FIXTURE, "benchmark/pcp", direct.SEED)
    if not g0.SOURCE_SHA.fullmatch(sha):
        raise g0.GateError("g0_direct_forensic_exact_sha_required")
    live._activated_state()
    live._docker_boundary(repo)
    attempt, started = _attempt()
    container_state = _container()
    sessions = _session_evidence(started)
    workspace = _workspace_evidence()
    recovered = (
        container_state != "running"
        and sessions.get("reconciled") is True
        and workspace["same_frozen_seed_ancestor"]
        and workspace["within_three_file_contract"]
        and not workspace["untracked_or_out_of_scope"]
        and workspace["diff_check_pass"]
    )
    reason = (
        None if recovered else
        "g0_direct_original_container_still_running" if container_state == "running"
        else sessions.get("reason") or "g0_direct_coding_evidence_incomplete"
    )
    return {
        "status": "PASS" if recovered else "STOP",
        "phase": "g0d_t01_direct_timeout_forensics",
        "project": g0.PROJECT,
        "source_sha": sha,
        "attempt_source_sha": ATTEMPT_SOURCE_SHA,
        "journal_state": attempt["state"],
        "wrapper_status": "failed_timeout",
        "direct_container_state": container_state,
        "session_evidence": sessions,
        "workspace_evidence": workspace,
        "recoverable_without_model": recovered,
        "original_journal_preserved": True,
        "model_calls_this_command": 0,
        "retry_authorized": False,
        "ready_to_dispatch_g0d_t01": False,
        "reason": reason,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect",))
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    try:
        result = inspect(
            Path.home() / "personal-coding-platform-v1",
            Path.home() / "pcp-g0-fixtures/pcp-g0-drupal-fixture",
            args.expected_sha,
        )
    except (g0.GateError, OSError, ValueError, TypeError, KeyError) as exc:
        result = {
            "status": "STOP",
            "phase": "g0d_t01_direct_timeout_forensics",
            "reason": str(exc) if isinstance(exc, g0.GateError)
                      else "g0_direct_forensic_inspection_failed",
            "do_not_retry_blindly": True,
            "original_journal_preserved": True,
            "model_calls_this_command": 0,
            "retry_authorized": False,
            "ready_to_dispatch_g0d_t01": False,
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
