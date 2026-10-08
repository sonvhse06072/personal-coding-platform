from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .activity import public_event
from .work_order_checkpoints import verification_checkpoint_summary


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




_SAFE_IDENTITY = re.compile(r"^[A-Za-z0-9._:/+-]+$")


def _safe_identity(value: Any, limit: int = 200) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > limit
        or _SAFE_IDENTITY.fullmatch(value) is None
    ):
        return None
    return value


def _failure_evidence(
    checkpoint: dict[str, Any],
    progress: dict[str, Any],
) -> dict[str, Any]:
    evidence: dict[str, Any] = {}

    summary = verification_checkpoint_summary(
        checkpoint.get("last_verification_summary")
    )
    if summary is not None:
        evidence["last_verification_summary"] = summary

    streak = checkpoint.get("deterministic_verification_failure_streak")
    streak = dict(streak) if isinstance(streak, dict) else {}
    if streak:
        safe_streak: dict[str, Any] = {}
        for key in ("count", "limit", "verification_attempt"):
            value = streak.get(key)
            if type(value) is int and 0 <= value <= 2**63 - 1:
                safe_streak[key] = value
        for key in ("signature", "diff_hash"):
            value = _safe_identity(streak.get(key))
            if value is not None:
                safe_streak[key] = value
        raw_phases = streak.get("failing_phases")
        phases = [
            value
            for raw in (raw_phases[:16] if isinstance(raw_phases, list) else [])
            if (value := _safe_identity(raw, 80)) is not None
        ]
        if phases:
            safe_streak["failing_phases"] = phases
        if safe_streak:
            evidence["deterministic_verification_failure_streak"] = safe_streak

    context = checkpoint.get("failure_context")
    context = dict(context) if isinstance(context, dict) else {}
    if context:
        safe_context: dict[str, Any] = {}
        version = context.get("version")
        if type(version) is int and 0 <= version <= 100:
            safe_context["version"] = version
        for key in ("kind", "source", "diff_hash", "decision_key"):
            value = _safe_identity(context.get(key), 500 if key == "decision_key" else 200)
            if value is not None:
                safe_context[key] = value
        if safe_context:
            evidence["failure_context"] = safe_context

    raw_fingerprints = progress.get("failure_fingerprints")
    fingerprints = [
        value
        for raw in (
            raw_fingerprints[-4:]
            if isinstance(raw_fingerprints, list)
            else []
        )
        if (value := _safe_identity(raw, 200)) is not None
    ]
    if fingerprints:
        evidence["recent_failure_fingerprints"] = fingerprints

    failure_kind = _safe_identity(progress.get("last_agent_failure_kind"), 120)
    if failure_kind is not None:
        evidence["last_agent_failure_kind"] = failure_kind

    return evidence


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
    pending_decision = dict(checkpoint.get("pending_decision") or {})
    decision = dict(pending_decision.get("decision") or {})
    failure_evidence = _failure_evidence(checkpoint, progress)

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
        "failure_evidence": failure_evidence or None,
        "pending_decision": (
            {
                "key": pending_decision.get("key"),
                "source": pending_decision.get("source"),
                "triggers": _bounded_list(
                    decision.get("triggers"),
                    limit=12,
                    item_limit=120,
                ),
                "reason": (
                    _text(decision.get("reason"), 600)
                    if decision.get("reason")
                    else None
                ),
            }
            if pending_decision
            else None
        ),
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


_KNOWN_PM_MERGE_BLOCKERS = frozenset({
    "canonical_bounded_direct_intake_required",
    "ci_commit_mismatch",
    "ci_not_successful",
    "conditional_review_has_no_pass_or_strong_evidence_skip",
    "current_delivery_ci_evidence_not_success",
    "current_github_ci_commit_mismatch",
    "delivery_not_finalized",
    "delivery_pr_branch_mismatch",
    "delivery_pr_head_mismatch",
    "delivery_pr_missing",
    "delivery_pr_number_mismatch",
    "delivery_state_not_mergeable",
    "deterministic_verification_not_passed",
    "dry_run_not_mergeable",
    "fresh_exact_head_ci_not_successful",
    "job_identity_mismatch",
    "job_not_completed",
    "job_result_not_accepted",
    "missing_job_branch",
    "missing_source_commit",
    "missing_verified_commit",
    "persisted_ci_commit_mismatch",
    "pm_evidence_has_unresolved_risks",
    "pull_request_base_mismatch",
    "pull_request_branch_mismatch",
    "pull_request_head_mismatch",
    "pull_request_identity_mismatch",
    "pull_request_not_open_unmerged",
    "required_checks_not_passed",
    "required_independent_review_not_passed",
    "required_review_independence_not_satisfied",
    "unexpected_scope",
    "work_order_identity_mismatch",
})


