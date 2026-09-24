from __future__ import annotations

import asyncio
from copy import deepcopy

from app.orchestrator_notifications import PlanOrchestrator


class FakeQueryResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return deepcopy(self.rows)


class FakeConnection:
    def __init__(self, storage):
        self.storage = storage

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        if "SELECT plan_id FROM cp_plan_orchestrations" in sql:
            return FakeQueryResult([{"plan_id": self.storage.plan_id}])
        raise AssertionError(f"unexpected fake SQL: {sql}")


class FakeStorage:
    def __init__(self, jobs=None, *, plan_id="pm-gh-200"):
        self.jobs = jobs or {}
        self.plan_id = plan_id

    def get(self, job_id):
        return self.jobs.get(job_id)

    def get_execution_plan(self, plan_id):
        return {
            "id": plan_id,
            "project_id": "demo",
            "ticket": {"id": "GH-5", "title": "Recovery", "description": "bounded"},
        }

    def connect(self):
        return FakeConnection(self)


class FakeDdev:
    def __init__(self):
        self.prs = {}

    async def github_pull_request(self, *, project_id, pr_number):
        return deepcopy(
            self.prs.get(
                pr_number,
                {"number": pr_number, "state": "open", "merged": False},
            )
        )


class FakeEngine:
    def __init__(self):
        self.ddev = FakeDdev()


class FakeControls:
    def __init__(self):
        self.orchestrator = None
        self.include_budget_action = True
        self.actions = {}
        self.created_action_count = 0

    def ensure(self):
        return None

    def manual_merge_advisory(self, pr_url):
        return {
            "title": "MANUAL MERGE REQUIRED",
            "phase": "delivery",
            "reason": "awaiting_merge",
            "summary": "PR passed its automated gates and is ready for manual merge.",
            "cause": "Manual merge policy.",
            "preserved": ["Downstream work is pending."],
            "impact": "Plan waits for owner merge.",
            "recommended": "Review and merge manually.",
            "metrics": [],
            "action_specs": [
                {"action_type": "url", "label": "Open PR", "url": pr_url},
                {
                    "action_type": "recheck_orchestration",
                    "label": "Recheck merge",
                    "payload": {},
                },
            ],
        }

    def waiting_human_advisory(self, work_order, job):
        return {
            "title": "HUMAN DECISION REQUIRED",
            "phase": "decision",
            "reason": "human_decision_required",
            "summary": "Owner decision required.",
            "cause": "Governance gate.",
            "preserved": [],
            "impact": "Job waits.",
            "recommended": "Review the decision.",
            "metrics": [],
            "action_specs": [],
        }

    def blocked_advisory(self, work_order, job):
        result = (job or {}).get("result") or {}
        reason = result.get("reason") or (work_order.get("detail") or {}).get("reason") or "work_order_blocked"
        metrics = []
        if reason == "execution_budget_exhausted":
            metrics = [{"key": "max_model_calls", "label": "Model calls", "used": 10, "limit": 10}]
        return {
            "title": "WORKORDER BLOCKED",
            "phase": "execution",
            "reason": reason,
            "summary": "Runtime execution is blocked.",
            "cause": "A bounded safety gate stopped the job.",
            "preserved": ["Same job/workspace and progress are preserved."],
            "impact": "Downstream work stays pending.",
            "recommended": "Use a bounded owner action.",
            "metrics": metrics,
            "action_specs": [],
        }

    def create_actions(self, *, plan, work_order, job, advisory, ttl_hours=48):
        if advisory["reason"] == "execution_budget_exhausted":
            actions = [
                {
                    "label": "📋 Chi tiết",
                    "action_id": "details-action",
                    "callback_data": "act:details-action",
                }
            ]
            if self.include_budget_action:
                actions.insert(
                    0,
                    {
                        "label": "➕ +4 Model calls",
                        "action_id": "opaque-action-id",
                        "callback_data": "act:opaque-action-id",
                    },
                )
            return actions
        if advisory["reason"] == "awaiting_merge":
            generation = repr(
                (
                    plan.get("plan_id"),
                    plan.get("status"),
                    work_order.get("work_order_id"),
                    work_order.get("state"),
                    work_order.get("pr_number"),
                    work_order.get("pr_url"),
                    work_order.get("detail"),
                    advisory.get("action_specs"),
                )
            )
            action = self.actions.get(generation)
            if action is None:
                self.created_action_count += 1
                action = {
                    "label": "Recheck merge",
                    "action_type": "recheck_orchestration",
                    "action_id": f"recheck-{self.created_action_count}",
                    "callback_data": f"act:recheck-{self.created_action_count}",
                    "work_order_id": work_order.get("work_order_id"),
                    "status": "pending",
                }
                self.actions[generation] = action
            return [
                {"label": "🔗 Open PR", "url": work_order.get("pr_url")},
                deepcopy(action),
            ]
        return [{"label": "📋 Chi tiết", "action_id": "details-action", "callback_data": "act:details-action"}]

    def supersede_obsolete_actions(self):
        if self.orchestrator is None:
            return 0
        changed = 0
        current_states = {
            row["work_order_id"]: row["state"]
            for row in self.orchestrator.store.rows
        }
        for action in self.actions.values():
            if (
                action["status"] == "pending"
                and current_states.get(action["work_order_id"])
                not in {"awaiting_merge", "blocked", "waiting_human"}
            ):
                action["status"] = "cancelled"
                changed += 1
        return changed


