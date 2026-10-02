from pathlib import Path
import subprocess

import pytest
import yaml
from fastapi import HTTPException

from app.main import (
    AdvanceDirectWorkspaceSourceRequest,
    PhaseRequest,
    PreviewRequest,
    PublishBranchRequest,
    QuiesceWorkspaceRequest,
    ReturnDirectWorkspaceRequest,
    WorkspaceRequest,
    advance_direct_workspace_source,
    create_workspace,
    phase,
    preview_status,
    publish_branch,
    start_preview,
    stop_preview,
    quiesce_workspace,
    remove_workspace,
    return_direct_workspace_to_base,
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
        calls.append((list(argv), dict(env)))
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
    assert calls[0][0] == ["ddev", "start", "-y"]
    assert calls[1][0] == ["bash", "-lc", "ddev exec echo check"]
    for _argv, env in calls:
        assert env["BUILDX_BUILDER"] == "pcp-builder"
        assert env["BUILDX_CONFIG"] == "/home/coder/.pcp-buildx"
        assert env["DDEV_NO_TUI"] == "true"
    assert len(response.infrastructure) == 1
    assert response.infrastructure[0].command == "ddev start -y"
    assert response.infrastructure[0].returncode == 0

def test_quiesce_workspace_can_release_only_validated_project_data(tmp_path, monkeypatch):
    _source, _remote, workspaces = configure(
        monkeypatch, tmp_path, allow_push=False
    )
    projects_file = tmp_path / "projects.yml"
    data = yaml.safe_load(projects_file.read_text())
    data["projects"]["demo"]["ddev"] = {"enabled": True}
    projects_file.write_text(yaml.safe_dump(data))

    job_id = "jobrelease123"
    workspace = workspaces / job_id
    ddev = workspace / ".ddev"
    ddev.mkdir(parents=True)
    run("git", "init", "-b", "ai/test", cwd=workspace)
    (workspace / "README.md").write_text("workspace\n")
    run("git", "add", "README.md", cwd=workspace)
    run(
        "git",
        "-c", "user.email=test@example.com",
        "-c", "user.name=Test",
        "commit", "-m", "init",
        cwd=workspace,
    )
    (ddev / "config.yaml").write_text("name: demo\ntype: drupal11\n")

    observed = {}

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        observed["argv"] = argv
        return 0, "Stopped and removed data\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)
    monkeypatch.setattr("app.main._job_has_active_process", lambda value: False)

    result = quiesce_workspace(
        QuiesceWorkspaceRequest(
            job_id=job_id,
            project_id="demo",
            workspace=str(workspace),
            remove_data=True,
        )
    )

    assert observed["argv"] == [
        "ddev",
        "stop",
        "--unlist",
        "--omit-snapshot",
        "--remove-data",
    ]
    assert result["quiesced"] is True
    assert result["data_removed"] is True
    assert workspace.exists()



def configure_direct(monkeypatch, tmp_path: Path, *, allow_push: bool = True):
    source, remote, workspaces = configure(
        monkeypatch, tmp_path, allow_push=allow_push
    )
    projects_file = tmp_path / "projects.yml"
    data = yaml.safe_load(projects_file.read_text())
    data["projects"]["demo"]["runtime"] = {
        "branch_prefix": "ai",
        "workspace_mode": "direct",
        "exclusive_project_lease": True,
    }
    projects_file.write_text(yaml.safe_dump(data))
    monkeypatch.setenv("CODING_DIRECT_PROJECT_ROOT", str(source))
    return source, remote, workspaces


def _advance_remote_main(remote: Path, tmp_path: Path, *, filename: str, content: str) -> str:
    producer = tmp_path / f"producer-{filename.replace('/', '-')}"
    run("git", "clone", str(remote), str(producer))
    run("git", "checkout", "main", cwd=producer)
    run("git", "config", "user.email", "producer@example.com", cwd=producer)
    run("git", "config", "user.name", "Producer", cwd=producer)
    path = producer / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    run("git", "add", filename, cwd=producer)
    run("git", "commit", "-m", f"advance {filename}", cwd=producer)
    run("git", "push", "origin", "main", cwd=producer)
    return run("git", "rev-parse", "HEAD", cwd=producer)


def test_direct_workspace_fast_forwards_clean_local_base_before_new_job(tmp_path, monkeypatch):
    source, remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    old = run("git", "rev-parse", "main", cwd=source)
    remote_head = _advance_remote_main(
        remote,
        tmp_path,
        filename="BACKEND.txt",
        content="merged dependency\n",
    )
    assert run("git", "rev-parse", "main", cwd=source) == old

    result = create_workspace(
        WorkspaceRequest(job_id="jobdirectsync", project_id="demo")
    )

    assert result["source_commit"] == remote_head
    assert result["branch"] == "ai/jobdirectsync"
    assert run("git", "rev-parse", "HEAD", cwd=source) == remote_head
    assert run("git", "rev-parse", "main", cwd=source) == remote_head
    assert run("git", "rev-parse", "origin/main", cwd=source) == remote_head


def test_direct_workspace_refuses_diverged_local_base(tmp_path, monkeypatch):
    source, remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    (source / "LOCAL.txt").write_text("local only\n")
    run("git", "add", "LOCAL.txt", cwd=source)
    run("git", "commit", "-m", "local divergent commit", cwd=source)
    local_head = run("git", "rev-parse", "HEAD", cwd=source)
    _advance_remote_main(
        remote,
        tmp_path,
        filename="REMOTE.txt",
        content="remote only\n",
    )

    with pytest.raises(HTTPException) as exc:
        create_workspace(
            WorkspaceRequest(job_id="jobdirectdiverge", project_id="demo")
        )

    assert exc.value.status_code == 409
    assert "diverged" in str(exc.value.detail)
    assert run("git", "rev-parse", "HEAD", cwd=source) == local_head
    assert run("git", "branch", "--show-current", cwd=source) == "main"


def test_direct_source_advance_preserves_disjoint_dirty_worktree(tmp_path, monkeypatch):
    source, remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobsourcestep", project_id="demo")
    )
    old = created["source_commit"]
    (source / "frontend").mkdir()
    (source / "frontend" / "page.tsx").write_text("preserve frontend\n")
    remote_head = _advance_remote_main(
        remote,
        tmp_path,
        filename="web/BACKEND.txt",
        content="merged backend\n",
    )

    result = advance_direct_workspace_source(
        AdvanceDirectWorkspaceSourceRequest(
            job_id="jobsourcestep",
            project_id="demo",
            workspace=str(source),
            branch=created["branch"],
            old_source=old,
            new_source=remote_head,
        )
    )

    assert result["old_source"] == old
    assert result["new_source"] == remote_head
    assert "frontend/page.tsx" in result["dirty_paths"]
    assert "web/BACKEND.txt" in result["dependency_paths"]
    assert run("git", "rev-parse", "HEAD", cwd=source) == remote_head
    assert (source / "frontend" / "page.tsx").read_text() == "preserve frontend\n"
    assert "frontend/page.tsx" in run("git", "status", "--porcelain", cwd=source)

    repeated = advance_direct_workspace_source(
        AdvanceDirectWorkspaceSourceRequest(
            job_id="jobsourcestep",
            project_id="demo",
            workspace=str(source),
            branch=created["branch"],
            old_source=old,
            new_source=remote_head,
        )
    )
    assert repeated["already_advanced"] is True
    assert run("git", "rev-parse", "HEAD", cwd=source) == remote_head
    assert (source / "frontend" / "page.tsx").read_text() == "preserve frontend\n"


