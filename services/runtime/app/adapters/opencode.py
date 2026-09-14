from __future__ import annotations

import json
import os
from pathlib import Path

from .base import AgentAdapter, AgentRun, classify_provider_failure
from ..shell import run_command


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

    OpenRouter coding jobs use an explicit model and an inline OpenCode provider
    configuration. The inline policy is deliberately stricter than account
    defaults: private repository content may be sent only to endpoints that deny
    provider data collection and advertise Zero Data Retention. OpenRouter may
    fail over between eligible endpoints for this same model, but PCP remains the
    authority for choosing a different model after a provider failure.
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
        "provider": {
            "openrouter": {
                "models": {
                    upstream_model: {
                        "options": {
                            "provider": {
                                "data_collection": "deny",
                                "zdr": True,
                                "require_parameters": True,
                                "allow_fallbacks": True,
                            }
                        }
                    }
                }
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

    async def run(self, *, workspace: Path, prompt: str, mode: str, timeout: int) -> AgentRun:
        agent = "plan" if mode in {"plan", "evaluate"} else "build"
        argv = ["opencode", "run", "--format", "json", "--agent", agent, "--dir", str(workspace)]
        if mode == "execute":
            argv.append("--auto")
        if self.model and self.model != "auto":
            argv += ["--model", self.model]
        argv.append(prompt)
        result = await run_command(
            argv,
            cwd=workspace,
            timeout=timeout,
            env=opencode_env_for_model(self.model),
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
