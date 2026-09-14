from __future__ import annotations

import asyncio
import json
import os
import shutil
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import httpx

from .config import models_doc


QUOTA_POLL_SECONDS = 300
QUOTA_STALE_SECONDS = 600
_MAX_LINE_BYTES = 2_000_000
_SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "cookie",
    "authorization",
    "credential",
    "private_key",
    "access_key",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _parse_timestamp(value: Any, *, observed_at: datetime, reset_in_seconds: Any = None) -> str | None:
    if isinstance(value, (int, float)):
        try:
            return _iso(datetime.fromtimestamp(float(value), tz=timezone.utc))
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        raw = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return _iso(parsed)
        except ValueError:
            return None
    if isinstance(reset_in_seconds, (int, float)):
        try:
            return _iso(observed_at + timedelta(seconds=max(0.0, float(reset_in_seconds))))
        except (OverflowError, ValueError):
            return None
    return None


def _percent(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return round(max(0.0, min(100.0, float(value))), 4)


def _remaining_percent(node: dict[str, Any]) -> float | None:
    for key in ("remainingPercent", "remaining_percent", "remainingPercentage", "remaining_percentage"):
        value = _percent(node.get(key))
        if value is not None:
            return value
    for key in ("remainingFraction", "remaining_fraction"):
        value = node.get(key)
        if isinstance(value, (int, float)):
            return round(max(0.0, min(1.0, float(value))) * 100.0, 4)
    return None


def _used_percent(node: dict[str, Any]) -> float | None:
    for key in ("usedPercent", "used_percent", "usedPercentage", "used_percentage"):
        value = _percent(node.get(key))
        if value is not None:
            return value
    remaining = _remaining_percent(node)
    if remaining is not None:
        return round(100.0 - remaining, 4)
    return None


def _reset_value(node: dict[str, Any]) -> tuple[Any, Any]:
    reset = None
    for key in ("resetsAt", "resets_at", "resetTime", "reset_time"):
        if node.get(key) is not None:
            reset = node.get(key)
            break
    reset_in = None
    for key in ("resetInSeconds", "reset_in_seconds"):
        if node.get(key) is not None:
            reset_in = node.get(key)
            break
    return reset, reset_in


def _window_snapshot(
    *,
    provider: str,
    quota_key: str,
    window_name: str,
    window: dict[str, Any],
    observed_at: datetime,
    source: str,
    quota_group: str | None = None,
    model_id: str | None = None,
    ordinary_usage_allowed: bool | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    used = _used_percent(window)
    remaining = _remaining_percent(window)
    if remaining is None and used is not None:
        remaining = round(100.0 - used, 4)
    if used is None and remaining is not None:
        used = round(100.0 - remaining, 4)
    if used is None and remaining is None:
        return None
    reset, reset_in = _reset_value(window)
    resets_at = _parse_timestamp(reset, observed_at=observed_at, reset_in_seconds=reset_in)
    window_minutes = window.get("windowDurationMins", window.get("window_duration_mins"))
    if not isinstance(window_minutes, (int, float)):
        window_minutes = None
    available: bool | None
    if ordinary_usage_allowed is False or (used is not None and used >= 100.0):
        available = False
    elif ordinary_usage_allowed is True and used is not None and used < 100.0:
        available = True
    elif remaining is not None:
        # Antigravity remaining_fraction is itself an authoritative capacity
        # signal. Codex callers pass ordinary_usage_allowed separately and the
        # parser below will set recovery to unknown when backend permission is
        # unavailable.
        available = remaining > 0.0
    else:
        available = None
    return {
        "provider": provider,
        "quota_key": f"{quota_key}:{window_name}",
        "model_id": model_id,
        "quota_group": quota_group,
        "used_percent": used,
        "remaining_percent": remaining,
        "available": available,
        "resets_at": resets_at,
        "window_minutes": int(window_minutes) if window_minutes is not None else None,
        "observed_at": _iso(observed_at),
        "source": source,
        "status": "fresh",
        "details": details or {},
    }


def normalize_codex_rate_limits(result: dict[str, Any], *, observed_at: datetime | None = None) -> list[dict[str, Any]]:
    """Normalize the official Codex `account/rateLimits/read` response."""
    observed_at = observed_at or utcnow()
    ordinary = result.get("ordinaryUsageAllowed")
    ordinary_allowed = ordinary if isinstance(ordinary, bool) else None
    buckets = result.get("rateLimitsByLimitId")
    entries: list[tuple[str, dict[str, Any]]] = []
    if isinstance(buckets, dict) and buckets:
        entries.extend((str(key), value) for key, value in buckets.items() if isinstance(value, dict))
    else:
        legacy = result.get("rateLimits")
        if isinstance(legacy, dict):
            limit_id = str(legacy.get("limitId") or "codex")
            entries.append((limit_id, legacy))

    snapshots: list[dict[str, Any]] = []
    for limit_id, bucket in entries:
        group = "codex_chatgpt_plus" if limit_id == "codex" else None
        details = {
            "limit_id": limit_id,
            "limit_name": bucket.get("limitName"),
            "normal_model_slug": bucket.get("normalModelSlug"),
            "ordinary_usage_allowed": ordinary_allowed,
        }
        for window_name in ("primary", "secondary"):
            window = bucket.get(window_name)
            if not isinstance(window, dict):
                continue
            snapshot = _window_snapshot(
                provider="openai",
                quota_key=limit_id,
                window_name=window_name,
                window=window,
                observed_at=observed_at,
                source="codex_app_server",
                quota_group=group,
                ordinary_usage_allowed=ordinary_allowed,
                details=details,
            )
            if snapshot is None:
                continue
            # Codex explicitly documents ordinaryUsageAllowed=null as
            # insufficient evidence for recovery. Percentages still inform
            # pressure/exhaustion, but do not clear an existing unavailable
            # quota marker merely because used_percent fell below 100.
            if ordinary_allowed is None and snapshot["available"] is True:
                snapshot["available"] = None
            snapshots.append(snapshot)
    return snapshots


def _safe_tree(value: Any, *, depth: int = 0) -> Any:
    """Bound arbitrary provider data while excluding credential-shaped fields."""
    if depth > 8:
        return None
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:100]:
            text = str(key)
            lower = text.lower()
            if any(part in lower for part in _SENSITIVE_KEY_PARTS):
                continue
            result[text[:120]] = _safe_tree(item, depth=depth + 1)
        return result
    if isinstance(value, list):
        return [_safe_tree(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:1000]


def _antigravity_models() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for model_id, model in (models_doc().get("models") or {}).items():
        if isinstance(model, dict) and model.get("provider") == "google_antigravity":
            result[str(model_id)] = dict(model)
    return result


def _norm_identifier(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _antigravity_target(identifier: str, models: dict[str, dict[str, Any]]) -> tuple[str | None, str | None]:
    needle = _norm_identifier(identifier)
    if needle:
        for model_id, model in models.items():
            candidates = {_norm_identifier(model_id), _norm_identifier(model.get("model"))}
            if needle in candidates or any(candidate and (candidate in needle or needle in candidate) for candidate in candidates):
                return model_id, str(model.get("quota_group") or "") or None
    lowered = str(identifier or "").lower()
    if "gemini" in lowered:
        return None, "antigravity_gemini"
    if "claude" in lowered or "gpt" in lowered:
        return None, "antigravity_claude_gpt"
    return None, None


def _quota_nodes(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], dict[str, Any]]]:
    if isinstance(value, dict):
        keys = set(value)
        metrics = {
            "remainingFraction", "remaining_fraction", "remainingPercent", "remaining_percent",
            "remainingPercentage", "remaining_percentage", "usedPercent", "used_percent",
            "usedPercentage", "used_percentage", "resetTime", "reset_time",
            "resetInSeconds", "reset_in_seconds", "resetsAt", "resets_at",
        }
        if keys & metrics and (_used_percent(value) is not None or _remaining_percent(value) is not None):
            yield path, value
        for key, item in value.items():
            yield from _quota_nodes(item, path + (str(key),))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _quota_nodes(item, path + (str(index),))


def normalize_antigravity_usage(payload: Any, *, observed_at: datetime | None = None) -> list[dict[str, Any]]:
    """Normalize Antigravity `/usage` structured output without assuming one root schema."""
    observed_at = observed_at or utcnow()
    safe = _safe_tree(payload)
    models = _antigravity_models()
    snapshots: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path, node in _quota_nodes(safe):
        identifier = ""
        for key in ("modelId", "model_id", "model", "id", "name", "displayName", "display_name", "bucket"):
            if isinstance(node.get(key), str) and node.get(key):
                identifier = str(node[key])
                break
        if not identifier and path:
            identifier = path[-1]
        if not identifier:
            identifier = "quota"
        model_id, quota_group = _antigravity_target(identifier, models)
        used = _used_percent(node)
        remaining = _remaining_percent(node)
        if remaining is None and used is not None:
            remaining = round(100.0 - used, 4)
        if used is None and remaining is not None:
            used = round(100.0 - remaining, 4)
        if used is None and remaining is None:
            continue
        reset, reset_in = _reset_value(node)
        resets_at = _parse_timestamp(reset, observed_at=observed_at, reset_in_seconds=reset_in)
        quota_key = str(identifier)[:200]
        unique = f"{quota_key}|{model_id or ''}|{quota_group or ''}|{resets_at or ''}|{used}"
        if unique in seen:
            continue
        seen.add(unique)
        snapshots.append({
            "provider": "google_antigravity",
            "quota_key": quota_key,
            "model_id": model_id,
            "quota_group": quota_group,
            "used_percent": used,
            "remaining_percent": remaining,
            "available": remaining > 0.0 if remaining is not None else (used < 100.0 if used is not None else None),
            "resets_at": resets_at,
            "window_minutes": None,
            "observed_at": _iso(observed_at),
            "source": "antigravity_usage",
            "status": "fresh",
            "details": {"path": ".".join(path)[:500]},
        })
    return snapshots


async def collect_codex_quota(*, timeout: float = 12.0) -> list[dict[str, Any]]:
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("codex_not_installed")
    proc = await asyncio.create_subprocess_exec(
        codex,
        "app-server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdin is not None and proc.stdout is not None

    async def send(message: dict[str, Any]) -> None:
        proc.stdin.write(json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n")
        await proc.stdin.drain()

    async def response_for(request_id: int) -> dict[str, Any]:
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            if not line:
                raise RuntimeError("codex_app_server_closed")
            if len(line) > _MAX_LINE_BYTES:
                raise RuntimeError("codex_app_server_response_too_large")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict) or message.get("id") != request_id:
                continue
            if message.get("error") is not None:
                raise RuntimeError("codex_rate_limits_request_failed")
            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("codex_rate_limits_invalid_response")
            return result

    try:
        await send({
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {"name": "pcp-quota-telemetry", "version": "1.0.0"},
                "capabilities": {"experimentalApi": False},
            },
        })
        await response_for(1)
        await send({"method": "notifications/initialized"})
        await send({
            "id": 2,
            "method": "account/rateLimits/read",
            "params": {"excludeResetCreditDetails": True},
        })
        result = await response_for(2)
        snapshots = normalize_codex_rate_limits(result)
        if not snapshots:
            raise RuntimeError("codex_rate_limits_empty")
        return snapshots
    finally:
        if proc.stdin and not proc.stdin.is_closing():
            proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()


async def collect_antigravity_quota(*, timeout: float = 20.0) -> list[dict[str, Any]]:
    base_url = os.getenv("ANTIGRAVITY_BRIDGE_URL", "http://host.docker.internal:8792").rstrip("/")
    token = os.getenv("ANTIGRAVITY_BRIDGE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("antigravity_bridge_token_not_configured")
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/quota",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        response.raise_for_status()
        body = response.json()
    payload = body.get("payload") if isinstance(body, dict) else None
    snapshots = normalize_antigravity_usage(payload)
    if not snapshots:
        raise RuntimeError("antigravity_quota_empty")
    return snapshots


class ProviderQuotaTelemetry:
    """Durable, authoritative-first quota state used for routing and observability."""

    def __init__(self, storage: Any) -> None:
        self.storage = storage
        self.poll_seconds = max(60, int(os.getenv("QUOTA_POLL_SECONDS", str(QUOTA_POLL_SECONDS))))
        self.stale_seconds = max(self.poll_seconds, int(os.getenv("QUOTA_STALE_SECONDS", str(QUOTA_STALE_SECONDS))))
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self.last_errors: dict[str, str] = {}

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.refresh()
            except Exception:
                # Per-provider failures are already captured in refresh(); this
                # outer guard keeps telemetry incapable of taking Runtime down.
                pass
            await asyncio.sleep(self.poll_seconds)

    def _provider_is_stale(self, provider: str) -> bool:
        rows = self.storage.list_quota_snapshots(provider=provider)
        if not rows:
            return True
        latest = max(row["observed_at"] for row in rows if row.get("observed_at") is not None)
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        return (utcnow() - latest).total_seconds() >= self.stale_seconds

    async def refresh_if_stale(self) -> None:
        providers = {
            provider
            for provider in ("openai", "google_antigravity")
            if self._provider_is_stale(provider)
        }
        if providers:
            await self.refresh(providers=providers)

    async def refresh(self, *, providers: set[str] | None = None) -> dict[str, Any]:
        requested = providers or {"openai", "google_antigravity"}
        async with self._lock:
            results: dict[str, Any] = {}
            collectors = {
                "openai": collect_codex_quota,
                "google_antigravity": collect_antigravity_quota,
            }
            for provider in sorted(requested):
                collector = collectors.get(provider)
                if collector is None:
                    continue
                try:
                    snapshots = await collector()
                    self.storage.replace_provider_quota_snapshots(provider, snapshots)
                    self.last_errors.pop(provider, None)
                    results[provider] = {"status": "ok", "count": len(snapshots)}
                except Exception as exc:
                    # Keep the last successful durable snapshot. Its age will
                    # naturally become stale; never replace known data with a
                    # fabricated zero/100 value because a collector failed.
                    self.last_errors[provider] = type(exc).__name__ + ": " + str(exc)[:300]
                    results[provider] = {"status": "unavailable"}
            return results

    def snapshots(self) -> list[dict[str, Any]]:
        cutoff = utcnow() - timedelta(seconds=self.stale_seconds)
        rows: list[dict[str, Any]] = []
        for value in self.storage.list_quota_snapshots():
            row = dict(value)
            observed = row.get("observed_at")
            if isinstance(observed, datetime):
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=timezone.utc)
                row["status"] = "fresh" if observed >= cutoff else "stale"
                row["observed_at"] = _iso(observed)
            resets = row.get("resets_at")
            if isinstance(resets, datetime):
                row["resets_at"] = _iso(resets)
            rows.append(row)
        return rows

    def apply_to_provider_state(self, provider_state: dict[str, Any]) -> dict[str, Any]:
        state = deepcopy(provider_state)
        aggregates: dict[str, dict[str, Any]] = {}
        for snapshot in self.snapshots():
            if snapshot.get("status") != "fresh":
                continue
            target = None
            if snapshot.get("model_id"):
                target = f"quota:model:{snapshot['model_id']}"
            elif snapshot.get("quota_group"):
                target = f"quota:{snapshot['quota_group']}"
            if target is None:
                continue
            aggregate = aggregates.setdefault(target, {
                "quota_pressure": 0.0,
                "available_values": [],
            })
            used = snapshot.get("used_percent")
            if isinstance(used, (int, float)):
                aggregate["quota_pressure"] = max(aggregate["quota_pressure"], max(0.0, min(1.0, float(used) / 100.0)))
            if isinstance(snapshot.get("available"), bool):
                aggregate["available_values"].append(bool(snapshot["available"]))

        for key, aggregate in aggregates.items():
            existing = dict(state.get(key) or {})
            availability = list(aggregate["available_values"])
            if availability:
                # Any exhausted active window blocks the mapped resource. A
                # fresh all-available snapshot is authoritative enough to clear
                # an earlier transient quota-only failure marker.
                available = all(availability)
                existing.update({
                    "healthy": True,
                    "available": available,
                    "error_rate": 0.0,
                    "quota_pressure": float(aggregate["quota_pressure"]),
                })
            else:
                existing["quota_pressure"] = max(
                    float(existing.get("quota_pressure", 0.0) or 0.0),
                    float(aggregate["quota_pressure"]),
                )
            state[key] = existing
        return state