def test_direct_source_advance_refuses_overlapping_dirty_path(tmp_path, monkeypatch):
    source, remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobsourcelap", project_id="demo")
    )
    old = created["source_commit"]
    (source / "README.md").write_text("local frontend-adjacent edit\n")
    remote_head = _advance_remote_main(
        remote,
        tmp_path,
        filename="README.md",
        content="dependency edit\n",
    )

    with pytest.raises(HTTPException) as exc:
        advance_direct_workspace_source(
            AdvanceDirectWorkspaceSourceRequest(
                job_id="jobsourcelap",
                project_id="demo",
                workspace=str(source),
                branch=created["branch"],
                old_source=old,
                new_source=remote_head,
            )
        )

    assert exc.value.status_code == 409
    assert "overlap" in str(exc.value.detail)
    assert run("git", "rev-parse", "HEAD", cwd=source) == old
    assert (source / "README.md").read_text() == "local frontend-adjacent edit\n"


def test_direct_workspace_uses_registered_repo_and_preserves_origin(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    source_commit = run("git", "rev-parse", "main", cwd=source)

    result = create_workspace(
        WorkspaceRequest(job_id="jobdirect123", project_id="demo")
    )

    assert Path(result["workspace"]) == source.resolve()
    assert result["workspace_mode"] == "direct"
    assert result["source_commit"] == source_commit
    assert result["branch"] == "ai/jobdirect123"
    assert run("git", "branch", "--show-current", cwd=source) == "ai/jobdirect123"
    assert run("git", "remote", cwd=source) == "origin"

    removed = remove_workspace(
        job_id="jobdirect123",
        project_id="demo",
        workspace=str(source),
    )
    assert removed["removed"] is False
    assert removed["preserved"] is True
    assert source.exists()
    assert (source / ".git").exists()


def test_direct_workspace_refuses_dirty_repo_without_branch_mutation(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    (source / "README.md").write_text("human owner edit\n")
    original_branch = run("git", "branch", "--show-current", cwd=source)

    with pytest.raises(HTTPException) as exc:
        create_workspace(
            WorkspaceRequest(job_id="jobdirty1234", project_id="demo")
        )

    assert exc.value.status_code == 409
    assert "will not reset, clean or stash" in str(exc.value.detail)
    assert run("git", "branch", "--show-current", cwd=source) == original_branch
    assert run("git", "status", "--porcelain", cwd=source)


def test_direct_workspace_publish_keeps_real_origin_and_pushes_exact_head(tmp_path, monkeypatch):
    source, remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    source_commit = run("git", "rev-parse", "main", cwd=source)
    created = create_workspace(
        WorkspaceRequest(job_id="jobdirectpub", project_id="demo")
    )

    (source / "DIRECT.txt").write_text("direct\n")
    run("git", "add", "DIRECT.txt", cwd=source)
    run("git", "commit", "-m", "direct publish", cwd=source)
    head = run("git", "rev-parse", "HEAD", cwd=source)

    result = publish_branch(
        PublishBranchRequest(
            job_id="jobdirectpub",
            project_id="demo",
            workspace=created["workspace"],
            branch=created["branch"],
            source_commit=source_commit,
            expected_commit=head,
        )
    )

    assert result["published"] is True
    assert result["commit"] == head
    assert run("git", "remote", cwd=source) == "origin"
    assert (
        run(
            "git",
            "--git-dir",
            str(remote),
            "rev-parse",
            "refs/heads/ai/jobdirectpub",
        )
        == head
    )


def test_direct_quiesce_preserves_normal_project_ddev_and_data(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobdirectqui", project_id="demo")
    )

    result = quiesce_workspace(
        QuiesceWorkspaceRequest(
            job_id="jobdirectqui",
            project_id="demo",
            workspace=created["workspace"],
            remove_data=True,
        )
    )

    assert result["quiesced"] is False
    assert result["data_removed"] is False
    assert result["preserved"] is True
    assert result["reason"] == "direct_workspace_preserved"
    assert source.exists()


def test_direct_phase_uses_normal_ddev_identity_without_pcp_override(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct(
        monkeypatch, tmp_path, allow_push=False
    )
    ddev = source / ".ddev"
    ddev.mkdir()
    (ddev / "config.yaml").write_text("name: demo\ntype: drupal11\n")
    run("git", "add", ".ddev/config.yaml", cwd=source)
    run("git", "commit", "-m", "add ddev", cwd=source)
    run("git", "push", "origin", "main", cwd=source)

    projects_file = tmp_path / "projects.yml"
    data = yaml.safe_load(projects_file.read_text())
    data["projects"]["demo"]["ddev"] = {
        "enabled": True,
        "targeted_tests": ["ddev exec echo ok"],
    }
    projects_file.write_text(yaml.safe_dump(data))

    created = create_workspace(
        WorkspaceRequest(job_id="jobdirectddev", project_id="demo")
    )
    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append((list(argv), cwd))
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)

    response = phase(
        PhaseRequest(
            job_id="jobdirectddev",
            project_id="demo",
            workspace=created["workspace"],
            phase="targeted_tests",
        )
    )

    assert response.passed is True
    assert calls[0][0] == ["ddev", "start", "-y"]
    assert calls[0][1] == source.resolve()
    assert calls[1][0] == ["bash", "-lc", "ddev exec echo ok"]
    assert not (ddev / "config.coding-platform.yaml").exists()



def test_direct_project_can_request_disposable_isolated_planning_workspace(tmp_path, monkeypatch):
    source, _remote, workspaces = configure_direct(
        monkeypatch, tmp_path, allow_push=False
    )
    source_branch = run("git", "branch", "--show-current", cwd=source)
    source_commit = run("git", "rev-parse", "main", cwd=source)

    result = create_workspace(
        WorkspaceRequest(
            job_id="plan-direct-123",
            project_id="demo",
            ref=source_commit,
            workspace_mode="isolated_clone",
        )
    )
    workspace = Path(result["workspace"])

    assert result["workspace_mode"] == "isolated_clone_no_remote"
    assert workspace == (workspaces / "plan-direct-123").resolve()
    assert workspace != source.resolve()
    assert run("git", "branch", "--show-current", cwd=source) == source_branch
    assert run("git", "branch", "--show-current", cwd=workspace) == "ai/plan-direct-"
    assert run("git", "remote", cwd=workspace) == ""

    removed = remove_workspace(
        job_id="plan-direct-123",
        project_id="demo",
        workspace=str(workspace),
    )
    assert removed["removed"] is True
    assert source.exists()



def configure_direct_preview(monkeypatch, tmp_path: Path):
    source, remote, workspaces = configure_direct(
        monkeypatch,
        tmp_path,
        allow_push=False,
    )
    projects_file = tmp_path / "projects.yml"
    data = yaml.safe_load(projects_file.read_text())
    data["projects"]["demo"]["preview"] = {
        "backend": {
            "enabled": True,
            "url": "https://demo.ddev.site",
        },
        "frontend": {
            "enabled": True,
            "directory": "frontend",
            "prepare": ["ddev exec bash -lc 'cd frontend && npm ci'"],
            "daemon": {
                "name": "pcp-next-dev",
                "command": "./node_modules/.bin/next dev --hostname 0.0.0.0 --port 3100",
                "directory": "/var/www/html/frontend",
                "container_port": 3100,
                "http_port": 3099,
                "https_port": 3100,
            },
            "url": "https://demo.ddev.site:3100",
            "api_origin_on_both": "https://demo.ddev.site",
        },
    }
    data["projects"]["demo"]["ddev"] = {
        "enabled": True,
        "workspace_nodejs_version": "24",
        "frontend_quality": ["ddev exec echo frontend-quality"],
    }
    projects_file.write_text(yaml.safe_dump(data))
    return source, remote, workspaces


def test_direct_frontend_preview_is_config_driven_and_git_clean(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreview123", project_id="demo")
    )
    calls = []
    node_override_observations = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append(list(argv))
        node_override = source / ".ddev" / "config.pcp-node.local.yaml"
        if list(argv) == ["ddev", "start", "-y"] or (
            list(argv)[:2] == ["bash", "-lc"]
            and "npm ci" in str(argv[-1])
        ):
            node_override_observations.append(
                (
                    list(argv),
                    node_override.read_text(encoding="utf-8")
                    if node_override.exists()
                    else "",
                )
            )
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)

    result = start_preview(
        PreviewRequest(
            job_id="jobpreview123",
            project_id="demo",
            workspace=created["workspace"],
            target="frontend",
        )
    )

    assert result["status"] == "ready"
    assert result["frontend_url"] == "https://demo.ddev.site:3100"
    assert result["backend_url"] is None
    override = source / ".ddev" / "config.pcp-preview.local.yaml"
    raw = override.read_text(encoding="utf-8")
    assert raw.startswith("# PCP-managed direct live preview; do not commit.\n")
    payload = yaml.safe_load("\n".join(raw.splitlines()[1:]))
    assert payload["nodejs_version"] == "24"
    assert node_override_observations
    assert all(
        'nodejs_version: "24"' in observed
        for _argv, observed in node_override_observations
    )
    assert not (source / ".ddev" / "config.pcp-node.local.yaml").exists()
    assert payload["web_extra_daemons"][0]["name"] == "pcp-next-dev"
    assert payload["web_extra_daemons"][0]["directory"] == "/var/www/html/frontend"
    assert payload["web_extra_exposed_ports"][0] == {
        "name": "pcp-next-dev",
        "container_port": 3100,
        "http_port": 3099,
        "https_port": 3100,
    }
    assert "NEXT_PUBLIC_DRUPAL_API_ORIGIN" not in payload["web_extra_daemons"][0]["command"]
    assert ".ddev/config.pcp-preview.local.yaml" not in run(
        "git", "status", "--porcelain", cwd=source
    )
    assert calls[0] == ["ddev", "start", "-y"]
    assert ["bash", "-lc", "ddev exec bash -lc 'cd frontend && npm ci'"] in calls
    assert ["ddev", "restart", "-y"] in calls


def test_direct_both_preview_uses_configured_local_api_origin(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewboth", project_id="demo")
    )

    monkeypatch.setattr(
        "app.main.run_tracked",
        lambda job, argv, *, cwd, timeout, env: (0, "ok\n", "", False),
    )

    result = start_preview(
        PreviewRequest(
            job_id="jobpreviewboth",
            project_id="demo",
            workspace=created["workspace"],
            target="both",
        )
    )

    assert result["frontend_url"] == "https://demo.ddev.site:3100"
    assert result["backend_url"] == "https://demo.ddev.site"
    assert "CORS/auth policy" in result["integration_note"]
    raw = (source / ".ddev" / "config.pcp-preview.local.yaml").read_text()
    payload = yaml.safe_load("\n".join(raw.splitlines()[1:]))
    assert (
        payload["web_extra_daemons"][0]["command"]
        .startswith("NEXT_PUBLIC_DRUPAL_API_ORIGIN=https://demo.ddev.site ")
    )


def test_preview_is_rejected_for_isolated_workspace(tmp_path, monkeypatch):
    _source, _remote, _workspaces = configure(
        monkeypatch,
        tmp_path,
        allow_push=False,
    )
    created = create_workspace(
        WorkspaceRequest(job_id="jobisolpreview", project_id="demo")
    )

    with pytest.raises(HTTPException) as exc:
        start_preview(
            PreviewRequest(
                job_id="jobisolpreview",
                project_id="demo",
                workspace=created["workspace"],
                target="frontend",
            )
        )

    assert exc.value.status_code == 409


def test_preview_stop_removes_only_pcp_override_and_preserves_source(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewstop", project_id="demo")
    )
    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append(list(argv))
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)
    request = PreviewRequest(
        job_id="jobpreviewstop",
        project_id="demo",
        workspace=created["workspace"],
        target="frontend",
    )
    start_preview(request)
    calls.clear()

    stopped = stop_preview(request)

    assert stopped["status"] == "stopped"
    assert calls == [
        [
            "ddev",
            "exec",
            "supervisorctl",
            "stop",
            "webextradaemons:pcp-next-dev",
        ],
        ["ddev", "start", "-y"],
    ]
    assert not (source / ".ddev" / "config.pcp-preview.local.yaml").exists()
    assert source.exists()
    assert run("git", "branch", "--show-current", cwd=source) == "ai/jobpreviewst"


