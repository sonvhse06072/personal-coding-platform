from __future__ import annotations

import json
from pathlib import Path

from .base import AgentAdapter, AgentRun, classify_provider_failure
from ..shell import run_command


class GeminiAdapter(AgentAdapter):
    name = "gemini_cli"

    async def run(self, *, workspace: Path, prompt: str, mode: str, timeout: int) -> AgentRun:
        approval = "plan" if mode in {"plan", "evaluate"} else "yolo"
        argv = ["gemini", "--skip-trust", "--approval-mode", approval, "--output-format", "json", "-p", prompt]
        if self.model and self.model != "auto":
            argv[1:1] = ["--model", self.model]
        result = await run_command(argv, cwd=workspace, timeout=timeout)
        usage = {}
        output = result.stdout
        try:
            payload = json.loads(result.stdout)
            output = payload.get("response") or result.stdout
            usage = payload.get("stats") or {}
        except json.JSONDecodeError:
            pass
        failure_kind, failure_message = classify_provider_failure(result.stderr, result.stdout, output)
        effective_returncode = result.returncode or (75 if failure_kind else 0)
        return AgentRun(
            self.name, self.model, effective_returncode, output, result.stderr, usage, result.stdout,
            failure_kind=failure_kind, failure_message=failure_message,
        )
