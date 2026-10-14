#!/usr/bin/env python3
"""Source-only G1 pilot capsule invariant checker: NEVER deploys or calls Codex.

The parked Compose does not admit a model, provider auth, GitHub token,
Executor/DDEV service or job. This checker only reads owned source files.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = "deploy/g1/compose.pilot.parked.yml"
MODELS = "config/g1-pilot/models.yml"
POLICY = "config/g1-pilot/routing-policy.yml"
SERVICES = {"db", "router", "executor", "runtime", "direct"}
PROJECT = "pcp-benchmark-g1-pilot"
MODEL = "codex_gpt6_luna"
IMAGE = "gpt-6-luna"
NETWORKS = {
    "db": {"g1-pilot-control"},
    "router": {"g1-pilot-control"},
    "executor": {"g1-pilot-control", "g1-pilot-github-egress"},
    "runtime": {"g1-pilot-control", "g1-pilot-provider-egress"},
    "direct": {"g1-pilot-direct-provider-egress"},
}


class PilotStop(ValueError):
    """Non-secret source/activation invariant; report only a stable code."""


def require(yes: bool, code: str) -> None:
    if not yes:
        raise PilotStop(code)


def load(root: Path, path: str) -> dict[str, Any]:
    target = root / path
    require(target.is_file() and not target.is_symlink(),
            "g1_pilot_source_file_missing")
    try:
        content = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, yaml.YAMLError) as exc:
        raise PilotStop("g1_pilot_yaml_invalid") from exc
    require(isinstance(content, dict), "g1_pilot_yaml_non_object")
    return content


def mounts(service: dict[str, Any]) -> list[dict[str, Any]]:
    entries = service.get("volumes", [])
    require(isinstance(entries, list), "g1_pilot_mounts_invalid")
    for entry in entries:
        require(isinstance(entry, (dict, str)), "g1_pilot_mounts_invalid")
    return [m for m in entries if isinstance(m, dict)]


def validate(root: Path = ROOT) -> dict[str, Any]:
    doc = load(root, COMPOSE)
    cfg = load(root, MODELS)
    policy = load(root, POLICY)

    contract = doc.get("x-g1-pilot-contract") or {}
    require(
        doc.get("name") == "pcp-g1-pilot"
        and isinstance(contract, dict)
        and contract.get("status") == "parked"
        and contract.get("allowed_project_id") == PROJECT
        and contract.get("accepted_smoke_job_reused") is False,
        "g1_pilot_project_identity_not_parked",
    )
    for key in (
        "model_dispatch_enabled",
        "independent_ddev_identities_proven",
        "provider_auth_provisioned",
        "provider_egress_domain_allowlist_proven",
        "github_token_repo_scope_proven",
        "github_delivery_enabled",
        "autonomous_e2e_proven",
        "benchmark_go",
    ):
        require(contract.get(key) is False, "g1_pilot_activation_gate_bypassed")
    require(contract.get("direct_control_separated") is True,
            "g1_pilot_direct_not_separated")

    services = doc.get("services") or {}
    require(isinstance(services, dict) and set(services) == SERVICES,
            "g1_pilot_unexpected_services")
    networks = doc.get("networks") or {}
    require(set(networks) == set().union(*NETWORKS.values()),
            "g1_pilot_network_set_changed")
    require(
        networks["g1-pilot-control"].get("internal") is True
        and all(networks[k].get("internal") is False
                for k in networks if k != "g1-pilot-control"),
        "g1_pilot_control_network_not_internal",
    )
    for k, net in networks.items():
        require(net.get("name") == "pcp-g1-pilot-" + k.removeprefix("g1-pilot-"),
                "g1_pilot_network_name_collision")
    volumes = doc.get("volumes") or {}
    require(set(volumes) == {"g1-pilot-db"}
            and volumes["g1-pilot-db"].get("name") == "pcp-g1-pilot-postgres",
            "g1_pilot_db_volume_collision")
    for name, service in services.items():
        require(service.get("profiles") == ["g1-pilot-parked"]
                and service.get("entrypoint") == ["/bin/false"]
                and service.get("restart") == "no"
                and service.get("read_only") is True
                and service.get("cap_drop") == ["ALL"]
                and service.get("security_opt") == ["no-new-privileges:true"]
                and not service.get("ports")
                and not service.get("privileged")
                and not service.get("network_mode")
                and set(service.get("networks") or []) == NETWORKS[name],
                "g1_pilot_service_not_inert_or_isolated")
        require((service.get("labels") or {}).get("pcp.scope") ==
                "g1-pilot-parked",
                "g1_pilot_service_scope_label_invalid")

    # A runnable normal Runtime could resume jobs / run global schedulers.
    runtime = services["runtime"]
    router = services["router"]
    executor = services["executor"]
    direct = services["direct"]
    require(runtime["environment"].get("PCP_RUNTIME_STARTUP_MODE") == "inspect"
            and runtime["environment"].get("PCP_TRUSTED_CODEX_BROKER_ENABLED") == ""
            and executor["environment"].get("PCP_TRUSTED_CODEX_BROKER_ENABLED") == "",
            "g1_pilot_runtime_not_default_off")
    require(router["environment"].get("ROUTER_MODELS_FILE") ==
            "/pilot/config/models.yml"
            and runtime["environment"].get("MODELS_FILE") ==
            "/pilot/config/models.yml"
            and runtime["environment"].get("ROUTING_POLICY_FILE") ==
            "/pilot/config/routing-policy.yml",
            "g1_pilot_router_config_scope_changed")

    # Only Executor has Docker socket + GitHub token. Neither can be seen by
    # Runtime model or direct Codex. In particular, no host global CODEX_HOME.
    for name, service in services.items():
        sources = [
            str(m.get("source") or "") + " -> " + str(m.get("target") or "")
            for m in mounts(service)
        ]
        socket = any("/var/run/docker.sock" in item for item in sources)
        require(socket is (name == "executor"),
                "g1_pilot_docker_socket_scope_broken")
        secrets = service.get("secrets") or []
        require(secrets == (["g1_pilot_repo_github_token"]
                            if name == "executor" else []),
                "g1_pilot_github_secret_scope_broken")
    require(set(doc.get("secrets") or {}) == {"g1_pilot_repo_github_token"}
            and "PCP_G1_PILOT_GITHUB_TOKEN_FILE:?" in
                doc["secrets"]["g1_pilot_repo_github_token"]["file"],
            "g1_pilot_repo_token_not_fresh")

    p_auth = runtime["environment"].get("CODEX_HOME")
    d_auth = direct["environment"].get("CODEX_HOME")
    require(p_auth == "/home/coder/.codex-g1-pilot"
            and d_auth == "/home/coder/.codex-g1-direct"
            and p_auth != d_auth,
            "g1_pilot_auth_roots_not_distinct")
    runtime_mounts = mounts(runtime)
    direct_mounts = mounts(direct)
    require(any("PCP_G1_PILOT_PCP_CODEX_AUTH_DIR:?" in str(m.get("source", ""))
                and m.get("target") == p_auth
                for m in runtime_mounts),
            "g1_pilot_pcp_auth_not_private")
    require(any("PCP_G1_PILOT_DIRECT_CODEX_AUTH_DIR:?" in str(m.get("source", ""))
                and m.get("target") == d_auth for m in direct_mounts),
            "g1_pilot_direct_auth_not_private")
    require(not any("CODEX_AUTH_DIR" in str(m.get("source") or "")
                    for name in ("executor", "router", "db")
                    for m in mounts(services[name])),
            "g1_pilot_auth_exposed_to_control")

    # The model registry can neither silently select Astra nor select any
    # different provider/adapter/effort tier on another profile.
    models = cfg.get("models") or {}
    require(set(models) == {MODEL}, "g1_pilot_model_allowlist_changed")
    model = models[MODEL]
    require(model.get("provider") == "openai"
            and model.get("adapter") == "codex_cli"
            and model.get("model") == IMAGE
            and model.get("allowed_profiles") == ["fast"]
            and "executor" in model.get("roles", [])
            and (model.get("privacy") or {}).get("training_allowed") is False,
            "g1_pilot_model_identity_or_privacy_changed")
    profiles = policy.get("profiles") or {}
    require(set(profiles) == {"fast", "standard", "complex", "critical"},
            "g1_pilot_profiles_not_complete")
    fast = profiles["fast"]
    require(policy.get("adaptive_budget", {}).get("enabled") is False
            and fast.get("planner") is False
            and fast.get("evaluator") is False
            and fast.get("reasoning_effort", {}).get("executor") == "medium"
            and fast.get("reasoning_ceiling", {}).get("executor") == "medium"
            and fast.get("preferred_executor_ids") == [MODEL]
            and fast.get("max_model_calls") == 2
            and fast.get("max_repair_iterations") == 1
            and fast.get("max_changed_files") == 2
            and fast.get("max_wall_time_minutes") <= 20
            and fast.get("hard_cost_usd") <= 0.5,
            "g1_pilot_budget_or_effort_broadened")
    # Only a fast-profile task can find an eligible model. High risk / other
    # profiles MUST fail selection rather than trigger another agent.
    require(all(fast.get("max_model_calls") == p.get("max_model_calls")
                and p.get("planner") is False and p.get("evaluator") is False
                for p in profiles.values()),
            "g1_pilot_other_profile_escalation")
    return {
        "status": "PASS_G1_PILOT_SOURCE_PARKED",
        "model": IMAGE,
        "reasoning": "medium",
        "pilot_services": sorted(SERVICES),
        "other_project_changes": 0,
        "ready_for_model_dispatch": False,
        "ready_for_autonomous_e2e": False,
        "model_calls": 0,
        "next_gate": "SEPARATE_PILOT_WORKSPACE_IDENTITY_AND_PROVIDER_GITHUB_AUTH",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-pcp-sha", default="")
    args = parser.parse_args()
    try:
        if args.expected_pcp_sha:
            require(re.fullmatch(r"[a-f0-9]{40}", args.expected_pcp_sha) is not None,
                    "g1_pilot_source_sha_invalid")
            head = subprocess.run(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                text=True, capture_output=True, timeout=10, check=False,
            )
            require(head.returncode == 0
                    and head.stdout.strip() == args.expected_pcp_sha,
                    "g1_pilot_source_head_not_pinned")
        report = validate()
        code = 0
    except (PilotStop, OSError, subprocess.TimeoutExpired) as exc:
        report = {
            "status": "STOP_G1_PILOT_SOURCE_CONTRACT",
            "blocker": str(exc) if isinstance(exc, PilotStop)
                       else "g1_pilot_source_checker_unavailable",
            "model_calls": 0,
            "ready_for_model_dispatch": False,
        }
        code = 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
