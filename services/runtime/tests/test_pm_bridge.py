from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from app import pm_bridge
from app.baseline import BaselineReferences, ProjectBaseline, SourceReference
from app.pm_bridge import DEFAULT_MARKER, PMBridgeService
from app.pm_control import CONTROL_MARKER


class FakeStorage:
    def __init__(self):
        self.plans = {}

    def get_execution_plan(self, plan_id):
        return self.plans.get(plan_id)

    def create_execution_plan(self, row):
        now = datetime.now(timezone.utc)
        self.plans[row["id"]] = {**row, "created_at": now, "updated_at": now}


class FakeEvents:
    def __init__(self):
        self.rows = {}

    def get(self, project_id, comment_id):
        return self.rows.get((project_id, comment_id))

    def record(self, **row):
        self.rows.setdefault((row["project_id"], row["comment_id"]), dict(row))


class FakeControlEvents:
    def __init__(self):
        self.rows = {}

    def get(self, project_id, comment_id):
        return self.rows.get((project_id, comment_id))

    def record(self, **row):
        self.rows.setdefault(
            (row["project_id"], row["comment_id"]),
            dict(row),
        )


class FakeGitHub:
    def __init__(self, comments, issue):
        self.comments = comments
        self.issue_payload = issue
        self.issue_calls = []

    async def recent_comments(self, *, project_id, per_page):
        return {"project_id": project_id, "repository": "example/chonhac", "comments": self.comments}

    async def issue(self, *, project_id, issue_number):
        self.issue_calls.append((project_id, issue_number))
        return {**self.issue_payload, "project_id": project_id, "repository": "example/chonhac", "number": issue_number}


def baseline():
    ref = [SourceReference(path="docs/scope.md")]
    return ProjectBaseline(
        project_id="demo",
        revision="v1",
        source_commit="a" * 40,
        references=BaselineReferences(
            goals=ref,
            non_goals=ref,
            requirements=ref,
            architecture_constraints=ref,
            quality_policy=ref,
            security_policy=ref,
            budget_policy=ref,
            roadmap_frame=ref,
        ),
    )


def project():
    return {
        "ddev": {
            "enabled": True,
            "targeted_tests": ["test-targeted"],
            "static_analysis": ["test-static"],
            "full_tests": [],
        }
    }


def proposal(parent_ticket="GH-4"):
    return {
        "scope_assessment": "in_scope",
        "summary": "Implement the bounded approved work.",
        "work_orders": [
            {
                "id": "WO-1",
                "parent_ticket": parent_ticket,
                "objective": "Collect bounded evidence",
                "baseline_revision": "v1",
                "source_references": [{"path": "docs/scope.md"}],
                "in_scope": ["bounded evidence"],
                "out_of_scope": ["unrelated work"],
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "Evidence is deterministic and cleaned up"}
                ],
                "constraints": ["Do not expand scope"],
                "requested_role": "backend_developer",
                "verification": {"required_phases": ["targeted_tests"]},
                "risk": {"level": "standard", "flags": []},
                "budget": {
                    "max_profile": "standard",
                    "max_model_calls": 4,
                    "max_repair_iterations": 1,
                    "max_wall_time_minutes": 20,
                    "max_changed_files": 8,
                },
                "dependencies": [],
            }
        ],
        "decision_boundaries": [],
    }


def comment(comment_id=100, *, author="owner", payload=None):
    envelope = {
        "schema_version": 1,
        "baseline_revision": "v1",
        "proposal": payload or proposal(),
    }
    return {
        "id": comment_id,
        "issue_number": 4,
        "author": author,
        "body": DEFAULT_MARKER + "\n```json\n" + json.dumps(envelope) + "\n```",
        "html_url": f"https://github.com/example/chonhac/issues/4#issuecomment-{comment_id}",
    }



def control_comment(
    comment_id=200,
    *,
    author="owner",
    envelope=None,
):
    payload = envelope or {
        "schema_version": 1,
        "project_id": "demo",
        "action": "request_diagnostics",
        "job_id": "job-0001",
        "diagnostic_collectors": ["job", "runtime_health"],
    }
    return {
        "id": comment_id,
        "issue_number": 4,
        "author": author,
        "body": CONTROL_MARKER + "\n" + json.dumps(payload),
        "html_url": (
            "https://github.com/example/chonhac/issues/4"
            f"#issuecomment-{comment_id}"
        ),
    }


def configure(monkeypatch, *, comments=None, issue=None):
    monkeypatch.setattr(
        pm_bridge,
        "bridge_project_config",
        lambda project_id: {
            "enabled": True,
            "allowed_authors": ["owner"],
            "marker": DEFAULT_MARKER,
            "max_comments_per_poll": 100,
        },
    )
    monkeypatch.setattr(pm_bridge, "project_config", lambda project_id: project())
    monkeypatch.setattr(pm_bridge, "resolve_project_baseline", lambda project_id, revision=None: baseline())
    storage = FakeStorage()
    events = FakeEvents()
    control_events = FakeControlEvents()
    github = FakeGitHub(
        comments or [comment()],
        issue or {
            "title": "Canonical GitHub title",
            "body": "Canonical GitHub issue body",
            "state": "open",
            "html_url": "https://github.com/example/chonhac/issues/4",
            "is_pull_request": False,
        },
    )
    return (
        PMBridgeService(
            storage,
            github=github,
            events=events,
            control_events=control_events,
        ),
        storage,
        events,
        github,
    )