def test_preview_health_retries_whole_ddev_exec_after_transient_failure(tmp_path, monkeypatch):
    _source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewretry", project_id="demo")
    )
    health_attempts = 0

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        nonlocal health_attempts
        command = list(argv)
        if (
            command[:5] == ["ddev", "exec", "--raw", "--", "curl"]
            and command[-1] == "http://127.0.0.1:3100/"
        ):
            health_attempts += 1
            if health_attempts == 1:
                return 1, "", "transient ddev exec failure", False
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)
    monkeypatch.setattr("app.main.time.sleep", lambda _seconds: None)

    result = start_preview(
        PreviewRequest(
            job_id="jobpreviewretry",
            project_id="demo",
            workspace=created["workspace"],
            target="frontend",
        )
    )

    assert result["status"] == "ready"
    assert health_attempts == 2


def test_preview_health_uses_raw_ddev_exec_without_nested_shell(tmp_path, monkeypatch):
    _source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewraw", project_id="demo")
    )
    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append(list(argv))
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)

    result = start_preview(
        PreviewRequest(
            job_id="jobpreviewraw",
            project_id="demo",
            workspace=created["workspace"],
            target="frontend",
        )
    )

    assert result["status"] == "ready"
    health_calls = [
        call for call in calls
        if call[:5] == ["ddev", "exec", "--raw", "--", "curl"]
    ]
    assert health_calls == [[
        "ddev",
        "exec",
        "--raw",
        "--",
        "curl",
        "--noproxy",
        "*",
        "-fsS",
        "--max-time",
        "3",
        "-o",
        "/dev/null",
        "http://127.0.0.1:3100/",
    ]]
    assert not any(
        call[:4] == ["ddev", "exec", "bash", "-lc"]
        for call in calls
    )


