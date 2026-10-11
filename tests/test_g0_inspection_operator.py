"""Offline tests for owner-approved G0 inspection activation and rollback.

No test invokes real Docker, DDEV, GitHub, Git, network or provider inference.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/g0-inspection-operator.py"
spec = importlib.util.spec_from_file_location("g0_inspection_operator", SOURCE)
operator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operator)
HEAD = "a" * 40


def test_exact_project_names_and_profile_are_not_dynamic():
    assert operator.PROJECT == "pcp-g0d01"
    assert operator.PROFILE == "owner-gated-g0"
    assert operator.NETWORK == "pcp-g0d01-private"
    assert operator.DATA_VOLUME == "pcp-g0d01-postgres-data"
    assert set(operator.NAMES) == {"db", "router", "executor", "runtime"}
    assert all(n.startswith("pcp-g0d01-") for n in operator.NAMES.values())
    assert operator.resource_names(HEAD) == {
        "router": "pcp-g0d01-router:aaaaaaaaaaaa",
        "executor": "pcp-g0d01-executor:aaaaaaaaaaaa",
        "runtime": "pcp-g0d01-runtime:aaaaaaaaaaaa",
    }


def test_compose_environment_strips_inherited_profile_and_provider_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPOSE_PROFILES", "dangerous")
    monkeypatch.setenv("PCP_G0_RUNTIME_IMAGE", "wrong")
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-leak")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "must-not-leak")
    env = operator.compose_env(tmp_path, tmp_path / "fixture", tmp_path / "work", HEAD, "f" * 48)
    assert env["COMPOSE_PARALLEL_LIMIT"] == "1"
    assert env["PCP_G0_POSTGRES_IMAGE"] == "postgres:17"
    assert env["PCP_G0_RUNTIME_IMAGE"] == "pcp-g0d01-runtime:aaaaaaaaaaaa"
    assert env["PCP_G0_DB_PASSWORD"] == "f" * 48
    assert "COMPOSE_PROFILES" not in env
    assert "GITHUB_TOKEN" not in env
    assert "OPENAI_API_KEY" not in env
    assert "ANTIGRAVITY_BRIDGE_TOKEN" not in env
    assert "CODEX_PASSWORD" not in {
        key for key in env if key.startswith("PCP_G0_")
    }
    argv = operator.compose_args(tmp_path)
    assert argv[:4] == ["docker", "compose", "-p", "pcp-g0d01"]
    assert argv[-2:] == ["--profile", operator.PROFILE]
    assert argv[5] == str(tmp_path / "deploy/g0/compose.candidate.yml")


def test_wrong_expected_commit_fails_before_external_calls(monkeypatch, tmp_path):
    monkeypatch.setattr(operator, "run", lambda *a, **k: pytest.fail("unexpected external command"))
    for invalid in ("", "ABC", "b" * 39, "b" * 41):
        with pytest.raises(operator.GateError, match="expected_source_sha_required"):
            operator.preflight(tmp_path, tmp_path, invalid)


def test_readonly_git_identity_and_dirty_worktree_gates(monkeypatch, tmp_path):
    observed = []
    def fake_run(argv, **kwargs):
        observed.append(argv)
        if argv[-3:] == ["remote", "get-url", "origin"]:
            return "https://github.com/sonvhse06072/personal-coding-platform"
        if argv[-2:] == ["branch", "--show-current"]:
            return "main"
        if argv[-2:] == ["rev-parse", "HEAD"]:
            return HEAD
        if argv[-2:] == ["status", "--porcelain=v1"]:
            return " M protected.txt"
        raise AssertionError(argv)
    monkeypatch.setattr(operator, "run", fake_run)
    with pytest.raises(operator.GateError, match="git_worktree_dirty"):
        operator.require_exact_repo(tmp_path, operator.EXPECTED_REPO, "main", HEAD)
    assert all(cmd[:2] == ["git", "-C"] for cmd in observed)


def test_missing_docker_resource_is_not_mistaken_for_daemon_failure(monkeypatch):
    def fake_cli(argv, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="Error: No such object: g0")
    monkeypatch.setattr(operator.subprocess, "run", fake_cli)
    assert operator.exists("container", "pcp-g0d01-postgres") is False
    monkeypatch.setattr(operator.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=1, stdout="", stderr="permission denied"))
    with pytest.raises(operator.GateError, match="docker_inspection_unexpected_error"):
        operator.exists("volume", operator.DATA_VOLUME)


def test_collisions_fail_without_mutating_any_resource(monkeypatch):
    names = []
    def fake_exists(kind, name):
        names.append((kind, name))
        return kind == "container" and name == "pcp-g0d01-runtime-1"
    monkeypatch.setattr(operator, "exists", fake_exists)
    with pytest.raises(operator.GateError, match="g0_container_identity_already_exists"):
        operator.require_no_g0_collision(HEAD)
    assert all(kind == "container" for kind, _ in names)
    assert all(name in operator.NAMES.values() for _, name in names)


def test_base_images_need_local_pins(monkeypatch):
    monkeypatch.setattr(operator, "exists", lambda kind, name: False)
    monkeypatch.setattr(operator, "inspect", lambda kind, name: {"Id": "sha256:" + "a" * 64})
    monkeypatch.setattr(operator, "run", lambda *a, **k: "")
    with pytest.raises(operator.GateError, match="postgres17_not_cached_no_implicit_pull"):
        operator.require_no_g0_collision(HEAD)


def test_offline_overlay_builds_use_only_g0_tags(monkeypatch, tmp_path):
    commands = []
    image_id = "sha256:" + "c" * 64
    def fake_inspect(kind, name):
        if kind != "image":
            raise AssertionError(kind)
        if name in operator.BASE_IMAGES.values():
            return {"Id": image_id}
        return {"Config": {"Labels": {
            "org.opencontainers.image.revision": HEAD,
            "org.opencontainers.image.pcp.g0": "inspection-only",
        }}}
    def fake_run(argv, **kwargs):
        commands.append((argv, kwargs))
        return ""
    monkeypatch.setattr(operator, "inspect", fake_inspect)
    monkeypatch.setattr(operator, "run", fake_run)
    operator.build_g0_overlays(tmp_path, HEAD)
    tags = [a for a, _ in commands if a[:2] == ["docker", "tag"]]
    builds = [(a, opts) for a, opts in commands if a[:2] == ["docker", "build"]]
    assert len(tags) == len(builds) == 3
    for args, options in builds:
        assert "--network=none" in args
        assert "--pull=false" in args
        assert "app /app/app" in options["stdin"]
        assert "from github" not in options["stdin"].lower()
        assert options["timeout"] <= 180
        assert any(tag in args for tag in operator.resource_names(HEAD).values())
    assert not any("docker.sock" in str(a) for a, _ in commands)


def test_verification_scopes_all_inspections_to_exact_g0_resources(monkeypatch, tmp_path):
    inspections = []
    calls = []
    def fake_inspect(kind, name):
        inspections.append((kind, name))
        if kind == "network":
            assert name == operator.NETWORK
            return {"Internal": True}
        if kind == "volume":
            assert name == operator.DATA_VOLUME
            return {"Labels": {"com.docker.compose.project": operator.PROJECT}}
        assert kind == "container"
        svc = next(s for s, n in operator.NAMES.items() if n == name)
        return {
            "Config": {"Labels": {
                "com.docker.compose.project": operator.PROJECT,
                "com.docker.compose.service": svc,
            }},
            "State": {"Running": True},
            "NetworkSettings": {"Networks": {operator.NETWORK: {}}},
            "HostConfig": {"Privileged": False, "PortBindings": {}},
            "Mounts": [],
        }
    monkeypatch.setattr(operator, "inspect", fake_inspect)
    monkeypatch.setattr(operator, "run", lambda argv, **kw: calls.append(argv) or "")
    result = operator.verify_inspection(tmp_path, {})
    assert result["status"] == "PASS"
    assert result["ready_to_dispatch_g0d_t01"] is False
    assert set(inspections) == {
        *{("container", n) for n in operator.NAMES.values()},
        ("network", operator.NETWORK),
        ("volume", operator.DATA_VOLUME),
    }
    assert len([a for a in calls if "exec" in a]) == 4
    assert not any("stop" in a or "down" in a for a in calls)


def test_verification_rejects_wrong_container_ownership(monkeypatch, tmp_path):
    monkeypatch.setattr(operator, "inspect", lambda kind, name: {
        "Config": {"Labels": {"com.docker.compose.project": "other"}},
        "State": {"Running": True},
    })
    monkeypatch.setattr(operator, "run", lambda *a, **k: pytest.fail("never exec other container"))
    with pytest.raises(operator.GateError, match="g0_container_ownership_mismatch"):
        operator.verify_inspection(tmp_path, {})


def test_partial_rollback_stops_only_verified_g0_names(monkeypatch, tmp_path):
    found = []
    monkeypatch.setattr(operator, "exists",
                        lambda kind, name: name in {
                            "pcp-g0d01-postgres", "pcp-g0d01-router-1"
                        })
    def fake_inspect(kind, name):
        svc = next(s for s, n in operator.NAMES.items() if n == name)
        return {
            "Config": {"Labels": {
                "com.docker.compose.project": operator.PROJECT,
                "com.docker.compose.service": svc,
            }},
            "State": {"Running": svc == "router"},
        }
    monkeypatch.setattr(operator, "inspect", fake_inspect)
    monkeypatch.setattr(operator, "run", lambda argv, **kw: found.append(argv) or "")
    result = operator.stop_g0(tmp_path, tmp_path)
    assert found == [["docker", "stop", "--time", "15", "pcp-g0d01-router-1"]]
    assert result["running_g0_services_stopped"] == 1
    assert result["g0_db_volume_preserved"]
    assert result["legacy_services_touched"] is False


def test_rollback_fails_closed_for_foreign_identity(monkeypatch, tmp_path):
    monkeypatch.setattr(operator, "exists", lambda kind, name: True)
    monkeypatch.setattr(operator, "inspect", lambda kind, name: {
        "Config": {"Labels": {"com.docker.compose.project": "not-g0"}},
        "State": {"Running": True},
    })
    monkeypatch.setattr(operator, "run", lambda *a, **k: pytest.fail("must not stop"))
    with pytest.raises(operator.GateError, match="g0_stop_identity_mismatch"):
        operator.stop_g0(tmp_path, tmp_path)


def test_private_g0_state_never_logs_password(monkeypatch, tmp_path):
    monkeypatch.setattr(operator.Path, "home", lambda: tmp_path)
    workspace = operator.save_private_state(tmp_path, "a" * 48, HEAD)
    assert workspace.is_dir()
    assert workspace.parent.name == ".pcp-g0d01"
    sha, password, observed_root = operator.read_private_state(tmp_path)
    assert sha == HEAD and password == "a" * 48
    assert observed_root == workspace
    assert workspace.parent.stat().st_mode & 0o077 == 0
    assert (workspace.parent / "owner-state.json").stat().st_mode & 0o077 == 0
    with pytest.raises(operator.GateError, match="g0_private_state_already_exists"):
        operator.save_private_state(tmp_path, "b" * 48, HEAD)


def test_source_contains_no_global_docker_or_chonhac_control():
    code = SOURCE.read_text(encoding="utf-8")
    for forbidden in (
        "docker system prune", "ddev start", "ddev poweroff",
        "chonhac/", "docker compose down",
        "docker restart", "docker stop --all", "git reset --hard",
        "rm -rf", "--remove-orphans", "--volumes",
    ):
        assert forbidden not in code
    assert '"ready_to_dispatch_g0d_t01": False' in code
    # This string is required to *deny* an accidental socket mount after startup.
    assert 'm.get("Destination") == "/var/run/docker.sock"' in code
