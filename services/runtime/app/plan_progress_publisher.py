"""Independent transport loop; a slow GitHub request never holds an engineering lock."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .plan_progress_handoff import sha256


logger = logging.getLogger(__name__)


class PlanProgressPublisher:
    def __init__(self, store: Any, executor: Any) -> None:
        self.store, self.executor = store, executor
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def publish_one(self) -> bool:
        claim = self.store.claim()
        if claim is None:
            return False
        try:
            result = await self.executor.upsert_plan_progress(
                project_id=claim["project_id"], issue_number=claim["issue_number"],
                handoff_key=claim["handoff_key"], body=claim["desired_body"],
                known_comment_id=claim["comment_id"],
            )
            rendered = f"<!-- PCP:PLAN-PROGRESS:{claim['handoff_key']} -->\n\n{claim['desired_body']}"
            if (result.get("issue_number") != claim["issue_number"]
                    or result.get("observed_body_sha256") != sha256(rendered)):
                raise ValueError("Progress publication postcondition mismatch")
            self.store.ack(claim, result["comment_id"])
        except Exception as exc:
            self.store.release(claim, exc)
        # Cancellation leaves an uncertain operation leased for restart recovery.
        return True

    async def _loop(self) -> None:
        while True:
            try:
                worked = await self.publish_one()
            except Exception as exc:
                logger.warning("Progress publisher unavailable (%s)", type(exc).__name__)
                worked = False
            await asyncio.sleep(1 if worked else 5)