def test_failed_frontend_health_reconciles_removed_preview_topology(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewhealthfail", project_id="demo")
    )
    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        command = list(argv)
        calls.append(command)
        if (
            command[:5] == ["ddev", "exec", "--raw", "--", "curl"]
            and command[-1] == "http://127.0.0.1:3100/"
        ):
            return 1, "", "health unavailable", False
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)
    monkeypatch.setattr("app.main.time.sleep", lambda _seconds: None)

    with pytest.raises(HTTPException) as exc:
        start_preview(
            PreviewRequest(
                job_id="jobpreviewhealthfail",
                project_id="demo",
                workspace=created["workspace"],
                target="frontend",
            )
        )

    assert exc.value.status_code == 502
    assert not (source / ".ddev" / "config.pcp-preview.local.yaml").exists()
    assert calls[-2] == [
        "ddev",
        "exec",
        "supervisorctl",
        "stop",
        "webextradaemons:pcp-next-dev",
    ]
    assert calls[-1] == ["ddev", "start", "-y"]


def test_preview_rebuild_replaces_only_the_owned_frontend_daemon(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewrebuild", project_id="demo")
    )
    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append(list(argv))
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)
    request = PreviewRequest(
        job_id="jobpreviewrebuild",
        project_id="demo",
        workspace=created["workspace"],
        target="frontend",
    )

    assert start_preview(request)["status"] == "ready"
    calls.clear()

    rebuilt = start_preview(request)

    assert rebuilt["status"] == "ready"
    assert calls[0] == [
        "ddev",
        "exec",
        "supervisorctl",
        "stop",
        "webextradaemons:pcp-next-dev",
    ]
    assert ["ddev", "start", "-y"] in calls
    assert ["ddev", "restart", "-y"] in calls
    assert source.exists()


