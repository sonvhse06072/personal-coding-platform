from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .base import (
    AgentAdapter,
    AgentRun,
    InvocationCapabilities,
    classify_provider_failure,
)
from ..developer_stream import agent_lifecycle_event, agent_public_event, emit_developer_event
from ..shell import CommandResult, CommandTimeoutError, run_command


PCP_ISOLATION_CLI_VERSION = "0.160.0"


def require_isolated_provider_configuration() -> None:
    # Empty tables merge with inherited profile entries in this pinned CLI.
    # Reject configuration sources before launching; never rely on {} to clear
    # a broader inherited root. Auth files are retained and never read here.
    codex_home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    if not codex_home.is_absolute() or codex_home.resolve() != codex_home or codex_home.is_symlink():
        raise ValueError('pcp_local_unreviewed_codex_configuration')
    configs = [codex_home / 'config.toml', Path('/etc/codex/config.toml')]
    if any(p.exists() or p.is_symlink() for p in configs):
        raise ValueError('pcp_local_unreviewed_codex_configuration')


def require_isolated_configuration(workspace: Path) -> None:
    require_isolated_provider_configuration()
    directories = set(workspace.rglob('.codex')) | {p / '.codex' for p in workspace.parents}
    if any(p.is_symlink() or (p.exists() and (not p.is_dir() or any(p.iterdir())))
           for p in directories):
        raise ValueError('pcp_local_unreviewed_codex_configuration')


def isolated_permissions(workspace: Path) -> str:
    """Pinned CLI permission profile; no writable/readable sibling or provider home.

    The CLI itself retains its existing provider transport/auth custody. Only its
    developer tools receive this filesystem view. The immutable Runtime image
    supplies /usr and /opt/venv; no new mount, socket or network permission.
    Use one TOML table override: dotted CLI keys do not parse quoted path keys.
    """
    if not workspace.is_absolute() or workspace.is_symlink() or workspace.resolve() != workspace:
        raise ValueError("PCP isolation requires the exact workspace path")
    return ('permissions={pcp_local={extends=":workspace", workspace_roots={}, '
            'filesystem={":root"="deny", ":minimal"="read", ":tmpdir"="deny", '
            '":slash_tmp"="deny", "/usr"="read", "/bin"="read", "/lib"="read", '
            '"/lib64"="read", "/opt/venv"="read", '
            + json.dumps(str(workspace)) + '="write"}, network={enabled=false}}}')


