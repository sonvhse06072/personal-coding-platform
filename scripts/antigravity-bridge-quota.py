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
import ssl
import subprocess
from http.server import ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


_LIVE_PATH = Path(__file__).with_name("antigravity-bridge-live.py")
_SPEC = importlib.util.spec_from_file_location("pcp_antigravity_bridge_live", _LIVE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load {_LIVE_PATH}")
live = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(live)

_QUOTA_PATH = "/exa.language_server_pb.LanguageServerService/GetUserStatus"
_METADATA = {
    "metadata": {
        "ideName": "antigravity",
        "extensionName": "antigravity",
        "ideVersion": "unknown",
        "locale": "en",
    }
}
_MAX_MODELS = 32


def _quota_path() -> Path:
    return Path(
        os.getenv(
            "ANTIGRAVITY_QUOTA_SNAPSHOT",
            str(Path.home() / ".coding-platform" / "antigravity-quota.json"),
        )
    ).expanduser()


def _statusline_capture_configured(settings: Path) -> bool:
    sink = os.getenv("ANTIGRAVITY_QUOTA_SINK", "").strip()
    if not sink:
        return False
    try:
        payload = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    statusline = payload.get("statusLine") if isinstance(payload, dict) else None
    return bool(
        isinstance(statusline, dict)
        and statusline.get("type") == "command"
        and str(statusline.get("command") or "").strip() == sink
        and statusline.get("enabled", True) is not False
    )


def _read_quota_snapshot() -> dict[str, Any] | None:
    path = _quota_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or not isinstance(value.get("quota"), dict):
        return None
    return value


def _proc_args(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [item.decode("utf-8", errors="replace") for item in raw.split(b"\0") if item]


def _arg_value(args: list[str], name: str) -> str | None:
    prefix = f"{name}="
    for index, arg in enumerate(args):
        if arg.startswith(prefix):
            return arg[len(prefix):]
        if arg == name and index + 1 < len(args):
            return args[index + 1]
    return None


def _language_servers() -> list[tuple[int, str, int | None]]:
    result: list[tuple[int, str, int | None]] = []
    proc = Path("/proc")
    try:
        entries = list(proc.iterdir())
    except OSError:
        return result
    for entry in entries:
        if not entry.name.isdigit():
            continue
        args = _proc_args(int(entry.name))
        command = " ".join(args).lower()
        if "language_server" not in command or "antigravity" not in command:
            continue
        token = _arg_value(args, "--csrf_token")
        if not token:
            continue
        port_raw = _arg_value(args, "--extension_server_port")
        try:
            port = int(port_raw) if port_raw else None
        except ValueError:
            port = None
        result.append((int(entry.name), token, port))
    return result


def _ports_from_ss(pid: int) -> list[int]:
    binary = shutil.which("ss")
    if not binary:
        return []
    try:
        completed = subprocess.run(
            [binary, "-ltnpH"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    ports: list[int] = []
    marker = f"pid={pid},"
    for line in completed.stdout.splitlines():
        if marker not in line:
            continue
        before_process = line.split("users:", 1)[0]
        matches = re.findall(r":(\d+)\s", before_process + " ")
        for match in matches:
            port = int(match)
            if 0 < port < 65536 and port not in ports:
                ports.append(port)
    return ports


def _ports_from_lsof(pid: int) -> list[int]:
    binary = shutil.which("lsof")
    if not binary:
        return []
    try:
        completed = subprocess.run(
            [binary, "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    ports: list[int] = []
    for line in completed.stdout.splitlines()[1:]:
        match = re.search(r":(\d+)\s+\(LISTEN\)", line)
        if not match:
            continue
        port = int(match.group(1))
        if port not in ports:
            ports.append(port)
    return ports


def _candidate_ports(pid: int, extension_port: int | None) -> list[int]:
    ports: list[int] = []
    if extension_port and 0 < extension_port < 65536:
        ports.append(extension_port)
    for port in [*_ports_from_ss(pid), *_ports_from_lsof(pid)]:
        if port not in ports:
            ports.append(port)
    return ports[:12]


def _local_status(port: int, token: str) -> dict[str, Any] | None:
    body = json.dumps(_METADATA, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Connect-Protocol-Version": "1",
        "X-Codeium-Csrf-Token": token,
    }
    for scheme in ("https", "http"):
        request = Request(
            f"{scheme}://127.0.0.1:{port}{_QUOTA_PATH}",
            data=body,
            headers=headers,
            method="POST",
        )
        context = ssl._create_unverified_context() if scheme == "https" else None
        try:
            with urlopen(request, timeout=2.0, context=context) as response:
                if response.status != 200:
                    continue
                value = json.loads(response.read(1_000_000).decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            return value
    return None


def _safe_text(value: Any, limit: int = 160) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:limit]


def _sanitize_local_status(payload: dict[str, Any]) -> dict[str, Any] | None:
    user_status = payload.get("userStatus")
    if not isinstance(user_status, dict):
        return None
    cascade = user_status.get("cascadeModelConfigData")
    configs = cascade.get("clientModelConfigs") if isinstance(cascade, dict) else None
    if not isinstance(configs, list):
        return None
    quota: dict[str, Any] = {}
    for item in configs[:_MAX_MODELS]:
        if not isinstance(item, dict):
            continue
        info = item.get("quotaInfo")
        if not isinstance(info, dict):
            continue
        remaining = info.get("remainingFraction")
        if not isinstance(remaining, (int, float)) or isinstance(remaining, bool):
            continue
        label = _safe_text(item.get("label"))
        model_or_alias = item.get("modelOrAlias")
        upstream = _safe_text(model_or_alias.get("model")) if isinstance(model_or_alias, dict) else None
        quota_id = label or upstream
        if not quota_id:
            continue
        entry: dict[str, Any] = {
            "remaining_fraction": max(0.0, min(1.0, float(remaining))),
        }
        reset_time = _safe_text(info.get("resetTime"), 80)
        if reset_time:
            entry["reset_time"] = reset_time
        if upstream:
            entry["upstream_model"] = upstream
        quota[quota_id] = entry
    if not quota:
        return None
    plan_status = user_status.get("planStatus")
    plan_info = plan_status.get("planInfo") if isinstance(plan_status, dict) else None
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "quota": quota,
        "plan_tier": _safe_text(plan_info.get("planName"), 80) if isinstance(plan_info, dict) else None,
        "source_contract": "local_language_server_get_user_status",
    }


def _read_live_quota() -> dict[str, Any] | None:
    # The local language-server endpoint is an internal Antigravity interface.
    # Discovery/auth stay host-local and fail open; CSRF tokens and raw account
    # data are never logged, persisted or returned through the bridge.
    for pid, token, extension_port in _language_servers():
        for port in _candidate_ports(pid, extension_port):
            payload = _local_status(port, token)
            if payload is None:
                continue
            safe = _sanitize_local_status(payload)
            if safe is not None:
                return safe
    return None


class QuotaBridge(live.StreamingBridge):
    def handler(self):
        bridge = self
        LiveHandler = super().handler()

        class Handler(LiveHandler):
            server_version = "PersonalCodingAntigravityBridge/1.8"

            def do_GET(self):
                if not self.authorized():
                    return self.send_json(401, {"error": "unauthorized"})
                if self.path == "/quota":
                    live_snapshot = _read_live_quota()
                    cached_snapshot = _read_quota_snapshot() if live_snapshot is None else None
                    snapshot = live_snapshot or cached_snapshot
                    source = "antigravity_local_status" if live_snapshot is not None else "antigravity_statusline"
                    return self.send_json(200, {
                        "status": "ok" if snapshot is not None else "unknown",
                        "source": source,
                        "source_supported": source == "antigravity_statusline",
                        "capture_configured": _statusline_capture_configured(bridge.settings),
                        "snapshot": snapshot,
                    })
                if self.path == "/health":
                    safe, safety = live.legacy.settings_status(bridge.settings)
                    with bridge._runs_lock:
                        active_runs = len(bridge._runs)
                        pending_cancellations = len(bridge._cancelled_runs)
                    snapshot_available = _read_quota_snapshot() is not None
                    return self.send_json(200 if safe else 503, {
                        "status": "ok" if safe else "degraded",
                        "service": "antigravity-host-bridge",
                        "version": "1.8",
                        "agy": bridge.agy_bin,
                        "workspaces": str(bridge.workspaces),
                        "active_runs": active_runs,
                        "pending_cancellations": pending_cancellations,
                        "safe_settings": safe,
                        "streaming": True,
                        "quota": True,
                        "quota_live_probe": True,
                        "quota_capture_configured": _statusline_capture_configured(bridge.settings),
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
    safe, safety = live.legacy.settings_status(settings)
    if not safe:
        raise SystemExit(f"Unsafe Antigravity settings: {json.dumps(safety, sort_keys=True)}")
    bridge = QuotaBridge(token=args.token, workspaces=workspaces, agy_bin=agy_bin, settings=settings)
    server = ThreadingHTTPServer((args.host, args.port), bridge.handler())
    print(
        f"Antigravity host bridge 1.8 listening on {args.host}:{args.port}; workspaces={workspaces}; safe_settings=true; streaming=true; quota=true",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