def test_preview_stop_is_idempotent_after_owned_frontend_is_removed(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewstop2", project_id="demo")
    )
    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append(list(argv))
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)
    request = PreviewRequest(
        job_id="jobpreviewstop2",
        project_id="demo",
        workspace=created["workspace"],
        target="frontend",
    )
    start_preview(request)

    assert stop_preview(request)["status"] == "stopped"
    calls.clear()
    stopped_again = stop_preview(request)

    assert stopped_again["status"] == "stopped"
    assert calls == []
    assert not (source / ".ddev" / "config.pcp-preview.local.yaml").exists()
    assert source.exists()


def test_frontend_quality_pauses_direct_preview_before_build(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewqual", project_id="demo")
    )
    calls = []

    node_override_seen = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append(list(argv))
        if list(argv) == ["ddev", "start", "-y"]:
            node_override = source / ".ddev" / "config.pcp-node.local.yaml"
            node_override_seen.append(
                node_override.read_text(encoding="utf-8")
                if node_override.exists()
                else ""
            )
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)
    request = PreviewRequest(
        job_id="jobpreviewqual",
        project_id="demo",
        workspace=created["workspace"],
        target="frontend",
    )
    start_preview(request)
    calls.clear()

    result = phase(
        PhaseRequest(
            job_id="jobpreviewqual",
            project_id="demo",
            workspace=created["workspace"],
            phase="frontend_quality",
        )
    )

    assert result.passed is True
    assert not (source / ".ddev" / "config.pcp-preview.local.yaml").exists()
    assert not (source / ".ddev" / "config.pcp-node.local.yaml").exists()
    assert node_override_seen
    assert 'nodejs_version: "24"' in node_override_seen[-1]
    assert calls[0] == [
        "ddev",
        "exec",
        "supervisorctl",
        "stop",
        "webextradaemons:pcp-next-dev",
    ]
    assert ["ddev", "restart", "-y"] not in calls
    assert ["ddev", "start", "-y"] in calls
    assert ["bash", "-lc", "ddev exec echo frontend-quality"] in calls


