from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_PROVIDER_FAILURE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "quota_exhausted",
        (
            "usage limit",
            "usage_limit",
            "quota exceeded",
            "quota_exceeded",
            "insufficient_quota",
            "credit balance",
            "credits exhausted",
            "limit reached",
            "reached your limit",
            "you have reached",
            "you've reached",
            "resource_exhausted",
        ),
    ),
    (
        "rate_limited",
        (
            "rate limit",
            "rate_limit",
            "too many requests",
            "http 429",
            "status 429",
        ),
    ),
    (
        "authentication",
        (
            "authentication failed",
            "not authenticated",
            "unauthorized",
            "invalid api key",
            "invalid_api_key",
            "please login",
            "please log in",
            "authentication required",
            "failed to retrieve token",
            "secret keyring is locked",
        ),
    ),
    (
        "provider_unavailable",
        (
            "service unavailable",
            "provider unavailable",
            "temporarily unavailable",
            "overloaded",
            "capacity",
            "http 503",
            "status 503",
            "unexpected server error",
            "internal server error",
        ),
    ),
    (
        "workspace_untrusted",
        (
            "fataluntrustedworkspaceerror",
            "not running in a trusted directory",
            "current folder is not trusted",
            "folder is not trusted",
            "approval mode overridden to default because the current folder is not trusted",
        ),
    ),
)


def classify_provider_failure(*parts: str) -> tuple[str | None, str | None]:
    """Classify resource/provider failures from CLI output.

    Coding CLIs do not always return a non-zero exit code when an upstream
    allowance/provider fails. The runtime therefore inspects the machine-readable
    and human-readable output as a second, deterministic guard.
    """
    text = "\n".join(part for part in parts if part).strip()
    lower = text.lower()
    for kind, patterns in _PROVIDER_FAILURE_PATTERNS:
        if any(pattern in lower for pattern in patterns):
            return kind, text[-12000:]
    return None, None


@dataclass
class AgentRun:
    adapter: str
    model: str
    returncode: int
    output: str
    stderr: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    raw: str = ""
    failure_kind: str | None = None
    failure_message: str | None = None

    @property
    def provider_failed(self) -> bool:
        return self.failure_kind in {
            "quota_exhausted",
            "rate_limited",
            "authentication",
            "provider_unavailable",
            "timeout",
        }


@dataclass(frozen=True)
class InvocationCapabilities:
    """Verification surfaces available to one adapter invocation."""

    local_listener: bool = True
    php_runtime: bool = True
    reason: str | None = None
    php_runtime_reason: str | None = None


class AgentAdapter:
    name = "base"

    def __init__(self, model: str, reasoning_effort: str | None = None):
        self.model = model
        self.reasoning_effort = reasoning_effort

    def invocation_capabilities(self, mode: str) -> InvocationCapabilities:
        del mode
        return InvocationCapabilities()

    async def run(self, *, workspace: Path, prompt: str, mode: str, timeout: int) -> AgentRun:
        raise NotImplementedError
