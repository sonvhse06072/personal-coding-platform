from __future__ import annotations

import json
from pathlib import Path

from .base import AgentAdapter, AgentRun, classify_provider_failure
from ..shell import run_command


class OpenCodeAdapter(AgentAdapter):
    name = "opencode"

    async def run(self, *, workspace: Path, prompt: str, mode: str, timeout: int) -> AgentRun:
        agent = "plan" if mode in {"plan", "evaluate"} else "build"
        argv = ["opencode", "run", "--format", "json", "--agent", agent, "--dir", str(workspace)]
        if mode == "execute":
            argv.append("--auto")
        if self.model and self.model != "auto":
            argv += ["--model", self.model]
        argv.append(prompt)
        result = await run_command(argv, cwd=workspace, timeout=timeout)
        chunks: list[str] = []
        errors: list[str] = []
        usage: dict = {}
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            part = event.get("part") or event.get("message") or event.get("text")
            if isinstance(part, str):
                chunks.append(part)
            if event.get("usage"):
                usage = event["usage"]
            if event.get("error"):
                err = event["error"]
                errors.append(json.dumps(err, ensure_ascii=False) if isinstance(err, (dict, list)) else str(err))
        output = "\n".join(chunks) or result.stdout
        failure_kind, failure_message = classify_provider_failure(result.stderr, result.stdout, "\n".join(errors), output)
        effective_returncode = result.returncode
        if errors and effective_returncode == 0:
            effective_returncode = 70
        if failure_kind and effective_returncode == 0:
            effective_returncode = 75
        return AgentRun(
            self.name, self.model, effective_returncode, output, result.stderr, usage, result.stdout,
            failure_kind=failure_kind, failure_message=failure_message,
        )
