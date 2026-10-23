"""B2.2a PCP-local worker admission: pure, fail-closed and NEVER a dispatch.

This module is not wired to Runtime startup, a scheduled poller or any route.
All evidence dictionaries MUST be populated by trusted, independently checked
Runtime/Executor/provider sources; issue/model-authored evidence is untrusted.
A positive decision is NOT a job lease, model call or permission grant.
"""
from __future__ import annotations

import os
import re
from typing import Any

from .pcp_local_task_queue import (
    LocalSourceTask, PROJECT_ID, REPOSITORY, TaskStop, require,
)

RECEIPT_FIELDS = frozenset({
    "repository", "project_id", "issue_number", "task_key",
    "body_sha256", "base_sha", "baseline_revision",
    "baseline_source_commit", "goal_sha256", "allowed_paths",
    "state", "generation", "job_id",
})
PROJECT_FIELDS = frozenset({
    "project_id", "repository", "base_branch", "registered",
    "allow_create_pr", "allow_production_deploy",
})
BASELINE_FIELDS = frozenset({
    "project_id", "revision", "source_commit", "active_revision", "status",
})
ISOLATION_FIELDS = frozenset({
    "current_main_sha", "source_repo_clean", "workspace_mode",
    "workspace_lease_state", "active_writers", "other_repo_mounts",
    "agent_docker_socket", "isolated_ddev_network",
})
PROVIDER_FIELDS = frozenset({
    "adapter", "model", "effort", "installed_cli_version",
    "approved_cli_version", "credential_scoped", "github_token_in_agent",
    "host_keyring_mounted", "provider_network_reviewed",
})
BUDGET_FIELDS = frozenset({
    "owner_approved", "provider_quota_verified", "model_calls",
    "max_wall_seconds", "max_changed_files", "cash_ceiling_usd",
})
MODEL_RE = re.compile(r"gpt-[a-z0-9][a-z0-9._-]{2,63}\Z")
VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9.]+)?\Z")


def _exact(data: Any, keys: frozenset[str], code: str) -> dict[str, Any]:
    # Reject untrusted extra fields: especially secrets, arbitrary commands
    # and future privilege fields which are not part of this contract.
    require(type(data) is dict and set(data) == keys, code)
    return data


def _equal_typed(value: Any, expected: Any) -> bool:
    return type(value) is type(expected) and value == expected


