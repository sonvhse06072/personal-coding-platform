from __future__ import annotations

from .antigravity import AntigravityAdapter
from .base import AgentAdapter
from .codex import CodexAdapter
from .fake import FakeAdapter
from .opencode import OpenCodeAdapter


def build_adapter(adapter: str, model: str, reasoning_effort: str | None = None) -> AgentAdapter:
    mapping = {
        "antigravity_host": AntigravityAdapter,
        "codex_cli": CodexAdapter,
        "opencode": OpenCodeAdapter,
        "fake": FakeAdapter,
    }
    if adapter not in mapping:
        raise RuntimeError(f"Unsupported coding adapter: {adapter}")
    return mapping[adapter](model, reasoning_effort)
