from pathlib import Path
import subprocess

import pytest
import yaml
from fastapi import HTTPException

from app import main as main_module
from app.main import (
    AdvanceDirectWorkspaceSourceRequest,
    PhaseRequest,
    SyncDirectBaseRequest,
    PreviewRequest,
    PublishBranchRequest,
    QuiesceWorkspaceRequest,
    ReturnDirectWorkspaceRequest,
    WorkspaceRequest,
    advance_direct_workspace_source,
    create_workspace,
    phase,
    preview_status,
    project_state,
    publish_branch,
    start_preview,
    stop_preview,
    quiesce_workspace,
    remove_workspace,
    return_direct_workspace_to_base,
    sync_direct_base,
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
    assert result["branch"] == f"ai/{'jobdirectsync'[:12]}"
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
    assert "frontend/page.tsx" in run("git", "status", "--porcelain", "--untracked-files=all", cwd=source)

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


def test_direct_phase_reuses_ready_running_ddev_when_opted_in(tmp_path, monkeypatch):
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
        "reuse_running_direct_ddev": True,
        "targeted_tests": ["ddev exec echo ok"],
    }
    projects_file.write_text(yaml.safe_dump(data))

    created = create_workspace(
        WorkspaceRequest(job_id="jobdirectreuse", project_id="demo")
    )
    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append((list(argv), timeout))
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)

    response = phase(
        PhaseRequest(
            job_id="jobdirectreuse",
            project_id="demo",
            workspace=created["workspace"],
            phase="targeted_tests",
        )
    )

    assert response.passed is True
    assert calls[0][0] == ["ddev", "exec", "true"]
    assert calls[0][1] == 30
    assert calls[1][0] == ["bash", "-lc", "ddev exec echo ok"]
    assert len(response.infrastructure) == 1
    assert response.infrastructure[0].command == "ddev exec true"
    assert response.infrastructure[0].returncode == 0


def test_direct_phase_falls_back_to_start_when_readiness_probe_fails(tmp_path, monkeypatch):
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
        "reuse_running_direct_ddev": True,
        "targeted_tests": ["ddev exec echo ok"],
    }
    projects_file.write_text(yaml.safe_dump(data))

    created = create_workspace(
        WorkspaceRequest(job_id="jobdirectfallback", project_id="demo")
    )
    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append(list(argv))
        if list(argv) == ["ddev", "exec", "true"]:
            return 1, "", "not running", False
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)

    response = phase(
        PhaseRequest(
            job_id="jobdirectfallback",
            project_id="demo",
            workspace=created["workspace"],
            phase="targeted_tests",
        )
    )

    assert response.passed is True
    assert calls[0] == ["ddev", "exec", "true"]
    assert calls[1] == ["ddev", "start", "-y"]
    assert calls[2] == ["bash", "-lc", "ddev exec echo ok"]
    assert [item.command for item in response.infrastructure] == [
        "ddev exec true",
        "ddev start -y",
    ]


def test_direct_phase_starts_when_ddev_config_is_dirty(tmp_path, monkeypatch):
    source, _remote, _workspaces = configure_direct(
        monkeypatch, tmp_path, allow_push=False
    )
    ddev = source / ".ddev"
    ddev.mkdir()
    config = ddev / "config.yaml"
    config.write_text("name: demo\ntype: drupal11\n")
    run("git", "add", ".ddev/config.yaml", cwd=source)
    run("git", "commit", "-m", "add ddev", cwd=source)
    run("git", "push", "origin", "main", cwd=source)

    projects_file = tmp_path / "projects.yml"
    data = yaml.safe_load(projects_file.read_text())
    data["projects"]["demo"]["ddev"] = {
        "enabled": True,
        "reuse_running_direct_ddev": True,
        "targeted_tests": ["ddev exec echo ok"],
    }
    projects_file.write_text(yaml.safe_dump(data))

    created = create_workspace(
        WorkspaceRequest(job_id="jobdirectdirty", project_id="demo")
    )
    config.write_text("name: demo\ntype: drupal11\nphp_version: 8.4\n")
    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append(list(argv))
        return 0, "ok\n", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)

    response = phase(
        PhaseRequest(
            job_id="jobdirectdirty",
            project_id="demo",
            workspace=created["workspace"],
            phase="targeted_tests",
        )
    )

    assert response.passed is True
    assert calls[0] == ["ddev", "start", "-y"]
    assert calls[1] == ["bash", "-lc", "ddev exec echo ok"]
    assert len(response.infrastructure) == 1
    assert response.infrastructure[0].command == "ddev start -y"



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



