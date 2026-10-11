"""Static G0-only Compose candidate tests; never invoke Docker or start services."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/g0/compose.candidate.yml"
PROJECT_ID = "pcp-g0-drupal-fixture"
PROFILE = "owner-gated-g0"
FIXTURE_TARGET = "/g0/sources/pcp-g0-fixtures/pcp-g0-drupal-fixture"
WORKSPACE_TARGET = "/g0/workspaces"
REGISTRY_TARGET = "/g0/config/projects.yml"
ALLOWED_SERVICES = {"db", "router", "runtime", "executor"}


def load_candidate():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def source_of(mount):
    return str(mount.get("source") or "")


def mounts_of(service):
    return service.get("volumes") or []


def validate(candidate):
    assert isinstance(candidate, dict)
    assert candidate["name"] == "pcp-g0d01"
    assert candidate["x-g0-contract"] == {
        "status": "parked",
        "approved_scope": "source_only",
        "activation_requires_owner": True,
        "ready_to_dispatch_g0d_t01": False,
    }
    assert set(candidate["services"]) == ALLOWED_SERVICES
    assert candidate["volumes"] == {
        "g0-db": {"name": "pcp-g0d01-postgres-data"}
    }
    assert candidate["networks"] == {
        "g0-private": {
            "name": "pcp-g0d01-private",
            "internal": True,
        }
    }

    forbidden = {
        "ports", "extra_hosts", "network_mode", "pid", "ipc",
        "privileged", "cap_add", "devices", "volumes_from",
        "links", "userns_mode", "build", "env_file", "secrets",
        "external_links",
    }
    for name, service in candidate["services"].items():
        assert not forbidden.intersection(service)
        assert service["profiles"] == [PROFILE]
        assert service["restart"] == "no"
        assert service["pull_policy"] == "never"
        assert service["networks"] == ["g0-private"]
        assert service["image"].startswith("${PCP_G0_")
        assert ":?" in service["image"]
        assert service["mem_limit"].endswith("m")
        assert int(service["mem_limit"][:-1]) <= 1024

    db = candidate["services"]["db"]
    assert db["container_name"] == "pcp-g0d01-postgres"
    assert db["environment"] == {
        "POSTGRES_USER": "g0",
        "POSTGRES_DB": "g0",
        "POSTGRES_PASSWORD": "${PCP_G0_DB_PASSWORD:?set_private_g0_password}",
    }
    assert mounts_of(db) == [{
        "type": "volume",
        "source": "g0-db",
        "target": "/var/lib/postgresql/data",
    }]

    router = candidate["services"]["router"]
    runtime = candidate["services"]["runtime"]
    executor = candidate["services"]["executor"]
    assert router["environment"]["ROUTER_PROJECTS_FILE"] == REGISTRY_TARGET
    assert runtime["environment"]["PROJECTS_FILE"] == REGISTRY_TARGET
    assert executor["environment"]["PROJECTS_FILE"] == REGISTRY_TARGET
    assert runtime["environment"]["PCP_RUNTIME_STARTUP_MODE"] == "inspect"
    assert executor["environment"]["PCP_EXECUTOR_PROJECT_SCOPE"] == PROJECT_ID
    assert executor["environment"]["CODING_PROJECTS_ROOT"] == "/g0/sources"
    assert runtime["environment"]["CODING_WORKSPACES_ROOT"] == WORKSPACE_TARGET
    assert executor["environment"]["CODING_WORKSPACES_ROOT"] == WORKSPACE_TARGET
    assert executor["environment"]["CODING_DIRECT_PROJECT_ROOT"] == "/g0/direct-disabled"
    assert runtime["environment"]["CODING_DIRECT_PROJECT_ROOT"] == "/g0/direct-disabled"
    for name in ("router", "runtime", "executor"):
        environment = candidate["services"][name]["environment"]
        assert not any("TOKEN" in k or "SECRET" in k for k in environment)
        assert candidate["services"][name]["security_opt"] == ["no-new-privileges:true"]

    def binds(name):
        return [
            m for m in mounts_of(candidate["services"][name])
            if m.get("type") == "bind"
        ]

    assert not any(m.get("type") == "volume" for n in ("router", "runtime", "executor")
                   for m in mounts_of(candidate["services"][n]))
    for name in ("router", "runtime", "executor"):
        for mount in binds(name):
            assert mount.get("bind") == {"create_host_path": False}
            source = source_of(mount)
            assert source.startswith((
                "${PCP_G0_REPO_ROOT:?",
                "${PCP_G0_FIXTURE_ROOT:?",
                "${PCP_G0_WORKSPACE_ROOT:?",
            ))
            assert "/var/run/docker.sock" not in source
            if source.startswith("${PCP_G0_REPO_ROOT:?"):
                assert mount.get("read_only") is True
                assert "/config/" in source
            elif source.startswith("${PCP_G0_FIXTURE_ROOT:?"):
                assert name == "executor"
                assert mount["target"] == FIXTURE_TARGET
                assert mount.get("read_only") is True
            elif source.startswith("${PCP_G0_WORKSPACE_ROOT:?"):
                assert name in {"runtime", "executor"}
                assert mount["target"] == WORKSPACE_TARGET
    assert len(binds("executor")) == 3
    assert len(binds("runtime")) == 4
    assert len(binds("router")) == 3
    assert any(m.get("target") == REGISTRY_TARGET for m in binds("router"))
    assert any(m.get("target") == REGISTRY_TARGET for m in binds("executor"))
    assert any(m.get("target") == REGISTRY_TARGET for m in binds("runtime"))

    # Neither the old PCP DB/registry nor Owner's Codex/Git credentials are mounted.
    encoded = yaml.safe_dump(candidate, allow_unicode=True)
    for forbidden_literal in (
        "personal-coding-platform-postgres",
        "chonhac",
        "/var/run/docker.sock",
        "/home/sonvh",
        "HOST_HOME",
        "/.codex",
        "/.gemini",
        "/.ddev",
    ):
        assert forbidden_literal not in encoded


def test_candidate_is_source_only_and_parked():
    validate(load_candidate())


@pytest.mark.parametrize("modify", [
    lambda d: d["services"].update({"n8n": {"image": "n8nio/n8n"}}),
    lambda d: d["services"]["executor"].update(ports=["8790:8790"]),
    lambda d: d["services"]["executor"].update(privileged=True),
    lambda d: d["services"]["runtime"].update(build="./unreviewed"),
    lambda d: d["services"]["executor"].update(env_file=["/home/sonvh/.env"]),
    lambda d: d["services"]["executor"].update(network_mode="host"),
    lambda d: d["services"]["executor"].update(volumes_from=["legacy-pcp"]),
    lambda d: d["services"]["runtime"].update(profiles=[]),
    lambda d: d["services"]["runtime"]["environment"].update(
        PCP_RUNTIME_STARTUP_MODE="normal"),
    lambda d: d["services"]["executor"]["environment"].update(
        PCP_EXECUTOR_PROJECT_SCOPE="chonhac"),
    lambda d: d["services"]["executor"]["environment"].update(
        CODING_PROJECTS_ROOT="/home/sonvh"),
    lambda d: d["services"]["executor"]["volumes"].append({
        "type": "bind", "source": "/var/run/docker.sock",
        "target": "/var/run/docker.sock",
    }),
    lambda d: d["services"]["executor"]["volumes"][1].update(read_only=False),
    lambda d: d["services"]["db"]["volumes"][0].update(
        source="personal-coding-platform-postgres"),
    lambda d: d["volumes"]["g0-db"].update(
        name="personal-coding-platform-postgres"),
    lambda d: d["networks"]["g0-private"].update(internal=False),
    lambda d: d["services"]["runtime"].update(
        pull_policy="always"),
    lambda d: d["x-g0-contract"].update(
        ready_to_dispatch_g0d_t01=True),
    lambda d: d["services"]["runtime"]["environment"].update(
        RUNTIME_API_TOKEN="unsafe-value"),
])
def test_unsafe_candidate_mutations_fail_static_review(modify):
    candidate = deepcopy(load_candidate())
    modify(candidate)
    with pytest.raises((AssertionError, KeyError, TypeError, ValueError)):
        validate(candidate)
