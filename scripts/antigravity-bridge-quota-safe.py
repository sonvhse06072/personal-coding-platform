#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
from http.server import ThreadingHTTPServer


_BASE_PATH = Path(__file__).with_name("antigravity-bridge-quota-refresh.py")
_SPEC = importlib.util.spec_from_file_location("pcp_antigravity_bridge_quota_refresh", _BASE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load {_BASE_PATH}")
quota19 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(quota19)


def _settings_snapshot(path: Path) -> tuple[bytes, int]:
    raw = path.read_bytes()
    mode = path.stat().st_mode & 0o777
    return raw, mode


def _restore_settings(path: Path, raw: bytes, mode: int) -> None:
    try:
        current_raw = path.read_bytes()
        current_mode = path.stat().st_mode & 0o777
    except OSError:
        current_raw = None
        current_mode = None
    if current_raw == raw and current_mode == mode:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.pcp-quota-restore-", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _read_cli_usage_preserving_settings(
    binary: str,
    settings: Path,
) -> tuple[dict | None, str]:
    try:
        original_raw, original_mode = _settings_snapshot(settings)
    except OSError:
        return None, "settings_snapshot_failed"

    snapshot = None
    status = "cli_usage_error"
    try:
        snapshot, status = quota19._read_cli_usage(binary)
    except Exception as exc:
        status = f"cli_usage_error:{type(exc).__name__}"
    finally:
        try:
            _restore_settings(settings, original_raw, original_mode)
        except OSError:
            return None, "settings_restore_failed"
    return snapshot, status


class SafeQuotaRefreshBridge(quota19.QuotaRefreshBridge):
    def handler(self):
        bridge = self
        ParentHandler = super().handler()

        class Handler(ParentHandler):
            server_version = "PersonalCodingAntigravityBridge/1.10"

            def do_GET(self):
                if not self.authorized():
                    return self.send_json(401, {"error": "unauthorized"})
                if self.path == "/quota":
                    live_snapshot = quota19.quota18._read_live_quota()
                    cli_snapshot = None
                    cli_status = "not_needed"
                    if live_snapshot is None and bridge._real_agy_bin:
                        # Antigravity jobs and quota probes share one signed-in global
                        # settings file. Serialize them, then restore that file exactly
                        # because the CLI may normalize/drop keys while serving /usage.
                        with bridge._agy_lock:
                            cli_snapshot, cli_status = _read_cli_usage_preserving_settings(
                                bridge._real_agy_bin,
                                bridge.settings,
                            )
                    cached_snapshot = None
                    if live_snapshot is None and cli_snapshot is None:
                        cached_snapshot = quota19.quota18._read_quota_snapshot()
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
                        "capture_configured": quota19.quota18._statusline_capture_configured(bridge.settings),
                        "cli_refresh_supported": bridge._cli_supported,
                        "cli_refresh_status": cli_status,
                        "snapshot": snapshot,
                    })
                if self.path == "/health":
                    safe, safety = quota19.quota18.live.legacy.settings_status(bridge.settings)
                    with bridge._runs_lock:
                        active_runs = len(bridge._runs)
                        pending_cancellations = len(bridge._cancelled_runs)
                    snapshot_available = quota19.quota18._read_quota_snapshot() is not None
                    version_text = (
                        ".".join(str(part) for part in bridge._cli_version)
                        if bridge._cli_version else None
                    )
                    return self.send_json(200 if safe else 503, {
                        "status": "ok" if safe else "degraded",
                        "service": "antigravity-host-bridge",
                        "version": "1.10",
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
                        "quota_capture_configured": quota19.quota18._statusline_capture_configured(bridge.settings),
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
    parser.add_argument("--direct-workspace", default="")
    parser.add_argument("--agy-bin", default="")
    parser.add_argument("--settings", required=True)
    args = parser.parse_args()

    agy_bin = args.agy_bin or shutil.which("agy") or ""
    if not agy_bin or not Path(agy_bin).exists():
        raise SystemExit("agy not found on WSL host. Install/login Antigravity first.")
    workspaces = Path(args.workspaces).expanduser().resolve()
    workspaces.mkdir(parents=True, exist_ok=True)
    settings = Path(args.settings).expanduser()
    safe, safety = quota19.quota18.live.legacy.settings_status(settings)
    if not safe:
        raise SystemExit(f"Unsafe Antigravity settings: {json.dumps(safety, sort_keys=True)}")
    direct_workspace = (
        Path(args.direct_workspace).expanduser().resolve()
        if str(args.direct_workspace).strip()
        else None
    )
    bridge = SafeQuotaRefreshBridge(
        token=args.token,
        workspaces=workspaces,
        agy_bin=agy_bin,
        settings=settings,
        direct_workspace=direct_workspace,
    )
    server = ThreadingHTTPServer((args.host, args.port), bridge.handler())
    print(
        f"Antigravity host bridge 1.10 listening on {args.host}:{args.port}; "
        "safe_settings=true; streaming=true; quota=true; quota_cli_refresh=true; settings_restore=true",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
