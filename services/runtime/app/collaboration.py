from __future__ import annotations

import asyncio
import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .adapters.factory import build_adapter
from .developer_stream import runtime_activity_event
from .executor_client import DdevExecutorClient
from .router_client import RouterClient
from .shell import run_command
from .usage import estimated_cost_usd, normalize_usage
from .work_order import work_order_snapshot


CollaborationRole = Literal[
    "consultant",
    "test_engineer",
    "debugger",
    "security_specialist",
    "reviewer",
]
CollaborationStatus = Literal["open", "resolved", "pm_handoff", "failed"]
_ALLOWED_INITIATORS = {"developer", "product_manager"}
_MAX_OPEN_THREADS = 3
_MAX_ROUNDS = 2
_MAX_EVIDENCE_ITEMS = 8
_MAX_EVIDENCE_SUMMARY = 4000
_MAX_PROMPT_CHARS = 28000


class CollaborationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=_MAX_EVIDENCE_SUMMARY)

    @field_validator("ref", "summary")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Collaboration evidence text must not be blank")
        return normalized


class CollaborationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: CollaborationRole
    topic: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=2000)
    question: str = Field(min_length=1, max_length=5000)
    evidence: list[CollaborationEvidence] = Field(min_length=1, max_length=_MAX_EVIDENCE_ITEMS)
    initiator_role: str = Field(default="developer", min_length=2, max_length=80)

    @field_validator("topic", "objective", "question", "initiator_role")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Collaboration request text must not be blank")
        return normalized

    @model_validator(mode="after")
    def deny_recursive_fanout(self) -> "CollaborationCreateRequest":
        if self.initiator_role not in _ALLOWED_INITIATORS:
            raise ValueError(
                "Only the primary developer or Product Manager may initiate collaboration; "
                "consultant-to-consultant fanout is disabled"
            )
        return self


class CollaborationRecheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    developer_response: str = Field(min_length=1, max_length=5000)
    evidence: list[CollaborationEvidence] = Field(default_factory=list, max_length=_MAX_EVIDENCE_ITEMS)
    initiator_role: str = Field(default="developer", min_length=2, max_length=80)

    @field_validator("developer_response", "initiator_role")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Collaboration re-check text must not be blank")
        return normalized

    @model_validator(mode="after")
    def deny_recursive_fanout(self) -> "CollaborationRecheckRequest":
        if self.initiator_role not in _ALLOWED_INITIATORS:
            raise ValueError(
                "Only the primary developer or Product Manager may request a re-check; "
                "recursive collaboration is disabled"
            )
        return self


class CollaborationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation: str = Field(min_length=1, max_length=8000)
    risks: list[str] = Field(default_factory=list, max_length=12)
    suggested_tests: list[str] = Field(default_factory=list, max_length=12)
    unresolved: bool = False

    @field_validator("recommendation")
    @classmethod
    def normalize_recommendation(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Collaboration recommendation must not be blank")
        return normalized

    @field_validator("risks", "suggested_tests")
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            normalized = str(value).strip()
            if not normalized:
                continue
            if len(normalized) > 1500:
                raise ValueError("Collaboration list item is too long")
            if normalized not in result:
                result.append(normalized)
        return result


class CollaborationView(BaseModel):
    id: str
    job_id: str
    work_order_id: str
    topic: str
    role: CollaborationRole
    objective: str
    question: str
    status: CollaborationStatus
    rounds: int
    max_rounds: int
    evidence: list[CollaborationEvidence]
    response: CollaborationResponse | None = None
    staffing: dict[str, Any] | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    pm_handoff: dict[str, Any] | None = None
    error: str | None = None


def _thread_view(thread: dict[str, Any]) -> CollaborationView:
    return CollaborationView.model_validate(thread)


def _parse_response(output: str) -> CollaborationResponse:
    text = (output or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            text = "\n".join(lines[1:-1]).strip()
            if text.lower().startswith("json\n"):
                text = text[5:].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Collaborator output must be one JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("Collaborator output must be a JSON object")
    return CollaborationResponse.model_validate(payload)


async def _workspace_state(workspace: Path) -> tuple[str, str]:
    head = await run_command(["git", "rev-parse", "HEAD"], cwd=workspace, timeout=20)
    status = await run_command(["git", "status", "--porcelain=v1", "-uall"], cwd=workspace, timeout=20)
    if head.returncode != 0 or status.returncode != 0:
        raise RuntimeError("Unable to verify collaboration workspace state")
    return head.stdout.strip(), status.stdout


class CollaborationManager:
    """Bounded, durable role-to-role consultation for one WorkOrder.

    Threads are stored in the job checkpoint so they survive Runtime restarts
    without introducing a second lifecycle database. Consultant calls use a
    disposable workspace and adapter plan mode; the primary implementation
    workspace is never passed to a collaborator.
    """

    def __init__(
        self,
        storage: Any,
        *,
        router: RouterClient | None = None,
        ddev: DdevExecutorClient | None = None,
        adapter_builder=build_adapter,
    ) -> None:
        self.storage = storage
        self.router = router or RouterClient()
        self.ddev = ddev or DdevExecutorClient()
        self.adapter_builder = adapter_builder
        self._lock = asyncio.Lock()

    @staticmethod
    def _threads(checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
        raw = checkpoint.get("collaboration_threads") or []
        return [deepcopy(item) for item in raw if isinstance(item, dict)]

    def _persist_threads(self, job_id: str, row: dict[str, Any], threads: list[dict[str, Any]]) -> None:
        checkpoint = deepcopy(row.get("checkpoint") or {})
        checkpoint["collaboration_threads"] = deepcopy(threads)
        self.storage.update(job_id, checkpoint=checkpoint)

    def list(self, job_id: str) -> list[CollaborationView]:
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        return [_thread_view(item) for item in self._threads(row.get("checkpoint") or {})]

    def get(self, job_id: str, thread_id: str) -> CollaborationView:
        for thread in self.list(job_id):
            if thread.id == thread_id:
                return thread
        raise RuntimeError("Unknown collaboration thread")

    @staticmethod
    def _work_order(row: dict[str, Any]):
        checkpoint = row.get("checkpoint") or {}
        work_order = work_order_snapshot(checkpoint.get("work_order"))
        if work_order is None:
            raise RuntimeError("Collaboration requires a pinned WorkOrder")
        return work_order

    @staticmethod
    def _profile(row: dict[str, Any]) -> str:
        route = row.get("route") or {}
        profile = str((route.get("strategy") or {}).get("profile") or "standard")
        return profile if profile in {"fast", "standard", "complex", "critical"} else "standard"

    @staticmethod
    def _semantic(row: dict[str, Any], role: CollaborationRole) -> dict[str, int]:
        route = row.get("route") or {}
        dimensions = route.get("dimensions") or {}
        risk = int(dimensions.get("risk", 40) or 40)
        verification = int(dimensions.get("verification_difficulty", 40) or 40)
        ambiguity = int(dimensions.get("ambiguity", 40) or 40)
        context = int(dimensions.get("context_requirement", 50) or 50)
        reasoning = int(dimensions.get("reasoning_requirement", 60) or 60)
        if role == "security_specialist":
            risk = max(risk, 80)
            reasoning = max(reasoning, 75)
        elif role == "test_engineer":
            verification = max(verification, 75)
        elif role == "debugger":
            reasoning = max(reasoning, 75)
        elif role == "reviewer":
            risk = max(risk, 55)
            reasoning = max(reasoning, 70)
        return {
            "ambiguity": max(0, min(100, ambiguity)),
            "architecture_impact": max(0, min(100, int(dimensions.get("architecture_impact", 30) or 30))),
            "verification_difficulty": max(0, min(100, verification)),
            "risk": max(0, min(100, risk)),
            "context_requirement": max(0, min(100, context)),
            "novelty": max(0, min(100, int(dimensions.get("novelty", 40) or 40))),
            "reasoning_requirement": max(0, min(100, reasoning)),
        }

    @staticmethod
    def _ensure_budget(row: dict[str, Any]) -> None:
        route = row.get("route") or {}
        budget = (route.get("strategy") or {}).get("budget") or {}
        progress = row.get("progress") or {}
        if int(progress.get("model_calls", 0)) >= int(budget.get("max_model_calls", 0) or 0):
            raise RuntimeError("Collaboration model call would exceed the job model-call emergency ceiling")

    @staticmethod
    def _build_prompt(
        *,
        work_order: Any,
        thread: dict[str, Any],
        round_number: int,
        developer_response: str | None,
        extra_evidence: list[CollaborationEvidence],
    ) -> str:
        prior = thread.get("response") if round_number > 1 else None
        evidence = [CollaborationEvidence.model_validate(item) for item in thread.get("evidence") or []]
        evidence.extend(extra_evidence)
        compact_evidence = [item.model_dump(mode="json") for item in evidence[-_MAX_EVIDENCE_ITEMS:]]
        contract = {
            "work_order_id": work_order.id,
            "objective": work_order.objective,
            "acceptance_criteria": [item.model_dump(mode="json") for item in work_order.acceptance_criteria],
            "constraints": list(work_order.constraints),
            "out_of_scope": list(work_order.out_of_scope),
        }
        context = {
            "thread_id": thread["id"],
            "topic": thread["topic"],
            "logical_role": thread["role"],
            "role_objective": thread["objective"],
            "question": thread["question"],
            "round": round_number,
            "evidence": compact_evidence,
        }
        if prior:
            # Only the prior structured artifact is propagated, never raw model
            # stdout/transcript. This is the compact reviewer-dialogue context.
            context["prior_structured_response"] = prior
        if developer_response:
            context["developer_response"] = developer_response
        schema = CollaborationResponse.model_json_schema()
        prompt = "\n".join(
            [
                f"You are the read-only logical role {thread['role']} consulting on one bounded WorkOrder.",
                "Do not modify files, commit, push, merge, deploy, change scope, or initiate another agent/consultation.",
                "Inspect repository state read-only only when the compact evidence is insufficient.",
                "Answer the concrete question using the WorkOrder contract and evidence. Stay inside scope.",
                "Set unresolved=true only when a material technical disagreement or missing evidence remains after this round.",
                "Return EXACTLY one JSON object matching OUTPUT_JSON_SCHEMA and no prose outside it.",
                f"WORK_ORDER: {json.dumps(contract, ensure_ascii=False, sort_keys=True)}",
                f"COLLABORATION: {json.dumps(context, ensure_ascii=False, sort_keys=True)}",
                "OUTPUT_JSON_SCHEMA:",
                json.dumps(schema, ensure_ascii=False, sort_keys=True),
            ]
        )
        if len(prompt) > _MAX_PROMPT_CHARS:
            raise ValueError("Compact collaboration context exceeds the bounded prompt limit")
        return prompt

    def _record_activity(
        self,
        row: dict[str, Any],
        *,
        kind: str,
        message: str,
        status: str,
        output: dict[str, Any] | None = None,
        choice: dict[str, Any] | None = None,
    ) -> None:
        choice = choice or {}
        self.storage.append_event(
            row["id"],
            runtime_activity_event(
                kind=kind,
                message=message,
                phase="collaboration",
                status=status,
                output=output,
                provider=str(choice.get("provider") or "") or None,
                model=str(choice.get("model") or "") or None,
                adapter=str(choice.get("adapter") or "") or None,
                workspace=Path(str(row.get("workspace") or ".")),
            ),
        )

    def _charge_usage(self, job_id: str, usage_raw: dict[str, Any], model_id: str) -> dict[str, Any]:
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        normalized = normalize_usage(usage_raw)
        cost = estimated_cost_usd(model_id, usage_raw)
        progress = deepcopy(row.get("progress") or {})
        progress["model_calls"] = int(progress.get("model_calls", 0)) + 1
        progress["input_tokens"] = int(progress.get("input_tokens", 0)) + int(normalized["input_tokens"])
        progress["output_tokens"] = int(progress.get("output_tokens", 0)) + int(normalized["output_tokens"])
        progress["cost_usd"] = round(float(progress.get("cost_usd", 0.0)) + cost, 8)
        progress["collaboration_model_calls"] = int(progress.get("collaboration_model_calls", 0)) + 1
        progress["collaboration_input_tokens"] = int(progress.get("collaboration_input_tokens", 0)) + int(normalized["input_tokens"])
        progress["collaboration_output_tokens"] = int(progress.get("collaboration_output_tokens", 0)) + int(normalized["output_tokens"])
        progress["collaboration_cost_usd"] = round(
            float(progress.get("collaboration_cost_usd", 0.0)) + cost,
            8,
        )
        self.storage.update(job_id, progress=progress)
        return {
            **normalized,
            "estimated_cost_usd": cost,
            "model_calls": 1,
        }

    async def create(self, job_id: str, request: CollaborationCreateRequest) -> CollaborationView:
        async with self._lock:
            row = self.storage.get(job_id)
            if not row:
                raise RuntimeError("Unknown job")
            work_order = self._work_order(row)
            threads = self._threads(row.get("checkpoint") or {})
            if sum(1 for item in threads if item.get("status") == "open") >= _MAX_OPEN_THREADS:
                raise RuntimeError(f"At most {_MAX_OPEN_THREADS} collaboration threads may be open per job")
            duplicate = any(
                item.get("status") == "open"
                and item.get("role") == request.role
                and str(item.get("question") or "").casefold() == request.question.casefold()
                for item in threads
            )
            if duplicate:
                raise RuntimeError("Duplicate open collaboration question is not allowed")
            self._ensure_budget(row)

            thread_id = f"ct-{uuid.uuid4().hex[:16]}"
            thread = {
                "id": thread_id,
                "job_id": job_id,
                "work_order_id": work_order.id,
                "topic": request.topic,
                "role": request.role,
                "objective": request.objective,
                "question": request.question,
                "status": "open",
                "rounds": 0,
                "max_rounds": _MAX_ROUNDS,
                "evidence": [item.model_dump(mode="json") for item in request.evidence],
                "response": None,
                "staffing": None,
                "usage": {},
                "pm_handoff": None,
                "error": None,
            }
            threads.append(thread)
            self._persist_threads(job_id, row, threads)
            return await self._run_round(job_id, thread_id, developer_response=None, extra_evidence=[])

    async def recheck(
        self,
        job_id: str,
        thread_id: str,
        request: CollaborationRecheckRequest,
    ) -> CollaborationView:
        async with self._lock:
            row = self.storage.get(job_id)
            if not row:
                raise RuntimeError("Unknown job")
            threads = self._threads(row.get("checkpoint") or {})
            thread = next((item for item in threads if item.get("id") == thread_id), None)
            if thread is None:
                raise RuntimeError("Unknown collaboration thread")
            if thread.get("status") != "open":
                raise RuntimeError(f"Collaboration thread cannot be re-checked from status={thread.get('status')}")
            if int(thread.get("rounds", 0)) >= _MAX_ROUNDS:
                raise RuntimeError("Collaboration round limit reached")
            self._ensure_budget(row)
            return await self._run_round(
                job_id,
                thread_id,
                developer_response=request.developer_response,
                extra_evidence=request.evidence,
            )

    async def _run_round(
        self,
        job_id: str,
        thread_id: str,
        *,
        developer_response: str | None,
        extra_evidence: list[CollaborationEvidence],
    ) -> CollaborationView:
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        work_order = self._work_order(row)
        threads = self._threads(row.get("checkpoint") or {})
        index = next((idx for idx, item in enumerate(threads) if item.get("id") == thread_id), None)
        if index is None:
            raise RuntimeError("Unknown collaboration thread")
        thread = threads[index]
        round_number = int(thread.get("rounds", 0)) + 1
        if round_number > _MAX_ROUNDS:
            raise RuntimeError("Collaboration round limit reached")

        profile = self._profile(row)
        staffing = await self.router.staff(
            {
                "request_id": thread_id,
                "project_id": row["project_id"],
                "role": thread["role"],
                "profile": profile,
                "semantic": self._semantic(row, thread["role"]),
                "provider_state": (row.get("checkpoint") or {}).get("provider_state") or {},
            }
        )
        choice = staffing.get("choice") or {}
        thread["staffing"] = {
            "role": staffing.get("role"),
            "profile": staffing.get("profile"),
            "choice": choice,
            "policy_version": staffing.get("policy_version"),
            "registry_version": staffing.get("registry_version"),
        }
        threads[index] = thread
        self._persist_threads(job_id, row, threads)
        self._record_activity(
            row,
            kind="collaboration_round",
            message=f"Starting read-only {thread['role']} collaboration round {round_number}/{_MAX_ROUNDS}",
            status="started",
            output={"thread_id": thread_id, "round": round_number, "role": thread["role"]},
            choice=choice,
        )

        workspace_info: dict[str, Any] | None = None
        try:
            workspace_job_id = f"{job_id[:48]}c{thread_id[3:11]}r{round_number}"
            workspace_info = await self.ddev.create_workspace(
                job_id=workspace_job_id,
                project_id=row["project_id"],
                ref=str(row.get("source_commit") or "") or None,
            )
            workspace = Path(str(workspace_info["workspace"]))
            before = await _workspace_state(workspace)
            prompt = self._build_prompt(
                work_order=work_order,
                thread=thread,
                round_number=round_number,
                developer_response=developer_response,
                extra_evidence=extra_evidence,
            )
            adapter = self.adapter_builder(
                str(choice["adapter"]),
                str(choice["model"]),
                str(choice.get("reasoning_effort") or "") or None,
            )
            run = await adapter.run(
                workspace=workspace,
                prompt=prompt,
                mode="plan",
                timeout=600 if profile in {"complex", "critical"} else 360,
            )
            after = await _workspace_state(workspace)
            if after != before:
                raise RuntimeError("Read-only collaborator modified its disposable workspace")
            usage = self._charge_usage(job_id, run.usage, str(choice.get("id") or ""))
            if run.returncode != 0:
                detail = run.failure_message or run.stderr or run.output or "collaborator failed"
                raise RuntimeError(
                    f"Collaborator model call failed ({run.failure_kind or run.returncode}): {detail[-12000:]}"
                )
            response = _parse_response(run.output)

            row = self.storage.get(job_id)
            assert row is not None
            threads = self._threads(row.get("checkpoint") or {})
            index = next((idx for idx, item in enumerate(threads) if item.get("id") == thread_id), None)
            if index is None:
                raise RuntimeError("Collaboration thread disappeared during execution")
            thread = threads[index]
            thread["rounds"] = round_number
            thread["response"] = response.model_dump(mode="json")
            aggregate = deepcopy(thread.get("usage") or {})
            aggregate["model_calls"] = int(aggregate.get("model_calls", 0)) + 1
            aggregate["input_tokens"] = int(aggregate.get("input_tokens", 0)) + int(usage["input_tokens"])
            aggregate["output_tokens"] = int(aggregate.get("output_tokens", 0)) + int(usage["output_tokens"])
            aggregate["estimated_cost_usd"] = round(
                float(aggregate.get("estimated_cost_usd", 0.0)) + float(usage["estimated_cost_usd"]),
                8,
            )
            thread["usage"] = aggregate
            thread["error"] = None
            if response.unresolved and round_number >= _MAX_ROUNDS:
                thread["status"] = "pm_handoff"
                thread["pm_handoff"] = {
                    "reason": "collaboration_round_limit_with_unresolved_disagreement",
                    "thread_id": thread_id,
                    "work_order_id": work_order.id,
                    "topic": thread["topic"],
                    "question": thread["question"],
                    "latest_response": response.model_dump(mode="json"),
                    "evidence_refs": [item.get("ref") for item in thread.get("evidence") or []],
                }
            elif response.unresolved:
                thread["status"] = "open"
            else:
                thread["status"] = "resolved"
            threads[index] = thread
            self._persist_threads(job_id, row, threads)
            self._record_activity(
                row,
                kind="collaboration_round",
                message=(
                    f"{thread['role']} collaboration round {round_number} "
                    f"{'requires another bounded round' if response.unresolved and round_number < _MAX_ROUNDS else thread['status']}"
                ),
                status=thread["status"],
                output={
                    "thread_id": thread_id,
                    "round": round_number,
                    "unresolved": response.unresolved,
                    "model_calls": aggregate["model_calls"],
                },
                choice=choice,
            )
            if thread["status"] == "pm_handoff":
                self._record_activity(
                    row,
                    kind="collaboration_pm_handoff",
                    message="Unresolved collaboration reached its round limit; structured evidence handed to PM",
                    status="pm_handoff",
                    output=thread["pm_handoff"],
                    choice=choice,
                )
            return _thread_view(thread)
        except Exception as exc:
            row = self.storage.get(job_id)
            if row:
                threads = self._threads(row.get("checkpoint") or {})
                index = next((idx for idx, item in enumerate(threads) if item.get("id") == thread_id), None)
                if index is not None:
                    thread = threads[index]
                    thread["error"] = f"{type(exc).__name__}: {exc}"[-12000:]
                    # Provider/infrastructure failures are resumable by an explicit
                    # re-check and do not consume a collaboration dialogue round.
                    thread["status"] = "open"
                    threads[index] = thread
                    self._persist_threads(job_id, row, threads)
                    self._record_activity(
                        row,
                        kind="collaboration_failure",
                        message=f"Collaboration round failed before a structured response: {type(exc).__name__}",
                        status="failed",
                        output={"thread_id": thread_id, "round": round_number},
                        choice=choice,
                    )
            raise
        finally:
            if workspace_info and workspace_info.get("workspace"):
                await self.ddev.remove_workspace(
                    job_id=workspace_job_id,
                    project_id=row["project_id"] if row else "",
                    workspace=str(workspace_info["workspace"]),
                )