class FakeStore:
    def __init__(self, rows, *, plan_id="pm-gh-200"):
        self.rows = [dict(row) for row in rows]
        self.plan_id = plan_id
        self.plan_status = "active"
        self.plan_updated_at = "p0"
        self.update_counter = 0
        self.notifications = []

    def ensure(self):
        return None

    def register_new_plans(self):
        return []

    def active_plans(self):
        if self.plan_status in {"blocked", "completed", "waiting_human"}:
            return []
        return [plan(plan_id=self.plan_id)]

    def any_busy_work_order(self):
        return any(item["state"] in {"running", "awaiting_merge", "waiting_human"} for item in self.rows)

    def work_orders(self, plan_id):
        return [deepcopy(row) for row in self.rows]

    def update_work_order(self, plan_id, work_order_id, **fields):
        row = next(item for item in self.rows if item["work_order_id"] == work_order_id)
        if all(row.get(key) == value for key, value in fields.items()):
            return False
        row.update(deepcopy(fields))
        self.update_counter += 1
        row["updated_at"] = f"t{self.update_counter}"
        return True

    def update_plan(self, plan_id, *, status):
        if self.plan_status == status:
            return False
        self.plan_status = status
        self.update_counter += 1
        self.plan_updated_at = f"p{self.update_counter}"
        return True

    def orchestration(self, plan_id):
        return {
            "plan_id": plan_id,
            "project_id": "demo",
            "status": self.plan_status,
            "ticket_id": "GH-5",
            "github_url": "https://github.com/example/repo/issues/5",
            "updated_at": self.plan_updated_at,
        }

    def emit_notification(self, **payload):
        attention_state = payload.pop("attention_state", None)
        attention_generation = payload.pop("attention_generation", None)
        if attention_state and attention_generation:
            for item in self.notifications:
                if (
                    item["status"] in {"pending", "delivering"}
                    and item.get("plan_id") == payload.get("plan_id")
                    and item.get("work_order_id") == payload.get("work_order_id")
                    and item.get("attention_state") == attention_state
                    and item.get("attention_generation") != attention_generation
                ):
                    item["status"] = "superseded"
        if not any(item["dedupe_key"] == payload["dedupe_key"] for item in self.notifications):
            self.notifications.append({
                **deepcopy(payload),
                "attention_state": attention_state,
                "attention_generation": attention_generation,
                "status": "pending",
            })
            return True
        return False

    def supersede_obsolete_notifications(self):
        states = {item["work_order_id"]: item["state"] for item in self.rows}
        changed = 0
        for item in self.notifications:
            if (
                item["status"] in {"pending", "delivering"}
                and item.get("attention_state")
                and states.get(item.get("work_order_id")) != item["attention_state"]
            ):
                item["status"] = "superseded"
                changed += 1
        return changed

    def claim_notification(self):
        return next((item for item in self.notifications if item["status"] == "pending"), None)


