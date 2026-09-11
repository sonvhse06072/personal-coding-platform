from __future__ import annotations

from pathlib import Path

from .base import AgentAdapter, AgentRun


class FakeAdapter(AgentAdapter):
    name = "fake"

    async def run(self, *, workspace: Path, prompt: str, mode: str, timeout: int) -> AgentRun:
        return AgentRun(self.name, self.model, 0, f"fake-{mode}-ok", usage={"input_tokens": 10, "output_tokens": 2})
