"""F2 fullpath topology source-only negative tests; NO Docker/DB/model actions."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g0_fullpath_topology_source.py"
SPEC = importlib.util.spec_from_file_location("f2_source_topology", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
f2 = module


@pytest.fixture
def source():
    topology, files = f2.read_source()
    return deepcopy(topology), deepcopy(files)


def checked(topology, files, failed=None):
    outcome = f2.assess(topology, files)
    assert outcome["status"] == "STOP"
    assert outcome["full_runtime_start_allowed"] is False
    assert outcome["ready_for_operational_activation"] is False
    assert outcome["new_resources_created"] == 0
    assert outcome["model_calls_this_command"] == 0
    assert f2.PARKED_BLOCKERS[-1] in outcome["blockers"]
    if failed:
        assert outcome["checks"][failed] is False
        assert outcome["source_topology_valid"] is False
        assert "source_contract_invalid" in outcome["blockers"]
    return outcome


def test_four_inert_isolated_services_and_configs_have_valid_source_only_shape(source):
    topo, files = source
    original = deepcopy((topo, files))
    outcome = checked(topo, files)
    assert outcome["source_topology_valid"] is True
    assert all(outcome["checks"].values())
    assert len(outcome["checks"]) >= 10
    assert len(outcome["blockers"]) >= 7
    assert (topo, files) == original
    assert set(topo["services"]) == set(f2.SERVICES)
    assert not any(v.get("ports") for v in topo["services"].values())
    assert all(x["entrypoint"] == ["/bin/false"] for x in topo["services"].values())


@pytest.mark.parametrize("change", [
    lambda d: d.update(name="pcp-g0d01"),
    lambda d: d.update(name="pcp"),
    lambda d: d["x-f2-contract"].update({"operational_activation_authorized": True}),
    lambda d: d["x-f2-contract"].update({"model_dispatch_allowed": True}),
    lambda d: d["x-f2-contract"].update({"privileged_github_delivery_proven": True}),
    lambda d: d.update(services={**d["services"], "chonhac": {}}),
    lambda d: d["services"]["fullpath-runtime"].update(
        profiles=["default"]),
    lambda d: d["services"]["fullpath-runtime"].update(
        entrypoint=["uvicorn", "app.main:app"]),
    lambda d: d["services"]["fullpath-db"].update(entrypoint=[]),
    lambda d: d["services"]["fullpath-executor"].update(pull_policy="always"),
    lambda d: d["services"]["fullpath-router"].update(restart="always"),
    lambda d: d["services"]["fullpath-runtime"].update(
        ports=["0.0.0.0:8787:8787"]),
    lambda d: d["services"]["fullpath-runtime"].update(
        network_mode="host"),
    lambda d: d["services"]["fullpath-router"].update(
        privileged=True),
    lambda d: d["services"]["fullpath-executor"].update(
        env_file=["/home/user/.env"]),
    lambda d: d["services"]["fullpath-runtime"].update(
        extra_hosts=["host.docker.internal:host-gateway"]),
    lambda d: d["services"]["fullpath-db"].update(
        build={"context": "."}),
    lambda d: d["services"]["fullpath-runtime"].update(
        image="node:latest"),
])
def test_no_activation_reuse_or_added_side_effectful_service(source, change):
    topo, files = source
    change(topo)
    outcome = checked(topo, files)
    assert outcome["source_topology_valid"] is False


@pytest.mark.parametrize("mutate", [
    lambda d: d["networks"]["fullpath-private"].update(internal=False),
    lambda d: d["networks"]["fullpath-provider"].update(internal=True),
    lambda d: d["networks"]["fullpath-private"].update(
        name="pcp-g0d01-private"),
    lambda d: d["networks"].update({"default": {}}),
    lambda d: d["volumes"]["fullpath-db-data"].update(
        name="pcp-g0d01-postgres-data"),
    lambda d: d["volumes"].update({"historical-pcp": {}}),
    lambda d: d["services"]["fullpath-db"].update(
        networks=["fullpath-provider"]),
    lambda d: d["services"]["fullpath-router"].update(
        networks=["fullpath-provider"]),
    lambda d: d["services"]["fullpath-executor"].update(
        networks=["fullpath-private", "fullpath-provider"]),
    lambda d: d["services"]["fullpath-runtime"].update(
        networks=["fullpath-private"]),
])
def test_private_db_network_and_egress_boundary_not_replaceable(source, mutate):
    topo, files = source
    mutate(topo)
    checked(topo, files)


@pytest.mark.parametrize("service,mutation", [
    ("fullpath-runtime", lambda s: s["volumes"].append({
        "type": "bind", "source": "/var/run/docker.sock",
        "target": "/var/run/docker.sock"})),
    ("fullpath-runtime", lambda s: s["volumes"][6].update(
        source="/home/user/.codex")),
    ("fullpath-runtime", lambda s: s["volumes"][5].update(
        source="/home/user/chonhac")),
    ("fullpath-runtime", lambda s: s["volumes"][0].update(
        bind={"create_host_path": True})),
    ("fullpath-runtime", lambda s: s["volumes"][0].update(
        read_only=False)),
    ("fullpath-runtime", lambda s: s["volumes"][1].update(
        source="/home/user/pcp/config/project-baselines.yml")),
    ("fullpath-executor", lambda s: s["volumes"][1].update(
        target="/home/coder/.codex-fullpath")),
    ("fullpath-executor", lambda s: s["volumes"][2].update(
        source="${PCP_F2_AUTH_ROOT:?new_f2_provider_auth_required}")),
    ("fullpath-router", lambda s: s["volumes"].append({
        "type": "bind", "source": "/home/user/chonhac",
        "target": "/home/user/chonhac"})),
    ("fullpath-router", lambda s: s["volumes"][-1].update(
        tmpfs={"size": 0})),
    ("fullpath-executor", lambda s: s.update(
        cap_drop=[])),
    ("fullpath-runtime", lambda s: s.update(
        user="root")),
    ("fullpath-runtime", lambda s: s.update(
        read_only=False)),
])
def test_foreign_mount_write_socket_privileged_root_rejected(source, service, mutation):
    topo, files = source
    mutation(topo["services"][service])
    outcome = checked(topo, files)
    assert not outcome["source_topology_valid"]


@pytest.mark.parametrize("service,key,value", [
    ("fullpath-runtime", "PCP_RUNTIME_STARTUP_MODE", "normal"),
    ("fullpath-runtime", "PCP_FULLPATH_SOURCE_ONLY", "false"),
    ("fullpath-runtime", "PCP_FULLPATH_PM_FINALIZATION_ENABLED", "owner-approved"),
    ("fullpath-runtime", "DATABASE_URL", "postgresql://db:db@db:5432/db"),
    ("fullpath-runtime", "ROUTER_URL", "http://router:8090"),
    ("fullpath-runtime", "CODEX_HOME", "/home/coder/.codex-g0"),
    ("fullpath-runtime", "GITHUB_DELIVERY_TOKEN", "secret"),
    ("fullpath-runtime", "ANTIGRAVITY_BRIDGE_TOKEN", "token"),
    ("fullpath-executor", "GITHUB_DELIVERY_TOKEN", "token"),
    ("fullpath-executor", "PCP_EXECUTOR_PROJECT_SCOPE", "chonhac"),
    ("fullpath-router", "ROUTER_API_TOKEN", "legacy"),
    ("fullpath-db", "POSTGRES_DB", "legacy"),
])
def test_no_legacy_ambient_tokens_or_wrong_runtime_identity(source, service, key, value):
    topo, files = source
    topo["services"][service]["environment"][key] = value
    checked(topo, files)


@pytest.mark.parametrize("mutation", [
    lambda d: d["projects"].update({"chonhac": {}}),
    lambda d: d["projects"].update({"pcp-g0-drupal-fixture": {}}),
    lambda d: d["projects"][f2.PROJECT_ID].update(
        base_branch="benchmark/pcp"),
    lambda d: d["projects"][f2.PROJECT_ID].update(
        path="/home/sonvh/chonhac"),
    lambda d: d["projects"][f2.PROJECT_ID]["runtime"].update(
        workspace_mode="direct"),
    lambda d: d["projects"][f2.PROJECT_ID]["runtime"].update(
        exclusive_project_lease=True),
    lambda d: d["projects"][f2.PROJECT_ID]["autonomy"].update(
        allow_create_pr=True),
    lambda d: d["projects"][f2.PROJECT_ID]["autonomy"].update(
        allow_production_deploy=True),
    lambda d: d["projects"][f2.PROJECT_ID]["ddev"].update(
        enabled=True),
    lambda d: d["projects"][f2.PROJECT_ID]["pm_standalone_review"].update(
        enabled=True),
])
def test_frozen_singleton_fixture_cannot_silently_gain_rights(source, mutation):
    topo, files = source
    mutation(files["projects.yml"])
    checked(topo, files, "singleton_fixture_source_parked")


@pytest.mark.parametrize("filename,mutation", [
    ("project-baselines.yml", lambda d: d["projects"][f2.PROJECT_ID].update(
        active_revision="v1",
        revisions={"v1": {"source_commit": "a"*40, "status": "approved"}},
    )),
    ("project-baselines.yml", lambda d: d["projects"].update({"chonhac": {}})),
    ("models.yml", lambda d: d["models"].update({"legacy": {
        "provider": "google_antigravity"}})),
    ("routing-policy.yml", lambda d: d["profiles"].update({
        "fast": {"preferred_executor_ids": ["antigravity_free"]}})),
])
def test_no_borrowed_baseline_or_routable_provider_without_new_review(source, filename, mutation):
    topo, files = source
    mutation(files[filename])
    checked(topo, files)


def test_source_audit_is_pure_and_returns_stop_even_when_parking_is_valid(source):
    topo, files = source
    outcome = f2.assess(topo, files)
    assert outcome["status"] == "STOP"
    assert outcome["source_topology_valid"] is True
    assert outcome["ready_for_operational_activation"] is False
    assert outcome["full_runtime_start_allowed"] is False


def test_readonly_cli_produces_sanitized_blockers_and_never_runs_docker():
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "inspect"], capture_output=True,
        text=True, cwd=ROOT, timeout=15,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert run.returncode == 2
    result = json.loads(run.stdout)
    assert result["status"] == "STOP"
    assert result["source_topology_valid"] is True
    assert result["model_calls_this_command"] == 0
    assert result["new_resources_created"] == 0
    assert "password" not in run.stdout.lower()
    for forbidden in (
        "docker compose", "docker run", "docker stop", "git push",
        "codex exec", "subprocess.Popen(", "subprocess.run(",
    ):
        assert forbidden not in SCRIPT.read_text(encoding="utf-8")


def test_future_db_bootstrap_superuser_is_separate_from_runtime_role(source):
    topology, files = source
    admin = topology["services"]["fullpath-db"]["environment"]
    runtime = topology["services"]["fullpath-runtime"]["environment"]
    assert admin["POSTGRES_USER"] == "fullpath_bootstrap_admin"
    assert admin["POSTGRES_USER"] != runtime["DATABASE_URL"].split("://")[1].split(":")[0]
    assert "PCP_F2_DB_ADMIN_PASSWORD" in admin["POSTGRES_PASSWORD"]
    assert "PCP_F2_DB_APP_PASSWORD" in runtime["DATABASE_URL"]
    assert "PCP_F2_DB_ADMIN_PASSWORD" not in str(runtime)
    assert "PCP_F2_DB_APP_PASSWORD" not in str(admin)


def test_swapping_app_and_db_bootstrap_secret_is_denied(source):
    topo, docs = source
    topo["services"]["fullpath-db"]["environment"]["POSTGRES_PASSWORD"] = (
        topo["services"]["fullpath-runtime"]["environment"]["DATABASE_URL"]
    )
    checked(topo, docs, "exact_inert_service_credentials")


def test_compose_is_static_yaml_not_host_mount_rendered(source):
    topology, files = source
    assert topology["name"] == "pcp-f2-fullpath"
    serialized = yaml.safe_dump(topology)
    assert "GITHUB_DELIVERY_TOKEN" not in serialized
    assert "/var/run/docker.sock" not in serialized
    assert "pcp-g0d01-postgres-data" not in serialized
    assert "pull_policy: never" in serialized
    assert files["models.yml"]["models"] == {}
