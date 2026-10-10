"""G0 shared WSL preflight is observational, never a license to execute.

All tests feed synthetic DDEV JSON; they do not run DDEV, Docker, GitHub,
Codex inference or inspect any actual project worktree.
"""
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/g0-wsl-coexistence-preflight.py"
spec = importlib.util.spec_from_file_location("g0_shared_host_readonly", SOURCE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def project(name, status):
    return {"name": name, "status": status, "location": "/private/never-print-me"}


def registry(*projects):
    return json.dumps({"level": "info", "raw": list(projects)})


def good_git(sha):
    return {"exists": True, "git_readable": True, "head_sha": sha, "clean": True}


def assess(data, *, fixture_sha=None, host_cli="codex-cli 0.160.0"):
    return probe.evaluate(
        ddev_json=data,
        local_pcp=good_git("a" * 40),
        local_fixture=good_git(fixture_sha or probe.FIXTURE_SEED),
        host_cli=host_cli,
        ddev_version="ddev version v1.25.4",
    )


def test_unrelated_active_ddev_is_not_a_name_collision_or_auto_permission():
    observed = assess(registry(
        project("another-owners-project", "running"),
        project("a-second-project", "paused"),
        project("Router", "healthy"),
    ))
    assert observed["ddev_registry"]["other_active_project_count"] == 2
    assert observed["ddev_registry"]["fixture_project_name_collision"] is False
    assert observed["ddev_registry"]["unrelated_active_projects_are_not_automatic_collision"]
    assert observed["ddev_registry"]["shared_router_indirect_impact_not_ruled_out"]
    assert observed["ready_to_dispatch_g0d_t01"] is False
    assert observed["deployment_or_ddev_execution_performed"] is False
    encoded = json.dumps(observed)
    assert "another-owners-project" not in encoded
    assert "a-second-project" not in encoded
    assert "/private/" not in encoded


def test_actual_fixture_name_collision_is_identified_without_other_project_names():
    observed = assess(registry(
        project("PCP-G0-DRUPAL-FIXTURE", "stopped"),
        project("another", "running"),
    ))
    assert observed["ddev_registry"]["fixture_project_name_collision"]
    assert "fixture_ddev_name_occupied_check_ownership" in observed["blockers"]
    assert "another" not in json.dumps(observed)
    assert observed["ready_to_dispatch_g0d_t01"] is False


def test_ndjson_informational_envelope_and_legacy_shape():
    multi = (
        json.dumps({"level": "info", "msg": "progress"}) + "\n"
        + registry(project("source", "stopped"))
    )
    assert len(probe.parse_ddev_json(multi)) == 1
    assert len(probe.parse_ddev_json('{"raw":{"projects":[]}}')) == 0


@pytest.mark.parametrize("payload", [
    "", "not-json", "{}", '{"level":"error","raw":[]}', '{"raw":null}',
    '{"raw":[],"extra":"ok"}\n{"raw":[]}', '{"raw":[{"name":"x"}]}',
    '{"raw":[{"name":"a","status":"running"},{"name":"A","status":"stopped"}]}',
    '{"raw":"invalid"}', '{"raw":[3]}',
])
def test_malformed_or_ambiguous_registry_fails_closed(payload):
    with pytest.raises(ValueError):
        probe.parse_ddev_json(payload)


def test_mismatched_source_and_cli_require_further_checks_not_global_downgrade():
    report = assess(
        registry(project("some-other", "running")),
        fixture_sha="f" * 40, host_cli="codex-cli 0.162.0",
    )
    assert "fixture_local_head_not_frozen_seed" in report["blockers"]
    assert "host_cli_differs_from_runtime_source_pin" in report["blockers"]
    assert report["runtime_source_pin"] == "0.160.0"
    assert report["host_codex_cli_version"] == "0.162.0"
    assert report["model_and_effort_unverified"]
    assert report["actual_runtime_binary_unverified"]
    assert report["ready_to_dispatch_g0d_t01"] is False


def test_only_whitelisted_read_commands_may_run(monkeypatch):
    observed = []
    class Fake:
        returncode = 0
        stdout = "ok"
        stderr = ""
    def fake_run(argv, **kwargs):
        observed.append(tuple(argv))
        assert kwargs["capture_output"] is True
        assert kwargs["timeout"] <= 20
        return Fake()
    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    for cmd in (
        ["ddev", "list", "-j"],
        ["ddev", "--version"],
        ["codex", "--version"],
        ["git", "-C", "/synthetic/pcp", "rev-parse", "HEAD"],
        ["git", "-C", "/synthetic/fixture", "status", "--porcelain=v1"],
    ):
        result, failure = probe.read_command(cmd)
        assert failure is None and result == "ok"
    assert len(observed) == 5
    for cmd in (
        ["ddev", "start", "-y"], ["ddev", "stop", "--all"],
        ["ddev", "poweroff"], ["docker", "system", "prune"],
        ["git", "-C", "/synthetic/fixture", "fetch"],
        ["codex", "exec", "modify source"],
    ):
        with pytest.raises(ValueError, match="unsupported_read_only_command"):
            probe.read_command(cmd)
    assert len(observed) == 5


def test_absent_source_paths_do_not_trigger_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.Path, "home", lambda: tmp_path)
    calls = []
    def fake_read(argv, *, cwd=None):
        calls.append(tuple(argv))
        if argv == ["ddev", "list", "-j"]:
            return registry(project("other", "running")), None
        if argv == ["ddev", "--version"]:
            return "ddev v1.25.4", None
        if argv == ["codex", "--version"]:
            return "codex-cli 0.162.0", None
        raise AssertionError("No Git call expected when source paths do not exist")
    monkeypatch.setattr(probe, "read_command", fake_read)
    assert probe.main() == 0
    assert len(calls) == 3
    assert list(tmp_path.iterdir()) == []


def test_no_source_hardcoded_global_mutations():
    src = SOURCE.read_text(encoding="utf-8")
    for forbidden in (
        "ddev start", "ddev stop", "ddev poweroff", "docker restart",
        "docker system prune", "git fetch", "git reset", "gh repo",
        "rm -rf", "shutil.rmtree", "os.system(", "subprocess.Popen(",
    ):
        # These can only occur as nonexecuting *string-deny fixtures* in test
        # descriptions; never in the operational script itself.
        assert forbidden not in src
    assert '"ready_to_dispatch_g0d_t01": False' in src
    assert '"deployment_or_ddev_execution_performed": False' in src
