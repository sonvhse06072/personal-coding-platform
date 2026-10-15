#!/usr/bin/env python3
"""Single owner-invoked G1-T01 PCP Engine/Router/Codex/Executor coding pilot.

Source remains PARKED by default. This operator alone activates one new
seed-pinned PCP job, never the Direct candidate or accepted no-model smoke.
An exclusive journal is created BEFORE Docker/job writes. STOP preserves all
work and does not retry a model, regenerate a workspace or clear a resource.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

PCP = Path(__file__).resolve().parents[1]
HOME = Path.home() / ".pcp-g1-pilot"
ROOT = HOME / "pcp-t01"
AUTH = HOME / "auth/pcp"
JOURNAL = ROOT / "job-evidence.json"
SEED = "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
PROJECT = "pcp-benchmark-g1-pilot"
BRANCH = "benchmark/g1-codex-smoke-v1"
REVISION = "g1-t01-2026-10-15"
REPO_URL = "https://github.com/sonvhse06072/pcp-g0-fullpath-fixture.git"
DIRECT_IMAGE = "pcp-g1-pilot-direct-codex"
DDEV_NAME = "pcp-g1-codex-pilot"
PRIVATE_NETWORK = "pcp-g1-codex-pilot-private"
ALLOWED = {
    "web/modules/custom/pcp_f2_fixture/src/WindowOverlapDetector.php",
    "web/modules/custom/pcp_f2_fixture/tests/src/Unit/WindowOverlapDetectorTest.php",
}
COMPOSE_FILES = (
    "deploy/g1/compose.pilot.parked.yml",
    "deploy/g1/compose.pilot.egress.parked.yml",
    "deploy/g1/compose.pilot.t01-operator.yml",
)
TASK = (
    "G1-T01 independent coding trial. Implement a public method "
    "intersectionMinutes(int $start, int $end, int $otherStart, int "
    "$otherEnd): int on WindowOverlapDetector. For valid nonempty same-day "
    "half-open minute ranges (0 <= start < end <= 1440), return the number "
    "of shared minutes. Return zero for disjoint or endpoint-touching "
    "ranges and for invalid, empty, out-of-day or overnight ranges. "
    "Preserve intersects() semantics exactly. Add focused PHPUnit unit "
    "tests for partial overlap, containment, equal intervals, symmetry, "
    "touching, disjoint, zero/1440 boundaries, invalid and overnight. "
    "Only edit the WindowOverlapDetector.php implementation and its "
    "tests/src/Unit/WindowOverlapDetectorTest.php file. No dependencies, "
    "schema, network, DDEV hooks or configuration. Do not commit or push; "
    "do not request privileges or use Docker, host services or GitHub. "
    "Finish this one coding turn with a concise implementation summary."
)


class Stop(RuntimeError):
    """Fixed operator failure code; never output raw subprocess stderr."""


def check(condition: bool, code: str) -> None:
    if not condition:
        raise Stop(code)


def run(argv: list[str], env: dict[str, str], label: str, *,
        timeout: int = 90, allow_failure: bool = False) -> str:
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, env=env,
                           timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop(label + "_unavailable_or_timeout") from exc
    if p.returncode and not allow_failure:
        raise Stop(label + "_failed")
    return p.stdout.strip()


def git(env: dict[str, str], root: Path, *args: str) -> str:
    return run(["git", "-C", str(root), *args], env, "g1_pcp_git", timeout=30)


def compose(env: dict[str, str], label: str, *args: str, timeout: int = 180) -> str:
    argv = ["docker", "compose", "--project-name", "pcp-g1-pilot"]
    for name in COMPOSE_FILES:
        argv += ["--file", str(PCP / name)]
    return run([*argv, "--profile", "g1-pilot-parked", *args],
               env, label, timeout=timeout)


def private(path: Path, data: str) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o600)


def journal(state: str, **kwargs: object) -> None:
    payload = json.dumps({"state": state, "lane": "pcp",
                          "seed": SEED, **kwargs}, sort_keys=True) + "\n"
    if state == "started":
        private(JOURNAL, payload)
    else:
        temp = ROOT / "job-evidence.tmp"
        private(temp, payload)
        os.replace(temp, JOURNAL)


def direct_version(env: dict[str, str]) -> str:
    raw = run(["docker", "image", "inspect", DIRECT_IMAGE, "--format",
               "{{json .Config.Labels}}"], env, "g1_direct_image_metadata")
    try:
        labels = json.loads(raw)
        version = labels["org.opencontainers.image.pcp.codex-version"]
        check(labels["org.opencontainers.image.pcp.g1-scope"] == "direct-control-only"
              and bool(re.fullmatch(r"\d+\.\d+\.\d+", version)),
              "g1_direct_image_version_drift")
    except (TypeError, KeyError, ValueError) as exc:
        raise Stop("g1_direct_image_labels_invalid") from exc
    return version


def preflight(expected: str) -> tuple[dict[str, str], str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GH_PROMPT_DISABLED": "1"}
    check(os.geteuid() != 0 and re.fullmatch(r"[a-f0-9]{40}", expected) is not None,
          "g1_pcp_unprivileged_exact_sha_required")
    check(git(env, PCP, "branch", "--show-current") == "main"
          and git(env, PCP, "rev-parse", "HEAD") == expected
          and not git(env, PCP, "status", "--porcelain"),
          "g1_pcp_clean_main_mismatch")
    check(HOME.is_dir() and not HOME.is_symlink()
          and HOME.stat().st_uid == os.geteuid()
          and not ROOT.exists() and not ROOT.is_symlink(),
          "g1_pcp_pilot_already_started_or_root_invalid")
    auth = AUTH / "auth.json"
    check(AUTH.is_dir() and not AUTH.is_symlink()
          and auth.is_file() and not auth.is_symlink()
          and auth.stat().st_uid == os.geteuid()
          and (auth.stat().st_mode & 0o077) == 0,
          "g1_pcp_independent_auth_invalid")
    check((HOME / "direct-workspace").is_dir()
          and (HOME / "auth/direct").is_dir(),
          "g1_pcp_direct_control_missing")
    proof = run(["python3", str(PCP / "scripts/g1-pilot-source-contract.py")],
                env, "g1_pcp_source_contract", timeout=35)
    check('"PASS_G1_PILOT_SOURCE_PARKED"' in proof,
          "g1_pcp_source_not_parked")
    socket = Path("/var/run/docker.sock")
    check(socket.is_socket(), "g1_pcp_docker_socket_absent")
    try:
        context = json.loads(run(["docker", "context", "inspect"],
                                 env, "g1_pcp_docker_context"))
        endpoint = context[0]["Endpoints"]["docker"]["Host"]
        check(len(context) == 1 and endpoint.startswith("unix://")
              and Path(endpoint[7:]).resolve() == socket.resolve()
              and os.getenv("DOCKER_HOST", "") in ("", endpoint),
              "g1_pcp_nonlocal_docker_denied")
    except (ValueError, KeyError, TypeError, IndexError, OSError) as exc:
        raise Stop("g1_pcp_docker_context_invalid") from exc
    for kind, names in {
        "container": ("ddev-pcp-g1-codex-pilot-web",
                      "ddev-pcp-g1-codex-pilot-db",
                      "pcp-g1-pilot-db-1", "pcp-g1-pilot-router-1",
                      "pcp-g1-pilot-executor-1",
                      "pcp-g1-pilot-g1-pilot-provider-proxy-1"),
        "volume": ("pcp-g1-pilot-postgres", "pcp-g1-pilot-cache"),
        "network": ("pcp-g1-pilot-control", "pcp-g1-pilot-provider-egress",
                    PRIVATE_NETWORK),
    }.items():
        for name in names:
            p = subprocess.run(["docker", kind, "inspect", name],
                               capture_output=True, stdin=subprocess.DEVNULL,
                               timeout=15, env=env)
            check(p.returncode != 0, "g1_pcp_resource_collision")
    return env, direct_version(env)


def bootstrap(env: dict[str, str]) -> None:
    for path in ("config", "workspaces", "xdg", "xdg/ddev"):
        (ROOT / path).mkdir(parents=True, mode=0o700, exist_ok=False)
    private(ROOT / "xdg/ddev/global_config.yaml",
            "omit_containers: [ddev-router, ddev-ssh-agent]\n"
            "instrumentation_opt_in: false\n")
    private(ROOT / "disabled-github-token", "")
    # Download ONLY the immutable seed branch; no Direct PR ref/object can be
    # searched by the PCP model even with git log --all.
    run(["git", "clone", "--single-branch", "--depth", "1", "--no-tags",
         "--branch", BRANCH, REPO_URL, str(ROOT / "source")],
        env, "g1_pcp_seed_only_clone", timeout=240)
    source = ROOT / "source"
    check(git(env, source, "rev-parse", "HEAD") == SEED
          and git(env, source, "branch", "--show-current") == BRANCH,
          "g1_pcp_seed_not_immutable")
    refs = git(env, source, "for-each-ref", "--format=%(refname)",
               "refs/remotes/").splitlines()
    check(bool(refs) and all(x.endswith("/" + BRANCH) for x in refs),
          "g1_pcp_direct_solution_ref_present")
    template = (PCP / "config/g1-pilot/projects.pcp.template.yml").read_text()
    placeholder = "$" + "{PCP_G1_PILOT_ROOT}"
    check(template.count(placeholder) == 1, "g1_pcp_template_root_invalid")
    # PHP commands run from Drupal's web docroot, not repository root.
    template = template.replace(placeholder, str(ROOT)).replace(
        "php, vendor/bin/phpunit, -c, web/core/phpunit.xml.dist, web/modules/custom/pcp_f2_fixture/tests/src/Unit",
        "php, ../vendor/bin/phpunit, -c, core/phpunit.xml.dist, modules/custom/pcp_f2_fixture/tests/src/Unit",
    ).replace(
        "php, vendor/bin/phpcs, --standard=Drupal, web/modules/custom/pcp_f2_fixture",
        "php, ../vendor/bin/phpcs, --standard=Drupal, modules/custom/pcp_f2_fixture",
    )
    private(ROOT / "config/projects.yml", template)
    for name in ("models.yml", "routing-policy.yml"):
        private(ROOT / "config" / name,
                (PCP / "config/g1-pilot" / name).read_text(encoding="utf-8"))
    refs = {x: [{"path": "docs/G1-SMOKE.md"}] for x in (
        "goals", "non_goals", "requirements", "architecture_constraints",
        "quality_policy", "security_policy", "budget_policy", "roadmap_frame",
    )}
    doc = {"version": 1, "projects": {PROJECT: {
        "active_revision": REVISION,
        "revisions": {REVISION: {"status": "approved",
                                "source_commit": SEED, "references": refs}},
    }}}
    private(ROOT / "config/project-baselines.yml",
            json.dumps(doc, sort_keys=True) + "\n")


def env_for_pilot(original: dict[str, str], version: str) -> dict[str, str]:
    return {**original,
        "PCP_G1_PILOT_ROOT": str(ROOT),
        "PCP_G1_PILOT_REPO_ROOT": str(PCP),
        "PCP_G1_PILOT_UID": str(os.geteuid()),
        "PCP_G1_PILOT_GID": str(os.getegid()),
        "PCP_G1_PILOT_SOCKET_GID": str(Path("/var/run/docker.sock").stat().st_gid),
        "PCP_G1_PILOT_CODEX_VERSION": version,
        "PCP_G1_PILOT_RUNTIME_IMAGE": DIRECT_IMAGE,
        "PCP_G1_PILOT_PCP_CODEX_AUTH_DIR": str(AUTH),
        "PCP_G1_PILOT_DIRECT_WORKSPACE_DIR": str(HOME / "direct-workspace"),
        "PCP_G1_PILOT_DIRECT_CODEX_AUTH_DIR": str(HOME / "auth/direct"),
        "PCP_G1_PILOT_GITHUB_TOKEN_FILE": str(ROOT / "disabled-github-token"),
        "PCP_G1_PILOT_DB_PASSWORD": secrets.token_hex(24),
        "PCP_G1_PILOT_INTERNAL_TOKEN": secrets.token_urlsafe(36),
        "PCP_G1_PILOT_ROUTER_TOKEN": secrets.token_urlsafe(36),
        "PCP_G1_PILOT_RUNTIME_TOKEN": secrets.token_urlsafe(36),
        "PCP_G1_PILOT_BROKER_ENABLED": "",
        "PCP_G1_PILOT_JOB_ID": "",
        "PCP_G1_PILOT_DEV_TOKEN": "",
        "PCP_G1_PILOT_DEADLINE": "",
    }


def runtime(env: dict[str, str], label: str, code: str,
            timeout: int = 180) -> dict[str, object]:
    out = compose(env, label, "run", "--rm", "--no-deps", "-T",
                  "--entrypoint", "python3", "runtime", "-c", code,
                  timeout=timeout)
    try:
        payload = json.loads(out.splitlines()[-1])
        check(isinstance(payload, dict), label + "_non_object")
        return payload
    except (TypeError, IndexError, ValueError) as exc:
        raise Stop(label + "_not_json") from exc


def add_job(env: dict[str, str]) -> str:
    task = {"title": "G1-T01 same-day intersection minutes",
            "description": TASK, "task_type": "drupal",
            "semantic": {
                "ambiguity": 5, "architecture_impact": 0, "risk": 5,
                "verification_difficulty": 10, "context_requirement": 15,
                "novelty": 10, "reasoning_requirement": 20}}
    payload = {"project_id": PROJECT, "task": task, "source_commit": SEED,
               "baseline_revision": REVISION, "auto_run": False,
               "dry_run": False, "repo_hints": {
                   "estimated_files": 2, "tests_available": True,
                   "existing_pattern": True, "security_sensitive": False}}
    code = (
        "import json;from app.telemetry_storage import TelemetryStorage;"
        "from app.engine import RuntimeEngine;"
        "s=TelemetryStorage();s.init();"
        "assert not s.list(limit=1),'G1 pilot DB already has jobs';"
        "j=RuntimeEngine(s).create_job(" + repr(payload) + ");"
        "print(json.dumps({'job_id':j}))"
    )
    job = runtime(env, "g1_pcp_single_job_insert", code).get("job_id")
    check(isinstance(job, str) and re.fullmatch(r"[a-f0-9]{32}", job) is not None,
          "g1_pcp_job_id_invalid")
    return job


def create_workspace(env: dict[str, str], job: str) -> Path:
    code = (
        "import os,json;from app.main import create_workspace,WorkspaceRequest;"
        "p=WorkspaceRequest(job_id=os.environ['PCP_TRUSTED_CODEX_JOB_ID'],"
        "project_id='" + PROJECT + "',ref='" + SEED + "',"
        "workspace_mode='isolated_clone');"
        "print(json.dumps(create_workspace(p)))"
    )
    out = compose(env, "g1_pcp_executor_clone", "run", "--rm", "--no-deps",
                  "-T", "--entrypoint", "python3", "executor", "-c", code,
                  timeout=330)
    try:
        result = json.loads(out.splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise Stop("g1_pcp_executor_clone_non_json") from exc
    ws = ROOT / "workspaces" / job
    check(result.get("workspace") == str(ws)
          and result.get("source_commit") == SEED
          and result.get("branch") == "ai/" + job[:12]
          and git(env, ws, "rev-parse", "HEAD") == SEED,
          "g1_pcp_workspace_provenance_mismatch")
    sys.path.insert(0, str(PCP / "services/ddev-executor"))
    from app.g1_pilot_ddev_identity import (
        OVERRIDE, OVERRIDE_FILE, CACHE_FILE, CACHE_COMPOSE,
        require_pilot_workspace_identity,
    )
    ddev = ws / ".ddev"
    check(ddev.is_dir() and not ddev.is_symlink()
          and not (ddev / OVERRIDE_FILE).exists()
          and not (ddev / CACHE_FILE).exists(),
          "g1_pcp_ddev_override_collision")
    private(ddev / OVERRIDE_FILE, OVERRIDE)
    private(ddev / CACHE_FILE, CACHE_COMPOSE)
    with (ws / ".git/info/exclude").open("a", encoding="utf-8") as stream:
        stream.write("\n.ddev/" + OVERRIDE_FILE + "\n.ddev/" + CACHE_FILE + "\n")
    require_pilot_workspace_identity(ws, prepared=True)
    check(not git(env, ws, "status", "--porcelain"),
          "g1_pcp_operator_overrides_dirty")
    # Runtime sees the ONE existing job workspace; it may not create a second.
    code = (
        "import json,os;from app.telemetry_storage import TelemetryStorage;"
        "s=TelemetryStorage();j=os.environ['PCP_TRUSTED_CODEX_JOB_ID'];"
        "s.update(j,workspace='" + str(ws) + "',branch='ai/" + job[:12]
        + "',source_commit='" + SEED + "');"
        "print(json.dumps({'workspace_registered':True}))"
    )
    check(runtime(env, "g1_pcp_register_exact_workspace", code)
          .get("workspace_registered") is True,
          "g1_pcp_workspace_registration_failed")
    return ws


def isolate_ddev(env: dict[str, str], workspace: Path) -> None:
    names = ("ddev-" + DDEV_NAME + "-web", "ddev-" + DDEV_NAME + "-db")
    listed = run(["docker", "container", "ls", "-a",
                  "--filter", "label=com.ddev.site-name=" + DDEV_NAME,
                  "--format", "{{.Names}}"], env,
                 "g1_pcp_ddev_inventory").splitlines()
    check(set(listed) == set(names), "g1_pcp_ddev_peers_unexpected")
    for name in names:
        doc = json.loads(run(["docker", "container", "inspect", name],
                             env, "g1_pcp_ddev_inspect"))[0]
        labels = doc["Config"].get("Labels") or {}
        check(labels.get("com.ddev.approot") == str(workspace)
              and labels.get("com.ddev.site-name") == DDEV_NAME
              and doc["State"]["Running"]
              and not doc["HostConfig"].get("Privileged"),
              "g1_pcp_ddev_identity_or_privilege_drift")
    run(["docker", "network", "create", "--internal", "--label",
         "pcp.scope=g1-pilot-only", PRIVATE_NETWORK],
        env, "g1_pcp_private_network")
    for name in names:
        run(["docker", "network", "connect", PRIVATE_NETWORK, name],
            env, "g1_pcp_network_attach")
    for name in names:
        doc = json.loads(run(["docker", "container", "inspect", name],
                             env, "g1_pcp_network_inspect"))[0]
        networks = doc["NetworkSettings"].get("Networks") or {}
        check(PRIVATE_NETWORK in networks, "g1_pcp_quarantine_not_attached")
        for other in sorted(set(networks) - {PRIVATE_NETWORK}):
            run(["docker", "network", "disconnect", other, name],
                env, "g1_pcp_quarantine_disconnect")
    from app.g1_pilot_ddev_identity import require_g1_pilot_isolated_ddev
    require_g1_pilot_isolated_ddev(workspace)


def focused_checks(env: dict[str, str], ws: Path) -> bool:
    code = (
        "import json,os,urllib.request;"
        "u='http://pcp-dev-executor:8790/v1/codex-dev/phase';"
        "b={'job_id':os.environ['PCP_TRUSTED_CODEX_JOB_ID'],"
        "'project_id':'" + PROJECT + "','workspace':'" + str(ws)
        + "','source_commit':'" + SEED + "'};"
        "checks=[];"
        "\nfor phase in ('targeted_tests','static_analysis'):\n"
        " d={**b,'phase':phase};"
        " q=urllib.request.Request(u,data=json.dumps(d).encode(),"
        "headers={'Content-Type':'application/json',"
        "'Authorization':'Bearer '+os.environ['PCP_TRUSTED_CODEX_DEV_TOKEN']},"
        "method='POST');"
        " r=urllib.request.urlopen(q,timeout=180);"
        " a=json.load(r);checks.append(a.get('passed') is True)\n"
        "print(json.dumps({'pass':len(checks)==2 and all(checks)}))"
    )
    return runtime(env, "g1_pcp_real_php_focused_tests", code,
                   timeout=390).get("pass") is True


def verify_commit(env: dict[str, str], ws: Path) -> str:
    paths = set(git(env, ws, "diff", "--name-only", SEED).splitlines())
    paths.update(git(env, ws, "diff", "--name-only").splitlines())
    paths.update(git(env, ws, "diff", "--cached", "--name-only").splitlines())
    check(paths == ALLOWED, "g1_pcp_code_or_tests_missing_or_out_of_scope")
    head = git(env, ws, "rev-parse", "HEAD")
    if head == SEED:
        run(["git", "-C", str(ws), "diff", "--check"], env,
            "g1_pcp_diff_check")
        run(["git", "-C", str(ws), "add", "--", *sorted(ALLOWED)],
            env, "g1_pcp_add_exact_paths")
        run(["git", "-C", str(ws), "-c", "core.hooksPath=/dev/null",
             "-c", "user.name=PCP G1 Pilot",
             "-c", "user.email=pcp-g1-pilot@localhost",
             "commit", "-m", "feat(g1-t01): count same-day intersection minutes"],
            env, "g1_pcp_scoped_commit")
        head = git(env, ws, "rev-parse", "HEAD")
    check(head != SEED and git(env, ws, "rev-parse", "HEAD^") == SEED
          and not git(env, ws, "status", "--porcelain", "-uno")
          and set(git(env, ws, "diff", "--name-only", SEED, "HEAD")
                  .splitlines()) == ALLOWED,
          "g1_pcp_commit_not_exact_seed_child")
    return head


def execute(expected: str) -> dict[str, object]:
    started = time.monotonic()
    original, version = preflight(expected)
    os.umask(0o077)
    ROOT.mkdir(mode=0o700, exist_ok=False)
    journal("started", pcp_main=expected, model_calls=0)
    bootstrap(original)
    env = env_for_pilot(original, version)
    compose(env, "g1_pcp_compose_check", "config", "--quiet", timeout=60)
    compose(env, "g1_pcp_build_minimal", "build",
            "runtime", "router", "executor", timeout=1800)
    compose(env, "g1_pcp_database_start", "up", "-d", "--wait",
            "db", timeout=260)
    job = add_job(env)
    env["PCP_G1_PILOT_JOB_ID"] = job
    journal("job_created", job_id=job, model_calls=0)
    ws = create_workspace(env, job)
    run(["docker", "volume", "create", "--label", "pcp.scope=g1-pilot-only",
         "pcp-g1-pilot-cache"], env, "g1_pcp_private_cache")
    compose(env, "g1_pcp_ddev_start", "run", "--rm", "--no-deps",
            "-T", "--entrypoint", "/bin/sh", "executor", "-c",
            'cd "$CODING_WORKSPACES_ROOT/$PCP_TRUSTED_CODEX_JOB_ID" && '
            'exec env -u PLATFORM_INTERNAL_TOKEN -u ROUTER_API_TOKEN '
            '-u RUNTIME_API_TOKEN -u PCP_TRUSTED_CODEX_DEV_TOKEN '
            'ddev start -y', timeout=900)
    isolate_ddev(env, ws)
    compose(env, "g1_pcp_services", "up", "-d", "--wait",
            "router", "executor", "g1-pilot-provider-proxy", timeout=270)
    login = compose(env, "g1_pcp_container_auth", "run", "--rm",
                    "--no-deps", "-T", "--entrypoint", "codex",
                    "runtime", "login", "status", timeout=75)
    check("Logged in using ChatGPT" in login,
          "g1_pcp_independent_codex_login_missing")
    env["PCP_G1_PILOT_DEV_TOKEN"] = secrets.token_urlsafe(48)
    env["PCP_G1_PILOT_DEADLINE"] = str(int(time.time()) + 1750)
    env["PCP_G1_PILOT_BROKER_ENABLED"] = "owner-approved"
    compose(env, "g1_pcp_one_job_broker", "up", "-d", "--no-deps",
            "--force-recreate", "executor", timeout=180)
    journal("model_reserved", job_id=job, model_calls="up_to_two")
    code = (
        "import asyncio,json,os;"
        "from app.telemetry_storage import TelemetryStorage;"
        "from app.engine import RuntimeEngine;"
        "s=TelemetryStorage();j=os.environ['PCP_TRUSTED_CODEX_JOB_ID'];"
        "asyncio.run(RuntimeEngine(s).run_job(j));"
        "r=s.get(j) or {};p=r.get('progress') or {};"
        "print(json.dumps({'job_id':j,'workspace':r.get('workspace'),"
        "'branch':r.get('branch'),'status':r.get('status'),"
        "'model_calls':p.get('model_calls',0)}))"
    )
    began_run = time.monotonic()
    result = runtime(env, "g1_pcp_real_engine_execute", code, timeout=1800)
    elapsed = round(time.monotonic() - began_run, 1)
    calls = result.get("model_calls")
    check(result.get("job_id") == job
          and result.get("workspace") == str(ws)
          and result.get("branch") == "ai/" + job[:12],
          "g1_pcp_engine_job_provenance_failed")
    check(type(calls) is int and 1 <= calls <= 2,
          "g1_pcp_model_calls_missing_or_overbudget")
    journal("coding_finished", job_id=job, model_calls=calls,
            engine_elapsed_seconds=elapsed, engine_status=result.get("status"))
    check(focused_checks(env, ws), "g1_pcp_focused_php_tests_failed")
    head = verify_commit(env, ws)
    journal("commit_verified", job_id=job, model_calls=calls,
            candidate_sha=head, focused_tests="PASS",
            engine_elapsed_seconds=elapsed)
    run(["git", "-C", str(ws), "push", REPO_URL,
         "HEAD:refs/heads/ai/" + job[:12]],
        env, "g1_pcp_exact_branch_push", timeout=180)
    journal("pushed", job_id=job, model_calls=calls,
            candidate_sha=head, branch="ai/" + job[:12],
            focused_tests="PASS", engine_elapsed_seconds=elapsed)
    run(["gh", "workflow", "run", "validation.yml",
         "--repo", "sonvhse06072/pcp-g0-fullpath-fixture",
         "--ref", "main", "-f", "candidate_sha=" + head],
        env, "g1_pcp_hosted_ci_dispatch", timeout=75)
    total = round(time.monotonic() - started, 1)
    journal("ci_dispatched", job_id=job, model_calls=calls,
            candidate_sha=head, branch="ai/" + job[:12],
            focused_tests="PASS", engine_elapsed_seconds=elapsed,
            operator_elapsed_seconds=total)
    return {"status": "G1_PCP_CANDIDATE_PUSHED_CI_DISPATCHED",
            "job_id": job, "branch": "ai/" + job[:12], "commit": head,
            "model": "gpt-6-luna", "reasoning": "medium",
            "model_calls": calls, "engine_elapsed_seconds": elapsed,
            "operator_elapsed_seconds": total,
            "focused_tests": "PASS", "hosted_ci": "DISPATCHED_NOT_VERIFIED",
            "pm_accepted_pr": False, "g0": "HOLD_NOT_GO"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-pcp-sha", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args.expected_pcp_sha), sort_keys=True))
        return 0
    except Stop as exc:
        print(json.dumps({"status": "STOP_G1_PCP_T01",
                          "blocker": str(exc), "no_automatic_retry": True,
                          "resources_and_journal_preserved": True,
                          "direct_and_smoke_untouched": True,
                          "f2_and_chonhac_untouched": True}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
