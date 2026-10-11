"""Source-only G0 fixture isolation invariants; tests never contact WSL/Docker."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/g0-fixture-isolation-contract.py"
SPEC = importlib.util.spec_from_file_location("g0_fixture_isolation_contract", PATH)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)

FILES = (
    "config/projects.yml",
    "config/project-baselines.yml",
    "config/g0-fixture-only/projects.yml",
    "config/g0-fixture-only/project-baselines.yml",
    "config/g0-fixture-only/pm-bridge.yml",
    "config/g0-fixture-only/source-contract.yml",
)


@pytest.fixture
def isolated_copy(tmp_path):
    for name in FILES:
        src = ROOT / name
        dst = tmp_path / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    return tmp_path


def edit(root, path, change):
    file = root / path
    data = yaml.safe_load(file.read_text(encoding="utf-8"))
    change(data)
    file.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_exact_source_contract_is_verified_without_executing_on_host(capsys, monkeypatch):
    result = guard.validate(ROOT)
    assert result["result"] == "PASS"
    assert result["source_sha"] == guard.SEED
    assert result["fixture_only_registry"] is True
    assert result["legacy_state_touched"] is False
    assert result["docker_or_ddev_invoked"] is False
    assert result["runtime_deployed"] is False
    assert result["ready_to_activate"] is False
    assert result["ready_to_dispatch_g0d_t01"] is False
    monkeypatch.setattr(sys, "argv", ["g0-fixture-isolation-contract"])
    assert guard.main() == 0
    stdout = capsys.readouterr().out
    assert "chonhac" not in stdout.casefold()
    assert "private/" not in stdout
    assert json.loads(stdout)["ready_to_dispatch_g0d_t01"] is False


@pytest.mark.parametrize(("path", "mutation"), [
    ("config/g0-fixture-only/projects.yml",
     lambda d: d["projects"].update({"unrelated": {"path": "/unrelated"}})),
    ("config/g0-fixture-only/projects.yml",
     lambda d: d["projects"][guard.FIXTURE]["ddev"].update(enabled=True)),
    ("config/g0-fixture-only/projects.yml",
     lambda d: d["projects"][guard.FIXTURE]["autonomy"].update(allow_create_pr=True)),
    ("config/g0-fixture-only/projects.yml",
     lambda d: d["projects"][guard.FIXTURE]["runtime"].update(workspace_mode="direct")),
    ("config/g0-fixture-only/projects.yml",
     lambda d: d["projects"][guard.FIXTURE].update(base_branch="main")),
    ("config/g0-fixture-only/project-baselines.yml",
     lambda d: d["projects"][guard.FIXTURE]["revisions"][guard.BASELINE].update(source_commit="e"*40)),
    ("config/g0-fixture-only/project-baselines.yml",
     lambda d: d["projects"][guard.FIXTURE].update(active_revision="unapproved")),
    ("config/g0-fixture-only/pm-bridge.yml",
     lambda d: d["projects"].update({"legacy": {"enabled": True}})),
    ("config/g0-fixture-only/source-contract.yml",
     lambda d: d["activation"].update(runtime_startup_mode="normal")),
    ("config/g0-fixture-only/source-contract.yml",
     lambda d: d["activation"].update(allow_docker_socket=True)),
    ("config/g0-fixture-only/source-contract.yml",
     lambda d: d["activation"].update(allow_ddev=True)),
    ("config/g0-fixture-only/source-contract.yml",
     lambda d: d["activation"].update(allow_github_delivery=True)),
    ("config/g0-fixture-only/source-contract.yml",
     lambda d: d["activation"].update(start_services=True)),
    ("config/g0-fixture-only/source-contract.yml",
     lambda d: d["separation"].update(database_volume="personal-coding-platform-postgres")),
    ("config/g0-fixture-only/source-contract.yml",
     lambda d: d["separation"].update(hard_isolation_verified=True)),
])
def test_activation_or_registry_drift_refuses_to_pass(isolated_copy, path, mutation):
    edit(isolated_copy, path, mutation)
    with pytest.raises(ValueError):
        guard.validate(isolated_copy)


def test_canonical_fixture_cannot_be_silently_promoted_even_when_stage_matches(isolated_copy):
    for path in ("config/projects.yml", "config/g0-fixture-only/projects.yml"):
        edit(isolated_copy, path,
             lambda d: d["projects"][guard.FIXTURE]["ddev"].update(enabled=True))
    with pytest.raises(ValueError, match="fixture_ddev_not_parked"):
        guard.validate(isolated_copy)


def test_canonical_baseline_cannot_be_repointed_even_when_stage_matches(isolated_copy):
    for path in ("config/project-baselines.yml",
                 "config/g0-fixture-only/project-baselines.yml"):
        edit(isolated_copy, path,
             lambda d: d["projects"][guard.FIXTURE]["revisions"][guard.BASELINE].update(
                 source_commit="e" * 40))
    with pytest.raises(ValueError, match="fixture_baseline_seed_drift"):
        guard.validate(isolated_copy)


def test_duplicate_yaml_keys_are_rejected(isolated_copy):
    path = isolated_copy / "config/g0-fixture-only/source-contract.yml"
    with path.open("a", encoding="utf-8") as stream:
        stream.write("\nschema_version: 1\n")
    with pytest.raises(ValueError, match="duplicate_yaml_key"):
        guard.validate(isolated_copy)


def test_missing_staged_fixture_blocks_cleanly(isolated_copy, monkeypatch, capsys):
    (isolated_copy / "config/g0-fixture-only/projects.yml").unlink()
    monkeypatch.setattr(sys, "argv", ["g0-fixture-isolation-contract",
                                       "--repo-root", str(isolated_copy)])
    assert guard.main() == 2
    data = json.loads(capsys.readouterr().out)
    assert data["result"] == "STOP"
    assert not data["ready_to_activate"]


def test_validator_has_no_operational_write_or_process_launch():
    source = PATH.read_text(encoding="utf-8")
    for forbidden in (
        "import subprocess", "subprocess.run(", "subprocess.Popen(",
        "os.system(", "docker start", "docker compose",
        "ddev start", "ddev stop", "docker exec", "requests.",
        "httpx.", "shutil.rmtree(", "write_text(", ".unlink(",
    ):
        assert forbidden not in source
    assert '"ready_to_dispatch_g0d_t01": False' in source
