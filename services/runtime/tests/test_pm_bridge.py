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

    def claim(self, project_id, comment_id):
        row = self.rows[(project_id, comment_id)]
        if row["status"] != "accepted_pending_dispatch":
            raise RuntimeError("not dispatchable")
        row["status"] = "dispatching"
        return dict(row)

    def finish(self, *, project_id, comment_id, status, result=None, error=None):
        row = self.rows[(project_id, comment_id)]
        if row["status"] != "dispatching":
            raise RuntimeError("terminal transition rejected")
        row["status"] = status
        row["result"] = result or {}
        row["error"] = error
        return dict(row)


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


def configure(monkeypatch, *, comments=None, issue=None, control_dispatcher=None):
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
            control_dispatcher=control_dispatcher,
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


def test_control_dispatcher_claims_once_and_records_terminal_result(monkeypatch):
    async def dispatcher(envelope, *, comment_id, issue_number):
        assert envelope.action == "request_diagnostics"
        assert comment_id == 200
        assert issue_number == 4
        return "unsupported_action_dispatch", {
            "status": "pending_future_slice",
            "action": envelope.action,
        }

    service, storage, _, _ = configure(
        monkeypatch,
        comments=[control_comment()],
        control_dispatcher=dispatcher,
    )

    first = asyncio.run(service.poll_project("demo"))
    second = asyncio.run(service.poll_project("demo"))

    assert storage.plans == {}
    assert first["controls_dispatched"] == [
        {
            "comment_id": 200,
            "action": "request_diagnostics",
            "status": "unsupported_action_dispatch",
            "result": {
                "status": "pending_future_slice",
                "action": "request_diagnostics",
            },
        }
    ]
    assert service.control_events.rows[("demo", 200)]["status"] == "unsupported_action_dispatch"
    assert second["controls_skipped"] == [200]


def test_control_dispatch_failure_is_terminal_and_not_replayed(monkeypatch):
    calls = []

    async def dispatcher(envelope, *, comment_id, issue_number):
        calls.append(comment_id)
        raise RuntimeError("stale target")

    service, _, _, _ = configure(
        monkeypatch,
        comments=[control_comment()],
        control_dispatcher=dispatcher,
    )

    first = asyncio.run(service.poll_project("demo"))
    second = asyncio.run(service.poll_project("demo"))

    assert calls == [200]
    assert first["controls_failed"][0]["comment_id"] == 200
    assert "stale target" in first["controls_failed"][0]["error"]
    assert service.control_events.rows[("demo", 200)]["status"] == "failed"
    assert second["controls_skipped"] == [200]


# B2.1 source queue: no existing PM plan/control flow may gain new authority.
def _local_source_test_payload(**changes):
    from app.pcp_local_task_queue import MARKER
    import hashlib
    task = {
        "version": 1, "key": "pcp-bounded-source",
        "base_sha": "c" * 40,
        "goal": "Make one small PCP source-only change and include regression tests.",
        "allowed_paths": ["scripts/pcp-light-new.py", "tests/test_pcp_light_new.py"],
        "mode": "github_source_pr_only",
    }
    body = MARKER + "\n" + json.dumps(task)
    source = {
        "project_id": "pcp-local",
        "repository": "sonvhse06072/personal-coding-platform",
        "number": 700, "author": "sonvhse06072", "state": "open",
        "is_pull_request": False,
        "html_url": "https://github.com/sonvhse06072/personal-coding-platform/issues/700",
        "main_sha": "c" * 40, "body": body,
    }
    source.update(changes)
    return source, pm_bridge.LocalSourceCheckRequest(
        project_id="pcp-local", issue_number=700,
        body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        base_sha="c" * 40, baseline_revision="v1",
    )


def test_pcp_source_feature_flag_absent_stops_before_any_git_or_db(monkeypatch):
    from app.pcp_local_task_queue import TaskStop

    monkeypatch.delenv("PCP_LOCAL_TASK_SOURCE_ENABLED", raising=False)
    github = type("GH", (), {
        "local_source_issue": lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("GitHub must remain untouched when OFF"))
    })()
    receipts = type("R", (), {
        "record": lambda *args: (_ for _ in ()).throw(
            AssertionError("Receipts must remain untouched when OFF"))
    })()
    service = pm_bridge.PMBridgeService(
        FakeStorage(), github=github, local_receipts=receipts,
    )
    _, request = _local_source_test_payload()
    with __import__("pytest").raises(TaskStop, match="pcp_local_source_disabled"):
        asyncio.run(service.check_local_source(request))


def test_pcp_source_malformed_flag_denies_without_expanding_permissions(monkeypatch):
    from app.pcp_local_task_queue import TaskStop

    monkeypatch.setenv("PCP_LOCAL_TASK_SOURCE_ENABLED", "true")
    service = pm_bridge.PMBridgeService(FakeStorage())
    _, request = _local_source_test_payload()
    with __import__("pytest").raises(TaskStop, match="pcp_local_source_disabled"):
        asyncio.run(service.check_local_source(request))