def test_direct_planning_clone_materializes_baseline_from_remote_tracking_ref(
    tmp_path, monkeypatch,
):
    source, remote, workspaces = configure_direct(
        monkeypatch, tmp_path, allow_push=False
    )
    stale_main = run("git", "rev-parse", "main", cwd=source)
    run("git", "checkout", "-b", "ai/historical-job", cwd=source)
    historical_head = run("git", "rev-parse", "HEAD", cwd=source)

    remote_head = _advance_remote_main(
        remote,
        tmp_path,
        filename="POST_PILOT.txt",
        content="governed successor baseline\n",
    )
    run(
        "git",
        "fetch",
        "origin",
        "refs/heads/main:refs/remotes/origin/main",
        cwd=source,
    )

    assert run("git", "branch", "--show-current", cwd=source) == "ai/historical-job"
    assert run("git", "rev-parse", "HEAD", cwd=source) == historical_head
    assert run("git", "rev-parse", "main", cwd=source) == stale_main
    assert run("git", "rev-parse", "origin/main", cwd=source) == remote_head
    run("git", "cat-file", "-e", remote_head + "^{commit}", cwd=source)

    result = create_workspace(
        WorkspaceRequest(
            job_id="plan-remote-ref-123",
            project_id="demo",
            ref=remote_head,
            workspace_mode="isolated_clone",
        )
    )
    workspace = Path(result["workspace"])

    assert result["source_commit"] == remote_head
    assert result["workspace_mode"] == "isolated_clone_no_remote"
    assert workspace == (workspaces / "plan-remote-ref-123").resolve()
    assert run("git", "rev-parse", "HEAD", cwd=workspace) == remote_head
    assert run("git", "remote", cwd=workspace) == ""
    assert subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "show-ref",
            "--verify",
            "--quiet",
            "refs/pcp/materialized-source",
        ],
        text=True,
        capture_output=True,
    ).returncode != 0

    # Planning materialization must not move or modify the direct source repo.
    assert run("git", "branch", "--show-current", cwd=source) == "ai/historical-job"
    assert run("git", "rev-parse", "HEAD", cwd=source) == historical_head
    assert run("git", "rev-parse", "main", cwd=source) == stale_main
    assert run("git", "rev-parse", "origin/main", cwd=source) == remote_head
    assert run("git", "status", "--porcelain", cwd=source) == ""

    removed = remove_workspace(
        job_id="plan-remote-ref-123",
        project_id="demo",
        workspace=str(workspace),
    )
    assert removed["removed"] is True


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



def _configure_cold_start_phase(monkeypatch, tmp_path: Path) -> tuple[str, Path]:
    _source, _remote, workspaces = configure(
        monkeypatch, tmp_path, allow_push=False
    )
    config = tmp_path / "projects.yml"
    data = yaml.safe_load(config.read_text())
    data["projects"]["demo"]["ddev"] = {
        "enabled": True,
        "targeted_tests": ["ddev exec echo check"],
    }
    config.write_text(yaml.safe_dump(data))
    job_id = "jobcoldstart12"
    workspace = workspaces / job_id
    (workspace / ".ddev").mkdir(parents=True)
    (workspace / ".ddev" / "config.yaml").write_text(
        "name: demo\ntype: drupal11\n"
    )
    monkeypatch.setenv("DDEV_COMMAND_TIMEOUT_SECONDS", "1800")
    return job_id, workspace


@pytest.mark.parametrize(
    ("policy", "phase_limit", "expected_start"),
    [
        ("1200", 1700, 1200),
        ("1500", 350, 350),
        (None, 1700, 600),
    ],
)
def test_cold_start_uses_explicit_policy_limited_by_phase(
    tmp_path, monkeypatch, policy, phase_limit, expected_start,
):
    job_id, workspace = _configure_cold_start_phase(monkeypatch, tmp_path)
    if policy is None:
        monkeypatch.delenv("DDEV_START_TIMEOUT_SECONDS", raising=False)
    else:
        monkeypatch.setenv("DDEV_START_TIMEOUT_SECONDS", policy)
    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append((list(argv), timeout))
        return 0, "ok", "", False

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)
    result = phase(
        PhaseRequest(
            job_id=job_id, project_id="demo", workspace=str(workspace),
            phase="targeted_tests", timeout_seconds=phase_limit,
        )
    )

    assert result.passed is True
    assert calls == [
        (["ddev", "start", "-y"], expected_start),
        (["bash", "-lc", "ddev exec echo check"], phase_limit),
    ]
    assert result.infrastructure[0].stderr == ""


