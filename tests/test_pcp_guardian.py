from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pcp_guardian.py"
SPEC = importlib.util.spec_from_file_location("pcp_guardian", SCRIPT)
assert SPEC and SPEC.loader
guardian = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guardian)


MARKER = "<!-- coding-platform:pcp-guardian:v1 -->"
SHA = "a" * 40


def config(tmp_path: Path) -> dict:
    return {
        "schema_version": 1,
        "repository": "sonvhse06072/personal-coding-platform",
        "allowed_actor": "sonvhse06072",
        "control_issue_number": 524,
        "default_branch": "main",
        "pcp_root": str(tmp_path / "pcp"),
        "marker": MARKER,
        "max_comment_bytes": 16384,
        "state_dir": str(tmp_path / "state"),
    }


def event(payload: dict | None = None, **overrides) -> dict:
    payload = payload or {"schema_version": 1, "action": "status_snapshot"}
    value = {
        "action": "created",
        "repository": {
            "full_name": "sonvhse06072/personal-coding-platform",
            "default_branch": "main",
        },
        "issue": {
            "number": 524,
            "state": "open",
        },
        "comment": {
            "id": 12345,
            "user": {"login": "sonvhse06072"},
            "body": MARKER + "\n" + json.dumps(payload),
        },
    }
    value.update(overrides)
    return value


def test_status_rollout_and_bridge_recovery_commands_are_exact(tmp_path):
    cfg = config(tmp_path)

    status = guardian.parse_command(event(), cfg)
    assert status["action"] == "status_snapshot"
    assert status["comment_id"] == 12345
    assert len(status["body_sha256"]) == 64

    rollout = guardian.parse_command(
        event(
            {
                "schema_version": 1,
                "action": "rollout_pcp_exact_main",
                "expected_main_sha": SHA,
            }
        ),
        cfg,
    )
    assert rollout["expected_main_sha"] == SHA

    recovery = guardian.parse_command(
        event(
            {
                "schema_version": 1,
                "action": "recover_antigravity_bridge",
            }
        ),
        cfg,
    )
    assert recovery["action"] == "recover_antigravity_bridge"

    bridge_snapshot = guardian.parse_command(
        event(
            {
                "schema_version": 1,
                "action": "pm_bridge_snapshot",
                "project_id": "chonhac",
                "target_comment_id": 6031547665,
            }
        ),
        cfg,
    )
    assert bridge_snapshot["project_id"] == "chonhac"
    assert bridge_snapshot["target_comment_id"] == 6031547665
    assert bridge_snapshot["comment_id"] == 12345

    bridge_poll = guardian.parse_command(
        event(
            {
                "schema_version": 1,
                "action": "pm_bridge_poll_project_once",
                "project_id": "chonhac",
            }
        ),
        cfg,
    )
    assert bridge_poll["project_id"] == "chonhac"


@pytest.mark.parametrize(
    "mutator,match",
    [
        (
            lambda e: e["comment"]["user"].update(login="intruder"),
            "author",
        ),
        (
            lambda e: e["issue"].update(number=999),
            "issue identity",
        ),
        (
            lambda e: e["issue"].update(pull_request={"url": "x"}),
            "pull requests",
        ),
        (
            lambda e: e["issue"].update(state="closed"),
            "remain open",
        ),
        (
            lambda e: e.update(action="edited"),
            "created comments",
        ),
        (
            lambda e: e["repository"].update(full_name="evil/repo"),
            "repository identity",
        ),
    ],
)
def test_event_identity_fails_closed(tmp_path, mutator, match):
    cfg = config(tmp_path)
    value = event()
    mutator(value)
    with pytest.raises(ValueError, match=match):
        guardian.parse_command(value, cfg)


@pytest.mark.parametrize(
    "payload,match",
    [
        (
            {"schema_version": 1, "action": "restart_service"},
            "Unsupported Guardian",
        ),
        (
            {
                "schema_version": 1,
                "action": "status_snapshot",
                "command": "rm -rf /",
            },
            "fields are not exact",
        ),
        (
            {
                "schema_version": 1,
                "action": "rollout_pcp_exact_main",
                "expected_main_sha": "not-a-sha",
            },
            "40-hex",
        ),
        (
            {
                "schema_version": 1,
                "action": "rollout_pcp_exact_main",
                "expected_main_sha": SHA,
                "path": "/tmp/other",
            },
            "fields are not exact",
        ),
        (
            {
                "schema_version": 1,
                "action": "recover_antigravity_bridge",
                "service": "router",
            },
            "fields are not exact",
        ),
        (
            {
                "schema_version": 1,
                "action": "pm_bridge_snapshot",
                "project_id": "other",
                "target_comment_id": 123,
            },
            "not allow-listed",
        ),
        (
            {
                "schema_version": 1,
                "action": "pm_bridge_snapshot",
                "project_id": "chonhac",
                "target_comment_id": 0,
            },
            "positive target_comment_id",
        ),
        (
            {
                "schema_version": 1,
                "action": "pm_bridge_poll_project_once",
                "project_id": "chonhac",
                "path": "/v1/jobs",
            },
            "fields are not exact",
        ),
    ],
)
def test_payload_cannot_supply_arbitrary_capability(tmp_path, payload, match):
    with pytest.raises(ValueError, match=match):
        guardian.parse_command(event(payload), config(tmp_path))


