from __future__ import annotations

import hashlib
import json
import os
import secrets
from copy import deepcopy
from datetime import timedelta
from typing import Any

from .legacy_delivery_recovery import (
    LEGACY_RECOVERY_BLOCK_REASON,
    recover_legacy_accepted_result,
)
from .orchestrator_resume import prepare_orchestrated_job_resume, reopen_orchestrated_job
from .state import checkpoint_from_row
from .storage import now


CONTROL_DDL = """
CREATE TABLE IF NOT EXISTS cp_control_actions (
  action_id TEXT PRIMARY KEY,
  dedupe_key TEXT NOT NULL UNIQUE,
  action_type TEXT NOT NULL,
  plan_id TEXT NOT NULL,
  work_order_id TEXT NOT NULL,
  job_id TEXT,
  state_fingerprint TEXT NOT NULL,
  generation_fingerprint TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'pending',
  result JSONB,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS cp_control_actions_lookup_idx
  ON cp_control_actions(status, plan_id, work_order_id, created_at DESC);
ALTER TABLE cp_control_actions
  ADD COLUMN IF NOT EXISTS generation_fingerprint TEXT;
UPDATE cp_control_actions
  SET generation_fingerprint=state_fingerprint
  WHERE generation_fingerprint IS NULL;
ALTER TABLE cp_control_actions
  ALTER COLUMN generation_fingerprint SET NOT NULL;
"""

_ACTIVE_JOB_STATUSES = {
    "queued", "routing", "planning", "executing", "verifying", "evaluating", "delivering"
}

_REMOTE_ROUTINE_ACTION_TYPES = frozenset({
    "pm_scope_reassess",
    "resume_same",
    "retry_delivery",
    "recheck_ci",
    "recheck_orchestration",
})

_REMOTE_STANDALONE_ACTION_TYPES = frozenset({
    "pm_scope_reassess",
    "resume_same",
    "retry_delivery",
    "recheck_ci",
})

# Explicit owner extensions may exceed a Router-selected/WorkOrder ceiling, but
# never these platform hard maxima. Consumed counters are never reset.
_BUDGET_EXTENSION_SPECS: dict[str, dict[str, Any]] = {
    "max_model_calls": {"counter": "model_calls", "increment": 4, "hard_max": 100, "label": "Model calls"},
    "max_tool_calls": {"counter": "tool_calls", "increment": 20, "hard_max": 500, "label": "Tool calls"},
    "max_test_runs": {"counter": "test_runs", "increment": 2, "hard_max": 100, "label": "Test runs"},
    "max_wall_time_minutes": {"counter": "elapsed_minutes", "increment": 20, "hard_max": 240, "label": "Wall time (min)"},
    "max_repair_iterations": {"counter": "repair_iterations", "increment": 1, "hard_max": 20, "label": "Repair iterations"},
    "max_iterations": {"counter": "iteration", "increment": 2, "hard_max": 30, "label": "Iterations"},
}

_BUDGET_FAILURE_MAP = {
    "model-call budget exhausted": "max_model_calls",
    "tool-call budget exhausted": "max_tool_calls",
    "tool-call budget would be exceeded by preflight": "max_tool_calls",
    "test-run budget exhausted": "max_test_runs",
    "repair budget exhausted": "max_repair_iterations",
    "wall-time budget exhausted": "max_wall_time_minutes",
    "iteration budget exhausted": "max_iterations",
}

_PROVIDER_BLOCK_REASONS = {
    "planner_provider_failure_without_fallback",
    "provider_failure_without_fallback",
    "evaluator_provider_failure_without_fallback",
}

_ADAPTIVE_WORK_SHAPE_DIMENSIONS = {
    "max_model_calls",
    "max_tool_calls",
    "max_test_runs",
    "max_repair_iterations",
    "max_iterations",
    "max_wall_time_minutes",
}




