#!/usr/bin/env python3
"""Verify the G0 fixture-only *source* contract; never start or configure services.

This is deliberately NOT a rollout/activation program. A future protected
activation must independently validate host-level Docker/DDEV capabilities.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


FIXTURE = "pcp-g0-drupal-fixture"
SEED = "39ef13c25b24c4a1b43a720ae53419f479996ed2"
BASELINE = "g0d01-seed-2026-10-10"
ROOT = Path(__file__).resolve().parents[1]
ISOLATED = Path("config/g0-fixture-only")

EXPECTED_CONTRACT = {
    "schema_version": 1,
    "authority": "proposal_only",
    "fixture": {
        "project_id": FIXTURE,
        "repository": "sonvhse06072/pcp-g0-drupal-fixture",
        "base_branch": "benchmark/pcp",
        "source_commit": SEED,
        "baseline_revision": BASELINE,
    },
    "activation": {
        "status": "parked",
        "runtime_startup_mode": "inspect",
        "start_services": False,
        "allow_real_jobs": False,
        "allow_ddev": False,
        "allow_docker_socket": False,
        "allow_github_delivery": False,
        "allow_pm_bridge": False,
        "allow_host_bridge": False,
        "allow_n8n": False,
        "require_owner_activation": True,
    },
    "separation": {
        "database_service": "pcp-g0d01-postgres",
        "database_volume": "pcp-g0d01-postgres-data",
        "database_host_port": None,
        "network": "pcp-g0d01-private",
        "workspace_root_suffix": "pcp-g0d01",
        "legacy_database_used": False,
        "legacy_project_registry_used": False,
        "shared_docker_host": True,
        "hard_isolation_verified": False,
    },
}


class UniqueKeyLoader(yaml.SafeLoader):
    """Treat ambiguous duplicate YAML keys as a failed source contract."""


def unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode) -> dict:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError("duplicate_yaml_key")
        result[key] = loader.construct_object(value_node)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping
)


def read_doc(root: Path, relative: str | Path) -> dict[str, Any]:
    source = (root / relative).resolve()
    if not source.is_relative_to(root.resolve()) or not source.is_file():
        raise ValueError("source_file_missing_or_outside_repository")
    doc = yaml.load(source.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    if not isinstance(doc, dict):
        raise ValueError("source_document_not_mapping")
    return doc


def only_fixture(doc: dict[str, Any]) -> dict[str, Any]:
    if doc.get("version") != 1 or set(doc) != {"version", "projects"}:
        raise ValueError("unexpected_registry_envelope")
    projects = doc.get("projects")
    if not isinstance(projects, dict) or set(projects) != {FIXTURE}:
        raise ValueError("g0_registry_not_fixture_only")
    item = projects[FIXTURE]
    if not isinstance(item, dict):
        raise ValueError("invalid_fixture_config")
    return item


def validate(root: Path = ROOT) -> dict[str, Any]:
    source_projects = read_doc(root, "config/projects.yml")
    source_baselines = read_doc(root, "config/project-baselines.yml")
    fixture_source = source_projects.get("projects", {}).get(FIXTURE)
    baseline_source = source_baselines.get("projects", {}).get(FIXTURE)
    if not isinstance(fixture_source, dict) or not isinstance(baseline_source, dict):
        raise ValueError("canonical_fixture_missing")

    staged_project = only_fixture(read_doc(root, ISOLATED / "projects.yml"))
    staged_baseline = only_fixture(read_doc(root, ISOLATED / "project-baselines.yml"))

    # Mirror only the already approved exact source; never create an alternative
    # baseline or quietly promote disabled capabilities to executable ones.
    if staged_project != fixture_source or staged_baseline != baseline_source:
        raise ValueError("fixture_source_registry_drift")
    if staged_project.get("path") != (
        "${CODING_PROJECTS_ROOT}/pcp-g0-fixtures/pcp-g0-drupal-fixture"
    ):
        raise ValueError("fixture_source_path_changed")
    if staged_project.get("base_branch") != "benchmark/pcp":
        raise ValueError("fixture_branch_changed")
    if staged_project.get("runtime", {}).get("workspace_mode") != "isolated_clone":
        raise ValueError("fixture_workspace_not_isolated")
    if staged_project.get("ddev", {}).get("enabled") is not False:
        raise ValueError("fixture_ddev_not_parked")
    for phase in ("preflight", "targeted_tests", "static_analysis", "full_tests", "cleanup"):
        if staged_project["ddev"].get(phase) != []:
            raise ValueError("parked_fixture_has_execution_phase")
    for enabled in ("allow_commit", "allow_push_ai_branch", "allow_create_pr",
                    "allow_auto_merge_low_risk", "allow_pm_merge", "allow_production_deploy"):
        if staged_project.get("autonomy", {}).get(enabled, False) is not False:
            raise ValueError("fixture_delivery_not_parked")

    if staged_baseline.get("active_revision") != BASELINE:
        raise ValueError("fixture_baseline_revision_drift")
    revisions = staged_baseline.get("revisions")
    if not isinstance(revisions, dict) or set(revisions) != {BASELINE}:
        raise ValueError("fixture_baseline_revisions_not_frozen")
    rev = revisions[BASELINE]
    if rev.get("status") != "approved" or rev.get("source_commit") != SEED:
        raise ValueError("fixture_baseline_seed_drift")

    if read_doc(root, ISOLATED / "pm-bridge.yml") != {
        "version": 1, "projects": {}
    }:
        raise ValueError("g0_pm_bridge_must_be_empty")
    if read_doc(root, ISOLATED / "source-contract.yml") != EXPECTED_CONTRACT:
        raise ValueError("g0_isolation_plan_changed_or_activated")

    return {
        "mode": "read_only_source_contract_validation",
        "result": "PASS",
        "project_id": FIXTURE,
        "source_sha": SEED,
        "fixture_only_registry": True,
        "separate_database_namespace_planned": True,
        "legacy_state_touched": False,
        "docker_or_ddev_invoked": False,
        "runtime_deployed": False,
        "executor_capability_verified": False,
        "ready_to_activate": False,
        "ready_to_dispatch_g0d_t01": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = validate(args.repo_root)
    except (ValueError, TypeError, KeyError, OSError, yaml.YAMLError):
        # No raw document contents, file paths, or project records in logs.
        print(json.dumps({
            "mode": "read_only_source_contract_validation",
            "result": "STOP",
            "ready_to_activate": False,
            "ready_to_dispatch_g0d_t01": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
