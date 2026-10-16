#!/usr/bin/env python3
"""Read-only, fail-closed G1-T02 preliminary PARKED source validation.

This validates only an inert source capsule, NEVER Runtime permission, live
network isolation, provider authentication, safe startup or model dispatch.
The missing separate egress review is an explicit STOP for real activation.
"""
from __future__ import annotations

import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "pcp-benchmark-g1-t02"
PATHS = {
    "project": "config/g1-t02/projects.pcp.template.yml",
    "baseline": "config/g1-t02/project-baselines.yml",
    "models": "config/g1-t02/models.yml",
    "policy": "config/g1-t02/routing-policy.yml",
    "compose": "deploy/g1/compose.t02.parked.yml",
}
EGRESS = "deploy/g1/compose.t02.egress.parked.yml"
SERVICES = {"db", "router", "executor", "runtime", "direct"}
NETS = {
    "g1-t02-control", "g1-t02-direct-control",
    "g1-t02-provider-egress", "g1-t02-github-egress",
    "g1-t02-direct-provider-egress",
}


class ParkedStop(ValueError):
    """A stable code, without raw config or credentials."""


def require(value: bool, code: str) -> None:
    if not value:
        raise ParkedStop(code)


def read(root: Path, name: str) -> dict:
    path = root / name
    require(path.is_file() and not path.is_symlink(), "t02_file_missing_or_symlink")
    try:
        item = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ParkedStop("t02_yaml_unreadable") from exc
    require(isinstance(item, dict), "t02_yaml_not_object")
    return item


