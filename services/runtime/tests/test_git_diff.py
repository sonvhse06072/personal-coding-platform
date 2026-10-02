from pathlib import Path
import subprocess

from app.repo import commit_changes, diff_state


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-q", str(repo)])
    subprocess.check_call(["git", "-C", str(repo), "config", "user.name", "Test"])
    subprocess.check_call(["git", "-C", str(repo), "config", "user.email", "test@example.com"])
    (repo / "README.md").write_text("base\n")
    subprocess.check_call(["git", "-C", str(repo), "add", "README.md"])
    subprocess.check_call(["git", "-C", str(repo), "commit", "-qm", "base"])
    return repo


def test_diff_includes_new_file_and_excludes_runtime_generated_files(tmp_path):
    repo = make_repo(tmp_path)

    (repo / "new.py").write_text("print('hello')\n")
    (repo / ".ddev").mkdir()
    (repo / ".ddev" / "config.coding-platform.yaml").write_text("name: temporary\n")
    cache = repo / "pkg" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "module.cpython-311.pyc").write_bytes(b"generated")
    (repo / "generated.pyc").write_bytes(b"generated")
    (repo / "generated.pyo").write_bytes(b"generated")

    state = diff_state(repo, 100000)

    assert state["changed_files"] == ["new.py"]
    assert "new.py" in state["diff"]
    assert "config.coding-platform.yaml" not in state["diff"]
    assert "__pycache__" not in state["diff"]
    assert "generated.pyc" not in state["diff"]
    assert "generated.pyo" not in state["diff"]

    sha = commit_changes(repo, "AI: test")
    assert sha
    tree = git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
    assert "new.py" in tree
    assert ".ddev/config.coding-platform.yaml" not in tree
    assert "pkg/__pycache__/module.cpython-311.pyc" not in tree
    assert "generated.pyc" not in tree
    assert "generated.pyo" not in tree


def test_generated_bytecode_only_is_not_a_material_diff_or_commit(tmp_path):
    repo = make_repo(tmp_path)
    cache = repo / "__pycache__"
    cache.mkdir()
    (cache / "module.cpython-311.pyc").write_bytes(b"generated")

    state = diff_state(repo, 100000)

    assert state["changed_files"] == []
    assert state["changed_file_count"] == 0
    assert state["diff"] == ""
    assert commit_changes(repo, "AI: generated only") is None


def test_tracked_bytecode_remains_visible_and_committable(tmp_path):
    repo = make_repo(tmp_path)
    tracked = repo / "fixtures" / "tracked.pyc"
    tracked.parent.mkdir()
    tracked.write_bytes(b"v1")
    subprocess.check_call(["git", "-C", str(repo), "add", "fixtures/tracked.pyc"])
    subprocess.check_call(["git", "-C", str(repo), "commit", "-qm", "track bytecode"])

    tracked.write_bytes(b"v2")
    cache = repo / "fixtures" / "__pycache__"
    cache.mkdir()
    (cache / "generated.cpython-311.pyc").write_bytes(b"generated")

    state = diff_state(repo, 100000)

    assert state["changed_files"] == ["fixtures/tracked.pyc"]
    assert "fixtures/tracked.pyc" in state["diff"]
    assert "__pycache__" not in state["diff"]

    sha = commit_changes(repo, "AI: tracked bytecode change")
    assert sha
    committed = subprocess.check_output(
        ["git", "-C", str(repo), "show", "HEAD:fixtures/tracked.pyc"]
    )
    assert committed == b"v2"
    tree = git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
    assert "fixtures/__pycache__/generated.cpython-311.pyc" not in tree


def test_diff_state_drops_deleted_intent_to_add_but_preserves_real_changes(tmp_path):
    repo = make_repo(tmp_path)

    temporary = repo / "temporary.php"
    temporary.write_text("<?php echo 'temporary';\n")
    first = diff_state(repo, 100000)
    assert "temporary.php" in first["changed_files"]
    assert "temporary.php" in first["diff"]

    temporary.unlink()
    (repo / "README.md").write_text("real modification\n")
    second = diff_state(repo, 100000)

    assert second["changed_files"] == ["README.md"]
    assert "temporary.php" not in second["diff"]
    assert "README.md" in second["diff"]
    assert "temporary.php" not in git(
        repo,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )


def test_diff_state_preserves_tracked_deletion(tmp_path):
    repo = make_repo(tmp_path)
    tracked = repo / "tracked.txt"
    tracked.write_text("tracked\n")
    subprocess.check_call(["git", "-C", str(repo), "add", "tracked.txt"])
    subprocess.check_call(["git", "-C", str(repo), "commit", "-qm", "track file"])

    tracked.unlink()
    state = diff_state(repo, 100000)

    assert state["changed_files"] == ["tracked.txt"]
    assert "deleted file mode" in state["diff"]
    assert "tracked.txt" in state["diff"]
