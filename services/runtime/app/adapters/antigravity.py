from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import suppress
from pathlib import Path

import httpx

from .base import AgentAdapter, AgentRun, classify_provider_failure


_PERMISSION_DENIED_PATTERNS = (
    'a tool required the "unsandboxed" permission',
    "headless mode cannot prompt for",
    "was auto-denied",
)


def _bridge_config() -> tuple[str, str]:
    return (
        os.getenv("ANTIGRAVITY_BRIDGE_URL", "http://host.docker.internal:8792").rstrip("/"),
        os.getenv("ANTIGRAVITY_BRIDGE_TOKEN", ""),
    )


def _permission_soft_denied(*parts: str) -> tuple[bool, str]:
    text = "\n".join(part for part in parts if part).strip()
    lower = text.lower()
    return any(pattern in lower for pattern in _PERMISSION_DENIED_PATTERNS), text[-12000:]


async def cancel_all_antigravity_runs() -> int:
    """Best-effort cleanup for host-side runs orphaned by a runtime restart."""
    base_url, token = _bridge_config()
    if not token:
        return 0
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{base_url}/cancel-all",
                headers={"Authorization": f"Bearer {token}"},
                json={},
            )
            response.raise_for_status()
            return int(response.json().get("cancelled", 0))
    except (httpx.HTTPError, ValueError, TypeError):
        return 0


class AntigravityAdapter(AgentAdapter):
    """Execute Antigravity on the WSL host through the constrained host bridge.

    Individual Antigravity sessions are stored in the host OS keyring, so running
    `agy` natively preserves the signed-in account/quota pool without exposing the
    host keyring or D-Bus session to the coding container.
    """

    name = "antigravity_host"

    async def _cancel_remote(self, base_url: str, token: str, run_id: str) -> None:
        with suppress(Exception):
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{base_url}/cancel",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"run_id": run_id},
                )

    async def run(self, *, workspace: Path, prompt: str, mode: str, timeout: int) -> AgentRun:
        base_url, token = _bridge_config()
        if not token:
            return AgentRun(
                self.name,
                self.model,
                78,
                "",
                "ANTIGRAVITY_BRIDGE_TOKEN is not configured",
                {},
                "",
                failure_kind="authentication",
                failure_message="Antigravity host bridge token is not configured",
            )

        run_id = uuid.uuid4().hex
        effort = "high" if mode in {"plan", "evaluate"} else "medium"
        payload = {
            "run_id": run_id,
            "workspace": str(workspace),
            "prompt": prompt,
            "model": self.model or "auto",
            "effort": effort,
            "mode": mode,
            "timeout": timeout,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout + 20) as client:
                response = await client.post(
                    f"{base_url}/run",
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                )
                response.raise_for_status()
                bridge = response.json()
        except asyncio.CancelledError:
            # The host bridge owns the actual `agy` process. Cancelling only the
            # HTTP client would leave that process consuming quota, so explicitly
            # terminate the corresponding host-side run before propagating cancel.
            await self._cancel_remote(base_url, token, run_id)
            raise
        except (httpx.HTTPError, ValueError) as exc:
            message = f"Antigravity host bridge unavailable: {exc}"
            return AgentRun(
                self.name,
                self.model,
                76,
                "",
                message,
                {},
                "",
                failure_kind="provider_unavailable",
                failure_message=message,
            )

        stdout = bridge.get("stdout", "") or ""
        stderr = bridge.get("stderr", "") or ""
        returncode = int(bridge.get("returncode", 1))
        output = stdout
        usage: dict = {}
        error_text = ""

        agy = bridge.get("payload")
        if isinstance(agy, dict):
            output = str(agy.get("response") or "")
            usage = dict(agy.get("usage") or {})
            error_text = str(agy.get("error") or "")
            status = str(agy.get("status") or "").upper()
            if status and status != "SUCCESS" and returncode == 0:
                returncode = 1

        permission_denied, permission_message = _permission_soft_denied(
            stderr, error_text, stdout, output
        )
        if permission_denied:
            # Antigravity headless permission denials are intentionally soft: the
            # CLI exits 0. Surface them as a deterministic non-provider failure so
            # Runtime records the real cause and can model-failover without marking
            # the Google provider unhealthy or consuming repair budget.
            returncode = 77
            failure_kind = "permission_denied"
            failure_message = permission_message
        else:
            failure_kind, failure_message = classify_provider_failure(
                stderr, error_text, stdout, output
            )
            if returncode != 0 and not failure_kind:
                failure_kind = "provider_unavailable" if error_text else None
                failure_message = error_text or stderr or stdout

        return AgentRun(
            self.name,
            self.model,
            returncode,
            output,
            stderr,
            usage,
            stdout,
            failure_kind=failure_kind,
            failure_message=failure_message,
        )
