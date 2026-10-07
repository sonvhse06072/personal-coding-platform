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
    def standalone_remote_actions(self, job_id):
        assert job_id == JOB_ID
        return {
            "job_id": job_id,
            "generation": "generation-exact",
            "reason": "reassessment_stopped",
            "phase": "reassessment",
            "actions": [
                {
                    "action_type": "pm_scope_reassess",
                    "label": "PM review file scope",
                }
            ],
        }


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
