from __future__ import annotations

import os
from typing import Any

import httpx


def _raise_for_status_with_detail(response: httpx.Response) -> None:
    if response.is_success:
        return
    detail = ""
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("detail"):
            detail = str(payload["detail"])
        else:
            detail = str(payload)
    except ValueError:
        detail = response.text
    message = f"DDEV executor HTTP {response.status_code}"
    if detail:
        message += f": {detail[-12000:]}"
    raise RuntimeError(message)


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

    async def cancel(self, *, job_id: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(
                    f"{self.base}/v1/cancel",
                    json={"job_id": job_id},
                    headers=self.headers,
                )
                response.raise_for_status()
                return bool(response.json().get("cancelled", False))
        except (httpx.HTTPError, ValueError):
            return False

    async def create_workspace(self, *, job_id: str, project_id: str, ref: str | None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=320) as client:
            response = await client.post(
                f"{self.base}/v1/workspaces",
                json={"job_id": job_id, "project_id": project_id, "ref": ref},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def publish_branch(
        self,
        *,
        job_id: str,
        project_id: str,
        workspace: str,
        branch: str,
        source_commit: str,
        expected_commit: str,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=320) as client:
            response = await client.post(
                f"{self.base}/v1/publish-branch",
                json={
                    "job_id": job_id,
                    "project_id": project_id,
                    "workspace": workspace,
                    "branch": branch,
                    "source_commit": source_commit,
                    "expected_commit": expected_commit,
                },
                headers=self.headers,
            )
            _raise_for_status_with_detail(response)
            return response.json()

    async def upsert_pull_request(
        self,
        *,
        job_id: str,
        project_id: str,
        branch: str,
        expected_commit: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base}/v1/github/pull-request",
                json={
                    "job_id": job_id,
                    "project_id": project_id,
                    "branch": branch,
                    "expected_commit": expected_commit,
                    "title": title,
                    "body": body,
                },
                headers=self.headers,
            )
            _raise_for_status_with_detail(response)
            return response.json()

    async def github_ci(self, *, project_id: str, commit: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f"{self.base}/v1/github/ci",
                params={"project_id": project_id, "commit": commit},
                headers=self.headers,
            )
            _raise_for_status_with_detail(response)
            return response.json()

    async def github_pull_request(self, *, project_id: str, pr_number: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f"{self.base}/v1/github/pm-bridge/pulls/{pr_number}",
                params={"project_id": project_id},
                headers=self.headers,
            )
            _raise_for_status_with_detail(response)
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
