from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.visual_evidence import (
    extract_visual_evidence,
    remove_visual_request,
    visual_request_path,
    write_visual_request,
)


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)


def project() -> dict:
    return {
        "preview": {
            "frontend": {"enabled": True},
            "visual_evidence": {
                "internal_base_url": "http://127.0.0.1:3100",
                "viewports": [360, 430, 1024],
            },
        }
    }


def test_visual_request_is_written_only_inside_git_metadata(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    init_repo(workspace)

    path = write_visual_request(
        workspace,
        routes=["/artist/demo", "/events"],
        project=project(),
    )

    assert path == visual_request_path(workspace)
    assert ".git" in path.parts
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "version": 1,
        "base_url": "http://127.0.0.1:3100",
        "routes": ["/artist/demo", "/events"],
        "viewports": [360, 430, 1024],
    }

    remove_visual_request(workspace)
    assert not path.exists()


def test_visual_request_rejects_nonlocal_preview_base(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    init_repo(workspace)
    cfg = project()
    cfg["preview"]["visual_evidence"]["internal_base_url"] = "https://example.com"

    with pytest.raises(RuntimeError, match="local preview listener"):
        write_visual_request(
            workspace,
            routes=["/"],
            project=cfg,
        )


def test_visual_evidence_parser_returns_bounded_compact_payload() -> None:
    marker = {
        "version": 1,
        "evidence_kind": "local_playwright_preview",
        "image_reviewed": False,
        "passed": True,
        "routes": ["/artist/demo"],
        "viewports": [390],
        "artifacts": [
            {
                "route": "/artist/demo",
                "viewport": {"width": 390, "height": 844},
                "status_code": 200,
                "navigation_error": None,
                "console_errors": [],
                "page_errors": [],
                "failed_requests": [],
                "dom": {
                    "title": "Artist",
                    "h1": ["Artist"],
                    "links": 4,
                    "buttons": 2,
                    "main_landmarks": 1,
                    "nav_landmarks": 1,
                    "horizontal_overflow": False,
                },
                "screenshot": {
                    "path": ".pcp-visual-evidence/artist-demo-390.png",
                    "sha256": "a" * 64,
                },
                "passed": True,
            }
        ],
    }
    phase = {
        "passed": True,
        "commands": [
            {
                "command": "npm run test:visual",
                "returncode": 0,
                "stdout": "noise\nPCP_VISUAL_EVIDENCE_JSON=" + json.dumps(marker),
                "stderr": "",
            }
        ],
    }

    result = extract_visual_evidence(phase)

    assert result is not None
    assert result["passed"] is True
    assert result["image_reviewed"] is False
    assert result["artifact_count"] == 1
    assert result["artifacts"][0]["route"] == "/artist/demo"
    assert result["artifacts"][0]["screenshot"]["sha256"] == "a" * 64
    assert "noise" not in json.dumps(result)


def test_visual_evidence_parser_requires_marker_and_version() -> None:
    assert extract_visual_evidence(
        {"commands": [{"stdout": "ordinary output"}]}
    ) is None

    with pytest.raises(RuntimeError, match="version 1"):
        extract_visual_evidence(
            {
                "commands": [
                    {
                        "stdout": 'PCP_VISUAL_EVIDENCE_JSON={"version":2,"artifacts":[]}'
                    }
                ]
            }
        )
