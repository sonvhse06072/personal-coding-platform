"""F2d-04B-02: privileged GitHub API operations reject foreign repositories.

No GitHub account, token, network, Docker, model or workspace operation is used.
The existing F2 HTTP boundary stays fully PARKED.
"""
from __future__ import annotations

import pytest

from app.github_delivery import GitHubDelivery


REPOSITORY = "sonvhse06072/pcp-g0-fullpath-fixture"
FOREIGN = "sonvhse06072/chonhac"
SHA = "a" * 40


def scoped():
    return GitHubDelivery(token="synthetic-not-a-credential", repository_scope=REPOSITORY)


def operations_for(repository: str):
    """Every network-bearing public delivery method needs a repository."""
    return (
        lambda d: d.assert_branch_commit(repository, "ai/test", SHA),
        lambda d: d.verify_review_repair(
            repository=repository, job_id="a" * 32, pr_number=1,
            branch="ai/test", base_branch="benchmark/fullpath",
            source_commit="b" * 40, expected_commit=SHA,
        ),
        lambda d: d.upsert_pull_request(
            repository=repository, job_id="a" * 32, branch="ai/test",
            base_branch="benchmark/fullpath", expected_commit=SHA,
            title="Test", body="Synthetic",
        ),
        lambda d: d.reconcile_merged_delivery(
            repository=repository, job_id="a" * 32,
            branch="ai/test", base_branch="benchmark/fullpath",
            source_commit="b" * 40, expected_commit=SHA,
        ),
        lambda d: d.ci_status(repository=repository, commit=SHA),
    )


@pytest.mark.parametrize("operation", range(5))
@pytest.mark.parametrize("foreign", [
    FOREIGN, "sonvhse06072/personal-coding-platform",
    "sonvhse06072/pcp-g0-drupal-fixture",
    "another-owner/pcp-g0-fullpath-fixture",
])
def test_scoped_client_blocks_foreign_repo_before_credential_use(
    monkeypatch, operation, foreign,
):
    delivery = scoped()
    monkeypatch.setattr(
        delivery, "_client",
        lambda: pytest.fail("Out-of-scope API must not open an HTTP client"),
    )
    with pytest.raises(RuntimeError, match="outside authorized scope"):
        operations_for(foreign)[operation](delivery)


@pytest.mark.parametrize("bad", [
    "", "https://github.com/sonvhse06072/pcp-g0-fullpath-fixture",
    "sonvhse06072/pcp-g0-fullpath-fixture/other",
    "sonvhse06072/*", "sonvhse06072/repo?branch=main",
    "sonvhse06072/repo\n", "sonvhse06072\\repo", "../legacy",
])
def test_scope_cannot_be_url_glob_multi_repo_or_whitespace(bad):
    with pytest.raises(ValueError, match="Invalid GitHub repository scope"):
        GitHubDelivery(token="synthetic", repository_scope=bad)


@pytest.mark.parametrize("bad", [
    "", "https://github.com/sonvhse06072/pcp-g0-fullpath-fixture",
    "sonvhse06072/pcp-g0-fullpath-fixture/other",
    "sonvhse06072/pcp-g0-fullpath-fixture?x=1",
    "sonvhse06072/..", None, 12, {}, "../legacy",
])
def test_scoped_client_rejects_invalid_repository_without_network(
    monkeypatch, bad,
):
    delivery = scoped()
    monkeypatch.setattr(
        delivery, "_client",
        lambda: pytest.fail("Invalid repo may not open an HTTP client"),
    )
    with pytest.raises(RuntimeError, match="Invalid GitHub delivery repository"):
        delivery.ci_status(repository=bad, commit=SHA)


@pytest.mark.parametrize("op", range(5))
def test_allowed_repository_can_reach_normal_client_boundary(monkeypatch, op):
    delivery = scoped()
    touched = []

    def fake_network():
        touched.append("client")
        raise RuntimeError("sentinel: approved network boundary reached")

    monkeypatch.setattr(delivery, "_client", fake_network)
    with pytest.raises(RuntimeError, match="sentinel"):
        operations_for(REPOSITORY)[op](delivery)
    assert touched == ["client"]


def test_scope_is_case_insensitive_but_cannot_change_repository():
    delivery = scoped()
    delivery._require_repository_scope("SONVHSE06072/PCP-G0-FULLPATH-FIXTURE")
    with pytest.raises(RuntimeError, match="outside authorized scope"):
        delivery._require_repository_scope("sonvhse06072/pcp-g0-drupal-fixture")


def test_legacy_unscoped_delivery_client_preserves_original_contract():
    legacy = GitHubDelivery(token="synthetic")
    assert legacy.repository_scope is None
    for repo in (FOREIGN, "sonvhse06072/personal-coding-platform", REPOSITORY):
        legacy._require_repository_scope(repo)
    assert legacy.configured is True


def test_scoped_restriction_does_not_authorize_f2_runtime():
    delivery = scoped()
    assert delivery.configured is True  # synthetic instance only
    assert delivery.repository_scope == REPOSITORY
    # No F2 Executor endpoint uses this optional repository-scoped client yet;
    # it cannot create a token, provision a service, or change parked status.
    assert not hasattr(delivery, "activate_f2")
    assert not hasattr(delivery, "deploy")
