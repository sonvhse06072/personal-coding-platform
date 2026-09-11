#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hmac
import json
import os
import signal
from pathlib import Path
import shutil
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


REQUIRED_SETTINGS = {
    "enableTerminalSandbox": True,
    "toolPermission": "proceed-in-sandbox",
    "artifactReviewPolicy": "always-proceed",
    "allowNonWorkspaceAccess": False,
    "enableTelemetry": False,
}
REQUIRED_ALLOW_RULES = {
    "read_file(.)",
    "write_file(.)",
    "unsandboxed(git status)",
    "unsandboxed(git diff)",
    "unsandboxed(git log)",
    "unsandboxed(git show)",
    "unsandboxed(git ls-files)",
    "unsandboxed(git grep)",
    "unsandboxed(git rev-parse)",
}
REQUIRED_DENY_RULES = {
    "read_file(.git/)",
    "write_file(.git/)",
    "command(ddev)",
    "command(docker)",
    "command(sudo)",
    "unsandboxed(ddev)",
    "unsandboxed(docker)",
    "unsandboxed(sudo)",
    "unsandboxed(git push)",
    "unsandboxed(git fetch)",
    "unsandboxed(git pull)",
    "unsandboxed(git commit)",
    "unsandboxed(git checkout)",
    "unsandboxed(git switch)",
    "unsandboxed(git reset)",
    "unsandboxed(git clean)",
    "unsandboxed(git merge)",
    "unsandboxed(git rebase)",
}
FORBIDDEN_ALLOW_RULES = {"unsandboxed(*)", "read_file(*)", "write_file(*)"}


