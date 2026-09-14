#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SAFE_QUOTA_KEYS = {"remaining_fraction", "reset_time", "reset_in_seconds"}


def bounded_text(value: Any, limit: int = 200) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:limit]


def sanitize(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    quota = payload.get("quota")
    if not isinstance(quota, dict) or not quota:
        return None
    safe_quota: dict[str, Any] = {}
    for quota_id, raw in quota.items():
        if not isinstance(raw, dict):
            continue
        entry: dict[str, Any] = {}
        remaining = raw.get("remaining_fraction")
        if isinstance(remaining, (int, float)) and not isinstance(remaining, bool):
            entry["remaining_fraction"] = max(0.0, min(1.0, float(remaining)))
        reset_time = bounded_text(raw.get("reset_time"), 80)
        if reset_time:
            entry["reset_time"] = reset_time
        reset_seconds = raw.get("reset_in_seconds")
        if isinstance(reset_seconds, (int, float)) and not isinstance(reset_seconds, bool):
            entry["reset_in_seconds"] = max(0, int(reset_seconds))
        if entry:
            safe_quota[str(quota_id)[:160]] = entry
    if not safe_quota:
        return None
    model = payload.get("model")
    safe_model: dict[str, str] | None = None
    if isinstance(model, dict):
        candidate = {
            key: text
            for key in ("id", "display_name")
            if (text := bounded_text(model.get(key), 160))
        }
        safe_model = candidate or None
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "quota": safe_quota,
        "model": safe_model,
        "plan_tier": bounded_text(payload.get("plan_tier"), 80),
        "version": bounded_text(payload.get("version"), 80),
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    safe = sanitize(payload)
    if safe is None:
        return 0
    target = Path(
        os.getenv(
            "ANTIGRAVITY_QUOTA_SNAPSHOT",
            str(Path.home() / ".coding-platform" / "antigravity-quota.json"),
        )
    ).expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(safe, separators=(",", ":")) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(target)
    except OSError:
        # Observability is fail-open and must never disturb Antigravity itself.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
