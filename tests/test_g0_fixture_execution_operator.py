"""Synthetic-only tests for gated G0 fixture activation source.

Tests never call a model, Docker, DDEV, GitHub delivery, or touch Owner data.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g0-fixture-execution-operator.py"
SPEC = importlib.util.spec_from_file_location("g0_fixture_activation", SCRIPT)
op = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(op)


def test_reviewed_overlay_is_exact_and_keeps_delivery_parked():
    op._validate_overlay()
    doc = yaml.safe_load(op.OVERLAY.read_text(encoding="utf-8"))
    assert doc["x-g0-execution-contract"]["status"] == "owner-activation-pending"
    assert doc["x-g0-execution-contract"]["automatic_dispatch"] is False
    assert doc["x-g0-execution-contract"]["github_delivery_enabled"] is False
    assert set(doc["services"]) == {"executor", "runtime"}
    assert doc["services"]["runtime"]["environment"]["PCP_RUNTIME_STARTUP_MODE"] == "g0_fixture_run"
    assert doc["services"]["runtime"]["environment"]["PCP_G0_DELIVERY_ENABLED"] == ""
    assert doc["services"]["runtime"]["environment"]["CODEX_HOME"] == "/home/coder/.codex-g0"
    assert doc["services"]["runtime"]["read_only"] is True


@pytest.mark.parametrize("change", [
    lambda d: d["x-g0-execution-contract"].update({"automatic_dispatch": True}),
    lambda d: d["x-g0-execution-contract"].update({"github_delivery_enabled": True}),
    lambda d: d["services"].update({"chonhac": {"image": "bad"}}),
    lambda d: d["services"]["runtime"].update({"privileged": True}),
    lambda d: d["services"]["runtime"]["environment"].update(
        {"PCP_G0_DELIVERY_ENABLED": "owner-approved"}
    ),
    lambda d: d["services"]["runtime"]["environment"].update(
        {"PCP_G0_MODEL_ID": "other-model"}
    ),
    lambda d: d["services"]["runtime"]["networks"].append("foreign-network"),
    lambda d: d["services"]["runtime"]["volumes"].append(
        {"type": "bind", "source": "/home/sonvh/chonhac", "target": "/chonhac"}
    ),
    lambda d: d["services"]["executor"]["environment"].update(
        {"GITHUB_DELIVERY_TOKEN": "unapproved"}
    ),
    lambda d: d["networks"].update({"g0-provider-direct": {"internal": False}}),
])
def test_protected_execution_overlay_fails_closed_on_scope_changes(
    tmp_path, monkeypatch, change
):
    doc = yaml.safe_load(op.OVERLAY.read_text(encoding="utf-8"))
    change(doc)
    path = tmp_path / "changed.yml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    monkeypatch.setattr(op, "OVERLAY", path)
    with pytest.raises(op.g0.GateError):
        op._validate_overlay()


@pytest.fixture
def preflight_stub(monkeypatch):
    monkeypatch.setattr(op.auth, "_context", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(op.auth, "_verify_rendered_tmpfs_mounts",
                        lambda *a, **k: None)
    monkeypatch.setattr(op.forensics, "inspect", lambda *a: {
        "status": "PASS",
        "direct_evidence": {"direct_turn_reconciled": True},
    })
    monkeypatch.setattr(op.auth, "_check_config", lambda *a: True)
    monkeypatch.setattr(op.g0, "inspect", lambda kind, name: {
        "Containers": {}, "Internal": False,
    })
    monkeypatch.setattr(op.g0, "require_headroom", lambda *a: None)
    monkeypatch.setattr(op, "_require_absent_files", lambda: None)
    monkeypatch.setattr(op, "_compose_env", lambda *a, **k: {})
    monkeypatch.setattr(op, "_render", lambda *a: None)
    return SimpleNamespace(repo=ROOT, fixture=ROOT, sha="a" * 40)


def test_preflight_reconciles_both_existing_model_turns_without_side_effects(
    preflight_stub, monkeypatch
):
    calls = []
    monkeypatch.setattr(op, "_render", lambda *args: calls.append("render"))
    monkeypatch.setattr(op.g0, "run",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            AssertionError("preflight must not mutate Docker")
                        ))
    report = op.preflight(
        preflight_stub.repo, preflight_stub.fixture, preflight_stub.sha
    )
    assert calls == ["render"]
    assert report["status"] == "PASS"
    assert report["protected_owner_activation_pending"] is True
    assert report["model_calls"] == 0
    assert report["ready_to_dispatch_g0d_t01"] is False


@pytest.mark.parametrize("missing", [
    "auth", "parity", "network", "private_artifact",
])
def test_preflight_fails_closed_before_activation(
    preflight_stub, monkeypatch, missing
):
    if missing == "auth":
        monkeypatch.setattr(op.auth, "_check_config", lambda *a: False)
    elif missing == "parity":
        monkeypatch.setattr(op.forensics, "inspect",
                            lambda *a: {"status": "STOP"})
    elif missing == "network":
        monkeypatch.setattr(op.g0, "inspect", lambda *a: {
            "Containers": {"foreign": {}}, "Internal": False
        })
    else:
        monkeypatch.setattr(op, "_require_absent_files",
                            lambda: (_ for _ in ()).throw(
                                op.g0.GateError("already_claimed")
                            ))
    with pytest.raises(op.g0.GateError):
        op.preflight(
            preflight_stub.repo, preflight_stub.fixture, preflight_stub.sha
        )


def test_activation_cannot_run_without_explicit_owner_approval(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("must stop before preflight or G0 mutations")
    monkeypatch.setattr(op, "preflight", forbidden)
    monkeypatch.setattr(op, "_exclusive_create", forbidden)
    monkeypatch.setattr(op.g0, "run", forbidden)
    with pytest.raises(op.g0.GateError, match="requires_owner"):
        op.activate(ROOT, ROOT, "a" * 40, False)


def test_one_owner_activation_recreates_only_two_exact_g0_services(
    preflight_stub, monkeypatch, tmp_path
):
    target = tmp_path / ".pcp-g0d01"
    target.mkdir(mode=0o700)
    monkeypatch.setattr(op.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(op, "preflight", lambda *a: {"status": "PASS"})
    monkeypatch.setattr(op, "_compose_env", lambda *a, **k: {
        "PATH": "/bin", "PCP_G0_INTERNAL_TOKEN": "private",
    })
    monkeypatch.setattr(op, "_render", lambda *a: None)
    monkeypatch.setattr(op.g0, "read_private_state", lambda *a: (
        op.auth.DEPLOYED_SHA, "private_db", tmp_path,
    ))
    monkeypatch.setattr(op.g0, "compose_env", lambda *a: {"PATH": "/bin"})
    monkeypatch.setattr(op, "_verify_containers", lambda *a: None)
    monkeypatch.setattr(op.auth.upgrader, "_read_json_secure",
                        lambda path: json.loads(path.read_text()))
    monkeypatch.setattr(op.auth.upgrader, "_private_write",
                        lambda path, data: path.write_text(json.dumps(data)))
    operations = []
    monkeypatch.setattr(op.g0, "run", lambda argv, **kw: operations.append(argv))
    outcome = op.activate(ROOT, ROOT, "a" * 40, True)
    assert outcome["status"] == "PASS"
    assert outcome["job_dispatched"] is False
    assert outcome["github_delivery_enabled"] is False
    assert len(operations) == 2
    for argv in operations:
        assert argv[:4] == ["docker", "compose", "-p", op.g0.PROJECT]
        assert "--no-deps" in argv
        assert "--no-build" in argv
        assert "--force-recreate" in argv
        assert "up" in argv
        assert "db" not in argv
        assert "router" not in argv
        assert "auth_pcp" not in argv
        assert "auth_direct" not in argv
    assert operations[0][-1] == "executor"
    assert operations[1][-1] == "runtime"
    assert (target / op.TOKENS_FILE).stat().st_mode & 0o077 == 0
    assert json.loads((target / op.JOURNAL_FILE).read_text())["state"] == "activated"


def test_running_activation_failure_preserves_claim_no_second_attempt(
    preflight_stub, monkeypatch, tmp_path
):
    private = tmp_path / ".pcp-g0d01"
    private.mkdir(mode=0o700)
    monkeypatch.setattr(op.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(op, "preflight", lambda *a: {"status": "PASS"})
    monkeypatch.setattr(op.g0, "read_private_state", lambda *a: (
        op.auth.DEPLOYED_SHA, "private", tmp_path,
    ))
    monkeypatch.setattr(op.g0, "compose_env", lambda *a: {})
    monkeypatch.setattr(op.auth.upgrader, "_read_json_secure",
                        lambda path: json.loads(path.read_text()))
    monkeypatch.setattr(op, "_render", lambda *a: None)
    monkeypatch.setattr(op.g0, "run",
                        lambda *a, **k: (_ for _ in ()).throw(
                            op.g0.GateError("g0_docker_compose_stopped")
                        ))
    with pytest.raises(op.g0.GateError, match="g0_docker_compose_stopped"):
        op.activate(ROOT, ROOT, "a" * 40, True)
    assert json.loads((private / op.JOURNAL_FILE).read_text())["state"] == "claimed"
    assert (private / op.TOKENS_FILE).exists()
    monkeypatch.setattr(op, "preflight",
                        lambda *a: (_ for _ in ()).throw(
                            op.g0.GateError("already_claimed_no_retry")
                        ))
    with pytest.raises(op.g0.GateError, match="already_claimed"):
        op.activate(ROOT, ROOT, "a" * 40, True)


def test_restore_checks_owner_gate_before_any_docker_or_db(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("No work unless Owner approved")
    monkeypatch.setattr(op.g0, "run", forbidden)
    with pytest.raises(op.g0.GateError, match="requires_owner"):
        op.restore(ROOT, ROOT, "a" * 40, False)


def test_status_incomplete_journal_remains_stopped(monkeypatch, tmp_path):
    monkeypatch.setattr(op.g0, "require_local_docker_context", lambda: None)
    monkeypatch.setattr(op.g0, "require_exact_repo", lambda *a: None)
    monkeypatch.setattr(op, "_validate_overlay", lambda: None)
    monkeypatch.setattr(op, "_private", lambda *a: tmp_path / "record")
    monkeypatch.setattr(op.auth.upgrader, "_read_json_secure",
                        lambda *a: {"state": "claimed", "source_sha": "a" * 40})
    monkeypatch.setattr(op, "_verify_containers",
                        lambda *a: (_ for _ in ()).throw(
                            AssertionError("unready activation must not pass")
                        ))
    result = op.status(ROOT, ROOT, "a" * 40)
    assert result["status"] == "STOP"
    assert result["ready_to_dispatch_g0d_t01"] is False


def test_real_cli_help_entrypoint_does_not_contact_provider_or_docker():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "--owner-approved-activate" in result.stdout
    assert "preflight" in result.stdout


def test_operator_source_has_no_model_dispatch_or_unscoped_docker_ops():
    src = SCRIPT.read_text(encoding="utf-8")
    for bad in (
        "ddev start", "ddev poweroff", "docker system prune", "docker stop",
        "docker restart", "docker rm", "git push", "gh pr create",
        "_direct_one_call(", "_probe_command(", "model_parity_probe.probe(",
        "CodexAdapter(", "GITHUB_DELIVERY_TOKEN=", "/home/sonvh/chonhac",
    ):
        assert bad not in src
    assert "no-deps" in src
    assert 'SERVICES = ("executor", "runtime")' in src