def plan(*, plan_id="pm-gh-200"):
    return {
        "plan_id": plan_id,
        "project_id": "demo",
        "ticket": {"id": "GH-5", "title": "Recovery", "description": "bounded"},
        "github_url": "https://github.com/example/repo/issues/5",
        "plan": {"work_orders": [], "decision_boundaries": []},
    }


def row(
    *,
    state="running",
    job_id="job-1",
    execution_mode="agent",
    plan_id="pm-gh-200",
    work_order_id="WO-1",
):
    return {
        "plan_id": plan_id,
        "work_order_id": work_order_id,
        "sequence_no": 0,
        "execution_mode": execution_mode,
        "state": state,
        "job_id": job_id,
        "pr_number": None,
        "pr_url": None,
        "detail": {},
        "updated_at": "t0",
    }


def service(storage, store, controls=None):
    return PlanOrchestrator(storage, FakeEngine(), store=store, controls=controls or FakeControls())


def test_ci_green_pr_transition_notifies_manual_merge_required():
    storage = FakeStorage(
        {
            "job-1": {
                "id": "job-1",
                "status": "completed",
                "result": {
                    "delivery": {
                        "state": "ci_success",
                        "pull_request": {
                            "number": 9,
                            "url": "https://github.com/example/repo/pull/9",
                        },
                    }
                },
                "progress": {},
            }
        }
    )
    store = FakeStore([row()])
    orchestrator = service(storage, store)

    asyncio.run(orchestrator.tick())

    assert store.rows[0]["state"] == "awaiting_merge"
    assert len(store.notifications) == 1
    event = store.notifications[0]
    assert event["event_type"] == "human_decision_required"
    assert event["github_url"] == "https://github.com/example/repo/pull/9"
    assert "manual merge" in event["summary"].lower()
    assert event["payload"]["advisory"]["reason"] == "awaiting_merge"
    assert event["payload"]["actions"][0]["url"].endswith("/pull/9")


def test_quota_exhaustion_notifies_even_when_job_can_keep_running():
    storage = FakeStorage(
        {
            "job-1": {
                "id": "job-1",
                "status": "executing",
                "result": None,
                "progress": {
                    "provider_failures": [
                        {
                            "model": "codex_plus",
                            "provider": "openai",
                            "kind": "quota_exhausted",
                        }
                    ]
                },
            }
        }
    )
    store = FakeStore([row()])
    orchestrator = service(storage, store)

    asyncio.run(orchestrator.tick())
    asyncio.run(orchestrator.tick())

    assert store.rows[0]["state"] == "running"
    assert len(store.notifications) == 1
    event = store.notifications[0]
    assert event["event_type"] == "provider_quota_exhausted"
    assert event["severity"] == "warning"
    assert event["payload"]["actions"] == []
    assert "fallback" in event["payload"]["advisory"]["cause"].lower()


def test_budget_block_transition_emits_diagnostic_and_context_action():
    storage = FakeStorage(
        {
            "job-1": {
                "id": "job-1",
                "status": "blocked",
                "result": {
                    "reason": "execution_budget_exhausted",
                    "last_failure": "model-call budget exhausted",
                },
                "progress": {"model_calls": 10},
            }
        }
    )
    store = FakeStore([row()])
    orchestrator = service(storage, store)

    asyncio.run(orchestrator.tick())

    assert store.rows[0]["state"] == "blocked"
    assert store.plan_status == "blocked"
    assert len(store.notifications) == 1
    event = store.notifications[0]
    assert event["event_type"] == "work_order_blocked"
    assert event["payload"]["advisory"]["reason"] == "execution_budget_exhausted"
    assert event["payload"]["advisory"]["metrics"][0]["used"] == 10
    assert event["payload"]["actions"][0]["callback_data"] == "act:opaque-action-id"


