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


def test_status_and_rollout_commands_are_exact(tmp_path):
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

    def snapshot(self):
        return {"safe": True}

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
