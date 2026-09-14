from __future__ import annotations

import os
from typing import Any

import httpx

from .quota_runtime import quota_coordinator


class RouterClient:
    def __init__(self) -> None:
        self.base = os.getenv("ROUTER_URL", "http://router:8090").rstrip("/")
        self.token = os.getenv("ROUTER_API_TOKEN", "change-me")

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

    async def route(self, payload: dict[str, Any]) -> dict[str, Any]:
        enriched = await quota_coordinator.enrich(payload)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.base}/v1/route", json=enriched, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def staff(self, payload: dict[str, Any]) -> dict[str, Any]:
        enriched = await quota_coordinator.enrich(payload)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.base}/v1/staff", json=enriched, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def reassess(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.base}/v1/reassess", json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
