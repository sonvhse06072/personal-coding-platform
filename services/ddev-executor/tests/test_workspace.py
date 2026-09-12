from pathlib import Path
import subprocess

import pytest
import yaml
from fastapi import HTTPException

from app.main import (
    PublishBranchRequest,
    WorkspaceRequest,
    create_workspace,
    publish_branch,
    remove_workspace,
)


def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def make_project(tmp_path: Path, *, allow_push: bool) -> tuple[Path, Path, Path]:
    source_root = tmp_path / "projects"
    source = source_root / "demo"
    remote = tmp_path / "remote.git"
    workspaces = tmp_path / "workspaces"
    source.mkdir(parents=True)
    workspaces.mkdir()

    run("git", "init", "--bare", str(remote))
    run("git", "init", "-b", "main", cwd=source)
    run("git", "config", "user.email", "test@example.com", cwd=source)
    run("git", "config", "user.name", "Test", cwd=source)
    (source / "README.md").write_text("hello\n")
    run("git", "add", "README.md", cwd=source)
    run("git", "commit", "-m", "initial", cwd=source)
    run("git", "remote", "add", "origin", str(remote), cwd=source)
    run("git", "push", "-u", "origin", "main", cwd=source)

    config = tmp_path / "projects.yml"
    config.write_text(yaml.safe_dump({
        "projects": {
            "demo": {
                "path": str(source),
                "base_branch": "main",
                "autonomy": {"allow_push_ai_branch": allow_push},
                "runtime": {"branch_prefix": "ai"},
                "ddev": {"enabled": False},
            }
        }
    }))
    return source, remote, workspaces


def configure(monkeypatch, tmp_path: Path, *, allow_push: bool):
    source, remote, workspaces = make_project(tmp_path, allow_push=allow_push)
    monkeypatch.setenv("PROJECTS_FILE", str(tmp_path / "projects.yml"))
    monkeypatch.setenv("CODING_WORKSPACES_ROOT", str(workspaces))
    return source, remote, workspaces


def test_workspace_is_self_contained_clone_without_remote(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure(monkeypatch, tmp_path, allow_push=False)
    commit = run("git", "rev-parse", "HEAD", cwd=source)

    result = create_workspace(WorkspaceRequest(job_id="job12345", project_id="demo"))
    workspace = Path(result["workspace"])

    assert result["source_commit"] == commit
    assert result["workspace_mode"] == "isolated_clone_no_remote"
    assert (workspace / ".git").is_dir(), "workspace must not point back to the source .git directory"
    assert run("git", "rev-parse", "HEAD", cwd=workspace) == commit
    assert run("git", "branch", "--show-current", cwd=workspace) == "ai/job12345"
    assert run("git", "remote", cwd=workspace) == ""

    removed = remove_workspace(job_id="job12345", project_id="demo", workspace=str(workspace))
    assert removed["removed"] is True
    assert not workspace.exists()


def test_publish_branch_pushes_verified_head_without_persisting_remote(tmp_path, monkeypatch):
    source, remote, _workspaces = configure(monkeypatch, tmp_path, allow_push=True)
    source_commit = run("git", "rev-parse", "HEAD", cwd=source)
    created = create_workspace(WorkspaceRequest(job_id="jobpublish1", project_id="demo"))
    workspace = Path(created["workspace"])

    run("git", "config", "user.email", "test@example.com", cwd=workspace)
    run("git", "config", "user.name", "Test", cwd=workspace)
    (workspace / "TEST.txt").write_text("published\n")
    run("git", "add", "TEST.txt", cwd=workspace)
    run("git", "commit", "-m", "test publish", cwd=workspace)
    head = run("git", "rev-parse", "HEAD", cwd=workspace)

    result = publish_branch(PublishBranchRequest(
        job_id="jobpublish1",
        project_id="demo",
        workspace=str(workspace),
        branch="ai/jobpublish1",
        source_commit=source_commit,
        expected_commit=head,
    ))

    assert result == {
        "published": True,
        "branch": "ai/jobpublish1",
        "commit": head,
        "source_commit": source_commit,
    }
    assert run("git", "remote", cwd=workspace) == ""
    assert run("git", "--git-dir", str(remote), "rev-parse", "refs/heads/ai/jobpublish1") == head


def test_publish_branch_fails_closed_when_project_policy_disallows_push(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure(monkeypatch, tmp_path, allow_push=False)
    source_commit = run("git", "rev-parse", "HEAD", cwd=source)
    created = create_workspace(WorkspaceRequest(job_id="jobpublish2", project_id="demo"))
    workspace = Path(created["workspace"])

    with pytest.raises(HTTPException) as exc:
        publish_branch(PublishBranchRequest(
            job_id="jobpublish2",
            project_id="demo",
            workspace=str(workspace),
            branch="ai/jobpublish2",
            source_commit=source_commit,
            expected_commit=source_commit,
        ))

    assert exc.value.status_code == 403
