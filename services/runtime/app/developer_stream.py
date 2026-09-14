from __future__ import annotations

import json
import re
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable


DeveloperSink = Callable[[dict[str, Any]], None]
_CURRENT_SINK: ContextVar[DeveloperSink | None] = ContextVar("pcp_developer_sink", default=None)

_MAX_TEXT = 2000
_MAX_COMMAND = 1000
_MAX_OUTPUT = 3000
_MAX_PATH = 240
_MAX_PATHS = 12

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|AUTHORIZATION|COOKIE)[A-Z0-9_]*)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_COMMON_TOKEN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{12,}|github_pat_[A-Za-z0-9_]{12,}|xox[baprs]-[A-Za-z0-9-]{12,})\b")
_PRIVATE_KEY = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.DOTALL)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def bind_developer_sink(sink: DeveloperSink | None) -> None:
    _CURRENT_SINK.set(sink)


def emit_developer_event(event: dict[str, Any] | None) -> None:
    if not event:
        return
    sink = _CURRENT_SINK.get()
    if sink is None:
        return
    try:
        sink(event)
    except Exception:
        # Observability must never change coding-job execution semantics.
        return


def _redact(value: Any, *, limit: int, workspace: Path) -> str:
    text = str(value or "")
    workspace_text = str(workspace)
    if workspace_text:
        text = text.replace(workspace_text, ".")
    text = _PRIVATE_KEY.sub("<redacted-private-key>", text)
    text = _BEARER.sub("Bearer <redacted>", text)
    text = _COMMON_TOKEN.sub("<redacted-token>", text)
    text = _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>", text)
    text = _CONTROL.sub("", text)
    return text[:limit]


def _role(mode: str) -> str:
    return {"plan": "planner", "execute": "executor", "evaluate": "evaluator"}.get(mode, "agent")


def _base_data(*, mode: str, model: str | None) -> dict[str, Any]:
    data: dict[str, Any] = {"role": _role(mode)}
    if model:
        data["model"] = str(model)[:160]
    return data


def _safe_paths(item: dict[str, Any], workspace: Path) -> list[str]:
    candidates: list[Any] = []
    if item.get("path"):
        candidates.append(item.get("path"))
    changes = item.get("changes")
    if isinstance(changes, list):
        for change in changes:
            if isinstance(change, dict):
                candidates.extend([change.get("path"), change.get("file_path")])
            elif isinstance(change, str):
                candidates.append(change)
    paths: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        text = _redact(candidate, limit=_MAX_PATH, workspace=workspace)
        if text and text not in paths:
            paths.append(text)
        if len(paths) >= _MAX_PATHS:
            break
    return paths


def codex_public_event(raw: dict[str, Any], *, workspace: Path, mode: str, model: str | None) -> dict[str, Any] | None:
    """Convert one Codex JSONL event into the allow-listed dashboard contract.

    Reasoning/internal model events are intentionally ignored. Only explicit agent
    messages and observable tool/file outcomes are eligible for persistence.
    """
    event_type = str(raw.get("type") or "")
    item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
    item_type = str(item.get("type") or "")
    data = _base_data(mode=mode, model=model)

    if item_type in {"reasoning", "analysis"}:
        return None

    if event_type == "item.completed" and item_type == "agent_message":
        text = _redact(item.get("text"), limit=_MAX_TEXT, workspace=workspace).strip()
        if not text:
            return None
        data["text"] = text
        return {"event_type": "developer_message", "phase": "execution", "level": "info", "message": "Developer update", "data": data}

    if item_type == "command_execution" and event_type in {"item.started", "item.completed"}:
        command = _redact(item.get("command"), limit=_MAX_COMMAND, workspace=workspace).strip()
        if command:
            data["command"] = command
        if event_type == "item.started":
            return {"event_type": "developer_command_started", "phase": "execution", "level": "info", "message": "Command started", "data": data}
        output = _redact(item.get("aggregated_output") or item.get("output"), limit=_MAX_OUTPUT, workspace=workspace).strip()
        if output:
            data["output"] = output
        exit_code = item.get("exit_code")
        if isinstance(exit_code, int):
            data["exit_code"] = exit_code
        status = item.get("status")
        if status is not None:
            data["status"] = str(status)[:80]
        level = "success" if exit_code in (None, 0) and str(status or "").lower() not in {"failed", "error"} else "error"
        return {"event_type": "developer_command_completed", "phase": "execution", "level": level, "message": "Command completed", "data": data}

    if event_type == "item.completed" and item_type in {"file_change", "file_changes"}:
        paths = _safe_paths(item, workspace)
        if not paths:
            return None
        data["paths"] = paths
        return {"event_type": "developer_file_activity", "phase": "execution", "level": "info", "message": "Files changed", "data": data}

    if event_type in {"error", "turn.failed", "item.failed"}:
        candidate = raw.get("error") or raw.get("message") or item
        if isinstance(candidate, (dict, list)):
            candidate = json.dumps(candidate, ensure_ascii=False)
        text = _redact(candidate, limit=_MAX_TEXT, workspace=workspace).strip()
        if not text:
            text = "Agent reported a bounded error"
        data["text"] = text
        return {"event_type": "developer_error", "phase": "execution", "level": "error", "message": "Developer error", "data": data}

    return None