def validate(root: Path = ROOT) -> dict:
    d = {key: read(root, path) for key, path in PATHS.items()}
    require(not (root / EGRESS).exists(), "t02_egress_not_reviewed")
    pdoc = d["project"]
    require(pdoc.get("version") == 1
            and set(pdoc.get("projects") or {}) == {PROJECT},
            "t02_project_registry_not_singleton")
    p = pdoc["projects"][PROJECT]
    runtime, autonomy = p.get("runtime") or {}, p.get("autonomy") or {}
    require(
        p.get("path") == "$" + "{PCP_G1_T02_ROOT}/source"
        and p.get("base_branch") == "benchmark/g1-codex-smoke-v1"
        and runtime.get("pilot_identity") == "g1-t02-pcp"
        and runtime.get("developer_permission_mode") == "trusted_project"
        and runtime.get("workspace_mode") == "isolated_clone"
        and runtime.get("exclusive_project_lease") is False
        and runtime.get("branch_prefix") == "ai"
        and (p.get("ddev") or {}).get("enabled") is True
        and all(autonomy.get(key) is False for key in (
            "allow_commit", "allow_push_ai_branch", "allow_create_pr",
            "allow_auto_merge_low_risk", "allow_production_deploy"
        )),
        "t02_project_not_inert",
    )
    tools = p.get("trusted_codex_tools") or {}
    require(
        set(tools) == {"targeted_tests", "static_analysis", "frontend_quality"}
        and tools.get("frontend_quality") == [[
            "ddev", "exec", "npm", "--prefix", "/var/www/html", "run", "build"
        ]],
        "t02_phase_commands_unreviewed",
    )
    baseline = d["baseline"]
    require(
        baseline.get("version") == 1
        and set(baseline.get("projects") or {}) == {PROJECT}
        and baseline["projects"][PROJECT].get("active_revision", "UNSET") is None
        and baseline["projects"][PROJECT].get("revisions") == {},
        "t02_project_baseline_not_parked",
    )
    models = d["models"].get("models") or {}
    model = models.get("codex_gpt6_luna") or {}
    policy = d["policy"]
    fast = (policy.get("profiles") or {}).get("fast") or {}
    require(
        set(models) == {"codex_gpt6_luna"}
        and model.get("provider") == "openai"
        and model.get("adapter") == "codex_cli"
        and model.get("model") == "gpt-6-luna"
        and model.get("allowed_profiles") == ["fast"]
        and (policy.get("adaptive_budget") or {}).get("enabled") is False
        and fast.get("planner") is False and fast.get("evaluator") is False
        and fast.get("reasoning_effort", {}).get("executor") == "medium"
        and fast.get("max_model_calls") == 2
        and fast.get("max_changed_files") == 2
        and fast.get("max_wall_time_minutes") <= 20
        and fast.get("hard_cost_usd") <= 0.50,
        "t02_model_budget_unreviewed",
    )
    c = d["compose"]
    contract = c.get("x-g1-t02-contract") or {}
    require(
        c.get("name") == "pcp-g1-t02"
        and contract.get("status") == "parked"
        and contract.get("allowed_project_id") == PROJECT
        and contract.get("accepted_smoke_job_reused") is False
        and contract.get("direct_control_separated") is True
        and all(contract.get(k) is False for k in (
            "model_dispatch_enabled", "independent_ddev_identities_proven",
            "provider_auth_provisioned", "provider_egress_domain_allowlist_proven",
            "github_token_repo_scope_proven", "github_delivery_enabled",
            "autonomous_e2e_proven", "benchmark_go"
        )),
        "t02_dispatch_not_parked",
    )
    services = c.get("services") or {}
    require(set(services) == SERVICES, "t02_services_changed")
    expected_nets = {
        "db": ["g1-t02-control"], "router": ["g1-t02-control"],
        "executor": ["g1-t02-control"], "runtime": ["g1-t02-control"],
        "direct": ["g1-t02-direct-control"],
    }
    for name, service in services.items():
        require(
            service.get("profiles") == ["g1-t02-parked"]
            and service.get("entrypoint") == ["/bin/false"]
            and service.get("restart") == "no"
            and service.get("read_only") is True
            and service.get("cap_drop") == ["ALL"]
            and service.get("security_opt") == ["no-new-privileges:true"]
            and service.get("networks") == expected_nets[name]
            and not service.get("ports")
            and not service.get("privileged")
            and not service.get("network_mode"),
            "t02_container_must_remain_inert",
        )
        mounts = service.get("volumes") or []
        require(isinstance(mounts, list), "t02_mounts_invalid")
        socket = any("/var/run/docker.sock" in str(x) for x in mounts)
        require(socket is (name == "executor"), "t02_docker_socket_boundary")
        require(
            (service.get("secrets") or []) ==
            (["g1_t02_repo_github_token"] if name == "executor" else []),
            "t02_github_secret_boundary",
        )
    nets = c.get("networks") or {}
    require(
        set(nets) == NETS
        and all(nets[n].get("name") == "pcp-" + n for n in NETS)
        and all(nets[n].get("internal") is True
                for n in {"g1-t02-control", "g1-t02-direct-control"})
        and all(nets[n].get("internal") is False for n in (
            NETS - {"g1-t02-control", "g1-t02-direct-control"}
        )),
        "t02_control_network_boundary",
    )
    volume = c.get("volumes") or {}
    require(
        set(volume) == {"g1-t02-db"}
        and volume["g1-t02-db"].get("name") == "pcp-g1-t02-postgres",
        "t02_database_scope",
    )
    require(set(c.get("secrets") or {}) == {"g1_t02_repo_github_token"},
            "t02_secret_singleton")
    for name in ("runtime", "executor"):
        env = services[name].get("environment") or {}
        require(
            env.get("PCP_TRUSTED_CODEX_BROKER_ENABLED") == ""
            and env.get("PCP_G1_T02_IDENTITY_ENABLED") == "",
            "t02_broker_not_disabled",
        )
    require(
        (services["runtime"].get("environment") or {}).get(
            "PCP_RUNTIME_STARTUP_MODE") == "inspect",
        "t02_runtime_not_inspect_only",
    )
    return {
        "status": "PASS_G1_T02_PARKED_PARTIAL_SOURCE",
        "model_calls": 0,
        "ready_for_model_dispatch": False,
        "ready_for_autonomous_e2e": False,
        "egress_activation": "NOT_REVIEWED",
    }


if __name__ == "__main__":
    try:
        print(json.dumps(validate(), sort_keys=True))
    except ParkedStop as exc:
        print(json.dumps({"status": "STOP_G1_T02_SOURCE", "reason": str(exc)}))
        raise SystemExit(2) from None