@pytest.mark.parametrize("invalid", ["", "oops", "0", "1801", "-3", "99999"])
def test_cold_start_rejects_invalid_timeout_before_spawning(
    tmp_path, monkeypatch, invalid,
):
    job_id, workspace = _configure_cold_start_phase(monkeypatch, tmp_path)
    monkeypatch.setenv("DDEV_START_TIMEOUT_SECONDS", invalid)
    calls = []
    monkeypatch.setattr(
        "app.main.run_tracked",
        lambda *args, **kwargs: calls.append(args),
    )

    with pytest.raises(HTTPException) as exc:
        phase(
            PhaseRequest(
                job_id=job_id, project_id="demo",
                workspace=str(workspace), phase="targeted_tests",
            )
        )

    assert exc.value.status_code == 500
    assert "DDEV_START_TIMEOUT_SECONDS" in str(exc.value.detail)
    assert calls == []


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "timed_out", "expected"),
    [
        (
            124, "Starting demo...\nBuilding project images...\n",
            "Command timed out after 600s", True,
            "ddev_start_timeout stage_hint=image_build",
        ),
        (
            1, "Starting demo...\n", "DDEV config invalid",
            False, "ddev_start_command_failure stage_hint=startup_other",
        ),
        (
            124, "Starting demo...\n", "Command timed out",
            True, "ddev_start_timeout stage_hint=startup_other",
        ),
    ],
)
def test_cold_start_failure_preserves_stage_hint_and_skips_commands(
    tmp_path, monkeypatch, returncode, stdout, stderr, timed_out, expected,
):
    job_id, workspace = _configure_cold_start_phase(monkeypatch, tmp_path)
    monkeypatch.setenv("DDEV_START_TIMEOUT_SECONDS", "600")
    calls = []

    def fake_run_tracked(job, argv, *, cwd, timeout, env):
        calls.append((list(argv), timeout))
        return returncode, stdout, stderr, timed_out

    monkeypatch.setattr("app.main.run_tracked", fake_run_tracked)
    result = phase(
        PhaseRequest(
            job_id=job_id, project_id="demo",
            workspace=str(workspace), phase="targeted_tests",
        )
    )

    assert result.passed is False
    assert result.commands == []
    assert calls == [(["ddev", "start", "-y"], 600)]
    assert len(result.infrastructure) == 1
    evidence = result.infrastructure[0]
    assert evidence.returncode == returncode
    assert evidence.timed_out is timed_out
    assert expected in evidence.stderr
    assert "effective_timeout_seconds=600" in evidence.stderr
    assert stderr in evidence.stderr


def test_phase_request_accepts_visual_quality() -> None:
    request = PhaseRequest(
        job_id="jobvisual123",
        project_id="demo",
        workspace="/tmp/demo",
        phase="visual_quality",
    )

    assert request.phase == "visual_quality"


def test_remote_direct_sync_fast_forwards_to_exact_expected_head(
    tmp_path,
    monkeypatch,
):
    source, remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    old = run("git", "rev-parse", "HEAD", cwd=source)
    remote_head = _advance_remote_main(
        remote,
        tmp_path,
        filename="REMOTE-SYNC.txt",
        content="remote sync\n",
    )
    assert old != remote_head

    result = sync_direct_base(
        SyncDirectBaseRequest(
            project_id="demo",
            expected_remote_head=remote_head,
        )
    )

    assert result["old_head"] == old
    assert result["remote_head"] == remote_head
    assert result["head"] == remote_head
    assert result["fast_forwarded"] is True
    assert result["clean"] is True
    assert run("git", "rev-parse", "HEAD", cwd=source) == remote_head
    assert project_state("demo")["head"] == remote_head


def test_remote_direct_sync_rejects_wrong_expected_sha_without_merge(
    tmp_path,
    monkeypatch,
):
    source, remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    old = run("git", "rev-parse", "HEAD", cwd=source)
    remote_head = _advance_remote_main(
        remote,
        tmp_path,
        filename="WRONG-EXPECTED.txt",
        content="advance\n",
    )
    assert remote_head != old

    with pytest.raises(HTTPException) as exc:
        sync_direct_base(
            SyncDirectBaseRequest(
                project_id="demo",
                expected_remote_head="f" * 40,
            )
        )

    assert exc.value.status_code == 409
    assert "expected exact SHA" in str(exc.value.detail)
    assert run("git", "rev-parse", "HEAD", cwd=source) == old


