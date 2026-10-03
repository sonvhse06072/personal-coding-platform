from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


_MARKER = "PCP_VISUAL_EVIDENCE_JSON="
_MAX_EVIDENCE_BYTES = 24000
_MAX_ARTIFACTS = 48
_DEFAULT_VIEWPORTS = [360, 390, 430, 768, 1024, 1440]


def _git_dir(workspace: Path) -> Path:
    proc = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "--git-dir"],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("Unable to resolve Git metadata for visual evidence request")
    raw = proc.stdout.strip()
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (workspace / path).resolve()


def visual_request_path(workspace: Path) -> Path:
    git_dir = _git_dir(workspace)
    return git_dir / "pcp-visual-request.json"


def write_visual_request(
    workspace: Path,
    *,
    routes: list[str],
    project: dict[str, Any],
) -> Path:
    preview = dict(project.get("preview") or {})
    visual = dict(preview.get("visual_evidence") or {})
    viewports = list(visual.get("viewports") or _DEFAULT_VIEWPORTS)
    if not viewports or len(viewports) > 6:
        raise RuntimeError("Visual evidence viewports must contain 1..6 widths")
    normalized_viewports: list[int] = []
    for raw in viewports:
        try:
            width = int(raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Visual evidence viewport width must be an integer") from exc
        if width < 320 or width > 1920:
            raise RuntimeError("Visual evidence viewport width is outside 320..1920")
        if width not in normalized_viewports:
            normalized_viewports.append(width)

    base_url = str(visual.get("internal_base_url") or "http://127.0.0.1:3100").strip()
    if base_url not in {"http://127.0.0.1:3100", "http://localhost:3100"}:
        raise RuntimeError("Visual evidence internal_base_url must use the local preview listener")

    payload = {
        "version": 1,
        "base_url": base_url,
        "routes": routes[:8],
        "viewports": normalized_viewports,
    }
    path = visual_request_path(workspace)
    tmp = path.with_suffix(".tmp")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    tmp.write_text(encoded + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)
    return path


def remove_visual_request(workspace: Path) -> None:
    try:
        visual_request_path(workspace).unlink(missing_ok=True)
    except OSError:
        pass


def _clip(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _bounded_artifact(raw: dict[str, Any]) -> dict[str, Any]:
    viewport = dict(raw.get("viewport") or {})
    screenshot = dict(raw.get("screenshot") or {})
    dom = dict(raw.get("dom") or {})
    failed_requests = []
    for item in raw.get("failed_requests") or []:
        if not isinstance(item, dict):
            continue
        failed_requests.append(
            {
                "path": _clip(item.get("path"), 300),
                "error": _clip(item.get("error"), 300),
            }
        )
        if len(failed_requests) >= 5:
            break
    return {
        "route": _clip(raw.get("route"), 240),
        "viewport": {
            "width": int(viewport.get("width") or 0),
            "height": int(viewport.get("height") or 0),
        },
        "status_code": raw.get("status_code"),
        "navigation_error": _clip(raw.get("navigation_error"), 500) or None,
        "console_errors": [_clip(item, 300) for item in (raw.get("console_errors") or [])[:5]],
        "page_errors": [_clip(item, 300) for item in (raw.get("page_errors") or [])[:5]],
        "failed_requests": failed_requests,
        "dom": {
            "title": _clip(dom.get("title"), 200),
            "h1": [_clip(item, 160) for item in (dom.get("h1") or [])[:4]],
            "links": int(dom.get("links") or 0),
            "buttons": int(dom.get("buttons") or 0),
            "main_landmarks": int(dom.get("main_landmarks") or 0),
            "nav_landmarks": int(dom.get("nav_landmarks") or 0),
            "horizontal_overflow": bool(dom.get("horizontal_overflow", False)),
        },
        "screenshot": {
            "path": _clip(screenshot.get("path"), 300),
            "sha256": _clip(screenshot.get("sha256"), 80),
        },
        "passed": bool(raw.get("passed", False)),
    }


def extract_visual_evidence(phase_result: dict[str, Any]) -> dict[str, Any] | None:
    marker_payload: str | None = None
    for command in reversed(list(phase_result.get("commands") or [])):
        if not isinstance(command, dict):
            continue
        for line in reversed(str(command.get("stdout") or "").splitlines()):
            if line.startswith(_MARKER):
                marker_payload = line[len(_MARKER) :]
                break
        if marker_payload is not None:
            break
    if marker_payload is None:
        return None
    if len(marker_payload.encode("utf-8")) > _MAX_EVIDENCE_BYTES:
        raise RuntimeError("Visual evidence marker exceeds the 24 KiB bound")
    try:
        raw = json.loads(marker_payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Visual evidence marker is not valid JSON") from exc
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise RuntimeError("Visual evidence marker must use version 1")

    artifacts = [
        _bounded_artifact(item)
        for item in (raw.get("artifacts") or [])[:_MAX_ARTIFACTS]
        if isinstance(item, dict)
    ]
    return {
        "version": 1,
        "evidence_kind": _clip(raw.get("evidence_kind"), 100),
        "image_reviewed": bool(raw.get("image_reviewed", False)),
        "passed": bool(raw.get("passed", False)),
        "artifact_count": len(artifacts),
        "routes": [_clip(item, 240) for item in (raw.get("routes") or [])[:8]],
        "viewports": [int(item) for item in (raw.get("viewports") or [])[:6]],
        "artifacts": artifacts,
    }


__all__ = [
    "extract_visual_evidence",
    "remove_visual_request",
    "visual_request_path",
    "write_visual_request",
]