def contained(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def terminate_process_group(proc: subprocess.Popen, grace_seconds: float = 3.0) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def settings_status(path: Path) -> tuple[bool, dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, {"error": "settings_unreadable", "path": str(path)}
    if not isinstance(raw, dict):
        return False, {"error": "settings_not_object", "path": str(path)}

    mismatches: dict[str, object] = {
        key: {"expected": expected, "actual": raw.get(key)}
        for key, expected in REQUIRED_SETTINGS.items()
        if raw.get(key) != expected
    }

    permissions = raw.get("permissions")
    if not isinstance(permissions, dict):
        permissions = {}
    allow = permissions.get("allow")
    deny = permissions.get("deny")
    allow_rules = set(allow) if isinstance(allow, list) else set()
    deny_rules = set(deny) if isinstance(deny, list) else set()

    missing_allow = sorted(REQUIRED_ALLOW_RULES - allow_rules)
    missing_deny = sorted(REQUIRED_DENY_RULES - deny_rules)
    forbidden_allow = sorted(FORBIDDEN_ALLOW_RULES & allow_rules)
    if missing_allow:
        mismatches["permissions.allow.missing"] = missing_allow
    if missing_deny:
        mismatches["permissions.deny.missing"] = missing_deny
    if forbidden_allow:
        mismatches["permissions.allow.forbidden"] = forbidden_allow

    return not mismatches, {
        "path": str(path),
        "required": REQUIRED_SETTINGS,
        "required_allow_rules": sorted(REQUIRED_ALLOW_RULES),
        "required_deny_rules": sorted(REQUIRED_DENY_RULES),
        "forbidden_allow_rules": sorted(FORBIDDEN_ALLOW_RULES),
        "mismatches": mismatches,
    }


class Bridge:
    def __init__(self, *, token: str, workspaces: Path, agy_bin: str, settings: Path):
        self.token = token
        self.workspaces = workspaces.resolve()
        self.agy_bin = agy_bin
        self.settings = settings.resolve()
        self._runs: dict[str, subprocess.Popen] = {}
        self._runs_lock = threading.Lock()

    def register_run(self, run_id: str, proc: subprocess.Popen) -> None:
        with self._runs_lock:
            self._runs[run_id] = proc

    def unregister_run(self, run_id: str) -> None:
        with self._runs_lock:
            self._runs.pop(run_id, None)

    def cancel_run(self, run_id: str) -> bool:
        with self._runs_lock:
            proc = self._runs.get(run_id)
        if proc is None:
            return False
        terminate_process_group(proc)
        return True

    def cancel_all_runs(self) -> int:
        with self._runs_lock:
            runs = list(self._runs.items())
        for _, proc in runs:
            terminate_process_group(proc)
        return len(runs)

    def handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "PersonalCodingAntigravityBridge/1.4"

            def log_message(self, fmt: str, *args):
                print(f"agy-bridge: {self.address_string()} - {fmt % args}", flush=True)

            def send_json(self, status: int, payload: dict):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def authorized(self) -> bool:
                header = self.headers.get("Authorization", "")
                supplied = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
                return bool(supplied) and hmac.compare_digest(supplied, bridge.token)

            def read_payload(self) -> dict:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                value = json.loads(raw or b"{}")
                if not isinstance(value, dict):
                    raise ValueError("JSON body must be an object")
                return value

            def do_GET(self):
                if not self.authorized():
                    return self.send_json(401, {"error": "unauthorized"})
                if self.path != "/health":
                    return self.send_json(404, {"error": "not_found"})
                safe, safety = settings_status(bridge.settings)
                with bridge._runs_lock:
                    active_runs = len(bridge._runs)
                return self.send_json(200 if safe else 503, {
                    "status": "ok" if safe else "degraded",
                    "service": "antigravity-host-bridge",
                    "version": "1.4",
                    "agy": bridge.agy_bin,
                    "workspaces": str(bridge.workspaces),
                    "active_runs": active_runs,
                    "safe_settings": safe,
                    "safety": safety,
                })

            def do_POST(self):
                if not self.authorized():
                    return self.send_json(401, {"error": "unauthorized"})
                try:
                    payload = self.read_payload()
                    if self.path == "/cancel-all":
                        return self.send_json(200, {"cancelled": bridge.cancel_all_runs()})
                    if self.path == "/cancel":
                        run_id = str(payload.get("run_id") or "").strip()
                        if not run_id:
                            return self.send_json(400, {"error": "run_id_required"})
                        return self.send_json(200, {
                            "run_id": run_id,
                            "cancelled": bridge.cancel_run(run_id),
                        })
                    if self.path != "/run":
                        return self.send_json(404, {"error": "not_found"})

                    safe, safety = settings_status(bridge.settings)
                    if not safe:
                        return self.send_json(503, {
                            "error": "unsafe_antigravity_settings",
                            "safety": safety,
                        })

                    workspace = Path(str(payload["workspace"])).resolve()
                    if not workspace.is_dir() or not contained(workspace, bridge.workspaces):
                        return self.send_json(403, {"error": "workspace_not_allowed"})
                    prompt = str(payload.get("prompt") or "").strip()
                    if not prompt:
                        return self.send_json(400, {"error": "prompt_required"})
                    timeout = max(30, min(int(payload.get("timeout", 900)), 5400))
                    model = str(payload.get("model") or "auto")
                    effort = str(payload.get("effort") or "medium")
                    if effort not in {"low", "medium", "high"}:
                        effort = "medium"
                    run_id = str(payload.get("run_id") or uuid.uuid4().hex).strip()
                    if not run_id or len(run_id) > 128:
                        return self.send_json(400, {"error": "invalid_run_id"})

                    cmd = [
                        bridge.agy_bin,
                        "-p", prompt,
                        "--output-format", "json",
                        "--sandbox",
                        "--effort", effort,
                        "--print-timeout", f"{timeout}s",
                    ]
                    if model and model != "auto":
                        cmd.extend(["--model", model])

                    env = os.environ.copy()
                    env["NO_COLOR"] = "1"
                    proc = subprocess.Popen(
                        cmd,
                        cwd=workspace,
                        env=env,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        start_new_session=True,
                    )
                    bridge.register_run(run_id, proc)
                    try:
                        stdout, stderr = proc.communicate(timeout=timeout + 15)
                    except subprocess.TimeoutExpired:
                        terminate_process_group(proc)
                        stdout, stderr = proc.communicate()
                        return self.send_json(200, {
                            "run_id": run_id,
                            "returncode": 124,
                            "stdout": stdout or "",
                            "stderr": (stderr or "") + "\nAntigravity run timed out",
                            "payload": None,
                        })
                    finally:
                        bridge.unregister_run(run_id)

                    parsed = None
                    try:
                        parsed = json.loads(stdout)
                    except json.JSONDecodeError:
                        pass
                    return self.send_json(200, {
                        "run_id": run_id,
                        "returncode": int(proc.returncode or 0),
                        "stdout": stdout,
                        "stderr": stderr,
                        "payload": parsed,
                    })
                except Exception as exc:
                    return self.send_json(500, {"error": f"{type(exc).__name__}: {exc}"})

        return Handler


def main():
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
    workspaces = Path(args.workspaces).expanduser()
    workspaces.mkdir(parents=True, exist_ok=True)
    settings = Path(args.settings).expanduser()
    safe, safety = settings_status(settings)
    if not safe:
        raise SystemExit(f"Unsafe Antigravity settings: {json.dumps(safety, sort_keys=True)}")
    bridge = Bridge(token=args.token, workspaces=workspaces, agy_bin=agy_bin, settings=settings)
    server = ThreadingHTTPServer((args.host, args.port), bridge.handler())
    print(
        f"Antigravity host bridge listening on {args.host}:{args.port}; workspaces={workspaces}; safe_settings=true",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