def test_duplicate_marker_and_oversized_body_fail_closed(tmp_path):
    cfg = config(tmp_path)
    duplicated = event()
    duplicated["comment"]["body"] = (
        MARKER + "\n" + MARKER + "\n"
        + json.dumps({"schema_version": 1, "action": "status_snapshot"})
    )
    with pytest.raises(ValueError, match="exactly one"):
        guardian.parse_command(duplicated, cfg)

    oversized = event()
    oversized["comment"]["body"] = MARKER + "\n" + ("x" * 20000)
    with pytest.raises(ValueError, match="byte bound"):
        guardian.parse_command(oversized, cfg)


def test_audit_claim_is_consume_once_and_detects_changed_body(tmp_path):
    cfg = config(tmp_path)
    command = guardian.parse_command(event(), cfg)

    with guardian.AuditStore(Path(cfg["state_dir"])) as audit:
        fresh, row = audit.claim(command)
        assert fresh is True
        assert row["status"] == "dispatching"

        replay, same = audit.claim(command)
        assert replay is False
        assert same["status"] == "dispatching"

        terminal = audit.finish(
            command,
            status="executed",
            result={"status": "executed", "action": "status_snapshot"},
        )
        assert terminal["status"] == "executed"

        replay, stored = audit.claim(command)
        assert replay is False
        assert stored["result"]["status"] == "executed"

        changed = dict(command)
        changed["body_sha256"] = "f" * 64
        with pytest.raises(RuntimeError, match="changed content"):
            audit.claim(changed)


def test_origin_parser_accepts_only_github_repo_forms():
    assert (
        guardian._canonical_origin(
            "https://github.com/sonvhse06072/personal-coding-platform.git"
        )
        == "sonvhse06072/personal-coding-platform"
    )
    assert (
        guardian._canonical_origin(
            "git@github.com:sonvhse06072/personal-coding-platform.git"
        )
        == "sonvhse06072/personal-coding-platform"
    )
    assert guardian._canonical_origin("https://evil.example/repo.git") is None


def good_snapshot() -> dict:
    return {
        "active_engineering": {
            "reachable": True,
            "active_engineering_jobs": 0,
        },
        "executor": {
            "reachable": True,
            "active_jobs": 0,
        },
        "antigravity": {
            "reachable": True,
            "active_runs": 0,
            "pending_cancellations": 0,
        },
    }


def test_quiescence_requires_three_independent_zero_activity_proofs():
    guardian.GuardianHost._require_quiescent(good_snapshot())

    for section, key in (
        ("active_engineering", "active_engineering_jobs"),
        ("executor", "active_jobs"),
        ("antigravity", "active_runs"),
        ("antigravity", "pending_cancellations"),
    ):
        snapshot = good_snapshot()
        snapshot[section][key] = 1
        with pytest.raises(RuntimeError):
            guardian.GuardianHost._require_quiescent(snapshot)

    snapshot = good_snapshot()
    snapshot["active_engineering"]["reachable"] = False
    with pytest.raises(RuntimeError, match="unavailable"):
        guardian.GuardianHost._require_quiescent(snapshot)


class FakeGitHub:
    def __init__(self, head: str) -> None:
        self.head = head

    def default_head(self, branch: str) -> str:
        assert branch == "main"
        return self.head


