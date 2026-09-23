from pathlib import Path
import subprocess

import pytest
import yaml
from fastapi import HTTPException

from app.main import (
    PhaseRequest,
    PublishBranchRequest,
    QuiesceWorkspaceRequest,
    WorkspaceRequest,
    create_workspace,
    phase,
    publish_branch,
    quiesce_workspace,
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
        "repository": None,
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


def test_github_publish_requires_dedicated_delivery_token(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure(monkeypatch, tmp_path, allow_push=True)
    source_commit = run("git", "rev-parse", "HEAD", cwd=source)
    created = create_workspace(WorkspaceRequest(job_id="jobpublish3", project_id="demo"))
    workspace = Path(created["workspace"])
    run("git", "remote", "set-url", "origin", "https://user:embedded@github.com/acme/demo.git", cwd=source)
    monkeypatch.delenv("GITHUB_DELIVERY_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        publish_branch(PublishBranchRequest(
            job_id="jobpublish3",
            project_id="demo",
            workspace=str(workspace),
            branch="ai/jobpublish3",
            source_commit=source_commit,
            expected_commit=source_commit,
        ))

    assert exc.value.status_code == 503
    assert run("git", "remote", cwd=workspace) == ""

def test_workspace_ddev_override_is_explicit_and_isolated(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure(monkeypatch, tmp_path, allow_push=False)
    ddev = source / ".ddev"
    ddev.mkdir()
    (ddev / "config.yaml").write_text("name: demo\ntype: drupal11\n")
    run("git", "add", ".ddev/config.yaml", cwd=source)
    run("git", "commit", "-m", "add ddev config", cwd=source)
    run("git", "push", "origin", "main", cwd=source)

    result = create_workspace(
        WorkspaceRequest(job_id="jobddev12345", project_id="demo")
    )
    workspace = Path(result["workspace"])
    override = yaml.safe_load(
        (workspace / ".ddev" / "config.coding-platform.yaml").read_text()
    )

    assert override == {
        "override_config": True,
        "name": "cp-jobddev123",
    }
    assert (workspace / ".ddev" / "config.yaml").read_text() == (
        "name: demo\ntype: drupal11\n"
    )


def test_phase_reconciles_legacy_workspace_ddev_override(tmp_path, monkeypatch):
    _source, _remote, workspaces = configure(
        monkeypatch, tmp_path, allow_push=False
    )
    projects_file = tmp_path / "projects.yml"
    data = yaml.safe_load(projects_file.read_text())
    data["projects"]["demo"]["ddev"] = {
        "enabled": True,
        "targeted_tests": ["ddev exec echo ok"],
    }
    projects_file.write_text(yaml.safe_dump(data))

    job_id = "jobreconcile12"
    workspace = workspaces / job_id
    ddev = workspace / ".ddev"
    ddev.mkdir(parents=True)
    (ddev / "config.yaml").write_text("name: demo\ntype: drupal11\n")
    override_path = ddev / "config.coding-platform.yaml"
    override_path.write_text("name: cp-jobreconci\n")

    observed = {}

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        observed["job"] = job
        observed["argv"] = argv
        observed["cwd"] = cwd
        observed["override"] = yaml.safe_load(override_path.read_text())
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)

    response = phase(
        PhaseRequest(
            job_id=job_id,
            project_id="demo",
            workspace=str(workspace),
            phase="targeted_tests",
        )
    )

    assert response.passed is True
    assert observed["job"] == job_id
    assert observed["cwd"] == workspace
    assert observed["override"] == {
        "override_config": True,
        "name": "cp-jobreconci",
    }
    assert (ddev / "config.yaml").read_text() == (
        "name: demo\ntype: drupal11\n"
    )

def test_workspace_ddev_override_can_pin_project_node_version(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure(
        monkeypatch, tmp_path, allow_push=False
    )
    ddev = source / ".ddev"
    ddev.mkdir()
    (ddev / "config.yaml").write_text(
        "name: demo\ntype: drupal11\nnodejs_version: \"22\"\n"
    )
    run("git", "add", ".ddev/config.yaml", cwd=source)
    run("git", "commit", "-m", "add ddev node config", cwd=source)
    run("git", "push", "origin", "main", cwd=source)

    projects_file = tmp_path / "projects.yml"
    data = yaml.safe_load(projects_file.read_text())
    data["projects"]["demo"]["ddev"] = {
        "enabled": True,
        "workspace_nodejs_version": "24",
    }
    projects_file.write_text(yaml.safe_dump(data))

    result = create_workspace(
        WorkspaceRequest(job_id="jobnode24123", project_id="demo")
    )
    workspace = Path(result["workspace"])
    override = yaml.safe_load(
        (workspace / ".ddev" / "config.coding-platform.yaml").read_text()
    )

    assert override == {
        "override_config": True,
        "name": "cp-jobnode241",
        "nodejs_version": "24",
    }
    assert "nodejs_version: \"22\"" in (
        workspace / ".ddev" / "config.yaml"
    ).read_text()


def test_phase_refreshes_node_pin_for_preserved_workspace(tmp_path, monkeypatch):
    _source, _remote, workspaces = configure(
        monkeypatch, tmp_path, allow_push=False
    )
    projects_file = tmp_path / "projects.yml"
    data = yaml.safe_load(projects_file.read_text())
    data["projects"]["demo"]["ddev"] = {
        "enabled": True,
        "workspace_nodejs_version": "24",
        "frontend_quality": ["ddev exec node --version"],
    }
    projects_file.write_text(yaml.safe_dump(data))

    job_id = "jobnodelegacy"
    workspace = workspaces / job_id
    ddev = workspace / ".ddev"
    ddev.mkdir(parents=True)
    (ddev / "config.yaml").write_text(
        "name: demo\ntype: drupal11\n"
    )
    override_path = ddev / "config.coding-platform.yaml"
    override_path.write_text(
        "override_config: true\nname: cp-jobnodeleg\n"
    )

    observed = {}

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        observed["override"] = yaml.safe_load(
            override_path.read_text()
        )
        return 0, "v24.0.0\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)

    response = phase(
        PhaseRequest(
            job_id=job_id,
            project_id="demo",
            workspace=str(workspace),
            phase="frontend_quality",
        )
    )

    assert response.passed is True
    assert observed["override"] == {
        "override_config": True,
        "name": "cp-jobnodeleg",
        "nodejs_version": "24",
    }

def test_quiesce_workspace_stops_only_validated_ddev_project(tmp_path, monkeypatch):
    _source, _remote, workspaces = configure(
        monkeypatch, tmp_path, allow_push=False
    )
    projects_file = tmp_path / "projects.yml"
    data = yaml.safe_load(projects_file.read_text())
    data["projects"]["demo"]["ddev"] = {"enabled": True}
    projects_file.write_text(yaml.safe_dump(data))

    job_id = "jobquiesce12"
    workspace = workspaces / job_id
    ddev = workspace / ".ddev"
    ddev.mkdir(parents=True)
    run("git", "init", "-b", "ai/test", cwd=workspace)
    (workspace / "README.md").write_text("workspace\n")
    run("git", "add", "README.md", cwd=workspace)
    run("git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "init", cwd=workspace)
    (ddev / "config.yaml").write_text("name: demo\ntype: drupal11\n")

    observed = {}

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        observed["job"] = job
        observed["argv"] = argv
        observed["cwd"] = cwd
        observed["timeout"] = timeout
        return 0, "Stopped cp-jobquiesc\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)
    monkeypatch.setattr("app.main._job_has_active_process", lambda value: False)

    result = quiesce_workspace(
        QuiesceWorkspaceRequest(
            job_id=job_id,
            project_id="demo",
            workspace=str(workspace),
        )
    )

    assert result["quiesced"] is True
    assert result["data_removed"] is False
    assert observed["job"] == job_id
    assert observed["argv"] == [
        "ddev",
        "stop",
        "--unlist",
        "--omit-snapshot",
    ]
    assert observed["cwd"] == workspace


def test_quiesce_workspace_refuses_active_executor_process(tmp_path, monkeypatch):
    _source, _remote, workspaces = configure(
        monkeypatch, tmp_path, allow_push=False
    )
    job_id = "jobactive123"
    workspace = workspaces / job_id
    workspace.mkdir()
    run("git", "init", "-b", "ai/test", cwd=workspace)
    (workspace / "README.md").write_text("workspace\n")
    run("git", "add", "README.md", cwd=workspace)
    run("git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "init", cwd=workspace)

    monkeypatch.setattr("app.main._job_has_active_process", lambda value: True)

    with pytest.raises(HTTPException) as exc:
        quiesce_workspace(
            QuiesceWorkspaceRequest(
                job_id=job_id,
                project_id="demo",
                workspace=str(workspace),
            )
        )

    assert exc.value.status_code == 409


def test_phase_starts_quiesced_ddev_before_configured_commands(tmp_path, monkeypatch):
    _source, _remote, workspaces = configure(
        monkeypatch, tmp_path, allow_push=False
    )
    projects_file = tmp_path / "projects.yml"
    data = yaml.safe_load(projects_file.read_text())
    data["projects"]["demo"]["ddev"] = {
        "enabled": True,
        "targeted_tests": ["ddev exec echo check"],
    }
    projects_file.write_text(yaml.safe_dump(data))

    job_id = "jobresume123"
    workspace = workspaces / job_id
    ddev = workspace / ".ddev"
    ddev.mkdir(parents=True)
    run("git", "init", "-b", "ai/test", cwd=workspace)
    (workspace / "README.md").write_text("workspace\n")
    run("git", "add", "README.md", cwd=workspace)
    run("git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "init", cwd=workspace)
    (ddev / "config.yaml").write_text("name: demo\ntype: drupal11\n")

    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append(list(argv))
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)

    response = phase(
        PhaseRequest(
            job_id=job_id,
            project_id="demo",
            workspace=str(workspace),
            phase="targeted_tests",
        )
    )

    assert response.passed is True
    assert calls[0] == ["ddev", "start", "-y"]
    assert calls[1] == ["bash", "-lc", "ddev exec echo check"]
    assert len(response.infrastructure) == 1
    assert response.infrastructure[0].command == "ddev start -y"
    assert response.infrastructure[0].returncode == 0

