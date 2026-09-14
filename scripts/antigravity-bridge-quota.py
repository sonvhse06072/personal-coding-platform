#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
from http.server import ThreadingHTTPServer
from typing import Any


_LIVE_PATH = Path(__file__).with_name("antigravity-bridge-live.py")
_SPEC = importlib.util.spec_from_file_location("pcp_antigravity_bridge_live", _LIVE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load {_LIVE_PATH}")
live = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(live)


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
                    snapshot = _read_quota_snapshot()
                    return self.send_json(200, {
                        "status": "ok" if snapshot is not None else "unknown",
                        "source": "antigravity_statusline",
                        "capture_configured": _statusline_capture_configured(bridge.settings),
                        "snapshot": snapshot,
                    })
                if self.path == "/health":
                    safe, safety = live.legacy.settings_status(bridge.settings)
                    with bridge._runs_lock:
                        active_runs = len(bridge._runs)
                        pending_cancellations = len(bridge._cancelled_runs)
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
                        "quota_capture_configured": _statusline_capture_configured(bridge.settings),
                        "quota_snapshot_available": _read_quota_snapshot() is not None,
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
