from copy import deepcopy

import httpx
import pytest
from fastapi import HTTPException

from app.github_delivery import GitHubDelivery
from app import main


SOURCE = "a" * 40
HEAD = "b" * 40


def pull_request():
    return {
        "number": 42,
        "state": "open",
        "merged": False,
        "merged_at": None,
        "html_url": "https://github.com/acme/demo/pull/42",
        "body": "Automated coding-platform delivery.\n\n- Job: `job12345`",
        "head": {
            "sha": HEAD,
            "ref": "ai/job12345",
            "repo": {"full_name": "acme/demo"},
        },
        "base": {
            "ref": "main",
            "repo": {"full_name": "acme/demo"},
        },
    }


def delivery_with_pull(monkeypatch, raw_pull, *, branch_head=HEAD, source_ok=True):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/acme/demo/pulls/42":
            return httpx.Response(200, json=raw_pull)
        if path == "/repos/acme/demo/git/ref/heads/ai/job12345":
            return httpx.Response(200, json={"object": {"sha": branch_head}})
        if path == f"/repos/acme/demo/compare/{SOURCE}...{HEAD}":
            return httpx.Response(
                200,
                json={
                    "status": "ahead" if source_ok else "diverged",
                    "merge_base_commit": {"sha": SOURCE if source_ok else "f" * 40},
                },
            )
        raise AssertionError(f"unexpected GitHub request: {request.url}")

    delivery = GitHubDelivery("token")
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        delivery,
        "_client",
        lambda: httpx.Client(transport=transport, headers=delivery.headers),
    )
    return delivery


def verify(delivery):
    return delivery.verify_review_repair(
        repository="acme/demo",
        job_id="job12345",
        pr_number=42,
        branch="ai/job12345",
        base_branch="main",
        source_commit=SOURCE,
        expected_commit=HEAD,
    )


def test_review_repair_verifies_exact_open_unmerged_pr_head_and_ancestry(monkeypatch):
    result = verify(delivery_with_pull(monkeypatch, pull_request()))

    assert result["number"] == 42
    assert result["head"] == HEAD
    assert result["head_ref"] == "ai/job12345"
    assert result["base_ref"] == "main"
    assert result["merged"] is False
    assert result["ancestry"]["merge_base"] == SOURCE


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda raw: raw["head"].update(sha="c" * 40), "head moved"),
        (lambda raw: raw["head"].update(ref="ai/other-job"), "head branch"),
        (lambda raw: raw["base"].update(ref="develop"), "base branch"),
        (lambda raw: raw.update(state="closed"), "open, unmerged"),
        (lambda raw: raw.update(merged=True, merged_at="2026-09-29T00:00:00Z"), "open, unmerged"),
        (lambda raw: raw.update(body="unbound PR"), "exact Runtime job"),
    ],
)
def test_review_repair_rejects_moved_or_mismatched_pr(monkeypatch, mutation, message):
    raw = deepcopy(pull_request())
    mutation(raw)
    delivery = delivery_with_pull(monkeypatch, raw)

    with pytest.raises(RuntimeError, match=message):
        verify(delivery)


def test_review_repair_rejects_moved_branch_or_invalid_source_relationship(monkeypatch):
    with pytest.raises(RuntimeError, match="Published GitHub branch moved"):
        verify(delivery_with_pull(monkeypatch, pull_request(), branch_head="c" * 40))

    with pytest.raises(RuntimeError, match="not descended"):
        verify(delivery_with_pull(monkeypatch, pull_request(), source_ok=False))


def test_exact_review_repair_upsert_updates_only_the_existing_pr(monkeypatch):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/repos/acme/demo/git/ref/heads/ai/job12345":
            return httpx.Response(200, json={"object": {"sha": HEAD}})
        if request.url.path == "/repos/acme/demo/pulls/42" and request.method == "GET":
            return httpx.Response(200, json=pull_request())
        if request.url.path == "/repos/acme/demo/pulls/42" and request.method == "PATCH":
            return httpx.Response(200, json=pull_request())
        raise AssertionError(f"unexpected GitHub request: {request.method} {request.url}")

    delivery = GitHubDelivery("token")
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        delivery,
        "_client",
        lambda: httpx.Client(transport=transport, headers=delivery.headers),
    )

    result = delivery.upsert_pull_request(
        repository="acme/demo",
        job_id="job12345",
        branch="ai/job12345",
        base_branch="main",
        expected_commit=HEAD,
        title="repair",
        body="Automated coding-platform delivery.\n\n- Job: `job12345`",
        expected_pr_number=42,
    )

    assert result["created"] is False
    assert result["number"] == 42
    assert ("POST", "/repos/acme/demo/pulls") not in requests


