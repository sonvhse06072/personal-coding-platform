#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ALLOWED_CONFIG_KEYS = {
    "schema_version",
    "repository",
    "allowed_actor",
    "control_issue_number",
    "default_branch",
    "pcp_root",
    "marker",
    "max_comment_bytes",
    "state_dir",
}
_ALLOWED_ACTIONS = {
    "status_snapshot",
    "rollout_pcp_exact_main",
    "recover_antigravity_bridge",
}
_SUBPROCESS_SCRUB_ENV = frozenset({
    # Secrets/tokens must never leak into host or DDEV child processes.
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "ACTIONS_RUNTIME_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_URL",
    # Self-hosted runner uses this marker to track/clean descendant processes.
    # A deliberately persistent host bridge must not inherit the job marker.
    "RUNNER_TRACKING_ID",
})
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def load_config(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != _ALLOWED_CONFIG_KEYS:
        raise ValueError("Guardian config keys are not exact")
    if raw.get("schema_version") != 1:
        raise ValueError("Unsupported Guardian config schema")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(raw["repository"])):
        raise ValueError("Invalid Guardian repository")
    if not re.fullmatch(r"[A-Za-z0-9-]{1,100}", str(raw["allowed_actor"])):
        raise ValueError("Invalid Guardian actor")
    if type(raw["control_issue_number"]) is not int or raw["control_issue_number"] < 1:
        raise ValueError("Invalid Guardian control issue")
    if str(raw["default_branch"]) != "main":
        raise ValueError("Guardian v1 supports only reviewed main default branch")
    if str(raw["marker"]) != "<!-- coding-platform:pcp-guardian:v1 -->":
        raise ValueError("Unsupported Guardian marker")
    if type(raw["max_comment_bytes"]) is not int or not 1024 <= raw["max_comment_bytes"] <= 65536:
        raise ValueError("Invalid Guardian comment bound")
    root = Path(os.path.expanduser(str(raw["pcp_root"]))).resolve()
    state_dir = Path(os.path.expanduser(str(raw["state_dir"]))).resolve()
    raw["pcp_root"] = str(root)
    raw["state_dir"] = str(state_dir)
    return raw


