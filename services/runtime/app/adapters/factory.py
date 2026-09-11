from __future__ import annotations

from .base import AgentAdapter
from .codex import CodexAdapter
from .fake import FakeAdapter
from .gemini import GeminiAdapter
from .opencode import OpenCodeAdapter


def build_adapter(adapter: str, model: str) -> AgentAdapter:
    mapping = {
        "gemini_cli": GeminiAdapter,
        "codex_cli": CodexAdapter,
        "opencode": OpenCodeAdapter,
        "fake": FakeAdapter,
    }
    if adapter not in mapping:
        raise RuntimeError(f"Unsupported coding adapter: {adapter}")
    return mapping[adapter](model)
