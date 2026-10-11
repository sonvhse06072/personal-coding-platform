#!/usr/bin/env python3
"""Read-only G0 fixture activation live checks. Never dispatch or alter a job.

Verifies the exact preapproved G0 activation journal, Docker ownership and
mounts, empty G0-only job store, and a bounded set of GET-only loopback HTTP
responses from only G0 Runtime/Executor. No secrets, model calls, POST, DDEV,
GitHub delivery, service lifecycle operations or unrelated projects.

  inspect --expected-sha <current-clean-PCP-main-SHA>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVATION_SCRIPT = ROOT / "scripts/g0-fixture-execution-operator.py"
ACTIVATION_SOURCE_SHA = "2a84b3d9b85511a00581f863d52c3b93fb8505c8"
TARGETS = ("runtime", "executor")
DUMMY_JOB = "0" * 32

# Executed inside ONE named G0 container. GET requests only; output is bounded
# to allowlisted status/health fields, never original bodies or headers.
HTTP_INSPECT = r"""
import json
import sys
import urllib.error
import urllib.request

port = int(sys.argv[1])
paths = json.loads(sys.argv[2])
out = {}
for path in paths:
    if not path.startswith("/") or any(c in path for c in "\r\n#"):
        raise RuntimeError("g0_http_path_invalid")
    req = urllib.request.Request(
        "http://127.0.0.1:" + str(port) + path, method="GET"
    )
    content = b""
    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            code = response.status
            if path == "/health":
                content = response.read(8192)
    except urllib.error.HTTPError as exc:
        code = exc.code
    if path == "/health" and code == 200:
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise RuntimeError("g0_health_invalid")
        allowed = {
            "status", "service", "router", "executor", "ddev",
            "docker", "buildx", "active_jobs",
            "github_delivery_configured",
        }
        out[path] = {
            "status_code": code,
            "health": {k: payload.get(k) for k in allowed if k in payload},
        }
    else:
        out[path] = {"status_code": code}
