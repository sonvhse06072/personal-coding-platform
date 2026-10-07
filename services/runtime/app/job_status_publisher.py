from __future__ import annotations

import hashlib
import json
from typing import Any


BODY_MAX_BYTES = 10 * 1024

DDL = """
CREATE TABLE IF NOT EXISTS cp_job_status_handoffs (
  job_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  issue_number BIGINT NOT NULL CHECK (issue_number > 0),
  desired_sha256 TEXT NOT NULL,
  desired_body TEXT NOT NULL CHECK (octet_length(desired_body) <= 10240),
  comment_id BIGINT,
  published_sha256 TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','delivering','sent')),
  attempts BIGINT NOT NULL DEFAULT 0,
  available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lease_until TIMESTAMPTZ,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cp_job_status_delivery_idx
  ON cp_job_status_handoffs(status, available_at);
"""


def _text(value: Any, limit: int = 300) -> str:
    if value is None:
        return "-"
    text = " ".join(str(value).split()).replace("\x00", "")
    return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore") or "-"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _render_job_status(
    job: dict[str, Any],
    *,
    attention: dict[str, Any] | None,
) -> str:
    result = dict(job.get("result") or {})
    delivery = dict(result.get("delivery") or {})
    pr = dict(delivery.get("pull_request") or {})
    ci = dict(delivery.get("ci") or {})
    reassess = dict(result.get("reassess") or {})
    checkpoint = dict(job.get("checkpoint") or {})
    baseline = dict(checkpoint.get("project_baseline") or {})
    progress = dict(job.get("progress") or {})
    route = dict(job.get("route") or {})
    strategy = dict(route.get("strategy") or {})

    lines = [
        "## PCP standalone job status",
        "",
        f"Job: {_text(job.get('id'), 100)}",
        f"Project: {_text(job.get('project_id'), 100)}",
        f"Status: {_text(job.get('status'), 60)}",
        f"Source: {_text(job.get('source_commit'), 80)}",
        f"Baseline: {_text(baseline.get('revision'), 100)}",
        f"Branch: {_text(job.get('branch'), 220)}",
        f"Profile: {_text(strategy.get('profile'), 60)}",
        f"Reason: {_text(result.get('reason'), 160)}",
    ]

    if reassess:
        lines += [
            f"Reassessment action: {_text(reassess.get('action'), 80)}",
            f"Reassessment reason: {_text(reassess.get('reason'), 500)}",
            "Reassessment signals: "
            + (
                ", ".join(
                    _text(value, 120)
                    for value in list(reassess.get("signals") or [])[:12]
                )
                or "-"
            ),
        ]

    lines += [
        "",
        "Delivery:",
        f"- Verified commit: {_text(result.get('commit'), 80)}",
        f"- State: {_text(delivery.get('state'), 80)}",
        f"- PR: {_text(pr.get('number'), 40)}",
        f"- PR head: {_text(pr.get('head'), 80)}",
        f"- CI: {_text(ci.get('state'), 80)} / {_text(ci.get('commit'), 80)}",
        "",
        "Progress:",
    ]
    for key in (
        "model_calls",
        "tool_calls",
        "test_runs",
        "repair_iterations",
        "iteration",
        "changed_files",
        "unexpected_scope",
        "required_checks_passed",
        "elapsed_minutes",
    ):
        if progress.get(key) is not None:
            lines.append(f"- {key}: {_text(progress.get(key), 80)}")

    if attention:
        lines += [
            "",
            "Remote recovery:",
            f"- Generation: {_text(attention.get('generation'), 100)}",
            f"- Phase: {_text(attention.get('phase'), 80)}",
        ]
        actions = list(attention.get("actions") or [])[:12]
        if actions:
            for item in actions:
                lines.append(
                    f"- {_text(item.get('action_type'), 100)}: "
                    f"{_text(item.get('label'), 120)}"
                )
        else:
            lines.append("- none")

    body = "\n".join(lines)
    raw = body.encode("utf-8")
    if len(raw) > BODY_MAX_BYTES:
        body = raw[: BODY_MAX_BYTES - 32].decode(
            "utf-8",
            errors="ignore",
        ) + "\n[status truncated]"
    return body


