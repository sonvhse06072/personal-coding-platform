"""Opt-in, single-writer G0 fixture job path; never touches legacy PCP jobs.

This is a narrowly scoped CI-first research execution mode, not a new
production engine. It reuses the existing Codex adapter, persisted Storage,
DDEV Executor client for *Git-only* workspaces, and review-gated delivery.
Nothing starts when the normal or inspection-only Runtime is running.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import re
import subprocess
import uuid
from typing import Any
from urllib.parse import urlsplit

from .adapters.codex import CodexAdapter
from .config import project_baselines_doc, projects_doc
from .executor_client import DdevExecutorClient
from .repo import diff_state
from .shell import agent_subprocess_env
from .storage import Storage


PROJECT_ID = "pcp-g0-drupal-fixture"
FIXTURE_REPO = "sonvhse06072/pcp-g0-drupal-fixture"
SEED = "39ef13c25b24c4a1b43a720ae53419f479996ed2"
REVISION = "g0d01-seed-2026-10-10"
TASK_ID = "G0D-T01"
WORKFLOW_BLOB = "30e1202a37a7e57cd29e10dad8d5a2dd06f35cd8"
VERIFICATION_POLICY = "g0d-t01-ci-first-validation-30e1202a"
ALLOWED_FILES = frozenset({
    "web/modules/custom/pcp_g0_fixture/src/EventLabelNormalizer.php",
    "web/modules/custom/pcp_g0_fixture/tests/src/Unit/EventLabelNormalizerTest.php",
    "web/modules/custom/pcp_g0_fixture/tests/src/Kernel/EventLabelServiceTest.php",
})
G0_PROMPT = """Implement G0D-T01 on this isolated Drupal fixture, not on any other project.
Change only EventLabelNormalizer.php and its named Unit/Kernel test files.
In EventLabelNormalizer::normalize(string), collapse consecutive internal ASCII
whitespace (space U+0020, tab, CR, LF) into one ASCII space. Preserve the
baseline trim behavior and nonbreaking spaces (NBSP U+00A0). Add real Unit and
Kernel coverage, including consecutive tabs, CR/LF, and negative NBSP cases.
Do not change dependencies, baseline, CI, .ddev, configuration, schema or docs.
Do not push, open a pull request, merge, or touch a non-fixture repository.
The same Composer/PHPCS/Unit/Kernel GitHub Actions acceptance applies to both
arms. Do not claim local DDEV or visual testing.
"""


class G0GateError(RuntimeError):
    """Controlled fixture-only stop; no implicit continuation or retries."""


def _policy_fixture_only() -> None:
    registry = projects_doc()
    projects = registry.get("projects")
    if not isinstance(projects, dict) or set(projects) != {PROJECT_ID}:
        raise G0GateError("G0 requires a fixture-only project registry")
    cfg = projects[PROJECT_ID]
    if (
        not isinstance(cfg, dict)
        or cfg.get("path")
            != "${CODING_PROJECTS_ROOT}/pcp-g0-fixtures/pcp-g0-drupal-fixture"
        or cfg.get("base_branch") != "benchmark/pcp"
        or not isinstance(cfg.get("runtime"), dict)
        or cfg["runtime"].get("workspace_mode") != "isolated_clone"
        or cfg["runtime"].get("exclusive_project_lease") is not False
        or not isinstance(cfg.get("ddev"), dict)
        or cfg["ddev"].get("enabled") is not False
    ):
        raise G0GateError("G0 fixture identity or PARKED DDEV policy changed")
    if any(v is not False for v in (cfg.get("autonomy") or {}).values()):
        raise G0GateError("G0 fixture policy cannot enable standard autonomy")

    baselines = project_baselines_doc().get("projects")
    if not isinstance(baselines, dict) or set(baselines) != {PROJECT_ID}:
        raise G0GateError("G0 requires fixture-only ProjectBaseline")
    policy = baselines[PROJECT_ID]
    if (
        not isinstance(policy, dict)
        or policy.get("active_revision") != REVISION
        or not isinstance(policy.get("revisions"), dict)
        or set(policy["revisions"]) != {REVISION}
        or policy["revisions"][REVISION].get("status") != "approved"
        or policy["revisions"][REVISION].get("source_commit") != SEED
    ):
        raise G0GateError("G0 ProjectBaseline revision is not frozen")
    if os.getenv("CODING_PROJECTS_ROOT") != "/g0/sources":
        raise G0GateError("G0 projects root must be isolated")
    if os.getenv("CODING_WORKSPACES_ROOT") != "/g0/workspaces":
        raise G0GateError("G0 workspace root must be isolated")
    if os.getenv("CODING_DIRECT_PROJECT_ROOT") != "/g0/direct-disabled":
        raise G0GateError("G0 direct project capability must remain disabled")
    if Path("/var/run/docker.sock").exists():
        raise G0GateError("G0 Runtime must not have the Docker socket")
    if os.getenv("ANTIGRAVITY_BRIDGE_URL") or os.getenv("ANTIGRAVITY_BRIDGE_TOKEN"):
        raise G0GateError("G0 cannot enable the host Antigravity bridge")


def _runtime_config() -> tuple[str, str, str]:
    """Explicit provider/runtime readiness, never default to another account."""
    if os.getenv("PCP_G0_EXECUTION_ENABLED") != "owner-approved":
        raise G0GateError("G0 source is not approved for local execution")
    dsn = urlsplit(os.getenv("DATABASE_URL", ""))
    if (
        dsn.scheme not in {"postgresql", "postgres"}
        or dsn.hostname != "db"
        or dsn.port != 5432
        or dsn.username != "g0"
        or dsn.path != "/g0"
    ):
        raise G0GateError("G0 must use its dedicated DB identity")
    model = os.getenv("PCP_G0_MODEL_ID", "")
    effort = os.getenv("PCP_G0_REASONING_EFFORT", "")
    version = os.getenv("PCP_G0_CODEX_CLI_VERSION", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}", model):
        raise G0GateError("Dedicated G0 Codex model is not pinned")
    if effort not in {"low", "medium", "high"}:
        raise G0GateError("Dedicated G0 reasoning effort is not pinned")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise G0GateError("Dedicated G0 Codex CLI version is not pinned")
    if os.getenv("PCP_G0_CODEX_HOME") != "/home/coder/.codex-g0":
        raise G0GateError("G0 requires a dedicated Codex profile")
    return model, effort, version


def validate_job_diff(diff: dict[str, Any]) -> list[str]:
    paths = diff.get("changed_files")
    if (
        not isinstance(paths, list)
        or not paths
        or any(type(p) is not str or p not in ALLOWED_FILES for p in paths)
        or set(paths) != ALLOWED_FILES
        or len(paths) != len(ALLOWED_FILES)
        or diff.get("diff_truncated") is not False
        or int(diff.get("changed_file_count", -1)) != len(paths)
        or bool(diff.get("dependency_manifest_changes"))
    ):
        raise G0GateError("G0 source changed outside exact fixture task contract")
    return paths


def _checked_workspace(root: Path, job_id: str, path: str) -> Path:
    try:
        workspace = Path(path).resolve(strict=True)
        expected = root.resolve(strict=True) / job_id
    except OSError as exc:
        raise G0GateError("G0 owned workspace is unavailable") from exc
    if workspace != expected or not workspace.is_dir():
        raise G0GateError("G0 workspace is outside its exact job path")
    return workspace


def _assert_frozen_workspace(workspace: Path, branch: str) -> None:
    """No model call if seed, private branch, cleanliness or origin drifted."""
    env = agent_subprocess_env({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
    })
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(workspace), "-c", "core.hooksPath=/dev/null",
             *args],
            capture_output=True, text=True, timeout=15, env=env,
        )
        if result.returncode:
            raise G0GateError("G0 workspace Git identity probe failed")
        return result.stdout.strip()

    if (
        git("rev-parse", "HEAD") != SEED
        or git("branch", "--show-current") != branch
        or git("remote")
        or git("status", "--porcelain=v1")
    ):
        raise G0GateError("G0 workspace is no longer a clean frozen seed clone")


def _commit_exact_g0(workspace: Path, paths: list[str]) -> str:
    """Commit only reviewed paths, with no Git hooks or inherited Runtime secrets."""
    if not paths or any(p not in ALLOWED_FILES for p in paths):
        raise G0GateError("G0 commit paths are outside the frozen fixture contract")
    if any((workspace / p).is_symlink() for p in paths):
        raise G0GateError("G0 cannot commit replaced symlink source files")
    env = agent_subprocess_env({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
    })

    def git(*args: str, allow_empty_commit: bool = False) -> str:
        p = subprocess.run(
            ["git", "-C", str(workspace), "-c", "core.hooksPath=/dev/null",
             *args],
            capture_output=True, text=True, timeout=30, env=env,
        )
        if p.returncode:
            if allow_empty_commit and "nothing to commit" in p.stdout:
                return ""
            raise G0GateError("Fixture-only scoped Git operation failed")
        return p.stdout.strip()

    git("add", "--", *paths)
    # Existing Codex-produced commits are allowed only if the source-to-final
    # diff has already been scoped by validate_job_diff().
    staged = git("diff", "--cached", "--name-only").splitlines()
    if staged and any(p not in ALLOWED_FILES for p in staged):
        raise G0GateError("G0 staging contains unauthorized paths")
    if staged:
        git("-c", "user.name=PCP G0 Fixture Developer",
            "-c", "user.email=pcp-g0-fixture@localhost",
            "commit", "-m", "test(g0): normalize internal ASCII whitespace")
    git("merge-base", "--is-ancestor", SEED, "HEAD")
    commit = git("rev-parse", "HEAD")
    if commit == SEED or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise G0GateError("Fixture-only job produced no derived commit")
    return commit


def _codex_version() -> str:
    try:
        p = subprocess.run(
            ["codex", "--version"], text=True, capture_output=True, timeout=12,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise G0GateError("Dedicated Codex CLI is unavailable") from exc
    match = re.fullmatch(r"codex-cli (\d+\.\d+\.\d+)", p.stdout.strip())
    if p.returncode != 0 or match is None:
        raise G0GateError("Dedicated Codex CLI output is invalid")
    return match.group(1)


class G0FixtureExecution:
    """One durable G0 job. No scheduler, old DB, DDEV, or provider fallback."""

    def __init__(self, storage: Storage, executor: DdevExecutorClient) -> None:
        self.storage = storage
        self.executor = executor
        self.workspace_root = Path("/g0/workspaces")
        self.lock = asyncio.Lock()

    def prepare_startup(self) -> None:
        _policy_fixture_only()
        _runtime_config()
        # Inspection source may be imported anywhere; only an explicitly
        # authorized fixture-only process executes the following dedicated DB
        # check. Never call the generic RuntimeEngine.start() or Antigravity.
        with self.storage.connect() as conn:
            previous = conn.execute("SELECT to_regclass('public.cp_jobs') AS table_name").fetchone()
            if previous and previous.get("table_name"):
                rows = conn.execute(
                    "SELECT project_id, status FROM cp_jobs LIMIT 2"
                ).fetchall()
                if (len(rows) > 1 or any(
                    r["project_id"] != PROJECT_ID or r["status"] == "executing"
                    for r in rows
                )):
                    raise G0GateError("G0 DB has foreign, concurrent or ambiguous jobs")
            # These tables should be empty for a single isolated G0 WorkOrder.
            # Do not repair/cancel/import an unexpected historical plan or lease.
            for table in (
                "cp_project_leases", "cp_execution_plans",
                "cp_plan_orchestrations", "cp_plan_work_orders",
            ):
                exists = conn.execute(
                    "SELECT to_regclass(%s) AS table_name", ("public." + table,)
                ).fetchone()
                if exists and exists.get("table_name"):
                    if conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                        raise G0GateError("G0 DB contains unexpected non-fixture work state")
        self.storage.init()

    def current(self, job_id: str) -> dict[str, Any]:
        row = self.storage.get(job_id)
        if not row or row.get("project_id") != PROJECT_ID:
            raise G0GateError("Unknown G0 fixture job")
        return row

    async def prepare(self) -> dict[str, Any]:
        async with self.lock:
            if self.storage.list(limit=2):
                raise G0GateError("G0 allows only one durable fixture job")
            model, effort, expected_cli = _runtime_config()
            _policy_fixture_only()
            if _codex_version() != expected_cli:
                raise G0GateError("Installed G0 Codex CLI version is not comparable")
            job_id = uuid.uuid4().hex
            self.storage.create({
                "id": job_id, "project_id": PROJECT_ID, "status": "queued",
                "source_commit": SEED,
                "task": {"title": TASK_ID, "description": G0_PROMPT, "task_type": "drupal"},
                "checkpoint": {"g0_fixture": {
                    "task_id": TASK_ID, "source_commit": SEED,
                    "model_id": model, "reasoning_effort": effort,
                    "codex_cli_version": expected_cli,
                    "verification_policy": VERIFICATION_POLICY,
                    "workflow_blob": WORKFLOW_BLOB,
                }},
                "progress": {},
            })
            try:
                ws = await self.executor.create_workspace(
                    job_id=job_id, project_id=PROJECT_ID, ref=SEED,
                    workspace_mode="isolated_clone",
                )
                workspace = _checked_workspace(self.workspace_root, job_id, str(ws["workspace"]))
                if (
                    ws.get("source_commit") != SEED
                    or ws.get("branch") != f"ai/{job_id[:12]}"
                    or ws.get("workspace_mode") != "isolated_clone_no_remote"
                ):
                    raise G0GateError("Executor did not return the frozen G0 workspace")
                self.storage.update(
                    job_id, workspace=str(workspace), branch=ws["branch"],
                )
            except Exception:
                self.storage.update(
                    job_id, status="blocked",
                    error="Fixture-only workspace preparation failed; preserve job for review",
                )
                raise
            return self.current(job_id)

    async def execute(self, job_id: str) -> dict[str, Any]:
        async with self.lock:
            row = self.current(job_id)
            if row["status"] != "queued" or not row.get("workspace"):
                raise G0GateError("G0 job is not prepared for exact one-time execution")
            model, effort, expected_cli = _runtime_config()
            _policy_fixture_only()
            if _codex_version() != expected_cli:
                raise G0GateError("G0 Codex binary changed since preflight")
            workspace = _checked_workspace(self.workspace_root, job_id, row["workspace"])
            _assert_frozen_workspace(workspace, str(row["branch"]))
            checkpoint = row["checkpoint"]["g0_fixture"]
            if any((checkpoint.get(k) != v) for k, v in {
                "model_id": model, "reasoning_effort": effort,
                "codex_cli_version": expected_cli, "source_commit": SEED,
                "verification_policy": VERIFICATION_POLICY, "workflow_blob": WORKFLOW_BLOB,
            }.items()):
                raise G0GateError("G0 persisted job policy does not match pinned runtime")
            self.storage.update(job_id, status="executing")
            try:
                adapter = CodexAdapter(model=model, reasoning_effort=effort)
                result = await adapter.run(
                    workspace=workspace, prompt=G0_PROMPT, mode="execute",
                    timeout=1800, environment={"CODEX_HOME": "/home/coder/.codex-g0"},
                )
                if result.returncode != 0 or result.provider_failed:
                    raise G0GateError("G0 Codex failed; same job requires explicit recovery review")
                diff = diff_state(workspace, max_bytes=60_000, base_ref=SEED)
                paths = validate_job_diff(diff)
                # Commit only the already scope-checked paths using sanitized
                # Git subprocesses and disabled hooks; the agent never receives
                # privileged delivery/API credentials.
                commit = _commit_exact_g0(workspace, paths)
                self.storage.update(
                    job_id, status="waiting_human",
                    result={
                        "stage": "awaiting_fixture_only_delivery",
                        "commit": commit, "source_commit": SEED,
                        "branch": row["branch"], "changed_files": paths,
                        "verification_policy": VERIFICATION_POLICY,
                        "workflow_blob": WORKFLOW_BLOB,
                        "model_id": model, "reasoning_effort": effort,
                        "codex_cli_version": expected_cli,
                        "usage": dict(result.usage or {}),
                        "deterministic_ci": "not_run_yet",
                    },
                )
            except Exception:
                self.storage.update(
                    job_id, status="blocked",
                    error="G0 execution stopped; original job/workspace preserved",
                )
                raise
            return self.current(job_id)

    async def deliver(self, job_id: str) -> dict[str, Any]:
        """PR creation is privileged Executor work, never a Codex agent action."""
        async with self.lock:
            row = self.current(job_id)
            if row["status"] != "waiting_human" or not row.get("result"):
                raise G0GateError("G0 job has no independently reviewable commit")
            if os.getenv("PCP_G0_DELIVERY_ENABLED") != "owner-approved":
                raise G0GateError("G0 fixture-only GitHub delivery is not activated")
            _policy_fixture_only()
            result = row["result"]
            if result.get("stage") != "awaiting_fixture_only_delivery":
                raise G0GateError("G0 delivery stage is already consumed")
            workspace = _checked_workspace(self.workspace_root, job_id, row["workspace"])
            await self.executor.publish_branch(
                job_id=job_id, project_id=PROJECT_ID, workspace=str(workspace),
                branch=row["branch"], source_commit=SEED, expected_commit=result["commit"],
            )
            pr = await self.executor.upsert_pull_request(
                job_id=job_id, project_id=PROJECT_ID,
                branch=row["branch"], expected_commit=result["commit"],
                title="[G0D-T01] Controlled Drupal ASCII whitespace normalization",
                body=("G0 fixture-only CI-first trial. Review against immutable "
                      "seed, PHPCS, Unit/Kernel, exact-head GitHub Actions."),
            )
            self.storage.update(
                job_id, status="delivering",
                result={
                    **result,
                    "stage": "awaiting_independent_ci_and_pm_review",
                    "pull_request": pr.get("pull_request"),
                    "deterministic_ci": "unverified",
                },
            )
            return self.current(job_id)
