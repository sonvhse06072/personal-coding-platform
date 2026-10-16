"""G1-T02 parked source regression tests: never touch Docker or models."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "g1_t02_source_contract", ROOT / "scripts/g1-t02-source-contract.py"
)
assert SPEC and SPEC.loader
t02 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(t02)


def test_exact_parked_t02_capsule_has_zero_activation_authority():
    result = t02.validate()
    assert result == {
        "status": "PASS_G1_T02_PARKED_PARTIAL_SOURCE",
        "model_calls": 0,
        "ready_for_model_dispatch": False,
        "ready_for_autonomous_e2e": False,
        "egress_activation": "NOT_REVIEWED",
    }


@pytest.fixture
def capsule(tmp_path):
    for path in t02.PATHS.values():
        src, dst = ROOT / path, tmp_path / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    assert t02.validate(tmp_path)["ready_for_model_dispatch"] is False
    return tmp_path


def mutate(root, section, update):
    file = root / t02.PATHS[section]
    record = yaml.safe_load(file.read_text(encoding="utf-8"))
    update(record)
    file.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")


@pytest.mark.parametrize("section,change,reason", [
    ("project", lambda d: d["projects"].update({"chonhac": {}}),
     "t02_project_registry_not_singleton"),
    ("project", lambda d: d["projects"][t02.PROJECT]["runtime"].update(
        pilot_identity="g1-t01-pcp"), "t02_project_not_inert"),
    ("project", lambda d: d["projects"][t02.PROJECT]["autonomy"].update(
        allow_create_pr=True), "t02_project_not_inert"),
    ("project", lambda d: d["projects"][t02.PROJECT]["autonomy"].update(
        allow_commit=True), "t02_project_not_inert"),
    ("baseline", lambda d: d["projects"][t02.PROJECT].update(
        active_revision="active"), "t02_project_baseline_not_parked"),
    ("baseline", lambda d: d["projects"][t02.PROJECT].update(
        revisions={"v1": {"status": "approved"}}),
     "t02_project_baseline_not_parked"),
    ("models", lambda d: d["models"].update({"other_model": {}}),
     "t02_model_budget_unreviewed"),
    ("policy", lambda d: d["profiles"]["fast"].update(
        max_model_calls=5), "t02_model_budget_unreviewed"),
    ("compose", lambda d: d["x-g1-t02-contract"].update(
        model_dispatch_enabled=True), "t02_dispatch_not_parked"),
    ("compose", lambda d: d["services"]["runtime"].update(
        entrypoint=["python3", "-m", "app.main"]),
     "t02_container_must_remain_inert"),
    ("compose", lambda d: d["services"]["executor"].update(
        privileged=True), "t02_container_must_remain_inert"),
    ("compose", lambda d: d["services"]["direct"].update(
        secrets=["g1_t02_repo_github_token"]), "t02_github_secret_boundary"),
    ("compose", lambda d: d["services"]["runtime"]["environment"].update(
        PCP_G1_T02_IDENTITY_ENABLED="owner-approved"),
     "t02_broker_not_disabled"),
    ("compose", lambda d: d["services"]["runtime"]["environment"].update(
        PCP_RUNTIME_STARTUP_MODE="normal"),
     "t02_runtime_not_inspect_only"),
    ("compose", lambda d: d["networks"]["g1-t02-control"].update(
        internal=False), "t02_control_network_boundary"),
    ("compose", lambda d: d["services"]["direct"].update(
        networks=["g1-t02-control"]), "t02_container_must_remain_inert"),
    ("compose", lambda d: d["services"]["runtime"]["volumes"].append({
        "type": "bind", "source": "/var/run/docker.sock",
        "target": "/var/run/docker.sock",
    }), "t02_docker_socket_boundary"),
])
def test_mutations_never_promote_capsule(capsule, section, change, reason):
    mutate(capsule, section, change)
    with pytest.raises(t02.ParkedStop, match=reason):
        t02.validate(capsule)


def test_foreign_egress_overlay_requires_separate_review(capsule):
    path = capsule / t02.EGRESS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("name: pcp-g1-t02\n", encoding="utf-8")
    with pytest.raises(t02.ParkedStop, match="t02_egress_not_reviewed"):
        t02.validate(capsule)


def test_t02_is_not_t01_or_f2_namespace(capsule):
    doc = yaml.safe_load(
        (capsule / t02.PATHS["compose"]).read_text(encoding="utf-8")
    )
    assert doc["name"] == "pcp-g1-t02"
    assert doc["x-g1-t02-contract"]["allowed_project_id"] == t02.PROJECT
    assert set(doc["networks"]).isdisjoint({
        "g1-pilot-control", "g1-pilot-direct-control", "ddev_default"
    })


def test_missing_or_symlinked_required_config_is_deny_by_default(capsule):
    path = capsule / t02.PATHS["models"]
    path.unlink()
    with pytest.raises(t02.ParkedStop, match="t02_file_missing_or_symlink"):
        t02.validate(capsule)
    path.symlink_to(ROOT / t02.PATHS["models"])
    with pytest.raises(t02.ParkedStop, match="t02_file_missing_or_symlink"):
        t02.validate(capsule)