def _safe_merge_gate_reason(
    snapshot: dict[str, Any] | None,
    progress: dict[str, Any] | None,
) -> str | None:
    """Expose only a known merge-gate code on an exact blocked checkpoint.

    This is diagnostic-only: no permission, checkpoint, job, or merge mutation.
    Other reasons (which may contain arbitrary text) remain private.
    """
    if not isinstance(snapshot, dict) or not isinstance(progress, dict):
        return None
    if progress.get("state") != "blocked":
        return None
    published = progress.get("last_checkpoint")
    checkpoint = snapshot.get("blocked_checkpoint")
    if not isinstance(published, dict) or not isinstance(checkpoint, dict):
        return None
    if published.get("kind") != "blocked" or published.get("state") != "blocked":
        return None
    if checkpoint.get("kind") != "blocked" or checkpoint.get("state") != "blocked":
        return None
    if any(
        published.get(key) != checkpoint.get(key)
        for key in ("id", "checkpoint_key", "work_order_id", "job_id")
    ):
        return None
    evidence = checkpoint.get("evidence")
    reason = evidence.get("reason") if isinstance(evidence, dict) else None
    if not isinstance(reason, str) or len(reason) > 128:
        return None
    if reason in {
        "pm_merge_replay_rejected",
        "uncertain_merge_attempt",
        "pull_request_closed_without_merge",
    }:
        return reason
    if reason.startswith("pm_merge_ineligible:"):
        suffix = reason.partition(":")[2]
        if suffix in _KNOWN_PM_MERGE_BLOCKERS:
            return reason
    return None


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

        if plan_id:
            plan = self.orchestrator.store.orchestration(plan_id)
            if plan is None:
                raise RuntimeError("Unknown diagnostic plan")
            if str(plan.get("project_id") or "") != project_id:
                raise RuntimeError("Diagnostic plan project identity mismatch")

        if "job" in collectors:
            if job is None:
                raise RuntimeError("job collector requires job_id")
            sections["job"] = _job_summary(job)

        if "attention" in collectors:
            if job is None:
                raise RuntimeError("attention collector requires job_id")
            checkpoint = dict(job.get("checkpoint") or {})
            intake = dict(checkpoint.get("canonical_intake") or {})
            canonical_direct = (
                intake.get("mode") == "direct"
                and intake.get("bounded_direct") is True
            )
            if (
                canonical_direct
                and str(job.get("status") or "") in {"blocked", "interrupted"}
            ):
                try:
                    sections["attention"] = (
                        self.controls.standalone_remote_actions(
                            str(job["id"])
                        )
                    )
                except RuntimeError:
                    sections["attention"] = {
                        "job_id": job.get("id"),
                        "status": job.get("status"),
                        "generation": None,
                        "actions": [],
                        "note": (
                            "No standalone routine recovery action is currently available."
                        ),
                    }
            elif not canonical_direct:
                actions = self.controls.remote_pending_actions(
                    str(job["id"])
                )
                sections["attention"] = {
                    **actions,
                    "status": job.get("status"),
                }
            else:
                sections["attention"] = {
                    "job_id": job.get("id"),
                    "status": job.get("status"),
                    "generation": None,
                    "actions": [],
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
            progress = _plan_summary(self.orchestrator.progress(plan_id))
            if isinstance(progress, dict) and progress.get("state") == "blocked":
                # A separate bounded, read-only checkpoint snapshot is required
                # because generic plan_progress deliberately omits raw reasons.
                # Exact checkpoint identity rejects races between the two reads.
                snapshot = self.orchestrator.store.progress_snapshot(plan_id)
                merge_gate_reason = _safe_merge_gate_reason(snapshot, progress)
                if merge_gate_reason is not None:
                    progress["merge_gate_reason"] = merge_gate_reason
            sections["plan_progress"] = progress

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