def test_remote_direct_sync_rejects_dirty_worktree(
    tmp_path,
    monkeypatch,
):
    source, _remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    head = run("git", "rev-parse", "HEAD", cwd=source)
    (source / "HUMAN.txt").write_text("preserve me\n")

    with pytest.raises(HTTPException) as exc:
        sync_direct_base(
            SyncDirectBaseRequest(
                project_id="demo",
                expected_remote_head=head,
            )
        )

    assert exc.value.status_code == 409
    assert "dirty" in str(exc.value.detail)
    assert (source / "HUMAN.txt").read_text() == "preserve me\n"


def test_remote_direct_sync_rejects_active_executor_process(
    tmp_path,
    monkeypatch,
):
    source, _remote, _workspaces = configure_direct(monkeypatch, tmp_path)
    head = run("git", "rev-parse", "HEAD", cwd=source)
    main_module._ACTIVE["busy-job"] = object()
    try:
        with pytest.raises(HTTPException) as exc:
            sync_direct_base(
                SyncDirectBaseRequest(
                    project_id="demo",
                    expected_remote_head=head,
                )
            )
    finally:
        main_module._ACTIVE.pop("busy-job", None)

    assert exc.value.status_code == 409
    assert "active jobs" in str(exc.value.detail)


# GH-815: PCP uses native Docker; ordinary non-PCP workspace tests above retain
# their existing DDEV behavior. All Docker calls below are strict fakes.
@pytest.fixture
def pcp_native(tmp_path, monkeypatch):
    from app import main as executor
    root = tmp_path / 'pcp-local-test815'
    (root / 'sources').mkdir(parents=True)
    job = 'a' * 32
    workspace = root / 'workspaces' / job
    (workspace / 'tests').mkdir(parents=True)
    (workspace / 'tests/test_pcp_light_sample.py').write_text('def test_sample(): assert True\n')
    (workspace / '.ddev').mkdir()
    (workspace / '.ddev/config.yaml').write_text('hooks: {pre-start: [{exec-host: forbidden}]}')
    (workspace / '.ddev/docker-compose.foreign.yaml').write_text('services: {foreign: {}}')
    image = 'sha256:' + 'c' * 64
    activation = dict(base_sha='b'*40, runtime_image_id=image, verification_image=image)
    cfg = {'ddev': {'enabled': True, 'targeted_tests': ['tests/test_pcp_light_sample.py'],
                    'full_tests': ['tests/test_pcp_light_sample.py']}}
    monkeypatch.setattr(executor, '_pcp_identity', lambda *_: (activation, cfg, root))
    monkeypatch.setattr(executor, '_validate_workspace', lambda *args: workspace)
    monkeypatch.setattr(executor, 'git', lambda *args: 'b'*40)
    monkeypatch.setattr(executor.os, 'getuid', lambda: 1000)
    monkeypatch.setattr(executor.os, 'getgid', lambda: 1000)
    return executor, root, workspace, job, activation, cfg


def test_pcp_copy_has_no_ddev_and_preserves_original_and_retry(pcp_native):
    executor, root, workspace, job, a, _ = pcp_native
    payload = executor.PhaseRequest(job_id=job, project_id='pcp-local', workspace=str(workspace), phase='targeted_tests')
    target, fingerprint = executor._pcp_verification_copy(payload, a, root)
    assert not (target/'.ddev').exists() and not (target/'.git').exists()
    assert (workspace/'.ddev/docker-compose.foreign.yaml').is_file()
    assert executor._pcp_verification_copy(payload, a, root) == (target, fingerprint)
    (target/'foreign').write_text('unreviewed')
    with pytest.raises(HTTPException, match='copy_changed'):
        executor._pcp_verification_copy(payload, a, root)
    assert (target/'foreign').is_file()  # No deletion to recover a partial/changed copy.


def test_pcp_copy_refuses_symlink_and_wrong_source(pcp_native, monkeypatch):
    executor, root, workspace, job, a, _ = pcp_native
    payload = executor.PhaseRequest(job_id=job, project_id='pcp-local', workspace=str(workspace), phase='targeted_tests')
    monkeypatch.setattr(executor, 'git', lambda *args: 'd'*40)
    with pytest.raises(HTTPException, match='source_changed'):
        executor._pcp_verification_copy(payload, a, root)
    (workspace/'foreign').symlink_to(root/'outside')
    with pytest.raises(HTTPException, match='symlink_denied'):
        executor._pcp_verification_copy(payload, a, root)


