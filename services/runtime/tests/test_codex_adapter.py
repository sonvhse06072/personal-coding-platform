import asyncio
import json
from pathlib import Path

import pytest

from app.adapters.base import AgentAdapter
from app.adapters.codex import CodexAdapter
from app.developer_stream import bind_developer_sink
from app.shell import CommandResult, CommandTimeoutError


def _event(payload: dict) -> str:
    return json.dumps(payload)


def _assert_bounded_unattended_policy(argv: list[str], *, sandbox: str) -> None:
    assert argv[argv.index("--sandbox") + 1] == sandbox
    assert 'approval_policy="never"' in argv
    assert "features.memories=false" in argv
    assert "memories.use_memories=false" in argv
    assert "memories.generate_memories=false" in argv
    assert "danger-full-access" not in argv
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv


def test_invocation_capabilities_default_to_local_listener_available():
    assert AgentAdapter("test-model").invocation_capabilities("execute").local_listener is True


def test_codex_invocation_capabilities_are_explicit_by_mode():
    adapter = CodexAdapter("gpt-5.6-sol")

    for mode in ("execute", "repair"):
        capabilities = adapter.invocation_capabilities(mode)
        assert capabilities.local_listener is False
        assert capabilities.reason == "codex_workspace_network_disabled"

    evaluation = adapter.invocation_capabilities("evaluate")
    assert evaluation.local_listener is False
    assert evaluation.reason == "codex_read_only_evaluation"

    assert adapter.invocation_capabilities("plan").local_listener is True


