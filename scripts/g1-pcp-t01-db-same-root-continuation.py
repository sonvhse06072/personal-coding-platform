#!/usr/bin/env python3
"""Single source-corrected G1-T01 PCP continuation after pre-resource DB STOP.

ONLY for the ORIGINAL pilot root/journal left by g1_pcp_database_start_failed
with no G1 database container, volume, network, workspace or model call.
Preserves that journal byte-for-byte. Does NOT reuse/rerun the first operator,
Direct control, no-model smoke, F2 or Chợ Nhạc. Never resets Docker, DB or
agent budgets; STOP is terminal pending another explicit PM decision.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

PCP = Path(__file__).resolve().parents[1]
ONE_SHOT = PCP / "scripts/g1-pcp-t01-one-shot.py"
ROOT = Path.home() / ".pcp-g1-pilot/pcp-t01"
JOURNAL = ROOT / "job-evidence.json"
EVIDENCE = ROOT / "db-continuation-evidence.json"
CREDENTIALS = ROOT / "db-continuation-credentials.json"
SEED = "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
DB = "pcp-g1-pilot-db-1"
VOLUME = "pcp-g1-pilot-postgres"
NETWORK = "pcp-g1-pilot-control"
EXPECTED_STATE = "started"
CLASSIFIERS = {
    "DISK_FULL": r"no space left on device",
    "PERMISSION_DENIED": r"permission denied|operation not permitted",
    "INVALID_CONFIG": r"invalid compose|invalid .*config|validating .+failed|yaml:|parsing",
    "UNSUPPORTED_FLAG": r"unknown flag|unknown shorthand flag|unknown option",
    "IMAGE_PROBLEM": r"pull access denied|manifest unknown|image not found|no matching manifest",
    "NETWORK_ERROR": r"network.*(not found|conflict|failed|denied|error)",
    "VOLUME_ERROR": r"volume.*(not found|conflict|failed|denied|error)",
    "CONTAINER_CONFLICT": r"container name.*already in use|conflict.*container",
    "OCI_RUNTIME": r"oci runtime|runc create failed|failed to create task",
    "DAEMON_ERROR": r"error response from daemon|cannot connect to the docker daemon",
    "POSTGRES_FATAL": r"\bfatal:",
    "POSTGRES_READY": r"database system is ready to accept connections",
}


class Stop(RuntimeError):
    """Short stable public STOP code; never print subprocess output or secrets."""


def check(ok: bool, code: str) -> None:
    if not ok:
        raise Stop(code)


def load_original():
    spec = importlib.util.spec_from_file_location("g1_pcp_original_operator", ONE_SHOT)
    check(spec is not None and spec.loader is not None, "g1_db_source_missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call(argv: list[str], env: dict[str, str], code: str,
         *, timeout: int = 30, allow_failure: bool = False) -> str:
    try:
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, check=False, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop(code + "_unavailable") from exc
    if p.returncode != 0 and not allow_failure:
        raise Stop(code + "_failed")
    return p.stdout.strip()


def absent(kind: str, name: str, env: dict[str, str]) -> bool:
    try:
        p = subprocess.run(["docker", kind, "inspect", name],
                           stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=15, env=env, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("g1_db_docker_inspect_unavailable") from exc
    return p.returncode != 0


def classes(raw: str) -> list[str]:
    return [k for k, expr in CLASSIFIERS.items()
            if re.search(expr, raw[-10000:], flags=re.IGNORECASE)]


def safe_checkpoint(env: dict[str, str], expected: str, m) -> str:
    check(os.geteuid() != 0 and re.fullmatch(r"[a-f0-9]{40}", expected) is not None,
          "g1_db_requires_exact_unprivileged_sha")
    check(m.git(env, PCP, "branch", "--show-current") == "main"
          and m.git(env, PCP, "rev-parse", "HEAD") == expected
          and not m.git(env, PCP, "status", "--porcelain"),
          "g1_db_not_clean_exact_pcp_main")
    check(ROOT == m.ROOT and JOURNAL == m.JOURNAL
          and ROOT.is_dir() and not ROOT.is_symlink()
          and ROOT.stat().st_uid == os.geteuid()
          and (ROOT.stat().st_mode & 0o077) == 0,
          "g1_db_original_root_not_private")
    check(JOURNAL.is_file() and not JOURNAL.is_symlink()
          and JOURNAL.stat().st_uid == os.geteuid()
          and (JOURNAL.stat().st_mode & 0o077) == 0,
          "g1_db_original_journal_not_private")
    check(not EVIDENCE.exists() and not EVIDENCE.is_symlink()
          and not CREDENTIALS.exists() and not CREDENTIALS.is_symlink()
          and not (ROOT / "job-evidence.tmp").exists(),
          "g1_db_continuation_already_consumed")
    try:
        prior = json.loads(JOURNAL.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise Stop("g1_db_original_journal_invalid") from exc
    check(isinstance(prior, dict)
          and prior.get("state") == EXPECTED_STATE
          and prior.get("lane") == "pcp"
          and prior.get("seed") == SEED
          and prior.get("pcp_main") == "1570819431861de9a994e62354ac2ae758b2f289"
          and type(prior.get("model_calls")) is int
          and prior["model_calls"] == 0,
          "g1_db_not_original_pre_job_stop")
    # Require the same already-cloned immutable source, not a new workspace.
    src = ROOT / "source"
    ws = ROOT / "workspaces"
    check(src.is_dir() and not src.is_symlink()
          and ws.is_dir() and not ws.is_symlink()
          and not any(ws.iterdir()),
          "g1_db_workspace_or_seed_root_drift")
    check(m.git(env, src, "rev-parse", "HEAD") == SEED
          and m.git(env, src, "branch", "--show-current") == m.BRANCH
          and not m.git(env, src, "status", "--porcelain"),
          "g1_db_immutable_seed_drift")
    refs = m.git(env, src, "for-each-ref", "--format=%(refname)",
                 "refs/remotes/").splitlines()
    check(bool(refs) and all(x.endswith("/" + m.BRANCH) for x in refs),
          "g1_db_direct_solution_ref_leak")
    owned = [ROOT / "config" / x for x in (
        "projects.yml", "project-baselines.yml", "models.yml",
        "routing-policy.yml")]
    owned.append(ROOT / "disabled-github-token")
    check(all(x.is_file() and not x.is_symlink()
              and x.stat().st_uid == os.geteuid() for x in owned),
          "g1_db_original_operator_configs_missing_or_unsafe")
    # Refuse project policy/mount/allowed command drift before issuing any
    # credential or Docker write. Match byte-exact private bootstrap outputs.
    template = (PCP / "config/g1-pilot/projects.pcp.template.yml").read_text()
    placeholder = "$" + "{PCP_G1_PILOT_ROOT}"
    expected_project = template.replace(placeholder, str(ROOT)).replace(
        "php, vendor/bin/phpunit, -c, web/core/phpunit.xml.dist, web/modules/custom/pcp_f2_fixture/tests/src/Unit",
        "php, ../vendor/bin/phpunit, -c, core/phpunit.xml.dist, modules/custom/pcp_f2_fixture/tests/src/Unit",
    ).replace(
        "php, vendor/bin/phpcs, --standard=Drupal, web/modules/custom/pcp_f2_fixture",
        "php, ../vendor/bin/phpcs, --standard=Drupal, modules/custom/pcp_f2_fixture",
    )
    check((ROOT / "config/projects.yml").read_text() == expected_project,
          "g1_db_original_project_scope_changed")
    for name in ("models.yml", "routing-policy.yml"):
        check((ROOT / "config" / name).read_text()
              == (PCP / "config/g1-pilot" / name).read_text(),
              "g1_db_model_or_routing_policy_drift")
    try:
        baseline = json.loads((ROOT / "config/project-baselines.yml").read_text())
        one = baseline["projects"][m.PROJECT]
        rev = one["revisions"][m.REVISION]
        check(set(baseline["projects"]) == {m.PROJECT}
              and one["active_revision"] == m.REVISION
              and rev["source_commit"] == SEED
              and rev["status"] == "approved",
              "g1_db_original_baseline_drift")
    except (ValueError, KeyError, TypeError) as exc:
        raise Stop("g1_db_original_baseline_invalid") from exc
    check(not call(["docker", "container", "ls", "-a",
                    "--filter", "label=com.docker.compose.project=pcp-g1-pilot",
                    "--filter", "label=com.docker.compose.service=db",
                    "--format", "{{.ID}}"], env,
                   "g1_db_label_inventory"),
          "g1_db_previous_database_container_present")
    check(absent("container", DB, env) and absent("volume", VOLUME, env)
          and absent("network", NETWORK, env),
          "g1_db_resource_exists_preserve_without_restart")
    # Do not inspect/modify Direct's container, auth, network or worktree.
    check((m.AUTH / "auth.json").is_file()
          and (m.HOME / "direct-workspace").is_dir()
          and (m.HOME / "auth/direct").is_dir(),
          "g1_db_separate_lane_identity_missing")
    socket = Path("/var/run/docker.sock")
    check(socket.is_socket(), "g1_db_docker_socket_unavailable")
    try:
        ctx = json.loads(call(["docker", "context", "inspect"], env,
                              "g1_db_docker_context"))
        host = ctx[0]["Endpoints"]["docker"]["Host"]
        check(len(ctx) == 1 and isinstance(host, str)
              and host.startswith("unix://")
              and Path(host.removeprefix("unix://")).resolve() == socket.resolve()
              and os.getenv("DOCKER_HOST", "") in ("", host),
              "g1_db_remote_or_mismatched_docker_denied")
    except (KeyError, IndexError, TypeError, ValueError, OSError) as exc:
        raise Stop("g1_db_docker_context_invalid") from exc
    # Never silently select a new model/CLI: use the pinned Direct image label.
    return m.direct_version(env)


def validate_rendered_db(m, env: dict[str, str]) -> None:
    raw = m.compose(env, "g1_db_rendered_compose", "config",
                    "--format", "json", timeout=50)
    try:
        config = json.loads(raw)
        db = config["services"]["db"]
        volume = config["volumes"]["g1-pilot-db"]
        network = config["networks"]["g1-pilot-control"]
        mounts = db.get("volumes") or []
        db_networks = db.get("networks") or {}
        check(db.get("image") == "postgres:16-alpine"
              and db.get("entrypoint") in (None, [], ["docker-entrypoint.sh"])
              and db.get("read_only") is False
              and "CHOWN" in (db.get("cap_add") or [])
              and volume.get("name") == VOLUME
              and network.get("name") == NETWORK
              and network.get("internal") is True
              and set(db_networks) == {"g1-pilot-control"}
              and any(isinstance(v, dict)
                      and v.get("source") == "g1-pilot-db"
                      and v.get("target") == "/var/lib/postgresql/data"
                      for v in mounts),
              "g1_db_rendered_db_contract_not_safe")
    except (KeyError, ValueError, TypeError) as exc:
        raise Stop("g1_db_rendered_compose_invalid") from exc


def inspect_database(env: dict[str, str]) -> dict[str, Any] | None:
    if absent("container", DB, env):
        return None
    text = call(["docker", "container", "inspect", DB], env,
                "g1_db_exact_container_inspect", timeout=20)
    try:
        parsed = json.loads(text)
        check(isinstance(parsed, list) and len(parsed) == 1,
              "g1_db_exact_container_inspect_invalid")
        return parsed[0]
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise Stop("g1_db_container_metadata_invalid") from exc


def verify_database(env: dict[str, str]) -> dict[str, Any]:
    deadline = time.monotonic() + 90
    while True:
        db = inspect_database(env)
        check(db is not None, "g1_db_container_not_created")
        state = db.get("State") or {}
        labels = (db.get("Config") or {}).get("Labels") or {}
        networks = (db.get("NetworkSettings") or {}).get("Networks") or {}
        mounts = db.get("Mounts") or []
        host = db.get("HostConfig") or {}
        check(
            db.get("Name") == "/" + DB
            and labels.get("com.docker.compose.project") == "pcp-g1-pilot"
            and labels.get("com.docker.compose.service") == "db"
            and not host.get("Privileged")
            and host.get("ReadonlyRootfs") is False
            and set(networks) == {NETWORK}
            and any(m.get("Name") == VOLUME and
                    m.get("Destination") == "/var/lib/postgresql/data"
                    for m in mounts if isinstance(m, dict)),
            "g1_db_container_provenance_drift",
        )
        health = (state.get("Health") or {}).get("Status")
        check(state.get("Running") is True,
              "g1_db_not_running_preserve")
        if health == "healthy":
            return {"healthy": True, "container_exact": True,
                    "volume_exact": True, "network_exact": True}
        check(health in ("starting", "unhealthy"),
              "g1_db_health_missing")
        if health == "unhealthy" or time.monotonic() >= deadline:
            raise Stop("g1_db_not_healthy_preserve")
        time.sleep(3)


def launch_db_once(m, env: dict[str, str]) -> dict[str, Any]:
    # Deliberately remove '--wait' from the one failed operation. Separate
    # container creation from independent read-only health attestation; do not
    # assume the original failure was a PostgreSQL error.
    argv = ["docker", "compose", "--project-name", "pcp-g1-pilot"]
    for source in m.COMPOSE_FILES:
        argv += ["--file", str(PCP / source)]
    argv += ["--profile", "g1-pilot-parked",
             "up", "-d", "--no-deps", "db"]
    try:
        result = subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=150, check=False, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("g1_db_explicit_up_unavailable_or_timed_out") from exc
    if result.returncode:
        observed = classes((result.stdout or "") + "\n" + (result.stderr or ""))
        return {"passed": False, "exit_code": result.returncode,
                "failure_classes": observed or ["UNCLASSIFIED"]}
    return {"passed": True, "exit_code": 0, "failure_classes": []}


def execute(expected: str) -> dict[str, Any]:
    m = load_original()
    initial_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0",
                   "GH_PROMPT_DISABLED": "1"}
    version = safe_checkpoint(initial_env, expected, m)
    env = m.env_for_pilot(initial_env, version)
    validate_rendered_db(m, env)  # READ ONLY: no journal changes yet.
    os.umask(0o077)
    m.private(EVIDENCE, json.dumps({
        "state": "db_continuation_started", "original_state": EXPECTED_STATE,
        "model_calls": 0, "attempts": 1, "pcp_main": expected,
        "seed": SEED, "original_journal_preserved": True,
    }, sort_keys=True) + "\n")
    # The first one-shot generated but did not persist ephemeral DB secrets;
    # no DB/volume was created, so one NEW private identity is safe. Persist it
    # in 0600 for forensic same-state continuity, never stdout or model prompt.
    credentials = {
        k: env[k] for k in (
            "PCP_G1_PILOT_DB_PASSWORD", "PCP_G1_PILOT_INTERNAL_TOKEN",
            "PCP_G1_PILOT_ROUTER_TOKEN", "PCP_G1_PILOT_RUNTIME_TOKEN")
    }
    m.private(CREDENTIALS, json.dumps(credentials, sort_keys=True) + "\n")
    launch = launch_db_once(m, env)
    if not launch["passed"]:
        # Remain STOP. This marker is intentionally exclusive/no retry.
        m.JOURNAL = EVIDENCE
        m.journal("db_create_failed", model_calls=0,
                  error_classes=launch["failure_classes"],
                  docker_exit_code=launch["exit_code"],
                  original_journal_preserved=True)
        raise Stop("g1_db_bounded_create_failed_" +
                   "_".join(launch["failure_classes"]))
    proof = verify_database(env)
    m.JOURNAL = EVIDENCE  # Original 0600 job-evidence.json never rewritten.
    m.journal("database_healthy", model_calls=0,
              **proof, original_journal_preserved=True)
    started = time.monotonic()
    try:
        return m.continue_after_database(env, started)
    except m.Stop as exc:
        # The reviewed original operator only raises fixed, sanitized codes.
        raise Stop("g1_db_original_postdb_" + str(exc)) from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-pcp-sha", required=True)
    args = parser.parse_args()
    try:
        result = execute(args.expected_pcp_sha)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Stop as exc:
        print(json.dumps({
            "status": "STOP_G1_PCP_DB_SAME_ROOT_CONTINUATION",
            "blocker": str(exc),
            "no_automatic_retry": True, "no_cleanup": True,
            "original_journal_preserved": True,
            "new_job_replaced_or_reset": False,
            "direct_smoke_f2_chonhac_untouched": True,
        }, sort_keys=True))
        return 2
    except Exception as exc:
        # Includes the original operator's fail-closed Stop: never print
        # exception content, Docker stderr, env or provider output.
        print(json.dumps({
            "status": "STOP_G1_PCP_DB_SAME_ROOT_CONTINUATION",
            "blocker": "g1_db_unclassified_" + type(exc).__name__,
            "no_automatic_retry": True, "no_cleanup": True,
            "original_journal_preserved": True,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