def pcp_image(root, activation):
    return {'Id': activation['runtime_image_id'], 'Config': {'Env': ['PATH=/opt/venv/bin:/usr/bin'],
        'Labels': {'org.pcp.local.instance': root.name,
                   'org.opencontainers.image.revision': activation['base_sha']}}}


@pytest.mark.parametrize('mutation', ['tag', 'different_image', 'source', 'owner', 'volume', 'secret'])
def test_pcp_verification_image_rejects_unowned_or_unsafe(pcp_native, monkeypatch, mutation):
    executor, root, _, _, a, _ = pcp_native
    item = pcp_image(root, a)
    if mutation == 'tag': a['runtime_image_id'] = 'runtime:latest'
    elif mutation == 'different_image': a['verification_image'] = 'sha256:'+'d'*64
    elif mutation == 'source': item['Config']['Labels']['org.opencontainers.image.revision'] = 'd'*40
    elif mutation == 'owner': item['Config']['Labels']['org.pcp.local.instance'] = 'foreign'
    elif mutation == 'volume': item['Config']['Volumes'] = {'/foreign': {}}
    else: item['Config']['Env'].append('GITHUB_TOKEN=fixture-secret')
    monkeypatch.setattr(executor, '_pcp_docker', lambda *args, **kwargs: item)
    with pytest.raises(HTTPException): executor._pcp_verification_image(a, root)


def _exercise_pcp_native_phase(pcp_native, monkeypatch, stdout, exit_code, expected):
    executor, root, workspace, job, a, _ = pcp_native
    calls, inspected = [], []
    container = {}
    cid = 'e'*64
    def inspect(kind, identity, **kwargs):
        inspected.append((kind, identity))
        if kind == 'image': return pcp_image(root, a)
        assert kind == 'container'
        if identity != cid:
            assert kwargs == {'missing_ok': True}
            assert identity.startswith(root.name+'-verify-')
            return None
        return container
    def execute(job_id, argv, **kwargs):
        calls.append(argv)
        assert job_id == job and kwargs['env'] == {'PATH': executor.os.environ.get('PATH', '/usr/bin:/bin')}
        assert argv[:3] == ['docker','--host','unix:///var/run/docker.sock']
        if argv[3] == 'create':
            assert '--pull=never' in argv and '--read-only' in argv and '--network=none' in argv
            assert '--cap-drop=ALL' in argv and '--security-opt=no-new-privileges:true' in argv
            assert '--cpus=1.5' in argv and '--memory=1g' in argv and '--memory-swap=1g' in argv
            assert '--pids-limit=256' in argv and '--workdir=/workspace' in argv
            assert argv[argv.index('--user')+1] == '1000:1000'
            assert argv[argv.index('--entrypoint=/usr/bin/timeout')+1] == '--env'
            mount = argv[argv.index('--mount')+1]
            assert mount.endswith('target=/workspace,readonly,bind-recursive=disabled')
            assert str(root/'sources/.pcp-local-verification') in mount
            assert 'docker.sock' not in mount and '/home/coder' not in mount
            assert '--rm' not in argv and '--env-file' not in argv
            env_args = [argv[i+1] for i,x in enumerate(argv) if x=='--env']
            assert env_args == ['HOME=/tmp','TMPDIR=/tmp']
            image_index = argv.index(a['runtime_image_id'])
            assert argv[image_index+1:image_index+3] == ['--signal=TERM','--kill-after=5s']
            assert argv[image_index+4:image_index+8] == ['/opt/venv/bin/python','-I','-B','-c']
            assert argv[-1] == 'tests/test_pcp_light_sample.py'
            labels = dict(argv[i+1].split('=',1) for i,x in enumerate(argv) if x=='--label')
            container.update({'Id':cid,'Name':'/'+argv[argv.index('--name')+1], 'Image':a['runtime_image_id'],
                'Config':{'Image':a['runtime_image_id'],'Labels':labels,'User':'1000:1000',
                    'WorkingDir':'/workspace','Entrypoint':['/usr/bin/timeout'],
                    'Cmd':argv[image_index+1:],'Env':['PATH=/opt/venv/bin:/usr/bin','HOME=/tmp','TMPDIR=/tmp']},
                'HostConfig':{'Privileged':False,'ReadonlyRootfs':True,'NetworkMode':'none','CapDrop':['ALL'],
                    'SecurityOpt':['no-new-privileges:true'],'Memory':1073741824,'MemorySwap':1073741824,
                    'NanoCpus':1500000000,'PidsLimit':256,'Tmpfs':{'/tmp':'rw,nosuid,nodev,size=268435456,mode=1777'}},
                'Mounts':[{'Type':'bind','Source':str(kwargs['cwd']),'Destination':'/workspace','RW':False}],
                'State':{'Status':'created','Running':False}})
            return 0, cid+'\n', '', False
        if argv[3:6] == ['container','stop','--time']:
            assert argv[6:] == ['5',cid] and container['State']['Running']
            container['State']={'Status':'exited','Running':False,'ExitCode':124}
            return 0, cid, '', False
        assert argv[3:] == ['start','--attach',cid]
        assert container['State']['Status']=='created'
        container['State']=({'Status':'running','Running':True} if exit_code==124 else
                            {'Status':'exited','Running':False,'ExitCode':exit_code})
        return exit_code, 'PCP_TEST_TOOLCHAIN=pytest8.4.1,PyYAML6.0.2\n'+stdout, '', exit_code==124
    monkeypatch.setattr(executor,'_pcp_docker',inspect)
    monkeypatch.setattr(executor,'run_tracked',execute)
    payload=executor.PhaseRequest(job_id=job,project_id='pcp-local',workspace=str(workspace),phase='targeted_tests')
    result=executor.phase(payload)
    assert result.passed is expected and len(result.commands)==1
    assert result.commands[0].returncode==exit_code
    assert len(calls)==(3 if exit_code==124 else 2) and all('ddev' not in c and 'ddev-global-cache' not in c for c in calls)
    assert inspected[0]==('image',a['runtime_image_id'])
    assert container['State']['Status']=='exited'  # Evidence/container retained, never removed.
    if exit_code==86: assert result.infrastructure[0].returncode==86
    if exit_code==124: assert any(c.timed_out for c in result.infrastructure)


