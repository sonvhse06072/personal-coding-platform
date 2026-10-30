"""Default-OFF PCP-local admission, concrete readers and bounded execution.

Dedicated startup installs no scheduler or model call. An authenticated one-shot
request must bind separately installed operational authority and live service
observations to the durable receipt. Legacy execution/replay remains forbidden.
"""
from __future__ import annotations

import hashlib
import inspect
from contextlib import contextmanager
import stat
import subprocess
import sys
import tempfile
from copy import deepcopy
from dataclasses import dataclass
import json
import math
import os
import time
from typing import Any

from .pcp_local_task_queue import (
    LocalSourceQueueStore, LocalSourceTask, TaskStop, verify_issue,
    require, PROJECT_ID, REPOSITORY, MARKER,
)
from .pcp_local_worker_admission import check_worker_admission

EVIDENCE_PARTS = frozenset({"project", "baseline", "isolation", "provider", "budget"})
LAUNCH_RECEIPT_FIELDS = frozenset({
    "job_id", "state", "source_commit", "baseline_revision",
})
OBSERVER_PARTS = EVIDENCE_PARTS | {"writer", "publisher", "model_choice"}


def claimed_source_receipt(task: LocalSourceTask) -> dict[str, Any]:
    """Complete immutable identity, shared with the transactional registrar."""
    return {
        **vars(task), "allowed_paths": list(task.allowed_paths),
        "state": "claimed", "generation": 1, "job_id": stable_job_id(task),
    }


