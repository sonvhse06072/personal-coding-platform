from __future__ import annotations

import os
from pathlib import Path

import httpx

from .base import AgentAdapter, AgentRun, classify_provider_failure


class AntigravityAdapter(AgentAdapter):
    """Execute Antigravity on the WSL host through the constrained host bridge.

    Individual Antigravity sessions are stored in the host OS keyring, so running
    `agy` natively preserves the signed-in account/quota pool without exposing the
    host keyring or D-Bus session to the coding container.
    """

    name = "antigravity_host"

    async def run(self, *, workspace: Path, prompt: str, mode: str, timeout: int) -> AgentRun:
        base_url = os.getenv("ANTIGRAVITY_BRIDGE_URL", "http://host.docker.internal:8792").rstrip("/")
        token = os.getenv("ANTIGRAVITY_BRIDGE_TOKEN", "")
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

        effort = "high" if mode in {"plan", "evaluate"} else "medium"
        payload = {
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

        failure_kind, failure_message = classify_provider_failure(stderr, error_text, stdout, output)
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
