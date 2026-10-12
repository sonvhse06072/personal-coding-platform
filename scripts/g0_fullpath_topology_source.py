#!/usr/bin/env python3
"""Read-only F2 SOURCE topology admission. Always STOP; never activates PCP.

Only parses the checked-in parked candidate YAML. Does not inspect Docker,
create volumes, read credentials, contact providers, alter DB or run Codex.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/fullpath/compose.source-only.yml"
CONFIG_DIR = ROOT / "config/fullpath-candidate"
PROJECT_ID = "pcp-g0-fullpath-fixture"
PROJECT = "pcp-f2-fullpath"
SERVICES = ("fullpath-db", "fullpath-router", "fullpath-executor", "fullpath-runtime")
PROFILE = "owner-gated-f2-source"
SOURCE_REQUIRED = ("projects.yml", "project-baselines.yml", "models.yml", "routing-policy.yml")
PARKED_BLOCKERS = (
    "new_f2_fixture_repository_and_approved_seed_absent",
    "fresh_db_volume_and_zero_history_unverified",
    "image_digests_and_service_runtime_attestation_missing",
    "privileged_github_delivery_credentials_not_installed",
    "provider_egress_domain_allowlist_not_proven",
    "normal_runtime_startup_host_side_effects_not_authorized",
    "separate_owner_approved_live_flight_not_granted",
)
IMAGE_ENV = {
    "fullpath-db": "PCP_F2_POSTGRES_IMAGE",
    "fullpath-router": "PCP_F2_ROUTER_IMAGE",
    "fullpath-executor": "PCP_F2_EXECUTOR_IMAGE",
    "fullpath-runtime": "PCP_F2_RUNTIME_IMAGE",
}
CONFIG_BIND = "${PCP_F2_CONFIG_ROOT:?new_f2_config_root}"
MOUNT_TARGETS = {
    "fullpath-db": {"/var/lib/postgresql/data"},
    "fullpath-router": {"/fullpath/config/models.yml", "/fullpath/config/routing-policy.yml",
                        "/fullpath/config/projects.yml", "/tmp"},
    "fullpath-executor": {"/fullpath/config/projects.yml",
                          "/fullpath/sources/pcp-g0-fullpath-fixture",
                          "/fullpath/workspaces", "/tmp"},
    "fullpath-runtime": {"/fullpath/config/projects.yml",
                         "/fullpath/config/project-baselines.yml",
                         "/fullpath/config/models.yml",
                         "/fullpath/config/routing-policy.yml",
                         "/fullpath/sources/pcp-g0-fullpath-fixture",
                         "/fullpath/workspaces", "/home/coder/.codex-fullpath", "/tmp"},
}
MOUNT_SOURCES = {
    "/fullpath/config/projects.yml": CONFIG_BIND + "/projects.yml",
    "/fullpath/config/project-baselines.yml": CONFIG_BIND + "/project-baselines.yml",
    "/fullpath/config/models.yml": CONFIG_BIND + "/models.yml",
    "/fullpath/config/routing-policy.yml": CONFIG_BIND + "/routing-policy.yml",
    "/fullpath/sources/pcp-g0-fullpath-fixture":
        "${PCP_F2_FIXTURE_ROOT:?new_f2_fixture_checkout_required}",
    "/fullpath/workspaces":
        "${PCP_F2_WORKSPACE_ROOT:?new_f2_workspace_root_required}",
    "/home/coder/.codex-fullpath":
        "${PCP_F2_AUTH_ROOT:?new_f2_provider_auth_required}",
}
RW_TARGETS = {"/fullpath/workspaces", "/home/coder/.codex-fullpath"}
RUNTIME_ENV = {
    "PCP_RUNTIME_STARTUP_MODE": "g0_fullpath_candidate",
    "PCP_FULLPATH_SOURCE_ONLY": "true",
    "PCP_FULLPATH_OPERATIONAL_ACTIVATION": "",
    "PCP_FULLPATH_PM_FINALIZATION_ENABLED": "",
    "CODING_PROJECTS_ROOT": "/fullpath/sources",
    "CODING_WORKSPACES_ROOT": "/fullpath/workspaces",
    "CODING_DIRECT_PROJECT_ROOT": "/fullpath/direct-disabled",
    "PROJECTS_FILE": "/fullpath/config/projects.yml",
    "PROJECT_BASELINES_FILE": "/fullpath/config/project-baselines.yml",
    "MODELS_FILE": "/fullpath/config/models.yml",
    "ROUTING_POLICY_FILE": "/fullpath/config/routing-policy.yml",
    "CODEX_HOME": "/home/coder/.codex-fullpath",
    "ROUTER_URL": "http://fullpath-router:8090",
    "DDEV_EXECUTOR_URL": "http://fullpath-executor:8790",
    "DATABASE_URL": "postgresql://fullpath:${PCP_F2_DB_APP_PASSWORD:?new_private_app_password_required}@fullpath-db:5432/fullpath",
    "ROUTER_API_TOKEN": "${PCP_F2_ROUTER_API_TOKEN:?private_f2_router_token}",
    "PLATFORM_INTERNAL_TOKEN": "${PCP_F2_INTERNAL_TOKEN:?private_f2_internal_token}",
    "RUNTIME_API_TOKEN": "${PCP_F2_RUNTIME_API_TOKEN:?private_f2_runtime_token}",
    "HOME": "/home/coder",
}
ROUTER_ENV = {
    "ROUTER_MODELS_FILE": "/fullpath/config/models.yml",
    "ROUTER_POLICY_FILE": "/fullpath/config/routing-policy.yml",
    "ROUTER_PROJECTS_FILE": "/fullpath/config/projects.yml",
    "ROUTER_API_TOKEN": RUNTIME_ENV["ROUTER_API_TOKEN"],
}
EXECUTOR_ENV = {
    "HOME": "/home/coder",
    "PROJECTS_FILE": "/fullpath/config/projects.yml",
    "CODING_PROJECTS_ROOT": "/fullpath/sources",
    "CODING_WORKSPACES_ROOT": "/fullpath/workspaces",
    "CODING_DIRECT_PROJECT_ROOT": "/fullpath/direct-disabled",
    "PLATFORM_INTERNAL_TOKEN": RUNTIME_ENV["PLATFORM_INTERNAL_TOKEN"],
    "PCP_EXECUTOR_PROJECT_SCOPE": PROJECT_ID,
}


def _mounts(service: str, value: dict[str, Any]) -> bool:
    volumes = value.get("volumes")
    if not isinstance(volumes, list) or len(volumes) != len(MOUNT_TARGETS[service]):
        return False
    found: dict[str, dict[str, Any]] = {}
    for m in volumes:
        if not isinstance(m, dict) or not isinstance(m.get("target"), str):
            return False
        target = m["target"]
        if target in found or target not in MOUNT_TARGETS[service]:
            return False
        found[target] = m
        if target == "/tmp":
            if m.get("type") != "tmpfs" or set(m) != {"type", "target", "tmpfs"}:
                return False
            opts = m.get("tmpfs")
            if not isinstance(opts, dict) or set(opts) != {"size"} or (
                type(opts["size"]) is not int or opts["size"] < 67108864
            ):
                return False
        elif service == "fullpath-db":
            if m != {"type": "volume", "source": "fullpath-db-data",
                     "target": "/var/lib/postgresql/data"}:
                return False
        else:
            # Bind host-path creation is forbidden and source identity must be
            # entirely under future F2-only variables (not a literal owner path).
            if (
                m.get("type") != "bind"
                or m.get("source") != MOUNT_SOURCES.get(target)
                or m.get("bind") != {"create_host_path": False}
                or set(m) != (
                    {"type", "source", "target", "bind"}
                    if target in RW_TARGETS
                    else {"type", "source", "target", "read_only", "bind"}
                )
                or (target in RW_TARGETS and "read_only" in m)
                or (target not in RW_TARGETS and m.get("read_only") is not True)
            ):
                return False
            if target == "/home/coder/.codex-fullpath" and service != "fullpath-runtime":
                return False
    return set(found) == MOUNT_TARGETS[service]


def assess(compose: Any, files: dict[str, Any]) -> dict[str, Any]:
    """Pure negative contract: even exact parked source is NEVER deploy-ready."""
    checks: dict[str, bool] = {}
    if not isinstance(compose, dict):
        compose = {}
    if not isinstance(files, dict):
        files = {}
    contract = compose.get("x-f2-contract")
    services = compose.get("services")
    networks = compose.get("networks")
    volumes = compose.get("volumes")
    checks["unique_project_and_parked_contract"] = bool(
        set(compose) == {"name", "x-f2-contract", "services", "volumes", "networks"}
        and compose.get("name") == PROJECT
        and isinstance(contract, dict)
        and contract == {
            "phase": "source_only", "status": "parked",
            "operational_activation_authorized": False,
            "model_dispatch_allowed": False, "historical_g0_reuse_allowed": False,
            "provider_domain_egress_proven": False,
            "privileged_github_delivery_proven": False,
        }
    )
    checks["private_network_and_fresh_db_volume"] = bool(
        networks == {
            "fullpath-private": {"name": "pcp-f2-fullpath-private", "internal": True},
            "fullpath-provider": {"name": "pcp-f2-fullpath-provider", "internal": False},
        }
        and volumes == {
            "fullpath-db-data": {"name": "pcp-f2-fullpath-postgres-data"}
        }
    )
    service_map = (
        services if isinstance(services, dict) and set(services) == set(SERVICES)
        else {}
    )
    checks["four_inert_nondefault_services"] = bool(service_map) and all(
        isinstance(value, dict)
        and value.get("profiles") == [PROFILE]
        and value.get("entrypoint") == ["/bin/false"]
        and value.get("pull_policy") == "never"
        and value.get("restart") == "no"
        and value.get("image") == "${" + IMAGE_ENV[name] + ":?preloaded_digest_required}"
        and not any(
            name in value for name in (
                "ports", "expose", "privileged", "pid", "ipc", "network_mode",
                "devices", "device_cgroup_rules", "extra_hosts", "env_file",
                "volumes_from", "external_links", "extends", "build",
                "dockerfile", "command", "secrets",
            )
        )
        for name, value in service_map.items()
    )
    checks["owned_mounts_and_nosocket"] = bool(service_map) and all(
        _mounts(name, cfg) for name, cfg in service_map.items()
    )
    checks["zero_privilege_nonroot_apps"] = bool(service_map) and all(
        isinstance(service_map[name], dict)
        and service_map[name].get("read_only") is True
        and service_map[name].get("cap_drop") == ["ALL"]
        and service_map[name].get("security_opt") == ["no-new-privileges:true"]
        and (
            isinstance(service_map[name].get("user"), str)
            and service_map[name]["user"]
            == "${PCP_F2_UID:?new_nonroot_uid}:${PCP_F2_GID:?new_nonroot_gid}"
        )
        and type(service_map[name].get("pids_limit")) is int
        and service_map[name]["pids_limit"] <= 192
        for name in ("fullpath-router", "fullpath-executor", "fullpath-runtime")
    )
    checks["isolated_service_networks"] = bool(service_map) and all(
        service_map.get(name, {}).get("networks") == allowed
        for name, allowed in {
            "fullpath-db": ["fullpath-private"],
            "fullpath-router": ["fullpath-private"],
            "fullpath-executor": ["fullpath-private"],
            "fullpath-runtime": ["fullpath-private", "fullpath-provider"],
        }.items()
    )
    checks["exact_inert_service_credentials"] = bool(service_map) and (
        # PostgreSQL image bootstrap owner must never be Runtime's app role.

        service_map["fullpath-router"].get("environment") == ROUTER_ENV
        and service_map["fullpath-executor"].get("environment") == EXECUTOR_ENV
        and service_map["fullpath-runtime"].get("environment") == RUNTIME_ENV
        and service_map["fullpath-db"].get("environment") == {
            "POSTGRES_USER": "fullpath_bootstrap_admin", "POSTGRES_DB": "fullpath",
            "POSTGRES_PASSWORD":
                "${PCP_F2_DB_ADMIN_PASSWORD:?new_private_admin_password_required}",
        }
        and not any(
            token in str(cfg) for cfg in service_map.values()
            for token in ("GITHUB_DELIVERY_TOKEN", "ANTIGRAVITY_BRIDGE_TOKEN",
                          "/var/run/docker.sock", "/home/sonvh/chonhac",
                          "pcp-g0d01")
        )
    )
    projects = files.get("projects.yml")
    project = projects.get("projects") if isinstance(projects, dict) else None
    config = project.get(PROJECT_ID) if isinstance(project, dict) else None
    autonomy = config.get("autonomy") if isinstance(config, dict) else None
    ddev = config.get("ddev") if isinstance(config, dict) else None
    runtime = config.get("runtime") if isinstance(config, dict) else None
    checks["singleton_fixture_source_parked"] = bool(
        isinstance(project, dict) and set(project) == {PROJECT_ID}
        and config.get("path") == "${CODING_PROJECTS_ROOT}/pcp-g0-fullpath-fixture"
        and config.get("base_branch") == "benchmark/fullpath"
        and isinstance(autonomy, dict) and autonomy
        and all(value is False for value in autonomy.values())
        and isinstance(ddev, dict) and ddev.get("enabled") is False
        and all(ddev.get(x) == [] for x in (
            "preflight", "targeted_tests", "static_analysis", "full_tests", "cleanup"
        ))
        and isinstance(runtime, dict)
        and runtime.get("workspace_mode") == "isolated_clone"
        and runtime.get("exclusive_project_lease") is False
        and runtime.get("developer_permission_mode") == "bounded"
        and config.get("pm_standalone_review") == {
            "enabled": False, "reviewer_login": ""
        }
    )
    baselines = files.get("project-baselines.yml")
    baselines = baselines.get("projects") if isinstance(baselines, dict) else None
    checks["new_fixture_baseline_deliberately_unapproved"] = bool(
        isinstance(baselines, dict) and set(baselines) == {PROJECT_ID}
        and baselines[PROJECT_ID] == {"active_revision": None, "revisions": {}}
    )
    models = files.get("models.yml")
    policy = files.get("routing-policy.yml")
    checks["no_preapproved_provider_model_or_route"] = bool(
        isinstance(models, dict) and models.get("models") == {}
        and isinstance(policy, dict) and policy.get("profiles") == {}
    )
    valid = all(checks.values())
    return {
        "status": "STOP",
        "phase": "g0_f2_source_only_topology",
        "source_topology_valid": valid,
        "checks": checks,
        "blockers": (
            (["source_contract_invalid"] if not valid else [])
            + list(PARKED_BLOCKERS)
        ),
        "new_resources_created": 0,
        "model_calls_this_command": 0,
        "full_runtime_start_allowed": False,
        "ready_for_operational_activation": False,
    }


def read_source() -> tuple[Any, dict[str, Any]]:
    with COMPOSE.open("r", encoding="utf-8") as stream:
        topology = yaml.safe_load(stream)
    files = {}
    for name in SOURCE_REQUIRED:
        with (CONFIG_DIR / name).open("r", encoding="utf-8") as stream:
            files[name] = yaml.safe_load(stream)
    return topology, files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect",))
    args = parser.parse_args()
    try:
        compose, docs = read_source()
        result = assess(compose, docs)
    except (OSError, ValueError, yaml.YAMLError):
        result = {
            "status": "STOP",
            "phase": "g0_f2_source_only_topology",
            "source_topology_valid": False,
            "blockers": ["source_yaml_unavailable_or_invalid"],
            "new_resources_created": 0,
            "model_calls_this_command": 0,
            "full_runtime_start_allowed": False,
            "ready_for_operational_activation": False,
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2  # STOP is intentional, including when the parked source is valid.


if __name__ == "__main__":
    raise SystemExit(main())
