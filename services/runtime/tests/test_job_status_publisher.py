from __future__ import annotations

import asyncio
from copy import deepcopy

from app.job_status_publisher import JobStatusPublisher


JOB_ID = "job-remote-12345678"


def remote_job():
    return {
        "id": JOB_ID,
        "project_id": "demo",
        "status": "blocked",
        "source_commit": "a" * 40,
        "branch": "ai/job-remote",
        "route": {"strategy": {"profile": "fast"}},
        "progress": {"model_calls": 3, "changed_files": 4},
        "checkpoint": {
            "project_baseline": {"revision": "v1"},
            "canonical_intake": {
                "mode": "direct",
                "bounded_direct": True,
            },
            "github_pm_binding": {
                "transport": "github_pm_control",
                "repository": "owner/demo",
                "issue_number": 77,
                "control_comment_id": 555,
            },
        },
        "result": {
            "reason": "reassessment_stopped",
            "last_failure": "SECRET raw failure /private/path",
            "reassess": {
                "action": "stop",
                "reason": "scope expansion",
                "signals": ["scope_expansion"],
            },
            "delivery": {"state": None, "ci": {}, "pull_request": {}},
        },
    }


class FakeStorage:
    def __init__(self, jobs):
        self.jobs = jobs

    def list(self, limit=200):
        return deepcopy(self.jobs[:limit])


class FakeControls:
    def __init__(self):
        self.generation = "generation-exact"

    def standalone_remote_actions(self, job_id):
        assert job_id == JOB_ID
        return {
            "job_id": job_id,
            "generation": self.generation,
            "reason": "reassessment_stopped",
            "phase": "reassessment",
            "actions": [
                {
                    "action_type": "pm_scope_reassess",
                    "label": "PM review file scope",
                }
            ],
        }

    def blocked_advisory(self, work_order, job):
        assert work_order == {}
        return {
            "title": "WORKORDER BỊ CHẶN",
            "phase": "reassessment",
            "reason": str((job.get("result") or {}).get("reason") or "blocked"),
            "summary": "Runtime không cho phép tiếp tục sau reassessment.",
            "cause": "Trạng thái hiện tại không cho phép tự động tiếp tục.",
            "preserved": ["legacy wording"],
            "impact": "legacy wording",
            "recommended": "Kiểm tra blocker hiện tại.",
            "metrics": [],
            "action_specs": [
                {
                    "action_type": "pm_scope_reassess",
                    "label": "PM review file scope",
                    "payload": {},
                }
            ],
        }


class FakeNotificationStore:
    def __init__(self, *, fail=False):
        self.events = []
        self.supersede_calls = []
        self.fail = fail

    def supersede_standalone_notifications(
        self,
        job_id,
        *,
        except_generation=None,
    ):
        if self.fail:
            raise RuntimeError("notification store unavailable")
        self.supersede_calls.append((job_id, except_generation))
        changed = 0
        for event in self.events:
            payload = event.get("payload") or {}
            if (
                event["status"] in {"pending", "delivering"}
                and payload.get("standalone_job_id") == job_id
                and (
                    except_generation is None
                    or payload.get("attention_generation") != except_generation
                )
            ):
                event["status"] = "superseded"
                changed += 1
        return changed

    def emit_notification(self, **kwargs):
        if self.fail:
            raise RuntimeError("notification store unavailable")
        if any(event["dedupe_key"] == kwargs["dedupe_key"] for event in self.events):
            return False
        payload = deepcopy(kwargs.get("payload") or {})
        if kwargs.get("attention_state") and kwargs.get("attention_generation"):
            payload["attention_state"] = kwargs["attention_state"]
            payload["attention_generation"] = kwargs["attention_generation"]
        self.events.append({**deepcopy(kwargs), "payload": payload, "status": "pending"})
        return True


class FakeStore:
    def __init__(self):
        self.pending = None
        self.staged = []
        self.acked = []
        self.released = []

    def ensure(self):
        pass

    def stage(self, job, *, body, issue_number):
        self.staged.append((job["id"], body, issue_number))
        self.pending = {
            "job_id": job["id"],
            "project_id": job["project_id"],
            "issue_number": issue_number,
            "desired_body": body,
            "desired_sha256": "hash",
            "comment_id": None,
            "attempts": 1,
        }
        return True

    def claim(self):
        value = self.pending
        self.pending = None
        return value

    def ack(self, claim, comment_id):
        self.acked.append((claim["job_id"], comment_id))
        return True

    def release(self, claim, error):
        self.released.append((claim["job_id"], type(error).__name__))
        return True