print(json.dumps(out, sort_keys=True))
"""


def _load():
    spec = importlib.util.spec_from_file_location(
        "g0_fixture_activation_live", ACTIVATION_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("G0 activation operator unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


activation = _load()
g0 = activation.g0


def _activated_state() -> None:
    state = activation.auth.upgrader._read_json_secure(
        activation._private(activation.JOURNAL_FILE)
    )
    if state != {
        "state": "activated",
        "source_sha": ACTIVATION_SOURCE_SHA,
        "services": ["executor", "runtime"],
        "ready_to_dispatch_g0d_t01": False,
    }:
        raise g0.GateError("g0_activation_journal_not_exact")
    # Existing verifier inspects only the exact G0 Executor and Runtime.
    activation._verify_containers("g0_fixture_run")


def _docker_boundary(repo: Path) -> None:
    deployed, _password, workspace = g0.read_private_state(Path.home())
    if deployed != activation.auth.DEPLOYED_SHA:
        raise g0.GateError("g0_running_source_identity_drift")
    private = g0.inspect("network", g0.NETWORK)
    provider = g0.inspect(
        "network", activation.auth.G0_AUTH_NETWORKS["pcp"]
    )
    if private.get("Internal") is not True or provider.get("Internal") is not False:
        raise g0.GateError("g0_network_internal_identity_changed")

    def members(doc: dict) -> set[str]:
        return {
            val.get("Name") for val in (doc.get("Containers") or {}).values()
            if isinstance(val, dict)
        }

    if members(private) != set(g0.NAMES.values()) or members(provider) != {
        g0.NAMES["runtime"]
    }:
        raise g0.GateError("g0_network_membership_unexpected")

    expected = {
        "runtime": {
            "/g0/config/projects.yml": str(repo / "config/g0-fixture-only/projects.yml"),
            "/g0/config/project-baselines.yml":
                str(repo / "config/g0-fixture-only/project-baselines.yml"),
            "/g0/config/models.yml": str(repo / "config/models.yml"),
            "/g0/workspaces": str(workspace),
            "/home/coder/.codex-g0": str(activation.auth._auth_dir("pcp")),
            "/tmp": None,
        },
        "executor": {
            "/g0/config/projects.yml": str(repo / "config/g0-fixture-only/projects.yml"),
            "/g0/sources/pcp-g0-fixtures/pcp-g0-drupal-fixture":
                str(Path.home() / "pcp-g0-fixtures/pcp-g0-drupal-fixture"),
            "/g0/workspaces": str(workspace),
        },
    }
    for svc in TARGETS:
        item = g0.inspect("container", g0.NAMES[svc])
        host = item.get("HostConfig") or {}
        if (
            host.get("Privileged") is not False
            or host.get("PortBindings")
            or (svc == "runtime" and host.get("ReadonlyRootfs") is not True)
        ):
            raise g0.GateError("g0_http_probe_container_privilege_changed")
        mounts = item.get("Mounts") or []
        by_target = {
            m.get("Destination"): m for m in mounts if isinstance(m, dict)
        }
        if len(by_target) != len(mounts) or set(by_target) != set(expected[svc]):
            raise g0.GateError("g0_http_probe_mount_target_changed")
        for target, origin in expected[svc].items():
            item_mount = by_target[target]
            if origin is None:
                if item_mount.get("Type") != "tmpfs":
                    raise g0.GateError("g0_http_probe_tmpfs_changed")
            elif (item_mount.get("Type") != "bind"
                  or item_mount.get("Source") != origin
                  or item_mount.get("RW") is not (
                      target in {"/g0/workspaces", "/home/coder/.codex-g0"}
                  )):
                raise g0.GateError("g0_http_probe_mount_origin_changed")

    for svc in ("db", "router"):
        item = g0.inspect("container", g0.NAMES[svc])
        labels = (item.get("Config") or {}).get("Labels") or {}
        if (
            item.get("Name") != "/" + g0.NAMES[svc]
            or labels.get("com.docker.compose.project") != g0.PROJECT
            or labels.get("com.docker.compose.service") != svc
            or (item.get("State") or {}).get("Running") is not True
            or set((item.get("NetworkSettings") or {}).get("Networks") or {})
                != {g0.NETWORK}
            or (item.get("HostConfig") or {}).get("PortBindings")
        ):
            raise g0.GateError("g0_readiness_core_service_identity_changed")


def _local_http(svc: str) -> dict:
    if svc not in TARGETS:
        raise g0.GateError("g0_http_probe_service_outside_allowlist")
    port = 8787 if svc == "runtime" else 8790
    routes = (
        ["/health", "/v1/jobs", "/v1/g0-fixture/jobs/" + DUMMY_JOB]
        if svc == "runtime" else
        ["/health", "/v1/project-state", "/v1/github/ci"]
    )
    # Docker exec addresses ONLY the identified G0 container. No credentials,
    # network-visible ports or arbitrary command/prompt interpolation.
    raw = g0.run(
        ["docker", "exec", "-e", "PYTHONDONTWRITEBYTECODE=1",
         g0.NAMES[svc], "python3", "-c", HTTP_INSPECT,
         str(port), json.dumps(routes)],
        label="g0_" + svc + "_read_only_http", timeout=35,
    )
    try:
        result = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise g0.GateError("g0_http_probe_response_invalid") from exc
    if not isinstance(result, dict) or set(result) != set(routes):
        raise g0.GateError("g0_http_probe_response_incomplete")
    codes = {
        path: value.get("status_code") for path, value in result.items()
        if isinstance(value, dict)
    }
    expected_codes = (
        {routes[0]: 200, routes[1]: 503, routes[2]: 401}
        if svc == "runtime" else
        {routes[0]: 200, routes[1]: 403, routes[2]: 403}
    )
    if codes != expected_codes:
        raise g0.GateError("g0_http_scope_or_auth_gate_failed")
    health = result["/health"].get("health")
    if not isinstance(health, dict):
        raise g0.GateError("g0_health_response_missing")
    if svc == "runtime":
        if not (
            health.get("status") == "degraded"
            and health.get("service") == "coding-runtime"
            and health.get("router") == "ok"
            and health.get("executor") == "ok"
        ):
            raise g0.GateError("g0_runtime_http_health_unexpected")
    elif not (
        health.get("status") == "degraded"
        and health.get("service") == "ddev-executor"
        and health.get("ddev") == "PARKED"
        and health.get("docker") == "not_probed"
        and health.get("buildx") == "not_probed"
        and health.get("active_jobs") == 0
        and health.get("github_delivery_configured") is False
    ):
        raise g0.GateError("g0_executor_http_health_unexpected")
    return {"health": "PASS", "http_get_codes": codes}


def inspect(repo: Path, fixture: Path, sha: str) -> dict:
    if not g0.SOURCE_SHA.fullmatch(sha):
        raise g0.GateError("g0_readiness_exact_source_required")
    g0.require_local_docker_context()
    g0.require_exact_repo(repo, g0.EXPECTED_REPO, "main", sha)
    g0.require_exact_repo(
        fixture, g0.EXPECTED_FIXTURE, "benchmark/pcp", g0.SEED
    )
    activation._validate_overlay()
    _activated_state()
    _docker_boundary(repo)
    # This executes SELECT-only queries against the dedicated G0 PostgreSQL.
    activation.auth.upgrader._require_empty_g0_job_store()
    checks = {svc: _local_http(svc) for svc in TARGETS}
    return {
        "status": "PASS",
        "phase": "g0_fixture_execution_http_readiness",
        "source_sha": sha,
        "activation_source_sha": ACTIVATION_SOURCE_SHA,
        "project": g0.PROJECT,
        "checks": checks,
        "g0_job_store_empty": True,
        "github_delivery_enabled": False,
        "model_calls": 0,
        "http_methods": ["GET"],
        "ready_to_dispatch_g0d_t01": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect",))
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    try:
        value = inspect(
            Path.home() / "personal-coding-platform-v1",
            Path.home() / "pcp-g0-fixtures/pcp-g0-drupal-fixture",
            args.expected_sha,
        )
    except (g0.GateError, OSError, ValueError, TypeError, KeyError) as exc:
        value = {
            "status": "STOP",
            "phase": "g0_fixture_execution_http_readiness",
            "reason": str(exc) if isinstance(exc, g0.GateError)
                      else "g0_live_http_readiness_validation_error",
            "do_not_retry_blindly": True,
            "model_calls": 0,
            "ready_to_dispatch_g0d_t01": False,
        }
    print(json.dumps(value, sort_keys=True, indent=2))
    return 0 if value["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
