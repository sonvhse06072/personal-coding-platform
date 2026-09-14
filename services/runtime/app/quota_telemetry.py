from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import psycopg
from psycopg.rows import dict_row

from .config import models_doc


DDL = """
CREATE TABLE IF NOT EXISTS cp_quota_snapshots (
  snapshot_key TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  provider TEXT NOT NULL,
  state_key TEXT,
  quota_id TEXT NOT NULL,
  window_name TEXT,
  used_percent DOUBLE PRECISION,
  remaining_percent DOUBLE PRECISION,
  reset_at TIMESTAMPTZ,
  observed_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  authoritative BOOLEAN NOT NULL DEFAULT TRUE,
  available BOOLEAN,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS cp_quota_snapshots_provider_idx
  ON cp_quota_snapshots(provider, expires_at DESC);

CREATE TABLE IF NOT EXISTS cp_quota_collectors (
  source TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  last_attempt_at TIMESTAMPTZ NOT NULL,
  last_success_at TIMESTAMPTZ,
  error TEXT
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp_percent(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return round(max(0.0, min(100.0, float(value))), 3)


def _parse_reset(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _logical_model_id(provider: str, upstream_model: str | None) -> str | None:
    needle = str(upstream_model or "").strip()
    if not needle:
        return None
    for model_id, cfg in (models_doc().get("models", {}) or {}).items():
        if str(cfg.get("provider") or "") != provider:
            continue
        if str(cfg.get("model") or "") == needle:
            return str(model_id)
    return None


def merge_provider_state(base: dict[str, Any] | None, telemetry: dict[str, Any] | None) -> dict[str, Any]:
    result = {str(key): dict(value or {}) for key, value in (base or {}).items()}
    for key, incoming_raw in (telemetry or {}).items():
        incoming = dict(incoming_raw or {})
        current = dict(result.get(str(key)) or {})
        result[str(key)] = {
            "healthy": bool(current.get("healthy", True)) and bool(incoming.get("healthy", True)),
            "quota_pressure": max(float(current.get("quota_pressure", 0.0) or 0.0), float(incoming.get("quota_pressure", 0.0) or 0.0)),
            "error_rate": max(float(current.get("error_rate", 0.0) or 0.0), float(incoming.get("error_rate", 0.0) or 0.0)),
            "latency_ms": max(int(current.get("latency_ms", 0) or 0), int(incoming.get("latency_ms", 0) or 0)),
            "predicted_success": current.get("predicted_success") if current.get("predicted_success") is not None else incoming.get("predicted_success"),
            "available": bool(current.get("available", True)) and bool(incoming.get("available", True)),
        }
    return result


class QuotaTelemetryStore:
    def __init__(self) -> None:
        self.dsn = os.getenv("DATABASE_URL", "postgresql://db:db@db:5432/db")

    def connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def init(self) -> None:
        with self.connect() as conn:
            conn.execute(DDL)
            conn.commit()

    def record_collector(self, source: str, *, success: bool, error: str | None = None) -> None:
        timestamp = utcnow()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO cp_quota_collectors(source,status,last_attempt_at,last_success_at,error)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT(source) DO UPDATE SET
                  status=EXCLUDED.status,
                  last_attempt_at=EXCLUDED.last_attempt_at,
                  last_success_at=CASE WHEN EXCLUDED.status='ok' THEN EXCLUDED.last_success_at ELSE cp_quota_collectors.last_success_at END,
                  error=EXCLUDED.error""",
                (source, "ok" if success else "error", timestamp, timestamp if success else None, (error or "")[:1000] or None),
            )
            conn.commit()

    def upsert(self, snapshot: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO cp_quota_snapshots
                (snapshot_key,source,provider,state_key,quota_id,window_name,used_percent,remaining_percent,
                 reset_at,observed_at,expires_at,authoritative,available,metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT(snapshot_key) DO UPDATE SET
                  source=EXCLUDED.source,
                  provider=EXCLUDED.provider,
                  state_key=EXCLUDED.state_key,
                  quota_id=EXCLUDED.quota_id,
                  window_name=EXCLUDED.window_name,
                  used_percent=EXCLUDED.used_percent,
                  remaining_percent=EXCLUDED.remaining_percent,
                  reset_at=EXCLUDED.reset_at,
                  observed_at=EXCLUDED.observed_at,
                  expires_at=EXCLUDED.expires_at,
                  authoritative=EXCLUDED.authoritative,
                  available=EXCLUDED.available,
                  metadata=EXCLUDED.metadata""",
                (
                    snapshot["snapshot_key"], snapshot["source"], snapshot["provider"], snapshot.get("state_key"),
                    snapshot["quota_id"], snapshot.get("window_name"), snapshot.get("used_percent"),
                    snapshot.get("remaining_percent"), snapshot.get("reset_at"), snapshot["observed_at"],
                    snapshot["expires_at"], bool(snapshot.get("authoritative", True)), snapshot.get("available"),
                    json.dumps(snapshot.get("metadata") or {}),
                ),
            )
            conn.commit()

    def provider_state(self) -> dict[str, Any]:
        now = utcnow()
        with self.connect() as conn:
            rows = list(conn.execute(
                """SELECT state_key, used_percent, available
                FROM cp_quota_snapshots
                WHERE state_key IS NOT NULL AND authoritative=TRUE AND expires_at>%s""",
                (now,),
            ).fetchall())
        result: dict[str, Any] = {}
        for row in rows:
            key = str(row.get("state_key") or "")
            if not key:
                continue
            current = result.setdefault(key, {
                "healthy": True,
                "quota_pressure": 0.0,
                "error_rate": 0.0,
                "latency_ms": 0,
                "predicted_success": None,
                "available": True,
            })
            used = _clamp_percent(row.get("used_percent"))
            if used is not None:
                current["quota_pressure"] = max(float(current["quota_pressure"]), used / 100.0)
            if row.get("available") is False:
                current["available"] = False
        return result

    def view(self) -> dict[str, Any]:
        with self.connect() as conn:
            snapshots = list(conn.execute(
                """SELECT snapshot_key,source,provider,state_key,quota_id,window_name,used_percent,
                          remaining_percent,reset_at,observed_at,expires_at,authoritative,available,metadata
                   FROM cp_quota_snapshots
                   ORDER BY provider, quota_id, window_name NULLS FIRST"""
            ).fetchall())
            collectors = list(conn.execute(
                "SELECT source,status,last_attempt_at,last_success_at,error FROM cp_quota_collectors ORDER BY source"
            ).fetchall())
        now = utcnow()
        for row in snapshots:
            row["fresh"] = bool(row.get("expires_at") and row["expires_at"] > now)
            for key in ("reset_at", "observed_at", "expires_at"):
                if row.get(key) is not None:
                    row[key] = row[key].isoformat()
        for row in collectors:
            for key in ("last_attempt_at", "last_success_at"):
                if row.get(key) is not None:
                    row[key] = row[key].isoformat()
        return {"snapshots": snapshots, "collectors": collectors, "provider_state": self.provider_state()}


@dataclass
class CodexQuotaCollector:
    ttl_seconds: int = 600

    async def _request(self) -> dict[str, Any]:
        codex = shutil.which("codex")
        if not codex:
            raise RuntimeError("codex executable unavailable")
        proc = await asyncio.create_subprocess_exec(
            codex, "app-server", "--listen", "stdio://",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin is not None and proc.stdout is not None

        async def send(payload: dict[str, Any]) -> None:
            proc.stdin.write((json.dumps(payload, separators=(",", ":")) + "\n").encode())
            await proc.stdin.drain()

        async def response(request_id: int) -> dict[str, Any]:
            while True:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=10)
                if not line:
                    raise RuntimeError("codex app-server closed before quota response")
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("id") == request_id:
                    if payload.get("error"):
                        raise RuntimeError(f"codex quota RPC failed: {str(payload['error'])[:500]}")
                    return dict(payload.get("result") or {})

        try:
            await send({
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {"name": "pcp-quota-telemetry", "version": "1.0.0"},
                    "capabilities": {"experimentalApi": False},
                },
            })
            await response(1)
            await send({"method": "initialized"})
            await send({"id": 2, "method": "account/rateLimits/read", "params": None})
            return await response(2)
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()

    def normalize(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        observed = utcnow()
        expires = observed + timedelta(seconds=self.ttl_seconds)
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
            state_key = f"quota:model:{logical_id}" if logical_id else "provider:openai"
            for window_name in ("primary", "secondary"):
                window = bucket.get(window_name)
                if not isinstance(window, dict):
                    continue
                used = _clamp_percent(window.get("usedPercent"))
                if used is None:
                    continue
                reset_at = _parse_reset(window.get("resetsAt"))
                available = bool(ordinary_allowed) if ordinary_allowed is not None else used < 100.0
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
                    "expires_at": expires,
                    "authoritative": True,
                    "available": available,
                    "metadata": {
                        "normal_model_slug": normal_model,
                        "window_duration_mins": window.get("windowDurationMins"),
                        "limit_name": bucket.get("limitName"),
                    },
                })
        return snapshots

    async def collect(self) -> list[dict[str, Any]]:
        return self.normalize(await self._request())


@dataclass
class AntigravityQuotaCollector:
    ttl_seconds: int = 600

    @staticmethod
    def _state_key(quota_id: str) -> str | None:
        lower = quota_id.lower()
        models = models_doc().get("models", {}) or {}
        for model_id, cfg in models.items():
            if str(cfg.get("provider") or "") != "google_antigravity":
                continue
            slug = str(cfg.get("model") or "").lower()
            if slug and slug in lower:
                return f"quota:model:{model_id}"
        if "gemini" in lower:
            return "quota:antigravity_gemini"
        if "claude" in lower or "gpt" in lower:
            return "quota:antigravity_claude_gpt"
        return None

    async def _request(self) -> dict[str, Any]:
        base = os.getenv("ANTIGRAVITY_BRIDGE_URL", "").rstrip("/")
        token = os.getenv("ANTIGRAVITY_BRIDGE_TOKEN", "").strip()
        if not base or not token:
            raise RuntimeError("Antigravity bridge quota telemetry is not configured")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base}/quota", headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
            return dict(response.json())

    def normalize(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        snapshot = payload.get("snapshot")
        if not isinstance(snapshot, dict):
            return []
        captured = _parse_reset(snapshot.get("captured_at")) or utcnow()
        expires = captured + timedelta(seconds=self.ttl_seconds)
        quota = snapshot.get("quota")
        if not isinstance(quota, dict):
            return []
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
            result.append({
                "snapshot_key": f"antigravity:{quota_id}",
                "source": "antigravity_statusline",
                "provider": "google_antigravity",
                "state_key": self._state_key(str(quota_id)),
                "quota_id": str(quota_id),
                "window_name": None,
                "used_percent": used,
                "remaining_percent": remaining,
                "reset_at": reset_at,
                "observed_at": captured,
                "expires_at": expires,
                "authoritative": True,
                "available": remaining_fraction > 0.0,
                "metadata": {
                    "reset_in_seconds": raw.get("reset_in_seconds"),
                    "plan_tier": snapshot.get("plan_tier"),
                    "model": snapshot.get("model"),
                },
            })
        return result

    async def collect(self) -> list[dict[str, Any]]:
        return self.normalize(await self._request())


class QuotaTelemetryService:
    def __init__(self, store: QuotaTelemetryStore) -> None:
        self.store = store
        self.interval = max(60, int(os.getenv("QUOTA_TELEMETRY_INTERVAL_SECONDS", "300")))
        self.collectors = [CodexQuotaCollector(), AntigravityQuotaCollector()]
        self._task: asyncio.Task | None = None

    async def refresh(self) -> None:
        for collector in self.collectors:
            source = "codex_app_server" if isinstance(collector, CodexQuotaCollector) else "antigravity_statusline"
            try:
                snapshots = await collector.collect()
                for snapshot in snapshots:
                    self.store.upsert(snapshot)
                self.store.record_collector(source, success=True)
            except Exception as exc:
                self.store.record_collector(source, success=False, error=f"{type(exc).__name__}: {exc}")

    async def _loop(self) -> None:
        while True:
            await self.refresh()
            await asyncio.sleep(self.interval)

    async def start(self) -> None:
        self.store.init()
        self._task = asyncio.create_task(self._loop(), name="provider-quota-telemetry")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
