"""Minimal stdio MCP tool for a single scoped G1 Codex development turn.

The model gets only a *job-specific phase capability*, never Runtime/Router/
GitHub/Executor control tokens or a host command. All executable commands are
chosen from the Executor's approved fixture configuration, not model arguments.
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

_PHASES = ("targeted_tests", "static_analysis", "frontend_quality")
_ENV = (
    "PCP_DEV_BROKER_URL", "PCP_DEV_BROKER_TOKEN", "PCP_DEV_JOB_ID",
    "PCP_DEV_PROJECT_ID", "PCP_DEV_WORKSPACE", "PCP_DEV_SOURCE_SHA",
)
_JOB = re.compile(r"[a-f0-9]{32}")
_SHA = re.compile(r"[a-f0-9]{40}")
_PROJECT = re.compile(r"pcp-benchmark-[a-z0-9-]{2,80}")
_VERSION = "2025-06-18"
_MAX_INPUT = 65536


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _scope() -> dict[str, str]:
    values = {k: os.environ.get(k, "") for k in _ENV}
    if not all(values.values()):
        raise ValueError("Scoped phase broker is not configured")
    url = urlsplit(values["PCP_DEV_BROKER_URL"])
    if not (
        url.scheme == "http" and url.hostname in ("ddev-executor", "pcp-dev-executor")
        and url.port == 8790
        and not (url.username or url.password or url.path or url.query or url.fragment)
        and re.fullmatch(r"[A-Za-z0-9_-]{40,128}", values["PCP_DEV_BROKER_TOKEN"])
        and _JOB.fullmatch(values["PCP_DEV_JOB_ID"])
        and _PROJECT.fullmatch(values["PCP_DEV_PROJECT_ID"])
        and _SHA.fullmatch(values["PCP_DEV_SOURCE_SHA"])
        and values["PCP_DEV_WORKSPACE"].endswith("/" + values["PCP_DEV_JOB_ID"])
    ):
        raise ValueError("Scoped phase broker identity invalid")
    return values


def _post_phase(phase: str) -> dict:
    scope = _scope()
    if phase not in _PHASES:
        raise ValueError("Only approved phase names are allowed")
    payload = {
        "phase": phase,
        "job_id": scope["PCP_DEV_JOB_ID"],
        "project_id": scope["PCP_DEV_PROJECT_ID"],
        "workspace": scope["PCP_DEV_WORKSPACE"],
        "source_commit": scope["PCP_DEV_SOURCE_SHA"],
    }
    url = scope["PCP_DEV_BROKER_URL"] + "/v1/codex-dev/phase"
    req = Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + scope["PCP_DEV_BROKER_TOKEN"],
        },
        method="POST",
    )
    try:
        with build_opener(_NoRedirect()).open(req, timeout=180) as response:
            if response.status != 200:
                raise ValueError("Executor rejected scoped phase")
            raw = response.read(20001)
            if len(raw) > 20000:
                raise ValueError("Executor response exceeded bounded output")
            result = json.loads(raw)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        # Never print exception object: headers/credentials might be embedded.
        raise ValueError("Scoped Executor phase unavailable or denied") from None
    if not isinstance(result, dict) or result.get("phase") != phase:
        raise ValueError("Executor phase response invalid")
    return result


def _tools() -> dict:
    return {"tools": [{
        "name": "pcp_run_project_checks",
        "description": (
            "Run one approved fixture build/test phase through PCP's scoped "
            "DDEV Executor. No arbitrary shell, Docker, GitHub or host actions. "
            "Use targeted_tests for PHP/Unit, static_analysis for PHPCS, "
            "frontend_quality for project-defined Node build/preview checks."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "phase": {"type": "string", "enum": list(_PHASES)},
            },
            "required": ["phase"],
            "additionalProperties": False,
        },
    }]}


def _handle(message: dict) -> dict | None:
    method = message.get("method")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {
            "protocolVersion": _VERSION,
            "serverInfo": {"name": "pcp-fixture-dev", "version": "0.1.0"},
            "capabilities": {"tools": {}},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return _tools()
    if method == "tools/call":
        params = message.get("params")
        if not isinstance(params, dict) or params.get("name") != "pcp_run_project_checks":
            raise ValueError("Unknown MCP tool")
        args = params.get("arguments")
        if (
            not isinstance(args, dict) or set(args) != {"phase"}
            or args.get("phase") not in _PHASES
        ):
            raise ValueError("Invalid phase tool arguments")
        result = _post_phase(args["phase"])
        return {
            "content": [{
                "type": "text",
                "text": json.dumps(result, ensure_ascii=False, sort_keys=True)[:18000],
            }],
            "isError": result.get("passed") is not True,
        }
    raise ValueError("Unknown MCP method")


def serve() -> None:
    for line in sys.stdin:
        if len(line) > _MAX_INPUT:
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                continue
        except (ValueError, UnicodeError):
            continue
        identity = message.get("id")
        try:
            result = _handle(message)
            if result is None or identity is None:
                continue
            response = {"jsonrpc": "2.0", "id": identity, "result": result}
        except (ValueError, TypeError):
            if identity is None:
                continue
            response = {
                "jsonrpc": "2.0", "id": identity,
                "error": {"code": -32602, "message": "Scoped tool call denied"},
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    serve()
