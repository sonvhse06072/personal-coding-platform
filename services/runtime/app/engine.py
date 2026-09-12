"""Governance-aware facade for the checkpointed Runtime engine.

The implementation remains split into engine_core (lifecycle/state transitions),
engine_execution (coding/verification loop), and engine_delivery (bounded GitHub
branch/PR/CI delivery). This facade owns project-governance metadata that must be
validated and pinned atomically when a job row is first created.
"""

from __future__ import annotations

import uuid
from typing import Any

from .baseline import resolve_project_baseline
from .config import project_config
from .engine_delivery import RuntimeEngine as _RuntimeEngine
from .work_order import (
    canonical_task_from_work_order,
    validate_work_order_against_baseline,
    work_order_snapshot,
)


class RuntimeEngine(_RuntimeEngine):
    def create_job(self, payload: dict[str, Any]) -> str:
        """Create one job with its governing baseline/contract in the same write."""

        project = project_config(payload["project_id"])
        work_order = work_order_snapshot(payload.get("work_order"))
        requested_revision = (
            work_order.baseline_revision if work_order is not None else payload.get("baseline_revision")
        )
        baseline = resolve_project_baseline(payload["project_id"], requested_revision)

        if work_order is not None:
            validate_work_order_against_baseline(work_order, baseline, project)
            task = canonical_task_from_work_order(work_order)
        else:
            task = payload.get("task")
            if not isinstance(task, dict):
                raise ValueError("Legacy job creation requires task when work_order is absent")

        job_id = uuid.uuid4().hex
        checkpoint = {
            "hints": payload.get("repo_hints", {}),
            "provider_state": payload.get("provider_state", {}),
            "route_history": [],
            "approved_decisions": [],
        }
        if baseline is not None:
            checkpoint["project_baseline"] = baseline.model_dump(mode="json")
        if work_order is not None:
            checkpoint["work_order"] = work_order.model_dump(mode="json")

        self.storage.create({
            "id": job_id,
            "project_id": payload["project_id"],
            "status": "queued",
            "source_commit": payload.get("source_commit"),
            "task": task,
            "repo_analysis": None,
            "progress": self._new_progress(),
            "checkpoint": checkpoint,
            "dry_run": bool(payload.get("dry_run", False)),
        })
        return job_id


__all__ = ["RuntimeEngine"]