def test_bridge_accepts_valid_plan_and_uses_canonical_github_ticket(monkeypatch):
    service, storage, events, github = configure(monkeypatch)

    result = asyncio.run(service.poll_project("demo"))

    assert result["accepted"] == [{"comment_id": 100, "plan_id": "pm-gh-100", "status": "ready"}]
    row = storage.plans["pm-gh-100"]
    assert row["ticket"] == {
        "id": "GH-4",
        "title": "Canonical GitHub title",
        "description": "Canonical GitHub issue body",
    }
    assert row["staffing"]["mode"] == "external"
    assert row["staffing"]["role"] == "product_manager"
    assert row["usage"] == {"model_calls": 0, "external_pm": True}
    assert events.rows[("demo", 100)]["status"] == "accepted"
    assert github.issue_calls == [("demo", 4)]


def test_bridge_rejects_unauthorized_author_without_plan(monkeypatch):
    service, storage, events, github = configure(monkeypatch, comments=[comment(author="intruder")])

    result = asyncio.run(service.poll_project("demo"))

    assert storage.plans == {}
    assert result["accepted"] == []
    assert result["rejected"][0]["comment_id"] == 100
    assert "not allowed" in result["rejected"][0]["error"]
    assert events.rows[("demo", 100)]["status"] == "rejected"
    assert github.issue_calls == []


def test_bridge_rejects_malformed_payload_once(monkeypatch):
    bad = comment()
    bad["body"] = DEFAULT_MARKER + "\n{not-json"
    service, storage, events, _ = configure(monkeypatch, comments=[bad])

    first = asyncio.run(service.poll_project("demo"))
    second = asyncio.run(service.poll_project("demo"))

    assert storage.plans == {}
    assert first["rejected"][0]["comment_id"] == 100
    assert second["skipped"] == [100]
    assert len(events.rows) == 1


def test_bridge_poll_is_idempotent_by_comment_id(monkeypatch):
    service, storage, events, _ = configure(monkeypatch)

    first = asyncio.run(service.poll_project("demo"))
    second = asyncio.run(service.poll_project("demo"))

    assert first["accepted"][0]["plan_id"] == "pm-gh-100"
    assert second["accepted"] == []
    assert second["skipped"] == [100]
    assert list(storage.plans) == ["pm-gh-100"]
    assert len(events.rows) == 1


def test_bridge_rejects_plan_that_rebinds_parent_ticket(monkeypatch):
    service, storage, events, _ = configure(
        monkeypatch,
        comments=[comment(payload=proposal(parent_ticket="GH-999"))],
    )

    result = asyncio.run(service.poll_project("demo"))

    assert storage.plans == {}
    assert "must set parent_ticket to 'GH-4'" in result["rejected"][0]["error"]
    assert events.rows[("demo", 100)]["status"] == "rejected"


def test_control_accepts_valid_command_without_mutating_plan(monkeypatch):
    service, storage, _, github = configure(
        monkeypatch,
        comments=[control_comment()],
    )

    result = asyncio.run(service.poll_project("demo"))

    assert storage.plans == {}
    assert result["accepted"] == []
    assert result["controls_accepted"] == [
        {
            "comment_id": 200,
            "action": "request_diagnostics",
            "status": "accepted_pending_dispatch",
            "target_identity": {"job_id": "job-0001"},
        }
    ]
    row = service.control_events.rows[("demo", 200)]
    assert row["status"] == "accepted_pending_dispatch"
    assert row["action"] == "request_diagnostics"
    assert row["target_identity"] == {"job_id": "job-0001"}
    assert github.issue_calls == [("demo", 4)]


def test_control_rejects_unauthorized_author_before_issue_read(monkeypatch):
    service, storage, _, github = configure(
        monkeypatch,
        comments=[control_comment(author="intruder")],
    )

    result = asyncio.run(service.poll_project("demo"))

    assert storage.plans == {}
    assert result["controls_accepted"] == []
    assert result["controls_rejected"][0]["comment_id"] == 200
    assert "not allowed" in result["controls_rejected"][0]["error"]
    assert service.control_events.rows[("demo", 200)]["status"] == "rejected"
    assert github.issue_calls == []


def test_control_comment_is_consumed_once(monkeypatch):
    service, storage, _, _ = configure(
        monkeypatch,
        comments=[control_comment()],
    )

    first = asyncio.run(service.poll_project("demo"))
    second = asyncio.run(service.poll_project("demo"))

    assert storage.plans == {}
    assert first["controls_accepted"][0]["comment_id"] == 200
    assert second["controls_accepted"] == []
    assert second["controls_skipped"] == [200]
    assert len(service.control_events.rows) == 1


