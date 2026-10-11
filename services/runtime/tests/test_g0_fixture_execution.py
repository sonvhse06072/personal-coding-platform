"""G0 fixture-only single-job source tests; no real Docker/provider/GitHub calls."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import g0_fixture_execution as g0


MODEL = "gpt-5.6"
EFFORT = "high"
CLI = "0.160.0"


class MemoryStorage:
    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.initialized = False

    def init(self):
        self.initialized = True

    def list(self, limit=50):
        return list(self.rows.values())[:limit]

    def get(self, jid):
        return deepcopy(self.rows.get(jid))

    def create(self, row):
        assert row["id"] not in self.rows
        self.rows[row["id"]] = deepcopy(row)

    def update(self, jid, **fields):
        assert jid in self.rows
        self.rows[jid].update(deepcopy(fields))


class FakeExecutor:
    def __init__(self, workspace_root: Path):
        self.root = workspace_root
        self.created = []
        self.published = []
        self.requests = []

    async def create_workspace(self, **kwargs):
        self.created.append(kwargs)
        workspace = self.root / kwargs["job_id"]
        workspace.mkdir()
        return {
            "workspace": str(workspace),
            "branch": "ai/" + kwargs["job_id"][:12],
            "source_commit": g0.SEED,
            "workspace_mode": "isolated_clone_no_remote",
        }

    async def publish_branch(self, **kwargs):
        self.published.append(kwargs)
        return {"published": True}

    async def upsert_pull_request(self, **kwargs):
        self.requests.append(kwargs)
        return {"pull_request": {"number": 22, "state": "open"}}


@pytest.fixture
def prepared(monkeypatch, tmp_path):
    monkeypatch.setattr(g0, "_policy_fixture_only", lambda: None)
    monkeypatch.setattr(g0, "_runtime_config", lambda: (MODEL, EFFORT, CLI))
    monkeypatch.setattr(g0, "_codex_version", lambda: CLI)
    storage = MemoryStorage()
    executor = FakeExecutor(tmp_path)
    runner = g0.G0FixtureExecution(storage, executor)
    runner.workspace_root = tmp_path
    return runner, storage, executor


def test_frozen_contract_never_includes_legacy_or_ddev_control():
    assert len(g0.SEED) == 40
    assert g0.WORKFLOW_BLOB == "30e1202a37a7e57cd29e10dad8d5a2dd06f35cd8"
    assert g0.VERIFICATION_POLICY == "g0d-t01-ci-first-validation-30e1202a"
    assert len(g0.ALLOWED_FILES) == 3
    assert all(p.startswith("web/modules/custom/pcp_g0_fixture/") for p in g0.ALLOWED_FILES)
    for prohibited in (
        "git push", "ddev start", "/home/sonvh/", "rm -rf",
        "gh pr create", "docker compose up", "Docker socket",
    ):
        assert prohibited not in g0.G0_PROMPT


@pytest.mark.parametrize("paths, truncated, deps", [
    ([], False, []),
    (["composer.lock"], False, []),
    (["web/modules/custom/pcp_g0_fixture/src/EventLabelNormalizer.php",
      "config/projects.yml"], False, []),
    ([".ddev/config.yaml"], False, []),
    ([next(iter(g0.ALLOWED_FILES))], True, []),
    ([next(iter(g0.ALLOWED_FILES))], False, ["composer.json"]),
])
def test_scope_guard_blocks_nonfixture_and_incomplete_diffs(paths, truncated, deps):
    with pytest.raises(g0.G0GateError, match="outside exact fixture"):
        g0.validate_job_diff({
            "changed_files": paths, "changed_file_count": len(paths),
            "diff_truncated": truncated, "dependency_manifest_changes": deps,
        })


def test_scope_guard_accepts_only_frozen_php_targets():
    changes = sorted(g0.ALLOWED_FILES)
    assert g0.validate_job_diff({
        "changed_files": changes, "changed_file_count": 3,
        "diff_truncated": False, "dependency_manifest_changes": [],
    }) == changes


def test_runtime_requires_explicit_activation_and_dedicated_credentials(monkeypatch):
    monkeypatch.delenv("PCP_G0_EXECUTION_ENABLED", raising=False)
    with pytest.raises(g0.G0GateError, match="not approved"):
        g0._runtime_config()
    monkeypatch.setenv("PCP_G0_EXECUTION_ENABLED", "owner-approved")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db:db@db:5432/db")
    monkeypatch.setenv("PCP_G0_MODEL_ID", MODEL)
    monkeypatch.setenv("PCP_G0_REASONING_EFFORT", EFFORT)
    monkeypatch.setenv("PCP_G0_CODEX_CLI_VERSION", CLI)
    monkeypatch.setenv("PCP_G0_CODEX_HOME", "/home/coder/.codex-g0")
    with pytest.raises(g0.G0GateError, match="dedicated DB"):
        g0._runtime_config()
    monkeypatch.setenv("DATABASE_URL", "postgresql://g0:test@db:5432/g0")
    assert g0._runtime_config() == (MODEL, EFFORT, CLI)
    monkeypatch.setenv("PCP_G0_CODEX_HOME", "/home/coder/.codex")
    with pytest.raises(g0.G0GateError, match="dedicated Codex profile"):
        g0._runtime_config()


def test_project_registry_policy_fails_closed_if_legacy_registry(monkeypatch):
    monkeypatch.setenv("CODING_PROJECTS_ROOT", "/g0/sources")
    monkeypatch.setenv("CODING_WORKSPACES_ROOT", "/g0/workspaces")
    monkeypatch.setenv("CODING_DIRECT_PROJECT_ROOT", "/g0/direct-disabled")
    monkeypatch.delenv("ANTIGRAVITY_BRIDGE_URL", raising=False)
    monkeypatch.delenv("ANTIGRAVITY_BRIDGE_TOKEN", raising=False)
    monkeypatch.setattr(g0.Path, "exists", lambda self: False)
    base = {
        "path": "${CODING_PROJECTS_ROOT}/pcp-g0-fixtures/pcp-g0-drupal-fixture",
        "base_branch": "benchmark/pcp",
        "runtime": {"workspace_mode": "isolated_clone",
                    "exclusive_project_lease": False},
        "ddev": {"enabled": False},
        "autonomy": {"allow_commit": False, "allow_create_pr": False},
    }
    mono = {g0.PROJECT_ID: base}
    fixed = {g0.PROJECT_ID: {"active_revision": g0.REVISION, "revisions": {
        g0.REVISION: {"status": "approved", "source_commit": g0.SEED}
    }}}
    monkeypatch.setattr(g0, "projects_doc", lambda: {"projects": mono})
    monkeypatch.setattr(g0, "project_baselines_doc", lambda: {"projects": fixed})
    g0._policy_fixture_only()
    mono["chonhac"] = {"path": "/not-accessed"}
    with pytest.raises(g0.G0GateError, match="fixture-only project registry"):
        g0._policy_fixture_only()


def test_prepare_exact_once_and_no_provider_or_delivery(prepared):
    runner, storage, executor = prepared
    row = asyncio.run(runner.prepare())
    assert row["project_id"] == g0.PROJECT_ID
    assert row["status"] == "queued"
    assert row["source_commit"] == g0.SEED
    assert row["workspace"].startswith(str(runner.workspace_root))
    assert row["branch"] == "ai/" + row["id"][:12]
    assert len(executor.created) == 1
    assert executor.created[0]["ref"] == g0.SEED
    assert executor.created[0]["workspace_mode"] == "isolated_clone"
    assert executor.published == []
    assert executor.requests == []
    with pytest.raises(g0.G0GateError, match="only one durable"):
        asyncio.run(runner.prepare())


def test_prepare_records_failure_without_replacing_job(prepared):
    runner, storage, executor = prepared
    async def fail(**kwargs):
        raise RuntimeError("fixture source checkout unavailable")
    executor.create_workspace = fail
    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(runner.prepare())
    row = storage.list()[0]
    assert row["status"] == "blocked"
    assert "preserve job" in row["error"]
    with pytest.raises(g0.G0GateError, match="only one durable"):
        asyncio.run(runner.prepare())


def test_execute_requires_one_prepared_pinned_job(prepared, monkeypatch):
    runner, storage, executor = prepared
    with pytest.raises(g0.G0GateError, match="Unknown G0"):
        asyncio.run(runner.execute("a" * 32))
    row = asyncio.run(runner.prepare())
    monkeypatch.setattr(g0, "_codex_version", lambda: "9.9.9")
    with pytest.raises(g0.G0GateError, match="binary changed"):
        asyncio.run(runner.execute(row["id"]))
    assert runner.current(row["id"])["status"] == "queued"


def test_execute_runs_existing_codex_adapter_without_publishing(prepared, monkeypatch):
    runner, storage, executor = prepared
    row = asyncio.run(runner.prepare())
    invocation = []

    class StubCodexAdapter:
        def __init__(self, *, model, reasoning_effort):
            assert model == MODEL and reasoning_effort == EFFORT
        async def run(self, **kwargs):
            invocation.append(kwargs)
            return SimpleNamespace(returncode=0, provider_failed=False, usage={
                "input_tokens": 22, "output_tokens": 14
            })

    class FakePopen:
        returncode = 0

    monkeypatch.setattr(g0, "CodexAdapter", StubCodexAdapter)
    monkeypatch.setattr(g0, "diff_state", lambda *a, **k: {
        "changed_files": sorted(g0.ALLOWED_FILES),
        "changed_file_count": 3,
        "diff_truncated": False,
        "dependency_manifest_changes": [],
    })
    monkeypatch.setattr(g0, "_commit_exact_g0", lambda *a, **k: "b" * 40)
    monkeypatch.setattr(g0.subprocess, "run", lambda *a, **k: FakePopen())

    result = asyncio.run(runner.execute(row["id"]))
    assert result["status"] == "waiting_human"
    assert result["result"]["stage"] == "awaiting_fixture_only_delivery"
    assert result["result"]["deterministic_ci"] == "not_run_yet"
    assert result["result"]["commit"] == "b" * 40
    assert len(invocation) == 1
    assert invocation[0]["mode"] == "execute"
    assert invocation[0]["environment"] == {"CODEX_HOME": "/home/coder/.codex-g0"}
    assert executor.published == executor.requests == []
    with pytest.raises(g0.G0GateError, match="one-time execution"):
        asyncio.run(runner.execute(row["id"]))


def test_model_scope_violation_blocks_same_job_and_keeps_workspace(prepared, monkeypatch):
    runner, storage, executor = prepared
    row = asyncio.run(runner.prepare())
    called = []

    class FakeCodex:
        def __init__(self, **kwargs):
            pass
        async def run(self, **kwargs):
            return SimpleNamespace(returncode=0, provider_failed=False, usage={})

    monkeypatch.setattr(g0, "CodexAdapter", FakeCodex)
    monkeypatch.setattr(g0, "diff_state", lambda *a, **k: {
        "changed_files": ["config/projects.yml"], "changed_file_count": 1,
        "diff_truncated": False, "dependency_manifest_changes": [],
    })
    monkeypatch.setattr(g0, "_commit_exact_g0",
                        lambda *a, **k: pytest.fail("must not commit out-of-scope diff"))
    with pytest.raises(g0.G0GateError, match="outside exact"):
        asyncio.run(runner.execute(row["id"]))
    saved = runner.current(row["id"])
    assert saved["status"] == "blocked"
    assert Path(saved["workspace"]).is_dir()


def test_delivery_still_requires_separate_owner_activation(prepared, monkeypatch):
    runner, storage, executor = prepared
    row = asyncio.run(runner.prepare())
    storage.update(row["id"], status="waiting_human", result={
        "stage": "awaiting_fixture_only_delivery",
        "commit": "c" * 40,
    })
    monkeypatch.delenv("PCP_G0_DELIVERY_ENABLED", raising=False)
    with pytest.raises(g0.G0GateError, match="not activated"):
        asyncio.run(runner.deliver(row["id"]))
    assert executor.published == executor.requests == []
    monkeypatch.setenv("PCP_G0_DELIVERY_ENABLED", "owner-approved")
    delivered = asyncio.run(runner.deliver(row["id"]))
    assert delivered["status"] == "delivering"
    assert delivered["result"]["stage"] == "awaiting_independent_ci_and_pm_review"
    assert delivered["result"]["deterministic_ci"] == "unverified"
    assert executor.published[0]["project_id"] == g0.PROJECT_ID
    assert executor.published[0]["source_commit"] == g0.SEED
    assert executor.requests[0]["project_id"] == g0.PROJECT_ID
    assert executor.requests[0]["title"].startswith("[G0D-T01]")
    with pytest.raises(g0.G0GateError, match="no independently reviewable"):
        asyncio.run(runner.deliver(row["id"]))


def test_never_show_unrelated_project_records(prepared):
    runner, storage, executor = prepared
    storage.create({"id": "a" * 32, "project_id": "chonhac", "status": "blocked"})
    with pytest.raises(g0.G0GateError, match="Unknown G0"):
        runner.current("a" * 32)



def test_g0_commit_disables_hooks_and_limits_staging_to_reviewed_files(
    monkeypatch, tmp_path
):
    allowed = next(iter(g0.ALLOWED_FILES))
    file = tmp_path / allowed
    file.parent.mkdir(parents=True)
    file.write_text("safe fixture\n", encoding="utf-8")
    commands = []
    class Response:
        def __init__(self, stdout=""):
            self.stdout = stdout
            self.returncode = 0

    def fake_run(argv, **kwargs):
        commands.append((argv, kwargs))
        assert kwargs["env"]["GIT_CONFIG_GLOBAL"] == "/dev/null"
        assert kwargs["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
        assert "RUNTIME_API_TOKEN" not in kwargs["env"]
        assert ["-c", "core.hooksPath=/dev/null"] == argv[3:5]
        if "diff" in argv:
            return Response(allowed + "\n")
        if "rev-parse" in argv:
            return Response("b" * 40 + "\n")
        return Response()

    monkeypatch.setenv("RUNTIME_API_TOKEN", "secret-that-must-not-enter-git")
    monkeypatch.setattr(g0.subprocess, "run", fake_run)
    assert g0._commit_exact_g0(tmp_path, [allowed]) == "b" * 40
    add = [argv for argv, _ in commands if "add" in argv]
    assert len(add) == 1
    assert add[0][-2:] == ["--", allowed]
    assert any("commit" in argv for argv, _ in commands)
    assert all("rm" not in argv for argv, _ in commands)


def test_g0_commit_rejects_symlinks_before_git(monkeypatch, tmp_path):
    allowed = next(iter(g0.ALLOWED_FILES))
    file = tmp_path / allowed
    file.parent.mkdir(parents=True)
    file.symlink_to(tmp_path / "elsewhere")
    monkeypatch.setattr(g0.subprocess, "run",
                        lambda *a, **k: pytest.fail("no git for symlink"))
    with pytest.raises(g0.G0GateError, match="symlink"):
        g0._commit_exact_g0(tmp_path, [allowed])



@pytest.mark.parametrize("foreign_table", [
    "cp_project_leases", "cp_execution_plans",
    "cp_plan_orchestrations", "cp_plan_work_orders",
])
def test_g0_startup_rejects_legacy_state_before_storage_init(
    prepared, foreign_table
):
    runner, storage, executor = prepared

    class FakeQuery:
        def __init__(self, sql):
            self.sql = sql
        def fetchone(self):
            if "to_regclass" in self.sql:
                return {"table_name": "exists"}
            if f"FROM {foreign_table}" in self.sql:
                return {"value": 1}
            return None
        def fetchall(self):
            return []

    class FakeConn:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, *_args): return FakeQuery(sql)

    storage.connect = FakeConn
    with pytest.raises(g0.G0GateError, match="unexpected non-fixture work"):
        runner.prepare_startup()
    assert storage.initialized is False


def test_g0_startup_allows_fresh_owned_db_without_historical_replay(prepared):
    runner, storage, executor = prepared
    sql_called = []

    class FakeQuery:
        def __init__(self, sql):
            self.sql = sql
        def fetchone(self):
            return {"table_name": None}
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, *_args):
            sql_called.append(sql)
            return FakeQuery(sql)

    storage.connect = Conn
    runner.prepare_startup()
    assert storage.initialized is True
    assert all("UPDATE" not in sql and "DELETE" not in sql for sql in sql_called)
    assert executor.created == []
