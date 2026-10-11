#!/usr/bin/env python3
"""G0-only real provider parity probe, NOT a benchmark WorkOrder.

  status --expected-sha SHA    read-only source/auth/image/CLI/empty-DB gates
  probe  --expected-sha SHA    exactly one short model call per G0-only arm

The explicit probe uses ephemeral non-root read-only Codex containers, separate
private ChatGPT CODEX_HOME roots, and the SAME versioned model/effort. No
fixture source or workspace is mounted, no GitHub credential or host Codex
state is touched, and no G0 Runtime/Executor mode is changed.

Real model calls consume quota and contact the provider. The Owner runs the
probe explicitly. A private 0600 journal prevents silent retries after errors.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
AUTH_SCRIPT = ROOT / "scripts/g0-codex-auth-operator.py"
EXPECTED_MODEL = "gpt-6-luna"
EXPECTED_EFFORT = "medium"
EXPECTED_CLI = "0.160.0"
EXPECTED_RESPONSE = "G0_PARITY_READY"
JOURNAL_NAME = "model-parity-probe.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("G0 parity authentication module missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = _load_module("g0_codex_auth_operator", AUTH_SCRIPT)
g0 = auth.g0


def _journal_path() -> Path:
    return Path.home() / ".pcp-g0d01" / JOURNAL_NAME


def _read_existing_journal() -> dict | None:
    path = _journal_path()
    if not path.exists() and not path.is_symlink():
        return None
    return auth.upgrader._read_json_secure(path)


def _write_report(record: dict) -> None:
    auth.upgrader._private_write(_journal_path(), record)


def _prepared_context(repo: Path, fixture: Path, sha: str) -> tuple[dict[str, str], dict]:
    env, status = auth._context(repo, fixture, sha, require_prepared=True)
    auth._verify_rendered_tmpfs_mounts(repo, env)
    if status.get("deployed_source_sha") != auth.DEPLOYED_SHA:
        raise g0.GateError("g0_deployed_image_source_mismatch")
    if status.get("installed_codex_cli_version") != EXPECTED_CLI:
        raise g0.GateError("g0_codex_cli_parity_mismatch")
    if auth._auth_dir("pcp") == auth._auth_dir("direct"):
        raise g0.GateError("g0_separate_auth_roots_not_proven")
    for arm in ("pcp", "direct"):
        if auth._check_config(arm) is not True:
            raise g0.GateError("g0_auth_cache_missing_" + arm)
    return env, status


def status(repo: Path, fixture: Path, sha: str) -> dict:
    _, evidence = _prepared_context(repo, fixture, sha)
    prior = _read_existing_journal()
    return {
        "status": "PASS",
        "phase": "g0_model_parity_preflight",
        "project": g0.PROJECT,
        "source_sha": sha,
        "deployed_source_sha": evidence["deployed_source_sha"],
        "fixture_seed": g0.SEED,
        "pcp_cached_auth_present": True,
        "direct_cached_auth_present": True,
        "model": EXPECTED_MODEL,
        "reasoning_effort": EXPECTED_EFFORT,
        "codex_cli_version": EXPECTED_CLI,
        "prior_parity_probe": None if prior is None else prior.get("state"),
        "same_provider_account_or_quota_proven": False,
        "model_entitlement_verified": prior is not None and prior.get("state") == "completed",
        "model_calls_this_command": 0,
        "ready_to_dispatch_g0d_t01": False,
    }


PROBE_PROMPT = (
    "This is a short G0 model capability check, not a coding task. "
    "Respond with exactly G0_PARITY_READY. Do not call tools, read files, "
    "change configuration, or perform network requests."
)


def _probe_command(repo: Path, arm: str) -> list[str]:
    if arm not in {"pcp", "direct"}:
        raise g0.GateError("g0_parity_arm_invalid")
    return auth._compose(repo) + [
        "run", "--rm", "--no-deps", "-T", "auth_" + arm,
        "exec", "--json", "--sandbox", "read-only",
        "--skip-git-repo-check", "--cd", "/tmp",
        "--model", EXPECTED_MODEL,
        "--config", f'model_reasoning_effort="{EXPECTED_EFFORT}"',
        "--config", 'approval_policy="never"',
        "--config", "features.memories=false",
        "--config", "memories.use_memories=false",
        "--config", "memories.generate_memories=false",
        PROBE_PROMPT,
    ]


def _parse_result(stdout: str, *, exit_code: int) -> dict:
    if exit_code != 0:
        raise g0.GateError("g0_provider_probe_process_failed")
    if len(stdout) > 1_000_000:
        raise g0.GateError("g0_provider_probe_output_oversized")
    terminal = None
    reply = ""
    usage = {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") in {"error", "turn.failed", "item.failed"}:
            raise g0.GateError("g0_provider_probe_reported_failure")
        if event.get("type") == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                reply = str(item.get("text", "")).strip()
        if event.get("type") == "turn.completed":
            terminal = "completed"
            data = event.get("usage")
            if isinstance(data, dict):
                usage = {
                    k: v for k, v in data.items()
                    if k in {"input_tokens", "cached_input_tokens", "output_tokens"}
                    and type(v) is int and 0 <= v <= 2_000_000
                }
    if terminal != "completed" or reply != EXPECTED_RESPONSE:
        raise g0.GateError("g0_provider_model_or_response_unverified")
    return {"terminal": "completed", "response_verified": True, "usage": usage}


def _run_probe(repo: Path, env: dict[str, str], arm: str) -> dict:
    argv = _probe_command(repo, arm)
    started = time.monotonic()
    try:
        result = subprocess.run(
            argv, env=env, capture_output=True, text=True,
            timeout=150, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise g0.GateError("g0_provider_probe_unavailable_or_timeout") from exc
    # Never report raw stderr/stdout, rendered Compose, OAuth tokens or headers.
    parsed = _parse_result(result.stdout, exit_code=result.returncode)
    return {
        "arm": arm, **parsed,
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }


def probe(repo: Path, fixture: Path, sha: str) -> dict:
    env, _ = _prepared_context(repo, fixture, sha)
    if _read_existing_journal() is not None:
        raise g0.GateError("g0_parity_probe_already_recorded_do_not_retry")
    auth.g0.require_headroom(repo)
    results: list[dict] = []
    record = {
        "state": "started", "source_sha": sha,
        "model": EXPECTED_MODEL, "reasoning_effort": EXPECTED_EFFORT,
        "codex_cli_version": EXPECTED_CLI,
        "attempted_arms": [], "completed_arms": [],
        "ready_to_dispatch_g0d_t01": False,
    }
    _write_report(record)
    for arm in ("pcp", "direct"):
        record["attempted_arms"].append(arm)
        _write_report(record)
        try:
            item = _run_probe(repo, env, arm)
        except g0.GateError:
            record["state"] = "failed"
            record["failed_arm"] = arm
            _write_report(record)
            raise
        results.append(item)
        record["completed_arms"].append(arm)
        record["results"] = list(results)
        _write_report(record)
    record["state"] = "completed"
    _write_report(record)
    return {
        "status": "PASS", "phase": "g0_model_parity_probe",
        "project": g0.PROJECT, "source_sha": sha,
        "model": EXPECTED_MODEL, "reasoning_effort": EXPECTED_EFFORT,
        "codex_cli_version": EXPECTED_CLI,
        "model_calls_attempted": 2,
        "both_provider_requests_completed": True,
        "arms": results,
        "same_account_or_quota_proven": False,
        "ready_to_dispatch_g0d_t01": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("status", "probe"))
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    repo = Path.home() / "personal-coding-platform-v1"
    fixture = Path.home() / "pcp-g0-fixtures/pcp-g0-drupal-fixture"
    try:
        if args.mode == "status":
            report = status(repo, fixture, args.expected_sha)
        else:
            report = probe(repo, fixture, args.expected_sha)
    except (g0.GateError, OSError, ValueError, TypeError, KeyError) as exc:
        reason = str(exc) if isinstance(exc, g0.GateError) else "unexpected_g0_parity_validation_error"
        print(json.dumps({
            "status": "STOP", "phase": args.mode, "reason": reason,
            "do_not_retry_blindly": True,
            "ready_to_dispatch_g0d_t01": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