def test_preview_status_detects_stopped_frontend(tmp_path, monkeypatch):
    _source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewstat", project_id="demo")
    )
    monkeypatch.setattr(
        "app.main.run_tracked",
        lambda job, argv, *, cwd, timeout, env: (0, "ok\n", "", False),
    )

    state = preview_status(
        PreviewRequest(
            job_id="jobpreviewstat",
            project_id="demo",
            workspace=created["workspace"],
            target="frontend",
        )
    )

    assert state["status"] == "stopped"
    assert state["frontend_url"] is None



@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (
            lambda data: data["projects"]["demo"]["preview"]["frontend"]["daemon"].update(
                {"name": "bad name;rm"}
            ),
            "daemon name is invalid",
        ),
        (
            lambda data: data["projects"]["demo"]["preview"]["frontend"]["daemon"].update(
                {"directory": "/tmp/frontend"}
            ),
            "directory must stay under /var/www/html",
        ),
        (
            lambda data: data["projects"]["demo"]["preview"]["frontend"]["daemon"].update(
                {"https_port": 70000}
            ),
            "https_port must be a valid port",
        ),
    ],
)
def test_preview_contract_rejects_invalid_checked_in_frontend_config(
    tmp_path,
    monkeypatch,
    mutator,
    expected,
):
    _source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    projects_file = tmp_path / "projects.yml"
    data = yaml.safe_load(projects_file.read_text())
    mutator(data)
    projects_file.write_text(yaml.safe_dump(data))

    source = Path(data["projects"]["demo"]["path"]).resolve()
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewbad", project_id="demo")
    )

    with pytest.raises(HTTPException) as exc:
        start_preview(
            PreviewRequest(
                job_id="jobpreviewbad",
                project_id="demo",
                workspace=created["workspace"],
                target="frontend",
            )
        )

    assert exc.value.status_code == 500
    assert expected in str(exc.value.detail)
    assert source.exists()



