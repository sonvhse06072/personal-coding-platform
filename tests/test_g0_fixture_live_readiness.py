"""Synthetic-only proof for the read-only G0 Runtime/Executor live probe.

No real Docker, model calls, fixture mutation, credential access or network calls.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g0-fixture-live-readiness.py"
SPEC = importlib.util.spec_from_file_location("g0_live_readiness", SCRIPT)
op = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(op)
EXPECTED_SHA = "a" * 40


def _health(svc):
    if svc == "runtime":
        return {"status": "degraded", "service": "coding-runtime",
                "router": "ok", "executor": "ok"}
    return {"status": "degraded", "service": "ddev-executor",
            "ddev": "PARKED", "docker": "not_probed",
            "buildx": "not_probed", "active_jobs": 0,
            "github_delivery_configured": False}


def _http_output(svc, routes):
    expected = (
        [200, 503, 401] if svc == "runtime" else [200, 403, 403]
    )
    return {
        path: ({"status_code": code, "health": _health(svc)}
               if i == 0 else {"status_code": code})
        for i, (path, code) in enumerate(zip(routes, expected, strict=True))
    }


@pytest.mark.parametrize("svc", ["runtime", "executor"])
def test_exact_get_only_probes_check_health_scope_and_auth(monkeypatch, svc):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        assert argv[:4] == ["docker", "exec", "-e", "PYTHONDONTWRITEBYTECODE=1"]
        assert argv[4] == op.g0.NAMES[svc]
        assert argv[5:7] == ["python3", "-c"]
        assert "method=\"GET\"" in argv[7]
        assert "method=\"POST\"" not in argv[7]
        assert argv[8] == ("8787" if svc == "runtime" else "8790")
        routes = json.loads(argv[9])
        assert len(routes) == 3
        assert all(path.startswith("/") for path in routes)
        return json.dumps(_http_output(svc, routes))

    monkeypatch.setattr(op.g0, "run", fake_run)
    got = op._local_http(svc)
    assert got["health"] == "PASS"
    assert got["http_get_codes"]["/health"] == 200
    assert len(calls) == 1


@pytest.mark.parametrize("error", ["missing_job_guard", "wrong_health", "delivery_on"])
def test_live_get_failure_is_not_reported_as_ready(monkeypatch, error):
    def fake_run(argv, **kwargs):
        routes = json.loads(argv[-1])
        out = _http_output("executor", routes)
        if error == "missing_job_guard":
            out["/v1/project-state"]["status_code"] = 200
        elif error == "wrong_health":
            out["/health"]["health"]["active_jobs"] = 1
        else:
            out["/health"]["health"]["github_delivery_configured"] = True
        return json.dumps(out)

    monkeypatch.setattr(op.g0, "run", fake_run)
    with pytest.raises(op.g0.GateError, match="gate_failed|health_unexpected"):
        op._local_http("executor")


def test_other_container_cannot_be_probed(monkeypatch):
    monkeypatch.setattr(
        op.g0, "run",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("non-G0 service must not be contacted")
        ),
    )
    with pytest.raises(op.g0.GateError, match="service_outside_allowlist"):
        op._local_http("chonhac")


def test_only_exact_original_activated_journal_is_accepted(monkeypatch):
    state = {
        "state": "activated",
        "source_sha": op.ACTIVATION_SOURCE_SHA,
        "services": ["executor", "runtime"],
        "ready_to_dispatch_g0d_t01": False,
    }
    calls = []
    monkeypatch.setattr(op.activation, "_private", lambda *a: Path("/g0/only"))
    monkeypatch.setattr(
        op.activation.auth.upgrader, "_read_json_secure", lambda *a: state
    )
    monkeypatch.setattr(
        op.activation, "_verify_containers",
        lambda mode: calls.append(mode),
    )
    op._activated_state()
    assert calls == ["g0_fixture_run"]
    state["state"] = "claimed"
    with pytest.raises(op.g0.GateError, match="journal_not_exact"):
        op._activated_state()
    assert calls == ["g0_fixture_run"]


@pytest.fixture
def docker_snapshot(monkeypatch):
    repo = Path("/g0/pcp-source")
    fixture = Path.home() / "pcp-g0-fixtures/pcp-g0-drupal-fixture"
    workspaces = Path("/g0/owned-workspaces")
    monkeypatch.setattr(
        op.g0, "read_private_state",
        lambda *args: (op.activation.auth.DEPLOYED_SHA, "redacted", workspaces),
    )
    private_members = {
        str(i): {"Name": name}
        for i, name in enumerate(op.g0.NAMES.values())
    }
    provider_members = {"runtime-id": {
        "Name": op.g0.NAMES["runtime"],
    }}
    networks = {
        op.g0.NETWORK: {"Internal": True, "Containers": private_members},
        op.activation.auth.G0_AUTH_NETWORKS["pcp"]: {
            "Internal": False, "Containers": provider_members,
        },
    }
    def mount(target, source, writable=False):
        if source is None:
            return {"Destination": target, "Type": "tmpfs", "RW": True}
        return {"Destination": target, "Type": "bind",
                "Source": str(source), "RW": writable}
    runtime_mounts = [
        mount("/g0/config/projects.yml",
              repo / "config/g0-fixture-only/projects.yml"),
        mount("/g0/config/project-baselines.yml",
              repo / "config/g0-fixture-only/project-baselines.yml"),
        mount("/g0/config/models.yml", repo / "config/models.yml"),
        mount("/g0/workspaces", workspaces, True),
        mount("/home/coder/.codex-g0", "/g0/private-auth", True),
        mount("/tmp", None),
    ]
    executor_mounts = [
        mount("/g0/config/projects.yml",
              repo / "config/g0-fixture-only/projects.yml"),
        mount("/g0/sources/pcp-g0-fixtures/pcp-g0-drupal-fixture", fixture),
        mount("/g0/workspaces", workspaces, True),
    ]
    containers = {}
    for svc in ("db", "router", "runtime", "executor"):
        n = op.g0.NAMES[svc]
        containers[n] = {
            "Name": "/" + n,
            "Config": {"Labels": {
                "com.docker.compose.project": op.g0.PROJECT,
                "com.docker.compose.service": svc,
            }},
            "State": {"Running": True},
            "HostConfig": {
                "Privileged": False, "PortBindings": {},
                "ReadonlyRootfs": svc == "runtime",
            },
            "NetworkSettings": {"Networks": {
                op.g0.NETWORK: {},
                **({op.activation.auth.G0_AUTH_NETWORKS["pcp"]: {}}
                   if svc == "runtime" else {}),
            }},
            "Mounts": (
                runtime_mounts if svc == "runtime"
                else executor_mounts if svc == "executor" else []
            ),
        }
    monkeypatch.setattr(op.activation.auth, "_auth_dir", lambda arm: Path("/g0/private-auth"))
    monkeypatch.setattr(
        op.g0, "inspect", lambda kind, name:
        (networks if kind == "network" else containers)[name],
    )
    return {"repo": repo, "networks": networks, "containers": containers}


def test_docker_boundary_accepts_only_g0_mounts_and_networks(docker_snapshot):
    op._docker_boundary(docker_snapshot["repo"])


@pytest.mark.parametrize("fault", ["foreign_provider", "foreign_bind", "port",
                                     "socket", "wrong_auth_source"])
def test_docker_boundary_stops_on_cross_project_or_privilege_drift(
    docker_snapshot, fault
):
    d = docker_snapshot
    runtime = d["containers"][op.g0.NAMES["runtime"]]
    executor = d["containers"][op.g0.NAMES["executor"]]
    if fault == "foreign_provider":
        d["networks"][op.activation.auth.G0_AUTH_NETWORKS["pcp"]][
            "Containers"
        ]["foreign"] = {"Name": "other"}
    elif fault == "foreign_bind":
        executor["Mounts"].append({
            "Destination": "/other", "Type": "bind",
            "Source": "/home/sonvh/chonhac", "RW": True,
        })
    elif fault == "port":
        executor["HostConfig"]["PortBindings"] = {"8790/tcp": [{}]}
    elif fault == "socket":
        runtime["Mounts"].append({
            "Destination": "/var/run/docker.sock", "Type": "bind",
            "Source": "/var/run/docker.sock", "RW": True,
        })
    else:
        runtime["Mounts"][4]["Source"] = "/home/coder/.codex"
    with pytest.raises(op.g0.GateError):
        op._docker_boundary(d["repo"])


def test_inspect_requires_activation_and_no_g0_jobs_before_gets(
    monkeypatch
):
    stages = []
    monkeypatch.setattr(op.g0, "require_local_docker_context",
                        lambda: stages.append("local_docker"))
    monkeypatch.setattr(op.g0, "require_exact_repo",
                        lambda *a: stages.append("exact_repo"))
    monkeypatch.setattr(op.activation, "_validate_overlay",
                        lambda: stages.append("overlay"))
    monkeypatch.setattr(op, "_activated_state",
                        lambda: stages.append("activation"))
    monkeypatch.setattr(op, "_docker_boundary",
                        lambda *a: stages.append("boundary"))
    monkeypatch.setattr(
        op.activation.auth.upgrader, "_require_empty_g0_job_store",
        lambda: stages.append("empty_job_store"),
    )
    monkeypatch.setattr(op, "_local_http",
                        lambda svc: stages.append(svc) or {
                            "health": "PASS", "http_get_codes": {},
                        })
    report = op.inspect(ROOT, ROOT, EXPECTED_SHA)
    assert stages == [
        "local_docker", "exact_repo", "exact_repo", "overlay",
        "activation", "boundary", "empty_job_store", "runtime", "executor",
    ]
    assert report["status"] == "PASS"
    assert report["github_delivery_enabled"] is False
    assert report["ready_to_dispatch_g0d_t01"] is False
    assert report["model_calls"] == 0


def test_never_probe_http_when_job_store_nonempty(monkeypatch):
    monkeypatch.setattr(op.g0, "require_local_docker_context", lambda: None)
    monkeypatch.setattr(op.g0, "require_exact_repo", lambda *a: None)
    monkeypatch.setattr(op.activation, "_validate_overlay", lambda: None)
    monkeypatch.setattr(op, "_activated_state", lambda: None)
    monkeypatch.setattr(op, "_docker_boundary", lambda *a: None)
    def fail_empty():
        raise op.g0.GateError("g0_job_already_started")
    monkeypatch.setattr(
        op.activation.auth.upgrader,
        "_require_empty_g0_job_store", fail_empty,
    )
    monkeypatch.setattr(
        op, "_local_http",
        lambda *a: (_ for _ in ()).throw(
            AssertionError("no HTTP queries when job store is unexpected")
        ),
    )
    with pytest.raises(op.g0.GateError, match="job_already_started"):
        op.inspect(ROOT, ROOT, EXPECTED_SHA)


def test_real_cli_help_does_not_contact_docker_or_model():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT, capture_output=True, text=True, timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--expected-sha" in result.stdout
    assert "inspect" in result.stdout


def test_live_source_exposes_only_bounded_read_only_operations():
    code = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "docker compose up", "docker stop", "docker rm",
        "docker restart", "ddev start", "git push", "gh pr create",
        "model_parity_probe.probe(", "_direct_one_call(",
        "PCP_G0_DELIVERY_ENABLED=owner-approved",
    ):
        assert forbidden not in code
    assert 'method="GET"' in code
    assert 'TARGETS = ("runtime", "executor")' in code
    assert "G0_FIXTURE" not in code or "_require_empty_g0_job_store" in code
