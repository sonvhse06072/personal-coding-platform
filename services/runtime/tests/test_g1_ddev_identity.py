"""G1 pinned DDEV identity: synthetic, no Docker or model calls."""
from __future__ import annotations

from pathlib import Path
import pytest

from app import engine_execution as execution

JOB = "a" * 32
SHA = "b" * 40
G1 = "pcp-benchmark-g1-smoke"


@pytest.fixture
def fixture_workspace(tmp_path: Path):
    target = tmp_path / JOB
    (target / ".ddev").mkdir(parents=True)
    (target / ".ddev" / "config.yaml").write_text(
        execution._G1_DDEV_CONFIG, encoding="utf-8",
    )
    return target


def admitted(ws: Path, **changes) -> bool:
    values = {
        "job_id": JOB, "project_id": G1,
        "source_commit": SHA, "workspace": ws,
    }
    values.update(changes)
    return execution.preserve_trusted_g1_ddev_name(**values)


def test_admitted_g1_preserves_pinned_name(fixture_workspace, monkeypatch):
    calls = []
    def allow(**args):
        calls.append(args)
        return {"PCP_DEV_JOB_ID": JOB}

    monkeypatch.setattr(execution, "trusted_codex_phase_broker", allow)
    assert admitted(fixture_workspace) is True
    assert calls == [{
        "job_id": JOB, "project_id": G1,
        "source_commit": SHA, "workspace": fixture_workspace,
        "mode": "execute", "adapter": "codex_cli",
    }]
    assert not (fixture_workspace / ".ddev" / "config.coding-platform.yaml").exists()


@pytest.mark.parametrize("foreign_project", [
    "chonhac", "pcp-g0-fullpath-fixture",
    "pcp-validation-fixture", "pcp-benchmark-unrelated",
])
def test_foreign_projects_never_use_override_exemption(
    fixture_workspace, monkeypatch, foreign_project,
):
    monkeypatch.setattr(
        execution, "trusted_codex_phase_broker",
        lambda **_: pytest.fail("Broker must not be queried for unrelated project"),
    )
    assert admitted(fixture_workspace, project_id=foreign_project) is False


@pytest.mark.parametrize("changed", [
    "name: unrelated\n",
    "hooks:\n  pre-exec: []\n",
    "", "name: pcp-g1-codex-smoke\n",
])
def test_changed_ddev_config_cannot_exempt_name_override(
    fixture_workspace, monkeypatch, changed,
):
    (fixture_workspace / ".ddev" / "config.yaml").write_text(
        changed, encoding="utf-8",
    )
    monkeypatch.setattr(
        execution, "trusted_codex_phase_broker",
        lambda **_: pytest.fail("Wrong fixture config must be rejected first"),
    )
    assert admitted(fixture_workspace) is False


def test_missing_or_symlink_config_cannot_exempt_name_override(
    fixture_workspace, monkeypatch,
):
    conf = fixture_workspace / ".ddev" / "config.yaml"
    conf.unlink()
    assert admitted(fixture_workspace) is False
    conf.symlink_to(fixture_workspace / "missing")
    assert admitted(fixture_workspace) is False


def test_unadmitted_g1_keeps_original_behavior(fixture_workspace, monkeypatch):
    monkeypatch.setattr(
        execution, "trusted_codex_phase_broker", lambda **_: None,
    )
    assert admitted(fixture_workspace) is False
