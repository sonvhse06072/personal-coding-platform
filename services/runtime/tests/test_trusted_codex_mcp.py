"""MCP framing and Codex invocation must not reveal privileged control tokens."""
from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

import pytest

from app.adapters.codex import CodexAdapter
from app.shell import CommandResult
from app import trusted_codex_mcp as mcp


BROKER = {
    "PCP_DEV_BROKER_URL": "http://ddev-executor:8790",
    "PCP_DEV_BROKER_TOKEN": "b" * 48,
    "PCP_DEV_JOB_ID": "a" * 32,
    "PCP_DEV_PROJECT_ID": "pcp-benchmark-synthetic",
    "PCP_DEV_WORKSPACE": "/workspaces/" + "a" * 32,
    "PCP_DEV_SOURCE_SHA": "c" * 40,
}


def test_scoped_broker_uses_stdio_tool_and_never_expands_codex_sandbox(monkeypatch, tmp_path: Path):
    seen = {}

    async def fake_run(argv, *, cwd, timeout, on_stdout_line=None, env=None):
        seen.update(argv=argv, cwd=cwd, timeout=timeout, env=env)
        return CommandResult(
            argv=argv, returncode=0,
            stdout=json.dumps({"type": "turn.completed", "usage": {}}),
            stderr="",
        )

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run)
    outcome = asyncio.run(CodexAdapter("gpt-6-luna", "medium").run(
        workspace=tmp_path, prompt="Add a PHP test", mode="execute",
        timeout=60, developer_broker=BROKER,
    ))
    assert outcome.returncode == 0
    args = seen["argv"]
    assert args[args.index("--sandbox") + 1] == "workspace-write"
    assert "sandbox_workspace_write.network_access=false" in args
    assert 'mcp_servers.pcp_dev.required=true' in args
    assert 'mcp_servers.pcp_dev.enabled_tools=["pcp_run_project_checks"]' in args
    assert "pcp_run_project_checks" in args[-1]
    assert "pcp_dev" in " ".join(args)
    assert "b" * 48 not in " ".join(args)  # bearer never in argv / prompts
    assert seen["env"] == BROKER
    assert "PLATFORM_INTERNAL_TOKEN" not in seen["env"]


def test_plan_and_evaluate_cannot_request_broker(tmp_path: Path):
    for mode in ("plan", "evaluate"):
        with pytest.raises(ValueError, match="never run"):
            asyncio.run(CodexAdapter("gpt-6-luna").run(
                workspace=tmp_path, prompt="Review", mode=mode,
                timeout=10, developer_broker=BROKER,
            ))


def test_normal_codex_without_broker_keeps_no_network_and_no_mcp(monkeypatch, tmp_path):
    observed = []

    async def fake_run(argv, *, cwd, timeout, on_stdout_line=None):
        observed.extend(argv)
        return CommandResult(
            argv=argv, returncode=0,
            stdout=json.dumps({"type": "turn.completed", "usage": {}}),
            stderr="",
        )
    monkeypatch.setattr("app.adapters.codex.run_command", fake_run)
    asyncio.run(CodexAdapter("gpt-6-luna").run(
        workspace=tmp_path, prompt="Normal coding", mode="execute", timeout=10,
    ))
    assert "sandbox_workspace_write.network_access=false" in observed
    assert not any("mcp_servers.pcp_dev" in str(x) for x in observed)


def test_mcp_tools_are_only_approved_named_phases(monkeypatch):
    assert [x["name"] for x in mcp._tools()["tools"]] == [
        "pcp_run_project_checks",
    ]
    monkeypatch.setattr(mcp, "_post_phase", lambda phase: {
        "phase": phase, "passed": True, "commands": [],
    })
    result = mcp._handle({
        "method": "tools/call",
        "params": {
            "name": "pcp_run_project_checks",
            "arguments": {"phase": "targeted_tests"},
        },
    })
    assert result["isError"] is False
    assert "targeted_tests" in result["content"][0]["text"]
    for args in (
        {"phase": "cleanup"},
        {"phase": "full_tests"},
        {"phase": "targeted_tests", "command": "docker ps"},
        {},
    ):
        with pytest.raises(ValueError, match="Invalid phase"):
            mcp._handle({
                "method": "tools/call",
                "params": {
                    "name": "pcp_run_project_checks", "arguments": args,
                },
            })


def test_mcp_initialize_list_and_bounded_jsonrpc(monkeypatch):
    monkeypatch.setattr(mcp, "_post_phase", lambda phase: {
        "phase": phase, "passed": False, "commands": [],
    })
    request = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "pcp_run_project_checks",
            "arguments": {"phase": "static_analysis"},
        }},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "host_exec", "arguments": {"command": "docker ps"},
        }},
    ]
    monkeypatch.setattr(mcp.sys, "stdin", io.StringIO(
        "\n".join(map(json.dumps, request)) + "\n",
    ))
    out = io.StringIO()
    monkeypatch.setattr(mcp.sys, "stdout", out)
    mcp.serve()
    data = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [x["id"] for x in data] == [1, 2, 3, 4]
    assert data[0]["result"]["capabilities"] == {"tools": {}}
    assert data[2]["result"]["isError"] is True
    assert data[3]["error"]["code"] == -32602


def test_scope_rejects_external_hosts_and_redirects(monkeypatch):
    for k, v in BROKER.items():
        monkeypatch.setenv(k, v)
    assert mcp._scope() == BROKER
    monkeypatch.setenv("PCP_DEV_BROKER_URL", "https://github.com")
    with pytest.raises(ValueError):
        mcp._scope()
    monkeypatch.setenv("PCP_DEV_BROKER_URL", BROKER["PCP_DEV_BROKER_URL"])
    assert mcp._NoRedirect().redirect_request(None, None, 0, "", {}, "") is None
