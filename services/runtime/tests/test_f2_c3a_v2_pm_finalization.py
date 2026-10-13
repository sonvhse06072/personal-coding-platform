"""F2 v2 PM closeout needs exact-hosted-CI and separately active source authority."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest

from app import fullpath_pm_review as pm
from app import fullpath_worker_only as worker
import test_g0_fullpath_pm_review as v1


def environment(monkeypatch):
    env = v1.safe_env()
    env.update({
        "PCP_RUNTIME_STARTUP_MODE": worker.F2_WORKER_MODE,
        "PCP_F2_WORKER_ONLY_ENABLED": "owner-approved",
    })
    real_exists = Path.exists
    monkeypatch.setattr(
        worker.Path, "exists",
        lambda self: False if str(self) == "/var/run/docker.sock"
        else real_exists(self),
    )
    monkeypatch.setattr(pm.os.path, "exists", lambda _path: False)
    return env


def prepared():
    request = v1.request(
        source_commit=worker.F2_V2_SEED,
        baseline_revision=worker.F2_V2_REVISION,
    )
    row = v1.job()
    row["source_commit"] = worker.F2_V2_SEED
    row["checkpoint"]["project_baseline"].update({
        "revision": worker.F2_V2_REVISION, "source_commit": worker.F2_V2_SEED,
    })
    row["result"]["delivery"]["pull_request"]["base_ref"] = "benchmark/fullpath-v2"
    row["result"]["diff"]["changed_files"] = [
        "web/modules/custom/pcp_f2_fixture/src/WindowOverlapDetector.php",
    ]
    gh = v1.FakeExecutor()
    gh.pr["base_ref"] = "benchmark/fullpath-v2"
    gh.review["body"] = v1.review_body(
        source_commit=worker.F2_V2_SEED,
        baseline_revision=worker.F2_V2_REVISION,
    )
    return request, row, gh


def f2_service(monkeypatch, *, active=True):
    request, row, gh = prepared()
    project = v1.fake_project()
    project["base_branch"] = "benchmark/fullpath-v2"
    db = v1.MemoryDB(row)
    monkeypatch.setattr(pm, "projects_doc", lambda: {"projects": {pm.PROJECT_ID: project}})
    monkeypatch.setattr(pm, "project_config", lambda _: project)
    monkeypatch.setattr(pm, "project_baselines_doc", lambda: {
        "projects": {pm.PROJECT_ID: {
            "active_revision": worker.F2_V2_REVISION if active else None,
        }},
    })
    monkeypatch.setattr(
        pm, "resolve_project_baseline",
        lambda *_args: SimpleNamespace(
            revision=worker.F2_V2_REVISION,
            source_commit=worker.F2_V2_SEED,
        ),
    )
    return request, db, gh


def test_f2_worker_pm_requires_exact_env_and_separate_review_switch(monkeypatch):
    env = environment(monkeypatch)
    pm.require_isolated_review_environment(env)
    for k, bad in (
        ("PCP_F2_WORKER_ONLY_ENABLED", ""),
        ("PCP_FULLPATH_PM_FINALIZATION_ENABLED", ""),
        ("DATABASE_URL", "postgresql://legacy:pw@db:5432/legacy"),
        ("GITHUB_DELIVERY_TOKEN", "foreign"),
        ("PCP_RUNTIME_STARTUP_MODE", "g0_fullpath_candidate"),
    ):
        with pytest.raises(RuntimeError):
            pm.require_isolated_review_environment({**env, k: bad})


def test_worker_pm_route_is_exact_and_additional_approval_required(monkeypatch):
    path = "/v1/g0-fullpath/jobs/" + v1.JOB + "/pm-review"
    monkeypatch.delenv("PCP_FULLPATH_PM_FINALIZATION_ENABLED", raising=False)
    assert worker.f2_direct_intake_route_allowed("POST", path) is False
    monkeypatch.setenv("PCP_FULLPATH_PM_FINALIZATION_ENABLED", "owner-approved")
    assert worker.f2_direct_intake_route_allowed("POST", path) is True
    assert worker.f2_direct_intake_route_allowed("GET", path) is False
    for forbidden in (
        "/v1/g0-fullpath/jobs/garbage/pm-review",
        "/v1/g0-fullpath/jobs/" + v1.JOB + "/cancel",
        "/v1/orchestrator/tick",
    ):
        assert not worker.f2_direct_intake_route_allowed("POST", forbidden)


def test_old_v1_pr_base_cannot_finalize_a_v2_job():
    request, row, gh = prepared()
    pm.require_eligible_job(
        row, request, job_id=v1.JOB, baseline_source=worker.F2_V2_SEED,
        expected_base_branch="benchmark/fullpath-v2",
    )
    proof = pm.validate_live_proof(
        row, request, job_id=v1.JOB, reviewer_login=v1.REVIEWER,
        pr=gh.pr, ci=gh.ci, review=gh.review,
        expected_base_branch="benchmark/fullpath-v2",
    )
    assert proof["review_id"] == 7
    row["result"]["delivery"]["pull_request"]["base_ref"] = "benchmark/fullpath"
    with pytest.raises(RuntimeError, match="job_not_eligible"):
        pm.require_eligible_job(
            row, request, job_id=v1.JOB, baseline_source=worker.F2_V2_SEED,
            expected_base_branch="benchmark/fullpath-v2",
        )
    wrong_pr = deepcopy(gh.pr)
    wrong_pr["base_ref"] = "benchmark/fullpath"
    with pytest.raises(RuntimeError, match="github_identity"):
        pm.validate_live_proof(
            row, request, job_id=v1.JOB, reviewer_login=v1.REVIEWER,
            pr=wrong_pr, ci=gh.ci, review=gh.review,
            expected_base_branch="benchmark/fullpath-v2",
        )


def test_v2_review_completes_only_after_ci_and_genuine_owner_review(monkeypatch):
    env = environment(monkeypatch)
    request, db, gh = f2_service(monkeypatch, active=True)
    result = asyncio.run(
        pm.FullpathPMReviewService(db, gh).finalize(v1.JOB, request, env=env)
    )
    assert result["status"] == "completed"
    assert result["github_pr_merged"] is False
    assert db.commits == 1
    assert gh.calls == ["pr", "ci", "review"]
    assert db.row["checkpoint"]["fullpath_pm_review"]["baseline_revision"] == (
        worker.F2_V2_REVISION
    )


def test_v2_review_inactive_baseline_stops_before_job_or_github(monkeypatch):
    env = environment(monkeypatch)
    request, db, gh = f2_service(monkeypatch, active=False)
    with pytest.raises(RuntimeError, match="baseline_still_inactive"):
        asyncio.run(
            pm.FullpathPMReviewService(db, gh).finalize(v1.JOB, request, env=env)
        )
    assert db.commits == 0 and gh.calls == []


def test_wrong_v1_request_stops_before_job_or_github(monkeypatch):
    env = environment(monkeypatch)
    _, db, gh = f2_service(monkeypatch, active=True)
    with pytest.raises(RuntimeError, match="v2_source_revision_mismatch"):
        asyncio.run(
            pm.FullpathPMReviewService(db, gh).finalize(
                v1.JOB, v1.request(), env=env,
            )
        )
    assert db.commits == 0 and gh.calls == []


def test_v1_default_still_requires_old_base_branch():
    pm.require_eligible_job(
        v1.job(), v1.request(), job_id=v1.JOB, baseline_source=v1.SOURCE,
    )
    old = v1.job()
    old["result"]["delivery"]["pull_request"]["base_ref"] = "benchmark/fullpath-v2"
    with pytest.raises(RuntimeError, match="job_not_eligible"):
        pm.require_eligible_job(
            old, v1.request(), job_id=v1.JOB, baseline_source=v1.SOURCE,
        )