def test_stable_attention_reemits_once_when_action_set_changes():
    storage = FakeStorage(
        {
            "job-1": {
                "id": "job-1",
                "status": "blocked",
                "result": {
                    "reason": "execution_budget_exhausted",
                    "last_failure": "model-call budget exhausted",
                },
                "progress": {"model_calls": 10},
            }
        }
    )
    store = FakeStore([row(state="blocked")])
    store.plan_status = "blocked"
    controls = FakeControls()
    controls.include_budget_action = False
    orchestrator = service(storage, store, controls=controls)
    current = store.work_orders("pm-gh-200")[0]

    orchestrator._emit_attention_for_state(plan(), current, "blocked")
    orchestrator._emit_attention_for_state(plan(), current, "blocked")

    assert len(store.notifications) == 1
    assert [item["action_id"] for item in store.notifications[0]["payload"]["actions"]] == ["details-action"]

    controls.include_budget_action = True
    orchestrator._emit_attention_for_state(plan(), current, "blocked")
    orchestrator._emit_attention_for_state(plan(), current, "blocked")

    assert len(store.notifications) == 2
    assert store.notifications[0]["dedupe_key"] != store.notifications[1]["dedupe_key"]
    assert [item["action_id"] for item in store.notifications[1]["payload"]["actions"]] == [
        "opaque-action-id",
        "details-action",
    ]


def test_action_set_fingerprint_ignores_opaque_action_identity():
    first = [{"label": "Recheck", "action_id": "a-1", "callback_data": "act:a-1"}]
    second = [{"label": "Recheck", "action_id": "a-2", "callback_data": "act:a-2"}]
    changed = [{"label": "Approve", "action_id": "a-2", "callback_data": "act:a-2"}]

    assert PlanOrchestrator._action_set_fingerprint(first) == (
        PlanOrchestrator._action_set_fingerprint(second)
    )
    assert PlanOrchestrator._action_set_fingerprint(first) != (
        PlanOrchestrator._action_set_fingerprint(changed)
    )


def test_operator_block_emits_one_rich_event_without_core_duplicate():
    storage = FakeStorage()
    store = FakeStore([row(state="waiting_human", job_id=None, execution_mode="operator")])
    store.plan_status = "waiting_human"
    orchestrator = service(storage, store)

    result = asyncio.run(
        orchestrator.resolve_operator(
            plan_id="pm-gh-200",
            work_order_id="WO-1",
            action="block",
            note="operator found a recovery mismatch",
        )
    )

    assert result["status"] == "blocked"
    assert store.rows[0]["state"] == "blocked"
    assert len(store.notifications) == 1
    assert store.notifications[0]["event_type"] == "work_order_blocked"
    assert store.notifications[0]["payload"]["advisory"]["reason"] == "operator_blocked"


