from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import suppress
from pathlib import Path

import httpx

from .base import AgentAdapter, AgentRun, classify_provider_failure
from ..developer_stream import agent_lifecycle_event, agent_public_event, emit_developer_event


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


def _result_payload(event: dict) -> dict:
    value = event.get("result")
    return dict(value) if isinstance(value, dict) else dict(event)


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
    """Execute Antigravity on the WSL host through the constrained host bridge."""

    name = "antigravity_host"
    provider = "google_antigravity"

    async def _cancel_remote(self, base_url: str, token: str, run_id: str) -> None:
        with suppress(Exception):
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{base_url}/cancel",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"run_id": run_id},
                )

    async def _legacy_run(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        token: str,
        payload: dict,
    ) -> dict:
        response = await client.post(
            f"{base_url}/run",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        response.raise_for_status()
        return response.json()

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
        emit_developer_event(
            agent_lifecycle_event(
                adapter=self.name,
                provider=self.provider,
                model=self.model,
                mode=mode,
                state="started",
            )
        )

        bridge_result: dict = {}
        final_result: dict = {}
        raw_events: list[str] = []
        legacy_bridge: dict | None = None
        try:
            async with httpx.AsyncClient(timeout=timeout + 20) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/run-stream",
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                ) as response:
                    if response.status_code in {404, 405}:
                        legacy_bridge = await self._legacy_run(
                            client=client,
                            base_url=base_url,
                            token=token,
                            payload=payload,
                        )
                    else:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                event = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if not isinstance(event, dict):
                                continue
                            if event.get("bridge_event") == "result":
                                bridge_result = event
                                continue
                            raw_events.append(line[:12000])
                            if len(raw_events) > 100:
                                raw_events = raw_events[-100:]
                            if str(event.get("event") or "") == "result":
                                final_result = _result_payload(event)
                            emit_developer_event(
                                agent_public_event(
                                    event,
                                    workspace=workspace,
                                    mode=mode,
                                    adapter=self.name,
                                    provider=self.provider,
                                    model=self.model,
                                )
                            )
        except asyncio.CancelledError:
            # The host bridge owns the actual `agy` process. Cancelling only the
            # HTTP client would leave that process consuming quota, so explicitly
            # terminate the corresponding host-side run before propagating cancel.
            await self._cancel_remote(base_url, token, run_id)
            raise
        except (httpx.HTTPError, ValueError) as exc:
            message = f"Antigravity host bridge unavailable: {exc}"
            emit_developer_event(
                agent_lifecycle_event(
                    adapter=self.name,
                    provider=self.provider,
                    model=self.model,
                    mode=mode,
                    state="failed",
                    detail="Host bridge unavailable",
                )
            )
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

        if legacy_bridge is not None:
            stdout = legacy_bridge.get("stdout", "") or ""
            stderr = legacy_bridge.get("stderr", "") or ""
            returncode = int(legacy_bridge.get("returncode", 1))
            output = stdout
            usage: dict = {}
            error_text = ""
            agy = legacy_bridge.get("payload")
            if isinstance(agy, dict):
                output = str(agy.get("response") or "")
                usage = dict(agy.get("usage") or {})
                error_text = str(agy.get("error") or "")
                status = str(agy.get("status") or "").upper()
                if status and status != "SUCCESS" and returncode == 0:
                    returncode = 1
            raw = stdout
        else:
            stderr = str(bridge_result.get("stderr") or "")
            returncode = int(bridge_result.get("returncode", 1))
            output = str(final_result.get("response") or "")
            usage = dict(final_result.get("usage") or {})
            error_text = str(final_result.get("error") or "")
            status = str(final_result.get("status") or "").upper()
            if status and status not in {"SUCCESS", "COMPLETED", "DONE"} and returncode == 0:
                returncode = 1
            raw = "\n".join(raw_events)[-30000:]

        permission_denied, permission_message = _permission_soft_denied(
            stderr, error_text, raw, output
        )
        if permission_denied:
            returncode = 77
            failure_kind = "permission_denied"
            failure_message = permission_message
        else:
            failure_kind, failure_message = classify_provider_failure(
                stderr, error_text, raw, output
            )
            if returncode != 0 and not failure_kind:
                failure_kind = "provider_unavailable" if error_text else None
                failure_message = error_text or stderr or raw

        emit_developer_event(
            agent_lifecycle_event(
                adapter=self.name,
                provider=self.provider,
                model=self.model,
                mode=mode,
                state="completed" if returncode == 0 else "failed",
            )
        )
        return AgentRun(
            self.name,
            self.model,
            returncode,
            output,
            stderr,
            usage,
            raw,
            failure_kind=failure_kind,
            failure_message=failure_message,
        )
