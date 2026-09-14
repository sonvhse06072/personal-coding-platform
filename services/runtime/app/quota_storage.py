from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .storage import Storage


QUOTA_DDL = """
CREATE TABLE IF NOT EXISTS cp_provider_quota_state (
  provider TEXT NOT NULL,
  quota_key TEXT NOT NULL,
  model_id TEXT,
  quota_group TEXT,
  used_percent DOUBLE PRECISION,
  remaining_percent DOUBLE PRECISION,
  available BOOLEAN,
  resets_at TIMESTAMPTZ,
  window_minutes INTEGER,
  observed_at TIMESTAMPTZ NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'fresh',
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (provider, quota_key)
);
CREATE INDEX IF NOT EXISTS cp_provider_quota_observed_idx
  ON cp_provider_quota_state(provider, observed_at DESC);
"""


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


class QuotaStorage(Storage):
    """Runtime storage plus platform-wide provider quota snapshots."""

    def ensure_quota_table(self) -> None:
        with self.connect() as conn:
            conn.execute(QUOTA_DDL)
            conn.commit()

    def init(self) -> None:
        super().init()
        self.ensure_quota_table()

    def replace_provider_quota_snapshots(
        self,
        provider: str,
        snapshots: list[dict[str, Any]],
    ) -> None:
        if not snapshots:
            raise ValueError("Refusing to replace provider quota state with an empty snapshot")
        with self.connect() as conn:
            conn.execute("DELETE FROM cp_provider_quota_state WHERE provider=%s", (provider,))
            for row in snapshots:
                observed_at = _timestamp(row.get("observed_at"))
                if observed_at is None:
                    raise ValueError("quota snapshot requires observed_at")
                conn.execute(
                    """INSERT INTO cp_provider_quota_state
                    (provider, quota_key, model_id, quota_group, used_percent,
                     remaining_percent, available, resets_at, window_minutes,
                     observed_at, source, status, details)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                    (
                        provider,
                        str(row["quota_key"]),
                        row.get("model_id"),
                        row.get("quota_group"),
                        row.get("used_percent"),
                        row.get("remaining_percent"),
                        row.get("available"),
                        _timestamp(row.get("resets_at")),
                        row.get("window_minutes"),
                        observed_at,
                        str(row.get("source") or "unknown"),
                        str(row.get("status") or "fresh"),
                        json.dumps(row.get("details") or {}),
                    ),
                )
            conn.commit()

    def list_quota_snapshots(self, provider: str | None = None) -> list[dict[str, Any]]:
        # Quota telemetry must never make job routing unavailable merely because
        # the optional snapshot table/database cannot be read. A failed read is
        # represented as no usable telemetry and normal provider-health routing
        # remains in force.
        try:
            with self.connect() as conn:
                if provider:
                    rows = conn.execute(
                        """SELECT provider, quota_key, model_id, quota_group, used_percent,
                                  remaining_percent, available, resets_at, window_minutes,
                                  observed_at, source, status, details
                           FROM cp_provider_quota_state
                           WHERE provider=%s
                           ORDER BY provider, quota_key""",
                        (provider,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT provider, quota_key, model_id, quota_group, used_percent,
                                  remaining_percent, available, resets_at, window_minutes,
                                  observed_at, source, status, details
                           FROM cp_provider_quota_state
                           ORDER BY provider, quota_key"""
                    ).fetchall()
                return list(rows)
        except Exception:
            return []