class JobStatusStore:
    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def ensure(self) -> None:
        with self.storage.connect() as conn:
            conn.execute(DDL)
            conn.commit()

    def stage(
        self,
        job: dict[str, Any],
        *,
        body: str,
        issue_number: int,
    ) -> bool:
        self.ensure()
        digest = _sha(body)
        with self.storage.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO cp_job_status_handoffs AS h
                  (job_id,project_id,issue_number,desired_sha256,desired_body)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (job_id) DO UPDATE SET
                  project_id=EXCLUDED.project_id,
                  issue_number=EXCLUDED.issue_number,
                  desired_sha256=EXCLUDED.desired_sha256,
                  desired_body=EXCLUDED.desired_body,
                  status=CASE
                    WHEN h.status='delivering' THEN 'delivering'
                    ELSE 'pending'
                  END,
                  available_at=now(),
                  updated_at=now()
                WHERE
                  (h.project_id,h.issue_number,h.desired_sha256)
                  IS DISTINCT FROM
                  (EXCLUDED.project_id,EXCLUDED.issue_number,EXCLUDED.desired_sha256)
                RETURNING job_id
                """,
                (
                    str(job["id"]),
                    str(job["project_id"]),
                    issue_number,
                    digest,
                    body,
                ),
            ).fetchone()
            conn.commit()
        return row is not None

    def claim(self) -> dict[str, Any] | None:
        self.ensure()
        with self.storage.connect() as conn:
            conn.execute(
                """
                UPDATE cp_job_status_handoffs
                SET status='pending',lease_until=NULL
                WHERE status='delivering' AND lease_until <= now()
                """
            )
            row = conn.execute(
                """
                WITH candidate AS (
                  SELECT job_id FROM cp_job_status_handoffs
                  WHERE status='pending' AND available_at <= now()
                  ORDER BY available_at,job_id
                  FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE cp_job_status_handoffs h
                SET status='delivering',
                    lease_until=now()+interval '180 seconds',
                    attempts=attempts+1,
                    updated_at=now()
                FROM candidate c
                WHERE h.job_id=c.job_id
                RETURNING h.*
                """
            ).fetchone()
            conn.commit()
            return dict(row) if row else None

    def ack(self, claim: dict[str, Any], comment_id: int) -> bool:
        if type(comment_id) is not int or comment_id <= 0:
            raise ValueError("Invalid job-status comment identity")
        with self.storage.connect() as conn:
            result = conn.execute(
                """
                UPDATE cp_job_status_handoffs
                SET comment_id=%s,
                    published_sha256=%s,
                    status=CASE
                      WHEN desired_sha256=%s AND desired_body=%s
                      THEN 'sent' ELSE 'pending'
                    END,
                    lease_until=NULL,
                    last_error=NULL,
                    available_at=now(),
                    updated_at=now()
                WHERE job_id=%s
                  AND status='delivering'
                  AND attempts=%s
                """,
                (
                    comment_id,
                    claim["desired_sha256"],
                    claim["desired_sha256"],
                    claim["desired_body"],
                    claim["job_id"],
                    claim["attempts"],
                ),
            )
            conn.commit()
            return bool(result.rowcount)

    def release(self, claim: dict[str, Any], error: Exception) -> bool:
        code = type(error).__name__[:100]
        delay = min(300, 5 * 2 ** min(int(claim["attempts"]), 6))
        with self.storage.connect() as conn:
            result = conn.execute(
                """
                UPDATE cp_job_status_handoffs
                SET status='pending',
                    lease_until=NULL,
                    last_error=%s,
                    available_at=now()+(%s * interval '1 second'),
                    updated_at=now()
                WHERE job_id=%s
                  AND status='delivering'
                  AND attempts=%s
                """,
                (code, delay, claim["job_id"], claim["attempts"]),
            )
            conn.commit()
            return bool(result.rowcount)


class JobStatusPublisher:
    def __init__(
        self,
        storage: Any,
        executor: Any,
        controls: Any,
        *,
        store: JobStatusStore | None = None,
        notification_store: Any | None = None,
    ) -> None:
        self.storage = storage
        self.executor = executor
        self.controls = controls
        self.store = store or JobStatusStore(storage)
        self.notification_store = notification_store
        self._task = None

    def _binding(self, job: dict[str, Any]) -> tuple[int, str] | None:
        checkpoint = dict(job.get("checkpoint") or {})
        binding = dict(checkpoint.get("github_pm_binding") or {})
        if binding.get("transport") != "github_pm_control":
            return None
        issue = binding.get("issue_number")
        repository = str(binding.get("repository") or "")
        if type(issue) is not int or issue <= 0 or not repository:
            return None
        return issue, repository

    @staticmethod
    def _fallback_attention_generation(job: dict[str, Any]) -> str:
        result = dict(job.get("result") or {})
        snapshot = {
            "job_id": job.get("id"),
            "project_id": job.get("project_id"),
            "status": job.get("status"),
            "updated_at": str(job.get("updated_at") or ""),
            "reason": result.get("reason"),
        }
        return _sha(
            json.dumps(
                snapshot,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
        )

    def _standalone_notification_advisory(
        self,
        job: dict[str, Any],
    ) -> dict[str, Any]:
        advisory = dict(self.controls.blocked_advisory({}, job))
        advisory.pop("action_specs", None)
        advisory["title"] = "STANDALONE JOB BỊ CHẶN"
        advisory["preserved"] = [
            "Giữ nguyên cùng durable job và workspace hiện tại.",
            "Giữ nguyên diff, tiến độ và các bộ đếm sử dụng bền vững.",
            "Không tạo replacement job chỉ để vượt qua blocker.",
        ]
        advisory["impact"] = (
            "Standalone job không chạy thêm tác vụ tự động cho đến khi "
            "một recovery/control hợp lệ được revalidate và thực thi."
        )
        return advisory

    def _stage_standalone_notification(
        self,
        job: dict[str, Any],
        *,
        issue_number: int,
        repository: str,
        attention: dict[str, Any] | None,
    ) -> None:
        if self.notification_store is None:
            return
        job_id = str(job.get("id") or "")
        if not job_id:
            return
        try:
            supersede = getattr(
                self.notification_store,
                "supersede_standalone_notifications",
                None,
            )
            if str(job.get("status") or "") != "blocked":
                if callable(supersede):
                    supersede(job_id)
                return

            advisory = self._standalone_notification_advisory(job)
            generation = str((attention or {}).get("generation") or "")
            if not generation:
                generation = self._fallback_attention_generation(job)
            if callable(supersede):
                supersede(job_id, except_generation=generation)

            remote_actions = [
                {
                    "action_type": str(item.get("action_type") or "")[:100],
                    "label": str(item.get("label") or "")[:120],
                }
                for item in list((attention or {}).get("actions") or [])[:12]
                if isinstance(item, dict)
                and str(item.get("action_type") or "")
            ]
            dedupe_key = _sha(
                f"{job.get('project_id')}:{job_id}:"
                f"standalone_job_blocked:{generation}"
            )
            self.notification_store.emit_notification(
                dedupe_key=dedupe_key,
                event_type="standalone_job_blocked",
                severity="error",
                project_id=str(job.get("project_id") or ""),
                ticket_id=f"GH-{issue_number}",
                plan_id=None,
                work_order_id=None,
                summary=str(
                    advisory.get("summary")
                    or "Standalone job đang bị chặn và cần owner chú ý."
                ),
                github_url=(
                    f"https://github.com/{repository}/issues/{issue_number}"
                ),
                payload={
                    "job_id": job_id,
                    "standalone_job_id": job_id,
                    "advisory": advisory,
                    # Standalone PM controls are GitHub-bound today. Keep their
                    # metadata visible without fabricating Telegram callbacks.
                    "actions": [],
                    "remote_actions": remote_actions,
                },
                attention_state="blocked",
                attention_generation=generation,
            )
        except Exception:
            # Telegram/outbox materialization is observability only. It must not
            # block GitHub status publication or mutate engineering state.
            return

    def stage_all(self) -> int:
        staged = 0
        for raw in self.storage.list(limit=200):
            job = dict(raw)
            binding = self._binding(job)
            if binding is None:
                continue
            issue_number, repository = binding
            attention = None
            if str(job.get("status") or "") in {"blocked", "interrupted"}:
                try:
                    attention = self.controls.standalone_remote_actions(
                        str(job["id"])
                    )
                except RuntimeError:
                    attention = {
                        "generation": None,
                        "phase": "blocked",
                        "actions": [],
                    }
            self._stage_standalone_notification(
                job,
                issue_number=issue_number,
                repository=repository,
                attention=attention,
            )
            body = _render_job_status(job, attention=attention)
            if self.store.stage(
                job,
                body=body,
                issue_number=issue_number,
            ):
                staged += 1
        return staged

    async def publish_one(self) -> bool:
        self.stage_all()
        claim = self.store.claim()
        if claim is None:
            return False
        identity = f"job:{claim['job_id']}"
        handoff_key = hashlib.sha256(
            (
                f"job_status:{claim['project_id']}:"
                f"{claim['issue_number']}:{identity}"
            ).encode()
        ).hexdigest()
        try:
            result = await self.executor.upsert_managed_comment(
                project_id=claim["project_id"],
                issue_number=int(claim["issue_number"]),
                channel="job_status",
                identity=identity,
                handoff_key=handoff_key,
                body=claim["desired_body"],
                known_comment_id=claim.get("comment_id"),
            )
            self.store.ack(claim, int(result["comment_id"]))
        except Exception as exc:
            self.store.release(claim, exc)
        return True

    async def start(self) -> None:
        import asyncio
        # Publication is observability/control-plane transport only. A transient
        # handoff-store failure must not make Runtime startup fail.
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        import asyncio
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        import asyncio
        while True:
            try:
                worked = await self.publish_one()
            except Exception:
                worked = False
            await asyncio.sleep(1 if worked else 5)