def load_event(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Guardian event must be an object")
    return raw


def trusted_comment_identity(
    event: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Validate only the authority envelope, before interpreting command payload."""
    if str(event.get("action") or "") != "created":
        raise ValueError("Guardian accepts created comments only")

    repository = event.get("repository") or {}
    if str(repository.get("full_name") or "") != config["repository"]:
        raise ValueError("Guardian repository identity mismatch")

    issue = event.get("issue") or {}
    if type(issue.get("number")) is not int or issue["number"] != config["control_issue_number"]:
        raise ValueError("Guardian control issue identity mismatch")
    if issue.get("pull_request"):
        raise ValueError("Guardian commands are not accepted on pull requests")
    if str(issue.get("state") or "") != "open":
        raise ValueError("Guardian control issue must remain open")

    comment = event.get("comment") or {}
    comment_id = comment.get("id")
    if type(comment_id) is not int or comment_id < 1:
        raise ValueError("Guardian comment id is invalid")
    actor = (comment.get("user") or {}).get("login")
    if str(actor or "") != config["allowed_actor"]:
        raise ValueError("Guardian comment author is not allowed")
    body = str(comment.get("body") or "")
    return {
        "comment_id": comment_id,
        "body": body,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


def parse_command(event: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    identity = trusted_comment_identity(event, config)
    comment_id = int(identity["comment_id"])
    body = str(identity["body"])
    if len(body.encode("utf-8")) > config["max_comment_bytes"]:
        raise ValueError("Guardian command exceeds byte bound")
    marker = config["marker"]
    if body.count(marker) != 1:
        raise ValueError("Guardian command must contain exactly one versioned marker")
    payload = body.split(marker, 1)[1].strip()
    if not payload:
        raise ValueError("Guardian marker must be followed by one JSON object")

    fence = chr(96) * 3
    if payload.startswith(fence):
        lines = payload.splitlines()
        if (
            len(lines) < 3
            or lines[0].strip() not in {fence, fence + "json"}
            or lines[-1].strip() != fence
        ):
            raise ValueError("Guardian fenced payload is incomplete")
        payload = "\n".join(lines[1:-1]).strip()

    try:
        command = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Guardian payload must be one JSON object") from exc
    if not isinstance(command, dict):
        raise ValueError("Guardian payload must be an object")
    action = str(command.get("action") or "")
    if command.get("schema_version") != 1 or action not in _ALLOWED_ACTIONS:
        raise ValueError("Unsupported Guardian action/schema")

    expected_keys = {"schema_version", "action"}
    if action == "rollout_pcp_exact_main":
        expected_keys.add("expected_main_sha")
    if set(command) != expected_keys:
        raise ValueError("Guardian action fields are not exact")
    if action == "rollout_pcp_exact_main":
        sha = str(command.get("expected_main_sha") or "")
        if not _SHA40.fullmatch(sha):
            raise ValueError("Guardian rollout requires exact lowercase 40-hex SHA")

    return {
        **command,
        "comment_id": comment_id,
        "body_sha256": identity["body_sha256"],
    }


class GitHubClient:
    def __init__(self, token: str, repository: str) -> None:
        if not token:
            raise RuntimeError("GITHUB_TOKEN is unavailable")
        self.token = token
        self.repository = repository
        self.base = "https://api.github.com"

    def request(self, method: str, path: str, payload: Any = None) -> Any:
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "pcp-guardian-v1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"GitHub API HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("GitHub API unavailable") from exc
        return json.loads(raw.decode("utf-8")) if raw else {}

    def default_head(self, branch: str) -> str:
        raw = self.request(
            "GET",
            f"/repos/{self.repository}/git/ref/heads/{branch}",
        )
        return str((raw.get("object") or {}).get("sha") or "")

    def _result_marker(self, comment_id: int) -> str:
        return f"<!-- PCP:GUARDIAN-RESULT:{comment_id} -->"

    def upsert_result(
        self,
        *,
        issue_number: int,
        comment_id: int,
        result: dict[str, Any],
    ) -> None:
        marker = self._result_marker(comment_id)
        body = marker + "\n\n## PCP Guardian result\n\n"
        body += f"Control comment: {comment_id}\n\n"
        body += json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        if len(body.encode("utf-8")) > 60 * 1024:
            raise RuntimeError("Guardian result comment exceeds safe bound")

        matches: list[int] = []
        for page in range(1, 6):
            comments = self.request(
                "GET",
                f"/repos/{self.repository}/issues/{issue_number}/comments"
                f"?per_page=100&page={page}",
            )
            if not isinstance(comments, list) or len(comments) > 100:
                raise RuntimeError("Invalid Guardian result discovery response")
            for raw in comments:
                existing_body = raw.get("body")
                if isinstance(existing_body, str) and marker in existing_body:
                    number = raw.get("id")
                    if type(number) is not int or number < 1:
                        raise RuntimeError("Invalid Guardian result comment id")
                    matches.append(number)
            if len(matches) > 1:
                raise RuntimeError("Multiple Guardian result markers")
            if len(comments) < 100:
                break
        else:
            raise RuntimeError("Guardian result discovery bound exhausted")

        if matches:
            number = matches[0]
            self.request(
                "PATCH",
                f"/repos/{self.repository}/issues/comments/{number}",
                {"body": body},
            )
        else:
            created = self.request(
                "POST",
                f"/repos/{self.repository}/issues/{issue_number}/comments",
                {"body": body},
            )
            number = created.get("id")
            if type(number) is not int or number < 1:
                raise RuntimeError("Guardian result create postcondition failed")

        observed = self.request(
            "GET",
            f"/repos/{self.repository}/issues/comments/{number}",
        )
        if observed.get("body") != body:
            raise RuntimeError("Guardian result comment postcondition mismatch")


class AuditStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        self.lock_handle = None

    def __enter__(self) -> "AuditStore":
        lock = (self.directory / "operation.lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock.close()
            raise RuntimeError("Another Guardian action is already running") from exc
        self.lock_handle = lock
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.lock_handle is not None:
            self.lock_handle.close()
            self.lock_handle = None

    def _path(self, comment_id: int) -> Path:
        return self.directory / f"event-{comment_id}.json"

    def read(self, comment_id: int) -> dict[str, Any] | None:
        path = self._path(comment_id)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None

    def _write(self, comment_id: int, value: dict[str, Any]) -> None:
        path = self._path(comment_id)
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temp, 0o600)
        temp.replace(path)

    def claim(self, command: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        comment_id = int(command["comment_id"])
        existing = self.read(comment_id)
        if existing is not None:
            if existing.get("body_sha256") != command["body_sha256"]:
                raise RuntimeError("Guardian comment identity was reused with changed content")
            return False, existing
        row = {
            "schema_version": 1,
            "comment_id": comment_id,
            "body_sha256": command["body_sha256"],
            "action": command["action"],
            "expected_main_sha": command.get("expected_main_sha"),
            "status": "dispatching",
            "created_at": utcnow(),
            "updated_at": utcnow(),
            "result": None,
        }
        self._write(comment_id, row)
        return True, row

    def finish(
        self,
        command: dict[str, Any],
        *,
        status: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        row = self.read(int(command["comment_id"]))
        if row is None or row.get("status") != "dispatching":
            raise RuntimeError("Guardian audit terminal transition rejected")
        row["status"] = status
        row["result"] = result
        row["updated_at"] = utcnow()
        self._write(int(command["comment_id"]), row)
        return row


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 30,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    # Guardian/Actions credentials and self-hosted runner process-tracking
    # metadata are never inherited by host/DDEV/service commands. One reviewed
    # git-fetch call may opt GITHUB_TOKEN back in through a secret-free
    # GIT_ASKPASS helper. RUNNER_TRACKING_ID is never re-added, so a deliberately
    # persistent host daemon is not collected when the workflow job exits.
    for key in _SUBPROCESS_SCRUB_ENV:
        merged_env.pop(key, None)
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=merged_env,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed safely: {Path(args[0]).name} exit {proc.returncode}"
        )
    return proc


def _json_command(
    args: list[str],
    *,
    cwd: Path,
    timeout: int = 30,
) -> dict[str, Any]:
    proc = _run(args, cwd=cwd, timeout=timeout)
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Health command returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Health command returned non-object JSON")
    return value


def _canonical_origin(value: str) -> str | None:
    value = value.strip()
    patterns = [
        r"^https://github\.com/([^/]+/[^/]+?)(?:\.git)?$",
        r"^git@github\.com:([^/]+/[^/]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/([^/]+/[^/]+?)(?:\.git)?$",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, value)
        if match:
            return match.group(1)
    return None


def _version_from_source(path: Path, variable: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(
        rf"^{re.escape(variable)}\s*=\s*[\"']([^\"']+)[\"']\s*$",
        text,
        flags=re.MULTILINE,
    )
    if not match:
        raise RuntimeError(f"Target source lacks {variable}")
    return match.group(1)


class GuardianHost:
    def __init__(self, config: dict[str, Any], checkout: Path) -> None:
        self.config = config
        self.root = Path(config["pcp_root"]).resolve()
        self.checkout = checkout.resolve()

    def _git(self, *args: str, check: bool = True) -> str:
        return _run(
            ["git", "-C", str(self.root), *args],
            timeout=120,
            check=check,
            env={"GIT_TERMINAL_PROMPT": "0"},
        ).stdout.strip()

    def _github_fetch_auth(self) -> tuple[Path, dict[str, str]]:
        """Create one secret-free askpass helper and scope token to git fetch only."""
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            raise RuntimeError("GITHUB_TOKEN is unavailable for exact GitHub fetch")
        directory = Path(self.config["state_dir"])
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        askpass = directory / "git-askpass.sh"
        content = (
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  *Username*) printf '%s\\n' 'x-access-token' ;;\n"
            "  *Password*) printf '%s\\n' \"$GITHUB_TOKEN\" ;;\n"
            "  *) exit 1 ;;\n"
            "esac\n"
        )
        askpass.write_text(content, encoding="utf-8")
        os.chmod(askpass, 0o700)
        return askpass, {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": str(askpass),
            "GITHUB_TOKEN": token,
        }

    def local_git(self) -> dict[str, Any]:
        if not self.root.is_dir():
            raise RuntimeError("Configured PCP root is unavailable")
        origin = self._git("remote", "get-url", "origin")
        origin_repo = _canonical_origin(origin)
        if origin_repo != self.config["repository"]:
            raise RuntimeError("Local PCP origin does not match Guardian repository")
        return {
            "branch": self._git("branch", "--show-current", check=False) or None,
            "head": self._git("rev-parse", "HEAD"),
            "clean": not bool(self._git("status", "--porcelain", check=False)),
            "origin_repository": origin_repo,
            "origin_main_cached": (
                self._git(
                    "rev-parse",
                    f"refs/remotes/origin/{self.config['default_branch']}",
                    check=False,
                )
                or None
            ),
        }

    def _runtime_active_count(self) -> dict[str, Any]:
        url = "https://personal-coding-platform.ddev.site:8788/v1/jobs/active-count"
        shell = (
            'curl -fsS --max-time 15 '
            '-H "Authorization: Bearer $RUNTIME_API_TOKEN" "$1"'
        )
        proc = _run(
            [
                "bash",
                str(self.root / "scripts/with-host-secrets.sh"),
                "bash",
                "-lc",
                shell,
                "_",
                url,
            ],
            cwd=self.root,
            timeout=30,
        )
        raw = json.loads(proc.stdout)
        count = raw.get("active_engineering_jobs")
        if type(count) is not int or count < 0:
            raise RuntimeError("Runtime active count is invalid")
        return {"active_engineering_jobs": count}

    def _runtime_health(self) -> dict[str, Any]:
        raw = _json_command(
            [
                "ddev",
                "exec",
                "-s",
                "coding-runtime",
                "curl",
                "-fsS",
                "http://127.0.0.1:8787/health",
            ],
            cwd=self.root,
        )
        return {
            key: raw.get(key)
            for key in ("status", "service", "version", "router", "executor")
        }

    def _router_health(self) -> dict[str, Any]:
        raw = _json_command(
            [
                "ddev",
                "exec",
                "-s",
                "router",
                "curl",
                "-fsS",
                "http://127.0.0.1:8090/health",
            ],
            cwd=self.root,
        )
        return {
            key: raw.get(key)
            for key in ("status", "service", "version")
            if raw.get(key) is not None
        }

    def _executor_health(self) -> dict[str, Any]:
        raw = _json_command(
            [
                "ddev",
                "exec",
                "-s",
                "ddev-executor",
                "curl",
                "-fsS",
                "http://127.0.0.1:8790/health",
            ],
            cwd=self.root,
        )
        active = raw.get("active_jobs")
        if type(active) is not int or active < 0:
            raise RuntimeError("Executor active job count is invalid")
        return {
            "status": raw.get("status"),
            "service": raw.get("service"),
            "version": raw.get("version"),
            "active_jobs": active,
        }

    def _antigravity_health(self) -> dict[str, Any]:
        proc = _run(
            [
                "bash",
                str(self.root / "scripts/with-host-secrets.sh"),
                "bash",
                str(self.root / "scripts/antigravity-bridge.sh"),
                "status",
            ],
            cwd=self.root,
            timeout=30,
            check=False,
        )
        try:
            raw = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Antigravity status returned invalid JSON") from exc
        if not isinstance(raw, dict):
            raise RuntimeError("Antigravity status returned non-object JSON")

        status = str(raw.get("status") or "")
        if status == "down":
            if proc.returncode == 0:
                raise RuntimeError("Antigravity down status returned success unexpectedly")
            return {
                "status": "down",
                "service": raw.get("service"),
            }
        if proc.returncode != 0:
            raise RuntimeError("Antigravity status command failed ambiguously")

        active = raw.get("active_runs")
        pending = raw.get("pending_cancellations")
        if type(active) is not int or type(pending) is not int:
            raise RuntimeError("Antigravity activity counters are invalid")
        return {
            "status": status,
            "service": raw.get("service"),
            "version": raw.get("version"),
            "active_runs": active,
            "pending_cancellations": pending,
            "safe_settings": raw.get("safe_settings"),
        }

    def _n8n_health(self) -> dict[str, Any]:
        code = (
            'fetch("http://127.0.0.1:5678/healthz")'
            '.then(async r=>{if(!r.ok)process.exit(1);console.log("ok")})'
            '.catch(()=>process.exit(1))'
        )
        proc = _run(
            ["ddev", "exec", "-s", "n8n", "node", "-e", code],
            cwd=self.root,
            timeout=30,
            check=False,
        )
        return {"ok": proc.returncode == 0 and proc.stdout.strip() == "ok"}

    def _credential_boundary(self) -> dict[str, Any]:
        proc = _run(
            ["bash", str(self.root / "scripts/service-secret-status.sh")],
            cwd=self.root,
            timeout=30,
            check=False,
        )
        return {"ok": proc.returncode == 0}

    @staticmethod
    def _probe(callable_obj) -> dict[str, Any]:
        try:
            value = callable_obj()
            return {"reachable": True, **value}
        except Exception as exc:
            return {
                "reachable": False,
                "error_type": type(exc).__name__,
            }

    def snapshot(self) -> dict[str, Any]:
        git_state = self._probe(self.local_git)
        return {
            "local_git": git_state,
            "runtime": self._probe(self._runtime_health),
            "active_engineering": self._probe(self._runtime_active_count),
            "router": self._probe(self._router_health),
            "executor": self._probe(self._executor_health),
            "antigravity": self._probe(self._antigravity_health),
            "n8n": self._probe(self._n8n_health),
            "credential_boundary": self._probe(self._credential_boundary),
        }

    @staticmethod
    def _require_quiescent(snapshot: dict[str, Any]) -> None:
        active = snapshot["active_engineering"]
        executor = snapshot["executor"]
        antigravity = snapshot["antigravity"]
        if not active.get("reachable"):
            raise RuntimeError("Runtime active-work state is unavailable")
        if active.get("active_engineering_jobs") != 0:
            raise RuntimeError("Runtime has active engineering work")
        if not executor.get("reachable") or executor.get("active_jobs") != 0:
            raise RuntimeError("DDEV executor is not provably idle")
        if (
            not antigravity.get("reachable")
            or antigravity.get("active_runs") != 0
            or antigravity.get("pending_cancellations") != 0
        ):
            raise RuntimeError("Antigravity bridge is not provably idle")

    @staticmethod
    def _post_rollout_ready(
        snapshot: dict[str, Any],
        target: dict[str, str],
    ) -> bool:
        runtime = snapshot["runtime"]
        router = snapshot["router"]
        executor = snapshot["executor"]
        antigravity = snapshot["antigravity"]
        n8n = snapshot["n8n"]
        credential = snapshot["credential_boundary"]
        active = snapshot["active_engineering"]
        return bool(
            runtime.get("reachable")
            and runtime.get("status") == "ok"
            and runtime.get("version") == target["runtime"]
            and router.get("reachable")
            and router.get("status") == "ok"
            and executor.get("reachable")
            and executor.get("status") == "ok"
            and executor.get("version") == target["executor"]
            and executor.get("active_jobs") == 0
            and antigravity.get("reachable")
            and antigravity.get("status") == "ok"
            and antigravity.get("safe_settings") is True
            and antigravity.get("active_runs") == 0
            and antigravity.get("pending_cancellations") == 0
            and active.get("reachable")
            and active.get("active_engineering_jobs") == 0
            and n8n.get("reachable")
            and n8n.get("ok") is True
            and credential.get("reachable")
            and credential.get("ok") is True
        )

    def _checkout_head(self) -> str:
        return _run(
            ["git", "-C", str(self.checkout), "rev-parse", "HEAD"],
            timeout=20,
        ).stdout.strip()

    def _target_versions(self) -> dict[str, str]:
        return {
            "runtime": _version_from_source(
                self.checkout / "services/runtime/app/main.py",
                "RUNTIME_VERSION",
            ),
            "executor": _version_from_source(
                self.checkout / "services/ddev-executor/app/main.py",
                "DDEV_EXECUTOR_VERSION",
            ),
        }

    @staticmethod
    def _require_bridge_recovery_preconditions(
        snapshot: dict[str, Any],
    ) -> None:
        local = snapshot["local_git"]
        runtime = snapshot["runtime"]
        active = snapshot["active_engineering"]
        executor = snapshot["executor"]
        credential = snapshot["credential_boundary"]
        antigravity = snapshot["antigravity"]

        if (
            not local.get("reachable")
            or local.get("branch") != "main"
            or local.get("clean") is not True
        ):
            raise RuntimeError("Local PCP main is not clean/reachable for bridge recovery")
        if not runtime.get("reachable") or runtime.get("status") != "ok":
            raise RuntimeError("Runtime is not healthy for bridge recovery")
        if (
            not active.get("reachable")
            or active.get("active_engineering_jobs") != 0
        ):
            raise RuntimeError("Runtime is not provably idle for bridge recovery")
        if (
            not executor.get("reachable")
            or executor.get("status") != "ok"
            or executor.get("active_jobs") != 0
        ):
            raise RuntimeError("DDEV executor is not provably idle for bridge recovery")
        if (
            not credential.get("reachable")
            or credential.get("ok") is not True
        ):
            raise RuntimeError("Credential boundary is not healthy for bridge recovery")

        if not antigravity.get("reachable"):
            raise RuntimeError("Antigravity status is ambiguous")
        status = str(antigravity.get("status") or "")
        if status == "ok":
            if (
                antigravity.get("safe_settings") is True
                and antigravity.get("active_runs") == 0
                and antigravity.get("pending_cancellations") == 0
            ):
                return
            raise RuntimeError("Running Antigravity bridge is not safe/idle")
        if status != "down":
            raise RuntimeError("Antigravity bridge is neither healthy nor explicitly down")

    def _require_reviewed_bridge_helpers(self) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for relative in (
            "scripts/with-host-secrets.sh",
            "scripts/antigravity-bridge.sh",
        ):
            local = self.root / relative
            reviewed = self.checkout / relative
            if not local.is_file() or not reviewed.is_file():
                raise RuntimeError("Bridge recovery helper is unavailable")
            local_bytes = local.read_bytes()
            reviewed_bytes = reviewed.read_bytes()
            if local_bytes != reviewed_bytes:
                raise RuntimeError(
                    f"Local bridge recovery helper differs from reviewed checkout: {relative}"
                )
            hashes[relative] = hashlib.sha256(reviewed_bytes).hexdigest()
        return hashes

    def recover_antigravity_bridge(self) -> dict[str, Any]:
        pre = self.snapshot()
        self._require_bridge_recovery_preconditions(pre)
        if (
            pre["local_git"].get("origin_repository")
            != self.config["repository"]
        ):
            raise RuntimeError(
                "Local PCP origin does not match reviewed Guardian repository"
            )
        antigravity = pre["antigravity"]

        if antigravity.get("status") == "ok":
            return {
                "status": "executed",
                "reused": True,
                "pre": pre,
                "post": pre,
            }

        helper_hashes = self._require_reviewed_bridge_helpers()
        _run(
            [
                "bash",
                str(self.root / "scripts/with-host-secrets.sh"),
                "bash",
                str(self.root / "scripts/antigravity-bridge.sh"),
                "start",
            ],
            cwd=self.root,
            timeout=60,
        )

        post_antigravity: dict[str, Any] | None = None
        for _ in range(30):
            try:
                post_antigravity = self._antigravity_health()
            except Exception:
                post_antigravity = None
            if (
                post_antigravity
                and post_antigravity.get("status") == "ok"
                and post_antigravity.get("safe_settings") is True
                and post_antigravity.get("active_runs") == 0
                and post_antigravity.get("pending_cancellations") == 0
            ):
                break
            time.sleep(0.5)

        if (
            not post_antigravity
            or post_antigravity.get("status") != "ok"
            or post_antigravity.get("safe_settings") is not True
            or post_antigravity.get("active_runs") != 0
            or post_antigravity.get("pending_cancellations") != 0
        ):
            raise RuntimeError(
                "Antigravity bridge did not become safe/idle after bounded start"
            )

        return {
            "status": "executed",
            "reused": False,
            "helper_sha256": helper_hashes,
            "pre": pre,
            "post": {
                "antigravity": {
                    "reachable": True,
                    **post_antigravity,
                }
            },
        }

    def rollout(self, expected_sha: str, github_head: str) -> dict[str, Any]:
        if expected_sha != github_head:
            raise RuntimeError("Guardian rollout SHA is stale against GitHub main")
        if self._checkout_head() != expected_sha:
            raise RuntimeError("Guardian workflow checkout is not exact expected main")

        pre = self.snapshot()
        self._require_quiescent(pre)
        local = pre["local_git"]
        if not local.get("reachable"):
            raise RuntimeError("Local PCP git state is unavailable")
        if local.get("branch") != self.config["default_branch"]:
            raise RuntimeError("Local PCP is not on configured main branch")
        if local.get("clean") is not True:
            raise RuntimeError("Local PCP worktree is dirty")

        old_head = str(local.get("head") or "")
        reviewed_remote = (
            f"https://github.com/{self.config['repository']}.git"
        )
        askpass, fetch_env = self._github_fetch_auth()
        try:
            _run(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-C",
                    str(self.root),
                    "fetch",
                    "--no-tags",
                    reviewed_remote,
                    f"+refs/heads/{self.config['default_branch']}:"
                    f"refs/remotes/origin/{self.config['default_branch']}",
                ],
                timeout=180,
                env=fetch_env,
            )
        finally:
            askpass.unlink(missing_ok=True)
        remote_head = self._git(
            "rev-parse",
            f"refs/remotes/origin/{self.config['default_branch']}",
        )
        if remote_head != expected_sha:
            raise RuntimeError("Fetched origin/main does not match expected SHA")
        ancestry = _run(
            [
                "git",
                "-C",
                str(self.root),
                "merge-base",
                "--is-ancestor",
                old_head,
                expected_sha,
            ],
            check=False,
        )
        if ancestry.returncode != 0:
            raise RuntimeError("Local PCP main cannot fast-forward to expected SHA")

        if old_head != expected_sha:
            _run(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-C",
                    str(self.root),
                    "merge",
                    "--ff-only",
                    expected_sha,
                ],
                timeout=60,
            )
        updated = self.local_git()
        if updated["head"] != expected_sha or updated["clean"] is not True:
            raise RuntimeError("Local PCP ff-only postcondition failed")

        target = self._target_versions()
        _run(["ddev", "restart", "-y"], cwd=self.root, timeout=900)

        post: dict[str, Any] | None = None
        for _ in range(60):
            post = self.snapshot()
            if self._post_rollout_ready(post, target):
                break
            time.sleep(2)
        assert post is not None

        self._require_quiescent(post)
        if not self._post_rollout_ready(post, target):
            raise RuntimeError(
                "PCP services did not reach all reviewed rollout postconditions"
            )
        if post["local_git"].get("head") != expected_sha:
            raise RuntimeError("Local PCP HEAD drifted after rollout")

        return {
            "status": "executed",
            "expected_main_sha": expected_sha,
            "old_head": old_head,
            "new_head": expected_sha,
            "target_versions": target,
            "pre": pre,
            "post": post,
        }


def execute_action(
    command: dict[str, Any],
    *,
    config: dict[str, Any],
    github: GitHubClient,
    host: GuardianHost,
) -> dict[str, Any]:
    github_head = github.default_head(config["default_branch"])
    if command["action"] == "status_snapshot":
        return {
            "status": "executed",
            "action": "status_snapshot",
            "github_main": github_head,
            "snapshot": host.snapshot(),
        }
    if command["action"] == "rollout_pcp_exact_main":
        return {
            "action": "rollout_pcp_exact_main",
            **host.rollout(str(command["expected_main_sha"]), github_head),
        }
    if command["action"] == "recover_antigravity_bridge":
        return {
            "action": "recover_antigravity_bridge",
            "github_main": github_head,
            **host.recover_antigravity_bridge(),
        }
    raise RuntimeError("Unsupported Guardian action")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config = load_config(Path(args.config).resolve())
    event = load_event(Path(args.event).resolve())
    # Wrong actor/repository/issue identities receive no response. The workflow
    # also prefilters them, while this check is the defense-in-depth authority.
    identity = trusted_comment_identity(event, config)
    token = os.getenv("GITHUB_TOKEN", "").strip()
    github = GitHubClient(token, config["repository"])
    state_dir = Path(config["state_dir"])

    try:
        command = parse_command(event, config)
    except Exception as exc:
        rejected = {
            "comment_id": int(identity["comment_id"]),
            "body_sha256": str(identity["body_sha256"]),
            "action": "invalid",
        }
        result = {
            "status": "rejected",
            "action": "invalid",
            "comment_id": int(identity["comment_id"]),
            "error_type": type(exc).__name__,
            "message": _bounded(str(exc), 500),
        }
        with AuditStore(state_dir) as audit:
            fresh, row = audit.claim(rejected)
            if fresh:
                audit.finish(rejected, status="rejected", result=result)
            elif isinstance(row.get("result"), dict):
                result = dict(row["result"])
        github.upsert_result(
            issue_number=config["control_issue_number"],
            comment_id=int(identity["comment_id"]),
            result=result,
        )
        return 20

    checkout = Path(os.getenv("GITHUB_WORKSPACE", os.getcwd())).resolve()
    host = GuardianHost(config, checkout)

    with AuditStore(state_dir) as audit:
        fresh, row = audit.claim(command)
        if not fresh:
            if row.get("status") == "dispatching":
                replay = {
                    "status": "uncertain",
                    "action": row.get("action"),
                    "comment_id": command["comment_id"],
                    "message": (
                        "Prior Guardian invocation did not reach terminal audit; "
                        "mutation is not replayed."
                    ),
                }
                github.upsert_result(
                    issue_number=config["control_issue_number"],
                    comment_id=command["comment_id"],
                    result=replay,
                )
                return 20
            stored = row.get("result")
            if not isinstance(stored, dict):
                stored = {
                    "status": str(row.get("status") or "unknown"),
                    "action": row.get("action"),
                    "comment_id": command["comment_id"],
                }
            github.upsert_result(
                issue_number=config["control_issue_number"],
                comment_id=command["comment_id"],
                result=stored,
            )
            return 0 if row.get("status") == "executed" else 20

        try:
            result = execute_action(
                command,
                config=config,
                github=github,
                host=host,
            )
        except Exception as exc:
            result = {
                "status": "failed",
                "action": command["action"],
                "comment_id": command["comment_id"],
                "error_type": type(exc).__name__,
                "message": _bounded(str(exc), 500),
            }
            terminal = "failed"
        else:
            result["comment_id"] = command["comment_id"]
            terminal = "executed"

        audit.finish(command, status=terminal, result=result)
        github.upsert_result(
            issue_number=config["control_issue_number"],
            comment_id=command["comment_id"],
            result=result,
        )
        return 0 if terminal == "executed" else 20


if __name__ == "__main__":
    sys.exit(main())