class CodexAdapter(AgentAdapter):
    name = "codex_cli"

    def invocation_capabilities(self, mode: str) -> InvocationCapabilities:
        if mode in {"execute", "repair"}:
            return InvocationCapabilities(
                local_listener=False,
                php_runtime=False,
                reason="codex_workspace_network_disabled",
                php_runtime_reason="runtime_container_php_unavailable",
            )
        if mode == "evaluate":
            return InvocationCapabilities(
                local_listener=False,
                php_runtime=False,
                reason="codex_read_only_evaluation",
                php_runtime_reason="runtime_container_php_unavailable",
            )
        return super().invocation_capabilities(mode)

    async def run(
        self, *, workspace: Path, prompt: str, mode: str, timeout: int,
        environment: dict[str, str] | None = None,
        developer_broker: dict[str, str] | None = None,
        isolate_workspace: bool = False,
    ) -> AgentRun:
        sandbox = "read-only" if mode in {"plan", "evaluate"} else "workspace-write"
        if developer_broker is not None and mode not in {"execute", "repair"}:
            raise ValueError("Scoped developer tools never run in plan/evaluate")
        # Runtime is non-interactive: a Codex approval prompt has no valid human
        # response channel. Make the policy explicit instead of inheriting mounted
        # user configuration. This does not broaden the sandbox; commands that need
        # more permission fail closed. Execute/repair also pins workspace network
        # access off so user config cannot silently widen that boundary.
        argv = [
            "codex",
            "exec",
            "--json",
            "--sandbox",
            sandbox,
            "--config",
            'approval_policy="never"',
            "--config",
            "features.memories=false",
            "--config",
            "memories.use_memories=false",
            "--config",
            "memories.generate_memories=false",
        ]
        if isolate_workspace:
            if mode not in {"execute", "repair"} or environment is not None or developer_broker is not None:
                raise ValueError("PCP isolation cannot accept extra tools/environment")
            require_isolated_configuration(workspace)
            # PCP-local only. Inherited user/rule configuration cannot widen this
            # invocation. Auth still uses the original CODEX_HOME, outside tools.
            argv[3:5] = []  # Named permissions replace legacy --sandbox mode.
            argv += ["--strict-config", "--ignore-user-config", "--ignore-rules",
                     "--config", 'default_permissions="pcp_local"',
                     "--config", isolated_permissions(workspace),
                     # 0.160 thread/start persists implicit writable-project
                     # trust even with --ignore-user-config. Explicit in-memory
                     # trust suppresses that write; it grants no permissions.
                     # Project configuration remains forbidden above.
                     "--config", 'projects={' + json.dumps(str(workspace))
                     + '={trust_level="trusted"}}']
        if sandbox == "workspace-write":
            argv += ["--config", "sandbox_workspace_write.network_access=false"]
        argv += ["--cd", str(workspace)]
        # This is an opt-in, per-job, token-scoped MCP *tool*, not blanket
        # Codex network/full-host access. The broker's bearer cannot authorize
        # any normal Executor/GitHub/Runtime endpoints.
        if developer_broker is not None:
            from ..trusted_codex_mcp import _ENV as _BROKER_ENV
            if set(developer_broker) != set(_BROKER_ENV):
                raise ValueError("Invalid scoped Codex tool environment")
            tool_file = Path(__file__).resolve().parent.parent / "trusted_codex_mcp.py"
            if not tool_file.is_file():
                raise ValueError("Trusted Codex MCP tool is unavailable")
            argv += [
                "--config", 'mcp_servers.pcp_dev.command="python3"',
                "--config", 'mcp_servers.pcp_dev.args='
                + json.dumps(["-u", str(tool_file)], separators=(",", ":")),
                "--config", 'mcp_servers.pcp_dev.env_vars='
                + json.dumps(list(_BROKER_ENV), separators=(",", ":")),
                "--config", "mcp_servers.pcp_dev.required=true",
                "--config", "mcp_servers.pcp_dev.tool_timeout_sec=180",
                "--config", 'mcp_servers.pcp_dev.enabled_tools=["pcp_run_project_checks"]',
            ]
            environment = {**(environment or {}), **developer_broker}
            prompt += (
                "\n\nFor this one disposable fixture you can call "
                "pcp_dev.pcp_run_project_checks (targeted_tests, static_analysis, "
                "frontend_quality) within this same developer turn. "
                "Do not attempt direct DDEV, network, Docker or privileged shell."
            )
        if self.model and self.model not in {"auto", "subscription-auto", "subscription-managed", "frontier-subscription-managed"}:
            argv += ["--model", self.model]
        if self.reasoning_effort:
            argv += ["--config", f'model_reasoning_effort="{self.reasoning_effort}"']

        # Keep the JSONL stream for progress/telemetry, but capture the final
        # assistant response separately. A Codex turn may emit several
        # agent_message events; structured consumers such as PM planning must not
        # receive progress prose concatenated ahead of the final JSON response.
        last_message_file = tempfile.NamedTemporaryFile(
            prefix="pcp-codex-last-message-",
            suffix=".txt",
            delete=False,
        )
        last_message_path = Path(last_message_file.name)
        last_message_file.close()
        argv += ["--output-last-message", str(last_message_path)]
        argv.append(prompt)

        try:
            emit_developer_event(
                agent_lifecycle_event(
                    adapter=self.name,
                    provider="openai",
                    model=self.model,
                    mode=mode,
                    state="started",
                )
            )

            def on_stdout_line(line: str) -> None:
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    return
                emit_developer_event(
                    agent_public_event(
                        raw,
                        workspace=workspace,
                        mode=mode,
                        adapter=self.name,
                        provider="openai",
                        model=self.model,
                    )
                )

            timed_out: CommandTimeoutError | None = None
            try:
                invoke = {
                    "cwd": workspace,
                    "timeout": timeout,
                    "on_stdout_line": on_stdout_line,
                }
                if environment is not None:
                    invoke["env"] = environment
                if isolate_workspace:
                    require_isolated_configuration(workspace)
                result = await run_command(argv, **invoke)
            except CommandTimeoutError as exc:
                timed_out = exc
                result = CommandResult(
                    argv=argv,
                    returncode=124,
                    stdout=exc.stdout,
                    stderr=exc.stderr or str(exc),
                )

            messages: list[str] = []
            errors: list[str] = []
            usage: dict = {}
            terminal_event: str | None = None
            saw_json_event = False

            for line in result.stdout.splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                saw_json_event = True
                event_type = str(event.get("type") or "")
                if event_type == "item.completed":
                    item = event.get("item", {})
                    if item.get("type") == "agent_message" and item.get("text"):
                        messages.append(str(item["text"]))
                if event_type == "turn.completed":
                    terminal_event = "turn.completed"
                    usage = event.get("usage") or usage
                if event_type in {"error", "turn.failed", "item.failed"}:
                    candidate = event.get("error") or event.get("message") or event.get("item") or event
                    if isinstance(candidate, (dict, list)):
                        errors.append(json.dumps(candidate, ensure_ascii=False))
                    else:
                        errors.append(str(candidate))
                    if event_type in {"error", "turn.failed"}:
                        terminal_event = event_type

            try:
                final_message = last_message_path.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError):
                final_message = ""
            output = final_message or "\n".join(messages) or result.stdout

            # `codex exec --json` has structured terminal turn events. A successful
            # `turn.completed` from a zero-exit process is authoritative even when
            # earlier/transient telemetry or stderr contains phrases such as
            # "rate limit". Scanning the whole raw stream in that case can turn a
            # completed, side-effecting run into a false provider failure.
            structured_success = (
                timed_out is None
                and terminal_event == "turn.completed"
                and result.returncode == 0
            )
            if structured_success:
                failure_kind = None
                failure_message = None
                effective_returncode = 0
            else:
                diagnostics = [result.stderr, "\n".join(errors)]
                if not saw_json_event or terminal_event is None:
                    diagnostics.append(result.stdout)
                failure_kind, failure_message = classify_provider_failure(*diagnostics)
                effective_returncode = result.returncode
                if timed_out is not None:
                    failure_kind = "timeout"
                    failure_message = str(timed_out)
                    effective_returncode = 124
                elif errors and effective_returncode == 0:
                    effective_returncode = 70
                elif failure_kind and effective_returncode == 0:
                    effective_returncode = 75
                if errors and not failure_message:
                    failure_message = "\n".join(errors)[-12000:]

            emit_developer_event(
                agent_lifecycle_event(
                    adapter=self.name,
                    provider="openai",
                    model=self.model,
                    mode=mode,
                    state="completed" if effective_returncode == 0 else "failed",
                )
            )
            return AgentRun(
                self.name,
                self.model,
                effective_returncode,
                output,
                result.stderr,
                usage,
                result.stdout,
                failure_kind=failure_kind,
                failure_message=failure_message,
            )
        finally:
            try:
                last_message_path.unlink(missing_ok=True)
            except OSError:
                pass