class FakeExecutor:
    def __init__(self):
        self.requests = []

    async def upsert_managed_comment(self, **kwargs):
        self.requests.append(kwargs)
        return {
            "comment_id": 900,
            "comment_url": "https://github.com/owner/demo/issues/77#issuecomment-900",
            "state": "created",
        }


def test_blocked_standalone_job_materializes_one_sanitized_telegram_generation():
    storage = FakeStorage([remote_job()])
    notifications = FakeNotificationStore()
    controls = FakeControls()
    publisher = JobStatusPublisher(
        storage,
        FakeExecutor(),
        controls,
        store=FakeStore(),
        notification_store=notifications,
    )

    publisher.stage_all()
    publisher.stage_all()

    assert len(notifications.events) == 1
    event = notifications.events[0]
    assert event["event_type"] == "standalone_job_blocked"
    assert event["project_id"] == "demo"
    assert event["ticket_id"] == "GH-77"
    assert event["plan_id"] is None
    assert event["work_order_id"] is None
    assert event["github_url"] == "https://github.com/owner/demo/issues/77"
    assert event["payload"]["job_id"] == JOB_ID
    assert event["payload"]["standalone_job_id"] == JOB_ID
    assert event["payload"]["attention_state"] == "blocked"
    assert event["payload"]["attention_generation"] == "generation-exact"
    assert event["payload"]["actions"] == []
    assert event["payload"]["remote_actions"] == [
        {
            "action_type": "pm_scope_reassess",
            "label": "PM review file scope",
        }
    ]
    advisory = event["payload"]["advisory"]
    assert advisory["title"] == "STANDALONE JOB BỊ CHẶN"
    assert "Standalone job" in advisory["impact"]
    assert "SECRET raw failure" not in repr(event)
    assert "/private/path" not in repr(event)


def test_changed_standalone_blocker_generation_supersedes_pending_old_notification():
    storage = FakeStorage([remote_job()])
    notifications = FakeNotificationStore()
    controls = FakeControls()
    publisher = JobStatusPublisher(
        storage,
        FakeExecutor(),
        controls,
        store=FakeStore(),
        notification_store=notifications,
    )

    publisher.stage_all()
    controls.generation = "generation-next"
    publisher.stage_all()

    assert len(notifications.events) == 2
    assert [event["status"] for event in notifications.events] == [
        "superseded",
        "pending",
    ]
    assert notifications.events[1]["payload"]["attention_generation"] == "generation-next"


def test_leaving_standalone_blocker_supersedes_pending_notification():
    storage = FakeStorage([remote_job()])
    notifications = FakeNotificationStore()
    publisher = JobStatusPublisher(
        storage,
        FakeExecutor(),
        FakeControls(),
        store=FakeStore(),
        notification_store=notifications,
    )

    publisher.stage_all()
    storage.jobs[0]["status"] = "executing"
    publisher.stage_all()

    assert [event["status"] for event in notifications.events] == ["superseded"]
    assert notifications.supersede_calls[-1] == (JOB_ID, None)


def test_notification_materialization_failure_does_not_block_github_status_publication():
    store = FakeStore()
    executor = FakeExecutor()
    publisher = JobStatusPublisher(
        FakeStorage([remote_job()]),
        executor,
        FakeControls(),
        store=store,
        notification_store=FakeNotificationStore(fail=True),
    )

    worked = asyncio.run(publisher.publish_one())

    assert worked is True
    assert store.acked == [(JOB_ID, 900)]
    assert len(executor.requests) == 1


def test_remote_bound_blocked_job_publishes_exact_safe_recovery_status():
    store = FakeStore()
    executor = FakeExecutor()
    publisher = JobStatusPublisher(
        FakeStorage([remote_job()]),
        executor,
        FakeControls(),
        store=store,
    )

    worked = asyncio.run(publisher.publish_one())

    assert worked is True
    assert store.acked == [(JOB_ID, 900)]
    assert len(executor.requests) == 1
    request = executor.requests[0]
    assert request["project_id"] == "demo"
    assert request["issue_number"] == 77
    assert request["channel"] == "job_status"
    assert request["identity"] == f"job:{JOB_ID}"
    body = request["body"]
    assert "reassessment_stopped" in body
    assert "generation-exact" in body
    assert "pm_scope_reassess" in body
    assert "SECRET raw failure" not in body
    assert "/private/path" not in body


def test_unbound_job_is_never_staged_or_published():
    job = remote_job()
    job["checkpoint"].pop("github_pm_binding")
    store = FakeStore()
    executor = FakeExecutor()
    publisher = JobStatusPublisher(
        FakeStorage([job]),
        executor,
        FakeControls(),
        store=store,
    )

    assert asyncio.run(publisher.publish_one()) is False
    assert store.staged == []
    assert executor.requests == []
