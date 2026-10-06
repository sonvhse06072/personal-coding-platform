import json
import subprocess
from pathlib import Path

from app.repo import diff_state


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "pcp@example.test")
    _git(repo, "config", "user.name", "PCP Test")
    frontend = repo / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "private": True,
                "scripts": {
                    "test:browser": "playwright test",
                    "test:visual": "node scripts/capture.mjs",
                },
                "dependencies": {"react": "19.0.0"},
                "devDependencies": {"playwright": "1.55.0"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    return repo


def test_diff_state_does_not_classify_package_script_only_change_as_dependency(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    package = repo / "frontend" / "package.json"
    document = json.loads(package.read_text(encoding="utf-8"))
    document["scripts"]["test:browser"] = (
        "node scripts/prepare-public-profile-demo.mjs && playwright test"
    )
    document["scripts"]["test:visual"] = "node scripts/run-visual-evidence.mjs"
    package.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    diff = diff_state(repo, 500_000, base_ref="HEAD")

    assert diff["changed_files"] == ["frontend/package.json"]
    assert diff["dependency_manifest_changes"] == []


def test_diff_state_classifies_package_dependency_version_change(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    package = repo / "frontend" / "package.json"
    document = json.loads(package.read_text(encoding="utf-8"))
    document["devDependencies"]["playwright"] = "1.56.0"
    package.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    diff = diff_state(repo, 500_000, base_ref="HEAD")

    assert diff["dependency_manifest_changes"] == ["frontend/package.json"]


def test_diff_state_lockfile_change_remains_material(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    lockfile = repo / "frontend" / "package-lock.json"
    lockfile.write_text('{"lockfileVersion":3}\n', encoding="utf-8")
    _git(repo, "add", "frontend/package-lock.json")
    _git(repo, "commit", "-qm", "add lock")

    lockfile.write_text('{"lockfileVersion":3,"packages":{"":{"name":"demo"}}}\n', encoding="utf-8")

    diff = diff_state(repo, 500_000, base_ref="HEAD")

    assert diff["dependency_manifest_changes"] == ["frontend/package-lock.json"]
