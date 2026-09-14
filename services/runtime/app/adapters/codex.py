from __future__ import annotations

import json
from pathlib import Path

from .base import AgentAdapter, AgentRun, classify_provider_failure
from ..developer_stream import agent_lifecycle_event, agent_public_event, emit_developer_event
from ..shell import run_command


class CodexAdapter(AgentAdapter):
    name = "codex_cli"

    async def run(self, *, workspace: Path, prompt: str, mode: str, timeout: int) -> AgentRun:
        sandbox = "read-only" if mode in {"plan", "evaluate"} else "workspace-write"
        # Runtime is non-interactive: a Codex approval prompt has no valid human
        # response channel. Make the policy explicit instead of inheriting mounted
        # user configuration. This does not broaden the sandbox; commands that need
        # more permission fail closed. Execute/repair also pins workspace network
        # access off so user config cannot silently widen that boundary.
        argv = [
            "codex",
            "exec",
            "--json",
            "--sandbox",
            sandbox,
            "--config",
            'approval_policy="never"',
        ]
        if sandbox == "workspace-write":
            argv += ["--config", "sandbox_workspace_write.network_access=false"]
        argv += ["--cd", str(workspace)]
        if self.model and self.model not in {"auto", "subscription-auto", "subscription-managed", "frontier-subscription-managed"}:
            argv += ["--model", self.model]
        if self.reasoning_effort:
            argv += ["--config", f'model_reasoning_effort="{self.reasoning_effort}"']
        argv.append(prompt)

        emit_developer_event(
            agent_lifecycle_event(
                adapter=self.name,
                provider="openai",
                model=self.model,
                mode=mode,
                state="started",
            )
        )

        def on_stdout_line(line: str) -> None:
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                return
            emit_developer_event(
                agent_public_event(
                    raw,
                    workspace=workspace,
                    mode=mode,
                    adapter=self.name,
                    provider="openai",
                    model=self.model,
                )
            )

        result = await run_command(
            argv,
            cwd=workspace,
            timeout=timeout,
            on_stdout_line=on_stdout_line,
        )
        messages: list[str] = []
        errors: list[str] = []
        usage: dict = {}
        terminal_event: str | None = None
        saw_json_event = False

        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            saw_json_event = True
            event_type = str(event.get("type") or "")
            if event_type == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message" and item.get("text"):
                    messages.append(str(item["text"]))
            if event_type == "turn.completed":
                terminal_event = "turn.completed"
                usage = event.get("usage") or usage
            if event_type in {"error", "turn.failed", "item.failed"}:
                candidate = event.get("error") or event.get("message") or event.get("item") or event
                if isinstance(candidate, (dict, list)):
                    errors.append(json.dumps(candidate, ensure_ascii=False))
                else:
                    errors.append(str(candidate))
                if event_type in {"error", "turn.failed"}:
                    terminal_event = event_type

        output = "\n".join(messages) or result.stdout

        # `codex exec --json` has structured terminal turn events. A successful
        # `turn.completed` from a zero-exit process is authoritative even when
        # earlier/transient telemetry or stderr contains phrases such as
        # "rate limit". Scanning the whole raw stream in that case can turn a
        # completed, side-effecting run into a false provider failure.
        structured_success = terminal_event == "turn.completed" and result.returncode == 0
        if structured_success:
            failure_kind = None
            failure_message = None
            effective_returncode = 0
        else:
            diagnostics = [result.stderr, "\n".join(errors)]
            if not saw_json_event or terminal_event is None:
                diagnostics.append(result.stdout)
            failure_kind, failure_message = classify_provider_failure(*diagnostics)
            effective_returncode = result.returncode
            if errors and effective_returncode == 0:
                effective_returncode = 70
            if failure_kind and effective_returncode == 0:
                effective_returncode = 75
            if errors and not failure_message:
                failure_message = "\n".join(errors)[-12000:]

        emit_developer_event(
            agent_lifecycle_event(
                adapter=self.name,
                provider="openai",
                model=self.model,
                mode=mode,
                state="completed" if effective_returncode == 0 else "failed",
            )
        )
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
