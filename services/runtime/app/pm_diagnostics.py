from __future__ import annotations

import hashlib
import json
from typing import Any

from .activity import public_event


_BODY_MAX_BYTES = 10 * 1024


def _text(value: Any, limit: int = 300) -> str:
    if value is None:
        return "-"
    text = " ".join(str(value).split()).replace("\x00", "")
    return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore") or "-"


def _bounded_list(values: Any, *, limit: int = 12, item_limit: int = 300) -> list[str]:
    if not isinstance(values, list):
        return []
    return [_text(value, item_limit) for value in values[:limit]]


def _job_summary(job: dict[str, Any]) -> dict[str, Any]:
    result = dict(job.get("result") or {})
    delivery = dict(result.get("delivery") or {})
    pr = dict(delivery.get("pull_request") or {})
    ci = dict(delivery.get("ci") or {})
    reassess = dict(result.get("reassess") or {})
    route = dict(job.get("route") or {})
    strategy = dict(route.get("strategy") or {})
    checkpoint = dict(job.get("checkpoint") or {})
    baseline = dict(checkpoint.get("project_baseline") or {})
    progress = dict(job.get("progress") or {})

    return {
        "id": job.get("id"),
        "project_id": job.get("project_id"),
        "status": job.get("status"),
        "source_commit": job.get("source_commit"),
        "baseline_revision": baseline.get("revision"),
        "branch": job.get("branch"),
        "profile": strategy.get("profile"),
        "reason": result.get("reason"),
        "reassess_action": reassess.get("action"),
        "reassess_reason": _text(reassess.get("reason"), 500) if reassess else None,
        "reassess_signals": _bounded_list(
            reassess.get("signals"),
            limit=12,
            item_limit=120,
        ),
        "verified_commit": result.get("commit"),
        "delivery_state": delivery.get("state"),
        "pr_number": pr.get("number"),
        "pr_head": pr.get("head"),
        "pr_head_ref": pr.get("head_ref"),
        "ci_state": ci.get("state"),
        "ci_commit": ci.get("commit"),
        "progress": {
            key: progress.get(key)
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
            )
            if progress.get(key) is not None
        },
    }