class FakeHost:
    def __init__(self) -> None:
        self.rollouts = []
        self.recoveries = 0
        self.bridge_snapshots = []
        self.bridge_polls = []

    def snapshot(self):
        return {"safe": True}

    def recover_antigravity_bridge(self):
        self.recoveries += 1
        return {
            "status": "executed",
            "reused": False,
        }

    def pm_bridge_snapshot(self, *, project_id, target_comment_id):
        self.bridge_snapshots.append((project_id, target_comment_id))
        return {
            "runtime": {"status": "ok"},
            "n8n": {"ok": True},
            "control_event": {"state": "absent"},
        }

    def pm_bridge_poll_project_once(self, *, project_id):
        self.bridge_polls.append(project_id)
        return {
            "runtime": {"status": "ok"},
            "n8n": {"ok": True},
            "poll": {"project_id": project_id, "scanned": 1},
        }

    def rollout(self, expected_sha: str, github_head: str):
        self.rollouts.append((expected_sha, github_head))
        if expected_sha != github_head:
            raise RuntimeError("stale")
        return {
            "status": "executed",
            "expected_main_sha": expected_sha,
        }


def test_action_dispatch_never_infers_rollout_sha(tmp_path):
    cfg = config(tmp_path)
    host = FakeHost()

    status = guardian.execute_action(
        {"action": "status_snapshot"},
        config=cfg,
        github=FakeGitHub(SHA),
        host=host,
    )
    assert status["snapshot"] == {"safe": True}
    assert host.rollouts == []

    rollout = guardian.execute_action(
        {"action": "rollout_pcp_exact_main", "expected_main_sha": SHA},
        config=cfg,
        github=FakeGitHub(SHA),
        host=host,
    )
    assert rollout["status"] == "executed"
    assert host.rollouts == [(SHA, SHA)]

    recovery = guardian.execute_action(
        {"action": "recover_antigravity_bridge"},
        config=cfg,
        github=FakeGitHub(SHA),
        host=host,
    )
    assert recovery["status"] == "executed"
    assert recovery["github_main"] == SHA
    assert host.recoveries == 1

    bridge_snapshot = guardian.execute_action(
        {
            "action": "pm_bridge_snapshot",
            "project_id": "chonhac",
            "target_comment_id": 6031547665,
        },
        config=cfg,
        github=FakeGitHub(SHA),
        host=host,
    )
    assert bridge_snapshot["control_event"]["state"] == "absent"
    assert host.bridge_snapshots == [("chonhac", 6031547665)]

    bridge_poll = guardian.execute_action(
        {
            "action": "pm_bridge_poll_project_once",
            "project_id": "chonhac",
        },
        config=cfg,
        github=FakeGitHub(SHA),
        host=host,
    )
    assert bridge_poll["poll"]["project_id"] == "chonhac"
    assert host.bridge_polls == ["chonhac"]


def test_guardian_workflow_is_owner_issue_and_default_branch_bound():
    text = (ROOT / ".github/workflows/pcp-guardian.yml").read_text(
        encoding="utf-8"
    )
    assert "issue_comment:" in text
    assert "types: [created]" in text
    assert "github.event.comment.user.login == 'sonvhse06072'" in text
    assert "github.event.issue.number == 524" in text
    assert "github.event.issue.pull_request == null" in text
    assert "github.event.repository.default_branch" in text
    assert "persist-credentials: false" in text
    injected_body_expression = "$" + "{{ github.event.comment.body }}"
    assert injected_body_expression not in text
    assert "workflow_dispatch" not in text


def test_reviewed_guardian_config_is_exact():
    cfg = guardian.load_config(ROOT / "config/guardian.json")
    assert cfg["repository"] == "sonvhse06072/personal-coding-platform"
    assert cfg["allowed_actor"] == "sonvhse06072"
    assert cfg["control_issue_number"] == 524
    assert cfg["default_branch"] == "main"
    assert cfg["pcp_root"] == "/home/sonvh/personal-coding-platform-v1"


def full_ready_snapshot() -> dict:
    return {
        "runtime": {
            "reachable": True,
            "status": "ok",
            "version": "1.0.122",
        },
        "router": {
            "reachable": True,
            "status": "ok",
        },
        "executor": {
            "reachable": True,
            "status": "ok",
            "version": "1.0.33",
            "active_jobs": 0,
        },
        "antigravity": {
            "reachable": True,
            "status": "ok",
            "safe_settings": True,
            "active_runs": 0,
            "pending_cancellations": 0,
        },
        "active_engineering": {
            "reachable": True,
            "active_engineering_jobs": 0,
        },
        "n8n": {
            "reachable": True,
            "ok": True,
        },
        "credential_boundary": {
            "reachable": True,
            "ok": True,
        },
    }