def test_executor_prepares_the_existing_clean_job_branch_without_creating_workspace(
    monkeypatch,
    tmp_path,
):
    repo = tmp_path / "workspace"
    repo.mkdir()
    main.subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True)
    main.subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    main.subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "file.txt").write_text("source\n", encoding="utf-8")
    main.subprocess.run(["git", "-C", str(repo), "add", "file.txt"], check=True)
    main.subprocess.run(["git", "-C", str(repo), "commit", "-m", "source"], check=True)
    source = main.git(repo, "rev-parse", "HEAD")
    main.subprocess.run(["git", "-C", str(repo), "checkout", "-b", "ai/job12345"], check=True)
    (repo / "file.txt").write_text("delivered\n", encoding="utf-8")
    main.subprocess.run(["git", "-C", str(repo), "commit", "-am", "delivered"], check=True)
    head = main.git(repo, "rev-parse", "HEAD")

    class FakeDelivery:
        def verify_review_repair(self, **kwargs):
            assert kwargs["source_commit"] == source
            assert kwargs["expected_commit"] == head
            return {
                "number": 42,
                "state": "open",
                "merged": False,
                "head": head,
                "head_ref": "ai/job12345",
                "base_ref": "main",
                "repository": "acme/demo",
            }

    cfg = {
        "base_branch": "main",
        "runtime": {"branch_prefix": "ai", "workspace_mode": "isolated_clone"},
        "autonomy": {"allow_push_ai_branch": True, "allow_create_pr": True},
    }
    monkeypatch.setattr(main, "project", lambda _project_id: cfg)
    monkeypatch.setattr(main, "_validate_workspace", lambda *_args, **_kwargs: repo)
    monkeypatch.setattr(main, "_workspace_instance_mode", lambda *_args, **_kwargs: "isolated_clone")
    monkeypatch.setattr(main, "_github_context", lambda _cfg: (FakeDelivery(), "acme/demo"))

    result = main.prepare_review_repair(
        main.ReviewRepairRequest(
            job_id="job12345",
            project_id="demo",
            workspace=str(repo),
            branch="ai/job12345",
            source_commit=source,
            expected_commit=head,
            pr_number=42,
        )
    )

    assert result["workspace"] == str(repo)
    assert result["branch"] == "ai/job12345"
    assert result["expected_commit"] == head
    assert result["pull_request"]["number"] == 42