def _enabled_pcp_local_service(monkeypatch, *, source_changes=None,
                               registered=True, approved=True):
    from app.pcp_local_task_queue import TaskStop
    monkeypatch.setenv("PCP_LOCAL_TASK_SOURCE_ENABLED", "owner-approved")

    project_calls = []
    def fake_project(project_id):
        project_calls.append(project_id)
        return {"base_branch": "main" if registered else "develop",
                "path": "/fresh/pcp-source"}

    def fake_baseline(project_id, revision=None):
        if not approved:
            return None
        return baseline().model_copy(update={"project_id": "pcp-local"})

    monkeypatch.setattr(pm_bridge, "project_config", fake_project)
    monkeypatch.setattr(pm_bridge, "resolve_project_baseline", fake_baseline)

    source, payload = _local_source_test_payload(**(source_changes or {}))
    github_calls = []
    async def fetch(*, issue_number):
        github_calls.append(issue_number)
        return source

    gh = type("GH", (), {"local_source_issue": staticmethod(fetch)})()

    class Receipts:
        def __init__(self):
            self.seen = set()
            self.calls = []
        def record(self, task):
            self.calls.append(task)
            key = (task.repository, task.issue_number, task.body_sha256)
            if key in self.seen:
                return False
            self.seen.add(key)
            return True

    receipts = Receipts()
    service = pm_bridge.PMBridgeService(
        FakeStorage(), github=gh, local_receipts=receipts
    )
    return service, payload, github_calls, project_calls, receipts


def test_pcp_local_source_contract_records_only_pending_without_job(monkeypatch):
    service, payload, github_calls, project_calls, receipts = (
        _enabled_pcp_local_service(monkeypatch)
    )
    result = asyncio.run(service.check_local_source(payload))
    assert result["status"] == "SOURCE_RECORDED_NOT_DISPATCHED"
    assert result["new_receipt"] is True
    assert result["queue_state"] == "pending"
    assert result["worker_enabled"] is False
    assert result["can_publish_or_merge"] is False
    assert result["model_calls"] == 0
    assert github_calls == [700]
    assert project_calls == ["pcp-local"]
    assert len(receipts.calls) == 1
    assert receipts.calls[0].baseline_source_commit == "a" * 40


def test_pcp_local_source_duplicate_does_not_claim_another_job(monkeypatch):
    service, payload, _, _, receipts = _enabled_pcp_local_service(monkeypatch)
    assert asyncio.run(service.check_local_source(payload))["new_receipt"] is True
    again = asyncio.run(service.check_local_source(payload))
    assert again["new_receipt"] is False
    assert again["model_calls"] == 0
    assert len(receipts.seen) == 1


def test_pcp_local_source_foreign_origin_denied_before_durable_write(monkeypatch):
    from app.pcp_local_task_queue import TaskStop
    service, payload, gh_calls, _, receipts = _enabled_pcp_local_service(
        monkeypatch, source_changes={"repository": "sonvhse06072/chonhac"}
    )
    with __import__("pytest").raises(TaskStop, match="github_identity_or_main_changed"):
        asyncio.run(service.check_local_source(payload))
    assert gh_calls == [700]
    assert receipts.calls == []


def test_pcp_local_source_requires_registered_main_and_approved_baseline(monkeypatch):
    from app.pcp_local_task_queue import TaskStop
    service, payload, gh_calls, _, receipts = _enabled_pcp_local_service(
        monkeypatch, registered=False
    )
    with __import__("pytest").raises(TaskStop, match="pcp_local_project_not_approved"):
        asyncio.run(service.check_local_source(payload))
    assert not gh_calls and not receipts.calls
    service, payload, gh_calls, _, receipts = _enabled_pcp_local_service(
        monkeypatch, approved=False
    )
    with __import__("pytest").raises(TaskStop, match="pcp_local_baseline_not_approved"):
        asyncio.run(service.check_local_source(payload))
    assert not gh_calls and not receipts.calls


def test_pcp_local_source_stale_head_and_pr_metadata_never_record(monkeypatch):
    from app.pcp_local_task_queue import TaskStop
    for changes in ({"main_sha": "d" * 40}, {"is_pull_request": True},
                    {"state": "closed"}, {"author": "foreign"}):
        service, payload, _, _, receipts = _enabled_pcp_local_service(
            monkeypatch, source_changes=changes
        )
        with __import__("pytest").raises(TaskStop):
            asyncio.run(service.check_local_source(payload))
        assert receipts.calls == []


# B2.2b discovery through existing PM Bridge is read-only and NOT intake.
def test_pcp_local_candidates_only_when_source_opted_in(monkeypatch):
    from app.pcp_local_task_queue import TaskStop
    monkeypatch.delenv("PCP_LOCAL_TASK_SOURCE_ENABLED", raising=False)
    monkeypatch.setattr(
        pm_bridge, "project_config",
        lambda _: (_ for _ in ()).throw(AssertionError("registry touched")),
    )
    service = pm_bridge.PMBridgeService(FakeStorage())
    with __import__("pytest").raises(TaskStop, match="pcp_local_source_disabled"):
        asyncio.run(service.preview_local_candidates())
    monkeypatch.setenv("PCP_LOCAL_TASK_SOURCE_ENABLED", "true")
    with __import__("pytest").raises(TaskStop, match="pcp_local_source_disabled"):
        asyncio.run(service.preview_local_candidates())


