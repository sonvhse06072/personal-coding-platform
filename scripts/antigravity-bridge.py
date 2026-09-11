#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def contained(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class Bridge:
    def __init__(self, *, token: str, workspaces: Path, agy_bin: str):
        self.token = token
        self.workspaces = workspaces.resolve()
        self.agy_bin = agy_bin

    def handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "PersonalCodingAntigravityBridge/1.0"

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

            def do_GET(self):
                if not self.authorized():
                    return self.send_json(401, {"error": "unauthorized"})
                if self.path != "/health":
                    return self.send_json(404, {"error": "not_found"})
                return self.send_json(200, {
                    "status": "ok",
                    "service": "antigravity-host-bridge",
                    "agy": bridge.agy_bin,
                    "workspaces": str(bridge.workspaces),
                })

            def do_POST(self):
                if not self.authorized():
                    return self.send_json(401, {"error": "unauthorized"})
                if self.path != "/run":
                    return self.send_json(404, {"error": "not_found"})
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length) or b"{}")
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

                    cmd = [
                        bridge.agy_bin,
                        "-p", prompt,
                        "--output-format", "json",
                        "--sandbox",
                        "--dangerously-skip-permissions",
                        "--effort", effort,
                        "--print-timeout", f"{timeout}s",
                    ]
                    if model and model != "auto":
                        cmd.extend(["--model", model])

                    env = os.environ.copy()
                    env["NO_COLOR"] = "1"
                    proc = subprocess.run(
                        cmd,
                        cwd=workspace,
                        env=env,
                        text=True,
                        capture_output=True,
                        timeout=timeout + 15,
                        check=False,
                    )
                    parsed = None
                    try:
                        parsed = json.loads(proc.stdout)
                    except json.JSONDecodeError:
                        pass
                    return self.send_json(200, {
                        "returncode": proc.returncode,
                        "stdout": proc.stdout,
                        "stderr": proc.stderr,
                        "payload": parsed,
                    })
                except subprocess.TimeoutExpired as exc:
                    return self.send_json(200, {
                        "returncode": 124,
                        "stdout": exc.stdout or "",
                        "stderr": (exc.stderr or "") + "\nAntigravity run timed out",
                        "payload": None,
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
    args = parser.parse_args()

    agy_bin = args.agy_bin or shutil.which("agy") or ""
    if not agy_bin or not Path(agy_bin).exists():
        raise SystemExit("agy not found on WSL host. Install/login Antigravity first.")
    workspaces = Path(args.workspaces).expanduser()
    workspaces.mkdir(parents=True, exist_ok=True)
    bridge = Bridge(token=args.token, workspaces=workspaces, agy_bin=agy_bin)
    server = ThreadingHTTPServer((args.host, args.port), bridge.handler())
    print(f"Antigravity host bridge listening on {args.host}:{args.port}; workspaces={workspaces}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