def test_live_shaped_awaiting_merge_ticks_and_completion_retire_stale_backlog():
    plan_id = "pm-gh-5772402026"
    work_order_id = "UI-CL-1-responsive-regression-matrix-r2"
    job_id = "812aabd7ab0a5adbb18a7a5edc8d7009"
    storage = FakeStorage(
        {
            job_id: {
                "id": job_id,
                "status": "completed",
                "result": {"delivery": {"state": "ci_success"}},
                "progress": {},
            }
        },
        plan_id=plan_id,
    )
    tracked = row(
        state="awaiting_merge",
        job_id=job_id,
        plan_id=plan_id,
        work_order_id=work_order_id,
    )
    tracked.update(
        pr_number=18,
        pr_url="https://github.com/example/chonhac/pull/18",
        detail={"job_id": job_id, "delivery_state": "ci_success"},
    )
    store = FakeStore([tracked], plan_id=plan_id)
    store.plan_status = "waiting_merge"
    controls = FakeControls()
    orchestrator = service(storage, store, controls=controls)

    asyncio.run(orchestrator.tick())
    stable_plan_stamp = store.plan_updated_at
    stable_work_order_stamp = store.rows[0]["updated_at"]
    asyncio.run(orchestrator.tick())
    asyncio.run(orchestrator.tick())

    merge_events = [
        item
        for item in store.notifications
        if (item.get("payload", {}).get("advisory") or {}).get("reason")
        == "awaiting_merge"
    ]
    assert len(merge_events) == 1
    assert controls.created_action_count == 1
    assert store.plan_updated_at == stable_plan_stamp
    assert store.rows[0]["updated_at"] == stable_work_order_stamp

    merge_events[0]["status"] = "sent"
    store.notifications.append(
        {
            **deepcopy(merge_events[0]),
            "dedupe_key": "legacy-pending-awaiting-merge",
            "status": "pending",
        }
    )
    orchestrator.engine.ddev.prs[18] = {
        "number": 18,
        "state": "closed",
        "merged": True,
        "merged_at": "2026-09-24T10:00:00Z",
        "merge_commit_sha": "c" * 40,
    }

    asyncio.run(orchestrator.tick())

    assert store.rows[0]["state"] == "completed"
    assert store.plan_status == "completed"
    assert merge_events[0]["status"] == "sent"
    legacy = next(
        item
        for item in store.notifications
        if item["dedupe_key"] == "legacy-pending-awaiting-merge"
    )
    assert legacy["status"] == "superseded"
    claimed = store.claim_notification()
    assert claimed is not None
    assert claimed["event_type"] == "ticket_completed"
    assert claimed["status"] != "superseded"
    assert {item["status"] for item in controls.actions.values()} == {"cancelled"}
    assert len(store.notifications) == 3  # sent merge, superseded legacy, completion audit


def test_blocked_and_waiting_human_dedupe_are_stable_across_ticks():
    blocked_storage = FakeStorage(
        {
            "job-1": {
                "id": "job-1",
                "status": "blocked",
                "result": {"reason": "reassessment_stopped"},
                "progress": {},
            }
        }
    )
    blocked_store = FakeStore([row(state="blocked")])
    blocked_store.plan_status = "blocked"
    blocked = service(blocked_storage, blocked_store)

    asyncio.run(blocked.tick())
    asyncio.run(blocked.tick())
    assert len(blocked_store.notifications) == 1

    waiting_storage = FakeStorage(
        {
            "job-1": {
                "id": "job-1",
                "status": "waiting_human",
                "result": {"reason": "human_decision_required"},
                "progress": {},
            }
        }
    )
    waiting_store = FakeStore([row(state="waiting_human")])
    waiting_store.plan_status = "waiting_human"
    waiting = service(waiting_storage, waiting_store)

    asyncio.run(waiting.tick())
    asyncio.run(waiting.tick())
    assert len(waiting_store.notifications) == 1


def test_owner_relevant_detail_change_emits_new_generation_and_supersedes_pending_old():
    storage = FakeStorage(
        {
            "job-1": {
                "id": "job-1",
                "status": "blocked",
                "result": {"reason": "reassessment_stopped"},
                "progress": {},
            }
        }
    )
    store = FakeStore([row(state="blocked")])
    store.plan_status = "blocked"
    orchestrator = service(storage, store)
    current = store.work_orders("pm-gh-200")[0]

    orchestrator._emit_attention_for_state(plan(), current, "blocked")
    store.rows[0]["detail"] = {"reason": "new_owner_relevant_reason"}
    changed = store.work_orders("pm-gh-200")[0]
    orchestrator._emit_attention_for_state(plan(), changed, "blocked")

    assert len(store.notifications) == 2
    assert [item["status"] for item in store.notifications] == [
        "superseded",
        "pending",
    ]
