from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any, Literal

import httpx
import yaml
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .baseline import resolve_project_baseline
from .config import _default_config_file, project_config
from .pm_planning import (
    PMPlanProposal,
    PMTicket,
    execution_plan_status,
    validate_plan_proposal,
)
from .storage import Storage, now


DEFAULT_MARKER = "<!-- coding-platform:pm-plan:v1 -->"
BRIDGE_DDL = """
CREATE TABLE IF NOT EXISTS cp_pm_bridge_events (
  project_id TEXT NOT NULL,
  comment_id BIGINT NOT NULL,
  repository TEXT NOT NULL,
  issue_number INTEGER NOT NULL,
  author TEXT NOT NULL,
  comment_url TEXT,
  body_sha256 TEXT NOT NULL,
  status TEXT NOT NULL,
  plan_id TEXT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (project_id, comment_id)
);
CREATE INDEX IF NOT EXISTS cp_pm_bridge_events_project_idx
  ON cp_pm_bridge_events(project_id, created_at DESC);
"""


class PMBridgeEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    baseline_revision: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$",
    )
    proposal: PMPlanProposal


class PMBridgePollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=200)


class PMBridgeGitHubClient:
    def __init__(self) -> None:
        self.base = os.getenv("DDEV_EXECUTOR_URL", "http://ddev-executor:8790").rstrip("/")
        self.token = os.getenv("PLATFORM_INTERNAL_TOKEN", "change-me")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def recent_comments(self, *, project_id: str, per_page: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f"{self.base}/v1/github/pm-bridge/comments",
                params={"project_id": project_id, "per_page": per_page},
                headers=self.headers,
            )
            _raise_executor_error(response)
            return response.json()

    async def issue(self, *, project_id: str, issue_number: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f"{self.base}/v1/github/pm-bridge/issues/{issue_number}",
                params={"project_id": project_id},
                headers=self.headers,
            )
            _raise_executor_error(response)
            return response.json()


def _raise_executor_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        payload = response.json()
        detail = str(payload.get("detail") if isinstance(payload, dict) else payload)
    except ValueError:
        detail = response.text
    raise RuntimeError(f"DDEV executor HTTP {response.status_code}: {detail[-12000:]}")