def _collaboration_summary(threads: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for view in threads[:12]:
        data = (
            view.model_dump(mode="json")
            if hasattr(view, "model_dump")
            else dict(view)
        )
        response = dict(data.get("response") or {})
        result.append(
            {
                "id": data.get("id"),
                "role": data.get("participant_role") or data.get("role"),
                "status": data.get("status"),
                "rounds": data.get("rounds"),
                "max_rounds": data.get("max_rounds"),
                "recommendation": (
                    _text(response.get("recommendation"), 800)
                    if response
                    else None
                ),
                "risks": _bounded_list(
                    response.get("risks"),
                    limit=8,
                    item_limit=300,
                ),
                "suggested_tests": _bounded_list(
                    response.get("suggested_tests"),
                    limit=8,
                    item_limit=300,
                ),
                "unresolved": response.get("unresolved") if response else None,
            }
        )
    return result


def _plan_summary(progress: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(progress, dict):
        return None
    supervision = dict(progress.get("supervision") or {})
    checkpoint = dict(progress.get("last_checkpoint") or {})
    supervised_checkpoint = dict(supervision.get("checkpoint") or {})
    return {
        "plan_id": progress.get("plan_id") or progress.get("id"),
        "state": progress.get("state") or progress.get("status"),
        "next": list(progress.get("next") or [])[:30],
        "supervision": {
            "mode": supervision.get("mode"),
            "state": supervision.get("state"),
            "generation": supervision.get("generation"),
            "continuation_key": supervision.get("continuation_key"),
            "ready_work_order_ids": list(
                supervision.get("ready_work_order_ids") or []
            )[:30],
            "checkpoint": {
                key: supervised_checkpoint.get(key)
                for key in ("id", "checkpoint_key")
            },
        },
        "last_checkpoint": {
            key: checkpoint.get(key)
            for key in (
                "id",
                "checkpoint_key",
                "work_order_id",
                "kind",
                "state",
                "job_id",
            )
        },
    }


def _render(title: str, sections: dict[str, Any]) -> str:
    lines = [f"## {title}", ""]
    for name, payload in sections.items():
        lines.extend([f"### {name}", ""])
        rendered = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
        lines.extend(rendered.splitlines())
        lines.append("")
    body = "\n".join(lines).rstrip()
    raw = body.encode("utf-8")
    if len(raw) > _BODY_MAX_BYTES:
        body = raw[: _BODY_MAX_BYTES - 32].decode(
            "utf-8",
            errors="ignore",
        ) + "\n[diagnostic truncated]"
    return body


class PMDiagnosticsService:
    def __init__(self, storage: Any, engine: Any, orchestrator: Any) -> None:
        self.storage = storage
        self.engine = engine
        self.orchestrator = orchestrator
        self.controls = orchestrator.controls

    async def collect_and_publish(
        self,
        *,
        project_id: str,
        issue_number: int,
        control_comment_id: int,
        job_id: str | None,
        plan_id: str | None,
        collectors: list[str],
    ) -> dict[str, Any]:
        sections: dict[str, Any] = {}
        job: dict[str, Any] | None = None

        if job_id:
            row = self.storage.get(job_id)
            if row is None:
                raise RuntimeError("Unknown diagnostic job")
            job = dict(row)
            if str(job.get("project_id") or "") != project_id:
                raise RuntimeError("Diagnostic job project identity mismatch")

        if "job" in collectors:
            if job is None:
                raise RuntimeError("job collector requires job_id")
            sections["job"] = _job_summary(job)

        if "attention" in collectors:
            if job is None:
                raise RuntimeError("attention collector requires job_id")
            if str(job.get("status") or "") in {"blocked", "interrupted"}:
                try:
                    sections["attention"] = self.controls.standalone_remote_actions(
                        str(job["id"])
                    )
                except RuntimeError:
                    sections["attention"] = {
                        "job_id": job.get("id"),
                        "status": job.get("status"),
                        "available_actions": [],
                        "note": (
                            "No standalone routine recovery action is currently available."
                        ),
                    }
            else:
                sections["attention"] = {
                    "job_id": job.get("id"),
                    "status": job.get("status"),
                    "available_actions": [],
                }

        if "collaboration" in collectors:
            if job is None:
                raise RuntimeError("collaboration collector requires job_id")
            sections["collaboration"] = _collaboration_summary(
                self.engine.collaboration.list(str(job["id"]))
            )

        if "plan_progress" in collectors:
            if not plan_id:
                raise RuntimeError("plan_progress collector requires plan_id")
            sections["plan_progress"] = _plan_summary(
                self.orchestrator.progress(plan_id)
            )

        if "recent_activity" in collectors:
            if job is None:
                raise RuntimeError("recent_activity collector requires job_id")
            events = self.storage.recent_events(
                [str(job["id"])],
                per_job_limit=30,
            )
            activity: list[dict[str, Any]] = []
            safe_data_keys = {
                "status",
                "role",
                "model",
                "adapter",
                "provider",
                "tool",
                "kind",
                "exit_code",
                "from_status",
                "to_status",
                "profile",
                "analysis_depth",
            }
            for event in events:
                item = public_event(dict(event))
                if item is None:
                    continue
                data = dict(item.get("data") or {})
                activity.append(
                    {
                        "seq": item.get("seq"),
                        "timestamp": item.get("timestamp"),
                        "phase": item.get("phase"),
                        "level": item.get("level"),
                        "event": item.get("event"),
                        "data": {
                            key: data.get(key)
                            for key in safe_data_keys
                            if data.get(key) is not None
                        },
                    }
                )
            sections["recent_activity"] = activity

        if "github_delivery" in collectors:
            if job is None:
                raise RuntimeError("github_delivery collector requires job_id")
            result = dict(job.get("result") or {})
            delivery = dict(result.get("delivery") or {})
            pr = dict(delivery.get("pull_request") or {})
            commit = str(result.get("commit") or "").strip()
            live: dict[str, Any] = {
                "persisted": {
                    "state": delivery.get("state"),
                    "pull_request": {
                        key: pr.get(key)
                        for key in ("number", "head", "head_ref", "base_ref")
                    },
                    "ci": {
                        key: (delivery.get("ci") or {}).get(key)
                        for key in ("state", "commit")
                    },
                }
            }
            if pr.get("number"):
                live["pull_request"] = (
                    await self.engine.ddev.github_pull_request(
                        project_id=project_id,
                        pr_number=int(pr["number"]),
                    )
                )
            if commit:
                live["ci"] = await self.engine.ddev.github_ci(
                    project_id=project_id,
                    commit=commit,
                )
            sections["github_delivery"] = live

        if "worktree" in collectors:
            sections["worktree"] = (
                await self.engine.ddev.project_worktree_state(
                    project_id=project_id,
                )
            )

        if "runtime_health" in collectors:
            sections["runtime_health"] = {
                "router": "ok" if await self.engine.router.health() else "down",
                "executor": "ok" if await self.engine.ddev.health() else "down",
                "active_engineering_jobs": (
                    self.storage.count_active_engineering_jobs()
                ),
            }

        identity = f"control:{control_comment_id}"
        handoff_key = hashlib.sha256(
            (
                f"diagnostic:{project_id}:{issue_number}:"
                f"{identity}"
            ).encode()
        ).hexdigest()
        body = _render("PCP remote diagnostic", sections)
        published = await self.engine.ddev.upsert_managed_comment(
            project_id=project_id,
            issue_number=issue_number,
            channel="diagnostic",
            identity=identity,
            handoff_key=handoff_key,
            body=body,
        )
        return {
            "status": "published",
            "collectors": list(sections),
            "comment_id": published.get("comment_id"),
            "comment_url": published.get("comment_url"),
            "state": published.get("state"),
        }
