from __future__ import annotations

import os
from typing import Any

import httpx


class DdevExecutorClient:
    def __init__(self) -> None:
        self.base = os.getenv("DDEV_EXECUTOR_URL", "http://ddev-executor:8790").rstrip("/")
        self.token = os.getenv("PLATFORM_INTERNAL_TOKEN", "change-me")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base}/health")
                return response.is_success
        except httpx.HTTPError:
            return False

    async def create_workspace(self, *, job_id: str, project_id: str, ref: str | None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base}/v1/workspaces",
                json={"job_id": job_id, "project_id": project_id, "ref": ref},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def remove_workspace(self, *, job_id: str, project_id: str, workspace: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.delete(
                f"{self.base}/v1/workspaces",
                params={"job_id": job_id, "project_id": project_id, "workspace": workspace},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def phase(self, *, job_id: str, project_id: str, workspace: str, phase: str, timeout_seconds: int | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(
                f"{self.base}/v1/phase",
                json={"job_id": job_id, "project_id": project_id, "workspace": workspace, "phase": phase, "timeout_seconds": timeout_seconds},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()
