#!/usr/bin/env python3
"""Read-only evidence check for ONE timed-out G0 Direct model-parity turn.

Only inspects the existing private Direct continuation, Codex session events and
the exact G0 Direct one-off Docker container. Does NOT invoke/retry a model,
modify either journal, manage containers, run DDEV, or execute the Drupal task.

  inspect --expected-sha CURRENT_PCP_MAIN_SHA
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
CONTINUATION_SCRIPT = ROOT / "scripts/g0-direct-only-parity-continuation.py"
ORIGINAL_DIRECT_ATTEMPT_SHA = "d2f86c3d541bf7294a2378494e2ff031ec298fbe"


def _module(path: Path):
    spec = importlib.util.spec_from_file_location("g0_continuation_forensics", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("G0 direct continuation source unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cont = _module(CONTINUATION_SCRIPT)
g0 = cont.g0


def _failed_direct_attempt() -> tuple[dict, float]:
    root = Path.home() / ".pcp-g0d01"
    for directory in (root, root / "provider", cont.auth._auth_dir("direct")):
        cont._private_file_guard(directory, is_dir=True)
    path = cont._continuation_path()
    cont._private_file_guard(path, is_dir=False)
    attempt = cont._read_continuation()
    if not isinstance(attempt, dict) or not (
        attempt.get("state") == "failed"
        and attempt.get("error_class") == "g0_direct_model_or_wrapper_timeout"
        and attempt.get("source_sha") == ORIGINAL_DIRECT_ATTEMPT_SHA
        and attempt.get("original_journal_status") == "failed"
        and attempt.get("direct_attempted") is True
        and attempt.get("direct_completed") is False
        and attempt.get("ready_to_dispatch_g0d_t01") is False
        and isinstance(attempt.get("pcp"), dict)
        and attempt["pcp"].get("pcp_turn_reconciled") is True
    ):
        raise g0.GateError("g0_direct_failed_continuation_not_exact")
    return attempt, path.stat().st_mtime


def _container_state() -> str:
    # Never use docker ps, compose up, stop, rm, or unscoped resource operations.
    if not g0.exists("container", cont.DIRECT_CONTAINER):
        return "absent"
    data = g0.inspect("container", cont.DIRECT_CONTAINER)
    labels = (data.get("Config") or {}).get("Labels") or {}
    networks = (data.get("NetworkSettings") or {}).get("Networks") or {}
    state = data.get("State") or {}
    if (
        data.get("Name") != "/" + cont.DIRECT_CONTAINER
        or labels.get("com.docker.compose.project") != g0.PROJECT
        or labels.get("com.docker.compose.service") != "auth_direct"
        or set(networks) != {cont.auth.G0_AUTH_NETWORKS["direct"]}
        or not isinstance(state.get("Running"), bool)
    ):
        raise g0.GateError("g0_direct_container_identity_unverified")
    return "running" if state["Running"] else "not_running"


def _parse_direct_rollout(path: Path, failed_mtime: float) -> dict:
    cli_match = False
    contexts = []
    canonical = []
    terminal = []
    token_seen = False
    error_seen = False
    count = 0
    before = path.stat()
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for position, line in enumerate(stream):
            if position >= 10000 or len(line) > 200_000:
                raise g0.GateError("g0_direct_session_event_limit")
            count += 1
            try:
                event = json.loads(line)
            except (TypeError, ValueError) as exc:
                raise g0.GateError("g0_direct_session_event_invalid") from exc
            if not isinstance(event, dict):
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            kind = event.get("type")
            if kind == "session_meta":
                cli_match = cli_match or payload.get("cli_version") in (
                    cont.original.EXPECTED_CLI,
                    "codex-cli " + cont.original.EXPECTED_CLI,
                )
            elif kind == "turn_context":
                contexts.append((
                    payload.get("model") == cont.original.EXPECTED_MODEL,
                    payload.get("effort") == cont.original.EXPECTED_EFFORT,
                ))
            elif kind == "response_item":
                text = cont._canonical_user(payload)
                if text is not None:
                    canonical.append((position, text == cont.original.PROBE_PROMPT))
            elif kind == "event_msg":
                typ = payload.get("type")
                if typ in {"error", "turn_aborted", "stream_error"}:
                    error_seen = True
                elif typ == "token_count":
                    token_seen = True
                elif typ == "task_complete":
                    stamp = cont._date(
                        payload.get("completed_at")
                    ) or cont._date(event.get("timestamp"))
                    terminal.append((
                        position,
                        payload.get("last_agent_message")
                        == cont.original.EXPECTED_RESPONSE,
                        stamp,
                    ))
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise g0.GateError("g0_direct_session_changed_during_read")

    prompts = [pos for pos, exact in canonical if exact]
    after_prompt = sum(
        1 for pos, exact in canonical
        if not exact and prompts and pos > prompts[0]
    )
    delta = (
        failed_mtime - terminal[0][2].timestamp()
        if len(terminal) == 1 and terminal[0][2] is not None else None
    )
    gates = {
        "cli_match": cli_match,
        "model_and_effort_match": len(contexts) == 1
            and contexts[0] == (True, True),
        "one_exact_canonical_prompt": len(prompts) == 1,
        "no_other_user_input_after_prompt": len(prompts) == 1
            and after_prompt == 0,
        "one_terminal_after_prompt": len(terminal) == 1
            and len(prompts) == 1 and prompts[0] < terminal[0][0],
        "exact_response": len(terminal) == 1 and terminal[0][1],
        "token_count_present": token_seen,
        "completion_before_failed_journal": delta is not None
            and -10 <= delta <= 1800,
        "no_error_or_abort": not error_seen,
    }
    return {
        "session_events_examined": count,
        "canonical_user_item_count": len(canonical),
        "gates": gates,
        "direct_turn_reconciled": all(gates.values()),
    }


def inspect(repo: Path, fixture: Path, expected_sha: str) -> dict:
    # Read-only environment gate; deliberately does not call the old status()
    # because that demands an ABSENT Direct container after a timeout.
    cont.original._prepared_context(repo, fixture, expected_sha)
    cont._original_failed_journal()
    pcp = cont._reconcile_existing_session()
    if pcp.get("pcp_turn_reconciled") is not True:
        raise g0.GateError("g0_original_pcp_completion_not_reconciled")
    _, failed_mtime = _failed_direct_attempt()
    state = _container_state()

    profile = cont.auth._auth_dir("direct")
    sessions = profile / "sessions"
    if sessions.is_symlink() or not sessions.is_dir():
        raise g0.GateError("g0_direct_sessions_directory_missing")

    matches = []
    for item in sessions.glob("*/*/*/rollout-*.jsonl"):
        if item.is_symlink() or not item.is_file():
            continue
        meta = item.stat()
        if (
            meta.st_uid == os.getuid()
            and 0 < meta.st_size <= 4_000_000
            and abs(meta.st_mtime - failed_mtime) <= 1800
            and item.resolve().is_relative_to(profile.resolve())
            and not any(p.is_symlink() for p in item.parents
                        if p != profile and p.is_relative_to(profile))
        ):
            matches.append(item)
            if len(matches) > 32:
                raise g0.GateError("g0_direct_session_candidate_limit")
    evidence = (
        _parse_direct_rollout(matches[0], failed_mtime)
        if len(matches) == 1 else None
    )
    complete = evidence is not None and evidence["direct_turn_reconciled"]
    safe_container = state != "running"
    passed = bool(complete and safe_container)
    reason = (
        None if passed else
        "g0_direct_container_still_running" if not safe_container else
        "g0_direct_session_not_unique" if len(matches) != 1 else
        "g0_direct_session_attribution_inconclusive"
    )
    return {
        "status": "PASS" if passed else "STOP",
        "phase": "g0_direct_timeout_forensics",
        "reason": reason,
        "project": g0.PROJECT,
        "source_sha": expected_sha,
        "attempt_source_sha": ORIGINAL_DIRECT_ATTEMPT_SHA,
        "original_wrapper_status": "failed",
        "direct_wrapper_status": "failed_timeout",
        "original_failed_journal_preserved": True,
        "direct_failed_journal_preserved": True,
        "direct_container_state": state,
        "direct_session_candidates": len(matches),
        "direct_evidence": evidence,
        "model_calls_this_command": 0,
        "direct_retry_authorized": False,
        "ready_to_dispatch_g0d_t01": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect",))
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    repo = Path.home() / "personal-coding-platform-v1"
    fixture = Path.home() / "pcp-g0-fixtures/pcp-g0-drupal-fixture"
    try:
        report = inspect(repo, fixture, args.expected_sha)
    except (g0.GateError, OSError, ValueError, TypeError, KeyError) as exc:
        report = {
            "status": "STOP",
            "phase": "g0_direct_timeout_forensics",
            "reason": str(exc) if isinstance(exc, g0.GateError)
                      else "g0_direct_forensics_validation_error",
            "do_not_retry_blindly": True,
            "model_calls_this_command": 0,
            "ready_to_dispatch_g0d_t01": False,
        }
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