def exact_value(actual: Any, expected: Any) -> bool:
    """JSON equality including types (True must never stand for generation 1)."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(
            exact_value(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            exact_value(a, b) for a, b in zip(actual, expected))
    return actual == expected


@dataclass(frozen=True)
class RuntimeObservation:
    """A trusted in-process reader's short-lived observation, never HTTP input.

    Authentic readers must be installed by a separately admitted Runtime caller.
    This type supplies no signing/Host authority, reader, credential or defaults.
    """

    value: dict[str, Any]
    revision: str
    observed_at: float
    valid_until: float


class RuntimeTaskAttestor:
    """Compose fresh Runtime/Executor observations for one exact source issue."""

    def __init__(self, *, issue_number: int, readers: dict[str, Any],
                 clock=time.monotonic) -> None:
        require(type(issue_number) is int and issue_number > 0,
                "pcp_local_approved_issue_required")
        require(type(readers) is dict and set(readers) == OBSERVER_PARTS
                and all(callable(r) for r in readers.values()) and callable(clock),
                "pcp_local_trusted_readers_required")
        self.issue_number = issue_number
        self.readers = dict(readers)
        self.clock = clock
        self._identity = None
        self._observed: dict[str, RuntimeObservation] = {}

    def require_fresh(self) -> None:
        current = self.clock()
        require(type(current) in (int, float) and math.isfinite(current),
                "pcp_local_observation_clock_invalid")
        require(set(self._observed) == OBSERVER_PARTS,
                "pcp_local_observers_not_checked")
        for observation in self._observed.values():
            require(type(observation) is RuntimeObservation
                    and type(observation.value) is dict
                    and type(observation.revision) is str
                    and len(observation.revision) == 64
                    and all(c in "0123456789abcdef" for c in observation.revision)
                    and all(type(v) in (int, float) and math.isfinite(v)
                            for v in (observation.observed_at, observation.valid_until))
                    and observation.observed_at <= current < observation.valid_until
                    and 0 < observation.valid_until - observation.observed_at <= 60,
                    "pcp_local_observation_expired_or_invalid")

    async def observe(self, task: LocalSourceTask) -> dict[str, Any]:
        require(task.issue_number == self.issue_number
                and task.project_id == PROJECT_ID and task.repository == REPOSITORY,
                "pcp_local_approved_issue_mismatch")
        observed = {}
        for key in sorted(OBSERVER_PARTS):
            result = self.readers[key](task)
            if inspect.isawaitable(result):
                result = await result
            require(type(result) is RuntimeObservation,
                    "pcp_local_typed_observation_required")
            observed[key] = deepcopy(result)
        self._observed = observed
        self.require_fresh()
        values = {k: v.value for k, v in observed.items()}
        writer = values["writer"]
        # Readers exclude ONLY this exact task's reserved job from this view;
        # its receipt/job ownership is independently locked in the transaction.
        require(set(writer) == {"project_id", "workspace_mode", "lease", "other_job_ids"}
                and writer["project_id"] == PROJECT_ID
                and writer["workspace_mode"] == "isolated_clone"
                and exact_value(writer["other_job_ids"], []),
                "pcp_local_writer_not_attested")
        lease = writer["lease"]
        require(lease is None or (
            type(lease) is dict
            and set(lease) == {"project_id", "owner_job_id", "generation", "state"}
            and lease["project_id"] == PROJECT_ID and lease["state"] == "released"
            and type(lease["generation"]) is int and lease["generation"] >= 1
            and type(lease["owner_job_id"]) is str and len(lease["owner_job_id"]) == 32
            and all(c in "0123456789abcdef" for c in lease["owner_job_id"])
        ), "pcp_local_lease_not_attested")
        require(exact_value(values["publisher"], {
            "project_id": PROJECT_ID, "repository": REPOSITORY,
            "executor_only": True, "allow_create_pr": True,
            "allow_merge": False, "credential_in_agent": False,
        }), "pcp_local_publisher_not_attested")
        choice = values["model_choice"]
        require(set(choice) == {"id", "adapter", "model", "reasoning_effort"}
                and all(type(v) is str and v for v in choice.values()),
                "pcp_local_model_identity_invalid")
        from .config import model_config
        from .model_capabilities import ModelCapabilityError, validate_model_choice
        try:
            validate_model_choice(choice)
        except ModelCapabilityError as exc:
            raise TaskStop("pcp_local_registered_model_denied") from exc
        registered = model_config(choice["id"])
        require(registered.get("kind") == "agent"
                and "executor" in registered.get("roles", [])
                and choice["adapter"] == "codex_cli"
                and choice["model"] == values["provider"].get("model")
                and choice["reasoning_effort"] == values["provider"].get("effort"),
                "pcp_local_provider_choice_mismatch")
        identity = {k: {"value": v.value, "revision": v.revision}
                    for k, v in observed.items()}
        require(self._identity is None or exact_value(identity, self._identity),
                "pcp_local_observation_identity_changed")
        self._identity = deepcopy(identity)
        return {k: deepcopy(values[k]) for k in EVIDENCE_PARTS}

    def binding(self, task: LocalSourceTask) -> dict[str, Any]:
        self.require_fresh()
        require(self._identity is not None, "pcp_local_observers_not_checked")
        return {
            "receipt": claimed_source_receipt(task),
            "observations": deepcopy(self._identity),
            "reservation": "pcp_local_isolated_queued_job",
            "model_execution_proof": "NOT_ATTESTED",
        }


def require_operational_project(project: dict[str, Any]) -> None:
    """Same project policy before receipt registration and inside job insertion.

    The queued row reserves admission; execution subsequently acquires the
    exclusive durable lease. Requiring the old source-only False setting here
    stranded a claim after readiness had accepted the operational True setting.
    """
    runtime = project.get('runtime') or {}
    rights = project.get('autonomy') or {}
    require(project.get('repository') == REPOSITORY
            and project.get('base_branch') == 'main'
            and project.get('registration_status') == 'approved'
            and runtime.get('workspace_mode') == 'isolated_clone'
            and runtime.get('developer_permission_mode') == 'bounded'
            and runtime.get('exclusive_project_lease') is True
            and (project.get('ddev') or {}).get('enabled') is True
            and all(rights.get(k) is True for k in (
                'allow_commit', 'allow_push_ai_branch', 'allow_create_pr'))
            and rights.get('allow_production_deploy') is False,
            'pcp_local_project_not_operational')


class RuntimeTaskLauncher:
    """One registration attempt and one existing-queue submission, no worker."""

    def __init__(self, *, engine: Any, attestor: RuntimeTaskAttestor,
                 github: Any, receipts: LocalSourceQueueStore) -> None:
        self.engine = engine
        self.attestor = attestor
        self.github = github
        self.receipts = receipts
        self.attempted = False
        self.task = None
        self.source_binding = None
        self.recovery = None

    async def _recheck(self, task: LocalSourceTask) -> None:
        operational_flag()
        self.receipts.read_claimed(task, job_id=stable_job_id(task))
        latest = await self.github.local_source_issue(issue_number=task.issue_number)
        checked = self.recovery.verify_issue(latest) if self.recovery is not None else verify_issue(
            latest, issue_number=task.issue_number, body_sha256=task.body_sha256,
            base_sha=task.base_sha, baseline_revision=task.baseline_revision,
            baseline_source_commit=task.baseline_source_commit,
        )
        require(checked == task, "pcp_local_task_identity_changed")
        facts = await self.attestor.observe(task)
        # Reuse the unchanged admission policy with the original pending identity.
        check_worker_admission(task, receipt={**claimed_source_receipt(task),
            "state": "pending", "generation": 0, "job_id": None}, recovery=self.recovery, **facts)
        self.require_registration()

    def require_registration(self) -> None:
        """Synchronous JIT gate, also run inside the insertion transaction."""
        operational_flag()
        if getattr(self, 'recovery', None) is not None:
            from .pcp_local_task_queue import RecoveryPermit
            require(type(self.recovery) is RecoveryPermit, 'claim_recovery_private_permit_required')
            self.recovery.require_task(self.task, self.recovery.value['repair_source'])
        self.attestor.require_fresh()
        require(self.engine.worker_task is None and not self.engine.active_jobs,
                "pcp_local_existing_worker_forbidden")
        require(self.engine.queue.empty(), "pcp_local_existing_queue_forbidden")
        require(type(self.task) is LocalSourceTask and self.attempted,
                "pcp_local_registration_not_prepared")
        from .config import project_config, project_baselines_doc
        from .baseline import resolve_project_baseline
        cfg = project_config(PROJECT_ID)
        revision = (project_baselines_doc().get("projects", {}).get(PROJECT_ID) or {})
        baseline = resolve_project_baseline(PROJECT_ID, self.task.baseline_revision)
        require_operational_project(cfg)
        require(revision.get("active_revision") == self.task.baseline_revision
                and baseline is not None and baseline.project_id == PROJECT_ID
                and baseline.source_commit == self.task.baseline_source_commit,
                "pcp_local_current_authority_changed")
        # Registration reserves a queued row; execution acquires its lease later.
        if self.source_binding is not None:
            require(exact_value(self.source_binding, self.attestor.binding(self.task)),
                    "pcp_local_registration_binding_changed")

    async def launch(self, *, task, goal, job_id, evidence) -> dict[str, Any]:
        require(not self.attempted, "pcp_local_launch_already_attempted")
        self.attempted = True  # Remains consumed across every uncertain outcome.
        self.task = task
        require(job_id == stable_job_id(task)
                and type(goal) is str and hashlib.sha256(goal.encode()).hexdigest() == task.goal_sha256,
                "pcp_local_launch_identity_invalid")
        await self._recheck(task)
        facts = {k: deepcopy(self.attestor._observed[k].value) for k in EVIDENCE_PARTS}
        decision = check_worker_admission(task, receipt={**claimed_source_receipt(task),
            "state": "pending", "generation": 0, "job_id": None}, **facts)
        require(exact_value(evidence, decision), "pcp_local_launch_evidence_changed")
        self.source_binding = self.attestor.binding(task)
        created = self.engine.create_job({
            "_job_id": job_id, "project_id": PROJECT_ID,
            "source_commit": task.base_sha, "baseline_revision": task.baseline_revision,
            "task": {"title": f"PCP-local issue #{task.issue_number}", "description": goal,
                     "task_type": "implementation"},
        }, _pcp_local_registration=self)
        require(created == job_id, "pcp_local_registration_ack_invalid")
        # A revoked observation after commit preserves the queued row and claim.
        await self._recheck(task)
        await self.engine.enqueue(job_id)
        return {"job_id": job_id, "state": "queued", "source_commit": task.base_sha,
                "baseline_revision": task.baseline_revision}


def source_worker_flags() -> None:
    """Two independent opt-ins. All are ABSENT from shipped DDEV Compose."""
    require(
        os.getenv("PCP_LOCAL_TASK_SOURCE_ENABLED", "") == "owner-approved"
        and os.getenv("PCP_LOCAL_TASK_WORKER_ENABLED", "") == "owner-approved",
        "pcp_local_worker_disabled",
    )


def operational_flag() -> None:
    source_worker_flags()
    # A source-only project approval must NOT automatically authorize model
    # calls, provider egress, host Docker or a privileged delivery publisher.
    require(
        os.getenv("PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION", "") == "owner-approved",
        "pcp_local_live_activation_not_approved",
    )


def stable_job_id(task: LocalSourceTask) -> str:
    """Stable job identity, does not allocate, authorize, or submit a job."""
    data = (
        f"pcp-local:v1:{task.repository}:{task.issue_number}:"
        f"{task.body_sha256}:{task.base_sha}:{task.baseline_revision}"
    )
    return hashlib.sha256(data.encode("ascii")).hexdigest()[:32]


class LocalWorkerLoop:
    """One-shot bounded scan/verification. NEVER an independent daemon.

    trusted_attestor is a future separately reviewed in-process component,
    not an object/value taken from GitHub or an HTTP request body.
    launcher is a future separately approved Runtime-owned durable job
    adapter. Neither is connected to live Runtime under this source change.
    """

    def __init__(self, *, receipts: LocalSourceQueueStore, github: Any,
                 trusted_attestor: Any | None = None,
                 launcher: Any | None = None) -> None:
        self.receipts = receipts
        self.github = github
        self.trusted_attestor = trusted_attestor
        self.launcher = launcher

    async def _prepare(self) -> tuple[
        LocalSourceTask, dict[str, Any], dict[str, Any], str,
        dict[str, Any]
    ] | None:
        source_worker_flags()
        from .pcp_local_task_queue import enabled
        require(not enabled(), 'claim_recovery_fresh_admission_disabled')
        from .pcp_local_recovery import enabled as held_enabled
        require(not held_enabled(), 'held_admission_forbidden')
        # Do not even read DB or GitHub if no approved trusted evidence
        # integration was installed. Model/issue-reported proofs are invalid.
        require(self.trusted_attestor is not None
                and callable(getattr(self.trusted_attestor, "observe", None)),
                "pcp_local_trusted_attestor_not_installed")
        receipt = self.receipts.next_pending()
        if receipt is None:
            return None
        require(receipt.get("project_id") == PROJECT_ID
                and receipt.get("repository") == REPOSITORY
                and receipt.get("state") == "pending"
                and receipt.get("generation") == 0
                and receipt.get("job_id") is None,
                "pcp_local_pending_receipt_changed")
        issue_number = receipt["issue_number"]
        if isinstance(self.trusted_attestor, RuntimeTaskAttestor):
            require(issue_number == self.trusted_attestor.issue_number,
                    "pcp_local_approved_issue_mismatch")
        # Executor token stays behind the existing narrow fixed-repo GET API.
        source = await self.github.local_source_issue(issue_number=issue_number)
        require(type(source) is dict, "pcp_local_source_shape_invalid")
        task = verify_issue(
            source,
            issue_number=issue_number,
            body_sha256=receipt["body_sha256"],
            base_sha=receipt["base_sha"],
            baseline_revision=receipt["baseline_revision"],
            baseline_source_commit=receipt["baseline_source_commit"],
        )
        # Independently attest the already-approved ProjectBaseline, source,
        # workspace, lease, provider and budget against live trusted state.
        evidence = self.trusted_attestor.observe(task)
        if inspect.isawaitable(evidence):
            evidence = await evidence
        require(type(evidence) is dict and set(evidence) == EVIDENCE_PARTS,
                "pcp_local_evidence_shape_invalid")
        decision = check_worker_admission(
            task, receipt=receipt,
            project=evidence["project"], baseline=evidence["baseline"],
            isolation=evidence["isolation"], provider=evidence["provider"],
            budget=evidence["budget"],
        )
        require(
            decision.get("status") == "ADMISSION_EVIDENCE_CHECKED_NOT_DISPATCHED"
            and decision.get("can_start_agent") is False
            and decision.get("can_claim_lease") is False
            and decision.get("can_publish_or_merge") is False,
            "pcp_local_admission_not_authorizing",
        )
        # Runtime prompt originates from exactly the digest-checked issue;
        # it may not contain arbitrary runtime flags, secrets or commands.
        body = source["body"]
        try:
            payload = json.loads(body.strip()[len(MARKER):].strip())
            goal = payload["goal"]
        except (KeyError, TypeError, ValueError) as exc:
            raise TaskStop("pcp_local_goal_invalid") from exc
        require(type(goal) is str
                and hashlib.sha256(goal.encode("utf-8")).hexdigest()
                == task.goal_sha256,
                "pcp_local_goal_identity_changed")
        return task, deepcopy(receipt), decision, goal, deepcopy(evidence)

    async def preview_once(self) -> dict[str, Any]:
        """No claims, no external writes, no model. One oldest pending only."""
        current = await self._prepare()
        if current is None:
            return {"status": "PCP_LOCAL_QUEUE_IDLE_NOT_DISPATCHED",
                    "model_calls": 0}
        task, _, decision, _, _ = current
        return {
            "status": "PCP_LOCAL_SOURCE_VALIDATED_NOT_DISPATCHED",
            "issue_number": task.issue_number,
            "body_sha256": task.body_sha256,
            "source_commit": task.base_sha,
            "baseline_revision": task.baseline_revision,
            "task_key": task.task_key,
            "job_id_if_authorized": stable_job_id(task),
            "can_start_agent": False,
            "can_claim_lease": False,
            "requires_fresh_live_recheck": decision["requires_fresh_live_recheck"],
            "model_calls": 0,
        }

    async def execute_once(self) -> dict[str, Any]:
        """FUTURE B2.2c ONLY: reserve once, invoke preinstalled trusted adapter.

        This function is NEVER wired into a Runtime endpoint/startup in B2.2b.
        After a durable claim, a crash or uncertain launch is NOT retried:
        an independent operator must reconcile the exact existing job.
        """
        operational_flag()  # Check before DB/GitHub reads, claims or model.
        require(self.launcher is not None
                and callable(getattr(self.launcher, "launch", None)),
                "pcp_local_durable_launcher_not_installed")
        current = await self._prepare()
        if current is None:
            return {"status": "PCP_LOCAL_QUEUE_IDLE_NOT_DISPATCHED",
                    "model_calls": 0}
        task, receipt, decision, goal, initial_evidence = current
        require(decision.get("requires_fresh_live_recheck") is True,
                "pcp_local_live_recheck_required")
        job_id = stable_job_id(task)
        self.receipts.advance(
            task, expected_state="pending", expected_generation=0,
            target_state="claimed", job_id=job_id, worker_authorized=True,
        )
        # P1: receipt/source/lease evidence may change between the initial
        # validation and a successful durable CAS. Do not pass that old
        # snapshot to a launcher without a second independent read.
        # A failure AFTER claim remains claimed for manual reconciliation;
        # never run the model and never create a replacement job/retry.
        try:
            self.receipts.read_claimed(task, job_id=job_id)
            latest = await self.github.local_source_issue(
                issue_number=task.issue_number
            )
            latest_task = verify_issue(
                latest,
                issue_number=task.issue_number,
                body_sha256=task.body_sha256,
                base_sha=task.base_sha,
                baseline_revision=task.baseline_revision,
                baseline_source_commit=task.baseline_source_commit,
            )
            require(latest_task == task, "pcp_local_task_identity_changed")
            fresh = self.trusted_attestor.observe(task)
            if inspect.isawaitable(fresh):
                fresh = await fresh
            require(type(fresh) is dict and set(fresh) == EVIDENCE_PARTS,
                    "pcp_local_fresh_evidence_invalid")
            fresh_decision = check_worker_admission(
                task, receipt=receipt,
                project=fresh["project"], baseline=fresh["baseline"],
                isolation=fresh["isolation"], provider=fresh["provider"],
                budget=fresh["budget"],
            )
            require(fresh == initial_evidence and fresh_decision == decision,
                    "pcp_local_evidence_changed_after_claim")
            operational_flag()  # A revoked activation cannot reach launcher.
        except Exception as exc:
            raise TaskStop(
                "pcp_local_prelaunch_recheck_uncertain_do_not_retry"
            ) from exc
        # The trusted launcher must perform its own just-in-time project/
        # lease/provider checks BEFORE touching Runtime jobs or Codex.
        try:
            result = self.launcher.launch(
                task=task, goal=goal, job_id=job_id,
                evidence=decision,
            )
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            # Do NOT auto-retry: after claim, the actual launch side effect is
            # unknowable. Preserve claimed row, original job and counters.
            raise TaskStop("pcp_local_launch_uncertain_do_not_retry") from exc
        require(type(result) is dict and set(result) == LAUNCH_RECEIPT_FIELDS
                and result.get("job_id") == job_id
                and result.get("state") == "queued"
                and result.get("source_commit") == task.base_sha
                and result.get("baseline_revision") == task.baseline_revision,
                "pcp_local_launch_ack_ambiguous_do_not_retry")
        # Retain claim until independent durable Runtime job confirmation.
        # Never treat an unreviewed PR or successful model turn as delivered.
        response = {
            "status": "PCP_LOCAL_CLAIMED_AWAITING_JOB_RECONCILIATION",
            "issue_number": task.issue_number, "job_id": job_id,
            "receipt_generation": 1,
            "source_commit": task.base_sha,
            "model_execution_proof": "NOT_ATTESTED",
            "can_merge": False,
        }
        if isinstance(self.launcher, RuntimeTaskLauncher):
            response.update(runtime_job_state="queued", model_calls=0)
        return response


async def run_admitted_job(engine, readers, task):
    """Consume ONE registered queue item. This is not the legacy worker/replay.

    The receipt moves to running before any invocation. A crash thereafter is
    intentionally not replayable; all checkpoints/diffs/counters remain intact.
    Known deterministic failure may repair in this same invocation only.
    """
    from pathlib import Path
    from .adapters.codex import CodexAdapter
    from .repo import diff_state, commit_changes
    from .scope_guard import changed_path_protected_signals
    from .security import harden_runtime_process_secret_boundary
    require(type(readers) is TrustedReaders and readers.engine is engine,
            'pcp_local_concrete_readers_required')
    require(engine.worker_task is None and not engine.active_jobs,
            'pcp_local_existing_worker_forbidden')
    job_id = stable_job_id(task)
    row = engine.storage.get(job_id)
    require(row is not None and row['project_id'] == PROJECT_ID
            and row['status'] == 'queued' and row['source_commit'] == task.base_sha
            and exact_value(row['checkpoint']['pcp_local_source']['receipt'], claimed_source_receipt(task)),
            'pcp_local_execution_identity_invalid')
    require(not changed_path_protected_signals(task.allowed_paths, row['checkpoint']),
            'pcp_local_protected_source_requires_separate_decision')
    receipts = LocalSourceQueueStore(engine.storage)
    receipts.read_claimed(task, job_id=job_id)
    await readers.refresh(task)
    require(not engine.queue.empty() and engine.queue.get_nowait() == job_id
            and engine.queue.empty(), 'pcp_local_queue_identity_invalid')
    # Durable CAS is the execution fence. It is deliberately consumed even if
    # lease acquisition or subsequent Host work has an uncertain result.
    if getattr(readers, 'recovery', None) is not None:
        from .pcp_local_task_queue import fence
        fence(engine.storage, readers.recovery)
    else:
        receipts.advance(task, expected_state='claimed', expected_generation=1,
                         target_state='running', job_id=job_id, worker_authorized=True)
    engine.queue.task_done()
    lease = engine.storage.acquire_project_lease(PROJECT_ID, job_id)
    readers.lease_generation = lease['generation']
    checkpoint = deepcopy(row['checkpoint'])
    from .storage import now
    checkpoint['pcp_local_execution'] = {'state': 'started', 'started_at': now().isoformat(), 'lease_generation': lease['generation'],
        'authority_digest': readers.authority_digest}
    progress = deepcopy(row['progress'])
    engine.storage.update(job_id, checkpoint=checkpoint, route=readers.route, status='executing')
    started = time.monotonic()
    try:
        harden_runtime_process_secret_boundary()
        await readers.refresh(task)
        ws = await engine.ddev.create_workspace(job_id=job_id, project_id=PROJECT_ID,
            ref=task.base_sha, workspace_mode='isolated_clone')
        workspace = Path(ws['workspace'])
        require(workspace == engine.workspace_root / job_id and not workspace.is_symlink()
                and ws['source_commit'] == task.base_sha
                and ws['branch'] == 'ai/' + job_id[:12], 'pcp_local_workspace_ack_invalid')
        engine.storage.update(job_id, workspace=str(workspace), branch=ws['branch'])
        project, _ = readers.authority()
        limits = readers.activation['budget']
        prompt = row['task']['description']
        verification = None
        for attempt in range(limits['model_calls']):
            await readers.refresh(task)
            # Project/home CLI configuration may not install agent-controlled
            # MCP servers, hooks or a different sandbox for a repair turn.
            require_isolated_codex_configuration(workspace)
            remaining = limits['max_wall_seconds'] - int(time.monotonic() - started)
            require(remaining > 0, 'pcp_local_resource_envelope_exhausted')
            require(float(progress.get('cost_usd', 0)) <= limits['cash_ceiling_usd'],
                    'pcp_local_material_budget_exhausted')
            choice = readers.snapshot['model_choice']
            checkpoint['pcp_local_execution'].update(state='invocation_started', attempt=attempt + 1,
                                                     model_choice=choice)
            progress['model_calls'] = int(progress.get('model_calls', 0)) + 1
            engine.storage.update(job_id, checkpoint=checkpoint, progress=progress)
            run = await CodexAdapter(choice['model'], choice['reasoning_effort']).run(
                workspace=workspace, prompt=prompt + '\nAllowed paths: ' + ', '.join(task.allowed_paths),
                mode='execute' if attempt == 0 else 'repair', timeout=remaining,
                isolate_workspace=True)
            engine._record_usage(progress, choice['id'], run.usage)
            engine._record_agent_attempt(progress, choice, run)
            checkpoint['pcp_local_execution']['state'] = 'invocation_returned'
            checkpoint['pcp_local_execution']['returned_invocation'] = dict(
                attempt=attempt + 1, returncode=run.returncode,
                provider_failed=run.provider_failed, usage_digest=digest(run.usage),
                model_calls=progress['model_calls'])
            progress['elapsed_minutes'] = (time.monotonic() - started) / 60
            engine.storage.update(job_id, checkpoint=checkpoint, progress=progress)
            # No retry after provider/timeout/ambiguous CLI failure, even if the
            # process may have left useful edits in the original workspace.
            require(not run.provider_failed, 'pcp_local_provider_failure_no_retry')
            require(run.returncode == 0, 'pcp_local_invocation_uncertain_no_retry')
            diff = diff_state(workspace, int(project['runtime'].get('max_diff_bytes', 750000)),
                              base_ref=task.base_sha)
            require(bool(diff['changed_files']) and set(diff['changed_files']) <= set(task.allowed_paths)
                    and len(diff['changed_files']) <= normalized_budget(limits, len(task.allowed_paths))['max_changed_files'],
                    'pcp_local_changed_paths_denied')
            await readers.refresh(task)
            remaining = limits['max_wall_seconds'] - int(time.monotonic() - started)
            require(remaining >= 10, 'pcp_local_resource_envelope_exhausted')
            from .pcp_local_recovery import verified_tree, commit_verified
            tested_tree = verified_tree(workspace, task, diff)
            verification = await engine.verify_pcp_local(job_id, workspace, project,
                timeout_seconds=remaining)
            progress['test_runs'] = progress.get('test_runs', 0) + verification['test_runs']
            progress['required_checks_passed'] = verification['passed']
            checkpoint['pcp_local_execution']['verification'] = verification
            engine.storage.update(job_id, checkpoint=checkpoint, progress=progress)
            require(verification.get('failure_kind') != 'infrastructure',
                    'pcp_local_infrastructure_failure_no_retry')
            if verification['passed']:
                break
            prompt = row['task']['description'] + '\nRepair deterministic failure:\n' + json.dumps(verification)
        require(verification is not None and verification['passed'], 'pcp_local_engineering_verification_failed')
        await readers.refresh(task)
        # Recheck after tests, which must not mutate the developer source copy.
        final_diff = diff_state(workspace, int(project['runtime'].get('max_diff_bytes', 750000)), base_ref=task.base_sha)
        require(final_diff['diff_hash'] == diff['diff_hash'], 'pcp_local_verified_diff_changed')
        require(verified_tree(workspace, task, diff) == tested_tree, 'pcp_local_verified_tree_changed')
        # Persist the original tested identity BEFORE Git; never refresh it to accept drift.
        from .pcp_local_recovery import verified_tree, commit_verified
        checkpoint['pcp_local_execution'].update(state='verified_uncommitted',
            duration_seconds=time.monotonic() - started, verified_tree=tested_tree, diff=diff, route=deepcopy(readers.route))
        engine.storage.update(job_id, checkpoint=checkpoint, progress=progress)
        commit = commit_verified(engine, job_id, task, workspace, checkpoint)

        require(bool(commit), 'pcp_local_verified_commit_missing')
        checkpoint['pcp_local_execution'].update(state='verified', commit=commit)
        progress['elapsed_minutes'] = (time.monotonic() - started) / 60
        result = dict(status='accepted', branch=ws['branch'], commit=commit, diff=diff,
                      verification=verification, route=readers.route, delivery_finalized=False)
        engine.storage.update(job_id, status='delivering', checkpoint=checkpoint, result=result,
                              progress=progress)
        await engine.deliver_pcp_local(job_id, readers, task)
    except BaseException as exc:
        # Do not release the writer reservation or rewind receipts after an
        # uncertain side effect. Reconciliation is for this exact job only.
        try:
            latest = engine.storage.get(job_id)
            if latest is not None:
                cp = deepcopy(latest['checkpoint'])
                execution = cp.setdefault('pcp_local_execution', {})
                if execution.get('state') == 'verified':
                    execution['delivery_uncertain'] = True
                elif execution.get('state') not in {'verified_uncommitted', 'commit_uncertain'}:
                    execution['held_from'] = execution.get('state')
                    execution['state'] = 'held'
                engine.storage.update(job_id, status='blocked', checkpoint=cp,
                    error=exc.code if isinstance(exc, TaskStop) else 'pcp_local_uncertain_execution_no_retry')
        except Exception as secondary:
            # Preserve the primary exception even if reading/writing its
            # failure checkpoint is unavailable. Never claim the write passed.
            exc.add_note('PCP failure checkpoint also failed: ' + type(secondary).__name__)
        raise
    return engine.storage.get(job_id)


# Concrete service-owned readers for the dedicated execution path.
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time

import httpx
import yaml

from .pcp_local_task_queue import PROJECT_ID, REPOSITORY, require, verify_issue

ACTIVATION_FILE = Path('/config/pcp-local-activation.json')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def normalized_budget(limits, path_count):
    value = dict(limits)
    redundant = value.pop('max_changed_files', path_count)
    require(type(redundant) is int and 0 < redundant <= path_count,
            'pcp_local_changed_file_limit_invalid')
    return dict(max_changed_files=redundant, **value)


def require_isolated_codex_configuration(workspace):
    # The sandbox may create empty protected .codex directories. They grant no
    # configuration. Reject symlinks or content, including ancestor project config;
    # user config/rules are separately disabled by the adapter flags. System config
    # is immutable image input and must remain absent for this pinned profile.
    from .adapters.codex import require_isolated_configuration
    try:
        require_isolated_configuration(workspace)
    except (ValueError, OSError) as exc:
        raise TaskStop('pcp_local_unreviewed_codex_configuration') from exc


def _retained_identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _retained_snapshot(path, destination=None):
    """Descriptor-relative reads; a replaced ancestor cannot redirect descent."""
    result = {}
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOATIME

    def visit(parent, name, rel, target):
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        directory = stat.S_ISDIR(before.st_mode)
        require(directory or (stat.S_ISREG(before.st_mode) and before.st_nlink == 1),
                'pcp_local_retained_git_escape')
        fd = os.open(name, flags | (os.O_DIRECTORY if directory else 0), dir_fd=parent)
        try:
            require(_retained_identity(before) == _retained_identity(os.fstat(fd)), 'pcp_local_retained_files_changed')
            if directory:
                if target is not None:
                    target.mkdir(mode=0o700)
                for child in sorted(os.listdir(fd)):
                    visit(fd, child, rel + '/' + child, target / child if target else None)
                digest = None
            else:
                h = hashlib.sha256()
                output = target.open('xb') if target is not None else None
                try:
                    while chunk := os.read(fd, 1024 * 1024):
                        h.update(chunk)
                        if output:
                            output.write(chunk)
                finally:
                    if output:
                        output.close()
                        target.chmod(stat.S_IMODE(before.st_mode))
                digest = h.hexdigest()
            require(_retained_identity(before) == _retained_identity(os.fstat(fd))
                    == _retained_identity(os.stat(name, dir_fd=parent, follow_symlinks=False)),
                    'pcp_local_retained_files_changed')
            result[rel] = (_retained_identity(before), digest)
        finally:
            os.close(fd)

    # The caller validates the fixed workspace root; pin it before descent.
    parent = os.open(path.parent, flags | os.O_DIRECTORY)
    try:
        visit(parent, path.name, '', destination)
    finally:
        os.close(parent)
    return result


def _retained_environment(home):
    # No inherited credentials, Git overrides, pager, helper or Python startup.
    return dict(PATH=os.defpath, HOME=str(home), LC_ALL='C',
        GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM='/dev/null',
        GIT_CONFIG_GLOBAL='/dev/null', GIT_OPTIONAL_LOCKS='0',
        GIT_NO_REPLACE_OBJECTS='1', GIT_ATTR_NOSYSTEM='1', GIT_ALLOW_PROTOCOL='',
        GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.hooksPath', GIT_CONFIG_VALUE_0='/dev/null',
        PYTHONDONTWRITEBYTECODE='1')


def _retained_run(args, home, **kwargs):
    return subprocess.run(args, cwd=home, env=_retained_environment(home),
        capture_output=True, check=True, timeout=30, **kwargs).stdout


def _retained_configuration(path, home):
    # --file does not perform repository discovery; --no-includes never opens
    # referenced paths. Git's parser supplies the real case/escaping semantics.
    raw = _retained_run(['git', 'config', '--file', str(path), '--no-includes', '--null', '--list'], home)
    values = {}
    for item in raw.split(b'\0'):
        if not item:
            continue
        key, separator, value = item.partition(b'\n')
        key = key.decode('utf-8').lower()
        require(key not in values, 'pcp_local_retained_git_configuration')
        values[key] = value.decode('utf-8') if separator else None
    return values


def _retained_boolean(value, expected):
    value = value.lower() if isinstance(value, str) else value
    return value in ((None, 'true', 'yes', 'on', '1') if expected
                     else ('', 'false', 'no', 'off', '0'))


def _retained_validate(path, home):
    gd = path / '.git'
    require(gd.is_dir() and not any((gd / p).exists() for p in (
        'commondir', 'worktrees', 'modules', 'objects/info/alternates',
        'objects/info/http-alternates', 'info/grafts', 'refs/replace', 'shallow')),
        'pcp_local_retained_git_escape')
    config = _retained_configuration(gd / 'config', home)
    core = {'core.repositoryformatversion', 'core.filemode', 'core.bare', 'core.logallrefupdates'}
    allowed = core | {'user.name', 'user.email', 'extensions.worktreeconfig',
                     'remote.origin.url', 'remote.origin.fetch'}
    # Inert tracking metadata from older non-sparse clones; no remote operation
    # is performed. All behavioral/extension keys remain denied by default.
    allowed |= {k for k in config if k.startswith('branch.') and k.endswith(('.remote', '.merge'))}
    require(core <= config.keys() and config.keys() <= allowed
        and config['core.repositoryformatversion'] in ('0', '1')
        and _retained_boolean(config['core.filemode'], True)
        and _retained_boolean(config['core.bare'], False)
        and _retained_boolean(config['core.logallrefupdates'], True), 'pcp_local_retained_git_configuration')
    sparse = 'extensions.worktreeconfig' in config
    worktree, patterns = gd / 'config.worktree', gd / 'info/sparse-checkout'
    if sparse:
        require(_retained_boolean(config['extensions.worktreeconfig'], True), 'pcp_local_retained_git_configuration')
        wc = _retained_configuration(worktree, home)
        require(set(wc) == {'core.sparsecheckout', 'core.sparsecheckoutcone'}
            and _retained_boolean(wc['core.sparsecheckout'], True)
            and _retained_boolean(wc['core.sparsecheckoutcone'], False), 'pcp_local_retained_git_configuration')
        require(patterns.read_bytes() == b'/*\n!/.ddev/\n' and not (path / '.ddev').exists(),
                'pcp_local_retained_sparse_changed')
    else:
        require(not worktree.exists() and not patterns.exists(), 'pcp_local_retained_git_configuration')
    # These commands now use only a validated private configuration. Neither
    # assume-unchanged nor fsmonitor-valid may suppress a filesystem comparison;
    # skip-worktree is legal only for the exact producer exclusion.
    def git(*args):
        # Sparse-aware index reads can clear skip-worktree for present files.
        # Inspect the stored flags with sparse interpretation disabled first.
        return _retained_run(['git', '-C', str(path), '-c', 'core.sparseCheckout=false', *args], home).split(b'\0')
    for option in ('-v', '-f'):
        for entry in filter(None, git('ls-files', option, '-z')):
            tag, name = entry[:1], entry[2:]
            expected = b'S' if sparse and name.startswith(b'.ddev/') else b'H'
            require(tag == expected, 'pcp_local_retained_index_changed')
    names = set()
    for entry in filter(None, git('ls-files', '--stage', '-z')):
        identity, name = entry.split(b'\t', 1)
        mode, _, stage = identity.split()
        require(mode in (b'100644', b'100755') and stage == b'0' and name not in names
            and not name.startswith(b'/') and not {b'.', b'..', b'.git'} & set(name.split(b'/')),
            'pcp_local_retained_index_changed')
        names.add(name)


def _retained_proof(path, row, base_sha, home):
    # Reuse the authoritative recovery proof unchanged, in an interpreter with a
    # clean environment. Do not mutate process-wide environment in the server.
    program = '''
import json,sys
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1])
from app.pcp_local_recovery import reconcile_commit
value=json.load(sys.stdin)
print(reconcile_commit(value['row'],SimpleNamespace(base_sha=value['base'])))
'''
    payload = dict(row=dict(workspace=str(path), checkpoint=row['checkpoint']), base=base_sha)
    return _retained_run([sys.executable, '-I', '-B', '-c', program, str(Path(__file__).resolve().parent.parent)],
                home, input=json.dumps(payload).encode()).decode().strip()


@contextmanager
def _retained_git(path):
    """Keep the original byte/metadata preimage across proof AND durable reads."""
    try:
        with tempfile.TemporaryDirectory(prefix='pcp-retained-') as scratch:
            home = Path(scratch)
            clone = home / 'snapshot'
            before = _retained_snapshot(path, clone)
            _retained_validate(clone, home)
            yield lambda row, base: _retained_proof(clone, row, base, home)
            require(_retained_snapshot(path) == before, 'pcp_local_retained_files_changed')
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        if isinstance(exc, TaskStop):
            raise
        raise TaskStop('pcp_local_retained_git_invalid') from exc


def retained_workspaces(storage, root, current_job_id):
    """Read-only validation of authentic completed siblings, never terminal flags alone.

    Caller keeps the existing exclusive project/admission locks. The developer
    profile hides every sibling even while it writes the current job. No rename,
    chmod, deletion, fresh proof or history replacement is permitted here.
    """
    import re
    from .pcp_local_readiness import operation_snapshot, finalization_ownership
    require(root.is_absolute() and root.resolve() == root and not root.is_symlink(),
            'pcp_local_workspace_root_invalid')
    for path in root.iterdir():
        require(path.is_dir() and not path.is_symlink() and path.resolve() == path
                and re.fullmatch('[a-f0-9]{32}', path.name), 'pcp_local_foreign_workspace')
        if path.name == current_job_id:
            continue
        row, receipt, lease = operation_snapshot(storage, path.name)
        cp, result = row['checkpoint'], row.get('result') or {}
        execution = cp.get('pcp_local_execution') or {}
        binding = (cp.get('pcp_local_source') or {}).get('receipt') or {}
        task_values = {k: binding.get(k) for k in LocalSourceTask.__dataclass_fields__}
        task_values['allowed_paths'] = tuple(task_values['allowed_paths'] or ())
        task = LocalSourceTask(**task_values)
        require(row['status'] == 'completed' and row['workspace'] == str(path)
                and result.get('delivery_finalized') is True
                and result.get('acceptance_phase') == 'pm_review_accepted'
                and result.get('review', {}).get('source') == 'authenticated_github_pm'
                and result['review'].get('verdict') == 'pass'
                and type(result['review'].get('review_id')) is int
                and result['review']['review_id'] > 0
                # Finalization can be accepted with PM auto-merge disabled.
                # Require the persisted blocker-free exact-head assessment,
                # not a new merge permission or the unrelated eligible flag.
                and result.get('pm_merge_eligibility', {}).get('blockers') == []
                and result['pm_merge_eligibility'].get('expected_head') == result.get('commit')
                and result['pm_merge_eligibility'].get('source_commit') == task.base_sha
                and result['review'].get('report', {}).get('diff_hash') == result.get('diff', {}).get('diff_hash')
                and result.get('delivery', {}).get('state') == 'ci_success'
                and result.get('verification', {}).get('passed') is True
                and result['verification'].get('test_runs', 0) > 0
                and row['source_commit'] == task.base_sha
                and row.get('branch') == 'ai/' + row['id'][:12]
                and result.get('branch') == row['branch']
                and execution.get('verified_tree', {}).get('branch') == row['branch']
                and task.project_id == PROJECT_ID and task.repository == REPOSITORY
                and stable_job_id(task) == row['id']
                and exact_value(binding, claimed_source_receipt(task))
                and cp.get('project_baseline', {}).get('revision') == task.baseline_revision
                and cp['project_baseline'].get('source_commit') == task.baseline_source_commit
                and execution.get('state') == 'verified' and 'pcp_local_retirement' not in cp
                and execution.get('commit') == result.get('commit')
                and execution.get('verification') == result.get('verification')
                and execution.get('diff') == result.get('diff'),
                'pcp_local_retained_evidence_invalid')
        finalization_ownership(row, receipt, lease)
        with _retained_git(path) as reconcile:
            require(reconcile(row, task.base_sha) == result['commit'],
                    'pcp_local_retained_commit_changed')
            # Both filesystem and durable preimages must survive validation.
            require(operation_snapshot(storage, path.name) == (row, receipt, lease),
                    'pcp_local_retained_evidence_changed')


def read_activation():
    """A switch is not authority: require an independently installed document."""
    from .pcp_local_recovery import enabled as held_enabled, HeldPermit
    if held_enabled():
        require(not ACTIVATION_FILE.exists(), "held_ordinary_activation_forbidden")
        return HeldPermit().activation
    from .pcp_local_task_queue import enabled, RecoveryPermit
    if enabled():
        return RecoveryPermit().activation
    require(not ACTIVATION_FILE.is_symlink() and ACTIVATION_FILE.is_file(),
            'pcp_local_operational_delegation_missing')
    value = json.loads(ACTIVATION_FILE.read_text())
    require(type(value) is dict and value.get('project_id') == PROJECT_ID
            and value.get('repository') == REPOSITORY
            and type(value.get('expires_at')) in (int, float)
            and time.time() < value['expires_at']
            and type(value.get('issue_number')) is int
            and value['issue_number'] > 0
            and value.get('developer_permission_mode') == 'bounded',
            'pcp_local_operational_delegation_invalid')
    return value


class TrustedReaders:
    """The concrete eight readers. Callables/dictionaries are not wire inputs."""
    def __init__(self, engine, github):
        self.engine, self.github = engine, github
        self.activation = read_activation()
        from .pcp_local_task_queue import enabled, RecoveryPermit
        self.recovery = RecoveryPermit() if enabled() else None
        from .pcp_local_recovery import enabled as held_enabled, HeldPermit
        self.held = HeldPermit() if held_enabled() else None
        require(not (self.held and self.recovery), "held_conflicting_authority")
        self.route = None
        self.task = None
        self.snapshot = None
        self.lease_generation = None
        self.authority_digest = None

    async def executor(self, path, payload):
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(self.engine.ddev.base + path,
                json=payload, headers=self.engine.ddev.headers)
            response.raise_for_status()
            return response.json()

    def authority(self):
        from . import config
        from .baseline import resolve_project_baseline
        require(read_activation() == self.activation, 'pcp_local_delegation_revoked')
        # Do not allow cached baseline/model files to survive a revocation.
        config.project_baselines_doc.cache_clear()
        config.models_doc.cache_clear()
        config.routing_policy_doc.cache_clear()
        projects = config.projects_doc().get('projects', {})
        require(set(projects) == {PROJECT_ID}, 'pcp_local_singleton_required')
        project = config.project_config(PROJECT_ID)
        require_operational_project(project)
        baseline = resolve_project_baseline(PROJECT_ID, self.activation['baseline_revision'])
        active = config.project_baselines_doc()['projects'][PROJECT_ID]['active_revision']
        require(baseline is not None and baseline.revision == active
                and baseline.source_commit == self.activation['baseline_source_commit'],
                'pcp_local_baseline_revoked')
        revision = digest({'project': project, 'baseline': baseline.model_dump(mode='json'),
                           'models': config.models_doc(), 'policy': config.routing_policy_doc()})
        require(self.authority_digest is None or self.authority_digest == revision,
                'pcp_local_authority_changed')
        self.authority_digest = revision
        return project, baseline

    async def source(self):
        self.authority()
        a = self.activation
        issue = await self.github.local_source_issue(issue_number=a['issue_number'])
        source_permit = getattr(self, 'held', None) or getattr(self, 'recovery', None)
        task = source_permit.verify_issue(issue) if source_permit is not None else verify_issue(issue, **{k: a[k] for k in (
            'issue_number', 'body_sha256', 'base_sha', 'baseline_revision', 'baseline_source_commit')})
        require(self.task is None or task == self.task, 'pcp_local_source_revoked')
        self.task = task
        return task, issue

    async def refresh_delivery(self, task):
        return await self.refresh(task, operation="delivery")

    async def refresh(self, task, *, operation="admission"):
        from .config import model_config
        from .model_capabilities import validate_model_choice
        from .quota_telemetry import CodexQuotaCollector
        from .shell import run_command
        require(not getattr(self, "held", None) or operation == "delivery", "held_admission_forbidden")
        observed_at = time.monotonic()
        project, baseline = self.authority()
        checked, issue = await self.source()
        require(checked == task, 'pcp_local_wrong_task')
        expected_tests = {p for p in task.allowed_paths if p.startswith('tests/')}
        require(bool(expected_tests) and all(expected_tests <= set(project['ddev'].get(phase) or [])
                for phase in ('targeted_tests', 'full_tests')), 'pcp_local_task_tests_not_configured')
        job_id = stable_job_id(task)
        if getattr(self, 'recovery', None) is not None:
            from .pcp_local_task_queue import plan
            plan(self.engine.storage, self.recovery)  # Original/audited identity only.
        with self.engine.storage.connect() as conn:
            retired = conn.execute("SELECT id FROM cp_jobs WHERE id=%s AND checkpoint ? 'pcp_local_retirement'", (job_id,)).fetchone()
            require(retired is None, 'pcp_local_retired_job')
        proof = await self.executor('/v1/pcp-local/observe', {
            'job_id': job_id, 'source_commit': task.base_sha,
            'activation_digest': digest(self.activation),
        })
        require(proof.get('job_id') == job_id and proof.get('source_commit') == task.base_sha
                and proof.get('activation_digest') == digest(self.activation),
                'pcp_local_executor_binding_invalid')
        retained_workspaces(self.engine.storage, self.engine.workspace_root, job_id)
        if operation == 'admission':
            require_isolated_codex_configuration(self.engine.workspace_root / job_id)
        require(not Path('/var/run/docker.sock').exists()
                and not any(os.getenv(k) for k in ('GITHUB_DELIVERY_TOKEN', 'GITHUB_TOKEN', 'GH_TOKEN'))
                and not (Path.home() / '.ssh').exists(), 'pcp_local_runtime_credential_boundary')
        with self.engine.storage.connect() as conn:
            foreign = conn.execute('SELECT id FROM cp_jobs WHERE project_id<>%s LIMIT 1', (PROJECT_ID,)).fetchone()
            require(foreign is None, 'pcp_local_database_not_dedicated')
            if self.lease_generation is not None:
                receipt = conn.execute('SELECT * FROM cp_pcp_local_source_receipts WHERE '
                    'repository=%s AND project_id=%s AND issue_number=%s',
                    (REPOSITORY, PROJECT_ID, task.issue_number)).fetchone()
                expected = {**vars(task), 'allowed_paths': list(task.allowed_paths),
                            'state': 'running', 'generation': 2, 'job_id': job_id}
                require(receipt is not None and all(exact_value(receipt.get(k), v)
                        for k, v in expected.items()), 'pcp_local_running_receipt_changed')
            rows = conn.execute('SELECT id FROM cp_jobs WHERE project_id=%s AND status NOT IN '
                "('completed','failed','cancelled') AND id<>%s", (PROJECT_ID, job_id)).fetchall()
            lease = conn.execute('SELECT * FROM cp_project_leases WHERE project_id=%s',
                                 (PROJECT_ID,)).fetchone()
        require(not rows, 'pcp_local_other_writer')
        if self.lease_generation is None:
            require(lease is None or lease['state'] == 'released', 'pcp_local_writer_busy')
        else:
            require(lease is not None and lease['state'] == 'active'
                    and lease['owner_job_id'] == job_id
                    and lease['generation'] == self.lease_generation,
                    'pcp_local_lease_revoked')
        if operation == 'delivery':
            if getattr(self, 'held', None) is not None:
                from .pcp_local_recovery import snapshot, classify
                classify(snapshot(self.engine.storage, self.held), self.held)
            # These exact authority/source/isolation/ownership checks still apply.
            # No Router choice or developer account is consumed by publication.
            require(time.monotonic() - observed_at < 30, 'pcp_local_observation_expired')
            self.authority()
            return proof
        if self.route is None:
            self.route = await self.engine.router.route({
                'job_id': job_id, 'project_id': PROJECT_ID, 'repository': REPOSITORY,
                'source_commit': task.base_sha,
                'task': {'title': f'PCP-local issue #{task.issue_number}',
                         'description': issue['body'], 'task_type': 'implementation'},
                'repo': {'estimated_files': len(task.allowed_paths), 'tests_available': True},
            })
        strategy = self.route['strategy']
        require(not strategy.get('human_decision', {}).get('required'),
                'pcp_local_protected_decision_pending')
        choice = strategy['executor']
        validate_model_choice(choice)
        require(choice['adapter'] == 'codex_cli'
                and model_config(choice['id']).get('kind') == 'agent',
                'pcp_local_selected_adapter_not_supported')
        version = await run_command(['codex', '--version'], cwd='/tmp', timeout=10)
        from .adapters.codex import PCP_ISOLATION_CLI_VERSION
        require(version.returncode == 0 and version.stdout.strip() ==
                'codex-cli ' + self.activation['codex_version']
                and self.activation['codex_version'] == PCP_ISOLATION_CLI_VERSION,
                'pcp_local_cli_version_mismatch')
        quota = await CodexQuotaCollector().collect()
        relevant = [q for q in quota if q.get('provider') == 'openai'
                    and q.get('state_key') in ('provider:openai', 'quota:model:' + choice['id'])]
        require(bool(relevant) and all(q.get('authoritative') is True
                and q.get('available') is True for q in relevant), 'pcp_local_provider_unavailable')
        limits = self.activation['budget']
        rights = project['autonomy']
        normalized_lease = None if lease is None else {k: lease[k] for k in (
            'project_id', 'owner_job_id', 'generation', 'state')}
        self.snapshot = {
            'project': dict(project_id=PROJECT_ID, repository=REPOSITORY, base_branch='main',
                            registered=True, allow_create_pr=rights.get('allow_create_pr'),
                            allow_production_deploy=rights.get('allow_production_deploy')),
            'baseline': dict(project_id=PROJECT_ID, revision=baseline.revision,
                             source_commit=baseline.source_commit, active_revision=baseline.revision,
                             status='approved'),
            'isolation': {**proof['isolation'], 'workspace_mode': 'isolated_clone',
                          'workspace_lease_state': 'free', 'active_writers': 0},
            'provider': dict(adapter='codex_cli', model=choice['model'],
                effort=choice['reasoning_effort'], installed_cli_version=self.activation['codex_version'],
                approved_cli_version=self.activation['codex_version'], **proof['provider']),
            'budget': dict(owner_approved=True, provider_quota_verified=True,
                **normalized_budget(limits, len(task.allowed_paths))),
            'writer': dict(project_id=PROJECT_ID, workspace_mode='isolated_clone',
                           lease=normalized_lease, other_job_ids=[]),
            'publisher': proof['publisher'],
            'model_choice': {k: choice[k] for k in ('id','adapter','model','reasoning_effort')},
        }
        require(time.monotonic() - observed_at < 30, 'pcp_local_observation_expired')
        self.authority()
        return self.snapshot

    def readers(self):
        # RuntimeTaskAttestor iterates sorted keys: refresh all live sources once
        # per complete observation, rather than collecting quota eight times.
        async def read(key, task):
            if key == min(OBSERVER_PARTS):
                await self.refresh(task)
            require(self.snapshot is not None, 'pcp_local_observation_missing')
            value = deepcopy(self.snapshot[key])
            now = time.monotonic()
            return RuntimeObservation(value, digest({'task': vars(task), 'value': value,
                'activation': self.activation, 'authority': self.authority_digest}), now, now + 30)
        return {k: lambda task, key=k: read(key, task) for k in OBSERVER_PARTS}