def _bridge_doc() -> dict[str, Any]:
    path = os.getenv(
        "PM_BRIDGE_CONFIG_FILE",
        _default_config_file("pm-bridge.yml", "/config/pm-bridge.yml"),
    )
    with open(path, "r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError("PM bridge config must be a YAML object")
    return value


def bridge_project_config(project_id: str) -> dict[str, Any]:
    projects = _bridge_doc().get("projects", {}) or {}
    if project_id not in projects:
        raise ValueError(f"PM bridge is not configured for project {project_id!r}")
    cfg = dict(projects[project_id] or {})
    if not cfg.get("enabled", False):
        raise ValueError(f"PM bridge is disabled for project {project_id!r}")
    authors = cfg.get("allowed_authors") or []
    if not isinstance(authors, list) or not authors or any(not isinstance(item, str) or not item.strip() for item in authors):
        raise ValueError(f"PM bridge allowed_authors must be a non-empty string list for {project_id!r}")
    marker = str(cfg.get("marker") or DEFAULT_MARKER)
    if marker != DEFAULT_MARKER:
        raise ValueError("Only the versioned PM bridge v1 marker is supported")
    per_page = int(cfg.get("max_comments_per_poll", 100))
    if per_page < 1 or per_page > 100:
        raise ValueError("PM bridge max_comments_per_poll must be between 1 and 100")
    cfg["allowed_authors"] = [item.strip() for item in authors]
    cfg["marker"] = marker
    cfg["max_comments_per_poll"] = per_page
    return cfg


def enabled_bridge_projects() -> list[str]:
    projects = _bridge_doc().get("projects", {}) or {}
    return sorted(
        project_id
        for project_id, cfg in projects.items()
        if isinstance(cfg, dict) and cfg.get("enabled", False)
    )


def parse_pm_bridge_comment(body: str, *, marker: str = DEFAULT_MARKER) -> PMBridgeEnvelope:
    if len(body.encode("utf-8")) > 65536:
        raise ValueError("PM bridge comment exceeds 64 KiB")
    if body.count(marker) != 1:
        raise ValueError("PM bridge comment must contain exactly one versioned marker")
    payload = body.split(marker, 1)[1].strip()
    if not payload:
        raise ValueError("PM bridge marker must be followed by one JSON object")
    if payload.startswith("```"):
        lines = payload.splitlines()
        if len(lines) < 3 or lines[0].strip() not in {"```", "```json"} or lines[-1].strip() != "```":
            raise ValueError("PM bridge fenced payload must contain exactly one complete JSON block")
        payload = "\n".join(lines[1:-1]).strip()
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("PM bridge payload must be one JSON object") from exc
    if not isinstance(raw, dict):
        raise ValueError("PM bridge payload must be a JSON object")
    return PMBridgeEnvelope.model_validate(raw)


class PMBridgeEventStore:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def ensure(self) -> None:
        with self.storage.connect() as conn:
            conn.execute(BRIDGE_DDL)
            conn.commit()

    def get(self, project_id: str, comment_id: int) -> dict[str, Any] | None:
        self.ensure()
        with self.storage.connect() as conn:
            return conn.execute(
                "SELECT * FROM cp_pm_bridge_events WHERE project_id=%s AND comment_id=%s",
                (project_id, comment_id),
            ).fetchone()

    def record(
        self,
        *,
        project_id: str,
        comment_id: int,
        repository: str,
        issue_number: int,
        author: str,
        comment_url: str | None,
        body_sha256: str,
        status: str,
        plan_id: str | None,
        error: str | None,
    ) -> None:
        self.ensure()
        with self.storage.connect() as conn:
            conn.execute(
                """INSERT INTO cp_pm_bridge_events
                (project_id, comment_id, repository, issue_number, author, comment_url,
                 body_sha256, status, plan_id, error, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (project_id, comment_id) DO NOTHING""",
                (
                    project_id,
                    comment_id,
                    repository,
                    issue_number,
                    author,
                    comment_url,
                    body_sha256,
                    status,
                    plan_id,
                    error,
                    now(),
                ),
            )
            conn.commit()


class PMBridgeService:
    def __init__(
        self,
        storage: Storage,
        *,
        github: PMBridgeGitHubClient | None = None,
        events: PMBridgeEventStore | None = None,
    ) -> None:
        self.storage = storage
        self.github = github or PMBridgeGitHubClient()
        self.events = events or PMBridgeEventStore(storage)
        self._lock = asyncio.Lock()

    async def poll_project(self, project_id: str) -> dict[str, Any]:
        async with self._lock:
            cfg = bridge_project_config(project_id)
            project = project_config(project_id)
            feed = await self.github.recent_comments(
                project_id=project_id,
                per_page=cfg["max_comments_per_poll"],
            )
            repository = str(feed.get("repository") or "")
            comments = list(feed.get("comments") or [])
            result: dict[str, Any] = {
                "project_id": project_id,
                "repository": repository,
                "scanned": len(comments),
                "accepted": [],
                "rejected": [],
                "skipped": [],
            }
            for comment in reversed(comments):
                body = str(comment.get("body") or "")
                marker = cfg["marker"]
                if marker not in body:
                    continue
                comment_id = int(comment["id"])
                existing = self.events.get(project_id, comment_id)
                if existing is not None:
                    result["skipped"].append(comment_id)
                    continue

                issue_number = int(comment["issue_number"])
                author = str(comment.get("author") or "")
                comment_url = comment.get("html_url")
                body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
                plan_id: str | None = None
                try:
                    if author not in set(cfg["allowed_authors"]):
                        raise ValueError(f"GitHub author {author!r} is not allowed to submit PM plans")
                    envelope = parse_pm_bridge_comment(body, marker=marker)
                    baseline = resolve_project_baseline(project_id, envelope.baseline_revision)
                    if baseline is None:
                        raise ValueError("External PM plan requires an approved ProjectBaseline")

                    issue = await self.github.issue(project_id=project_id, issue_number=issue_number)
                    if issue.get("is_pull_request"):
                        raise ValueError("PM bridge comments must belong to GitHub issues, not pull requests")
                    if str(issue.get("state") or "") != "open":
                        raise ValueError("PM bridge only accepts plans for open GitHub issues")
                    ticket = PMTicket(
                        id=f"GH-{issue_number}",
                        title=str(issue.get("title") or ""),
                        description=str(issue.get("body") or ""),
                    )
                    plan = validate_plan_proposal(
                        envelope.proposal,
                        ticket=ticket,
                        baseline=baseline,
                        project=project,
                    )
                    status = execution_plan_status(plan)
                    plan_id = f"pm-gh-{comment_id}"
                    existing_plan = self.storage.get_execution_plan(plan_id)
                    if existing_plan is None:
                        self.storage.create_execution_plan(
                            {
                                "id": plan_id,
                                "project_id": project_id,
                                "status": status,
                                "baseline_revision": baseline.revision,
                                "baseline_source_commit": baseline.source_commit,
                                "ticket": ticket.model_dump(mode="json"),
                                "staffing": {
                                    "mode": "external",
                                    "role": "product_manager",
                                    "transport": "github_issue_comment",
                                    "repository": repository,
                                    "issue_number": issue_number,
                                    "comment_id": comment_id,
                                    "author": author,
                                    "comment_url": comment_url,
                                },
                                "plan": plan.model_dump(mode="json"),
                                "usage": {"model_calls": 0, "external_pm": True},
                                "error": None,
                            }
                        )
                    else:
                        if (
                            existing_plan["project_id"] != project_id
                            or existing_plan["baseline_revision"] != baseline.revision
                        ):
                            raise RuntimeError("Deterministic external PM plan id collides with different plan metadata")
                    self.events.record(
                        project_id=project_id,
                        comment_id=comment_id,
                        repository=repository,
                        issue_number=issue_number,
                        author=author,
                        comment_url=comment_url,
                        body_sha256=body_sha256,
                        status="accepted",
                        plan_id=plan_id,
                        error=None,
                    )
                    result["accepted"].append({"comment_id": comment_id, "plan_id": plan_id, "status": status})
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"[-12000:]
                    self.events.record(
                        project_id=project_id,
                        comment_id=comment_id,
                        repository=repository,
                        issue_number=issue_number,
                        author=author,
                        comment_url=comment_url,
                        body_sha256=body_sha256,
                        status="rejected",
                        plan_id=plan_id,
                        error=error,
                    )
                    result["rejected"].append({"comment_id": comment_id, "error": error})
            return result


def _runtime_auth(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("RUNTIME_API_TOKEN", "").strip()
    if not expected or expected in {"CHANGE_ME", "change-me"}:
        raise HTTPException(503, "RUNTIME_API_TOKEN is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "Invalid bearer token")


router = APIRouter(prefix="/v1/pm-bridge", tags=["pm-bridge"], dependencies=[Depends(_runtime_auth)])
_storage = Storage()
_service = PMBridgeService(_storage)


@router.post("/poll")
async def poll(payload: PMBridgePollRequest) -> dict[str, Any]:
    try:
        return await _service.poll_project(payload.project_id)
    except (KeyError, RuntimeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/poll-all")
async def poll_all() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for project_id in enabled_bridge_projects():
        try:
            results.append(await _service.poll_project(project_id))
        except Exception as exc:
            results.append({"project_id": project_id, "error": f"{type(exc).__name__}: {exc}"[-12000:]})
    return {"projects": results}


@router.get("/events/{project_id}/{comment_id}")
def event(project_id: str, comment_id: int) -> dict[str, Any]:
    row = _service.events.get(project_id, comment_id)
    if row is None:
        raise HTTPException(404, "PM bridge event not found")
    return dict(row)
