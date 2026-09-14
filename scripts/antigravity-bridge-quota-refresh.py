#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from http.server import ThreadingHTTPServer
from typing import Any


_BASE_PATH = Path(__file__).with_name("antigravity-bridge-quota.py")
_SPEC = importlib.util.spec_from_file_location("pcp_antigravity_bridge_quota", _BASE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load {_BASE_PATH}")
quota18 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(quota18)

# Antigravity CLI 1.1.11 introduced read-only slash-command handling in print
# mode. Older releases could interpret `/usage` as an ordinary model prompt, so
# never run the proactive CLI quota probe below this version.
_MIN_SAFE_PRINT_USAGE = (1, 1, 11)
_VERSION_RE = re.compile(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)")
_CLI_TIMEOUT_SECONDS = 20
_MAX_GROUPS = 16
_MAX_BUCKETS = 64


def _safe_env() -> dict[str, str]:
    """Pass only session variables needed by the signed-in CLI/keyring."""
    allowed = (
        "HOME",
        "PATH",
        "USER",
        "LOGNAME",
        "SHELL",
        "LANG",
        "LC_ALL",
        "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS",
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "WSL_DISTRO_NAME",
    )
    return {key: os.environ[key] for key in allowed if os.environ.get(key)}


def _real_agy() -> str | None:
    configured = os.getenv("ANTIGRAVITY_REAL_AGY_BIN", "").strip()
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which("agy")
    return found or None


def _agy_version(binary: str) -> tuple[int, int, int] | None:
    try:
        completed = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            env=_safe_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = _VERSION_RE.search(f"{completed.stdout}\n{completed.stderr}")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _print_usage_supported(binary: str) -> tuple[bool, tuple[int, int, int] | None]:
    version = _agy_version(binary)
    return bool(version and version >= _MIN_SAFE_PRINT_USAGE), version


def _usage_snapshot_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize only Antigravity's structured read-only `/usage` payload."""
    command = payload.get("command")
    data = command.get("data") if isinstance(command, dict) else None
    groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(groups, list):
        return None

    quota: dict[str, Any] = {}
    bucket_count = 0
    for group in groups[:_MAX_GROUPS]:
        if not isinstance(group, dict):
            continue
        group_name = str(group.get("name") or "").strip()[:120]
        buckets = group.get("buckets")
        if not isinstance(buckets, list):
            continue
        for bucket in buckets:
            if bucket_count >= _MAX_BUCKETS:
                break
            if not isinstance(bucket, dict):
                continue
            remaining = bucket.get("remaining_fraction")
            if not isinstance(remaining, (int, float)) or isinstance(remaining, bool):
                continue
            bucket_id = str(bucket.get("id") or "").strip()[:120]
            if not bucket_id:
                continue
            window = str(bucket.get("window") or "").strip()[:80]
            # Include the provider-visible group in the quota key so Runtime can
            # distinguish Gemini from Claude/GPT shared pools without inventing a
            # relationship between individual models.
            key_parts = [part for part in (group_name, bucket_id) if part]
            quota_id = " / ".join(key_parts)
            entry: dict[str, Any] = {
                "remaining_fraction": max(0.0, min(1.0, float(remaining))),
            }
            reset = bucket.get("reset_time")
            if isinstance(reset, str) and reset.strip():
                entry["reset_time"] = reset.strip()[:80]
            if window:
                entry["window"] = window
            quota[quota_id] = entry
            bucket_count += 1

    if not quota:
        return None

    plan = data.get("plan") or data.get("plan_type") or data.get("planTier")
    plan_tier = str(plan).strip()[:80] if isinstance(plan, str) and plan.strip() else None
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "quota": quota,
        "plan_tier": plan_tier,
        "source_contract": "cli_print_usage_json",
    }


def _read_cli_usage(binary: str) -> tuple[dict[str, Any] | None, str]:
    supported, version = _print_usage_supported(binary)
    version_text = ".".join(str(part) for part in version) if version else "unknown"
    if not supported:
        return None, f"unsupported_cli_version:{version_text}"

    # Use an empty temporary cwd so repository-local agents/plugins cannot affect
    # this read-only quota command. The command is handled by the CLI itself and
    # must return the structured `command.data` envelope; anything else is dropped.
    try:
        with tempfile.TemporaryDirectory(prefix="pcp-agy-quota-") as cwd:
            completed = subprocess.run(
                [binary, "-p", "/usage", "--output-format", "json"],
                cwd=cwd,
                env=_safe_env(),
                capture_output=True,
                text=True,
                timeout=_CLI_TIMEOUT_SECONDS,
                check=False,
            )
    except subprocess.TimeoutExpired:
        return None, "cli_usage_timeout"
    except OSError:
        return None, "cli_usage_unavailable"

    if completed.returncode != 0:
        return None, "cli_usage_failed"
    try:
        payload = json.loads(completed.stdout, strict=False)
    except (json.JSONDecodeError, TypeError):
        return None, "cli_usage_invalid_json"
    if not isinstance(payload, dict):
        return None, "cli_usage_invalid_payload"
    snapshot = _usage_snapshot_from_payload(payload)
    return (snapshot, "ok") if snapshot is not None else (None, "cli_usage_no_data")


