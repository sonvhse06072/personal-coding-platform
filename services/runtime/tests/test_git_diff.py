from pathlib import Path
import subprocess

from app.repo import commit_changes, diff_state


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def test_diff_includes_new_file_and_commit_excludes_runtime_ddev_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-q", str(repo)])
    subprocess.check_call(["git", "-C", str(repo), "config", "user.name", "Test"])
    subprocess.check_call(["git", "-C", str(repo), "config", "user.email", "test@example.com"])
    (repo / "README.md").write_text("base\n")
    subprocess.check_call(["git", "-C", str(repo), "add", "README.md"])
    subprocess.check_call(["git", "-C", str(repo), "commit", "-qm", "base"])

    (repo / "new.py").write_text("print('hello')\n")
    (repo / ".ddev").mkdir()
    (repo / ".ddev" / "config.coding-platform.yaml").write_text("name: temporary\n")

    state = diff_state(repo, 100000)
    assert "new.py" in state["changed_files"]
    assert "new.py" in state["diff"]
    assert "config.coding-platform.yaml" not in state["diff"]

    sha = commit_changes(repo, "AI: test")
    assert sha
    tree = git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
    assert "new.py" in tree
    assert ".ddev/config.coding-platform.yaml" not in tree
