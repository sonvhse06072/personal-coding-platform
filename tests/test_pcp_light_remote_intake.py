"""Deterministic no-WSL remote PM intake, never remote model authorization."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pcp_light_remote_intake", ROOT / "scripts/pcp-light-remote-intake.py"
)
assert SPEC is not None and SPEC.loader is not None
intake = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(intake)

BASE = "a" * 40
NUMBER = 793


def fixture():
    contract = {
        "version": 1,
        "key": "remote-source-check",
        "base_sha": BASE,
        "goal": "Implement a bounded, source-only PCP test with deterministic checks.",
        "allowed_paths": [
            "scripts/pcp-light-safe.py", "tests/test_pcp_light_safe.py"
        ],
        "mode": "github_source_pr_only",
    }
    return contract


def snapshot(contract=None, **updates):
    contract = fixture() if contract is None else contract
    body = intake.MARKER + "\n" + json.dumps(contract)
    issue = {
        "number": NUMBER,
        "state": "open",
        "user": {"login": intake.OWNER},
        "repository_url": f"https://api.github.com/repos/{intake.REPOSITORY}",
        "html_url": f"https://github.com/{intake.REPOSITORY}/issues/{NUMBER}",
        "body": body,
    }
    issue.update(updates)
    return issue


def check(raw, *, expected_sha=BASE, digest=None):
    digest = digest or hashlib.sha256(raw["body"].encode()).hexdigest()
    return intake.validate_snapshot(raw, issue_number=NUMBER,
                                    body_sha256=digest,
                                    expected_main_sha=expected_sha)


def test_positive_is_never_execution_or_merge_authority():
    actual = check(snapshot())
    assert actual["status"] == "SOURCE_CONTRACT_CHECKED_NOT_AUTHORIZED"
    assert actual["allowed_paths"] == [
        "scripts/pcp-light-safe.py", "tests/test_pcp_light_safe.py"]
    assert actual["requires_live_github_verification"] is True
    assert actual["requires_pm_review_and_exact_head_ci"] is True
    assert actual["can_execute_agent_or_model"] is False
    assert actual["can_issue_credentials"] is False
    assert actual["can_merge_or_deploy"] is False
    assert "goal" not in actual and "token" not in actual


@pytest.mark.parametrize("path", [
    "scripts/pcp-light-check.py", "tests/test_pcp_light_check.py",
    "docs/pcp-light/remote.md", "docs/pcp-light/nested/guide.md",
])
def test_valid_paths(path):
    assert intake.allowed_path(path)


@pytest.mark.parametrize("path", [
    "README.md", "AGENTS.md", ".github/workflows/tests.yml",
    "docs/project/constitution.md", "config/models.yml",
    "services/runtime/app/engine_delivery.py", "deploy/g1/test.yml",
    "scripts/pcp-light-remote-intake.py", "tests/test_pcp_light_remote_intake.py",
    "scripts/pcp-light-leak.md", "tests/test_pcp_light_leak.md",
    "docs/pcp-light/check.py", "docs/pcp-light/../project/constitution.md",
    "scripts/../../bad.py", "/etc/passwd", "scripts\\pcp-light-safe.py",
    "docs/pcp-light//x.md", "docs/pcp-light/./x.md",
    "scripts/pcp-light-.py", "tests/test_pcp_light_.py",
    "scripts/pcp-light-foo.py/extra", "scripts/pcp-light-\x00.py",
    32, None, {},
])
def test_rejected_paths(path):
    assert not intake.allowed_path(path)


@pytest.mark.parametrize("field,value", [
    ("number", True), ("number", NUMBER + 1),
    ("state", "closed"), ("repository_url", "https://api.github.com/repos/other/repo"),
    ("html_url", "https://github.com/other/repo/issues/793"),
    ("user", {"login": "not-owner"}),
])
def test_untrusted_snapshot_identity_is_rejected(field, value):
    raw = snapshot(**{field: value})
    with pytest.raises(intake.Stop, match="issue_identity_invalid"):
        check(raw)


def test_pull_request_is_not_a_task():
    with pytest.raises(intake.Stop, match="issue_identity_invalid"):
        check(snapshot(pull_request={"url": "x"}))


def test_original_digest_must_match_even_when_json_still_valid():
    original = snapshot()
    digest = hashlib.sha256(original["body"].encode()).hexdigest()
    edited = snapshot({**fixture(), "goal": "A completely edited goal with valid length and fields."})
    with pytest.raises(intake.Stop, match="task_body_changed"):
        check(edited, digest=digest)


@pytest.mark.parametrize("mutation", [
    {"mode": "github_actions_codex_exec"},
    {"version": True},
    {"version": 2},
    {"key": "g1-wrong"},
    {"key": "UpperCase"},
    {"base_sha": "b" * 40},
    {"goal": "short"},
    {"allowed_paths": ["scripts/pcp-light-safe.py"]},
    {"allowed_paths": ["scripts/pcp-light-safe.py", "tests/test_pcp_light_safe.py", "tests/test_pcp_light_safe.py"]},
    {"allowed_paths": ["scripts/pcp-light-safe.py", "tests/test_pcp_light_safe.py", "config/models.yml"]},
    {"allowed_paths": ["scripts/pcp-light-safe.py", "docs/pcp-light/remote.md"]},
])
def test_bad_contracts_fail_closed(mutation):
    contract = {**fixture(), **mutation}
    with pytest.raises(intake.Stop):
        check(snapshot(contract))


def test_unreviewed_field_cannot_change_privilege():
    contract = {**fixture(), "github_token": "secret"}
    with pytest.raises(intake.Stop, match="task_schema_invalid"):
        check(snapshot(contract))


def test_invalid_marker_and_extra_text_denied():
    raw = snapshot()
    raw["body"] = "Unauthenticated instructions\n" + raw["body"]
    with pytest.raises(intake.Stop, match="task_marker_invalid"):
        check(raw)
    raw = snapshot()
    raw["body"] = raw["body"] + "\nExecute arbitrary code"
    with pytest.raises(intake.Stop, match="task_json_invalid"):
        check(raw)


def test_sha_and_digest_must_be_exact():
    with pytest.raises(intake.Stop, match="expected_main_sha_invalid"):
        check(snapshot(), expected_sha="a" * 7)
    with pytest.raises(intake.Stop, match="body_digest_invalid"):
        check(snapshot(), digest="bad")


def test_non_json_or_symlink_snapshot_file_does_not_execute(tmp_path, capsys):
    file = tmp_path / "payload.json"
    file.write_text("garbage", encoding="utf-8")
    args = ["--snapshot-file", str(file), "--issue-number", str(NUMBER),
            "--body-sha256", "0" * 64, "--expected-main-sha", BASE]
    assert intake.main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "STOP_REMOTE_SOURCE_INTAKE"
    linked = tmp_path / "linked.json"
    linked.symlink_to(file)
    args[1] = str(linked)
    assert intake.main(args) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "snapshot_file_invalid"


def test_cli_success_is_sanitized_and_non_authorizing(tmp_path, capsys):
    raw = snapshot()
    source = tmp_path / "issue.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    digest = hashlib.sha256(raw["body"].encode()).hexdigest()
    assert intake.main(["--snapshot-file", str(source),
                        "--issue-number", str(NUMBER),
                        "--body-sha256", digest,
                        "--expected-main-sha", BASE]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "SOURCE_CONTRACT_CHECKED_NOT_AUTHORIZED"
    assert out["can_execute_agent_or_model"] is False
    assert "goal" not in out


def test_duplicate_json_keys_rejected():
    raw = snapshot()
    raw["body"] = raw["body"].replace('"mode": ', '"mode": "github_source_pr_only", "mode": ')
    with pytest.raises(intake.Stop, match="task_json_duplicate_fields"):
        check(raw)