@pytest.mark.parametrize('stdout,exit_code,expected', [
    ('3 passed, 1 skipped', 0, True), ('1 skipped', 0, False),
    ('no tests ran', 5, False), ('1 failed, 2 passed', 1, False),
    ('', 86, False), ('', 0, False), ('1 passed', 124, False),
])
def test_pcp_native_phase_executes_only_bounded_owned_container(pcp_native, monkeypatch, stdout, exit_code, expected):
    _exercise_pcp_native_phase(pcp_native, monkeypatch, stdout, exit_code, expected)


@pytest.mark.parametrize('fault', ['socket', 'rw', 'network', 'secret', 'root', 'memory', 'tmpfs', 'image', 'job'])
def test_pcp_actual_container_is_validated_before_execution(pcp_native, monkeypatch, fault):
    executor = pcp_native[0]
    original = executor._pcp_test_identity
    checked = []
    def verify(item, **kwargs):
        original(item, **kwargs)  # Fixture must first satisfy every real invariant.
        checked.append(item['State']['Status'])
        if fault == 'socket': item['Mounts'].append({'Type':'bind','Source':'/var/run/docker.sock'})
        elif fault == 'rw': item['Mounts'][0]['RW'] = True
        elif fault == 'network': item['HostConfig']['NetworkMode'] = 'bridge'
        elif fault == 'secret': item['Config']['Env'].append('GH_TOKEN=fixture-secret')
        elif fault == 'root': item['Config']['User'] = '0:0'
        elif fault == 'memory': item['HostConfig']['Memory'] = 0
        elif fault == 'tmpfs': item['HostConfig']['Tmpfs']['/tmp'] = 'rw,dev,suid'
        elif fault == 'image': item['Image'] = 'sha256:'+'f'*64
        else: item['Config']['Labels']['org.pcp.local.job'] = 'foreign'
        original(item, **kwargs)
    monkeypatch.setattr(executor, '_pcp_test_identity', verify)
    with pytest.raises(HTTPException, match='container_identity_invalid'):
        _exercise_pcp_native_phase(pcp_native, monkeypatch, '3 passed', 0, True)
    assert checked == ['created']


def test_pcp_native_disabled_verification_denies_before_docker(pcp_native, monkeypatch):
    executor, _, workspace, job, _, cfg = pcp_native
    cfg['ddev']['enabled'] = False
    monkeypatch.setattr(executor, '_pcp_docker', lambda *args, **kwargs: pytest.fail('Docker invoked'))
    with pytest.raises(HTTPException, match='phase_denied'):
        executor.phase(executor.PhaseRequest(job_id=job, project_id='pcp-local', workspace=str(workspace), phase='targeted_tests'))


