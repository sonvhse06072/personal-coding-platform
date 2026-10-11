"""No-network tests for the controlled, two-arm Codex model parity probe."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/g0-codex-parity-probe.py"
SPEC = importlib.util.spec_from_file_location("g0_codex_parity_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
SHA = "a" * 40


def succeeded(stdout: str = probe.EXPECTED_RESPONSE) -> str:
    return "\n".join([
        json.dumps({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": stdout},
        }),
        json.dumps({
            "type": "turn.completed",
            "usage": {
                "input_tokens": 61,
                "cached_input_tokens": 0,
                "output_tokens": 3,
            },
        }),
    ])


def test_probe_uses_same_pinned_codex_model_effort_and_sandbox():
    assert probe.EXPECTED_MODEL == "gpt-6-luna"
    assert probe.EXPECTED_EFFORT == "medium"
    assert probe.EXPECTED_CLI == probe.auth.CLI_VERSION == "0.160.0"
    assert probe.EXPECTED_RESPONSE == "G0_PARITY_READY"
    for arm in ("pcp", "direct"):
        argv = probe._probe_command(ROOT, arm)
        assert argv[-1] == probe.PROBE_PROMPT
        assert "exec" in argv and "--json" in argv
        assert argv[argv.index("--model") + 1] == probe.EXPECTED_MODEL
        assert f'model_reasoning_effort="{probe.EXPECTED_EFFORT}"' in argv
        assert "--skip-git-repo-check" in argv
        assert argv[argv.index("--sandbox") + 1] == "read-only"
        assert 'approval_policy="never"' in argv
        assert "--no-deps" in argv and "--rm" in argv and "-T" in argv
        assert "gh" not in argv and "--force-recreate" not in argv
        # Host paths to the two reviewed Compose source files are expected.
        # Nothing passed *into Codex* may refer to the Owner host/workspaces.
        codex_argv = argv[argv.index("exec"):]
        assert "/home/sonvh" not in " ".join(codex_argv)
        assert argv[argv.index("run") + 4] == "auth_" + arm
    assert probe._probe_command(ROOT, "pcp") != probe._probe_command(ROOT, "direct")
    with pytest.raises(probe.g0.GateError, match="arm_invalid"):
        probe._probe_command(ROOT, "chonhac")


@pytest.mark.parametrize("value", [
    succeeded(), succeeded(" G0_PARITY_READY "),
])
def test_accepted_probe_requires_true_terminal_event_and_exact_reply(value):
    result = probe._parse_result(value, exit_code=0)
    assert result["terminal"] == "completed"
    assert result["response_verified"] is True
    assert result["usage"]["input_tokens"] == 61


@pytest.mark.parametrize(("body", "code"), [
    ("", 0),
    (succeeded(), 1),
    ("error: authenticated but no entitlement", 0),
    (json.dumps({"type": "turn.failed", "error": "secrets"}), 0),
    (succeeded("NOT_THE_EXPECTED_TOKEN"), 0),
    (succeeded() + "\n" + json.dumps({"type": "item.failed"}), 0),
])
def test_failed_or_wrong_model_turn_is_not_declared_valid(body, code):
    with pytest.raises(probe.g0.GateError):
        probe._parse_result(body, exit_code=code)


def test_usage_filters_malformed_or_unbounded_values():
    text = "\n".join([
        json.dumps({"type": "item.completed", "item": {
            "type": "agent_message", "text": probe.EXPECTED_RESPONSE,
        }}),
        json.dumps({"type": "turn.completed", "usage": {
            "input_tokens": True,
            "output_tokens": 2_000_001,
            "cached_input_tokens": 12,
            "private": "never-include",
        }}),
    ])
    result = probe._parse_result(text, exit_code=0)
    assert result["usage"] == {"cached_input_tokens": 12}


def test_provider_probe_does_not_expose_raw_stdout_stderr(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(probe.subprocess, "run",
                        lambda argv, **kw: (
                            seen.append((argv, kw)) or SimpleNamespace(
                                returncode=0, stdout=succeeded(),
                                stderr="secret-not-returned",
                            )
                        ))
    report = probe._run_probe(tmp_path, {"PCP_G0_DB_PASSWORD": "test-secret"}, "pcp")
    assert report["arm"] == "pcp"
    assert report["response_verified"] is True
    assert "stderr" not in report
    assert "secret-not-returned" not in json.dumps(report)
    assert len(seen) == 1
    assert seen[0][1]["timeout"] == 150
    assert seen[0][1]["capture_output"] is True
    assert seen[0][1]["check"] is False
    assert seen[0][1]["env"]["PCP_G0_DB_PASSWORD"] == "test-secret"


@pytest.fixture
def ready(monkeypatch, tmp_path):
    monkeypatch.setattr(probe.auth, "_context",
                        lambda *a, **k: ({"PATH": "/usr/bin"}, {
                            "deployed_source_sha": probe.auth.DEPLOYED_SHA,
                            "installed_codex_cli_version": probe.EXPECTED_CLI,
                        }))
    monkeypatch.setattr(probe.auth, "_verify_rendered_tmpfs_mounts",
                        lambda *a: None)
    monkeypatch.setattr(probe.auth, "_check_config", lambda *a: True)
    monkeypatch.setattr(probe.auth, "_auth_dir",
                        lambda arm: tmp_path / arm)
    monkeypatch.setattr(probe.g0, "require_headroom", lambda *a: None)
    return tmp_path


def test_status_reports_only_sanitized_auth_and_no_inference(ready, monkeypatch):
    monkeypatch.setattr(probe, "_read_existing_journal", lambda: None)
    report = probe.status(ready, ready, SHA)
    assert report["phase"] == "g0_model_parity_preflight"
    assert report["model"] == "gpt-6-luna"
    assert report["reasoning_effort"] == "medium"
    assert report["model_calls_this_command"] == 0
    assert report["model_entitlement_verified"] is False
    assert report["ready_to_dispatch_g0d_t01"] is False
    assert "token" not in json.dumps(report).lower()


@pytest.mark.parametrize("arm", ["pcp", "direct"])
def test_missing_either_profile_refuses_before_any_provider_call(
    ready, monkeypatch, arm
):
    monkeypatch.setattr(probe.auth, "_check_config",
                        lambda name: name != arm)
    monkeypatch.setattr(probe, "_run_probe",
                        lambda *a: pytest.fail("must not call provider"))
    with pytest.raises(probe.g0.GateError, match="auth_cache_missing"):
        probe.probe(ready, ready, SHA)


def test_explicit_probe_runs_serial_exactly_once_per_arm_and_journals(
    ready, monkeypatch
):
    logs = []
    record = []
    monkeypatch.setattr(probe, "_read_existing_journal", lambda: None)
    monkeypatch.setattr(probe, "_write_report",
                        lambda item: record.append(json.loads(json.dumps(item))))
    def fake_model(repo, env, arm):
        logs.append(arm)
        return {
            "arm": arm, "terminal": "completed", "response_verified": True,
            "usage": {"input_tokens": 4, "output_tokens": 2},
            "elapsed_seconds": 1.2,
        }
    monkeypatch.setattr(probe, "_run_probe", fake_model)
    report = probe.probe(ready, ready, SHA)
    assert logs == ["pcp", "direct"]
    assert report["both_provider_requests_completed"] is True
    assert report["model_calls_attempted"] == 2
    assert report["same_account_or_quota_proven"] is False
    assert report["ready_to_dispatch_g0d_t01"] is False
    assert record[0]["state"] == "started"
    assert record[-1]["state"] == "completed"
    assert record[-1]["attempted_arms"] == ["pcp", "direct"]
    assert record[-1]["completed_arms"] == ["pcp", "direct"]


def test_partial_provider_failure_is_recorded_and_not_automatically_retried(
    ready, monkeypatch
):
    seen = []
    monkeypatch.setattr(probe, "_read_existing_journal", lambda: None)
    monkeypatch.setattr(probe, "_write_report",
                        lambda item: seen.append(json.loads(json.dumps(item))))
    def provider(repo, env, arm):
        if arm == "direct":
            raise probe.g0.GateError("g0_provider_probe_process_failed")
        return {"arm": arm, "terminal": "completed", "usage": {}}
    monkeypatch.setattr(probe, "_run_probe", provider)
    with pytest.raises(probe.g0.GateError, match="process_failed"):
        probe.probe(ready, ready, SHA)
    assert seen[-1]["state"] == "failed"
    assert seen[-1]["failed_arm"] == "direct"
    assert seen[-1]["completed_arms"] == ["pcp"]
    monkeypatch.setattr(probe, "_read_existing_journal",
                        lambda: {"state": "failed"})
    monkeypatch.setattr(probe, "_run_probe",
                        lambda *a: pytest.fail("no blind retry allowed"))
    with pytest.raises(probe.g0.GateError, match="already_recorded"):
        probe.probe(ready, ready, SHA)


def test_no_provider_probe_if_prior_journal_exists(ready, monkeypatch):
    monkeypatch.setattr(probe, "_read_existing_journal",
                        lambda: {"state": "started"})
    with pytest.raises(probe.g0.GateError, match="already_recorded"):
        probe.probe(ready, ready, SHA)


def test_source_never_calls_ddev_host_codex_git_delivery_or_fixture_job():
    source = PATH.read_text(encoding="utf-8")
    for forbidden in (
        "ddev start", "ddev poweroff", "docker system prune",
        "docker stop", "docker restart", "git push", "git reset --hard",
        "gh pr create", "GITHUB_DELIVERY_TOKEN=", "OPENAI_API_KEY=",
        "PCP_G0_EXECUTION_ENABLED=owner-approved",
        "/home/sonvh/chonhac",
    ):
        assert forbidden not in source
    assert "ready_to_dispatch_g0d_t01" in source
