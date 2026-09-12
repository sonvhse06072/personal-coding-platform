from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from app import pm_bridge
from app.baseline import BaselineReferences, ProjectBaseline, SourceReference
from app.pm_bridge import DEFAULT_MARKER, PMBridgeService


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
    return PMBridgeService(storage, github=github, events=events), storage, events, github


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