@pytest.mark.parametrize('tests', [[], ['missing'], [None], ['tests/test_pcp_light_a.py']*2])
def test_pcp_native_invalid_checks_never_reach_docker(pcp_native, monkeypatch, tests):
    executor, _, workspace, job, _, cfg = pcp_native
    cfg['ddev']['targeted_tests']=tests
    monkeypatch.setattr(executor,'_pcp_docker',lambda *args,**kwargs:pytest.fail('Docker invoked'))
    with pytest.raises(HTTPException,match='mandatory_tests_missing'):
        executor.phase(executor.PhaseRequest(job_id=job,project_id='pcp-local',workspace=str(workspace),phase='targeted_tests'))


def test_pcp_native_collision_does_not_resume_or_remove(pcp_native,monkeypatch):
    executor,root,workspace,job,a,_=pcp_native
    monkeypatch.setattr(executor,'_pcp_docker',lambda kind,*args,**kw:pcp_image(root,a) if kind=='image' else {'Id':'foreign'})
    monkeypatch.setattr(executor,'run_tracked',lambda *args,**kwargs:pytest.fail('mutated collision'))
    with pytest.raises(HTTPException,match='collision_no_retry'):
        executor.phase(executor.PhaseRequest(job_id=job,project_id='pcp-local',workspace=str(workspace),phase='targeted_tests'))


def test_pcp_clone_omits_legacy_ddev_without_changing_tracked_diff(tmp_path, monkeypatch):
    import hashlib
    from app import main as executor
    root = tmp_path/'pcp-local-testing'
    source = root/'sources/personal-coding-platform'
    source.mkdir(parents=True)
    workspaces = root/'workspaces'
    workspaces.mkdir()
    run('git','init','-b','main',cwd=source)
    run('git','config','user.email','test@example.com',cwd=source)
    run('git','config','user.name','Test',cwd=source)
    (source/'.ddev').mkdir()
    (source/'.ddev/config.yaml').write_text('hooks: {pre-start: [{exec-host: forbidden}]}\n')
    (source/'.ddev/docker-compose.legacy.yaml').write_text('services: {foreign: {}}\n')
    (source/'README.md').write_text('source\n')
    run('git','add','.',cwd=source)
    run('git','commit','-m','source fixture',cwd=source)
    sha = run('git','rev-parse','HEAD',cwd=source)
    a = dict(root=str(root),issue_number=999,body_sha256='b'*64,base_sha=sha,baseline_revision='test')
    job = hashlib.sha256((f"pcp-local:v1:{executor._PCP_REPOSITORY}:999:{'b'*64}:{sha}:test").encode()).hexdigest()[:32]
    registry = tmp_path/'pcp-projects.yml'
    registry.write_text(yaml.safe_dump({'projects': {'pcp-local': {
        'path':str(source),'repository':executor._PCP_REPOSITORY,'registration_status':'approved',
        'base_branch':'main','runtime':{'workspace_mode':'isolated_clone','developer_permission_mode':'bounded'},
        'ddev':{'enabled':True}}}}))
    monkeypatch.setenv('PROJECTS_FILE',str(registry))
    monkeypatch.setenv('CODING_PROJECTS_ROOT',str(root/'sources'))
    monkeypatch.setenv('CODING_WORKSPACES_ROOT',str(workspaces))
    monkeypatch.setattr(executor,'_pcp_activation',lambda:a)
    payload = WorkspaceRequest(job_id=job,project_id='pcp-local',ref=sha,workspace_mode='isolated_clone')
    result = executor.create_workspace(payload)
    workspace = Path(result['workspace'])
    assert not (workspace/'.ddev').exists()
    assert (source/'.ddev/config.yaml').is_file()
    assert run('git','status','--porcelain',cwd=workspace)==''
    assert run('git','rev-parse','HEAD',cwd=workspace)==sha
    with pytest.raises(HTTPException, match='Workspace already exists'):
        executor.create_workspace(payload)
    assert (workspace/'README.md').read_text()=='source\n'


