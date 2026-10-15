"""G1-T01 parked capsule: no Docker/HTTP/provider or model execution in tests."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g1-pilot-source-contract.py"
spec = importlib.util.spec_from_file_location("g1_pilot_source_contract", SCRIPT)
assert spec and spec.loader
g1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g1)


def test_reviewed_capsule_is_strictly_parked_and_model_is_singleton():
    verdict = g1.validate(ROOT)
    assert verdict["status"] == "PASS_G1_PILOT_SOURCE_PARKED"
    assert verdict["model"] == "gpt-6-luna"
    assert verdict["reasoning"] == "medium"
    assert verdict["ready_for_model_dispatch"] is False
    assert verdict["ready_for_autonomous_e2e"] is False
    assert verdict["model_calls"] == 0
    assert sorted(verdict["pilot_services"]) == [
        "db", "direct", "executor", "router", "runtime",
    ]


@pytest.fixture
def capsule(tmp_path):
    for path in (g1.COMPOSE, g1.MODELS, g1.POLICY, g1.TEMPLATE,
                 g1.EGRESS, g1.PROXY_SOURCE):
        source, dest = ROOT / path, tmp_path / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    assert g1.validate(tmp_path)["ready_for_model_dispatch"] is False
    return tmp_path


def mutate(root, path, callback):
    file = root / path
    doc = yaml.safe_load(file.read_text(encoding="utf-8"))
    callback(doc)
    file.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


@pytest.mark.parametrize("path,change,blocker", [
    (g1.COMPOSE,
     lambda v: v["services"]["runtime"].update(entrypoint=["uvicorn"]),
     "g1_pilot_service_not_inert_or_isolated"),
    (g1.COMPOSE,
     lambda v: v["services"]["runtime"]["environment"].update(
         PCP_RUNTIME_STARTUP_MODE="normal"),
     "g1_pilot_runtime_not_default_off"),
    (g1.COMPOSE,
     lambda v: v["services"]["executor"]["environment"].update(
         PCP_G1_PILOT_IDENTITY_ENABLED="owner-approved"),
     "g1_pilot_runtime_not_default_off"),
    (g1.TEMPLATE,
     lambda v: v["projects"].update({"chonhac": {}}),
     "g1_pilot_project_template_not_singleton"),
    (g1.TEMPLATE,
     lambda v: v["projects"]["pcp-benchmark-g1-pilot"]["runtime"].update(
         pilot_identity="g1-t02"),
     "g1_pilot_project_template_scope_broadened"),
    (g1.TEMPLATE,
     lambda v: v["projects"]["pcp-benchmark-g1-pilot"][
         "trusted_codex_tools"].update(
         frontend_quality=[["ddev", "exec", "bash", "docker ps"]]),
     "g1_pilot_project_phase_command_drift"),
    (g1.COMPOSE,
     lambda v: v["services"]["executor"]["environment"].update(
         PCP_TRUSTED_CODEX_BROKER_ENABLED="owner-approved"),
     "g1_pilot_runtime_not_default_off"),
    (g1.COMPOSE,
     lambda v: v["networks"]["g1-pilot-control"].update(internal=False),
     "g1_pilot_control_network_not_internal"),
    (g1.COMPOSE,
     lambda v: v["services"]["direct"]["networks"].append(
         "g1-pilot-control"),
     "g1_pilot_service_not_inert_or_isolated"),
    (g1.COMPOSE,
     lambda v: v["services"]["runtime"]["networks"].append(
         "g1-pilot-github-egress"),
     "g1_pilot_service_not_inert_or_isolated"),
    (g1.COMPOSE,
     lambda v: v["services"]["direct"]["networks"].append(
         "g1-pilot-direct-provider-egress"),
     "g1_pilot_service_not_inert_or_isolated"),
    (g1.COMPOSE,
     lambda v: v["networks"]["g1-pilot-direct-control"].update(internal=False),
     "g1_pilot_control_network_not_internal"),
    (g1.EGRESS,
     lambda v: v["services"]["runtime"]["networks"].append(
         "g1-pilot-provider-egress"),
     "g1_pilot_client_proxy_not_scoped"),
    (g1.EGRESS,
     lambda v: v["services"]["direct"]["environment"].update(
         HTTPS_PROXY="http://g1-pilot-provider-proxy:3128"),
     "g1_pilot_client_proxy_not_scoped"),
    (g1.EGRESS,
     lambda v: v["services"]["g1-pilot-provider-proxy"].update(
         entrypoint=["python3"]),
     "g1_pilot_proxy_identity_changed"),
    (g1.EGRESS,
     lambda v: v["services"]["g1-pilot-github-proxy"]["environment"].update(
         G1_EGRESS_ROLE="provider"),
     "g1_pilot_proxy_identity_changed"),
    (g1.EGRESS,
     lambda v: v["x-g1-pilot-egress-contract"].update(
         activation_approved=True),
     "g1_pilot_egress_overlay_not_parked"),
    (g1.COMPOSE,
     lambda v: v["services"]["runtime"].update(
         secrets=["g1_pilot_repo_github_token"]),
     "g1_pilot_github_secret_scope_broken"),
    (g1.COMPOSE,
     lambda v: v["services"]["direct"]["volumes"].append({
         "type": "bind", "source": "/var/run/docker.sock",
         "target": "/var/run/docker.sock",
     }),
     "g1_pilot_docker_socket_scope_broken"),
    (g1.COMPOSE,
     lambda v: v["x-g1-pilot-contract"].update(
         model_dispatch_enabled=True),
     "g1_pilot_activation_gate_bypassed"),
    (g1.COMPOSE,
     lambda v: v["x-g1-pilot-contract"].update(
         accepted_smoke_job_reused=True),
     "g1_pilot_project_identity_not_parked"),
    (g1.COMPOSE,
     lambda v: v["services"]["db"]["labels"].update(
         {"pcp.scope": "f2-c3b-one-job"}),
     "g1_pilot_service_scope_label_invalid"),
    (g1.COMPOSE,
     lambda v: v["volumes"]["g1-pilot-db"].update(
         name="pcp-g1-smoke-postgres"),
     "g1_pilot_db_volume_collision"),
    (g1.MODELS,
     lambda v: v["models"].update({
         "frontier_codex": dict(v["models"]["codex_gpt6_luna"])
     }),
     "g1_pilot_model_allowlist_changed"),
    (g1.MODELS,
     lambda v: v["models"]["codex_gpt6_luna"].update(model="gpt-6-astra"),
     "g1_pilot_model_identity_or_privacy_changed"),
    (g1.MODELS,
     lambda v: v["models"]["codex_gpt6_luna"].update(
         allowed_profiles=["fast", "critical"]),
     "g1_pilot_model_identity_or_privacy_changed"),
    (g1.POLICY,
     lambda v: v["profiles"]["fast"]["reasoning_effort"].update(
         executor="high"),
     "g1_pilot_budget_or_effort_broadened"),
    (g1.POLICY,
     lambda v: v["profiles"]["fast"].update(max_model_calls=3),
     "g1_pilot_budget_or_effort_broadened"),
    (g1.POLICY,
     lambda v: v["profiles"]["fast"].update(max_changed_files=4),
     "g1_pilot_budget_or_effort_broadened"),
])
def test_drift_always_refuses_pilot_admission(capsule, path, change, blocker):
    mutate(capsule, path, change)
    with pytest.raises(g1.PilotStop, match=blocker):
        g1.validate(capsule)


def test_missing_or_broken_source_cannot_count_as_readiness(capsule):
    (capsule / g1.MODELS).unlink()
    with pytest.raises(g1.PilotStop, match="g1_pilot_source_file_missing"):
        g1.validate(capsule)
    (capsule / g1.MODELS).write_text("models: [bad]", encoding="utf-8")
    with pytest.raises(g1.PilotStop, match="g1_pilot_model_allowlist_changed"):
        g1.validate(capsule)


def test_all_credential_paths_are_new_and_provider_egress_is_not_allowlist():
    compose = yaml.safe_load((ROOT / g1.COMPOSE).read_text())
    assert compose["x-g1-pilot-contract"]["provider_egress_domain_allowlist_proven"] is False
    assert compose["x-g1-pilot-contract"]["provider_auth_provisioned"] is False
    assert compose["x-g1-pilot-contract"]["github_token_repo_scope_proven"] is False
    names = [v["name"] for v in compose["networks"].values()]
    assert all(x.startswith("pcp-g1-pilot-") for x in names)
    assert "pcp-g1-smoke-control" not in names
    assert compose["services"]["executor"]["networks"] == ["g1-pilot-control"]
    assert compose["services"]["runtime"]["networks"] == ["g1-pilot-control"]
    assert compose["services"]["direct"]["networks"] == ["g1-pilot-direct-control"]
    assert compose["networks"]["g1-pilot-direct-control"]["internal"] is True
    assert compose["services"]["runtime"]["environment"]["CODEX_HOME"] != (
        compose["services"]["direct"]["environment"]["CODEX_HOME"]
    )
    # The parked execution topology cannot be started by a profile alone.
    assert all(x["entrypoint"] == ["/bin/false"]
               for x in compose["services"].values())


def test_doc_task_scoped_and_no_automatic_launch_commands():
    body = (ROOT / "docs/project/history/g1-pilot-t01-parked-2026-10-15.md").read_text()
    for term in (
        "intersectionMinutes", "benchmark/g1-codex-smoke-v1",
        "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3",
        "NOT PROVEN", "HOLD / NOT GO", "PCP_RUNTIME_STARTUP_MODE=inspect",
    ):
        assert term in body
    assert "docker compose up" not in body
    assert "codex exec" not in body