class ControlActionService:
    """Durable, one-time owner controls for Telegram and other trusted transports.

    Telegram/n8n may carry only the opaque action id. Runtime revalidates the
    exact plan/WorkOrder/job state immediately before every mutation.
    """

    def __init__(self, storage: Any, engine: Any, store: Any, orchestrator: Any | None = None) -> None:
        self.storage = storage
        self.engine = engine
        self.store = store
        self.orchestrator = orchestrator

    @staticmethod
    def _adaptive_work_shape_nonblocking(job: dict[str, Any]) -> bool:
        route = dict(job.get("route") or {})
        strategy = dict(route.get("strategy") or {})
        mode = str(strategy.get("budget_mode") or "")
        if mode:
            return mode == "adaptive"

        checkpoint = dict(job.get("checkpoint") or {})
        work_order = dict(checkpoint.get("work_order") or {})
        budget = dict(work_order.get("budget") or {})
        return str(budget.get("mode") or "") == "adaptive"

    def ensure(self) -> None:
        self.store.ensure()
        with self.storage.connect() as conn:
            conn.execute(CONTROL_DDL)
            conn.commit()

    @staticmethod
    def _iso(value: Any) -> str:
        return value.isoformat() if hasattr(value, "isoformat") else str(value or "")

    def state_fingerprint(
        self,
        plan: dict[str, Any],
        work_order: dict[str, Any],
        job: dict[str, Any] | None,
    ) -> str:
        result = dict((job or {}).get("result") or {})
        snapshot = {
            "plan_id": plan.get("plan_id") or plan.get("id"),
            "plan_status": plan.get("status"),
            "plan_lifecycle": plan.get("lifecycle") or "active",
            "plan_updated_at": self._iso(plan.get("updated_at")),
            "work_order_id": work_order.get("work_order_id"),
            "work_order_state": work_order.get("state"),
            "work_order_lifecycle": work_order.get("lifecycle") or "active",
            "work_order_updated_at": self._iso(work_order.get("updated_at")),
            "job_id": (job or {}).get("id"),
            "job_status": (job or {}).get("status"),
            "job_updated_at": self._iso((job or {}).get("updated_at")),
            "reason": result.get("reason"),
        }
        encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def attention_generation_fingerprint(
        self,
        plan: dict[str, Any],
        work_order: dict[str, Any],
        job: dict[str, Any] | None,
        advisory: dict[str, Any],
    ) -> str:
        """Identify owner-relevant meaning without polling timestamps or opaque ids."""
        snapshot = {
            "plan_id": plan.get("plan_id") or plan.get("id"),
            "plan_status": plan.get("status"),
            "plan_lifecycle": plan.get("lifecycle") or "active",
            "work_order_id": work_order.get("work_order_id"),
            "work_order_state": work_order.get("state"),
            "work_order_lifecycle": work_order.get("lifecycle") or "active",
            "execution_mode": work_order.get("execution_mode"),
            "job_id": (job or {}).get("id"),
            "job_status": (job or {}).get("status"),
            "pr_number": work_order.get("pr_number"),
            "pr_url": work_order.get("pr_url"),
            "detail": work_order.get("detail") or {},
            "job_result": (job or {}).get("result") or {},
            "advisory_reason": advisory.get("reason"),
            "action_specs": advisory.get("action_specs") or [],
        }
        encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def standalone_attention_generation_fingerprint(
        self,
        job: dict[str, Any],
        advisory: dict[str, Any],
    ) -> str:
        """Bind one standalone blocker action to the exact durable direct-job state."""
        snapshot = {
            "job_id": job.get("id"),
            "project_id": job.get("project_id"),
            "job_status": job.get("status"),
            "job_updated_at": self._iso(job.get("updated_at")),
            "source_commit": job.get("source_commit"),
            "branch": job.get("branch"),
            "route": job.get("route") or {},
            "progress": job.get("progress") or {},
            "checkpoint": job.get("checkpoint") or {},
            "job_result": job.get("result") or {},
            "advisory_reason": advisory.get("reason"),
            "action_specs": advisory.get("action_specs") or [],
        }
        encoded = json.dumps(
            snapshot,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def supersede_pending_actions(
        self,
        *,
        plan_id: str,
        work_order_id: str,
        except_generation: str | None = None,
    ) -> int:
        self.ensure()
        generation_filter = ""
        values: list[Any] = [now(), plan_id, work_order_id]
        if except_generation is not None:
            generation_filter = " AND generation_fingerprint IS DISTINCT FROM %s"
            values.append(except_generation)
        with self.storage.connect() as conn:
            result = conn.execute(
                f"""UPDATE cp_control_actions SET status='cancelled', updated_at=%s
                WHERE status='pending' AND plan_id=%s AND work_order_id=%s
                {generation_filter}""",
                values,
            )
            conn.commit()
            return int(result.rowcount or 0)

    def supersede_obsolete_actions(self) -> int:
        """Cancel unexecuted controls whose WorkOrder left owner-attention state."""
        self.ensure()
        with self.storage.connect() as conn:
            result = conn.execute(
                """UPDATE cp_control_actions action
                SET status='cancelled', updated_at=%s
                FROM cp_plan_work_orders work_order
                WHERE action.status='pending'
                  AND action.plan_id=work_order.plan_id
                  AND action.work_order_id=work_order.work_order_id
                  AND (work_order.lifecycle <> 'active'
                    OR work_order.state NOT IN ('awaiting_merge','blocked','waiting_human'))""",
                (now(),),
            )
            conn.commit()
            return int(result.rowcount or 0)

    def _current_context(self, action: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
        plan_id = str(action["plan_id"])
        work_order_id = str(action["work_order_id"])
        plan = self.store.orchestration(plan_id)
        if plan is None:
            raise RuntimeError("Control action plan no longer exists")
        rows = {str(row["work_order_id"]): dict(row) for row in self.store.work_orders(plan_id)}
        work_order = rows.get(work_order_id)
        if work_order is None:
            raise RuntimeError("Control action WorkOrder no longer exists")
        job_id = str(action.get("job_id") or "")
        job = self.storage.get(job_id) if job_id else None
        if job_id and job is None:
            raise RuntimeError("Control action job no longer exists")
        return dict(plan), work_order, dict(job) if job else None

    @staticmethod
    def _last_provider_failure(job: dict[str, Any]) -> dict[str, Any]:
        failures = list((job.get("progress") or {}).get("provider_failures") or [])
        for item in reversed(failures):
            if isinstance(item, dict):
                return dict(item)
        return {}

    @staticmethod
    def _phase(reason: str) -> str:
        if reason.startswith("planner_"):
            return "planning"
        if reason.startswith("preflight_"):
            return "preflight"
        if reason.startswith("evaluator_"):
            return "evaluation"
        if reason.startswith("github_") or reason.startswith("delivery_"):
            return "delivery"
        if reason in {"reassessment_stopped", "unsafe_bare_completion"}:
            return "reassessment"
        return "execution"

    @staticmethod
    def _budget_metric(job: dict[str, Any], dimension: str) -> dict[str, Any] | None:
        spec = _BUDGET_EXTENSION_SPECS.get(dimension)
        route = job.get("route") or {}
        budget = ((route.get("strategy") or {}).get("budget") or {})
        progress = job.get("progress") or {}
        if not spec or dimension not in budget:
            return None
        used = progress.get(spec["counter"], 0)
        limit = budget.get(dimension)
        return {"key": dimension, "label": spec["label"], "used": used, "limit": limit}

    @staticmethod
    def _changed_file_scope_recovery_candidate(job: dict[str, Any]) -> bool:
        result = dict(job.get("result") or {})
        if str(result.get("reason") or "") != "reassessment_stopped":
            return False

        reassess = dict(result.get("reassess") or {})
        signals = {
            str(item)
            for item in reassess.get("signals") or []
            if str(item)
        }
        # Adaptive estimate/headroom signals are informational telemetry. They do
        # not represent an abnormal execution condition and must not mask an
        # otherwise recoverable legacy changed-file scope stop. Emergency
        # threshold signals remain material and therefore fail closed.
        material_signals = {
            signal
            for signal in signals
            if not signal.startswith("budget_headroom_active:")
            and not signal.startswith("budget_estimate_exceeded:")
        }
        if material_signals != {"scope_expansion"}:
            return False

        route = dict(job.get("route") or {})
        strategy = dict(route.get("strategy") or {})
        if strategy.get("budget_mode") != "adaptive":
            return False

        progress = dict(job.get("progress") or {})
        if not bool(progress.get("unexpected_scope")):
            return False

        budget = dict(strategy.get("budget") or {})
        try:
            changed_files = int(progress.get("changed_files") or 0)
            previous_limit = int(budget["max_changed_files"])
        except (KeyError, TypeError, ValueError):
            return False
        return changed_files > previous_limit

    def blocked_advisory(self, work_order: dict[str, Any], job: dict[str, Any] | None) -> dict[str, Any]:
        job = job or {}
        result = dict(job.get("result") or {})
        reason = str(result.get("reason") or ("runtime_failed" if job.get("status") == "failed" else "work_order_blocked"))
        last_failure = str(result.get("last_failure") or "")
        progress = dict(job.get("progress") or {})
        route = dict(job.get("route") or {})
        budget = dict((route.get("strategy") or {}).get("budget") or {})
        provider_failure = self._last_provider_failure(job)
        failure_kind = str(provider_failure.get("kind") or "")
        model = str(provider_failure.get("model") or "")
        provider = str(provider_failure.get("provider") or "")

        advisory: dict[str, Any] = {
            "title": "WORKORDER BLOCKED",
            "phase": self._phase(reason),
            "reason": reason,
            "summary": "The WorkOrder is blocked and requires owner attention.",
            "cause": "Runtime stopped safely at a durable control gate.",
            "preserved": [
                "Same job and workspace are preserved when present.",
                "Existing diff, progress and durable usage counters are preserved.",
                "Downstream WorkOrders remain pending until existing gates are satisfied.",
            ],
            "impact": "No further automated work will run for this WorkOrder until a valid recovery action succeeds.",
            "recommended": "Review the safe details below and choose only an available bounded action.",
            "metrics": [],
            "action_specs": [
                {"action_type": "details", "label": "📋 Chi tiết", "payload": {}},
                {"action_type": "keep_blocked", "label": "⛔ Giữ blocked", "payload": {}},
            ],
        }

        legacy_recovery = recover_legacy_accepted_result(job)

        dimension = _BUDGET_FAILURE_MAP.get(last_failure)
        if (
            self._adaptive_work_shape_nonblocking(job)
            and dimension in _ADAPTIVE_WORK_SHAPE_DIMENSIONS
        ):
            dimension = None
        if reason in {"planner_budget_exhausted", "preflight_budget_exhausted", "execution_budget_exhausted"}:
            advisory["summary"] = "Runtime execution budget was exhausted."
            advisory["cause"] = "A Runtime safety budget reached its current limit. This is not a provider rolling quota reset."
            if dimension:
                metric = self._budget_metric(job, dimension)
                if metric:
                    advisory["metrics"].append(metric)
                spec = _BUDGET_EXTENSION_SPECS[dimension]
                advisory["recommended"] = (
                    f"Approve a bounded +{spec['increment']} extension only if the existing WorkOrder still needs more work."
                )
                advisory["action_specs"].insert(
                    0,
                    {
                        "action_type": "budget_extend",
                        "label": f"➕ +{spec['increment']} {spec['label']}",
                        "payload": {"dimension": dimension, "increment": spec["increment"]},
                    },
                )
            else:
                advisory["recommended"] = "Keep the WorkOrder blocked and review the exhausted token/cost budget outside Telegram."

        elif reason in _PROVIDER_BLOCK_REASONS:
            advisory["summary"] = "Provider/model execution failed and no eligible fallback completed the phase."
            advisory["metrics"] = [
                item for item in (
                    {"label": "Model", "value": model} if model else None,
                    {"label": "Provider", "value": provider} if provider else None,
                    {"label": "Failure kind", "value": failure_kind} if failure_kind else None,
                ) if item
            ]
            if failure_kind == "quota_exhausted":
                advisory["cause"] = "The provider reported quota exhaustion; the job state was preserved."
                advisory["recommended"] = "Wait for the provider quota window to reset, then confirm from Telegram."
                advisory["action_specs"] = [
                    {"action_type": "provider_quota_reset", "label": "✅ Quota đã reset — tiếp tục", "payload": {}},
                    {"action_type": "reroute_provider", "label": "🔀 Chuyển provider", "payload": {}},
                    {"action_type": "details", "label": "📋 Chi tiết", "payload": {}},
                    {"action_type": "keep_blocked", "label": "⛔ Giữ blocked", "payload": {}},
                ]
            elif failure_kind in {"rate_limited", "provider_unavailable", "unavailable", "timeout", "transient"}:
                advisory["cause"] = "The selected provider was temporarily unavailable or rate limited."
                advisory["recommended"] = "Retry the provider or request a fresh eligible route."
                advisory["action_specs"] = [
                    {"action_type": "retry_provider", "label": "🔁 Thử lại provider", "payload": {}},
                    {"action_type": "reroute_provider", "label": "🔀 Chuyển provider", "payload": {}},
                    {"action_type": "details", "label": "📋 Chi tiết", "payload": {}},
                    {"action_type": "keep_blocked", "label": "⛔ Giữ blocked", "payload": {}},
                ]
            elif failure_kind in {"authentication", "auth", "configuration", "invalid_api_key"}:
                advisory["cause"] = "Provider authentication or configuration needs operator repair outside Telegram."
                advisory["recommended"] = "Repair provider credentials/configuration, then confirm that repair before retrying."
                advisory["action_specs"] = [
                    {"action_type": "provider_credentials_fixed", "label": "✅ Credentials đã sửa — retry", "payload": {}},
                    {"action_type": "reroute_provider", "label": "🔀 Chuyển provider", "payload": {}},
                    {"action_type": "details", "label": "📋 Chi tiết", "payload": {}},
                    {"action_type": "keep_blocked", "label": "⛔ Giữ blocked", "payload": {}},
                ]
            else:
                advisory["cause"] = "The provider/model failed with a non-actionable or unknown safe category."
                advisory["recommended"] = "Request a fresh route only if policy can resolve another eligible provider; otherwise keep blocked."
                advisory["action_specs"] = [
                    {"action_type": "reroute_provider", "label": "🔀 Reroute", "payload": {}},
                    {"action_type": "details", "label": "📋 Chi tiết", "payload": {}},
                    {"action_type": "keep_blocked", "label": "⛔ Giữ blocked", "payload": {}},
                ]

        elif legacy_recovery["candidate"]:
            advisory["phase"] = "delivery"
            if legacy_recovery["accepted_result"] is not None:
                advisory["summary"] = "Legacy Runtime lost the accepted result after GitHub delivery had already begun."
                advisory["cause"] = "Authoritative delivery, verification, review, route, branch and commit evidence still match."
                advisory["recommended"] = "Retry delivery or recheck CI using the exact preserved accepted commit."
                advisory["action_specs"] = [
                    {"action_type": "retry_delivery", "label": "🔁 Retry delivery", "payload": {}},
                    {"action_type": "recheck_ci", "label": "🔄 Recheck CI", "payload": {}},
                    {"action_type": "details", "label": "📋 Chi tiết", "payload": {}},
                    {"action_type": "keep_blocked", "label": "⛔ Giữ blocked", "payload": {}},
                ]
            else:
                advisory["summary"] = "Legacy Runtime lost the accepted result after delivery, but the remaining evidence is incomplete."
                advisory["cause"] = "Runtime will not reconstruct acceptance or return to coding without every required authoritative binding."
                advisory["recommended"] = "Keep the job blocked and inspect the missing durable acceptance evidence outside Telegram."

        elif reason == LEGACY_RECOVERY_BLOCK_REASON:
            advisory["phase"] = "delivery"
            advisory["summary"] = "Legacy delivery acceptance evidence is incomplete."
            advisory["cause"] = "Runtime stopped before coding because it cannot safely reconstruct the prior accepted result."
            advisory["recommended"] = "Keep the same job blocked and repair or verify acceptance only through an authoritative operator mechanism."

        elif reason == "material_change_missing_without_model_fallback":
            advisory["summary"] = "The coding agent completed without the required material repository change."
            advisory["cause"] = "Runtime could not find an eligible model fallback after a no-effect attempt."
            advisory["recommended"] = "Retry with a fresh eligible route without broadening WorkOrder scope."
            advisory["action_specs"].insert(0, {"action_type": "reroute_retry", "label": "🔀 Reroute + retry", "payload": {}})

        elif reason == "preflight_failed":
            advisory["summary"] = "Deterministic preflight verification failed."
            advisory["cause"] = "A configured preflight check failed; raw command output is intentionally not sent to Telegram."
            advisory["recommended"] = "Inspect the deterministic verification failure outside Telegram before retrying."

        elif reason in {"reassessment_stopped", "unsafe_bare_completion"}:
            advisory["summary"] = "Runtime reassessment refused to continue or complete automatically."
            reassess = dict(result.get("reassess") or {})
            nested_reason = str(reassess.get("reason") or "").strip()[:300]
            safe_signals = [
                str(item)[:120]
                for item in reassess.get("signals") or []
                if str(item).replace("_", "").replace(":", "").replace("-", "").isalnum()
            ][:12]
            advisory["cause"] = (
                f"Router reassessment: {nested_reason}"
                if nested_reason
                else "The current Definition-of-Done/reassessment state did not authorize automatic completion."
            )
            if safe_signals:
                advisory["metrics"].append({
                    "label": "Reassessment signals",
                    "value": ", ".join(safe_signals),
                })

            if self._changed_file_scope_recovery_candidate(job):
                progress = dict(job.get("progress") or {})
                strategy = dict((job.get("route") or {}).get("strategy") or {})
                budget = dict(strategy.get("budget") or {})
                advisory["metrics"].append({
                    "label": "Changed files",
                    "used": int(progress.get("changed_files") or 0),
                    "limit": int(budget.get("max_changed_files") or 0),
                    "key": "max_changed_files",
                })
                advisory["recommended"] = (
                    "Refresh the current adaptive scope policy and resume the same job only if "
                    "fresh changed-file emergency headroom exists and no protected path is present."
                )
                advisory["action_specs"].insert(0, {
                    "action_type": "pm_scope_reassess",
                    "label": "🧭 PM review file scope",
                    "payload": {},
                })
            else:
                advisory["recommended"] = "Review the WorkOrder and existing decision boundary. There is intentionally no force-complete action."

        elif reason in {
            "github_delivery_failed",
            "github_ci_timeout",
            "github_ci_infrastructure_failure",
        }:
            advisory["summary"] = "Locally verified work is blocked in GitHub delivery/CI observation."
            if reason == "github_ci_infrastructure_failure":
                advisory["cause"] = "GitHub CI failed before repository execution began; the accepted commit and PR are preserved."
            else:
                advisory["cause"] = "The accepted local result is preserved; Runtime does not need to recode it before a delivery retry."
            advisory["recommended"] = "Retry delivery or recheck CI while preserving the accepted result."
            advisory["action_specs"] = [
                {"action_type": "retry_delivery", "label": "🔁 Retry delivery", "payload": {}},
                {"action_type": "recheck_ci", "label": "🔄 Recheck CI", "payload": {}},
                {"action_type": "details", "label": "📋 Chi tiết", "payload": {}},
                {"action_type": "keep_blocked", "label": "⛔ Giữ blocked", "payload": {}},
            ]

        elif reason == "github_delivery_budget_exhausted":
            metric = self._budget_metric(job, "max_wall_time_minutes")
            if metric:
                advisory["metrics"].append(metric)
            if self._adaptive_work_shape_nonblocking(job):
                advisory["summary"] = "Verified adaptive work hit a historical total wall-time delivery gate."
                advisory["cause"] = "The accepted commit is preserved; total adaptive wall time is telemetry under the current policy."
                advisory["recommended"] = "Retry the preserved delivery state; no wall-time extension is required."
                advisory["action_specs"] = [
                    {"action_type": "retry_delivery", "label": "🔄 Thử lại delivery", "payload": {}},
                    {"action_type": "details", "label": "📋 Chi tiết", "payload": {}},
                    {"action_type": "keep_blocked", "label": "⛔ Giữ blocked", "payload": {}},
                ]
            else:
                advisory["summary"] = "GitHub delivery ran out of the Runtime wall-time budget."
                advisory["cause"] = "The locally verified accepted result is preserved, but no delivery time remains."
                advisory["recommended"] = "Approve a bounded wall-time extension, then retry the same delivery state."
                spec = _BUDGET_EXTENSION_SPECS["max_wall_time_minutes"]
                advisory["action_specs"] = [
                    {
                        "action_type": "budget_extend",
                        "label": f"➕ +{spec['increment']} phút",
                        "payload": {"dimension": "max_wall_time_minutes", "increment": spec["increment"]},
                    },
                    {"action_type": "details", "label": "📋 Chi tiết", "payload": {}},
                    {"action_type": "keep_blocked", "label": "⛔ Giữ blocked", "payload": {}},
                ]

        elif reason == "delivery_missing_verified_commit":
            advisory["summary"] = "Delivery cannot proceed because the accepted result has no verified commit."
            advisory["cause"] = "Runtime will not fabricate a commit or force GitHub delivery."
            advisory["recommended"] = "Review the preserved local result and repair the delivery invariant outside Telegram."

        elif job.get("status") == "interrupted":
            advisory["summary"] = "Runtime execution was interrupted and requires explicit same-job recovery."
            advisory["cause"] = "The previous in-flight process stopped; durable job/workspace state was preserved."
            advisory["recommended"] = "Resume the same job, optionally requesting a fresh route."
            advisory["action_specs"] = [
                {"action_type": "resume_same", "label": "▶️ Resume same job", "payload": {}},
                {"action_type": "resume_reroute", "label": "🔀 Resume + reroute", "payload": {}},
                {"action_type": "details", "label": "📋 Chi tiết", "payload": {}},
                {"action_type": "keep_blocked", "label": "⛔ Giữ blocked", "payload": {}},
            ]

        if budget:
            for dimension in ("max_model_calls", "max_tool_calls", "max_test_runs", "max_wall_time_minutes", "max_repair_iterations"):
                if not any(item.get("key") == dimension for item in advisory["metrics"] if isinstance(item, dict)):
                    metric = self._budget_metric(job, dimension)
                    if metric and metric["used"]:
                        advisory["metrics"].append(metric)

        return advisory

    def waiting_human_advisory(self, work_order: dict[str, Any], job: dict[str, Any] | None) -> dict[str, Any]:
        if str(work_order.get("execution_mode") or "") == "operator":
            return {
                "title": "OPERATOR ACTION REQUIRED",
                "phase": "operator",
                "reason": "operator_waiting_human",
                "summary": "An operator WorkOrder is waiting for owner confirmation.",
                "cause": "The plan intentionally requires a human/operator step before dependencies may continue.",
                "preserved": ["Downstream WorkOrders remain pending."],
                "impact": "Automation will not pass this operator gate until the owner resolves it.",
                "recommended": "Complete the documented operator procedure, then mark it complete or blocked.",
                "metrics": [],
                "action_specs": [
                    {"action_type": "operator_complete", "label": "✅ Mark complete", "payload": {}},
                    {"action_type": "operator_block", "label": "⛔ Mark blocked", "payload": {}},
                    {"action_type": "details", "label": "📋 Xem hướng dẫn", "payload": {}},
                ],
            }
        checkpoint = dict((job or {}).get("checkpoint") or {})
        pending = dict(checkpoint.get("pending_decision") or {})
        decision_key = str(pending.get("key") or "")
        decision_payload = {"decision_key": decision_key} if decision_key else {}
        review_repair_churn = str(pending.get("source") or "") == "review_repair_churn"
        return {
            "title": "HUMAN DECISION REQUIRED",
            "phase": "decision",
            "reason": (
                "repair_churn_circuit_breaker"
                if review_repair_churn
                else "human_decision_required"
            ),
            "summary": (
                "Review repair reached its bounded anomaly window."
                if review_repair_churn
                else "Runtime is waiting for an explicit human decision."
            ),
            "cause": (
                "Another repair/verification window requires explicit authorization for this exact request generation."
                if review_repair_churn
                else "A configured governance decision boundary requires owner approval before execution continues."
            ),
            "preserved": ["Same job/workspace and durable progress are preserved."],
            "impact": "The job will not continue until this exact durable decision is resolved.",
            "recommended": (
                "Approve only to authorize one new bounded repair window; otherwise reject and keep the epoch baseline unchanged."
                if review_repair_churn
                else "Approve only if the displayed WorkOrder decision boundary is acceptable; otherwise reject it."
            ),
            "metrics": [],
            "action_specs": [
                {"action_type": "human_decision_approve", "label": "✅ Approve", "payload": decision_payload},
                {"action_type": "human_decision_reject", "label": "❌ Reject", "payload": decision_payload},
                {"action_type": "details", "label": "📋 Chi tiết", "payload": {}},
            ],
        }

    @staticmethod
    def manual_merge_advisory(pr_url: str | None) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        if pr_url:
            actions.append({"action_type": "url", "label": "🔗 Open PR", "url": pr_url})
        actions.append({"action_type": "recheck_orchestration", "label": "🔄 Tôi đã merge — kiểm tra lại", "payload": {}})
        return {
            "title": "MANUAL MERGE REQUIRED",
            "phase": "delivery",
            "reason": "awaiting_merge",
            "summary": "PR passed automated gates and is waiting for manual merge.",
            "cause": "The platform intentionally never auto-merges owner-reviewed work.",
            "preserved": ["Downstream WorkOrders remain pending until merge is observed."],
            "impact": "The plan cannot advance past this WorkOrder yet.",
            "recommended": "Open the PR, review and merge it manually, then ask Runtime to reconcile.",
            "metrics": [],
            "action_specs": actions,
        }

    def create_actions(
        self,
        *,
        plan: dict[str, Any],
        work_order: dict[str, Any],
        job: dict[str, Any] | None,
        advisory: dict[str, Any],
        ttl_hours: int = 48,
    ) -> list[dict[str, Any]]:
        self.ensure()
        if (
            str(plan.get("lifecycle") or "active") != "active"
            or str(work_order.get("lifecycle") or "active") != "active"
        ):
            return []
        fingerprint = self.state_fingerprint(plan, work_order, job)
        generation_fingerprint = self.attention_generation_fingerprint(
            plan,
            work_order,
            job,
            advisory,
        )
        plan_id = str(plan.get("plan_id") or plan.get("id") or "")
        work_order_id = str(work_order.get("work_order_id") or "")
        rendered: list[dict[str, Any]] = []
        for spec in advisory.get("action_specs") or []:
            action_type = str(spec.get("action_type") or "")
            label = str(spec.get("label") or "")[:80]
            if action_type == "url":
                url = str(spec.get("url") or "")
                if url.startswith("https://github.com/"):
                    rendered.append({"label": label, "url": url})
                continue
            payload = deepcopy(spec.get("payload") or {})
            if action_type == "details":
                payload["advisory"] = {key: deepcopy(value) for key, value in advisory.items() if key != "action_specs"}
            action = self.create_action(
                action_type=action_type,
                plan_id=plan_id,
                work_order_id=work_order_id,
                job_id=str((job or {}).get("id") or "") or None,
                state_fingerprint=fingerprint,
                generation_fingerprint=generation_fingerprint,
                payload=payload,
                ttl_hours=ttl_hours,
            )
            rendered.append({
                "label": label,
                "action_type": action_type,
                "action_id": action["action_id"],
                "callback_data": f"act:{action['action_id']}",
            })
        self.supersede_pending_actions(
            plan_id=plan_id,
            work_order_id=work_order_id,
            except_generation=generation_fingerprint,
        )
        return rendered

    def create_action(
        self,
        *,
        action_type: str,
        plan_id: str,
        work_order_id: str,
        job_id: str | None,
        state_fingerprint: str,
        generation_fingerprint: str,
        payload: dict[str, Any],
        ttl_hours: int,
    ) -> dict[str, Any]:
        if not action_type or not plan_id or not work_order_id:
            raise RuntimeError("Invalid control action identity")
        timestamp = now()
        expires_at = timestamp + timedelta(hours=max(1, min(168, int(ttl_hours))))
        dedupe_source = json.dumps(
            {
                "action_type": action_type,
                "plan_id": plan_id,
                "work_order_id": work_order_id,
                "job_id": job_id,
                "generation_fingerprint": generation_fingerprint,
                "payload": payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        dedupe_key = hashlib.sha256(dedupe_source.encode("utf-8")).hexdigest()
        action_id = secrets.token_urlsafe(18)
        with self.storage.connect() as conn:
            row = conn.execute(
                """INSERT INTO cp_control_actions
                (action_id, dedupe_key, action_type, plan_id, work_order_id, job_id,
                 state_fingerprint, generation_fingerprint, payload, status, result,
                 expires_at, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'pending',NULL,%s,%s,%s)
                ON CONFLICT (dedupe_key) DO UPDATE SET
                  status = CASE
                    WHEN cp_control_actions.status='failed'
                     AND cp_control_actions.state_fingerprint=EXCLUDED.state_fingerprint
                     AND cp_control_actions.generation_fingerprint=EXCLUDED.generation_fingerprint
                    THEN 'pending'
                    ELSE cp_control_actions.status
                  END,
                  result = CASE
                    WHEN cp_control_actions.status='failed'
                     AND cp_control_actions.state_fingerprint=EXCLUDED.state_fingerprint
                     AND cp_control_actions.generation_fingerprint=EXCLUDED.generation_fingerprint
                    THEN NULL
                    ELSE cp_control_actions.result
                  END,
                  expires_at = CASE
                    WHEN cp_control_actions.status='failed'
                     AND cp_control_actions.state_fingerprint=EXCLUDED.state_fingerprint
                     AND cp_control_actions.generation_fingerprint=EXCLUDED.generation_fingerprint
                    THEN EXCLUDED.expires_at
                    ELSE cp_control_actions.expires_at
                  END,
                  updated_at = CASE
                    WHEN cp_control_actions.status='failed'
                     AND cp_control_actions.state_fingerprint=EXCLUDED.state_fingerprint
                     AND cp_control_actions.generation_fingerprint=EXCLUDED.generation_fingerprint
                    THEN EXCLUDED.updated_at
                    ELSE cp_control_actions.updated_at
                  END
                RETURNING *""",
                (
                    action_id, dedupe_key, action_type, plan_id, work_order_id, job_id,
                    state_fingerprint, generation_fingerprint, json.dumps(payload),
                    expires_at, timestamp, timestamp,
                ),
            ).fetchone()
            conn.commit()
        return dict(row)

    def get_action(self, action_id: str) -> dict[str, Any] | None:
        self.ensure()
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM cp_control_actions WHERE action_id=%s", (action_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def _expected_owner_identity() -> tuple[str, str]:
        return (
            os.getenv("TELEGRAM_OWNER_USER_ID", "").strip(),
            os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        )

    def _validate_owner_identity(self, *, telegram_user_id: str, telegram_chat_id: str) -> None:
        expected_user, expected_chat = self._expected_owner_identity()
        if not expected_user or not expected_chat:
            raise RuntimeError("Telegram owner identity is not configured")
        if not secrets.compare_digest(str(telegram_user_id), expected_user):
            raise RuntimeError("Telegram owner identity mismatch")
        if not secrets.compare_digest(str(telegram_chat_id), expected_chat):
            raise RuntimeError("Telegram chat identity mismatch")

    @staticmethod
    def _already_resolved_result(action: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "already_resolved",
            "action_id": action["action_id"],
            "action_type": action["action_type"],
            "message": "The merge gate is already resolved and the WorkOrder is completed; no action is required.",
        }

    @staticmethod
    def _superseded_result(action: dict[str, Any], work_order: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "superseded",
            "action_id": action["action_id"],
            "action_type": action["action_type"],
            "message": "This WorkOrder was explicitly replaced; no recovery action is required.",
            "superseded_by_plan_id": work_order.get("superseded_by_plan_id"),
            "superseded_by_work_order_id": work_order.get("superseded_by_work_order_id"),
        }

    async def execute(
        self,
        action_id: str,
        *,
        telegram_user_id: str,
        telegram_chat_id: str,
    ) -> dict[str, Any]:
        self._validate_owner_identity(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
        )
        return await self._execute_authorized(action_id)

    async def execute_remote(
        self,
        action_id: str,
        *,
        expected_job_id: str,
        expected_generation: str,
    ) -> dict[str, Any]:
        """Execute one already-issued routine recovery action via GitHub PM control."""
        action = self.get_action(action_id)
        if action is None:
            raise RuntimeError("Unknown control action")
        if str(action.get("job_id") or "") != expected_job_id:
            raise RuntimeError("Remote control action job identity mismatch")
        if not secrets.compare_digest(
            str(action.get("generation_fingerprint") or ""),
            expected_generation,
        ):
            raise RuntimeError("Remote control action generation mismatch")
        action_type = str(action.get("action_type") or "")
        if action_type not in _REMOTE_ROUTINE_ACTION_TYPES:
            raise RuntimeError(
                f"Remote PM channel cannot execute action_type={action_type}"
            )
        return await self._execute_authorized(action_id)

    async def _execute_authorized(self, action_id: str) -> dict[str, Any]:
        self.ensure()
        timestamp = now()
        with self.storage.connect() as conn:
            action = conn.execute(
                "SELECT * FROM cp_control_actions WHERE action_id=%s FOR UPDATE",
                (action_id,),
            ).fetchone()
            if action is None:
                raise RuntimeError("Unknown control action")
            action = dict(action)
            if action["status"] == "executed":
                return dict(action.get("result") or {})
            _, current_work_order, _ = self._current_context(action)
            if str(current_work_order.get("lifecycle") or "active") == "superseded":
                return self._superseded_result(action, current_work_order)
            if action["action_type"] == "recheck_orchestration":
                work_order = current_work_order
                if str(work_order.get("state") or "") == "completed":
                    result = self._already_resolved_result(action)
                    if action["status"] == "pending":
                        conn.execute(
                            """UPDATE cp_control_actions
                            SET status='executed', result=%s::jsonb, updated_at=%s
                            WHERE action_id=%s AND status='pending'""",
                            (json.dumps(result), timestamp, action_id),
                        )
                        conn.commit()
                    return result
            if action["status"] != "pending":
                raise RuntimeError(f"Control action is not pending (status={action['status']})")
            if action["expires_at"] <= timestamp:
                conn.execute(
                    "UPDATE cp_control_actions SET status='expired', updated_at=%s WHERE action_id=%s",
                    (timestamp, action_id),
                )
                conn.commit()
                raise RuntimeError("Control action expired")

            plan, work_order, job = self._current_context(action)
            fingerprint = self.state_fingerprint(plan, work_order, job)
            if not secrets.compare_digest(fingerprint, str(action["state_fingerprint"])):
                conn.execute(
                    "UPDATE cp_control_actions SET status='stale', updated_at=%s WHERE action_id=%s",
                    (timestamp, action_id),
                )
                conn.commit()
                raise RuntimeError("Control action is stale because Runtime state changed")
            if job and str(job.get("status") or "") in _ACTIVE_JOB_STATUSES:
                raise RuntimeError("Control action cannot mutate an in-flight job")
            claimed = conn.execute(
                """UPDATE cp_control_actions SET status='executing', updated_at=%s
                WHERE action_id=%s AND status='pending' RETURNING *""",
                (timestamp, action_id),
            ).fetchone()
            conn.commit()
        if claimed is None:
            raise RuntimeError("Control action could not be claimed")
        action = dict(claimed)

        try:
            result = await self._dispatch(action)
        except Exception as exc:
            safe = {
                "status": "failed",
                "action_id": action_id,
                "action_type": str(action.get("action_type") or ""),
                "phase": "dispatch",
                "message": f"Control action failed safely: {type(exc).__name__}",
            }
            with self.storage.connect() as conn:
                conn.execute(
                    """UPDATE cp_control_actions SET status='failed', result=%s::jsonb, updated_at=%s
                    WHERE action_id=%s""",
                    (json.dumps(safe), now(), action_id),
                )
                conn.commit()
            raise

        with self.storage.connect() as conn:
            conn.execute(
                """UPDATE cp_control_actions SET status='executed', result=%s::jsonb, updated_at=%s
                WHERE action_id=%s""",
                (json.dumps(result), now(), action_id),
            )
            if action["action_type"] != "details":
                conn.execute(
                    """UPDATE cp_control_actions SET status='cancelled', updated_at=%s
                    WHERE status='pending' AND plan_id=%s AND work_order_id=%s
                      AND state_fingerprint=%s AND action_id<>%s""",
                    (now(), action["plan_id"], action["work_order_id"], action["state_fingerprint"], action_id),
                )
            conn.commit()
        return result

    async def _resume(
        self,
        job_id: str,
        *,
        reset_transient_provider_failures: bool,
        reroute: bool,
        require_changed_file_headroom: bool = False,
    ) -> dict[str, Any]:
        context = prepare_orchestrated_job_resume(self.store, job_id)
        row = await self.engine.resume(
            job_id,
            reset_transient_provider_failures=reset_transient_provider_failures,
            reroute=reroute,
            _allow_failed_orchestrated_resume=bool(context and context.get("reopen")),
            _require_changed_file_headroom=require_changed_file_headroom,
        )
        reopen_orchestrated_job(self.store, context, job_id)
        return dict(row)

    def _apply_budget_extension(self, action: dict[str, Any]) -> dict[str, Any]:
        job_id = str(action.get("job_id") or "")
        if not job_id:
            raise RuntimeError("Budget extension requires a Runtime job")
        job = self.storage.get(job_id)
        if not job:
            raise RuntimeError("Unknown job")
        payload = dict(action.get("payload") or {})
        dimension = str(payload.get("dimension") or "")
        spec = _BUDGET_EXTENSION_SPECS.get(dimension)
        if spec is None:
            raise RuntimeError("Unsupported budget extension dimension")
        increment = int(payload.get("increment") or 0)
        if increment != int(spec["increment"]):
            raise RuntimeError("Budget extension increment is not authorized")

        route = deepcopy(job.get("route") or {})
        strategy = route.get("strategy") or {}
        budget = dict(strategy.get("budget") or {})
        if dimension not in budget:
            raise RuntimeError("Current route does not expose the requested budget dimension")
        previous_limit = float(budget[dimension]) if dimension == "max_wall_time_minutes" else int(budget[dimension])
        hard_max = spec["hard_max"]
        new_limit = min(previous_limit + increment, hard_max)
        if new_limit <= previous_limit:
            raise RuntimeError("Budget extension reached the platform hard maximum")

        progress = dict(job.get("progress") or {})
        used = progress.get(spec["counter"], 0)
        budget[dimension] = new_limit
        strategy["budget"] = budget
        route["strategy"] = strategy

        checkpoint = checkpoint_from_row(job)
        authorizations = list(checkpoint.get("budget_authorizations") or [])
        authorizations.append({
            "action_id": action["action_id"],
            "channel": "telegram",
            "dimension": dimension,
            "previous_limit": previous_limit,
            "new_limit": new_limit,
            "used": used,
            "approved_at": now().isoformat(),
        })
        checkpoint["budget_authorizations"] = authorizations[-20:]
        self.storage.update(job_id, route=route, checkpoint=checkpoint)
        return {"dimension": dimension, "previous_limit": previous_limit, "new_limit": new_limit, "used": used}

    async def _dispatch(self, action: dict[str, Any]) -> dict[str, Any]:
        action_type = str(action["action_type"])
        job_id = str(action.get("job_id") or "")
        payload = dict(action.get("payload") or {})

        if action_type == "details":
            return {
                "status": "ok",
                "action_id": action["action_id"],
                "action_type": action_type,
                "message": "Detailed Runtime advisory requested.",
                "advisory": deepcopy(payload.get("advisory") or {}),
            }
        if action_type == "keep_blocked":
            return {
                "status": "executed",
                "action_id": action["action_id"],
                "action_type": action_type,
                "message": "WorkOrder remains blocked. Other actions from this state were cancelled.",
            }
        if action_type in {"provider_quota_reset", "provider_credentials_fixed"}:
            row = await self._resume(job_id, reset_transient_provider_failures=True, reroute=True)
            return self._resume_result(action, row, "Provider state cleared and the same job was resumed with a fresh route.")
        if action_type == "retry_provider":
            row = await self._resume(job_id, reset_transient_provider_failures=True, reroute=False)
            return self._resume_result(action, row, "Transient provider state cleared and the same job was retried.")
        if action_type in {"reroute_provider", "reroute_retry", "resume_reroute"}:
            row = await self._resume(job_id, reset_transient_provider_failures=True, reroute=True)
            return self._resume_result(action, row, "The same job was resumed through a fresh eligible route.")
        if action_type == "pm_scope_reassess":
            current = self.storage.get(job_id) or {}
            if not self._changed_file_scope_recovery_candidate(current):
                raise RuntimeError("Changed-file scope recovery is no longer valid")
            row = await self._resume(
                job_id,
                reset_transient_provider_failures=False,
                reroute=True,
                require_changed_file_headroom=True,
            )
            return self._resume_result(
                action,
                row,
                "Current adaptive scope policy was revalidated; the same job resumed into the PM reassessment gate without resetting its workspace, diff or counters.",
            )
        if action_type == "resume_same":
            row = await self._resume(job_id, reset_transient_provider_failures=False, reroute=False)
            return self._resume_result(action, row, "The same interrupted job was resumed without replacing its route.")
        if action_type == "budget_extend":
            authorization = self._apply_budget_extension(action)
            row = await self._resume(job_id, reset_transient_provider_failures=False, reroute=False)
            result = self._resume_result(action, row, "Bounded budget extension approved; the same job was resumed without resetting usage.")
            result["budget_authorization"] = authorization
            return result
        if action_type in {"retry_delivery", "recheck_ci"}:
            row = await self._resume(job_id, reset_transient_provider_failures=False, reroute=False)
            return self._resume_result(action, row, "Preserved accepted work was queued for delivery/CI recheck.")
        if action_type in {"human_decision_approve", "human_decision_reject"}:
            decision_action = "approve" if action_type.endswith("approve") else "reject"
            row = await self.engine.resolve_human_decision(
                job_id,
                action=decision_action,
                note="Resolved by Telegram owner control action",
                expected_decision_key=(
                    str(payload.get("decision_key"))
                    if payload.get("decision_key")
                    else None
                ),
            )
            if self.orchestrator is not None:
                await self.orchestrator.tick()
            return self._resume_result(action, row, f"Human decision {decision_action}d through the exact durable decision key.")
        if action_type in {"operator_complete", "operator_block"}:
            if self.orchestrator is None:
                raise RuntimeError("Operator control requires orchestration context")
            operator_action = "complete" if action_type.endswith("complete") else "block"
            view = await self.orchestrator.resolve_operator(
                plan_id=str(action["plan_id"]),
                work_order_id=str(action["work_order_id"]),
                action=operator_action,
                note="Resolved by Telegram owner control action",
            )
            return {
                "status": "executed",
                "action_id": action["action_id"],
                "action_type": action_type,
                "message": f"Operator WorkOrder marked {operator_action}.",
                "plan_status": view.get("status"),
            }
        if action_type == "recheck_orchestration":
            if self.orchestrator is None:
                raise RuntimeError("Recheck requires orchestration context")
            tick = await self.orchestrator.tick()
            return {
                "status": "executed",
                "action_id": action["action_id"],
                "action_type": action_type,
                "message": "Orchestration reconciliation completed; Runtime did not merge the PR.",
                "tick": tick,
            }
        raise RuntimeError("Unsupported control action type")

    @staticmethod
    def _resume_result(action: dict[str, Any], row: dict[str, Any], message: str) -> dict[str, Any]:
        return {
            "status": "executed",
            "action_id": action["action_id"],
            "action_type": action["action_type"],
            "message": message,
            "job_id": row.get("id"),
            "job_status": row.get("status"),
        }
