"""Synthetic checks for the Owner's one-pass G1 WSL *read-only* admission.

No Git mutations, Docker service starts, DDEV commands beyond --version/list,
real Codex agent turns, host credentials or active project inspection.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/g1-trusted-codex-readiness.py"
SPEC = importlib.util.spec_from_file_location("g1_smoke_readiness", SCRIPT)
assert SPEC and SPEC.loader
g1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(g1)

SOURCE_SHA = "a" * 40
DOCKER_WEB = "ddev-pcp-g1-codex-smoke-web"


class Runner:
    """Exact protocol snapshot; every command must be an approved read-only op."""

    def __init__(self):
        self.calls = []
        self.responses = {
            ("git", "-C", "/pcp", "rev-parse", "HEAD"): (0, SOURCE_SHA, ""),
            ("git", "-C", "/pcp", "status", "--porcelain"): (0, "", ""),
            ("docker", "context", "inspect"): (
                0, json.dumps([{"Endpoints": {"docker": {
                    "Host": "unix:///var/run/docker.sock",
                }}}]), "",
            ),
            ("docker", "info", "--format", "{{json .}}"): (
                0, json.dumps({
                    "OperatingSystem": "Docker Desktop",
                    "ServerVersion": "28.1.1",
                }), "",
            ),
            ("docker", "container", "ls", "--all", "--format", "{{json .}}"): (
                0, "", "",
            ),
            ("docker", "volume", "ls", "--format", "{{json .}}"): (
                0, "", "",
            ),
            ("docker", "network", "ls", "--format", "{{json .}}"): (
                0, json.dumps({"Name": "bridge", "Labels": ""}), "",
            ),
            ("ddev", "--version"): (0, "ddev v1.25.4", ""),
            ("ddev", "list", "-j"): (
                0, json.dumps({"level": "info", "raw": [
                    {"name": "existing-private-project", "status": "running"},
                ]}), "",
            ),
            ("codex", "--version"): (0, "codex-cli 0.162.1", ""),
            ("codex", "mcp", "--help"): (0, "Manage MCP servers", ""),
        }

    def __call__(self, argv):
        target = tuple(argv)
        self.calls.append(target)
        if target not in self.responses:
            raise AssertionError("An unapproved host-side command was requested")
        code, out, err = self.responses[target]
        return subprocess.CompletedProcess(argv, code, out, err)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(g1.os, "geteuid", lambda: 1000)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    home = tmp_path / "owner"
    home.mkdir()
    return home, Runner()


def check(state):
    home, runner = state
    return g1.read_only_readiness(
        SOURCE_SHA,
        source_root=Path("/pcp"),
        home=home,
        runner=runner,
    )


def test_exact_clean_source_local_docker_mcp_and_no_collision_pass(state):
    home, runner = state
    report = check(state)
    assert report["status"] == "PASS_HOST_PREFLIGHT_NO_ACTIVATION"
    assert report["fixture_source_commit"] == g1.FIXTURE_SHA
    assert report["other_registered_ddev_project_count"] == 1
    assert report["ready_to_dispatch_new_job"] is False
    assert report["model_calls"] == 0
    assert report["docker_ddev_git_mutations"] == 0
    assert report["disposable_docker_resources_absent_including_stopped"] is True
    assert report["fixture_inventory"]["fixture_container_count"] == 0
    assert report["fixture_inventory"]["fixture_volume_count"] == 0
    assert report["disposable_writer_or_runtime_lease"] == "NOT_PROVEN_NO_JOB_DISPATCH"
    assert report["actual_ddev_web_socket_and_egress"] == "NOT_YET_PROVEN"
    assert all(
        tuple(argv) in runner.responses
        for argv in runner.calls
    )
    assert not any(
        "start" in argv or "clone" in argv or "pull" in argv
        for argv in runner.calls
    )


@pytest.mark.parametrize("command,reply,code", [
    (("git", "-C", "/pcp", "rev-parse", "HEAD"),
     (0, "b" * 40, ""), "pcp_source_head_stale"),
    (("git", "-C", "/pcp", "status", "--porcelain"),
     (0, " M security.txt", ""), "pcp_source_dirty"),
    (("docker", "context", "inspect"),
     (0, '[{"Endpoints":{"docker":{"Host":"tcp://remote:2375"}}}]', ""),
     "docker_context_not_local_unix"),
    (("docker", "info", "--format", "{{json .}}"),
     (1, "", "DOCKER_HOST incorrect"), "docker_engine_unreachable"),
    (("docker", "container", "ls", "--all", "--format", "{{json .}}"),
     (0, json.dumps({"Names": DOCKER_WEB, "Labels": "", "State": "exited"}), ""),
     "disposable_containers_already_present"),
    (("docker", "container", "ls", "--all", "--format", "{{json .}}"),
     (1, "", "permission denied"), "docker_container_inventory_unavailable"),
    (("codex", "mcp", "--help"),
     (1, "", "unknown command"), "codex_mcp_subcommand_unavailable"),
])
def test_wrong_source_remote_docker_or_collision_fail_closed(state, command, reply, code):
    _, runner = state
    runner.responses[command] = reply
    with pytest.raises(g1.Stop, match=code):
        check(state)


def test_existing_ddev_registration_never_reused(state):
    _, runner = state
    runner.responses[("ddev", "list", "-j")] = (
        0, json.dumps({"level": "info", "raw": [
            {"name": "pcp-g1-codex-smoke", "status": "stopped"},
        ]}), "",
    )
    with pytest.raises(g1.Stop, match="ddev_fixture_name_collision"):
        check(state)


def test_ambiguous_ddev_response_fails_closed(state):
    _, runner = state
    runner.responses[("ddev", "list", "-j")] = (
        0, json.dumps({"level": "info", "raw": []}) + "\n"
           + json.dumps({"level": "info", "raw": []}), "",
    )
    with pytest.raises(g1.Stop, match="ddev_registry_ambiguous_or_invalid"):
        check(state)


def test_target_root_exists_or_symlink_refuses_any_docker_access(state):
    home, runner = state
    root = home / g1.SMOKE_ROOT_NAME
    root.mkdir()
    with pytest.raises(g1.Stop, match="disposable_target_already_present"):
        check(state)
    assert not any(argv[0] == "docker" for argv in runner.calls)


def test_global_ddev_host_hooks_are_not_silently_trusted(state):
    home, _ = state
    folder = home / ".ddev"
    folder.mkdir()
    (folder / "global_config.yaml").write_text(
        "hooks:\n  pre-exec:\n    - exec-host: whoami\n",
        encoding="utf-8",
    )
    with pytest.raises(g1.Stop, match="global_ddev_hooks_unreviewed"):
        check(state)


def test_operator_must_not_be_root(state, monkeypatch):
    monkeypatch.setattr(g1.os, "geteuid", lambda: 0)
    with pytest.raises(g1.Stop, match="operator_must_be_unprivileged"):
        check(state)


def test_remote_docker_host_override_denied(state, monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://someone-else:2375")
    with pytest.raises(g1.Stop, match="remote_docker_host_override"):
        check(state)


def test_ddev_registered_foreign_project_not_exposed(state):
    report = check(state)
    assert "existing-private-project" not in json.dumps(report)


def test_renamed_labeled_fixture_container_detected_even_if_stopped(state):
    _, runner = state
    key = ("docker", "container", "ls", "--all", "--format", "{{json .}}")
    runner.responses[key] = (0, json.dumps({
        "Names": "unexpected-web-container",
        "State": "exited",
        "Labels": "com.ddev.site-name=pcp-g1-codex-smoke",
    }), "")
    with pytest.raises(g1.Stop, match="disposable_containers_already_present") as exc:
        check(state)
    assert exc.value.facts["fixture_container_states"] == ["exited"]
    assert exc.value.facts["fixture_container_count"] == 1


@pytest.mark.parametrize("kind,entry,reason", [
    ("volume", {"Name": "ddev-pcp-g1-codex-smoke-mariadb", "Labels": ""},
     "disposable_fixture_volume_or_network_already_present"),
    ("network", {"Name": "unrelated-network", "Labels": "com.ddev.site-name=pcp-g1-codex-smoke"},
     "disposable_fixture_volume_or_network_already_present"),
])
def test_targeted_volumes_and_networks_are_not_silently_reused(state, kind, entry, reason):
    _, runner = state
    key = ("docker", kind, "ls", "--format", "{{json .}}")
    baseline = runner.responses[key][1]
    runner.responses[key] = (0, baseline + ("\n" if baseline else "") + json.dumps(entry), "")
    with pytest.raises(g1.Stop, match=reason) as exc:
        check(state)
    assert exc.value.facts["fixture_" + kind + "_count"] == 1


def test_malformed_container_list_fails_without_inferring_absence(state):
    _, runner = state
    runner.responses[("docker", "container", "ls", "--all", "--format", "{{json .}}")] = (
        0, "this is not JSON", "",
    )
    with pytest.raises(g1.Stop, match="docker_container_inventory_invalid"):
        check(state)
