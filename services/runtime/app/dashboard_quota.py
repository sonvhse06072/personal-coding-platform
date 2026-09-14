from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Cookie

from .dashboard import _require_session


def create_quota_dashboard_router(telemetry: Any, readiness: Any) -> APIRouter:
    """Read-only quota surface protected by the existing dashboard session."""
    router = APIRouter()

    @router.get("/v1/dashboard/provider-quotas", include_in_schema=False)
    def provider_quotas(
        pcp_dashboard_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_session(pcp_dashboard_session)
        ready = bool(readiness())
        return {
            "storage_ready": ready,
            "poll_seconds": telemetry.poll_seconds,
            "stale_seconds": telemetry.stale_seconds,
            "snapshots": telemetry.snapshots() if ready else [],
            "collector_errors": dict(telemetry.last_errors) if ready else {},
        }

    return router
