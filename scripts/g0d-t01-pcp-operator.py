#!/usr/bin/env python3
"""G0D-T01: one authorized PCP fixture job, no retries or delivery.

prepare --expected-sha HEAD: read-only gates, durable claim, ONE Runtime POST
status  --expected-sha HEAD: GET-only persisted job (never writes)
execute --expected-sha HEAD: durable claim, ONE Runtime model execution POST

The only target is the already activated fixture-only G0 Runtime. Neither this
operator nor its agent receives GitHub credentials or touches Chợ Nhạc, legacy
PCP, DDEV, fixture base refs, Docker lifecycle or Direct's independent arm.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
READINESS_SOURCE = ROOT / "scripts/g0-fixture-live-readiness.py"
JOURNAL = "g0d-t01-pcp-attempt.json"
PROJECT = "pcp-g0-drupal-fixture"
SEED = "39ef13c25b24c4a1b43a720ae53419f479996ed2"
ALLOWED_FILES = sorted((
    "web/modules/custom/pcp_g0_fixture/src/EventLabelNormalizer.php",
    "web/modules/custom/pcp_g0_fixture/tests/src/Unit/EventLabelNormalizerTest.php",
    "web/modules/custom/pcp_g0_fixture/tests/src/Kernel/EventLabelServiceTest.php",
))
JOB_ID = re.compile(r"^[0-9a-f]{32}$")

# This is executed exclusively by Python inside the exact G0 Runtime container.
# Its secret comes from the container's existing private process environment.
# Only preapproved local routes are accepted; the raw HTTP body is never echoed
# and no untrusted URL, OAuth token or prompt crosses the host Docker CLI.
HTTP = r"""
import json, os, sys, urllib.request, urllib.error
method, path, bound = sys.argv[1:]
bound = int(bound)
if (method, path) != ("POST", "/v1/g0-fixture/prepare") and not (
    path.startswith("/v1/g0-fixture/jobs/")
    and __import__("re").fullmatch(
        r"/v1/g0-fixture/jobs/[0-9a-f]{32}(?:/execute)?", path
    )
    and method in {"GET", "POST"}
    and (method == "GET" or path.endswith("/execute"))
):
    raise RuntimeError("g0_http_route_not_allowed")
token = os.environ["RUNTIME_API_TOKEN"]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
req = urllib.request.Request(
    "http://127.0.0.1:8787" + path,
    headers={"Authorization": "Bearer " + token},
    data=b"" if method == "POST" else None,
    method=method,
)
try:
    with opener.open(req, timeout=bound) as resp:
        status = resp.status
        raw = resp.read(16000)
except urllib.error.HTTPError as exc:
    print(json.dumps({"http_status": exc.code}, sort_keys=True))
else:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    result = data.get("result")
    if not isinstance(result, dict):
        result = {}
    allowed = (
        "stage", "commit", "changed_files", "verification_policy",
        "workflow_blob", "codex_cli_version", "deterministic_ci",
        "pull_request",
    )
    print(json.dumps({
        "http_status": status,
        "job_id": data.get("job_id"),
        "project_id": data.get("project_id"),
        "source_commit": data.get("source_commit"),
        "branch": data.get("branch"),
        "job_status": data.get("status"),
        "result": {k: result[k] for k in allowed if k in result},
    }, sort_keys=True))
