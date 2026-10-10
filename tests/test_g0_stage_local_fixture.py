"""Source-only fixture staging tests; NEVER clone or inspect user projects.

gh and git are stubbed; the tests write only within pytest tmp_path.
"""
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/g0-stage-local-fixture.py"
spec = importlib.util.spec_from_file_location("g0_stage_fixture", FILE)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def synthetic_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(fixture.os, "geteuid", lambda: 1000)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return home


def mock_gh(monkeypatch, *, pcp_seed=None, direct_seed=None, privacy=True):
    issued = []
    def fake_call(argv, *, timeout=40):
        issued.append(tuple(argv))
        if argv[:3] == ["gh", "auth", "status"]:
            return ""
        if argv[:2] == ["gh", "api"]:
            endpoint = argv[2]
            if endpoint.endswith("/git/ref/heads/benchmark/pcp"):
                return json.dumps({"object": {"sha": pcp_seed or fixture.SOURCE_COMMIT}})
            if endpoint.endswith("/git/ref/heads/benchmark/direct"):
                return json.dumps({"object": {"sha": direct_seed or fixture.SOURCE_COMMIT}})
            if endpoint == "repos/" + fixture.REPOSITORY:
                return json.dumps({"full_name": fixture.REPOSITORY, "private": privacy})
        if argv[:3] == ["gh", "repo", "clone"]:
            target = Path(argv[4])
            target.mkdir()
            (target / ".git").mkdir()
            return ""
        raise AssertionError("Unapproved shell/network command: " + repr(argv))
    monkeypatch.setattr(fixture, "call", fake_call)
    return issued


def test_read_only_inspect_does_not_create_parent_or_invoke_codex(tmp_path, monkeypatch):
    home = synthetic_home(tmp_path, monkeypatch)
    issued = mock_gh(monkeypatch)
    result = fixture.stage(home, create=False)
    assert result["stage_status"] == "eligible_for_new_checkout"
    assert result["ready_to_dispatch_g0d_t01"] is False
    assert not (home / "pcp-g0-fixtures").exists()
    assert len(issued) == 4
    assert all(cmd[0] == "gh" for cmd in issued)
    assert not any("clone" in cmd for cmd in issued)


def test_correct_two_remote_branch_shas_and_private_repo_are_mandatory(tmp_path, monkeypatch):
    home = synthetic_home(tmp_path, monkeypatch)
    for kwargs in (
        {"pcp_seed": "b" * 40},
        {"direct_seed": "c" * 40},
        {"privacy": False},
    ):
        issued = mock_gh(monkeypatch, **kwargs)
        with pytest.raises(fixture.StageStopped):
            fixture.stage(home, create=True)
        assert not (home / "pcp-g0-fixtures").exists()
        assert not any("clone" in cmd for cmd in issued)


def test_existing_folder_and_symlink_fail_before_any_gh_operation(tmp_path, monkeypatch):
    home = synthetic_home(tmp_path, monkeypatch)
    called = []
    monkeypatch.setattr(fixture, "call", lambda argv, **k: called.append(argv))
    parent = home / "pcp-g0-fixtures"
    parent.mkdir()
    (parent / fixture.FOLDER).mkdir()
    with pytest.raises(fixture.StageStopped, match="already_exists"):
        fixture.stage(home, create=True)
    assert called == []
    (parent / fixture.FOLDER).rmdir()
    (parent / fixture.FOLDER).symlink_to(home, target_is_directory=True)
    with pytest.raises(fixture.StageStopped, match="already_exists"):
        fixture.stage(home, create=True)
    assert called == []


def test_parent_symlink_and_github_actions_environment_are_rejected(tmp_path, monkeypatch):
    home = synthetic_home(tmp_path, monkeypatch)
    (home / "pcp-g0-fixtures").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(fixture.StageStopped, match="parent_invalid"):
        fixture.stage(home, create=False)
    (home / "pcp-g0-fixtures").unlink()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(fixture.StageStopped, match="owner_wsl_only"):
        fixture.stage(home, create=False)


def test_explicit_create_only_calls_one_frozen_branch_clone(tmp_path, monkeypatch):
    home = synthetic_home(tmp_path, monkeypatch)
    issued = mock_gh(monkeypatch)
    observed = []
    def verified(target):
        observed.append(target)
        assert target == home / "pcp-g0-fixtures" / fixture.FOLDER
        assert (target / ".git").is_dir()
        return {"head_sha": fixture.SOURCE_COMMIT, "branch": fixture.SOURCE_BRANCH}
    monkeypatch.setattr(fixture, "verify_new_checkout", verified)
    result = fixture.stage(home, create=True)
    assert result["stage_status"] == "clean_new_source_checkout_verified"
    assert result["ready_to_dispatch_g0d_t01"] is False
    assert len(observed) == 1
    clones = [c for c in issued if c[:3] == ("gh", "repo", "clone")]
    assert len(clones) == 1
    assert clones[0][3] == fixture.REPOSITORY
    assert clones[0][5:] == (
        "--", "--branch", "benchmark/pcp", "--single-branch", "--no-tags",
    )


@pytest.mark.parametrize(("origin", "expected"), [
    ("https://github.com/sonvhse06072/pcp-g0-drupal-fixture.git", True),
    ("git@github.com:sonvhse06072/pcp-g0-drupal-fixture.git", True),
    ("https://evil.example/sonvhse06072/pcp-g0-drupal-fixture", False),
    ("https://token@github.com/sonvhse06072/pcp-g0-drupal-fixture", False),
    ("https://github.com/sonvhse06072/chonhac", False),
    ("file:///home/sonvh/chonhac", False),
])
def test_origin_identity_and_no_embedded_credentials(origin, expected):
    assert fixture.allowed_origin(origin) is expected


def test_checkout_verifier_is_read_only_and_pinned_to_lock_digest(tmp_path, monkeypatch):
    dst = tmp_path / fixture.FOLDER
    (dst / ".git").mkdir(parents=True)
    (dst / "PROJECT-BASELINE.md").write_text("candidate only")
    (dst / "composer.lock").write_text("fake")
    issued = []
    def git_call(argv, *, timeout=40):
        issued.append(argv)
        if argv[-2:] == ["rev-parse", "HEAD"]:
            return fixture.SOURCE_COMMIT
        if argv[-2:] == ["branch", "--show-current"]:
            return fixture.SOURCE_BRANCH
        if argv[-2:] == ["status", "--porcelain=v1"]:
            return ""
        if argv[-3:] == ["remote", "get-url", "origin"]:
            return "https://github.com/" + fixture.REPOSITORY + ".git"
        raise AssertionError("Unexpected command")
    monkeypatch.setattr(fixture, "call", git_call)
    with pytest.raises(fixture.StageStopped, match="lock_digest_mismatch"):
        fixture.verify_new_checkout(dst)
    assert len(issued) == 4


def test_unsupported_commands_rejected_before_spawn(monkeypatch):
    def fail_spawn(*args, **kwargs):
        pytest.fail("unsupported process must never spawn")
    monkeypatch.setattr(fixture.subprocess, "run", fail_spawn)
    with pytest.raises(fixture.StageStopped):
        fixture.call(["docker", "system", "prune"])
    with pytest.raises(fixture.StageStopped):
        fixture.call(["ddev", "start"])
    with pytest.raises(fixture.StageStopped):
        fixture.call(["codex", "exec", "task"])