def test_codex_turn_completed_is_authoritative_over_transient_rate_limit_text(monkeypatch, tmp_path: Path):
    stdout = "\n".join([
        _event({"type": "turn.started"}),
        _event({"type": "rate_limits.updated", "message": "rate limit telemetry refreshed"}),
        _event({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "Implemented the requested test."},
        }),
        _event({
            "type": "turn.completed",
            "usage": {"input_tokens": 513294, "output_tokens": 6475},
        }),
    ])
    captured = {}

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
        captured["argv"] = argv
        return CommandResult(argv=argv, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    run = asyncio.run(
        CodexAdapter("gpt-5.6-sol", "medium").run(
            workspace=tmp_path,
            prompt="add a test",
            mode="execute",
            timeout=30,
        )
    )

    assert run.returncode == 0
    assert run.failure_kind is None
    assert not run.provider_failed
    assert run.output == "Implemented the requested test."
    assert run.usage["input_tokens"] == 513294
    assert run.usage["output_tokens"] == 6475
    assert "--model" in captured["argv"]
    assert "gpt-5.6-sol" in captured["argv"]
    assert "--config" in captured["argv"]
    assert 'model_reasoning_effort="medium"' in captured["argv"]
    _assert_bounded_unattended_policy(captured["argv"], sandbox="workspace-write")
    assert "sandbox_workspace_write.network_access=false" in captured["argv"]


def test_codex_output_uses_only_last_agent_message(monkeypatch, tmp_path: Path):
    progress = "Inspecting the approved baseline before planning."
    final_json = json.dumps({
        "scope_assessment": "in_scope",
        "summary": "The ticket is routine and bounded.",
        "work_orders": [],
        "decision_boundaries": [],
    })
    stdout = "\n".join([
        _event({"type": "turn.started"}),
        _event({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": progress},
        }),
        _event({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": final_json},
        }),
        _event({"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 50}}),
    ])
    captured: dict[str, object] = {}

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
        output_index = argv.index("--output-last-message")
        output_path = Path(argv[output_index + 1])
        captured["path"] = output_path
        captured["argv"] = argv
        assert output_path.exists()
        output_path.write_text(final_json, encoding="utf-8")
        return CommandResult(argv=argv, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    run = asyncio.run(
        CodexAdapter("gpt-5.6-terra", "low").run(
            workspace=tmp_path,
            prompt="return one JSON object",
            mode="plan",
            timeout=30,
        )
    )

    assert run.returncode == 0
    assert run.output == final_json
    assert progress not in run.output
    raw_events = [json.loads(line) for line in run.raw.splitlines()]
    raw_messages = [
        event["item"]["text"]
        for event in raw_events
        if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") == "agent_message"
    ]
    assert raw_messages == [progress, final_json]
    assert "--output-last-message" in captured["argv"]
    _assert_bounded_unattended_policy(captured["argv"], sandbox="read-only")
    assert not captured["path"].exists()


def test_codex_last_message_tempfile_is_removed_on_cancellation(monkeypatch, tmp_path: Path):
    captured: dict[str, Path] = {}

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
        output_index = argv.index("--output-last-message")
        output_path = Path(argv[output_index + 1])
        captured["path"] = output_path
        output_path.write_text("partial", encoding="utf-8")
        raise asyncio.CancelledError()

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            CodexAdapter("gpt-5.6-terra").run(
                workspace=tmp_path,
                prompt="plan",
                mode="plan",
                timeout=30,
            )
        )

    assert not captured["path"].exists()


def test_codex_read_only_modes_are_noninteractive_without_write_network_override(monkeypatch, tmp_path: Path):
    captured: list[list[str]] = []

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
        captured.append(argv)
        return CommandResult(
            argv=argv,
            returncode=0,
            stdout=_event({"type": "turn.completed", "usage": {}}),
            stderr="",
        )

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    for mode in ("plan", "evaluate"):
        asyncio.run(
            CodexAdapter("gpt-5.6-luna").run(
                workspace=tmp_path,
                prompt="inspect",
                mode=mode,
                timeout=30,
            )
        )

    assert len(captured) == 2
    for argv in captured:
        _assert_bounded_unattended_policy(argv, sandbox="read-only")
        assert "sandbox_workspace_write.network_access=false" not in argv
        assert not any(str(arg).startswith("model_reasoning_effort=") for arg in argv)


def test_codex_turn_failed_still_classifies_provider_failure(monkeypatch, tmp_path: Path):
    stdout = "\n".join([
        _event({"type": "turn.started"}),
        _event({
            "type": "turn.failed",
            "error": {"message": "Too many requests: rate limit exceeded"},
        }),
    ])

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
        return CommandResult(argv=argv, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    run = asyncio.run(
        CodexAdapter("gpt-5.6-sol").run(
            workspace=tmp_path,
            prompt="add a test",
            mode="execute",
            timeout=30,
        )
    )

    assert run.returncode != 0
    assert run.failure_kind == "rate_limited"
    assert run.provider_failed


def test_codex_plain_cli_failure_without_terminal_json_is_still_classified(monkeypatch, tmp_path: Path):
    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
        return CommandResult(
            argv=argv,
            returncode=1,
            stdout="",
            stderr="You have reached your usage limit. Try again later.",
        )

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    run = asyncio.run(
        CodexAdapter("gpt-5.6-sol").run(
            workspace=tmp_path,
            prompt="add a test",
            mode="execute",
            timeout=30,
        )
    )

    assert run.returncode == 1
    assert run.failure_kind == "quota_exhausted"
    assert run.provider_failed


def test_codex_emits_provider_neutral_activity_during_stdout_stream(monkeypatch, tmp_path: Path):
    line = _event({
        "type": "item.completed",
        "item": {"type": "agent_message", "text": "Editing the recovery runner."},
    })
    terminal = _event({"type": "turn.completed", "usage": {}})
    seen: list[dict] = []

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
        assert on_stdout_line is not None
        on_stdout_line(line)
        return CommandResult(argv=argv, returncode=0, stdout=f"{line}\n{terminal}", stderr="")

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    bind_developer_sink(seen.append)
    try:
        asyncio.run(
            CodexAdapter("gpt-5.6-terra").run(
                workspace=tmp_path,
                prompt="implement",
                mode="execute",
                timeout=30,
            )
        )
    finally:
        bind_developer_sink(None)

    messages = [event for event in seen if event["event_type"] == "developer_message"]
    assert len(messages) == 1
    assert messages[0]["data"]["text"] == "Editing the recovery runner."
    assert messages[0]["data"]["provider"] == "openai"
    assert messages[0]["data"]["adapter"] == "codex_cli"
    assert messages[0]["data"]["model"] == "gpt-5.6-terra"
    lifecycle = [event["data"].get("status") for event in seen if event["event_type"] == "developer_step"]
    assert lifecycle == ["started", "completed"]

def test_codex_timeout_returns_structured_failure_and_removes_last_message_file(monkeypatch, tmp_path: Path):
    captured: dict[str, Path] = {}
    seen: list[dict] = []
    partial = _event({
        "type": "item.completed",
        "item": {"type": "agent_message", "text": "Partial progress before timeout."},
    })

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
        output_index = argv.index("--output-last-message")
        output_path = Path(argv[output_index + 1])
        captured["path"] = output_path
        assert output_path.exists()
        assert on_stdout_line is not None
        on_stdout_line(partial)
        raise CommandTimeoutError(
            timeout=timeout,
            argv=argv,
            stdout=partial + "\n",
        )

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    bind_developer_sink(seen.append)
    try:
        run = asyncio.run(
            CodexAdapter("gpt-5.6-terra").run(
                workspace=tmp_path,
                prompt="implement",
                mode="execute",
                timeout=30,
            )
        )
    finally:
        bind_developer_sink(None)

    assert run.returncode == 124
    assert run.failure_kind == "timeout"
    assert run.failure_message == "Command timed out after 30s"
    assert run.provider_failed is True
    assert run.output == "Partial progress before timeout."
    assert not captured["path"].exists()
    lifecycle = [
        event["data"].get("status")
        for event in seen
        if event["event_type"] == "developer_step"
    ]
    assert lifecycle == ["started", "failed"]


@pytest.mark.parametrize('mode', ['execute', 'repair'])
def test_pcp_profile_is_explicit_and_preserves_provider_custody(monkeypatch,tmp_path,mode):
    import tomllib
    from app.shell import agent_subprocess_env
    captured={}
    monkeypatch.setenv('CODEX_HOME','/fixture-provider')
    monkeypatch.setenv('RUNTIME_API_TOKEN','SYNTHETIC_PRIVATE')
    monkeypatch.setenv('GITHUB_DELIVERY_TOKEN','SYNTHETIC_PRIVATE')
    async def run(argv,**kwargs):
        captured.update(argv=argv,env=agent_subprocess_env(kwargs.get('env')))
        return CommandResult(argv=argv,returncode=0,stdout=_event({'type':'turn.completed'}),stderr='')
    monkeypatch.setattr('app.adapters.codex.run_command',run)
    asyncio.run(CodexAdapter('fixture-model').run(workspace=tmp_path,prompt='fixture',mode=mode,timeout=10,isolate_workspace=True))
    args=captured['argv']
    assert '--sandbox' not in args
    assert {'--ignore-user-config','--ignore-rules','--strict-config'}<=set(args)
    assert 'approval_policy="never"' in args and 'sandbox_workspace_write.network_access=false' in args
    config=tomllib.loads(next(v for v in args if v.startswith('permissions=')))['permissions']['pcp_local']
    assert config['extends']==':workspace' and config['workspace_roots']=={}
    assert config['network']=={'enabled':False}
    assert config['filesystem'][':root']=='deny' and config['filesystem'][str(tmp_path)]=='write'
    assert '/fixture-provider' not in config['filesystem']
    assert captured['env']['CODEX_HOME']=='/fixture-provider'
    assert not any('TOKEN' in k for k in captured['env'])


@pytest.mark.parametrize('override', [{'environment':{'TMPDIR':'/foreign'}},
    {'developer_broker':{'x':'y'}},{'mode':'plan'}])
def test_pcp_profile_refuses_incompatible_transport_or_mode(tmp_path,override):
    args=dict(workspace=tmp_path,prompt='fixture',mode='execute',timeout=10,isolate_workspace=True)
    args.update(override)
    with pytest.raises(ValueError):
        asyncio.run(CodexAdapter('fixture-model').run(**args))


def test_pcp_profile_refuses_symlinked_workspace(tmp_path):
    from app.adapters.codex import isolated_permissions
    (tmp_path/'link').symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(ValueError):isolated_permissions(tmp_path/'link')


@pytest.mark.parametrize('location', ['user','project','ancestor','symlink'])
def test_pcp_inherited_configuration_fails_closed_before_subprocess(monkeypatch,tmp_path,location):
    workspace=tmp_path/'jobs'/'b';workspace.mkdir(parents=True)
    home=tmp_path/'provider';home.mkdir()
    monkeypatch.setenv('CODEX_HOME',str(home))
    target=home if location=='user' else (workspace if location in ('project','symlink') else workspace.parent)/'.codex'
    target.mkdir(exist_ok=True)
    if location=='symlink':
        target.rmdir();target.symlink_to(home,target_is_directory=True)
    else:(target/'config.toml').write_text('[permissions.pcp_local.workspace_roots]\n"/foreign"=true\n')
    def forbidden(*a,**k):pytest.fail('configuration must be rejected before any command')
    monkeypatch.setattr('app.adapters.codex.run_command',forbidden)
    with pytest.raises(ValueError,match='unreviewed_codex_configuration'):
        asyncio.run(CodexAdapter('fixture-model').run(workspace=workspace,prompt='fixture',mode='execute',timeout=10,isolate_workspace=True))


@pytest.mark.parametrize('text', [
    '[projects."/exact"]\ntrust_level="trusted"\n',
    '[permissions.pcp_local]\nextends=":all"\n',
    'x=1\nx=2\n', '[mcp_servers.host]\ncommand="unsafe"\n',
    'include="/foreign"\n', 'model_provider="foreign"\n'])
def test_generated_looking_or_hostile_config_is_still_denied(monkeypatch,tmp_path,text):
    home=tmp_path/'home';home.mkdir();workspace=tmp_path/'job';workspace.mkdir()
    monkeypatch.setenv('CODEX_HOME',str(home));(home/'config.toml').write_text(text)
    async def forbidden(*a,**k):pytest.fail('configuration-sensitive subprocess executed')
    monkeypatch.setattr('app.adapters.codex.run_command',forbidden)
    with pytest.raises(ValueError,match='unreviewed_codex_configuration'):
        asyncio.run(CodexAdapter('fixture').run(workspace=workspace,prompt='fixture',mode='execute',timeout=10,isolate_workspace=True))


def test_config_race_during_invocation_preparation_is_rechecked(monkeypatch,tmp_path):
    from app.adapters import codex
    home=tmp_path/'home';home.mkdir();workspace=tmp_path/'job';workspace.mkdir()
    monkeypatch.setenv('CODEX_HOME',str(home))
    original=codex.tempfile.NamedTemporaryFile
    def race(*a,**k):
        (home/'config.toml').write_text('permissions={pcp_local={extends=":all"}}')
        return original(*a,**k)
    monkeypatch.setattr(codex.tempfile,'NamedTemporaryFile',race)
    async def forbidden(*a,**k):pytest.fail('raced configuration reached subprocess')
    monkeypatch.setattr(codex,'run_command',forbidden)
    with pytest.raises(ValueError,match='unreviewed_codex_configuration'):
        asyncio.run(CodexAdapter('fixture').run(workspace=workspace,prompt='fixture',mode='execute',timeout=10,isolate_workspace=True))


def test_project_trust_is_exact_in_memory_and_does_not_grant_permission(monkeypatch,tmp_path):
    import tomllib
    from app.adapters import codex
    monkeypatch.setenv('CODEX_HOME',str(tmp_path/'home'))
    async def run(argv,**kwargs):
        projects=tomllib.loads(next(x for x in argv if x.startswith('projects=')))
        assert projects=={'projects':{str(tmp_path):{'trust_level':'trusted'}}}
        assert 'default_permissions="pcp_local"' in argv and codex.isolated_permissions(tmp_path) in argv
        return CommandResult(argv,0,'{"type":"turn.completed"}','')
    monkeypatch.setattr(codex,'run_command',run)
    asyncio.run(CodexAdapter('fixture').run(workspace=tmp_path,prompt='fixture',mode='execute',timeout=10,isolate_workspace=True))


def test_large_pinned_context_reaches_transport_whole_without_argument_limit(monkeypatch,tmp_path):
    from app.adapters import codex
    prompt = 'Original acceptance criterion — tiêu chí đầy đủ\n' * 12000
    monkeypatch.setenv('CODEX_HOME',str(tmp_path/'home'))
    async def run(argv,**kwargs):
        assert argv[-1]=='-' and prompt not in argv
        assert kwargs['input_text']==prompt and len(prompt.encode())>131072
        return CommandResult(argv,0,'{"type":"turn.completed"}','')
    monkeypatch.setattr(codex,'run_command',run)
    asyncio.run(CodexAdapter('fixture').run(workspace=tmp_path,prompt=prompt,mode='repair',timeout=10,isolate_workspace=True))