def test_control_rejects_mixed_plan_and_control_markers(monkeypatch):
    mixed = control_comment()
    mixed["body"] = (
        DEFAULT_MARKER
        + "\n"
        + CONTROL_MARKER
        + "\n"
        + json.dumps(
            {
                "schema_version": 1,
                "project_id": "demo",
                "action": "request_diagnostics",
                "job_id": "job-0001",
                "diagnostic_collectors": ["job"],
            }
        )
    )
    service, storage, _, github = configure(
        monkeypatch,
        comments=[mixed],
    )

    result = asyncio.run(service.poll_project("demo"))

    assert storage.plans == {}
    assert result["controls_accepted"] == []
    assert "cannot mix plan and control markers" in result["controls_rejected"][0]["error"]
    assert service.control_events.rows[("demo", 200)]["status"] == "rejected"
    assert github.issue_calls == []


def test_control_rejects_extra_fields_and_missing_target(monkeypatch):
    extra = control_comment(
        comment_id=201,
        envelope={
            "schema_version": 1,
            "project_id": "demo",
            "action": "request_diagnostics",
            "job_id": "job-0001",
            "diagnostic_collectors": ["job"],
            "shell": "rm -rf /",
        },
    )
    missing = control_comment(
        comment_id=202,
        envelope={
            "schema_version": 1,
            "project_id": "demo",
            "action": "request_diagnostics",
            "diagnostic_collectors": ["job"],
        },
    )
    service, storage, _, github = configure(
        monkeypatch,
        comments=[extra, missing],
    )

    result = asyncio.run(service.poll_project("demo"))

    assert storage.plans == {}
    assert result["controls_accepted"] == []
    assert {item["comment_id"] for item in result["controls_rejected"]} == {
        201,
        202,
    }
    assert service.control_events.rows[("demo", 201)]["status"] == "rejected"
    assert service.control_events.rows[("demo", 202)]["status"] == "rejected"
    assert github.issue_calls == []


def test_control_rejects_wrong_project_and_oversized_body(monkeypatch):
    wrong_project = control_comment(
        comment_id=203,
        envelope={
            "schema_version": 1,
            "project_id": "other-project",
            "action": "request_diagnostics",
            "job_id": "job-0001",
            "diagnostic_collectors": ["job"],
        },
    )
    oversized = control_comment(comment_id=204)
    oversized["body"] = CONTROL_MARKER + "\n" + ("x" * 65536)

    service, storage, _, github = configure(
        monkeypatch,
        comments=[wrong_project, oversized],
    )

    result = asyncio.run(service.poll_project("demo"))

    assert storage.plans == {}
    assert result["controls_accepted"] == []
    assert {item["comment_id"] for item in result["controls_rejected"]} == {
        203,
        204,
    }
    assert "must match the polled project" in next(
        item["error"]
        for item in result["controls_rejected"]
        if item["comment_id"] == 203
    )
    assert "exceeds 64 KiB" in next(
        item["error"]
        for item in result["controls_rejected"]
        if item["comment_id"] == 204
    )
    assert github.issue_calls == []


def test_control_rejects_closed_issue_and_pull_request(monkeypatch):
    closed_service, closed_storage, _, _ = configure(
        monkeypatch,
        comments=[control_comment(comment_id=205)],
        issue={
            "title": "Closed control issue",
            "body": "closed",
            "state": "closed",
            "html_url": "https://github.com/example/chonhac/issues/4",
            "is_pull_request": False,
        },
    )
    closed = asyncio.run(closed_service.poll_project("demo"))

    assert closed_storage.plans == {}
    assert closed["controls_accepted"] == []
    assert "open GitHub issues" in closed["controls_rejected"][0]["error"]

    pr_service, pr_storage, _, _ = configure(
        monkeypatch,
        comments=[control_comment(comment_id=206)],
        issue={
            "title": "PR conversation",
            "body": "pr",
            "state": "open",
            "html_url": "https://github.com/example/chonhac/pull/4",
            "is_pull_request": True,
        },
    )
    pull = asyncio.run(pr_service.poll_project("demo"))

    assert pr_storage.plans == {}
    assert pull["controls_accepted"] == []
    assert "not pull requests" in pull["controls_rejected"][0]["error"]


def test_control_rejects_duplicate_control_marker(monkeypatch):
    duplicated = control_comment(comment_id=207)
    duplicated["body"] = (
        CONTROL_MARKER
        + "\n"
        + CONTROL_MARKER
        + "\n"
        + json.dumps(
            {
                "schema_version": 1,
                "project_id": "demo",
                "action": "request_diagnostics",
                "job_id": "job-0001",
                "diagnostic_collectors": ["job"],
            }
        )
    )

    service, storage, _, github = configure(
        monkeypatch,
        comments=[duplicated],
    )
    result = asyncio.run(service.poll_project("demo"))

    assert storage.plans == {}
    assert result["controls_accepted"] == []
    assert "exactly one versioned control marker" in result["controls_rejected"][0]["error"]
    assert github.issue_calls == []
