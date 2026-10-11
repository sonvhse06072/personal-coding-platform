"""Offline negative tests for upgrading ONLY the two G0 inspection images.

No test invokes Docker, DDEV, Git, Codex inference, GitHub or a WSL service.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts/g0-inspection-source-upgrade.py"
SPEC = importlib.util.spec_from_file_location("g0_inspection_source_upgrade", SRC)
upgrade = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upgrade)

OLD = upgrade.OLD_SOURCE
NEW = "b" * 40


@pytest.fixture
def private(monkeypatch, tmp_path):
    directory = tmp_path / ".pcp-g0d01"
    directory.mkdir(mode=0o700)
    monkeypatch.setattr(upgrade, "_private_root", lambda: directory)
    monkeypatch.setattr(upgrade, "_owner_state",
                        lambda: (OLD, "a" * 48, directory / "workspaces"))
    return directory


def fake_resources(*, source=OLD, project="pcp-g0d01", mode="inspect",
                   docker_socket=False, extra_env=None):
    mapping = {}
    for svc in upgrade.g0.G0_SERVICES:
        config = {
            "Labels": {"com.docker.compose.project": project,
                       "com.docker.compose.service": svc},
            "Env": [],
        }
        if svc == "runtime":
            config["Env"].append("PCP_RUNTIME_STARTUP_MODE=" + mode)
        elif svc == "executor":
            config["Env"].append(
                "PCP_EXECUTOR_PROJECT_SCOPE=pcp-g0-drupal-fixture"
            )
        config["Env"].extend(extra_env or [])
        mapping[upgrade.g0.NAMES[svc]] = {
            "Config": config,
            "State": {"Running": True},
            "NetworkSettings": {
                "Networks": {upgrade.g0.NETWORK: {}},
            },
            "HostConfig": {"Privileged": False, "PortBindings": {}},
            "Mounts": [
                {
                    "Destination": dst, "Type": typ, "RW": not readonly,
                    **({"Name": upgrade.g0.DATA_VOLUME}
                       if typ == "volume" else {}),
                }
                for dst, (typ, readonly) in upgrade.EXPECTED_MOUNTS[svc].items()
            ] + ([{"Destination": "/var/run/docker.sock"}]
                  if docker_socket else []),
            "Image": "sha256:" + ("1" if svc == "runtime" else "2") * 64,
        }

    def inspector(kind, name):
        if kind == "container":
            return mapping[name]
        if kind == "network":
            return {"Internal": True}
        if kind == "volume":
            return {"Labels": {"com.docker.compose.project": project}}
        if kind == "image":
            svc = next(s for s in ("executor", "runtime") if
                       upgrade.g0.resource_names(source)[s] == name)
            return {
                "Id": "sha256:" + ("1" if svc == "runtime" else "2") * 64,
                "Config": {"Labels": {
                    "org.opencontainers.image.revision": source,
                    "org.opencontainers.image.pcp.g0": "inspection-only",
                }},
            }
        raise AssertionError((kind, name))

    return inspector


def test_exact_resources_verify_without_running_any_engine(monkeypatch):
    monkeypatch.setattr(upgrade.g0, "inspect", fake_resources())
    upgrade._verify_g0_resources(OLD)


@pytest.mark.parametrize("changes,reason", [
    ({"project": "legacy-pcp"}, "ownership_or_state_changed"),
    ({"mode": "normal"}, "runtime_mode_not_inspect"),
    ({"docker_socket": True}, "host_docker_socket_exposed"),
    ({"extra_env": ["PCP_G0_EXECUTION_ENABLED=owner-approved"]},
     "live_credentials_or_capability_unexpected"),
    ({"extra_env": ["GITHUB_DELIVERY_TOKEN=secret"]},
     "live_credentials_or_capability_unexpected"),
])
def test_foreign_or_activated_g0_state_is_rejected(monkeypatch, changes, reason):
    monkeypatch.setattr(upgrade.g0, "inspect", fake_resources(**changes))
    with pytest.raises(upgrade.g0.GateError, match=reason):
        upgrade._verify_g0_resources(OLD)


def test_unknown_g0_mount_or_secret_fails_closed(monkeypatch):
    raw = fake_resources()
    def extra_mount(kind, name):
        data = raw(kind, name)
        if kind == "container" and name == upgrade.g0.NAMES["executor"]:
            data["Mounts"].append({
                "Type": "bind", "Destination": "/home/coder/.codex",
                "RW": False,
            })
        return data
    monkeypatch.setattr(upgrade.g0, "inspect", extra_mount)
    with pytest.raises(upgrade.g0.GateError, match="g0_mount_scope_changed"):
        upgrade._verify_g0_resources(OLD)


def test_readonly_g0_db_check_never_writes_or_touches_legacy(monkeypatch):
    queries = []
    def fake_run(argv, **kwargs):
        assert argv[:3] == ["docker", "exec", "pcp-g0d01-postgres"]
        sql = argv[-1]
        queries.append(sql)
        if sql.startswith("SELECT to_regclass"):
            return "" if "cp_jobs" in sql else "cp_project_leases"
        assert sql.startswith("SET default_transaction_read_only=on; SELECT COUNT(*)")
        return "0"
    monkeypatch.setattr(upgrade.g0, "run", fake_run)
    upgrade._require_empty_g0_job_store()
    assert all("UPDATE" not in q and "DELETE" not in q
               for q in queries)
    assert len(queries) == 9
    assert not any("chonhac" in q for q in queries)


def test_g0_db_existing_work_stops_source_upgrade(monkeypatch):
    def fake_run(argv, **kwargs):
        if argv[-1].startswith("SELECT to_regclass"):
            return "cp_jobs"
        return "2"
    monkeypatch.setattr(upgrade.g0, "run", fake_run)
    with pytest.raises(upgrade.g0.GateError, match="durable_work_not_empty"):
        upgrade._require_empty_g0_job_store()


def test_preflight_never_builds_or_recreates_containers(monkeypatch, private, tmp_path):
    monkeypatch.setattr(upgrade, "_base_source_validation", lambda *a: None)
    monkeypatch.setattr(upgrade, "_verify_g0_resources", lambda *a: None)
    monkeypatch.setattr(upgrade, "_require_empty_g0_job_store", lambda: None)
    monkeypatch.setattr(upgrade, "_codex_cli_version", lambda: "0.160.0")
    monkeypatch.setattr(upgrade.g0, "exists", lambda k, n: k == "image" and n == "postgres:17")
    monkeypatch.setattr(upgrade.g0, "inspect", lambda k, n: {
        "Id": "sha256:" + "a" * 64
    })
    monkeypatch.setattr(upgrade.g0, "run",
                        lambda *a, **k: pytest.fail("preflight launched a process"))
    outcome = upgrade.preflight(tmp_path, tmp_path, NEW)
    assert outcome["status"] == "PASS"
    assert outcome["ready_to_dispatch_g0d_t01"] is False
    assert outcome["source_upgrade_available"] is True
    assert outcome["installed_g0_codex_cli_version"] == "0.160.0"


def test_preflight_stops_on_existing_journal_without_retry(monkeypatch, private, tmp_path):
    upgrade._private_write(private / upgrade.JOURNAL,
                           {"state": "started", "old_sha": OLD, "target_sha": NEW})
    monkeypatch.setattr(upgrade, "_base_source_validation", lambda *a: None)
    with pytest.raises(upgrade.g0.GateError, match="journal_already_exists"):
        upgrade.preflight(tmp_path, tmp_path, NEW)


def test_compose_recreate_target_is_only_runtime_or_executor(monkeypatch, tmp_path):
    recorded = []
    monkeypatch.setattr(upgrade.g0, "compose_args",
                        lambda repo: ["docker", "compose", "-p", "pcp-g0d01"])
    monkeypatch.setattr(upgrade.g0, "run",
                        lambda argv, **kwargs: recorded.append(argv) or "")
    for name in upgrade.TARGET_SERVICES:
        upgrade._up_one(tmp_path, {}, name)
    assert len(recorded) == 2
    for command in recorded:
        assert "--no-deps" in command
        assert "--force-recreate" in command
        assert command[-1] in {"runtime", "executor"}
        assert not any(z in command for z in ("db", "router", "down",
                                            "--remove-orphans", "--volumes"))
    with pytest.raises(upgrade.g0.GateError, match="not_in_scope"):
        upgrade._up_one(tmp_path, {}, "db")


def test_upgrade_keeps_real_credentials_unmounted_and_preserves_db(
    monkeypatch, private, tmp_path
):
    call_order = []
    monkeypatch.setattr(upgrade, "preflight",
                        lambda *a: {"status": "PASS"})
    monkeypatch.setattr(upgrade, "_build_target_images",
                        lambda *a: call_order.append("build"))
    monkeypatch.setattr(upgrade, "_base_source_validation", lambda *a:
                        call_order.append("validate"))
    monkeypatch.setattr(upgrade, "_verify_g0_resources",
                        lambda sha: call_order.append("inspect_" + sha[:6]))
    monkeypatch.setattr(upgrade, "_require_empty_g0_job_store",
                        lambda: call_order.append("readonly_db"))
    monkeypatch.setattr(upgrade, "_compose_environment",
                        lambda *a: {"RUNTIME": "inspect"})
    monkeypatch.setattr(upgrade, "_up_one",
                        lambda repo, env, svc: call_order.append("up_" + svc))
    monkeypatch.setattr(upgrade.g0, "compose_args", lambda r: ["docker", "compose"])
    monkeypatch.setattr(upgrade.g0, "run",
                        lambda *a, **k: call_order.append("compose_config"))
    monkeypatch.setattr(upgrade.g0, "verify_inspection",
                        lambda *a: call_order.append("health"))
    monkeypatch.setattr(upgrade, "_codex_cli_version", lambda: "0.160.0")
    result = upgrade.upgrade(tmp_path, tmp_path, NEW)
    assert result["phase"] == "inspection_source_upgrade"
    assert result["ready_to_dispatch_g0d_t01"] is False
    assert result["credentials_added"] is False
    assert result["external_egress_added"] is False
    assert result["database_recreated"] is False
    assert "up_executor" in call_order
    assert "up_runtime" in call_order
    assert "inspect_" + NEW[:6] in call_order
    record = json.loads((private / "owner-state.json").read_text())
    assert record["source_sha"] == NEW
    assert record["password"] == "a" * 48
    assert json.loads((private / upgrade.JOURNAL).read_text())["state"] == "complete"
    assert (private / upgrade.JOURNAL).stat().st_mode & 0o077 == 0
    assert "model" not in " ".join(call_order)


def test_rollback_can_recover_partial_upgrade_with_only_original_images(
    monkeypatch, private, tmp_path
):
    upgrade._private_write(private / upgrade.JOURNAL, {
        "old_sha": OLD, "target_sha": NEW, "state": "started",
    })
    monkeypatch.setattr(upgrade.g0, "require_local_docker_context",
                        lambda: None)
    monkeypatch.setattr(upgrade.g0, "exists",
                        lambda kind, name: (
                            kind == "container" and name in {
                                upgrade.g0.NAMES["executor"],
                                upgrade.g0.NAMES["runtime"],
                            }
                        ) or (kind == "image" and ":" + OLD[:12] in name))
    monkeypatch.setattr(upgrade, "_require_empty_g0_job_store", lambda: None)
    def fake_inspect(kind, name):
        if kind == "network":
            return {"Internal": True}
        if kind == "volume":
            return {"Labels": {"com.docker.compose.project": upgrade.g0.PROJECT}}
        if kind == "container":
            svc = next(s for s in upgrade.TARGET_SERVICES
                       if upgrade.g0.NAMES[s] == name)
            return {
                "Config": {"Labels": {
                    "com.docker.compose.project": upgrade.g0.PROJECT,
                    "com.docker.compose.service": svc,
                }},
                "State": {"Running": True, "Status": "running"},
                "Image": "sha256:" + "a" * 64,
            }
        return {"Id": "sha256:" + "a" * 64}
    monkeypatch.setattr(upgrade.g0, "inspect", fake_inspect)
    monkeypatch.setattr(upgrade, "_compose_environment",
                        lambda *a: {})
    targets = []
    monkeypatch.setattr(upgrade, "_up_one",
                        lambda repo, env, svc: targets.append(svc))
    monkeypatch.setattr(upgrade, "_verify_g0_resources", lambda *a: None)
    monkeypatch.setattr(upgrade.g0, "verify_inspection", lambda *a: None)
    result = upgrade.rollback(tmp_path, tmp_path)
    assert targets == ["executor", "runtime"]
    assert result["source_sha"] == OLD
    assert result["ready_to_dispatch_g0d_t01"] is False
    assert json.loads((private / upgrade.JOURNAL).read_text())["state"] == "rolled_back"


def test_no_generic_host_or_legacy_commands_in_operator():
    source = SRC.read_text(encoding="utf-8")
    for forbidden in (
        "ddev start", "ddev poweroff", "docker system prune",
        "docker compose down", "rm -rf", "git reset --hard",
        "--remove-orphans", "codex exec", "GITHUB_DELIVERY_TOKEN=",
        "OPENAI_API_KEY=", "PCP_G0_EXECUTION_ENABLED=owner-approved",
    ):
        assert forbidden not in source
    assert 'ready_to_dispatch_g0d_t01": False' in source