def check_worker_admission(
    task: LocalSourceTask,
    *,
    receipt: dict[str, Any],
    project: dict[str, Any],
    baseline: dict[str, Any],
    isolation: dict[str, Any],
    provider: dict[str, Any],
    budget: dict[str, Any],
) -> dict[str, Any]:
    """Check authenticated *caller-supplied evidence*; perform NO side effects.

    This is NOT a safe substitute for verifying live state immediately before
    any future mutation. Both source and worker flags must be separately
    authorized, and they remain UNSET in the checked-in configuration.
    """
    require(
        os.getenv("PCP_LOCAL_TASK_SOURCE_ENABLED", "") == "owner-approved"
        and os.getenv("PCP_LOCAL_TASK_WORKER_ENABLED", "") == "owner-approved",
        "worker_flags_not_authorized",
    )
    require(isinstance(task, LocalSourceTask), "task_type_invalid")
    require(task.project_id == PROJECT_ID and task.repository == REPOSITORY,
            "task_project_not_approved")

    row = _exact(receipt, RECEIPT_FIELDS, "receipt_shape_invalid")
    expected = {
        "repository": task.repository,
        "project_id": task.project_id,
        "issue_number": task.issue_number,
        "task_key": task.task_key,
        "body_sha256": task.body_sha256,
        "base_sha": task.base_sha,
        "baseline_revision": task.baseline_revision,
        "baseline_source_commit": task.baseline_source_commit,
        "goal_sha256": task.goal_sha256,
        "allowed_paths": list(task.allowed_paths),
        "state": "pending",
        "generation": 0,
        "job_id": None,
    }
    require(all(_equal_typed(row[key], value)
                for key, value in expected.items()),
            "receipt_identity_or_generation_stale")

    p = _exact(project, PROJECT_FIELDS, "project_shape_invalid")
    require(
        p["project_id"] == PROJECT_ID
        and p["repository"] == REPOSITORY
        and p["base_branch"] == "main"
        and p["registered"] is True
        and p["allow_create_pr"] is True
        and p["allow_production_deploy"] is False,
        "project_authority_denied",
    )

    b = _exact(baseline, BASELINE_FIELDS, "baseline_shape_invalid")
    require(
        b["project_id"] == PROJECT_ID
        and b["revision"] == task.baseline_revision
        and b["active_revision"] == task.baseline_revision
        and b["source_commit"] == task.baseline_source_commit
        and b["status"] == "approved",
        "baseline_not_active_or_drifted",
    )

    i = _exact(isolation, ISOLATION_FIELDS, "isolation_shape_invalid")
    require(
        i["current_main_sha"] == task.base_sha
        and i["source_repo_clean"] is True
        and i["workspace_mode"] == "isolated_clone"
        and i["workspace_lease_state"] == "free"
        and type(i["active_writers"]) is int
        and i["active_writers"] == 0
        and i["other_repo_mounts"] is False
        and i["agent_docker_socket"] is False
        and i["isolated_ddev_network"] is True,
        "workspace_or_lease_not_attested",
    )

    model = _exact(provider, PROVIDER_FIELDS, "provider_shape_invalid")
    require(
        model["adapter"] == "codex_cli"
        and isinstance(model["model"], str)
        and MODEL_RE.fullmatch(model["model"]) is not None
        and isinstance(model["effort"], str)
        and model["effort"] in {"low", "medium", "high", "xhigh"}
        and isinstance(model["installed_cli_version"], str)
        and VERSION_RE.fullmatch(model["installed_cli_version"]) is not None
        and model["approved_cli_version"] == model["installed_cli_version"]
        and model["credential_scoped"] is True
        and model["github_token_in_agent"] is False
        and model["host_keyring_mounted"] is False
        and model["provider_network_reviewed"] is True,
        "provider_or_credential_not_attested",
    )

    limits = _exact(budget, BUDGET_FIELDS, "budget_shape_invalid")
    require(
        limits["owner_approved"] is True
        and limits["provider_quota_verified"] is True
        and type(limits["model_calls"]) is int
        and 1 <= limits["model_calls"] <= 2
        and type(limits["max_wall_seconds"]) is int
        and 60 <= limits["max_wall_seconds"] <= 900
        and type(limits["max_changed_files"]) is int
        and limits["max_changed_files"] == len(task.allowed_paths)
        and type(limits["cash_ceiling_usd"]) in {float, int}
        and 0 <= limits["cash_ceiling_usd"] <= 5,
        "budget_not_independently_approved",
    )

    # No unchecked bytes/goal, bearer, issue comments or agent tool output
    # may be reflected into an Owner/worker status response.
    return {
        "status": "ADMISSION_EVIDENCE_CHECKED_NOT_DISPATCHED",
        "project_id": PROJECT_ID,
        "repository": REPOSITORY,
        "issue_number": task.issue_number,
        "body_sha256": task.body_sha256,
        "base_sha": task.base_sha,
        "baseline_revision": task.baseline_revision,
        "receipt_generation": 0,
        "model": model["model"],
        "approved_cli_version": model["approved_cli_version"],
        "allowed_paths": list(task.allowed_paths),
        "model_calls_cap": limits["model_calls"],
        "max_wall_seconds": limits["max_wall_seconds"],
        "can_start_agent": False,
        "can_claim_lease": False,
        "can_publish_or_merge": False,
        "requires_fresh_live_recheck": True,
        "model_calls_executed": 0,
    }
