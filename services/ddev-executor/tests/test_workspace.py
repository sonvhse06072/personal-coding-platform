from pathlib import Path
import subprocess

import yaml

from app.main import WorkspaceRequest, create_workspace, remove_workspace


def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def test_workspace_is_self_contained_clone(tmp_path, monkeypatch):
    source_root = tmp_path / "projects"
    source = source_root / "demo"
    workspaces = tmp_path / "workspaces"
    source.mkdir(parents=True)
    workspaces.mkdir()

    run("git", "init", "-b", "main", cwd=source)
    run("git", "config", "user.email", "test@example.com", cwd=source)
    run("git", "config", "user.name", "Test", cwd=source)
    (source / "README.md").write_text("hello\n")
    run("git", "add", "README.md", cwd=source)
    run("git", "commit", "-m", "initial", cwd=source)
    commit = run("git", "rev-parse", "HEAD", cwd=source)

    config = tmp_path / "projects.yml"
    config.write_text(yaml.safe_dump({
        "projects": {
            "demo": {
                "path": str(source),
                "base_branch": "main",
                "runtime": {"branch_prefix": "ai"},
                "ddev": {"enabled": False},
            }
        }
    }))
    monkeypatch.setenv("PROJECTS_FILE", str(config))
    monkeypatch.setenv("CODING_WORKSPACES_ROOT", str(workspaces))

    result = create_workspace(WorkspaceRequest(job_id="job12345", project_id="demo"))
    workspace = Path(result["workspace"])

    assert result["source_commit"] == commit
    assert result["workspace_mode"] == "isolated_clone"
    assert (workspace / ".git").is_dir(), "workspace must not point back to the source .git directory"
    assert run("git", "rev-parse", "HEAD", cwd=workspace) == commit
    assert run("git", "branch", "--show-current", cwd=workspace) == "ai/job12345"

    removed = remove_workspace(job_id="job12345", project_id="demo", workspace=str(workspace))
    assert removed["removed"] is True
    assert not workspace.exists()
