"""F2 PM GitHub read endpoints reuse the issuer-scoped Executor client only."""
from __future__ import annotations
import pytest
from fastapi import HTTPException
from app import main
from app import pm_bridge_github


@pytest.mark.parametrize("path,ok", [
    ("/v1/github/pm-bridge/pulls/42", True),
    ("/v1/github/pm-bridge/pulls/42/reviews/9", True),
    ("/v1/github/pm-bridge/pulls/0", False),
    ("/v1/github/pm-bridge/pulls/42/reviews/0", False),
    ("/v1/github/pm-bridge/pulls/42/merge", False),
    ("/v1/github/pm-bridge/issues/42", False),
    ("/v1/github/pm-bridge/managed-comment", False),
    ("/v1/github/pm-bridge/pulls/42?project_id=x", False),
])
def test_only_exact_read_pr_and_review_paths(path, ok):
    assert main._f2_git_only_route_allowed("GET", path) is ok
    assert main._f2_git_only_route_allowed("POST", path) is False
    assert main._f2_git_only_route_allowed("DELETE", path) is False


def test_pm_repository_lookup_reuses_f2_exact_project_and_scope(monkeypatch):
    visited = []
    monkeypatch.setattr(main, "_f2_git_only_scoped", lambda: True)

    def project(name):
        visited.append(("project", name))
        if name != "pcp-g0-fullpath-fixture":
            raise HTTPException(403, "foreign project forbidden")
        return {"checked": True}

    def context(config):
        visited.append(("context", config))
        assert config == {"checked": True}
        return object(), "sonvhse06072/pcp-g0-fullpath-fixture"

    monkeypatch.setattr(main, "project", project)
    monkeypatch.setattr(main, "_github_context", context)
    delivery, name = pm_bridge_github._repository("pcp-g0-fullpath-fixture")
    assert delivery is not None and name == "sonvhse06072/pcp-g0-fullpath-fixture"
    with pytest.raises(HTTPException, match="foreign"):
        pm_bridge_github._repository("chonhac")
    assert visited == [
        ("project", "pcp-g0-fullpath-fixture"),
        ("context", {"checked": True}),
        ("project", "chonhac"),
    ]