def test_post_rollout_ready_requires_health_versions_and_mobile_control_plane():
    target = {"runtime": "1.0.122", "executor": "1.0.33"}
    snapshot = full_ready_snapshot()
    assert guardian.GuardianHost._post_rollout_ready(snapshot, target) is True

    cases = [
        ("runtime", "status", "degraded"),
        ("runtime", "version", "1.0.120"),
        ("router", "reachable", False),
        ("executor", "status", "degraded"),
        ("executor", "version", "1.0.32"),
        ("executor", "active_jobs", 1),
        ("antigravity", "safe_settings", False),
        ("antigravity", "active_runs", 1),
        ("active_engineering", "active_engineering_jobs", 1),
        ("n8n", "ok", False),
        ("credential_boundary", "ok", False),
    ]
    for section, key, value in cases:
        changed = json.loads(json.dumps(snapshot))
        changed[section][key] = value
        assert guardian.GuardianHost._post_rollout_ready(changed, target) is False


def test_guardian_actions_metadata_is_scrubbed_from_subprocesses_by_default(
    monkeypatch,
):
    scrubbed = {
        "GITHUB_TOKEN": "github-secret",
        "GH_TOKEN": "gh-secret",
        "ACTIONS_RUNTIME_TOKEN": "runtime-secret",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "oidc-secret",
        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.example/request",
        "RUNNER_TRACKING_ID": "runner-job-marker",
    }
    for key, value in scrubbed.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PCP_UNRELATED_ENV", "preserved")

    keys = sorted([*scrubbed, "PCP_UNRELATED_ENV"])
    probe = (
        "import json, os; "
        "print(json.dumps({k: os.environ.get(k) for k in "
        + repr(keys)
        + "}))"
    )
    default = guardian._run([guardian.sys.executable, "-c", probe])
    observed = json.loads(default.stdout)
    assert all(observed[key] is None for key in scrubbed)
    assert observed["PCP_UNRELATED_ENV"] == "preserved"

    scoped = guardian._run(
        [guardian.sys.executable, "-c", probe],
        env={"GITHUB_TOKEN": "scoped-token"},
    )
    observed = json.loads(scoped.stdout)
    assert observed["GITHUB_TOKEN"] == "scoped-token"
    assert observed["RUNNER_TRACKING_ID"] is None
    assert observed["PCP_UNRELATED_ENV"] == "preserved"
    assert all(
        observed[key] is None
        for key in scrubbed
        if key != "GITHUB_TOKEN"
    )


def test_git_fetch_askpass_contains_no_secret_and_is_private(
    tmp_path,
    monkeypatch,
):
    cfg = config(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "super-secret-token")
    host = guardian.GuardianHost(cfg, tmp_path)

    askpass, env = host._github_fetch_auth()
    try:
        text = askpass.read_text(encoding="utf-8")
        assert "super-secret-token" not in text
        assert "$GITHUB_TOKEN" in text
        assert env["GITHUB_TOKEN"] == "super-secret-token"
        assert env["GIT_ASKPASS"] == str(askpass)
        assert "RUNNER_TRACKING_ID" not in env
        assert (askpass.stat().st_mode & 0o777) == 0o700
    finally:
        askpass.unlink(missing_ok=True)



def bridge_recovery_snapshot(status="down"):
    snapshot = full_ready_snapshot()
    snapshot["runtime"]["version"] = "1.0.121"
    snapshot["antigravity"] = {
        "reachable": True,
        "status": status,
    }
    if status == "ok":
        snapshot["antigravity"].update(
            {
                "safe_settings": True,
                "active_runs": 0,
                "pending_cancellations": 0,
            }
        )
    snapshot["local_git"] = {
        "reachable": True,
        "branch": "main",
        "clean": True,
        "head": "a" * 40,
        "origin_repository": "sonvhse06072/personal-coding-platform",
    }
    return snapshot


def test_bridge_recovery_requires_explicit_down_or_already_safe_idle():
    down = bridge_recovery_snapshot("down")
    guardian.GuardianHost._require_bridge_recovery_preconditions(down)

    healthy = bridge_recovery_snapshot("ok")
    guardian.GuardianHost._require_bridge_recovery_preconditions(healthy)

    busy = bridge_recovery_snapshot("ok")
    busy["antigravity"]["active_runs"] = 1
    with pytest.raises(RuntimeError, match="not safe/idle"):
        guardian.GuardianHost._require_bridge_recovery_preconditions(busy)

    ambiguous = bridge_recovery_snapshot("degraded")
    with pytest.raises(RuntimeError, match="neither healthy nor explicitly down"):
        guardian.GuardianHost._require_bridge_recovery_preconditions(ambiguous)

    unreachable = bridge_recovery_snapshot("down")
    unreachable["antigravity"]["reachable"] = False
    with pytest.raises(RuntimeError, match="ambiguous"):
        guardian.GuardianHost._require_bridge_recovery_preconditions(unreachable)


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("local_git", "clean", False),
        ("runtime", "status", "degraded"),
        ("active_engineering", "active_engineering_jobs", 1),
        ("executor", "active_jobs", 1),
        ("credential_boundary", "ok", False),
    ],
)
def test_bridge_recovery_requires_idle_healthy_control_plane(
    section,
    key,
    value,
):
    snapshot = bridge_recovery_snapshot("down")
    snapshot[section][key] = value
    with pytest.raises(RuntimeError):
        guardian.GuardianHost._require_bridge_recovery_preconditions(snapshot)


