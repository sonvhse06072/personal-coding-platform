from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "n8n" / "workflows" / "telegram-control.json"


def test_callback_ack_failure_cannot_block_runtime_action_attempt() -> None:
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    code_nodes = [
        node
        for node in workflow["nodes"]
        if node["type"] == "n8n-nodes-base.code"
    ]
    assert len(code_nodes) == 1
    code = code_nodes[0]["parameters"]["jsCode"]

    helper_start = code.index("const answerBestEffort = async")
    helper_end = code.index("if (fromId !== ownerUserId", helper_start)
    helper = code[helper_start:helper_end]

    assert "try {" in helper
    assert "answerCallbackQuery" in helper
    assert "catch (error)" in helper
    assert "return null;" in helper
    assert "throw" not in helper

    processing_ack = code.index("await answerBestEffort('Đang xử lý action…');")
    runtime_action = code.index("/v1/control-actions/")
    assert processing_ack < runtime_action

    assert "await answerBestEffort('Bạn không có quyền thực hiện action này.', true);" in code
    assert "await answerBestEffort('Action không hợp lệ hoặc đã hết hạn.', true);" in code
    assert "const answer = async" not in code
