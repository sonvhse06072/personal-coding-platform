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


def safe_activity_text(value: Any, *, workspace: Path, limit: int = _MAX_TEXT) -> str:
    """Sanitize text before it enters the durable public activity stream."""
    return _redact(value, limit=max(1, min(int(limit), _MAX_OUTPUT)), workspace=workspace)


def _role(mode: str) -> str:
    return {"plan": "planner", "execute": "executor", "evaluate": "evaluator"}.get(mode, "agent")


def provider_for_adapter(adapter: str, model: str | None) -> str:
    normalized = str(model or "").strip()
    if adapter == "codex_cli":
        return "openai"
    if adapter == "antigravity_host":
        return "google_antigravity"
    if adapter == "opencode":
        prefix = normalized.split("/", 1)[0].strip().lower()
        return prefix or "opencode"
    return adapter or "unknown"


def _base_data(
    *,
    mode: str,
    adapter: str,
    model: str | None,
    provider: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "role": _role(mode),
        "adapter": str(adapter)[:80],
        "provider": str(provider or provider_for_adapter(adapter, model))[:80],
    }
    if model:
        data["model"] = str(model)[:160]
    return data


def agent_lifecycle_event(
    *,
    adapter: str,
    model: str | None,
    mode: str,
    state: str,
    provider: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    data = _base_data(mode=mode, adapter=adapter, model=model, provider=provider)
    data["status"] = str(state)[:80]
    if detail:
        data["text"] = str(detail)[:_MAX_TEXT]
    level = "error" if state in {"failed", "error"} else "info"
    return {
        "event_type": "developer_step",
        "phase": "execution",
        "level": level,
        "message": f"Agent {state}",
        "data": data,
    }


def agent_response_event(
    *,
    adapter: str,
    model: str | None,
    mode: str,
    text: Any,
    workspace: Path,
    provider: str | None = None,
) -> dict[str, Any] | None:
    """Emit one bounded public response after an agent turn completes.

    Streaming token/text deltas are transport details, not durable activity
    events. Persist only the completed public response so Dashboard activity
    remains readable and does not split words across rows.
    """
    bounded = _redact(text, limit=_MAX_TEXT, workspace=workspace).strip()
    if not bounded:
        return None
    data = _base_data(mode=mode, adapter=adapter, model=model, provider=provider)
    data["status"] = "response_completed"
    data["text"] = bounded
    return {
        "event_type": "developer_message",
        "phase": "execution",
        "level": "info",
        "message": "Developer update",
        "data": data,
    }


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


def _stringify_bounded(value: Any, *, workspace: Path, limit: int) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return _redact(value, limit=limit, workspace=workspace).strip()


def _known_command(container: Any, *, workspace: Path) -> str:
    if not isinstance(container, dict):
        return ""
    for key in ("CommandLine", "command", "cmd", "script"):
        value = container.get(key)
        if isinstance(value, str) and value.strip():
            return _redact(value, limit=_MAX_COMMAND, workspace=workspace).strip()
    return ""


def codex_public_event(
    raw: dict[str, Any],
    *,
    workspace: Path,
    mode: str,
    model: str | None,
) -> dict[str, Any] | None:
    """Compatibility wrapper for the Codex JSONL schema."""
    return agent_public_event(
        raw,
        workspace=workspace,
        mode=mode,
        adapter="codex_cli",
        provider="openai",
        model=model,
    )


def _codex_public_event(
    raw: dict[str, Any],
    *,
    workspace: Path,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    event_type = str(raw.get("type") or "")
    item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
    item_type = str(item.get("type") or "")

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
        text = _stringify_bounded(candidate, workspace=workspace, limit=_MAX_TEXT)
        if not text:
            text = "Agent reported a bounded error"
        data["text"] = text
        return {"event_type": "developer_error", "phase": "execution", "level": "error", "message": "Developer error", "data": data}

    return None


def _opencode_public_event(
    raw: dict[str, Any],
    *,
    workspace: Path,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    """Map OpenCode NDJSON without exposing ambiguous/internal text parts.

    OpenCode currently emits completed `text` parts without enough owner metadata
    to reliably distinguish public assistant text from auto-compaction internals.
    Fail closed for raw text/reasoning while still exposing safe step/tool/error
    activity and provider/model identity.
    """
    event_type = str(raw.get("type") or "")
    part = raw.get("part") if isinstance(raw.get("part"), dict) else {}
    part_type = str(part.get("type") or "")

    if event_type in {"reasoning", "text"} or part_type in {"reasoning", "analysis", "text"}:
        if event_type == "text" and not part.get("synthetic"):
            data["status"] = "response_text_completed"
            return {"event_type": "developer_step", "phase": "execution", "level": "info", "message": "Model response text completed", "data": data}
        return None

    if event_type == "step_start":
        data["status"] = "step_started"
        return {"event_type": "developer_step", "phase": "execution", "level": "info", "message": "Model step started", "data": data}

    if event_type == "step_finish":
        reason = part.get("reason") or raw.get("reason")
        data["status"] = str(reason or "step_finished")[:80]
        return {"event_type": "developer_step", "phase": "execution", "level": "success", "message": "Model step finished", "data": data}

    if event_type == "tool_use":
        tool = str(part.get("tool") or "tool")[:120]
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        status = str(state.get("status") or "completed")[:80]
        data["tool"] = tool
        data["status"] = status
        command = _known_command(state.get("input") or part.get("input") or {}, workspace=workspace)
        if command:
            data["command"] = command
        output = _stringify_bounded(state.get("output"), workspace=workspace, limit=_MAX_OUTPUT)
        error = _stringify_bounded(state.get("error"), workspace=workspace, limit=_MAX_TEXT)
        if output:
            data["output"] = output
        if error:
            data["text"] = error
        level = "error" if status in {"error", "failed"} or error else "success"
        message = f"OpenCode tool {tool} {status}"
        return {"event_type": "developer_command_completed", "phase": "execution", "level": level, "message": message, "data": data}

    if event_type == "error" or raw.get("error"):
        text = _stringify_bounded(raw.get("error") or raw, workspace=workspace, limit=_MAX_TEXT)
        data["text"] = text or "OpenCode reported a bounded error"
        return {"event_type": "developer_error", "phase": "execution", "level": "error", "message": "Developer error", "data": data}

    return None


def _antigravity_public_event(
    raw: dict[str, Any],
    *,
    workspace: Path,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    event = str(raw.get("event") or "")
    if event == "init":
        data["status"] = "session_started"
        return {"event_type": "developer_step", "phase": "execution", "level": "info", "message": "Antigravity session started", "data": data}

    if event == "step_update":
        step = raw.get("step_update") if isinstance(raw.get("step_update"), dict) else {}
        step_type = str(step.get("step_type") or "")
        state = str(step.get("state") or "")[:80]
        data["status"] = state or step_type
        if step_type == "user_input":
            return None
        if step_type == "agent_response":
            # Antigravity emits transport-level text deltas that may split a
            # single word across many events. The adapter emits one completed
            # bounded response from the terminal result instead.
            return None
        if step_type == "tool":
            tool_info = step.get("tool_info") if isinstance(step.get("tool_info"), dict) else {}
            tool = str(step.get("tool_name") or tool_info.get("name") or "tool")[:120]
            data["tool"] = tool
            command = _known_command(tool_info.get("parameters") or {}, workspace=workspace)
            if command:
                data["command"] = command
            output = _stringify_bounded(tool_info.get("output"), workspace=workspace, limit=_MAX_OUTPUT)
            error = _stringify_bounded(tool_info.get("error"), workspace=workspace, limit=_MAX_TEXT)
            if output:
                data["output"] = output
            if error:
                data["text"] = error
            running = state.upper() == "ACTIVE"
            event_type = "developer_command_started" if running else "developer_command_completed"
            level = "error" if error else ("info" if running else "success")
            return {"event_type": event_type, "phase": "execution", "level": level, "message": f"Antigravity tool {tool}", "data": data}
        data["tool"] = step_type or "step"
        return {"event_type": "developer_step", "phase": "execution", "level": "info", "message": f"Antigravity {step_type or 'step'}", "data": data}

    if event == "result":
        result = raw.get("result") if isinstance(raw.get("result"), dict) else {}
        status = str(result.get("status") or "completed")[:80]
        data["status"] = status
        if status.upper() not in {"SUCCESS", "COMPLETED", "DONE"}:
            error = _stringify_bounded(result.get("error"), workspace=workspace, limit=_MAX_TEXT)
            if error:
                data["text"] = error
            return {"event_type": "developer_error", "phase": "execution", "level": "error", "message": "Antigravity run failed", "data": data}
        return {"event_type": "developer_step", "phase": "execution", "level": "success", "message": "Antigravity run completed", "data": data}

    return None


def agent_public_event(
    raw: dict[str, Any],
    *,
    workspace: Path,
    mode: str,
    adapter: str,
    model: str | None,
    provider: str | None = None,
) -> dict[str, Any] | None:
    """Convert one adapter-specific event into the shared dashboard contract."""
    data = _base_data(mode=mode, adapter=adapter, model=model, provider=provider)
    if adapter == "codex_cli":
        return _codex_public_event(raw, workspace=workspace, data=data)
    if adapter == "opencode":
        return _opencode_public_event(raw, workspace=workspace, data=data)
    if adapter == "antigravity_host":
        return _antigravity_public_event(raw, workspace=workspace, data=data)
    return None


def runtime_activity_event(
    *,
    kind: str,
    message: str,
    phase: str,
    workspace: Path,
    level: str = "info",
    command: str | None = None,
    output: Any = None,
    status: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    adapter: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {"kind": str(kind)[:80]}
    if command:
        data["command"] = _redact(command, limit=_MAX_COMMAND, workspace=workspace).strip()
    bounded_output = _stringify_bounded(output, workspace=workspace, limit=_MAX_OUTPUT)
    if bounded_output:
        data["output"] = bounded_output
    if status:
        data["status"] = str(status)[:80]
    if provider:
        data["provider"] = str(provider)[:80]
    if model:
        data["model"] = str(model)[:160]
    if adapter:
        data["adapter"] = str(adapter)[:80]
    return {
        "event_type": "runtime_activity",
        "phase": str(phase)[:40] or "execution",
        "level": level if level in {"info", "success", "warning", "error"} else "info",
        "message": _redact(message, limit=_MAX_TEXT, workspace=workspace).strip() or "Runtime activity",
        "data": data,
    }
