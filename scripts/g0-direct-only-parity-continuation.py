#!/usr/bin/env python3
"""Reconcile one completed G0 PCP Codex session; resume ONLY untried direct arm.

The original failed model-parity-probe.json is strictly read-only. No PCP retry.
  status --expected-sha SHA : deterministic, no model/provider invocation
  direct --expected-sha SHA : one explicit direct-only model turn, no retry

This is an infrastructure parity check, not the Drupal G0D-T01 WorkOrder.
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
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
PROBE_SOURCE = ROOT / "scripts/g0-codex-parity-probe.py"
EXPECTED_ORIGINAL_SHA = "fb9026c06dd43cb1f2dc98b9c3662b2aadb700f0"
DIRECT_CONTAINER = "pcp-g0d01-direct-parity-once"
CONTINUATION_NAME = "model-parity-continuation.json"
TIMEOUT_SECONDS = 210


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("G0 original probe module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


original = _module("g0_codex_parity_probe", PROBE_SOURCE)
auth = original.auth
g0 = original.g0


def _original_failed_journal() -> dict:
    prior = original._read_existing_journal()
    if not isinstance(prior, dict) or not (
        prior.get("state") == "failed"
        and prior.get("failed_arm") == "pcp"
        and prior.get("attempted_arms") == ["pcp"]
        and prior.get("completed_arms") == []
        and prior.get("model") == original.EXPECTED_MODEL
        and prior.get("reasoning_effort") == original.EXPECTED_EFFORT
        and prior.get("codex_cli_version") == original.EXPECTED_CLI
        and prior.get("source_sha") == EXPECTED_ORIGINAL_SHA
    ):
        raise g0.GateError("g0_original_failed_probe_journal_changed")
    return prior


def _date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _canonical_user(payload: dict) -> str | None:
    item = payload.get("item", payload)
    if not isinstance(item, dict) or item.get("type") != "message" or (
        item.get("role") != "user"
    ):
        return None
    content = item.get("content")
    if not isinstance(content, list):
        return None
    parts = []
    for piece in content:
        if not isinstance(piece, dict):
            continue
        if piece.get("type") in {"text", "input_text"}:
            value = piece.get("text")
            if not isinstance(value, str):
                return None
            parts.append(value)
    return "".join(parts) if parts else None


def _private_file_guard(path: Path, *, is_dir: bool) -> None:
    if path.is_symlink() or (not path.is_dir() if is_dir else not path.is_file()):
        raise g0.GateError("g0_private_session_or_journal_invalid")
    stat = path.stat()
    if stat.st_uid != os.getuid() or (stat.st_mode & 0o077):
        raise g0.GateError("g0_private_session_or_journal_permissions")


def _reconcile_existing_session() -> dict:
    # Never modify the original journal or either CODEX_HOME.
    root = Path.home() / ".pcp-g0d01"
    profile = auth._auth_dir("pcp")
    for directory in (root, root / "provider", profile):
        _private_file_guard(directory, is_dir=True)
    journal = original._journal_path()
    _private_file_guard(journal, is_dir=False)
    _original_failed_journal()

    sessions = profile / "sessions"
    if sessions.is_symlink() or not sessions.is_dir():
        raise g0.GateError("g0_pcp_session_directory_missing")
    original_mtime = journal.stat().st_mtime
    candidates: list[Path] = []
    for path in sessions.glob("*/*/*/rollout-*.jsonl"):
        if path.is_symlink() or not path.is_file():
            continue
        stat = path.stat()
        if (stat.st_uid == os.getuid()
                and 0 < stat.st_size <= 4_000_000
                and abs(stat.st_mtime - original_mtime) <= 1800
                and path.resolve().is_relative_to(profile.resolve())
                and not any(parent.is_symlink() for parent in path.parents
                            if parent != profile and
                            parent.is_relative_to(profile))):
            candidates.append(path)
    if len(candidates) != 1:
        raise g0.GateError("g0_pcp_session_attribution_not_unique")

    cli_match = False
    turn_contexts = 0
    model_match = False
    effort_match = False
    messages: list[tuple[int, bool]] = []
    response_match = False
    completed_at = None
    task_complete_positions = []
    token_seen = False
    error_seen = False
    event_count = 0
    with candidates[0].open("r", encoding="utf-8", errors="replace") as stream:
        for position, line in enumerate(stream):
            if position >= 10000 or len(line) > 200_000:
                raise g0.GateError("g0_pcp_session_event_limit")
            event_count += 1
            try:
                event = json.loads(line)
            except (TypeError, ValueError) as exc:
                raise g0.GateError("g0_pcp_session_event_invalid") from exc
            if not isinstance(event, dict):
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            kind = event.get("type")
            if kind == "session_meta":
                cli_match = cli_match or (
                    payload.get("cli_version") in (
                        original.EXPECTED_CLI,
                        "codex-cli " + original.EXPECTED_CLI,
                    )
                )
            elif kind == "turn_context":
                turn_contexts += 1
                model_match = payload.get("model") == original.EXPECTED_MODEL
                effort_match = payload.get("effort") == original.EXPECTED_EFFORT
            elif kind == "response_item":
                user_text = _canonical_user(payload)
                if user_text is not None:
                    messages.append(
                        (position, user_text == original.PROBE_PROMPT)
                    )
            elif kind == "event_msg":
                typ = payload.get("type")
                if typ in {"error", "turn_aborted", "stream_error"}:
                    error_seen = True
                elif typ == "token_count":
                    token_seen = True
                elif typ == "task_complete":
                    task_complete_positions.append(position)
                    response_match = (
                        isinstance(payload.get("last_agent_message"), str)
                        and payload["last_agent_message"].strip()
                            == original.EXPECTED_RESPONSE
                    )
                    completed_at = (
                        _date(payload.get("completed_at"))
                        or _date(event.get("timestamp"))
                    )

    exact_positions = [i for i, match in messages if match]
    nonmatching_after = (
        sum(1 for i, match in messages
            if not match and exact_positions and i > exact_positions[0])
    )
    completed_before_failure = False
    if completed_at is not None:
        delta = original_mtime - completed_at.timestamp()
        completed_before_failure = -10 <= delta <= 1800
    gates = {
        "cli_match": cli_match,
        "model_match": model_match,
        "effort_match": effort_match,
        "exact_canonical_prompt_count": len(exact_positions),
        "other_canonical_items_before_prompt": sum(
            1 for i, match in messages
            if not match and exact_positions and i < exact_positions[0]
        ),
        "other_canonical_items_after_prompt": nonmatching_after,
        "completion_count": len(task_complete_positions),
        "response_match": response_match,
        "token_count_present": token_seen,
        "completion_before_original_failure": completed_before_failure,
        "error_or_abort_seen": error_seen,
    }
    attributed = (
        gates["cli_match"] and turn_contexts == 1
        and gates["model_match"] and gates["effort_match"]
        and len(exact_positions) == 1
        and nonmatching_after == 0
        and len(task_complete_positions) == 1
        and exact_positions[0] < task_complete_positions[0]
        and response_match and token_seen
        and completed_before_failure and not error_seen
    )
    if not attributed:
        raise g0.GateError("g0_original_pcp_session_attribution_inconclusive")
    return {
        "pcp_turn_reconciled": True,
        "original_wrapper_status": "failed_timeout_or_spawn",
        "canonical_user_item_count": len(messages),
        "extra_user_inputs_before_fixed_prompt":
            gates["other_canonical_items_before_prompt"],
        "canonical_user_input_after_fixed_prompt": False,
        "cli_version": original.EXPECTED_CLI,
        "model": original.EXPECTED_MODEL,
        "reasoning_effort": original.EXPECTED_EFFORT,
        "response_verified": True,
        "token_count_present": True,
        "session_events_examined": event_count,
    }


def _continuation_path() -> Path:
    return Path.home() / ".pcp-g0d01" / CONTINUATION_NAME


def _read_continuation() -> dict | None:
    path = _continuation_path()
    if not path.exists() and not path.is_symlink():
        return None
    return auth.upgrader._read_json_secure(path)


def _claim_continuation(data: dict) -> None:
    """Atomically claim the ONE remaining direct attempt across processes."""
    path = _continuation_path()
    root = path.parent
    _private_file_guard(root, is_dir=True)
    if path.exists() or path.is_symlink():
        raise g0.GateError("g0_direct_continuation_already_recorded_no_retry")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise g0.GateError("g0_direct_continuation_concurrently_claimed") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, sort_keys=True)
    except OSError as exc:
        raise g0.GateError("g0_direct_continuation_record_failed") from exc


def _write_continuation(data: dict) -> None:
    # The original failed parity journal must remain unchanged.
    path = _continuation_path()
    _private_file_guard(path, is_dir=False)
    auth.upgrader._private_write(path, data)


def _direct_container_absent() -> None:
    if g0.exists("container", DIRECT_CONTAINER):
        raise g0.GateError("g0_direct_probe_container_name_occupied")
    net = g0.inspect("network", auth.G0_AUTH_NETWORKS["direct"])
    if ((net.get("Labels") or {}).get("com.docker.compose.project") != g0.PROJECT
            or net.get("Internal") is not False
            or (net.get("Containers") or {})):
        raise g0.GateError("g0_direct_provider_network_not_private_to_g0")


def _context(repo: Path, fixture: Path, sha: str) -> tuple[dict, dict]:
    env, _ = original._prepared_context(repo, fixture, sha)
    _original_failed_journal()
    _direct_container_absent()
    recovered = _reconcile_existing_session()
    return env, recovered


def status(repo: Path, fixture: Path, sha: str) -> dict:
    _, evidence = _context(repo, fixture, sha)
    prior = _read_continuation()
    return {
        "status": "PASS",
        "phase": "g0_pcp_recovered_direct_pending",
        "project": g0.PROJECT,
        "source_sha": sha,
        "pcp_evidence": evidence,
        "original_failed_journal_preserved": True,
        "prior_direct_continuation": (
            None if prior is None else prior.get("state")
        ),
        "direct_only_call_authorized_by_operator": prior is None,
        "model_calls_this_command": 0,
        "ready_to_dispatch_g0d_t01": False,
    }


def _direct_command(repo: Path) -> list[str]:
    command = original._probe_command(repo, "direct")
    i = command.index("auth_direct")
    return command[:i] + ["--name", DIRECT_CONTAINER] + command[i:]


def _direct_one_call(repo: Path, env: dict) -> dict:
    argv = _direct_command(repo)
    started = time.monotonic()
    try:
        result = subprocess.run(
            argv, env=env, text=True, capture_output=True,
            timeout=TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise g0.GateError("g0_direct_model_or_wrapper_timeout") from exc
    except OSError as exc:
        raise g0.GateError("g0_direct_docker_cli_unavailable") from exc
    parsed = original._parse_result(
        result.stdout, exit_code=result.returncode
    )
    return {
        "response_verified": parsed["response_verified"],
        "terminal": parsed["terminal"],
        "usage": parsed["usage"],
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "codex_cli_version": original.EXPECTED_CLI,
        "model": original.EXPECTED_MODEL,
        "reasoning_effort": original.EXPECTED_EFFORT,
    }


def direct(repo: Path, fixture: Path, sha: str) -> dict:
    env, pcp = _context(repo, fixture, sha)
    if _read_continuation() is not None:
        raise g0.GateError("g0_direct_continuation_already_recorded_no_retry")
    g0.require_headroom(repo)
    entry = {
        "state": "started", "source_sha": sha,
        "original_journal_status": "failed",
        "pcp": pcp,
        "direct_attempted": True,
        "direct_completed": False,
        "ready_to_dispatch_g0d_t01": False,
    }
    _claim_continuation(entry)
    try:
        direct_result = _direct_one_call(repo, env)
    except g0.GateError as exc:
        entry["state"] = "failed"
        entry["error_class"] = str(exc)
        entry["direct_container_remaining"] = g0.exists(
            "container", DIRECT_CONTAINER
        )
        _write_continuation(entry)
        raise
    entry.update({
        "state": "direct_completed",
        "direct_completed": True,
        "direct_result": direct_result,
    })
    _write_continuation(entry)
    return {
        "status": "PASS",
        "phase": "g0_model_parity_reconciled",
        "pcp_reconciled_from_session": True,
        "original_wrapper_timeout_preserved": True,
        "direct_only_model_calls_attempted": 1,
        "direct_response_verified": direct_result["response_verified"],
        "model": direct_result["model"],
        "reasoning_effort": direct_result["reasoning_effort"],
        "cli_version": direct_result["codex_cli_version"],
        "direct_usage": direct_result["usage"],
        "direct_elapsed_seconds": direct_result["elapsed_seconds"],
        "original_failed_journal_modified": False,
        "same_provider_account_or_quota_proven": False,
        "ready_to_dispatch_g0d_t01": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("status", "direct"))
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    repo = Path.home() / "personal-coding-platform-v1"
    fixture = Path.home() / "pcp-g0-fixtures/pcp-g0-drupal-fixture"
    try:
        result = (
            status(repo, fixture, args.expected_sha)
            if args.mode == "status"
            else direct(repo, fixture, args.expected_sha)
        )
    except (g0.GateError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({
            "status": "STOP", "phase": args.mode,
            "reason": (str(exc) if isinstance(exc, g0.GateError)
                       else "g0_parity_continuation_validation_error"),
            "do_not_retry_blindly": True,
            "ready_to_dispatch_g0d_t01": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