def test_direct_backend_only_preview_uses_shared_ddev_without_frontend_override(
    tmp_path,
    monkeypatch,
):
    source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewback", project_id="demo")
    )
    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append(list(argv))
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)
    request = PreviewRequest(
        job_id="jobpreviewback",
        project_id="demo",
        workspace=created["workspace"],
        target="backend",
    )

    started = start_preview(request)
    stopped = stop_preview(request)

    assert started["status"] == "ready"
    assert started["backend_url"] == "https://demo.ddev.site"
    assert started["frontend_url"] is None
    assert "shared direct-workspace DDEV runtime" in started["integration_note"]
    assert "does not stop DDEV or remove its data" in started["integration_note"]
    assert stopped["status"] == "stopped"
    assert not (source / ".ddev" / "config.pcp-preview.local.yaml").exists()
    assert calls == [["ddev", "start", "-y"]]
    assert source.exists()


@pytest.mark.parametrize(
    ("target", "field_path", "bad_value", "expected"),
    [
        (
            "backend",
            ("backend", "url"),
            "https://example.com",
            "local HTTPS DDEV URL",
        ),
        (
            "frontend",
            ("frontend", "url"),
            "http://demo.ddev.site:3100",
            "local HTTPS DDEV URL",
        ),
        (
            "both",
            ("frontend", "api_origin_on_both"),
            "https://example.com",
            "local HTTPS DDEV URL",
        ),
    ],
)
def test_preview_contract_rejects_nonlocal_or_unsafe_urls(
    tmp_path,
    monkeypatch,
    target,
    field_path,
    bad_value,
    expected,
):
    _source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    projects_file = tmp_path / "projects.yml"
    data = yaml.safe_load(projects_file.read_text())
    section, key = field_path
    data["projects"]["demo"]["preview"][section][key] = bad_value
    projects_file.write_text(yaml.safe_dump(data))

    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewurl", project_id="demo")
    )

    with pytest.raises(HTTPException) as exc:
        start_preview(
            PreviewRequest(
                job_id="jobpreviewurl",
                project_id="demo",
                workspace=created["workspace"],
                target=target,
            )
        )

    assert exc.value.status_code == 500
    assert expected in str(exc.value.detail)


