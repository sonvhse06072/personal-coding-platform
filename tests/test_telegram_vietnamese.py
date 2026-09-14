from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / "n8n" / "workflows"


def _code(name: str) -> str:
    workflow = json.loads((WORKFLOW_DIR / name).read_text(encoding="utf-8"))
    nodes = [node for node in workflow["nodes"] if node["type"] == "n8n-nodes-base.code"]
    assert len(nodes) == 1
    return nodes[0]["parameters"]["jsCode"]


def test_telegram_notification_user_visible_labels_are_vietnamese():
    code = _code("telegram-notifications.json")

    for text in (
        "Dự án:",
        "Giai đoạn:",
        "Mã lý do:",
        "Tại sao:",
        "Trạng thái được giữ nguyên:",
        "Ảnh hưởng:",
        "Chỉ số:",
        "Khuyến nghị:",
        "WORKORDER BỊ CHẶN",
        "PROVIDER HẾT QUOTA",
    ):
        assert text in code

    for old_label in (
        "Project:",
        "Phase:",
        "Reason:",
        "Why:",
        "State preserved:",
        "Impact:",
        "Metrics:",
        "Recommended:",
        "Platform attention required.",
    ):
        assert old_label not in code

    # Sanitization boundary remains transport-only.
    assert "last_failure" not in code
    assert "agent_attempts" not in code
    assert "output_excerpt" not in code
    assert "stderr_excerpt" not in code


def test_telegram_control_user_visible_responses_are_vietnamese():
    code = _code("telegram-control.json")

    for text in (
        "Bạn không có quyền thực hiện action này.",
        "Action không hợp lệ hoặc đã hết hạn.",
        "Đang xử lý action…",
        "Action của owner đã được xử lý",
        "Trạng thái:",
        "Ngân sách:",
        "Mã lý do:",
        "Tại sao:",
        "Khuyến nghị:",
        "Action đã bị từ chối hoặc thất bại an toàn.",
    ):
        assert text in code

    for old_text in (
        "Unauthorized owner control.",
        "Invalid or stale action.",
        "Owner action processed",
        "Runtime accepted the action.",
        "Owner action was rejected or failed safely.",
    ):
        assert old_text not in code

    # n8n still carries only opaque owner actions; it never mutates jobs directly.
    assert "/v1/control-actions/" in code
    assert "/v1/jobs/" not in code
    assert "force_complete" not in code
    assert "reset_budget" not in code