class QuotaRefreshBridge(quota18.QuotaBridge):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._real_agy_bin = _real_agy()
        if self._real_agy_bin:
            self._cli_supported, self._cli_version = _print_usage_supported(self._real_agy_bin)
        else:
            self._cli_supported, self._cli_version = False, None

    def handler(self):
        bridge = self
        ParentHandler = super().handler()

        class Handler(ParentHandler):
            server_version = "PersonalCodingAntigravityBridge/1.9"

            def do_GET(self):
                if not self.authorized():
                    return self.send_json(401, {"error": "unauthorized"})
                if self.path == "/quota":
                    live_snapshot = quota18._read_live_quota()
                    cli_snapshot = None
                    cli_status = "not_needed"
                    if live_snapshot is None and bridge._real_agy_bin:
                        cli_snapshot, cli_status = _read_cli_usage(bridge._real_agy_bin)
                    cached_snapshot = None
                    if live_snapshot is None and cli_snapshot is None:
                        cached_snapshot = quota18._read_quota_snapshot()
                    snapshot = live_snapshot or cli_snapshot or cached_snapshot
                    if live_snapshot is not None:
                        source = "antigravity_local_status"
                        source_supported = False
                    elif cli_snapshot is not None:
                        source = "antigravity_cli_usage"
                        source_supported = True
                    else:
                        source = "antigravity_statusline"
                        source_supported = True
                    return self.send_json(200, {
                        "status": "ok" if snapshot is not None else "unknown",
                        "source": source,
                        "source_supported": source_supported,
                        "capture_configured": quota18._statusline_capture_configured(bridge.settings),
                        "cli_refresh_supported": bridge._cli_supported,
                        "cli_refresh_status": cli_status,
                        "snapshot": snapshot,
                    })
                if self.path == "/health":
                    safe, safety = quota18.live.legacy.settings_status(bridge.settings)
                    with bridge._runs_lock:
                        active_runs = len(bridge._runs)
                        pending_cancellations = len(bridge._cancelled_runs)
                    snapshot_available = quota18._read_quota_snapshot() is not None
                    version_text = (
                        ".".join(str(part) for part in bridge._cli_version)
                        if bridge._cli_version else None
                    )
                    return self.send_json(200 if safe else 503, {
                        "status": "ok" if safe else "degraded",
                        "service": "antigravity-host-bridge",
                        "version": "1.9",
                        "agy": bridge.agy_bin,
                        "workspaces": str(bridge.workspaces),
                        "active_runs": active_runs,
                        "pending_cancellations": pending_cancellations,
                        "safe_settings": safe,
                        "streaming": True,
                        "quota": True,
                        "quota_live_probe": True,
                        "quota_cli_refresh": True,
                        "quota_cli_refresh_supported": bridge._cli_supported,
                        "antigravity_cli_version": version_text,
                        "quota_capture_configured": quota18._statusline_capture_configured(bridge.settings),
                        "quota_snapshot_available": snapshot_available,
                        "safety": safety,
                    })
                return super().do_GET()

        return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8792)
    parser.add_argument("--token", required=True)
    parser.add_argument("--workspaces", required=True)
    parser.add_argument("--agy-bin", default="")
    parser.add_argument("--settings", required=True)
    args = parser.parse_args()

    agy_bin = args.agy_bin or shutil.which("agy") or ""
    if not agy_bin or not Path(agy_bin).exists():
        raise SystemExit("agy not found on WSL host. Install/login Antigravity first.")
    workspaces = Path(args.workspaces).expanduser().resolve()
    workspaces.mkdir(parents=True, exist_ok=True)
    settings = Path(args.settings).expanduser()
    safe, safety = quota18.live.legacy.settings_status(settings)
    if not safe:
        raise SystemExit(f"Unsafe Antigravity settings: {json.dumps(safety, sort_keys=True)}")
    bridge = QuotaRefreshBridge(
        token=args.token,
        workspaces=workspaces,
        agy_bin=agy_bin,
        settings=settings,
    )
    server = ThreadingHTTPServer((args.host, args.port), bridge.handler())
    print(
        f"Antigravity host bridge 1.9 listening on {args.host}:{args.port}; "
        "safe_settings=true; streaming=true; quota=true; quota_cli_refresh=true",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