def test_executor_restores_completed_direct_workspace_from_base_to_existing_ai_branch(
    monkeypatch,
    tmp_path,
):
    repo = tmp_path / "direct"
    repo.mkdir()
    main.subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True)
    main.subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    main.subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "file.txt").write_text("source\n", encoding="utf-8")
    main.subprocess.run(["git", "-C", str(repo), "add", "file.txt"], check=True)
    main.subprocess.run(["git", "-C", str(repo), "commit", "-m", "source"], check=True)
    source = main.git(repo, "rev-parse", "HEAD")
    main.subprocess.run(["git", "-C", str(repo), "checkout", "-b", "ai/job12345"], check=True)
    (repo / "file.txt").write_text("delivered\n", encoding="utf-8")
    main.subprocess.run(["git", "-C", str(repo), "commit", "-am", "delivered"], check=True)
    head = main.git(repo, "rev-parse", "HEAD")
    main.subprocess.run(["git", "-C", str(repo), "checkout", "main"], check=True)

    class FakeDelivery:
        def verify_review_repair(self, **_kwargs):
            return {
                "number": 42,
                "state": "open",
                "merged": False,
                "head": head,
                "head_ref": "ai/job12345",
                "base_ref": "main",
                "repository": "acme/demo",
            }

    cfg = {
        "base_branch": "main",
        "runtime": {"branch_prefix": "ai", "workspace_mode": "direct"},
        "autonomy": {"allow_push_ai_branch": True, "allow_create_pr": True},
    }
    monkeypatch.setattr(main, "project", lambda _project_id: cfg)
    monkeypatch.setattr(main, "_validate_workspace", lambda *_args, **_kwargs: repo)
    monkeypatch.setattr(main, "_workspace_instance_mode", lambda *_args, **_kwargs: "direct")
    monkeypatch.setattr(main, "_github_context", lambda _cfg: (FakeDelivery(), "acme/demo"))

    main.prepare_review_repair(
        main.ReviewRepairRequest(
            job_id="job12345",
            project_id="demo",
            workspace=str(repo),
            branch="ai/job12345",
            source_commit=source,
            expected_commit=head,
            pr_number=42,
        )
    )

    assert main.git(repo, "branch", "--show-current") == "ai/job12345"
    assert main.git(repo, "rev-parse", "HEAD") == head
    assert main.git(repo, "status", "--porcelain", check=False) == ""


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw.update(state="closed"),
        lambda raw: raw.update(merged=True, merged_at="2026-09-29T00:00:00Z"),
        lambda raw: raw["base"].update(ref="develop"),
        lambda raw: raw["head"].update(sha="f" * 40),
    ],
    ids=["closed", "merged", "base-moved", "head-moved"],
)
def test_repair_publish_revalidates_stale_pr_and_never_pushes(
    monkeypatch,
    tmp_path,
    mutation,
):
    repo = tmp_path / "workspace"
    repo.mkdir()
    main.subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True)
    main.subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
    )
    main.subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
    )
    (repo / "file.txt").write_text("source\n", encoding="utf-8")
    main.subprocess.run(["git", "-C", str(repo), "add", "file.txt"], check=True)
    main.subprocess.run(["git", "-C", str(repo), "commit", "-m", "source"], check=True)
    source = main.git(repo, "rev-parse", "HEAD")
    main.subprocess.run(
        ["git", "-C", str(repo), "checkout", "-b", "ai/job12345"],
        check=True,
    )
    (repo / "file.txt").write_text("delivered\n", encoding="utf-8")
    main.subprocess.run(["git", "-C", str(repo), "commit", "-am", "delivered"], check=True)
    previous = main.git(repo, "rev-parse", "HEAD")
    (repo / "file.txt").write_text("repaired\n", encoding="utf-8")
    main.subprocess.run(["git", "-C", str(repo), "commit", "-am", "repair"], check=True)
    repaired = main.git(repo, "rev-parse", "HEAD")

    stale_pull = pull_request()
    stale_pull["head"]["sha"] = previous
    mutation(stale_pull)

    class StaleDelivery:
        configured = True
        token = "token"

        def verify_review_repair(self, **kwargs):
            assert kwargs["pr_number"] == 42
            assert kwargs["source_commit"] == source
            assert kwargs["expected_commit"] in {previous, repaired}
            return GitHubDelivery._review_repair_pull_request(
                stale_pull,
                repository=kwargs["repository"],
                job_id=kwargs["job_id"],
                branch=kwargs["branch"],
                base_branch=kwargs["base_branch"],
                expected_commit=kwargs["expected_commit"],
            )

    publish_calls = []
    cfg = {
        "base_branch": "main",
        "runtime": {"branch_prefix": "ai", "workspace_mode": "isolated_clone"},
        "autonomy": {"allow_push_ai_branch": True, "allow_create_pr": True},
    }
    monkeypatch.setattr(main, "project", lambda _project_id: cfg)
    monkeypatch.setattr(main, "_validate_workspace", lambda *_args, **_kwargs: repo)
    monkeypatch.setattr(
        main,
        "_workspace_instance_mode",
        lambda *_args, **_kwargs: "isolated_clone",
    )
    monkeypatch.setattr(
        main,
        "_source_origin",
        lambda _cfg: (repo, "https://github.com/acme/demo.git"),
    )
    monkeypatch.setattr(main, "GitHubDelivery", StaleDelivery)
    monkeypatch.setattr(
        main,
        "run_tracked",
        lambda *_args, **_kwargs: publish_calls.append((_args, _kwargs)),
    )

    with pytest.raises(HTTPException) as exc:
        main.publish_branch(
            main.PublishBranchRequest(
                job_id="job12345",
                project_id="demo",
                workspace=str(repo),
                branch="ai/job12345",
                source_commit=source,
                expected_commit=repaired,
                review_repair_pr_number=42,
                review_repair_previous_commit=previous,
            )
        )

    assert exc.value.status_code == 409
    assert publish_calls == []