def _pcp_local_discovery(monkeypatch, result=None):
    monkeypatch.setenv("PCP_LOCAL_TASK_SOURCE_ENABLED", "owner-approved")
    monkeypatch.setattr(
        pm_bridge, "project_config",
        lambda _: {"base_branch": "main", "path": "/isolated/pcp-local"},
    )
    sample = {
        "project_id": "pcp-local",
        "repository": "sonvhse06072/personal-coding-platform",
        "main_sha": "a" * 40, "can_dispatch": False,
        "candidates": [{
            "number": 778, "body_sha256": "b" * 64,
            "html_url": "https://github.com/sonvhse06072/personal-coding-platform/issues/778",
            "status": "UNTRUSTED_CANDIDATE_NOT_AUTHORIZED",
        }],
    }
    if result is not None:
        sample.update(result)

    class GitHub:
        def __init__(self):
            self.calls = []
        async def local_source_candidates(self, *, per_page):
            self.calls.append(per_page)
            return sample

    gh = GitHub()
    service = pm_bridge.PMBridgeService(FakeStorage(), github=gh)
    return service, gh


def test_pcp_candidate_metadata_is_not_an_approved_job(monkeypatch):
    service, gh = _pcp_local_discovery(monkeypatch)
    out = asyncio.run(service.preview_local_candidates(per_page=5))
    assert out == {
        "status": "PCP_LOCAL_CANDIDATES_NOT_ADMITTED",
        "main_sha": "a" * 40,
        "candidates": [{
            "number": 778, "body_sha256": "b" * 64,
            "html_url": "https://github.com/sonvhse06072/personal-coding-platform/issues/778",
            "status": "UNTRUSTED_CANDIDATE_NOT_AUTHORIZED",
        }],
        "can_dispatch": False,
    }
    assert gh.calls == [5]
    assert "body" not in out and "goal" not in out


def test_candidate_discovery_needs_registered_main_project(monkeypatch):
    from app.pcp_local_task_queue import TaskStop
    monkeypatch.setenv("PCP_LOCAL_TASK_SOURCE_ENABLED", "owner-approved")
    monkeypatch.setattr(pm_bridge, "project_config",
                        lambda _: {"base_branch": "develop"})
    service = pm_bridge.PMBridgeService(FakeStorage())
    with __import__("pytest").raises(TaskStop, match="pcp_local_project_not_approved"):
        asyncio.run(service.preview_local_candidates())


def test_candidate_discovery_limit_rejects_malformed_before_api(monkeypatch):
    from app.pcp_local_task_queue import TaskStop
    service, gh = _pcp_local_discovery(monkeypatch)
    for limit in (0, 11, True, "10"):
        with __import__("pytest").raises(TaskStop, match="pcp_local_candidates_limit_invalid"):
            asyncio.run(service.preview_local_candidates(per_page=limit))
    assert gh.calls == []


def test_candidate_discovery_does_not_trust_foreign_repo_or_permission(monkeypatch):
    from app.pcp_local_task_queue import TaskStop
    for bad in ({"repository": "sonvhse06072/chonhac"},
                {"can_dispatch": True},
                {"project_id": "chonhac"}):
        service, gh = _pcp_local_discovery(monkeypatch, result=bad)
        with __import__("pytest").raises(TaskStop, match="pcp_local_candidates_invalid"):
            asyncio.run(service.preview_local_candidates())
        assert gh.calls == [10]


def test_candidate_discovery_denies_forged_candidate_metadata(monkeypatch):
    from app.pcp_local_task_queue import TaskStop
    bad = {"candidates": [{
        "number": 778, "body_sha256": "b" * 64,
        "html_url": "https://github.com/sonvhse06072/chonhac/issues/778",
        "status": "UNTRUSTED_CANDIDATE_NOT_AUTHORIZED",
    }]}
    service, gh = _pcp_local_discovery(monkeypatch, result=bad)
    with __import__("pytest").raises(TaskStop, match="pcp_local_candidate_identity_invalid"):
        asyncio.run(service.preview_local_candidates())


def test_pcp_candidate_hex_identity_denied(monkeypatch):
    from app.pcp_local_task_queue import TaskStop
    for change in (
        {"main_sha": "g" * 40},
        {"candidates": [{
            "number": 778, "body_sha256": "z" * 64,
            "html_url": "https://github.com/sonvhse06072/personal-coding-platform/issues/778",
            "status": "UNTRUSTED_CANDIDATE_NOT_AUTHORIZED",
        }]},
    ):
        service, _ = _pcp_local_discovery(monkeypatch, result=change)
        with __import__("pytest").raises(TaskStop):
            asyncio.run(service.preview_local_candidates())