def test_unhealthy_frontend_preview_removes_only_managed_override(
    tmp_path,
    monkeypatch,
):
    source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewbadhealth", project_id="demo")
    )
    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append(list(argv))
        if (
            list(argv)[:5] == ["ddev", "exec", "--raw", "--", "curl"]
            and list(argv)[-1] == "http://127.0.0.1:3100/"
        ):
            return 1, "", "health failed", False
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)

    with pytest.raises(HTTPException) as exc:
        start_preview(
            PreviewRequest(
                job_id="jobpreviewbadhealth",
                project_id="demo",
                workspace=created["workspace"],
                target="frontend",
            )
        )

    assert exc.value.status_code == 502
    assert exc.value.detail == "Frontend preview did not become healthy"
    assert not (source / ".ddev" / "config.pcp-preview.local.yaml").exists()
    assert [
        "ddev",
        "exec",
        "supervisorctl",
        "stop",
        "webextradaemons:pcp-next-dev",
    ] in calls
    assert source.exists()



def test_direct_frontend_preview_requires_configured_node_runtime(tmp_path, monkeypatch):
    _source, _remote, _workspaces = configure_direct_preview(monkeypatch, tmp_path)
    projects_file = tmp_path / "projects.yml"
    data = yaml.safe_load(projects_file.read_text())
    data["projects"]["demo"]["ddev"].pop("workspace_nodejs_version", None)
    projects_file.write_text(yaml.safe_dump(data))
    created = create_workspace(
        WorkspaceRequest(job_id="jobpreviewnode", project_id="demo")
    )

    with pytest.raises(HTTPException) as exc:
        start_preview(
            PreviewRequest(
                job_id="jobpreviewnode",
                project_id="demo",
                workspace=created["workspace"],
                target="frontend",
            )
        )

    assert exc.value.status_code == 500
    assert "requires ddev.workspace_nodejs_version" in str(exc.value.detail)


def test_direct_workspace_returns_clean_owned_ai_branch_to_base(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobreturn123", project_id="demo")
    )
    ai_branch = created["branch"]
    ai_head = run("git", "rev-parse", "HEAD", cwd=source)

    result = return_direct_workspace_to_base(
        ReturnDirectWorkspaceRequest(
            job_id="jobreturn123",
            project_id="demo",
            workspace=created["workspace"],
            branch=ai_branch,
        )
    )

    assert result["returned"] is True
    assert result["reused"] is False
    assert result["branch"] == "main"
    assert run("git", "branch", "--show-current", cwd=source) == "main"
    assert run("git", "status", "--porcelain", cwd=source) == ""
    assert run("git", "rev-parse", ai_branch, cwd=source) == ai_head


def test_direct_workspace_return_to_base_refuses_dirty_repo(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobreturndirty", project_id="demo")
    )
    (source / "HUMAN.txt").write_text("preserve me\n")

    with pytest.raises(HTTPException) as exc:
        return_direct_workspace_to_base(
            ReturnDirectWorkspaceRequest(
                job_id="jobreturndirty",
                project_id="demo",
                workspace=created["workspace"],
                branch=created["branch"],
            )
        )

    assert exc.value.status_code == 409
    assert "will not reset, clean or stash" in str(exc.value.detail)
    assert run("git", "branch", "--show-current", cwd=source) == created["branch"]
    assert (source / "HUMAN.txt").read_text() == "preserve me\n"


def test_direct_workspace_return_to_base_refuses_branch_mismatch(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    created = create_workspace(
        WorkspaceRequest(job_id="jobreturnmismatch", project_id="demo")
    )
    run("git", "checkout", "main", cwd=source)
    run("git", "checkout", "-b", "human/manual", cwd=source)

    with pytest.raises(HTTPException) as exc:
        return_direct_workspace_to_base(
            ReturnDirectWorkspaceRequest(
                job_id="jobreturnmismatch",
                project_id="demo",
                workspace=created["workspace"],
                branch=created["branch"],
            )
        )

    assert exc.value.status_code == 409
    assert "branch changed outside the owning job" in str(exc.value.detail)
    assert run("git", "branch", "--show-current", cwd=source) == "human/manual"