def _write_helper_pair(root: Path, checkout: Path, relative: str, content: str):
    local = root / relative
    reviewed = checkout / relative
    local.parent.mkdir(parents=True, exist_ok=True)
    reviewed.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(content, encoding="utf-8")
    reviewed.write_text(content, encoding="utf-8")


def test_bridge_recovery_helpers_must_match_reviewed_checkout(tmp_path):
    cfg = config(tmp_path)
    root = Path(cfg["pcp_root"])
    checkout = tmp_path / "checkout"
    for relative in (
        "scripts/with-host-secrets.sh",
        "scripts/antigravity-bridge.sh",
    ):
        _write_helper_pair(root, checkout, relative, "#!/bin/sh\nexit 0\n")

    host = guardian.GuardianHost(cfg, checkout)
    hashes = host._require_reviewed_bridge_helpers()
    assert set(hashes) == {
        "scripts/with-host-secrets.sh",
        "scripts/antigravity-bridge.sh",
    }

    (root / "scripts/antigravity-bridge.sh").write_text(
        "#!/bin/sh\necho changed\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="differs from reviewed checkout"):
        host._require_reviewed_bridge_helpers()


def test_bridge_recovery_only_starts_exact_bridge_after_preconditions(
    tmp_path,
    monkeypatch,
):
    cfg = config(tmp_path)
    root = Path(cfg["pcp_root"])
    checkout = tmp_path / "checkout"
    for relative in (
        "scripts/with-host-secrets.sh",
        "scripts/antigravity-bridge.sh",
    ):
        _write_helper_pair(root, checkout, relative, "#!/bin/sh\nexit 0\n")

    host = guardian.GuardianHost(cfg, checkout)
    monkeypatch.setattr(host, "snapshot", lambda: bridge_recovery_snapshot("down"))
    monkeypatch.setattr(
        host,
        "_antigravity_health",
        lambda: {
            "status": "ok",
            "service": "antigravity-host-bridge",
            "version": "1.13",
            "safe_settings": True,
            "active_runs": 0,
            "pending_cancellations": 0,
        },
    )
    calls = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return Result()

    monkeypatch.setattr(guardian, "_run", fake_run)

    result = host.recover_antigravity_bridge()

    assert result["status"] == "executed"
    assert result["reused"] is False
    assert len(calls) == 1
    assert calls[0][0] == [
        "bash",
        str(root / "scripts/with-host-secrets.sh"),
        "bash",
        str(root / "scripts/antigravity-bridge.sh"),
        "start",
    ]
    assert calls[0][1]["cwd"] == root


def test_antigravity_down_status_is_explicit_not_probe_failure(
    tmp_path,
    monkeypatch,
):
    cfg = config(tmp_path)
    host = guardian.GuardianHost(cfg, tmp_path)

    class Result:
        returncode = 1
        stdout = '{"status":"down","service":"antigravity-host-bridge"}'
        stderr = ""

    monkeypatch.setattr(guardian, "_run", lambda *args, **kwargs: Result())
    assert host._antigravity_health() == {
        "status": "down",
        "service": "antigravity-host-bridge",
    }



def test_pm_bridge_snapshot_keeps_guardian_audit_identity_distinct(tmp_path):
    cfg = config(tmp_path)
    value = event(
        {
            "schema_version": 1,
            "action": "pm_bridge_snapshot",
            "project_id": "chonhac",
            "target_comment_id": 6031547665,
        }
    )
    value["comment"]["id"] = 6031656967

    command = guardian.parse_command(value, cfg)

    assert command["comment_id"] == 6031656967
    assert command["target_comment_id"] == 6031547665

    with guardian.AuditStore(Path(cfg["state_dir"])) as audit:
        fresh, row = audit.claim(command)
        assert fresh is True
        assert row["comment_id"] == 6031656967
        assert audit.read(6031547665) is None


def test_pm_bridge_control_event_projection_is_bounded_and_allow_listed():
    raw = {
        "project_id": "chonhac",
        "comment_id": 6031547665,
        "action": "request_diagnostics",
        "status": "failed",
        "target_identity": {
            "job_id": "job-12345678",
            "plan_id": "plan-1",
            "finding": "SECRET should not project",
            "arbitrary": "/private/path",
        },
        "error": "x" * 2000,
        "created_at": "2026-10-07T05:00:00+00:00",
        "updated_at": "2026-10-07T05:01:00+00:00",
        "body_sha256": "secret",
        "author": "owner",
    }

    projected = guardian.GuardianHost._sanitize_pm_control_event(raw)

    assert projected["state"] == "present"
    assert projected["target_identity"] == {
        "job_id": "job-12345678",
        "plan_id": "plan-1",
    }
    assert len(projected["error"]) == 500
    rendered = json.dumps(projected)
    assert "SECRET" not in rendered
    assert "/private/path" not in rendered
    assert "body_sha256" not in rendered
    assert "author" not in rendered


def test_late_review_guardian_snapshot_shows_bounded_no_capacity_outcome():
    raw = {
        "project_id": "chonhac",
        "comment_id": 6055219870,
        "action": "request_late_independent_review",
        "status": "executed",
        "target_identity": {
            "job_id": "057f6acff17b501eae3a673cbb6bbe36",
            "work_order_id": "SECRET job contract",
        },
        "result": {
            "status": "executed",
            "action": "request_late_independent_review",
            "result": {
                "status": "no_capacity",
                "reason": "no_eligible_higher_tier_reviewer",
                "reviewer_output": "SECRET model transcript",
                "workspace": "/home/private/repo",
            },
            "raw": "SECRET response",
        },
    }
    projected = guardian.GuardianHost._sanitize_pm_control_event(raw)
    assert projected["late_review_outcome"] == {
        "status": "no_capacity",
        "reason": "no_eligible_higher_tier_reviewer",
    }
    rendered = json.dumps(projected)
    assert "SECRET" not in rendered
    assert "/home/private" not in rendered


def test_late_review_guardian_snapshot_disallows_unknown_status_and_reason():
    raw = {
        "project_id": "chonhac",
        "comment_id": 6055219870,
        "action": "request_late_independent_review",
        "status": "executed",
        "result": {
            "result": {
                "status": "claimed",
                "review_mode": "cross_provider",
                "attempt_id": 101,
                "reason": "SECRET arbitrary reason",
                "secret": "SECRET",
            },
        },
    }
    projected = guardian.GuardianHost._sanitize_pm_control_event(raw)
    assert projected["late_review_outcome"] == {
        "status": "claimed",
        "review_mode": "cross_provider",
        "attempt_id": 101,
    }
    raw["result"]["result"]["status"] = "SECRET arbitrary status"
    assert "late_review_outcome" not in guardian.GuardianHost._sanitize_pm_control_event(raw)
    raw["result"]["result"]["status"] = "no_capacity"
    raw["action"] = "request_diagnostics"
    assert "late_review_outcome" not in guardian.GuardianHost._sanitize_pm_control_event(raw)
    raw["action"] = "request_late_independent_review"
    raw["status"] = "failed"
    assert "late_review_outcome" not in guardian.GuardianHost._sanitize_pm_control_event(raw)
    raw["status"] = "executed"
    raw["result"]["result"]["status"] = ["not a scalar"]
    assert "late_review_outcome" not in guardian.GuardianHost._sanitize_pm_control_event(raw)
    raw["result"]["result"]["status"] = "no_capacity"
    raw["result"]["result"]["reason"] = {"unexpected": "SECRET"}
    raw["result"]["result"]["review_mode"] = ["SECRET"]
    assert guardian.GuardianHost._sanitize_pm_control_event(raw)[
        "late_review_outcome"
    ] == {"status": "no_capacity"}


def test_pm_chat_guardian_snapshot_reveals_only_verified_attestation_id():
    raw = {
        "project_id": "chonhac",
        "comment_id": 6059100422,
        "action": "record_pm_chat_review",
        "status": "executed",
        "target_identity": {
            "job_id": "job-12345678",
            "plan_id": "plan-1",
            "work_order_id": "WO-1",
            "expected_head": "b" * 40,
            "review_id": 5455737177,
            "checkpoint_id": 182,
        },
        "result": {
            "status": "executed",
            "action": "record_pm_chat_review",
            "plan_id": "plan-1",
            "work_order_id": "WO-1",
            "job_id": "job-12345678",
            "result": {
                "status": "attested",
                "review_mode": "pm_chat_manual_review",
                "attestation_id": 91,
                "expected_head": "b" * 40,
                "reviewer_secret": "SECRET",
                "workspace": "/private/worktree",
            },
        },
    }
    expected = {
        "status": "attested",
        "review_mode": "pm_chat_manual_review",
        "attestation_id": 91,
        "expected_head": "b" * 40,
    }
    projected = guardian.GuardianHost._sanitize_pm_control_event(raw)
    assert projected["pm_chat_review_outcome"] == expected
    serialized = json.dumps(projected)
    assert "SECRET" not in serialized
    assert "/private/worktree" not in serialized
    assert "review_id" not in projected["target_identity"]

    # No control-supplied value, alternate action or malformed outcome can be
    # mistaken for a trusted PM-chat release identifier.
    for mutation in (
        lambda x: x.update(action="request_diagnostics"),
        lambda x: x.update(status="failed"),
        lambda x: x["result"].update(status="failed"),
        lambda x: x["result"].update(action="release_pm_chat_review"),
        lambda x: x["result"].update(plan_id="other-plan"),
        lambda x: x["result"].update(work_order_id="other-WO"),
        lambda x: x["result"].update(job_id="other-job"),
        lambda x: x["result"]["result"].update(expected_head="c" * 40),
        lambda x: x["result"]["result"].update(review_mode="cross_provider"),
        lambda x: x["result"]["result"].update(status="claimed"),
        lambda x: x["result"]["result"].update(attestation_id=True),
        lambda x: x["result"]["result"].update(attestation_id="91"),
        lambda x: x["result"]["result"].update(attestation_id=0),
        lambda x: x["result"]["result"].update(attestation_id=2**63),
    ):
        changed = json.loads(json.dumps(raw))
        mutation(changed)
        assert "pm_chat_review_outcome" not in (
            guardian.GuardianHost._sanitize_pm_control_event(changed)
        )

    failed = json.loads(json.dumps(raw))
    failed["result"]["result"].update(status="review_failed", attestation_id=91)
    assert guardian.GuardianHost._sanitize_pm_control_event(failed)[
        "pm_chat_review_outcome"
    ] == {
        "status": "review_failed",
        "review_mode": "pm_chat_manual_review",
    }


def test_pm_chat_guardian_snapshot_release_has_separate_exact_gate():
    raw = {
        "project_id": "chonhac",
        "comment_id": 6059200000,
        "action": "release_pm_chat_review",
        "status": "executed",
        "target_identity": {
            "job_id": "job-12345678",
            "plan_id": "plan-1",
            "work_order_id": "WO-1",
            "expected_head": "b" * 40,
            "attestation_id": 91,
            "checkpoint_id": 182,
        },
        "result": {
            "status": "executed",
            "action": "release_pm_chat_review",
            "plan_id": "plan-1",
            "work_order_id": "WO-1",
            "job_id": "job-12345678",
            "result": {
                "status": "released",
                "review_mode": "pm_chat_manual_review",
                "attestation_id": 91,
                "head": "b" * 40,
                "checkpoint_id": 183,
            },
        },
    }
    assert guardian.GuardianHost._sanitize_pm_control_event(raw)[
        "pm_chat_review_outcome"
    ] == {
        "status": "released",
        "review_mode": "pm_chat_manual_review",
        "attestation_id": 91,
        "expected_head": "b" * 40,
        "checkpoint_id": 183,
    }
    for nested in (
        {"head": "c" * 40},
        {"attestation_id": 92},
        {"checkpoint_id": True},
        {"checkpoint_id": -1},
        {"review_mode": "cross_provider"},
        {"status": "attested"},
    ):
        changed = json.loads(json.dumps(raw))
        changed["result"]["result"].update(nested)
        assert "pm_chat_review_outcome" not in (
            guardian.GuardianHost._sanitize_pm_control_event(changed)
        )


def test_pm_bridge_poll_projection_drops_raw_results_and_bounds_errors():
    raw = {
        "project_id": "chonhac",
        "repository": "sonvhse06072/chonhac",
        "scanned": 3,
        "controls_accepted": [
            {"comment_id": 10, "action": "request_diagnostics"},
        ],
        "controls_skipped": [11],
        "controls_dispatched": [
            {
                "comment_id": 12,
                "action": "request_diagnostics",
                "status": "executed",
                "result": {
                    "status": "published",
                    "comment_id": 900,
                    "raw": "SECRET",
                },
            }
        ],
        "controls_failed": [
            {
                "comment_id": 13,
                "action": "resume_same_job",
                "error": "e" * 2000,
            }
        ],
        "controls_rejected": [
            {"comment_id": 14, "error": "reject " + ("z" * 1000)}
        ],
        "controls_uncertain": [15],
        "accepted": [{"plan_id": "plan-1", "proposal": "SECRET"}],
    }

    projected = guardian.GuardianHost._sanitize_pm_bridge_poll(raw)

    assert projected["controls_accepted"] == [10]
    assert projected["controls_skipped"] == [11]
    assert projected["controls_uncertain"] == [15]
    assert projected["controls_dispatched"] == [
        {
            "comment_id": 12,
            "action": "request_diagnostics",
            "status": "executed",
            "result_status": "published",
            "diagnostic_comment_id": 900,
        }
    ]
    assert len(projected["controls_failed"][0]["error"]) == 500
    assert len(projected["controls_rejected"][0]["error"]) == 500
    assert projected["accepted_plan_ids"] == ["plan-1"]
    assert "SECRET" not in json.dumps(projected)



def test_pm_bridge_runtime_transport_reuses_host_secret_boundary(
    tmp_path,
    monkeypatch,
):
    cfg = config(tmp_path)
    host = guardian.GuardianHost(cfg, tmp_path)
    calls = []

    class Result:
        returncode = 0
        stdout = '{"status":"executed"}\n200\n'
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return Result()

    monkeypatch.setattr(guardian, "_run", fake_run)

    value = host._runtime_pm_bridge_request(
        method="GET",
        path="/v1/pm-bridge/control-events/chonhac/6031547665",
    )

    assert value == {"status": "executed"}
    args, kwargs = calls[0]
    assert args[:4] == [
        "bash",
        str(Path(cfg["pcp_root"]) / "scripts/with-host-secrets.sh"),
        "bash",
        "-lc",
    ]
    assert "ddev" not in args
    assert args[-3] == "GET"
    assert args[-2] == (
        "https://personal-coding-platform.ddev.site:8788"
        "/v1/pm-bridge/control-events/chonhac/6031547665"
    )
    assert kwargs["cwd"] == Path(cfg["pcp_root"])


def test_pm_bridge_runtime_transport_allows_only_explicit_404(
    tmp_path,
    monkeypatch,
):
    cfg = config(tmp_path)
    host = guardian.GuardianHost(cfg, tmp_path)

    class NotFound:
        returncode = 0
        stdout = '{"detail":"not found"}\n404\n'
        stderr = ""

    monkeypatch.setattr(guardian, "_run", lambda *args, **kwargs: NotFound())
    assert host._runtime_pm_bridge_request(
        method="GET",
        path="/v1/pm-bridge/control-events/chonhac/6031547665",
        allow_404=True,
    ) is None

    with pytest.raises(RuntimeError, match="HTTP 404"):
        host._runtime_pm_bridge_request(
            method="GET",
            path="/v1/pm-bridge/control-events/chonhac/6031547665",
            allow_404=False,
        )

    with pytest.raises(RuntimeError, match="Unsupported fixed Runtime PM Bridge path"):
        host._runtime_pm_bridge_request(
            method="GET",
            path="/v1/jobs/active-count",
        )


def test_pm_bridge_snapshot_and_poll_use_only_fixed_runtime_contract(
    tmp_path,
    monkeypatch,
):
    cfg = config(tmp_path)
    host = guardian.GuardianHost(cfg, tmp_path)
    calls = []

    monkeypatch.setattr(
        host,
        "_runtime_health",
        lambda: {"status": "ok", "version": "1.0.122"},
    )
    monkeypatch.setattr(host, "_n8n_health", lambda: {"ok": True})

    def fake_request(*, method, path, payload=None, allow_404=False):
        calls.append((method, path, payload, allow_404))
        if method == "GET":
            return None
        return {
            "project_id": "chonhac",
            "repository": "sonvhse06072/chonhac",
            "scanned": 1,
            "controls_dispatched": [],
        }

    monkeypatch.setattr(host, "_runtime_pm_bridge_request", fake_request)

    snapshot = host.pm_bridge_snapshot(
        project_id="chonhac",
        target_comment_id=6031547665,
    )
    assert snapshot["control_event"] == {"state": "absent"}
    assert calls[0] == (
        "GET",
        "/v1/pm-bridge/control-events/chonhac/6031547665",
        None,
        True,
    )

    poll = host.pm_bridge_poll_project_once(project_id="chonhac")
    assert poll["poll"]["project_id"] == "chonhac"
    assert calls[1] == (
        "POST",
        "/v1/pm-bridge/poll",
        {"project_id": "chonhac"},
        False,
    )

    with pytest.raises(RuntimeError, match="allow-listed"):
        host.pm_bridge_poll_project_once(project_id="other")
