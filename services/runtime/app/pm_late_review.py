"""Bounded read-only cross-provider review of a delivered, merge-blocked WorkOrder.

No existing job/result/review-policy is mutated. A claimed review is never
replayed after an uncertain completion. Attestations are append-only and can be
consumed only through the constrained PM merge gate.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .adapters import build_adapter
from .config import project_config
from .model_capabilities import validate_model_choice
from .pm_merge import LateReviewProof, evaluate_pm_merge
from .prompts import evaluator_prompt
from .review import parse_review_output
from .storage import now
from .usage import normalize_usage


LATE_REVIEW_DDL = """
CREATE TABLE IF NOT EXISTS cp_pm_late_review_attempts (
  id BIGSERIAL PRIMARY KEY,
  plan_id TEXT NOT NULL,
  work_order_id TEXT NOT NULL,
  job_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  checkpoint_id BIGINT NOT NULL,
  checkpoint_key TEXT NOT NULL,
  pr_number INTEGER NOT NULL,
  source_commit TEXT NOT NULL,
  branch TEXT NOT NULL,
  expected_head TEXT NOT NULL,
  diff_hash TEXT NOT NULL,
  writer_providers JSONB NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('claimed','no_capacity','failed','passed','uncertain')),
  reviewer_provider TEXT,
  reviewer_model TEXT,
  result JSONB,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE (plan_id, work_order_id, job_id, expected_head, checkpoint_id)
);
CREATE TABLE IF NOT EXISTS cp_pm_late_review_attestations (
  id BIGSERIAL PRIMARY KEY,
  attempt_id BIGINT NOT NULL UNIQUE REFERENCES cp_pm_late_review_attempts(id),
  payload JSONB NOT NULL,
  payload_sha256 TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS cp_pm_late_review_attempts_active_idx
  ON cp_pm_late_review_attempts(status, project_id);
"""


def _digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def writer_providers(job: dict[str, Any]) -> tuple[str, ...]:
    """Every attempted coding turn must have trusted, complete provider telemetry.

    A truncated 12-entry history cannot prove all contributors; reject it.
    Even an unsuccessful command may have modified files, so include its provider.
    """
    progress = dict(job.get("progress") or {})
    attempts = progress.get("agent_attempts")
    iterations = progress.get("iteration")
    if (
        type(iterations) is not int or iterations < 1
        or not isinstance(attempts, list) or len(attempts) < iterations
    ):
        raise RuntimeError("late_review_writer_history_incomplete")
    seen: set[int] = set()
    providers: set[str] = set()
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise RuntimeError("late_review_writer_history_incomplete")
        iteration = attempt.get("iteration")
        provider = attempt.get("provider")
        model = attempt.get("model")
        adapter = attempt.get("adapter")
        if (
            type(iteration) is not int or iteration < 1
            or not isinstance(provider, str) or not provider.strip()
            or not isinstance(model, str) or not model.strip()
            or not isinstance(adapter, str) or not adapter.strip()
            or type(attempt.get("returncode")) is not int
        ):
            raise RuntimeError("late_review_writer_history_incomplete")
        seen.add(iteration)
        providers.add(provider)
    if seen != set(range(1, iterations + 1)):
        raise RuntimeError("late_review_writer_history_incomplete")
    # Router choice and last persisted executor choice may be conservatively
    # broader than the observed attempts; they must never make the exclusion
    # set narrower if there was an unrecorded handoff.
    checkpoint = dict(job.get("checkpoint") or {})
    route = dict((job.get("result") or {}).get("route") or job.get("route") or {})
    strategy = dict(route.get("strategy") or {})
    for choice in (checkpoint.get("executor_choice"), strategy.get("executor")):
        if choice is None:
            continue
        if not isinstance(choice, dict) or not str(choice.get("provider") or "").strip():
            raise RuntimeError("late_review_writer_history_incomplete")
        providers.add(str(choice["provider"]))
    return tuple(sorted(providers))


def _git(workspace: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(workspace), *args],
        capture_output=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("late_review_git_evidence_unavailable")
    return proc.stdout.decode("utf-8", errors="replace").strip()


def accepted_diff(job: dict[str, Any], workspace_root: Path) -> str:
    """Read the exact *committed* source-to-head diff without editing job files."""
    result = dict(job.get("result") or {})
    evidence = dict(result.get("diff") or {})
    source, head = str(job.get("source_commit") or ""), str(result.get("commit") or "")
    expected = str(evidence.get("diff_hash") or "")
    workspace_raw = str(job.get("workspace") or "")
    root = workspace_root.resolve()
    workspace = Path(workspace_raw).resolve()
    if (
        re.fullmatch(r"[0-9a-f]{40}", source) is None
        or re.fullmatch(r"[0-9a-f]{40}", head) is None
        or re.fullmatch(r"[0-9a-f]{64}", expected) is None
        or not workspace_raw or workspace == root
        or not workspace.is_relative_to(root)
        or not workspace.is_dir()
        or evidence.get("diff_truncated") is True
    ):
        raise RuntimeError("late_review_exact_diff_unavailable")
    for revision in (source, head):
        if _git(workspace, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}") != revision:
            raise RuntimeError("late_review_commit_identity_mismatch")
    proc = subprocess.run(
        ["git", "-C", str(workspace), "diff", "--binary", source, head],
        capture_output=True,
        timeout=45,
        check=False,
    )
    if proc.returncode != 0 or hashlib.sha256(proc.stdout).hexdigest() != expected:
        raise RuntimeError("late_review_accepted_diff_mismatch")
    return proc.stdout.decode("utf-8", errors="replace")


class LateReviewStore:
    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def ensure(self) -> None:
        with self.storage.connect() as conn:
            conn.execute(LATE_REVIEW_DDL)
            conn.commit()

    def find(self, identity: dict[str, Any]) -> dict[str, Any] | None:
        """Check durable claim before Router staffing; this performs no model call."""
        self.ensure()
        with self.storage.connect() as conn:
            row = conn.execute(
                """SELECT * FROM cp_pm_late_review_attempts
                WHERE plan_id=%s AND work_order_id=%s AND job_id=%s
                  AND expected_head=%s AND checkpoint_id=%s""",
                (
                    identity["plan_id"], identity["work_order_id"], identity["job_id"],
                    identity["expected_head"], identity["checkpoint_id"],
                ),
            ).fetchone()
        if row is None:
            return None
        actual = dict(row)
        if any(
            actual.get(key) != identity[key]
            for key in ("project_id", "checkpoint_key", "pr_number",
                        "source_commit", "branch", "diff_hash")
        ) or sorted(actual["writer_providers"]) != identity["writer_providers"]:
            raise RuntimeError("late_review_claim_identity_conflict")
        return actual

    def claim(self, identity: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """One durable model-call slot per exact head and blocked checkpoint."""
        self.ensure()
        with self.storage.connect() as conn:
            row = conn.execute(
                """INSERT INTO cp_pm_late_review_attempts
                (plan_id,work_order_id,job_id,project_id,checkpoint_id,checkpoint_key,
                 pr_number,source_commit,branch,expected_head,diff_hash,writer_providers,
                 status,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'claimed',%s,%s)
                ON CONFLICT (plan_id,work_order_id,job_id,expected_head,checkpoint_id)
                DO NOTHING RETURNING *""",
                (
                    identity["plan_id"], identity["work_order_id"], identity["job_id"],
                    identity["project_id"], identity["checkpoint_id"],
                    identity["checkpoint_key"], identity["pr_number"],
                    identity["source_commit"], identity["branch"],
                    identity["expected_head"], identity["diff_hash"],
                    json.dumps(identity["writer_providers"]), now(), now(),
                ),
            ).fetchone()
            created = row is not None
            if row is None:
                row = conn.execute(
                    """SELECT * FROM cp_pm_late_review_attempts
                    WHERE plan_id=%s AND work_order_id=%s AND job_id=%s
                      AND expected_head=%s AND checkpoint_id=%s""",
                    (identity["plan_id"], identity["work_order_id"], identity["job_id"],
                     identity["expected_head"], identity["checkpoint_id"]),
                ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("late_review_claim_unavailable")
        actual = dict(row)
        for field in (
            "project_id", "checkpoint_key", "pr_number", "source_commit",
            "branch", "diff_hash",
        ):
            if actual.get(field) != identity[field]:
                raise RuntimeError("late_review_claim_identity_conflict")
        if sorted(actual["writer_providers"]) != identity["writer_providers"]:
            raise RuntimeError("late_review_writer_identity_changed")
        return actual, created

    def finish(
        self, attempt_id: int, *, status: str, reviewer: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None, attestation: dict[str, Any] | None = None,
    ) -> int | None:
        if status not in {"no_capacity", "failed", "passed", "uncertain"}:
            raise ValueError("Invalid late-review status")
        reviewer = reviewer or {}
        if (status in {"passed", "failed"}) != (attestation is not None):
            raise ValueError("Definitive structured review outcomes require an attestation")
        with self.storage.connect() as conn:
            row = conn.execute(
                """UPDATE cp_pm_late_review_attempts
                SET status=%s, reviewer_provider=%s, reviewer_model=%s,
                    result=%s::jsonb, updated_at=%s
                WHERE id=%s AND status='claimed' RETURNING id""",
                (status, reviewer.get("provider"), reviewer.get("id"),
                 json.dumps(result or {}), now(), attempt_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("late_review_attempt_already_finalized")
            attestation_id = None
            if attestation is not None:
                saved = conn.execute(
                    """INSERT INTO cp_pm_late_review_attestations
                    (attempt_id,payload,payload_sha256,created_at)
                    VALUES (%s,%s::jsonb,%s,%s) RETURNING id""",
                    (attempt_id, json.dumps(attestation), _digest(attestation), now()),
                ).fetchone()
                if saved is None:
                    raise RuntimeError("late_review_attestation_insert_failed")
                attestation_id = int(saved["id"])
            conn.commit()
        return attestation_id

    def get_attestation(self, attestation_id: int) -> dict[str, Any] | None:
        self.ensure()
        with self.storage.connect() as conn:
            row = conn.execute(
                """SELECT a.id, a.payload, a.payload_sha256, t.status, t.id AS attempt_id,
                          t.plan_id, t.work_order_id, t.job_id, t.project_id,
                          t.checkpoint_id, t.checkpoint_key, t.pr_number,
                          t.source_commit, t.branch, t.expected_head, t.diff_hash,
                          t.writer_providers, t.reviewer_provider, t.reviewer_model
                FROM cp_pm_late_review_attestations a
                JOIN cp_pm_late_review_attempts t ON t.id=a.attempt_id
                WHERE a.id=%s""",
                (attestation_id,),
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        if value["status"] != "passed" or _digest(value["payload"]) != value["payload_sha256"]:
            raise RuntimeError("late_review_attestation_integrity_failure")
        return value

    def active_count(self) -> int:
        self.ensure()
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM cp_pm_late_review_attempts WHERE status='claimed'"
            ).fetchone()
        return int(row["n"])

    def status(self, *, plan_id: str, job_id: str) -> dict[str, Any] | None:
        self.ensure()
        with self.storage.connect() as conn:
            row = conn.execute(
                """SELECT t.id,t.status,t.expected_head,t.checkpoint_id,t.reviewer_provider,
                          t.reviewer_model,a.id AS attestation_id
                FROM cp_pm_late_review_attempts t
                LEFT JOIN cp_pm_late_review_attestations a ON a.attempt_id=t.id
                WHERE t.plan_id=%s AND t.job_id=%s ORDER BY t.id DESC LIMIT 1""",
                (plan_id, job_id),
            ).fetchone()
        return dict(row) if row else None


class LateReviewService:
    def __init__(self, storage: Any, engine: Any, orchestrator: Any) -> None:
        self.storage = storage
        self.engine = engine
        self.orchestrator = orchestrator
        self.store = LateReviewStore(storage)
        self._tasks: set[asyncio.Task] = set()

    def _snapshot(self, envelope: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        plan_id = str(envelope.plan_id)
        plan = self.orchestrator.store.orchestration(plan_id)
        definition = self.storage.get_execution_plan(plan_id) or {}
        if (
            not plan or plan.get("lifecycle") != "active"
            or str(plan.get("project_id") or "") != envelope.project_id
            or str(plan.get("status") or "") != "blocked"
        ):
            raise RuntimeError("late_review_plan_not_currently_blocked")
        tracked = next(
            (dict(item) for item in self.orchestrator.store.work_orders(plan_id)
             if item.get("work_order_id") == envelope.work_order_id), None,
        )
        if (
            tracked is None or tracked.get("lifecycle") != "active"
            or tracked.get("state") != "blocked"
            or tracked.get("job_id") != envelope.job_id
            or tracked.get("pr_number") != envelope.pr_number
            or (tracked.get("detail") or {}).get("reason")
            != "pm_merge_ineligible:required_review_independence_not_satisfied"
        ):
            raise RuntimeError("late_review_blocked_work_order_identity_changed")
        checkpoints = self.orchestrator.store.checkpoints(plan_id, work_order_id=envelope.work_order_id)
        latest = checkpoints[-1] if checkpoints else {}
        if (
            latest.get("id") != envelope.checkpoint_id
            or latest.get("checkpoint_key") != envelope.checkpoint_key
            or latest.get("state") != "blocked" or latest.get("kind") != "blocked"
            or latest.get("job_id") != envelope.job_id
            or (latest.get("evidence") or {}).get("reason")
            != "pm_merge_ineligible:required_review_independence_not_satisfied"
        ):
            raise RuntimeError("late_review_checkpoint_stale")
        job = self.storage.get(str(envelope.job_id))
        result = dict((job or {}).get("result") or {})
        strategy = dict((result.get("route") or {}).get("strategy") or {})
        policy = dict(strategy.get("review_policy") or {})
        if (
            not job or job.get("project_id") != envelope.project_id
            or job.get("status") != "completed"
            or str(job.get("source_commit") or "") != envelope.source_commit
            or str(job.get("branch") or "") != envelope.branch
            or str(result.get("commit") or "") != envelope.expected_head
            or result.get("status") != "accepted" or result.get("delivery_finalized") is not True
            or not (result.get("verification") or {}).get("passed")
            or not (job.get("progress") or {}).get("required_checks_passed")
            or (result.get("review") or {}).get("verdict") != "pass"
            or not policy.get("required") or not policy.get("independent")
            or policy.get("independence_satisfied") is not False
        ):
            raise RuntimeError("late_review_job_delivery_identity_changed")
        return {**dict(plan), "plan": definition.get("plan") or {}}, tracked, dict(job)

    async def _preflight(self, envelope: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], str]:
        plan, tracked, job = self._snapshot(envelope)
        writers = writer_providers(job)
        diff_text = accepted_diff(job, self.engine.workspace_root)
        audit = self.orchestrator.merge_audit.get(
            plan_id=envelope.plan_id, work_order_id=envelope.work_order_id,
            expected_head=envelope.expected_head,
        )
        if audit is not None:
            raise RuntimeError("late_review_existing_merge_audit")
        pr = await self.engine.ddev.github_pull_request(
            project_id=envelope.project_id, pr_number=envelope.pr_number,
        )
        ci = await self.engine.ddev.github_ci(
            project_id=envelope.project_id, commit=envelope.expected_head,
        )
        if ci.get("state") != "success" or ci.get("commit") != envelope.expected_head:
            raise RuntimeError("late_review_fresh_ci_not_success")
        config = project_config(envelope.project_id)
        eligibility = evaluate_pm_merge(
            project=config, plan=plan, tracked=tracked, job=job, pr=pr, current_ci=ci,
        )
        if (
            eligibility.manual_only or eligibility.requires_human
            or eligibility.blockers != ("required_review_independence_not_satisfied",)
        ):
            raise RuntimeError("late_review_other_merge_gates_not_satisfied")
        return plan, tracked, job, {"writers": writers, "pr": pr, "ci": ci}, diff_text

    def _identity(self, envelope: Any, job: dict[str, Any], writers: tuple[str, ...]) -> dict[str, Any]:
        return {
            "plan_id": envelope.plan_id, "work_order_id": envelope.work_order_id,
            "job_id": envelope.job_id, "project_id": envelope.project_id,
            "checkpoint_id": envelope.checkpoint_id, "checkpoint_key": envelope.checkpoint_key,
            "pr_number": envelope.pr_number, "source_commit": envelope.source_commit,
            "branch": envelope.branch, "expected_head": envelope.expected_head,
            "diff_hash": str((job["result"]["diff"] or {}).get("diff_hash") or ""),
            "writer_providers": list(writers),
        }

    async def request(self, envelope: Any) -> dict[str, Any]:
        _, _, job, extra, diff_text = await self._preflight(envelope)
        identity = self._identity(envelope, job, extra["writers"])
        previous = self.store.find(identity)
        if previous is not None:
            return {
                "status": str(previous["status"]), "attempt_id": int(previous["id"]),
                "replayed": True, "head": envelope.expected_head,
            }
        # Reviewer *staffing* consumes no model call. No-capacity does not
        # spend the unique model-call slot, so a later explicit PM control may
        # recheck capacity without resetting or replaying a failed invocation.
        provider_state = dict((job.get("checkpoint") or {}).get("provider_state") or {})
        unavailable = {
            "healthy": False, "available": False, "quota_pressure": 1.0,
            "error_rate": 1.0, "latency_ms": 0,
        }
        for provider in extra["writers"]:
            provider_state["provider:" + provider] = dict(unavailable)
        request_id = "late-review:" + _digest(identity)[:24]
        try:
            response = await self.engine.router.staff({
                "request_id": request_id,
                "project_id": envelope.project_id, "role": "reviewer",
                "profile": "critical",
                "semantic": dict((job.get("task") or {}).get("semantic") or {}),
                "provider_state": provider_state,
            })
            choice = dict(response.get("choice") or {})
            validate_model_choice(choice)
            if (
                str(response.get("role") or "") != "reviewer"
                or str(response.get("request_id") or "") != request_id
                or not choice.get("provider")
                or choice["provider"] in extra["writers"]
            ):
                raise RuntimeError("late_review_independent_staffing_unavailable")
        except Exception:
            return {"status": "no_capacity", "head": envelope.expected_head}

        # Atomic claim occurs strictly *before* any reviewer model invocation.
        # Another concurrent caller may have claimed after our read-only lookup;
        # only the winner may schedule an invocation.
        attempt, created = self.store.claim(identity)
        if not created:
            return {
                "status": str(attempt["status"]), "attempt_id": int(attempt["id"]),
                "replayed": True, "head": envelope.expected_head,
            }
        attempt_id = int(attempt["id"])
        task = asyncio.create_task(
            self._execute_claim(envelope, job, extra, diff_text, identity, attempt_id, choice)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return {"status": "claimed", "attempt_id": attempt_id, "head": envelope.expected_head}

    async def _execute_claim(
        self, envelope: Any, job: dict[str, Any],
        extra: dict[str, Any], diff_text: str,
        identity: dict[str, Any], attempt_id: int,
        choice: dict[str, Any],
    ) -> dict[str, Any]:
        """Run at most one reviewer outside the PM Bridge HTTP request lifetime."""
        try:
            original = Path(str(job["workspace"])).resolve()
            with tempfile.TemporaryDirectory(prefix="pcp-late-review-") as temp:
                checkout = Path(temp) / "review"
                clone = subprocess.run(
                    ["git", "clone", "--quiet", "--no-local", "--no-checkout", "--", str(original), str(checkout)],
                    capture_output=True, timeout=90, check=False,
                )
                if clone.returncode != 0:
                    raise RuntimeError("late_review_isolated_clone_failed")
                subprocess.run(
                    ["git", "-C", str(checkout), "checkout", "--quiet", "--detach", envelope.expected_head],
                    capture_output=True, timeout=45, check=True,
                )
                if _git(checkout, "rev-parse", "HEAD") != envelope.expected_head:
                    raise RuntimeError("late_review_checkout_head_changed")
                adapter = build_adapter(
                    choice["adapter"], choice["model"], choice.get("reasoning_effort"),
                )
                run = await adapter.run(
                    workspace=checkout,
                    prompt=evaluator_prompt(
                        task=dict(job.get("task") or {}), diff=diff_text,
                        verification=dict((job["result"] or {}).get("verification") or {}),
                        work_order=dict((job.get("checkpoint") or {}).get("work_order") or {}),
                        baseline=dict((job.get("checkpoint") or {}).get("project_baseline") or {}),
                    ),
                    mode="evaluate", timeout=600,
                )
                if (
                    _git(checkout, "rev-parse", "HEAD") != envelope.expected_head
                    or _git(checkout, "status", "--porcelain")
                ):
                    raise RuntimeError("late_review_read_only_checkout_modified")
            if (
                run.provider_failed or run.returncode != 0
                or run.adapter != choice["adapter"]
                or run.model != choice["model"]
            ):
                raise RuntimeError("late_review_provider_execution_uncertain")
            output = (run.output or "").strip()
            if (
                not output.startswith(("PASS\n", "FAIL\n"))
                or "\nREVIEW_JSON:" not in output
            ):
                raise RuntimeError("late_review_structured_protocol_required")
            # Legacy PASS/FAIL text is not sufficient for a critical trust gate.
            marker_line = next(
                (line for line in output.splitlines()[1:]
                 if line.strip().startswith("REVIEW_JSON:")), None,
            )
            try:
                structured = json.loads(marker_line.split("REVIEW_JSON:", 1)[1])
            except (ValueError, TypeError, AttributeError) as exc:
                raise RuntimeError("late_review_structured_protocol_invalid") from exc
            report = parse_review_output(output)
            if (
                not isinstance(structured, dict)
                or not {"verdict", "summary", "findings", "jit_context_used"} <= set(structured)
                or not report.protocol_valid
                or report.verdict.upper() != output.splitlines()[0]
                or structured.get("verdict") != report.verdict
            ):
                raise RuntimeError("late_review_structured_protocol_invalid")
            # Review is useful only while source, PR and gates still match.
            await self._preflight(envelope)
            verdict = "passed" if report.verdict == "pass" and not report.findings else "failed"
            # Both definitive PASS and FAIL have immutable provenance. Only
            # PASS can ever become a trusted merge-eligibility proof.
            attestation = {
                **identity,
                "attempt_id": attempt_id,
                "reviewer_provider": choice["provider"],
                "reviewer_model": choice["id"],
                "reviewer_adapter": choice["adapter"],
                "verdict": "pass" if verdict == "passed" else "fail",
                "finding_count": len(report.findings),
                "protocol_valid": True,
                "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            }
            attestation_id = self.store.finish(
                attempt_id, status=verdict, reviewer=choice,
                result={
                    "verdict": report.verdict,
                    "findings": [
                        {"id": f.id, "severity": f.severity, "category": f.category,
                         "message": f.message[:600]} for f in report.findings[:12]
                    ],
                    "summary": report.summary[:1000], "usage": normalize_usage(run.usage),
                },
                attestation=attestation,
            )
            return {
                "status": verdict, "attempt_id": attempt_id,
                "attestation_id": attestation_id, "head": envelope.expected_head,
                "reviewer_provider": choice["provider"], "reviewer_model": choice["id"],
            }
        except BaseException:
            # Cancellation/timeouts are uncertain; a new control cannot replay
            # the same model call, and Guardian sees any still-claimed attempt.
            self.store.finish(
                attempt_id, status="uncertain", reviewer=choice,
                result={"reason": "review_invocation_or_preflight_uncertain"},
            )
            return {"status": "uncertain", "attempt_id": attempt_id, "head": envelope.expected_head}

    async def stop(self) -> None:
        """Cancel in-flight reviews and wait for their durable uncertain audit."""
        pending = tuple(self._tasks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def trusted_proof(
        self, *, plan: dict[str, Any], tracked: dict[str, Any],
        job: dict[str, Any], attestation_id: int,
        checkpoint_id: int, checkpoint_key: str,
    ) -> LateReviewProof | None:
        att = self.store.get_attestation(attestation_id)
        if att is None:
            return None
        data = dict(att["payload"])
        writers = writer_providers(job)
        if (
            data.get("verdict") != "pass" or data.get("protocol_valid") is not True
            or data.get("writer_providers") != list(writers)
            or data.get("reviewer_provider") in writers
            or not data.get("reviewer_provider") or not data.get("reviewer_model")
            or att.get("attempt_id") != data.get("attempt_id")
            or data.get("checkpoint_id") != checkpoint_id
            or data.get("checkpoint_key") != checkpoint_key
        ):
            raise RuntimeError("late_review_attestation_not_independent")
        for field in (
            "plan_id", "work_order_id", "job_id", "source_commit", "branch",
            "expected_head", "diff_hash", "pr_number", "checkpoint_id", "checkpoint_key",
            "reviewer_provider", "reviewer_model",
        ):
            if att.get(field) != data.get(field):
                raise RuntimeError("late_review_attestation_identity_mismatch")
        proof = LateReviewProof(
            attestation_id=int(att["id"]), plan_id=data["plan_id"],
            work_order_id=data["work_order_id"], job_id=data["job_id"],
            source_commit=data["source_commit"], branch=data["branch"],
            expected_head=data["expected_head"], pr_number=data["pr_number"],
            diff_hash=data["diff_hash"], checkpoint_id=data["checkpoint_id"],
            checkpoint_key=data["checkpoint_key"],
            writer_providers=tuple(writers),
            reviewer_provider=data["reviewer_provider"],
            reviewer_model=data["reviewer_model"], verdict="pass",
        )
        return proof if proof.matches(plan, tracked, job) else None

    async def release(self, envelope: Any) -> dict[str, Any]:
        plan, tracked, job, extra, _ = await self._preflight(envelope)
        att_id = int(envelope.attestation_id)
        proof = self.trusted_proof(
            plan=plan, tracked=tracked, job=job, attestation_id=att_id,
            checkpoint_id=envelope.checkpoint_id, checkpoint_key=envelope.checkpoint_key,
        )
        if proof is None:
            raise RuntimeError("late_review_no_valid_attestation")
        decision = evaluate_pm_merge(
            project=project_config(envelope.project_id), plan=plan, tracked=tracked,
            job=job, pr=extra["pr"], current_ci=extra["ci"], late_review_proof=proof,
        )
        if not decision.eligible or decision.requires_human or decision.blockers:
            raise RuntimeError("late_review_merge_gate_still_blocked")
        if self.orchestrator.merge_audit.get(
            plan_id=envelope.plan_id, work_order_id=envelope.work_order_id,
            expected_head=envelope.expected_head,
        ) is not None:
            raise RuntimeError("late_review_merge_audit_replay_rejected")
        detail = dict(tracked.get("detail") or {})
        detail["late_review_release"] = {
            "attestation_id": proof.attestation_id,
            "checkpoint_id": proof.checkpoint_id,
            "checkpoint_key": proof.checkpoint_key,
            "head": proof.expected_head,
        }
        detail.pop("reason", None)
        checkpoint = self.orchestrator._checkpoint_transition(
            tracked, kind="late_review_released", state="awaiting_merge",
            job=job, pr=extra["pr"], detail=detail,
        )
        self.orchestrator.store.update_plan(envelope.plan_id, status="waiting_merge")
        return {
            "status": "released", "attestation_id": proof.attestation_id,
            "checkpoint_id": checkpoint["id"], "head": proof.expected_head,
        }