"""


def _load():
    spec = importlib.util.spec_from_file_location("g0_live_for_pcpt01", READINESS_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("G0 HTTP readiness source unavailable")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


live = _load()
g0 = live.g0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path() -> Path:
    root = Path.home() / ".pcp-g0d01"
    live.activation.auth._check_private_existing(root, directory=True)
    if root.is_symlink():
        raise g0.GateError("g0_pcp_private_root_symlink")
    return root / JOURNAL


def _existing() -> dict:
    path = _path()
    return live.activation.auth.upgrader._read_json_secure(path)


def _claim(data: dict) -> None:
    path = _path()
    if path.exists() or path.is_symlink():
        raise g0.GateError("g0_pcp_attempt_already_claimed_no_retry")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise g0.GateError("g0_pcp_concurrent_claim") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())


def _update(data: dict) -> None:
    path = _path()
    live.activation.auth._check_private_existing(path, directory=False)
    live.activation.auth.upgrader._private_write(path, data)


def _identity(repo: Path, fixture: Path, sha: str) -> None:
    if not g0.SOURCE_SHA.fullmatch(sha):
        raise g0.GateError("g0_pcp_source_sha_invalid")
    g0.require_local_docker_context()
    g0.require_exact_repo(repo, g0.EXPECTED_REPO, "main", sha)
    g0.require_exact_repo(fixture, g0.EXPECTED_FIXTURE, "benchmark/pcp", SEED)
    live.activation._validate_overlay()
    live._activated_state()
    live._docker_boundary(repo)


def _http(method: str, route: str, timeout: int) -> dict:
    if method not in {"GET", "POST"}:
        raise g0.GateError("g0_pcp_method_not_allowed")
    if not (
        (method == "POST" and route == "/v1/g0-fixture/prepare")
        or (method == "GET" and re.fullmatch(
            r"/v1/g0-fixture/jobs/[0-9a-f]{32}", route
        ))
        or (method == "POST" and re.fullmatch(
            r"/v1/g0-fixture/jobs/[0-9a-f]{32}/execute", route
        ))
    ):
        raise g0.GateError("g0_pcp_route_not_allowed")
    raw = g0.run(
        [
            "docker", "exec", "-e", "PYTHONDONTWRITEBYTECODE=1",
            g0.NAMES["runtime"], "python3", "-c", HTTP,
            method, route, str(timeout - 15),
        ],
        timeout=timeout, label="g0_pcp_" + method.lower() + "_scoped",
    )
    try:
        report = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise g0.GateError("g0_pcp_http_result_unreadable") from exc
    if not isinstance(report, dict) or report.get("http_status") != 200:
        raise g0.GateError("g0_pcp_http_non_success")
    return report


def _valid_job(row: dict, *, require_result: bool = False) -> str:
    jid = row.get("job_id")
    if (
        not isinstance(jid, str) or not JOB_ID.fullmatch(jid)
        or row.get("project_id") != PROJECT
        or row.get("source_commit") != SEED
        or row.get("branch") != "ai/" + jid[:12]
    ):
        raise g0.GateError("g0_pcp_fixture_job_identity_invalid")
    if row.get("job_status") not in {"queued", "executing", "blocked",
                                     "waiting_human", "delivering"}:
        raise g0.GateError("g0_pcp_fixture_job_status_unknown")
    result = row.get("result") or {}
    if row["job_status"] == "waiting_human" or require_result:
        if (
            not isinstance(result, dict)
            or result.get("stage") != "awaiting_fixture_only_delivery"
            or not re.fullmatch(r"[0-9a-f]{40}", str(result.get("commit") or ""))
            or sorted(result.get("changed_files") or []) != ALLOWED_FILES
        ):
            raise g0.GateError("g0_pcp_result_outside_frozen_contract")
    return jid


def prepare(repo: Path, fixture: Path, sha: str) -> dict:
    # The existing live GET-only operator also checks the G0 DB is empty.
    live_check = live.inspect(repo, fixture, sha)
    if live_check.get("status") != "PASS" or live_check.get("g0_job_store_empty") is not True:
        raise g0.GateError("g0_pcp_live_readiness_not_pass")
    path = _path()
    if path.exists() or path.is_symlink():
        raise g0.GateError("g0_pcp_attempt_already_claimed_no_retry")
    record = {
        "phase": "pcp", "state": "prepare_claimed",
        "source_sha": sha, "task_id": "G0D-T01", "seed": SEED,
        "prepare_started_at": _now(), "prepare_attempted": True,
        "execute_attempted": False, "delivery_enabled": False,
    }
    _claim(record)
    response = _http("POST", "/v1/g0-fixture/prepare", 400)
    _valid_job(response)
    if response["job_status"] != "queued":
        raise g0.GateError("g0_pcp_prepare_not_queued")
    record.update({
        "state": "prepared", "job_id": response["job_id"],
        "branch": response["branch"], "prepare_completed_at": _now(),
    })
    _update(record)
    return {
        "status": "PASS", "phase": "g0d_t01_pcp_prepared",
        "job_id": response["job_id"], "branch": response["branch"],
        "source_sha": sha, "seed": SEED,
        "model_calls_this_command": 0, "ready_for_one_execute": True,
        "github_delivery_enabled": False,
    }


def status(repo: Path, fixture: Path, sha: str) -> dict:
    _identity(repo, fixture, sha)
    record = _existing()
    if record.get("source_sha") != sha or record.get("phase") != "pcp":
        raise g0.GateError("g0_pcp_attempt_identity_drift")
    jid = record.get("job_id")
    if not isinstance(jid, str) or not JOB_ID.fullmatch(jid):
        return {
            "status": "STOP", "phase": "g0d_t01_pcp_status",
            "journal_state": record.get("state"),
            "reason": "g0_pcp_prepare_claimed_without_job_id_manual_reconciliation",
            "model_calls_this_command": 0, "retry_authorized": False,
        }
    row = _http("GET", "/v1/g0-fixture/jobs/" + jid, 30)
    _valid_job(row)
    return {
        "status": "PASS", "phase": "g0d_t01_pcp_status",
        "job_id": jid, "journal_state": record.get("state"),
        "job_status": row["job_status"], "result": row.get("result") or {},
        "model_calls_this_command": 0, "retry_authorized": False,
        "github_delivery_enabled": False,
    }


def execute(repo: Path, fixture: Path, sha: str) -> dict:
    _identity(repo, fixture, sha)
    record = _existing()
    if (
        record.get("state") != "prepared"
        or record.get("source_sha") != sha
        or record.get("phase") != "pcp"
        or record.get("execute_attempted") is not False
    ):
        raise g0.GateError("g0_pcp_not_prepared_or_execute_already_claimed")
    jid = record.get("job_id")
    if not isinstance(jid, str) or not JOB_ID.fullmatch(jid):
        raise g0.GateError("g0_pcp_job_id_missing")
    before = _http("GET", "/v1/g0-fixture/jobs/" + jid, 30)
    _valid_job(before)
    if before["job_status"] != "queued" or before["branch"] != record["branch"]:
        raise g0.GateError("g0_pcp_job_not_pristine_queued")
    record.update({
        "state": "execute_claimed", "execute_attempted": True,
        "execute_started_at": _now(),
    })
    _update(record)
    # Exactly one long-running model execution. If the HTTP/CLI wrapper loses
    # the response or times out, status-only recovery is allowed, NEVER retry.
    result = _http(
        "POST", "/v1/g0-fixture/jobs/" + jid + "/execute", 1880
    )
    _valid_job(result)
    if result["job_status"] != "waiting_human":
        raise g0.GateError("g0_pcp_execution_not_reviewable")
    record.update({
        "state": "executed", "execute_completed_at": _now(),
        "commit": result["result"]["commit"],
    })
    _update(record)
    return {
        "status": "PASS", "phase": "g0d_t01_pcp_executed",
        "job_id": jid, "commit": record["commit"],
        "changed_files": result["result"]["changed_files"],
        "codex_cli_invocations_attempted": 1,
        "model_api_calls_observed": None, "github_delivery_enabled": False,
        "needs_independent_ci_review": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "status", "execute"))
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    repo = Path.home() / "personal-coding-platform-v1"
    fixture = Path.home() / "pcp-g0-fixtures/pcp-g0-drupal-fixture"
    try:
        report = {
            "prepare": prepare, "status": status, "execute": execute
        }[args.mode](repo, fixture, args.expected_sha)
    except (g0.GateError, OSError, ValueError, TypeError, KeyError) as exc:
        report = {
            "status": "STOP", "phase": "g0d_t01_pcp_" + args.mode,
            "reason": str(exc) if isinstance(exc, g0.GateError)
                       else "g0_pcp_operator_validation_error",
            "do_not_retry_blindly": True,
            "ready_to_dispatch_g0d_t01": False,
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
