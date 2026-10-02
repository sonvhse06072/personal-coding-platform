from __future__ import annotations

import json
import os
from pathlib import Path

from .base import AgentAdapter, AgentRun, InvocationCapabilities, classify_provider_failure
from ..developer_stream import (
    agent_lifecycle_event,
    agent_public_event,
    emit_developer_event,
    provider_for_adapter,
)
from ..shell import CommandResult, CommandTimeoutError, run_command


_PROVIDER_KEY_BY_MODEL_PREFIX = {
    "deepseek": "DEEPSEEK_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
_OPENROUTER_PREFIX = "openrouter/"


def provider_env_for_model(model: str) -> dict[str, str]:
    """Return only the API credential required by this OpenCode model.

    OpenCode may also use its mounted user configuration for authenticated
    providers. Unknown/auto models therefore receive no API key by default rather
    than inheriting every provider credential available to Runtime.
    """
    prefix = (model or "").split("/", 1)[0].strip().lower()
    key = _PROVIDER_KEY_BY_MODEL_PREFIX.get(prefix)
    if not key:
        return {}
    value = os.getenv(key, "").strip()
    return {key: value} if value else {}


def opencode_env_for_model(model: str) -> dict[str, str]:
    """Build the provider-scoped environment for one OpenCode invocation.

    OpenRouter coding jobs use one explicit model and an inline OpenCode provider
    configuration. PCP keeps the provider/model allowlist narrow and disables
    OpenCode sharing, while the Human Owner's effectiveness-first policy permits
    repository source code to use eligible free endpoints without requiring ZDR
    or provider data-collection denial. OpenRouter may fail over between endpoints
    serving the same selected model; PCP remains authoritative for cross-model
    failover after a provider failure.
    """
    env = provider_env_for_model(model)
    normalized = (model or "").strip()
    if not normalized.startswith(_OPENROUTER_PREFIX):
        return env

    upstream_model = normalized.removeprefix(_OPENROUTER_PREFIX).strip()
    if not upstream_model or upstream_model == "free":
        raise RuntimeError(
            "OpenRouter coding runs require an explicit model; openrouter/free is not allowed"
        )

    config = {
        "$schema": "https://opencode.ai/config.json",
        "share": "disabled",
        # OpenCode 1.18.30 accepts this allowlist in OPENCODE_CONFIG_CONTENT.
        # It prevents mounted host configuration or credentials from selecting a
        # provider other than the provider PCP Router already selected.
        "enabled_providers": ["openrouter"],
        "provider": {
            "openrouter": {
                # Keep the selectable model set as narrow as the Router's
                # selected model. This is not an OpenRouter cross-model fallback
                # list. Endpoint fallback is allowed only for this same model.
                "whitelist": [upstream_model],
                "models": {
                    upstream_model: {
                        "options": {
                            "provider": {
                                "require_parameters": True,
                                "allow_fallbacks": True,
                            }
                        }
                    }
                },
            }
        },
    }
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(
        config, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    # Defense in depth for older OpenCode behavior; the inline `share=disabled`
    # policy above is the authoritative setting for current versions.
    env["OPENCODE_AUTO_SHARE"] = "false"
    return env


class OpenCodeAdapter(AgentAdapter):
    name = "opencode"

    def invocation_capabilities(self, mode: str) -> InvocationCapabilities:
        del mode
        return InvocationCapabilities(
            php_runtime=False,
            php_runtime_reason="runtime_container_php_unavailable",
        )

    async def run(self, *, workspace: Path, prompt: str, mode: str, timeout: int) -> AgentRun:
        agent = "plan" if mode in {"plan", "evaluate"} else "build"
        argv = ["opencode", "run", "--format", "json", "--agent", agent, "--dir", str(workspace)]
        if mode == "execute":
            argv.append("--auto")
        if self.model and self.model != "auto":
            argv += ["--model", self.model]
        argv.append(prompt)
        provider = provider_for_adapter(self.name, self.model)
        emit_developer_event(
            agent_lifecycle_event(
                adapter=self.name,
                provider=provider,
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
                    provider=provider,
                    model=self.model,
                )
            )

        timed_out: CommandTimeoutError | None = None
        try:
            result = await run_command(
                argv,
                cwd=workspace,
                timeout=timeout,
                env=opencode_env_for_model(self.model),
                on_stdout_line=on_stdout_line,
            )
        except CommandTimeoutError as exc:
            timed_out = exc
            result = CommandResult(
                argv=argv,
                returncode=124,
                stdout=exc.stdout,
                stderr=exc.stderr or str(exc),
            )

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
        failure_kind, failure_message = classify_provider_failure(
            result.stderr,
            result.stdout,
            "\n".join(errors),
            output,
        )
        effective_returncode = result.returncode
        if timed_out is not None:
            failure_kind = "timeout"
            failure_message = str(timed_out)
            effective_returncode = 124
        elif errors and effective_returncode == 0:
            effective_returncode = 70
        elif failure_kind and effective_returncode == 0:
            effective_returncode = 75
        emit_developer_event(
            agent_lifecycle_event(
                adapter=self.name,
                provider=provider,
                model=self.model,
                mode=mode,
                state="completed" if effective_returncode == 0 else "failed",
            )
        )
        return AgentRun(
            self.name, self.model, effective_returncode, output, result.stderr, usage, result.stdout,
            failure_kind=failure_kind, failure_message=failure_message,
        )