def test_pcp_draft_creation_never_publishes_ready_pr(monkeypatch):
    from types import SimpleNamespace
    from app import main as executor
    calls=[]
    class Reply:
        def __init__(self,data): self.data=data
        def raise_for_status(self): pass
        def json(self): return self.data
    class Client:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def get(self,url,**kwargs): return Reply([])
        def post(self,url,**kwargs):
            calls.append(kwargs['json'])
            return Reply(dict(number=12,html_url='https://github.com/test/pr/12',state='open',draft=True,
                head={'sha':'c'*40,'ref':'ai/'+'a'*12,'repo':{'full_name':executor._PCP_REPOSITORY}},
                base={'ref':'main'}))
    delivery=SimpleNamespace(base='https://api.github.com',_client=Client,
        assert_branch_commit=lambda *args:None)
    cfg={'autonomy':{'allow_create_pr':True}}
    monkeypatch.setattr(executor,'_pcp_identity',lambda *args:({},cfg,None))
    monkeypatch.setattr(executor,'_github_context',lambda cfg:(delivery,executor._PCP_REPOSITORY))
    result=executor.upsert_pull_request(executor.PullRequestRequest(job_id='a'*32,
        project_id='pcp-local',branch='ai/'+'a'*12,expected_commit='c'*40,title='test',body='verified'))
    assert calls[0]['draft'] is True and result['draft'] is True


@pytest.mark.parametrize('fault', [None, 'head', 'reviewer', 'dismissed', 'baseline', 'skipped_suite', 'missing_step', 'missing_suite'])
def test_pcp_pm_review_requires_authenticated_exact_head_and_four_executed_suites(monkeypatch, fault):
    import json
    from copy import deepcopy
    from types import SimpleNamespace
    from app import main as executor
    job='a'*32
    head='b'*40
    a={'base_sha':'c'*40,'baseline_revision':'approved','pm_login':'reviewer'}
    report=dict(verdict='pass',findings=[],job_id=job,source_commit=a['base_sha'],
        expected_head=head,baseline_revision='approved',diff_hash='d'*64,
        summary='Independent review checked source scope, deterministic verification and delivery evidence.')
    pr=dict(state='open',merged=False,head=dict(sha=head,ref='ai/'+job[:12],
        repo=dict(full_name=executor._PCP_REPOSITORY)),base=dict(ref='main'))
    review=dict(user={'login':'reviewer'},commit_id=head,state='COMMENTED')
    names=['structure-tests','python-tests (services/router)','python-tests (services/runtime)',
           'python-tests (services/ddev-executor)']
    jobs=[dict(name=n,conclusion='success',steps=[dict(name='Run tests',conclusion='success')]) for n in names]
    if fault=='head': pr['head']['sha']='e'*40
    if fault=='reviewer': review['user']['login']='developer'
    if fault=='dismissed': review['state']='DISMISSED'
    if fault=='baseline': report['baseline_revision']='wrong'
    if fault=='skipped_suite': jobs[0]['conclusion']='skipped'
    if fault=='missing_step': jobs[0]['steps']=[]
    if fault=='missing_suite': jobs.pop()
    review['body']='<!-- coding-platform:pcp-local-pm-review:v1 -->\n'+json.dumps(report)
    calls=[]
    class Reply:
        def __init__(self,data): self.data=data
        def raise_for_status(self): pass
        def json(self): return deepcopy(self.data)
    class Client:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def get(self,url):
            calls.append(url)
            assert url.startswith('https://api.github.com/repos/'+executor._PCP_REPOSITORY+'/')
            if url.endswith('/pulls/7'): return Reply(pr)
            if url.endswith('/reviews/8'): return Reply(review)
            if '/actions/runs?' in url:
                return Reply({'workflow_runs':[dict(id=10,name='tests',head_sha=head,
                    event='pull_request',status='completed',conclusion='success')]})
            assert url.endswith('/actions/runs/10/jobs?filter=latest&per_page=100')
            return Reply({'jobs':jobs})
    monkeypatch.setattr(executor,'_pcp_identity',lambda *args:(a,{},None))
    monkeypatch.setattr(executor,'_github_context',lambda cfg:(SimpleNamespace(
        base='https://api.github.com',_client=Client),executor._PCP_REPOSITORY))
    monkeypatch.setattr(executor,'github_ci',lambda *args:{'state':'success','commit':head})
    request=executor.PcpLocalReviewRequest(job_id=job,source_commit=a['base_sha'],
        expected_head=head,activation_digest=executor._pcp_digest(a),pr_number=7,review_id=8)
    if fault:
        with pytest.raises(HTTPException): executor.pcp_local_review(request)
    else:
        proof=executor.pcp_local_review(request)
        assert proof['expected_head']==head and proof['ci_run_id']==10
        assert proof['suites']==sorted(names) and proof['report']==report
