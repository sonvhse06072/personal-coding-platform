from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
import re

from .config import models_doc
from .quota_telemetry import (
    AntigravityQuotaCollector,
    CodexQuotaCollector,
    QuotaTelemetryService,
    _clamp_percent,
    _logical_model_id,
    _parse_reset,
    utcnow,
)


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _expires_at(observed: datetime, ttl_seconds: int, reset_at: datetime | None) -> datetime:
    ttl = observed + timedelta(seconds=ttl_seconds)
    # A snapshot describing a pre-reset allowance must stop influencing Router at
    # the provider-reported reset boundary. It is not evidence of post-reset
    # capacity; the next poll will repopulate fresh values.
    if reset_at is not None and reset_at > observed:
        return min(ttl, reset_at)
    return ttl


class PolicyCodexQuotaCollector(CodexQuotaCollector):
    """Codex quota normalization that never infers recovery from reset time alone."""

    def normalize(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        observed = utcnow()
        ordinary_allowed = payload.get("ordinaryUsageAllowed")
        buckets = payload.get("rateLimitsByLimitId")
        if not isinstance(buckets, dict) or not buckets:
            single = payload.get("rateLimits")
            buckets = {"codex": single} if isinstance(single, dict) else {}
        snapshots: list[dict[str, Any]] = []
        for bucket_id, bucket_raw in buckets.items():
            if not isinstance(bucket_raw, dict):
                continue
            bucket = dict(bucket_raw)
            normal_model = str(bucket.get("normalModelSlug") or "").strip() or None
            logical_id = _logical_model_id("openai", normal_model)
            # Codex ChatGPT allowance is a shared registered quota scope, not
            # generic OpenAI provider health and not a per-model health marker.
            # Keep every Codex subscription bucket under the shared group so a
            # Terra exhaustion does not mark provider:openai and post-reset
            # telemetry can rehabilitate the exact durable quota key.
            quota_group = ""
            if logical_id:
                quota_group = str(
                    (models_doc().get("models", {}).get(logical_id, {}) or {}).get("quota_group") or ""
                ).strip()
            state_key = f"quota:{quota_group}" if quota_group else "quota:codex_chatgpt_plus"
            for window_name in ("primary", "secondary"):
                window = bucket.get(window_name)
                if not isinstance(window, dict):
                    continue
                used = _clamp_percent(window.get("usedPercent"))
                if used is None:
                    continue
                reset_at = _parse_reset(window.get("resetsAt"))
                # ordinaryUsageAllowed=false is authoritative quota denial for
                # Codex ordinary usage. A full individual window is unavailable.
                # A reset timestamp never means quota has recovered by itself.
                available = ordinary_allowed is not False and used < 100.0
                snapshots.append({
                    "snapshot_key": f"codex:{bucket_id}:{window_name}",
                    "source": "codex_app_server",
                    "provider": "openai",
                    "state_key": state_key,
                    "quota_id": str(bucket_id),
                    "window_name": window_name,
                    "used_percent": used,
                    "remaining_percent": round(100.0 - used, 3),
                    "reset_at": reset_at,
                    "observed_at": observed,
                    "expires_at": _expires_at(observed, self.ttl_seconds, reset_at),
                    "authoritative": True,
                    "available": available,
                    "metadata": {
                        "normal_model_slug": normal_model,
                        "window_duration_mins": window.get("windowDurationMins"),
                        "limit_name": bucket.get("limitName"),
                        "plan_type": bucket.get("planType"),
                    },
                })
        return snapshots


class PolicyAntigravityQuotaCollector(AntigravityQuotaCollector):
    @staticmethod
    def _state_key(quota_id: str, upstream_model: str | None = None) -> str | None:
        compact_id = _compact(quota_id)
        compact_upstream = _compact(upstream_model)
        models = models_doc().get("models", {}) or {}
        for model_id, cfg in models.items():
            if str(cfg.get("provider") or "") != "google_antigravity":
                continue
            compact_slug = _compact(cfg.get("model"))
            if compact_slug and (
                compact_slug == compact_id
                or compact_slug == compact_upstream
                or compact_slug in compact_id
                or (compact_upstream and compact_slug in compact_upstream)
            ):
                return f"quota:model:{model_id}"
        lower = str(quota_id or "").lower()
        if "gemini" in lower:
            return "quota:antigravity_gemini"
        if "claude" in lower or "gpt" in lower:
            return "quota:antigravity_claude_gpt"
        return None

    def normalize(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        snapshot = payload.get("snapshot")
        if not isinstance(snapshot, dict):
            return []
        captured = _parse_reset(snapshot.get("captured_at")) or utcnow()
        quota = snapshot.get("quota")
        if not isinstance(quota, dict):
            return []
        source = str(payload.get("source") or "antigravity_statusline")[:80]
        source_supported = bool(payload.get("source_supported", source == "antigravity_statusline"))
        result: list[dict[str, Any]] = []
        for quota_id, raw in quota.items():
            if not isinstance(raw, dict):
                continue
            remaining_fraction = raw.get("remaining_fraction")
            if not isinstance(remaining_fraction, (int, float)) or isinstance(remaining_fraction, bool):
                continue
            remaining_fraction = max(0.0, min(1.0, float(remaining_fraction)))
            remaining = round(remaining_fraction * 100.0, 3)
            used = round(100.0 - remaining, 3)
            reset_at = _parse_reset(raw.get("reset_time"))
            upstream_model = str(raw.get("upstream_model") or "").strip() or None
            result.append({
                "snapshot_key": f"antigravity:{quota_id}",
                "source": source,
                "provider": "google_antigravity",
                "state_key": self._state_key(str(quota_id), upstream_model),
                "quota_id": str(quota_id),
                "window_name": None,
                "used_percent": used,
                "remaining_percent": remaining,
                "reset_at": reset_at,
                "observed_at": captured,
                "expires_at": _expires_at(captured, self.ttl_seconds, reset_at),
                # Both sources originate from Antigravity's own local state. The
                # local GetUserStatus transport is unsupported, so that fact stays
                # explicit in metadata even though the quota values are provider data.
                "authoritative": True,
                "available": remaining_fraction > 0.0,
                "metadata": {
                    "reset_in_seconds": raw.get("reset_in_seconds"),
                    "plan_tier": snapshot.get("plan_tier"),
                    "model": snapshot.get("model"),
                    "upstream_model": upstream_model,
                    "source_supported": source_supported,
                    "source_contract": snapshot.get("source_contract"),
                },
            })
        return result


class PolicyQuotaTelemetryService(QuotaTelemetryService):
    def __init__(self, store) -> None:
        super().__init__(store)
        self.collectors = [PolicyCodexQuotaCollector(), PolicyAntigravityQuotaCollector()]

    async def refresh(self) -> None:
        for collector in self.collectors:
            collector_name = "codex_app_server" if isinstance(collector, PolicyCodexQuotaCollector) else "antigravity_quota"
            try:
                snapshots = await collector.collect()
                for snapshot in snapshots:
                    self.store.upsert(snapshot)
                self.store.record_collector(collector_name, success=True)
            except Exception as exc:
                self.store.record_collector(
                    collector_name,
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                )

    async def _loop(self) -> None:
        while True:
            try:
                await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Database/provider telemetry outages must not kill the long-lived
                # advisory collector. A later interval can recover automatically.
                pass
            await asyncio.sleep(self.interval)
