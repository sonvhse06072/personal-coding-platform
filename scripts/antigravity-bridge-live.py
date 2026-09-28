#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import queue
from pathlib import Path
import shutil
import subprocess
import threading
import time
import uuid
from http.server import ThreadingHTTPServer
from typing import Any


_LEGACY_PATH = Path(__file__).with_name("antigravity-bridge.py")
_SPEC = importlib.util.spec_from_file_location("pcp_antigravity_bridge_legacy", _LEGACY_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load {_LEGACY_PATH}")
legacy = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(legacy)

_MAX_TEXT = 12000
_MAX_TOOL_NAME = 160
_SAFE_USAGE_KEYS = {
    "input_tokens",
    "output_tokens",
    "thinking_tokens",
    "cache_read_tokens",
    "cached_input_tokens",
    "total_tokens",
}


def _bounded(value: Any, limit: int = _MAX_TEXT) -> str:
    return str(value or "")[:limit]


def _safe_usage(value: Any) -> dict[str, int | float]:
    if not isinstance(value, dict):
        return {}
    safe: dict[str, int | float] = {}
    for key in _SAFE_USAGE_KEYS:
        item = value.get(key)
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            safe[key] = item
    return safe


def _safe_tool_info(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    safe: dict[str, Any] = {}
    name = value.get("name")
    if isinstance(name, str) and name:
        safe["name"] = name[:_MAX_TOOL_NAME]
    # Parameters/output make activity useful, but unknown top-level tool metadata,
    # child log URIs and conversation identifiers are excluded here. Runtime
    # applies a second redaction/bounding layer before persistence/dashboard use.
    if isinstance(value.get("parameters"), (dict, list, str)):
        safe["parameters"] = value["parameters"]
    if isinstance(value.get("output"), (dict, list, str, int, float, bool)):
        safe["output"] = value["output"]
    if value.get("error") is not None:
        safe["error"] = _bounded(value.get("error"), 4000)
    return safe


def _safe_stream_event(value: Any) -> dict[str, Any] | None:
    """Field-level allowlist for observable Antigravity stream events.

    The prompt is represented by a user_input step in stream-json. It is dropped
    at the host boundary. Reasoning/analysis steps and unknown top-level fields are
    also discarded so a future CLI schema addition cannot become a log leak by
    default.
    """
    if not isinstance(value, dict):
        return None
    event = str(value.get("event") or "")

    if event == "init":
        safe: dict[str, Any] = {"event": "init"}
        model = value.get("model")
        if isinstance(model, str) and model:
            safe["model"] = model[:160]
        return safe

    if event == "result":
        source = value.get("result") if isinstance(value.get("result"), dict) else value
        result: dict[str, Any] = {}
        status = source.get("status")
        if status is not None:
            result["status"] = _bounded(status, 80)
        response = source.get("response")
        if response is not None:
            result["response"] = _bounded(response, _MAX_TEXT)
        usage = _safe_usage(source.get("usage"))
        if usage:
            result["usage"] = usage
        if source.get("error") is not None:
            result["error"] = _bounded(source.get("error"), 4000)
        return {"event": "result", "result": result}

    if event != "step_update":
        return None
    step = value.get("step_update")
    if not isinstance(step, dict):
        return None
    step_type = str(step.get("step_type") or "")
    if step_type in {"user_input", "reasoning", "analysis"}:
        return None

    safe_step: dict[str, Any] = {"step_type": step_type[:80]}
    state = step.get("state")
    if state is not None:
        safe_step["state"] = _bounded(state, 80)

    if step_type == "agent_response":
        text_delta = step.get("text_delta")
        if text_delta is not None:
            safe_step["text_delta"] = _bounded(text_delta, 4000)
    elif step_type == "tool":
        tool_name = step.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            safe_step["tool_name"] = tool_name[:_MAX_TOOL_NAME]
        tool_info = _safe_tool_info(step.get("tool_info"))
        if tool_info:
            safe_step["tool_info"] = tool_info
    # Other documented non-sensitive step types are represented only by type and
    # state. No subagent log URI/conversation id or unknown payload is forwarded.
    return {"event": "step_update", "step_update": safe_step}


class StreamingBridge(legacy.Bridge):
    def handler(self):
        bridge = self
        LegacyHandler = super().handler()

        class Handler(LegacyHandler):
            server_version = "PersonalCodingAntigravityBridge/1.7"

            def do_GET(self):
                if not self.authorized():
                    return self.send_json(401, {"error": "unauthorized"})
                if self.path != "/health":
                    return self.send_json(404, {"error": "not_found"})
                safe, safety = legacy.settings_status(bridge.settings)
                with bridge._runs_lock:
                    active_runs = len(bridge._runs)
                    pending_cancellations = len(bridge._cancelled_runs)
                return self.send_json(200 if safe else 503, {
                    "status": "ok" if safe else "degraded",
                    "service": "antigravity-host-bridge",
                    "version": "1.7",
                    "agy": bridge.agy_bin,
                    "workspaces": str(bridge.workspaces),
                    "active_runs": active_runs,
                    "pending_cancellations": pending_cancellations,
                    "safe_settings": safe,
                    "streaming": True,
                    "safety": safety,
                })

            def _write_ndjson(self, payload: dict[str, Any]) -> None:
                body = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
                self.wfile.write(body)
                self.wfile.flush()

            def _stream_run(self, payload: dict[str, Any]):
                safe, safety = legacy.settings_status(bridge.settings)
                if not safe:
                    return self.send_json(503, {
                        "error": "unsafe_antigravity_settings",
                        "safety": safety,
                    })

                workspace = Path(str(payload["workspace"])).resolve()
                if not workspace.is_dir() or not bridge.workspace_allowed(workspace):
                    return self.send_json(403, {"error": "workspace_not_allowed"})
                prompt = str(payload.get("prompt") or "").strip()
                if not prompt:
                    return self.send_json(400, {"error": "prompt_required"})
                timeout = max(30, min(int(payload.get("timeout", 900)), 5400))
                model = str(payload.get("model") or "auto")
                raw_effort = payload.get("effort")
                effort = str(raw_effort).strip() if raw_effort is not None else None
                if effort not in legacy._REASONING_EFFORTS:
                    effort = None
                run_id = str(payload.get("run_id") or uuid.uuid4().hex).strip()
                if not run_id or len(run_id) > 128:
                    return self.send_json(400, {"error": "invalid_run_id"})

                cmd = legacy.build_run_command(
                    bridge.agy_bin,
                    prompt=prompt,
                    model=model,
                    effort=effort,
                    timeout=timeout,
                    output_format="stream-json",
                )
                env = os.environ.copy()
                env["NO_COLOR"] = "1"

                # No Content-Length: the authenticated connection closes after the
                # terminal bridge_result line. This endpoint is run-scoped only;
                # there is deliberately no endpoint for browsing arbitrary host logs.
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True

                timed_out = False
                stderr_chunks: list[str] = []
                proc: subprocess.Popen | None = None
                scoped_allow: set[str] = set()
                scoped_deny: set[str] = set()
                safe_stream_failure: str | None = None
                try:
                    with bridge._agy_lock:
                        if bridge.consume_cancelled(run_id):
                            return self._write_ndjson({
                                "bridge_event": "result",
                                "run_id": run_id,
                                "returncode": 130,
                                "stderr": "Antigravity run cancelled before start",
                                "timed_out": False,
                            })
                        scoped_allow, scoped_deny = legacy.add_workspace_file_rules(
                            bridge.settings, workspace
                        )
                        if bridge.consume_cancelled(run_id):
                            return self._write_ndjson({
                                "bridge_event": "result",
                                "run_id": run_id,
                                "returncode": 130,
                                "stderr": "Antigravity run cancelled before process launch",
                                "timed_out": False,
                            })

                        proc = subprocess.Popen(
                            cmd,
                            cwd=workspace,
                            env=env,
                            text=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            bufsize=1,
                            start_new_session=True,
                        )
                        bridge.register_run(run_id, proc)
                        stdout_queue: queue.Queue[str | None] = queue.Queue()

                        def drain_stdout() -> None:
                            assert proc is not None and proc.stdout is not None
                            try:
                                for line in proc.stdout:
                                    stdout_queue.put(line)
                            finally:
                                stdout_queue.put(None)

                        def drain_stderr() -> None:
                            assert proc is not None and proc.stderr is not None
                            for line in proc.stderr:
                                stderr_chunks.append(line)
                                if sum(len(part) for part in stderr_chunks) > 24000:
                                    del stderr_chunks[:-8]

                        stdout_thread = threading.Thread(target=drain_stdout, daemon=True)
                        stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
                        stdout_thread.start()
                        stderr_thread.start()
                        deadline = time.monotonic() + timeout + 15
                        stdout_done = False

                        while not stdout_done:
                            if time.monotonic() >= deadline:
                                timed_out = True
                                legacy.terminate_process_group(proc)
                                break
                            try:
                                line = stdout_queue.get(timeout=0.2)
                            except queue.Empty:
                                if proc.poll() is not None and not stdout_thread.is_alive():
                                    break
                                continue
                            if line is None:
                                stdout_done = True
                                continue
                            try:
                                raw = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            public = _safe_stream_event(raw)
                            if public is not None:
                                self._write_ndjson(public)

                        if proc.poll() is None:
                            if timed_out:
                                legacy.terminate_process_group(proc)
                            else:
                                proc.wait(timeout=5)
                        stdout_thread.join(timeout=2)
                        stderr_thread.join(timeout=2)
                except (BrokenPipeError, ConnectionResetError):
                    if proc is not None:
                        legacy.terminate_process_group(proc)
                    return
                except Exception as exc:
                    safe_stream_failure = type(exc).__name__
                    if proc is not None:
                        legacy.terminate_process_group(proc)
                finally:
                    if proc is not None:
                        bridge.unregister_run(run_id)
                    if scoped_allow or scoped_deny:
                        legacy.remove_workspace_file_rules(
                            bridge.settings, scoped_allow, scoped_deny
                        )

                stderr = "".join(stderr_chunks)[-12000:]
                if timed_out:
                    stderr = (stderr + "\nAntigravity run timed out").strip()
                if safe_stream_failure:
                    stderr = (stderr + f"\nAntigravity bridge stream failed safely: {safe_stream_failure}").strip()
                try:
                    return self._write_ndjson({
                        "bridge_event": "result",
                        "run_id": run_id,
                        "returncode": (
                            124 if timed_out else
                            1 if safe_stream_failure else
                            int(proc.returncode or 0) if proc else 1
                        ),
                        "stderr": stderr,
                        "timed_out": timed_out,
                    })
                except (BrokenPipeError, ConnectionResetError):
                    return None

            def do_POST(self):
                if self.path != "/run-stream":
                    return super().do_POST()
                if not self.authorized():
                    return self.send_json(401, {"error": "unauthorized"})
                try:
                    return self._stream_run(self.read_payload())
                except Exception as exc:
                    # Only pre-stream validation/setup errors reach here. Once the
                    # NDJSON response starts, _stream_run converts internal failures
                    # into a bounded terminal result or closes the connection.
                    return self.send_json(500, {"error": f"stream_setup_failed:{type(exc).__name__}"})

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
    safe, safety = legacy.settings_status(settings)
    if not safe:
        raise SystemExit(f"Unsafe Antigravity settings: {json.dumps(safety, sort_keys=True)}")
    direct_workspace = (
        Path(args.direct_workspace).expanduser().resolve()
        if str(args.direct_workspace).strip()
        else None
    )
    bridge = StreamingBridge(
        token=args.token,
        workspaces=workspaces,
        agy_bin=agy_bin,
        settings=settings,
        direct_workspace=direct_workspace,
    )
    server = ThreadingHTTPServer((args.host, args.port), bridge.handler())
    print(
        f"Antigravity host bridge 1.7 listening on {args.host}:{args.port}; workspaces={workspaces}; safe_settings=true; streaming=true",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
