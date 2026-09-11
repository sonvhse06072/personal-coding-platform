from __future__ import annotations

import json
from pathlib import Path

from .base import AgentAdapter, AgentRun, classify_provider_failure
from ..shell import run_command


class CodexAdapter(AgentAdapter):
    name = "codex_cli"

    async def run(self, *, workspace: Path, prompt: str, mode: str, timeout: int) -> AgentRun:
        sandbox = "read-only" if mode in {"plan", "evaluate"} else "workspace-write"
        argv = ["codex", "exec", "--json", "--sandbox", sandbox, "--cd", str(workspace)]
        if self.model and self.model not in {"auto", "subscription-auto", "subscription-managed", "frontier-subscription-managed"}:
            argv += ["--model", self.model]
        argv.append(prompt)
        result = await run_command(argv, cwd=workspace, timeout=timeout)
        messages: list[str] = []
        errors: list[str] = []
        usage: dict = {}
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = str(event.get("type") or "")
            if event_type == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message" and item.get("text"):
                    messages.append(str(item["text"]))
            if event_type == "turn.completed":
                usage = event.get("usage") or usage
            if event_type in {"error", "turn.failed", "item.failed"}:
                candidate = event.get("error") or event.get("message") or event.get("item") or event
                if isinstance(candidate, (dict, list)):
                    errors.append(json.dumps(candidate, ensure_ascii=False))
                else:
                    errors.append(str(candidate))

        output = "\n".join(messages) or result.stdout
        failure_kind, failure_message = classify_provider_failure(
            result.stderr,
            result.stdout,
            "\n".join(errors),
        )
        effective_returncode = result.returncode
        if errors and effective_returncode == 0:
            effective_returncode = 70
        if failure_kind and effective_returncode == 0:
            # EX_TEMPFAIL-like code: provider/resource failure despite CLI exit 0.
            effective_returncode = 75
        if errors and not failure_message:
            failure_message = "\n".join(errors)[-12000:]

        return AgentRun(
            self.name,
            self.model,
            effective_returncode,
            output,
            result.stderr,
            usage,
            result.stdout,
            failure_kind=failure_kind,
            failure_message=failure_message,
        )
