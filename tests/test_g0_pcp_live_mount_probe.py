"""Pure synthetic tests of the PCP-only, read-only WSL container probe.

No real Docker, DDEV, Codex, secrets, other projects or files are queried.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g0-pcp-live-mount-probe.py"
spec = importlib.util.spec_from_file_location("g0_pcp_live_mount_probe", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixture(tmp_path, monkeypatch):
    home = tmp_path / "userhome"
    path = home / "pcp-g0-fixtures" / mod.FIXTURE
    path.mkdir(parents=True)
    (path / "composer.lock").write_text("fake", encoding="utf-8")
    monkeypatch.setattr(mod.Path, "home", lambda: home)
    monkeypatch.setattr(
        mod, "local_fixture_proof",
        lambda candidate: {"fixture_lock_sha256_matches_frozen_seed": candidate == path},
    )
    monkeypatch.setattr(
        mod, "resource_snapshot",
        lambda candidate: {"fixture_disk_free_gib": 21.0, "capacity_and_port_safety_not_proven": True},
    )
    return path


def mount(root):
    return [{"Type": "bind", "Destination": root, "Source": "/docker-desktop/mounts/example"}]


def test_project_root_visibility_matches_exact_local_fixture_not_default_projects():
    target = Path("/home/fixture/pcp-g0-fixtures/pcp-g0-drupal-fixture")
    good = mod.assess_mounts(mount("/home/fixture"), "/home/fixture", target)
    assert good["fixture_path_matches_registered_project_root"]
    assert good["executor_has_projects_root_bind"]
    assert good["eligible_for_read_only_fixture_visibility_check"]

    wrong = mod.assess_mounts(mount("/home/fixture/projects"), "/home/fixture/projects", target)
    assert not wrong["fixture_path_matches_registered_project_root"]
    assert wrong["executor_has_projects_root_bind"]
    assert not wrong["eligible_for_read_only_fixture_visibility_check"]


@pytest.mark.parametrize("root", [
    "", "/", "/tmp", "/var/run", "/var/run/docker.sock",
    "relative", "/home/user/../root", "/home/user/./projects", "/home/user\nsecret",
])
def test_suspicious_project_root_is_rejected(root):
    with pytest.raises(mod.SafeStop, match="projects_root_invalid"):
        mod.registered_path(root)


def test_docker_command_allowlist_only_our_two_pcp_services(monkeypatch):
    invoked = []
    def fake_run(argv, **options):
        invoked.append(argv)
        assert options["capture_output"] and options["timeout"] <= 25
        return SimpleNamespace(returncode=0, stdout="true", stderr="")
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    allowed_fixture = str(Path.home() / "pcp-g0-fixtures" / mod.FIXTURE)
    commands = [
        ["docker", "inspect", "--format", "{{json .Mounts}}", mod.EXECUTOR],
        ["docker", "inspect", "--format", "{{json .Config.Labels}}", mod.RUNTIME],
        ["docker", "exec", mod.EXECUTOR, "printenv", "CODING_PROJECTS_ROOT"],
        ["docker", "exec", mod.RUNTIME, "codex", "--version"],
        ["docker", "exec", mod.EXECUTOR, "test", "-d", allowed_fixture],
        ["docker", "exec", mod.EXECUTOR, "test", "-f", allowed_fixture + "/composer.lock"],
    ]
    for cmd in commands:
        assert mod.call(cmd) == "true"
    assert len(invoked) == len(commands)
    rejected = [
        ["docker", "ps"],
        ["docker", "exec", "ddev-chonhac-web", "bash"],
        ["docker", "inspect", "--format", "{{json .Config.Env}}", mod.EXECUTOR],
        ["docker", "inspect", "--format", "{{json .Mounts}}", "ddev-chonhac-db"],
        ["docker", "stop", mod.EXECUTOR],
        ["docker", "exec", mod.RUNTIME, "codex", "exec"],
        ["docker", "exec", mod.EXECUTOR, "printenv"],
        ["docker", "exec", mod.EXECUTOR, "test", "-f", "/home/sonvh/chonhac/settings.php"],
        ["docker", "exec", mod.EXECUTOR, "test", "-d", "/home/sonvh/chonhac"],
        ["docker", "exec", mod.EXECUTOR, "test", "-d", "/fixture"],
        ["ddev", "start"],
        ["git", "fetch"],
    ]
    for cmd in rejected:
        with pytest.raises(mod.SafeStop, match="unapproved_read_only_command"):
            mod.call(cmd)
    assert len(invoked) == len(commands)


def test_inspect_requires_exact_container_name_and_real_pcp_ownership(monkeypatch):
    answers = {
        "name": "/" + mod.EXECUTOR,
        "labels": {"com.docker.compose.project": "ddev-personal-coding-platform"},
        "running": True,
        "mounts": mount("/home/fixture"),
    }
    monkeypatch.setattr(mod, "call", lambda args: json.dumps(
        answers[next(k for k, v in mod.FORMATS.items() if args[3] == v)]
    ))
    assert mod.inspect_pcp_service(mod.EXECUTOR)["name"] == mod.EXECUTOR
    with pytest.raises(mod.SafeStop, match="non_pcp_container_rejected"):
        mod.inspect_pcp_service("ddev-chonhac-web")
    answers["labels"] = {"com.docker.compose.project": "ddev-chonhac"}
    with pytest.raises(mod.SafeStop, match="ownership_labels"):
        mod.inspect_pcp_service(mod.EXECUTOR)
    answers["labels"] = {"com.docker.compose.project": "ddev-personal-coding-platform"}
    answers["running"] = False
    with pytest.raises(mod.SafeStop, match="running_state"):
        mod.inspect_pcp_service(mod.EXECUTOR)


def test_runtime_and_mount_proof_when_paths_match(tmp_path, monkeypatch):
    local = fixture(tmp_path, monkeypatch)
    root = str(local.parents[1])
    calls = []
    def fake_call(args):
        calls.append(tuple(args))
        if args[2] == mod.EXECUTOR and args[-2:] == ["printenv", "CODING_PROJECTS_ROOT"]:
            return root
        if args[2] == mod.RUNTIME and args[-2:] == ["codex", "--version"]:
            return "codex-cli 0.160.0"
        if args[2] == mod.EXECUTOR and args[3] == "test":
            return ""
        raise AssertionError("unexpected command " + repr(args))
    monkeypatch.setattr(mod, "inspect_pcp_service",
                        lambda name: {"name": name, "mounts": mount(root)})
    monkeypatch.setattr(mod, "call", fake_call)
    result = mod.examine()
    assert result["executor_fixture_visible"]
    assert result["pcp_runtime_codex_cli_version"] == "0.160.0"
    assert result["blockers"] == []
    assert result["ready_to_dispatch_g0d_t01"] is False
    assert result["pcp_runtime_deployed_source_unverified"] is True
    assert result["active_job_lease_unverified"] is True
    assert result["model_effort_and_provider_auth_unverified"] is True
    assert result["ddev_router_shared_side_effects_unverified"] is True
    assert len(calls) == 4
    assert all(c[2] in (mod.EXECUTOR, mod.RUNTIME) for c in calls)


def test_missing_mount_stops_before_any_executor_file_probe(tmp_path, monkeypatch):
    local = fixture(tmp_path, monkeypatch)
    root = str(local.parent.parent / "projects")
    seen = []
    monkeypatch.setattr(mod, "inspect_pcp_service", lambda name: {
        "name": name, "mounts": mount(root),
    })
    def fake_call(args):
        seen.append(args)
        if args[2] == mod.EXECUTOR:
            assert args[-2:] == ["printenv", "CODING_PROJECTS_ROOT"]
            return root
        if args[2] == mod.RUNTIME:
            return "codex-cli 0.162.0"
        raise AssertionError("No other command")
    monkeypatch.setattr(mod, "call", fake_call)
    result = mod.examine()
    assert "fixture_checkout_outside_configured_project_root" in result["blockers"]
    assert result["executor_fixture_visible"] is False
    assert "runtime_codex_cli_differs_from_source_pin" in result["blockers"]
    assert result["ready_to_dispatch_g0d_t01"] is False
    assert all(s[-3] != "test" for s in seen)
    assert "projects" not in json.dumps(result) or "projects_root" in json.dumps(result)
    assert str(local) not in json.dumps(result)


def test_no_global_changes_credentials_or_chonhac_access_in_source():
    text = SCRIPT.read_text(encoding="utf-8")
    for prohibited in (
        "ddev start", "ddev stop", "ddev restart", "docker stop",
        "docker restart", "docker system prune", "codex exec",
        "gh auth", "os.environ[", "Config.Env", "subprocess.Popen",
        "os.system(", "shutil.rmtree", "git checkout", "docker ps",
    ):
        # Code may mention Config.Env in comments; prohibit Docker
        # *template access*, which could reveal provider credentials.
        if prohibited == "Config.Env":
            assert "{{json .Config.Env}}" not in text
        else:
            assert prohibited not in text
    assert '"ready_to_dispatch_g0d_t01": False' in text
    assert '"unrelated_container_inspection_performed": False' in text
