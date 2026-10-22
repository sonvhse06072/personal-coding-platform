"""Mandatory exact-HEAD hosted CI contract for a FUTURE isolated PCP fixture.

No GitHub requests, provider calls, legacy PCP database, Docker or Chợ Nhạc.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from app.delivery import DeliveryError, deliver_verified_work
from app.required_ci import (
    FULLPATH_FIXTURE_REPO,
    FULLPATH_WORKFLOW,
    required_ci_for_project,
    required_github_actions_pass,
)
from app.fullpath_fixture_safety import PROJECT_ID
from test_delivery import FakeDdev, common_kwargs


HEAD = "b" * 40
REQUIRED = (FULLPATH_FIXTURE_REPO, FULLPATH_WORKFLOW)
PERMISSIONS = {"push_ai_branch": True, "create_pr": True}


def ci_evidence(*, commit=HEAD, repo=FULLPATH_FIXTURE_REPO, workflow="validation"):
    return {
        "state": "success",
        "repository": repo,
        "commit": commit,
        "actions_runs": [{
            "source": "github_actions",
            "id": 101,
            "run_id": 101,
            "name": workflow,
            "head_sha": commit,
            "status": "completed",
            "conclusion": "success",
            "details_url": (
                "https://github.com/" + repo + "/actions/runs/101"
            ),
        }],
        "effective_failures": [],
        "trusted_contract_invalid": False,
        "trusted_order_ambiguous": False,
    }


def test_only_the_new_fixture_uses_mandatory_ci():
    assert required_ci_for_project(PROJECT_ID) == REQUIRED
    for project_id in ("demo", "chonhac", "pcp-g0-drupal-fixture", "", "default"):
        assert required_ci_for_project(project_id) is None


def test_genuine_ci_run_on_exact_head_qualifies():
    assert required_github_actions_pass(
        ci_evidence(), repository=REQUIRED[0],
        commit=HEAD, workflow_name=REQUIRED[1],
    )


@pytest.mark.parametrize("mutate", [
    lambda d: d.update({"state": "none"}),
    lambda d: d.update({"state": "pending"}),
    lambda d: d.update({"commit": "a"*40}),
    lambda d: d.update({"repository": "another/repo"}),
    lambda d: d.update({"actions_runs": []}),
    lambda d: d.update({"actions_runs": "not-list"}),
    lambda d: d["actions_runs"][0].update({"name": "unrelated-ci"}),
    lambda d: d["actions_runs"][0].update({"head_sha": "a"*40}),
    lambda d: d["actions_runs"][0].update({"source": "commit_status"}),
    lambda d: d["actions_runs"][0].update({"conclusion": "cancelled"}),
    lambda d: d["actions_runs"][0].update({"status": "in_progress"}),
    lambda d: d["actions_runs"][0].update({"run_id": False}),
    lambda d: d["actions_runs"][0].update({"id": True}),
    lambda d: d["actions_runs"][0].update({"details_url": "http://github.com/foo"}),
    lambda d: d["actions_runs"][0].update({
        "details_url": "https://github.com/other/repo/actions/runs/101"}),
    lambda d: d["actions_runs"][0].update({
        "details_url": "https://github.com/sonvhse06072/pcp-g0-fullpath-fixture/actions/runs/101?x=y"}),
    lambda d: d.update({"trusted_contract_invalid": True}),
    lambda d: d.update({"trusted_order_ambiguous": True}),
    lambda d: d.update({"effective_failures": [{"name": "quality"}]}),
    lambda d: d["actions_runs"].append(deepcopy(d["actions_runs"][0])),
])
def test_missing_foreign_spoofed_or_ambiguous_ci_cannot_pass(mutate):
    evidence = ci_evidence()
    mutate(evidence)
    assert not required_github_actions_pass(
        evidence, repository=REQUIRED[0],
        commit=HEAD, workflow_name=REQUIRED[1],
    )


@pytest.mark.parametrize("repository,sha,name", [
    ("", HEAD, "validation"),
    ("../repo", HEAD, "validation"),
    (FULLPATH_FIXTURE_REPO, "short", "validation"),
    (FULLPATH_FIXTURE_REPO, HEAD, ""),
    (FULLPATH_FIXTURE_REPO, HEAD, "invalid/name"),
])
def test_invalid_required_identity_fails(repository, sha, name):
    assert not required_github_actions_pass(
        ci_evidence(), repository=repository, commit=sha,
        workflow_name=name,
    )


def _run(states, *, permissions=None, reconcile=False, reconciled=None):
    ddev = FakeDdev(
        ci_states=states,
        reconcile_result=reconciled,
    )
    kwargs = common_kwargs(ddev, PERMISSIONS if permissions is None else permissions)
    kwargs["required_ci"] = REQUIRED
    kwargs["reconcile_existing"] = reconcile
    return ddev, asyncio.run(deliver_verified_work(**kwargs))


def test_strict_delivery_waits_then_accepts_only_exact_hosted_ci():
    ddev, outcome = _run(["pending", ci_evidence()])
    assert outcome["state"] == "ci_success"
    assert outcome["ci"]["actions_runs"][0]["head_sha"] == HEAD
    assert [x[0] for x in ddev.calls] == [
        "publish", "pr", "ci", "ci",
    ]


@pytest.mark.parametrize("ci", [
    "none", "success",
    {"state": "success", "repository": FULLPATH_FIXTURE_REPO},
    {**ci_evidence(), "actions_runs": []},
    {**ci_evidence(), "actions_runs": [{**ci_evidence()["actions_runs"][0],
                                       "head_sha": "a"*40}]},
    {**ci_evidence(), "state": "success",
     "actions_runs": [{**ci_evidence()["actions_runs"][0], "name": "other"}]},
])
def test_required_delivery_never_accepts_missing_or_generic_ci(ci):
    ddev = FakeDdev([ci])
    kwargs = common_kwargs(ddev, PERMISSIONS)
    kwargs["required_ci"] = REQUIRED
    with pytest.raises(DeliveryError, match="CI|workflow"):
        asyncio.run(deliver_verified_work(**kwargs))


@pytest.mark.parametrize("permissions", [
    {"push_ai_branch": False, "create_pr": True},
    {"push_ai_branch": True, "create_pr": False},
    {"push_ai_branch": False, "create_pr": False},
])
def test_required_ci_rejects_disabled_publishing_before_side_effects(permissions):
    ddev = FakeDdev()
    kwargs = common_kwargs(ddev, permissions)
    kwargs["required_ci"] = REQUIRED
    with pytest.raises(DeliveryError) as failure:
        asyncio.run(deliver_verified_work(**kwargs))
    assert failure.value.reason == "required_hosted_ci_unavailable"
    assert ddev.calls == []


def test_reconciliation_must_prove_exact_ci_not_only_existing_pr():
    data = {"reconciled": True, "delivery": {
        "number": 77, "ci": {"state": "success", "commit": HEAD},
    }}
    ddev = FakeDdev(reconcile_result=data)
    kwargs = common_kwargs(ddev, PERMISSIONS)
    kwargs.update({"required_ci": REQUIRED, "reconcile_existing": True})
    with pytest.raises(DeliveryError) as failure:
        asyncio.run(deliver_verified_work(**kwargs))
    assert failure.value.reason == "required_exact_ci_unproven"
    assert [x[0] for x in ddev.calls] == ["reconcile"]


def test_reconciliation_with_real_hosted_ci_can_pass():
    data = {"reconciled": True, "delivery": {
        "number": 77, "ci": ci_evidence(),
    }}
    ddev = FakeDdev(reconcile_result=data)
    kwargs = common_kwargs(ddev, PERMISSIONS)
    kwargs.update({"required_ci": REQUIRED, "reconcile_existing": True})
    result = asyncio.run(deliver_verified_work(**kwargs))
    assert result["state"] == "ci_success"
    assert result["reconciled_external_merge"] is True
    assert [x[0] for x in ddev.calls] == ["reconcile"]


def test_legacy_ci_none_behavior_is_unchanged():
    ddev = FakeDdev(["none"])
    kwargs = common_kwargs(ddev, PERMISSIONS)
    result = asyncio.run(deliver_verified_work(**kwargs))
    assert result["state"] == "ci_none"

def test_g1_t02_requires_distinct_workflow_dispatch_policy():
    from app.required_ci import (
        G1_T02_PROJECT, G1_T02_DISPATCH_POLICY, G1_T02_FIXTURE_REPO,
        required_ci_for_project, required_github_actions_pass,
    )
    assert required_ci_for_project(G1_T02_PROJECT) == (
        G1_T02_FIXTURE_REPO, G1_T02_DISPATCH_POLICY,
    )
    assert required_ci_for_project(PROJECT_ID) == REQUIRED
    proof = {
        "state": "success", "repository": G1_T02_FIXTURE_REPO,
        "commit": HEAD,
        "g1_t02_dispatch": {
            "verdict": "CI_VERIFIED_WAITING_PM_REVIEW",
            "source_sha": "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3",
            "candidate_sha": HEAD,
            "workflow_blob_sha": "a098e80472afc8dc628723bd26cc72204d8f3faf",
            "workflow_run_id": 312,
            "workflow_run_head_sha": "c" * 40,
            "job_id": "f" * 32, "branch": "ai/" + "f" * 12,
            "repository": G1_T02_FIXTURE_REPO,
        },
    }
    assert required_github_actions_pass(
        proof, repository=G1_T02_FIXTURE_REPO,
        commit=HEAD, workflow_name=G1_T02_DISPATCH_POLICY,
    )
    proof["g1_t02_dispatch"]["candidate_sha"] = "0" * 40
    assert not required_github_actions_pass(
        proof, repository=G1_T02_FIXTURE_REPO,
        commit=HEAD, workflow_name=G1_T02_DISPATCH_POLICY,
    )
