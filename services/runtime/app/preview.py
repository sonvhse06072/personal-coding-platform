from __future__ import annotations

import asyncio
import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Literal

from .config import project_config, projects_doc


PreviewTarget = Literal["frontend", "backend", "both"]


def _public_preview_error(exc: Exception) -> str:
    """Return a bounded browser-safe failure summary, never raw executor stderr."""
    text = str(exc)
    lower = text.lower()
    if "timed out" in lower or "timeout" in lower:
        return "Preview operation timed out."
    if "active process" in lower or "busy" in lower:
        return "Preview is temporarily busy with another executor operation."
    if "lease" in lower:
        return "Preview is unavailable because the direct project lease is not active."
    if "not enabled" in lower or "unsupported" in lower:
        return "The requested preview target is not enabled for this project."
    if "did not become healthy" in lower or "health" in lower:
        return "Preview started but did not become healthy."
    match = re.search(r"DDEV executor HTTP\s+(\d{3})", text)
    if match:
        return f"Preview infrastructure operation failed (executor HTTP {match.group(1)})."
    return "Preview operation failed."


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    text = str(value).strip()
    return text or None


class PreviewManager:
    """Manage local direct-workspace previews without changing coding-job state."""

    def __init__(self, storage: Any, ddev: Any) -> None:
        self.storage = storage
        self.ddev = ddev

    @staticmethod
    def _workspace_mode(job: dict[str, Any]) -> str:
        checkpoint = dict(job.get("checkpoint") or {})
        return str(checkpoint.get("workspace_mode") or "isolated_clone")

    @staticmethod
    def _target_supported(project: dict[str, Any], target: str) -> bool:
        preview = project.get("preview") or {}
        if not isinstance(preview, dict):
            return False
        backend = preview.get("backend") or {}
        frontend = preview.get("frontend") or {}
        backend_enabled = bool(
            isinstance(backend, dict) and backend.get("enabled", False)
        )
        frontend_enabled = bool(
            isinstance(frontend, dict) and frontend.get("enabled", False)
        )
        if target == "backend":
            return backend_enabled
        if target == "frontend":
            return frontend_enabled
        if target == "both":
            return backend_enabled and frontend_enabled
        return False

    def _job(self, job_id: str) -> dict[str, Any]:
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        return dict(row)

    def _direct_context(
        self,
        job_id: str,
        *,
        target: PreviewTarget | None = None,
        require_lease: bool,
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        job = self._job(job_id)
        if self._workspace_mode(job) != "direct":
            raise RuntimeError("Live preview is supported only for direct-workspace jobs")
        workspace = str(job.get("workspace") or "").strip()
        if not workspace:
            raise RuntimeError("Direct job does not have a prepared workspace")
        project = project_config(str(job["project_id"]))
        runtime = project.get("runtime", {}) or {}
        if str(runtime.get("workspace_mode") or "isolated_clone") != "direct":
            raise RuntimeError("Project is no longer configured for direct workspace execution")
        if target is not None and not self._target_supported(project, target):
            raise RuntimeError(f"Preview target {target!r} is not enabled for this project")
        if require_lease:
            lease = self.storage.project_lease(str(job["project_id"]))
            if (
                not lease
                or str(lease.get("state") or "") != "active"
                or str(lease.get("owner_job_id") or "") != job_id
            ):
                raise RuntimeError("Direct preview requires the exact active project lease")
        return job, project, workspace

    @staticmethod
    def _public(
        row: dict[str, Any] | None,
        *,
        job_id: str,
        workspace_mode: str,
        supported: bool,
    ) -> dict[str, Any]:
        if not row:
            return {
                "job_id": job_id,
                "workspace_mode": workspace_mode,
                "supported": supported,
                "target": None,
                "status": "not_built" if supported else "unsupported",
                "generation": 0,
                "frontend_url": None,
                "backend_url": None,
                "integration_note": None,
                "error": None,
                "updated_at": None,
                "stopped_at": None,
            }
        return {
            "job_id": job_id,
            "workspace_mode": workspace_mode,
            "supported": supported,
            "target": row.get("target"),
            "status": row.get("status"),
            "generation": int(row.get("generation") or 0),
            "frontend_url": row.get("frontend_url"),
            "backend_url": row.get("backend_url"),
            "integration_note": row.get("integration_note"),
            "error": row.get("error"),
            "updated_at": _iso(row.get("updated_at")),
            "stopped_at": _iso(row.get("stopped_at")),
        }

    async def start(self, job_id: str, target: PreviewTarget) -> dict[str, Any]:
        job, _project, workspace = self._direct_context(
            job_id,
            target=target,
            require_lease=True,
        )
        previous = self.storage.preview_state(job_id)
        generation = int((previous or {}).get("generation") or 0) + 1
        self.storage.upsert_preview_state(
            job_id=job_id,
            project_id=str(job["project_id"]),
            target=target,
            status="starting",
            generation=generation,
        )
        try:
            result = await self.ddev.preview_start(
                job_id=job_id,
                project_id=str(job["project_id"]),
                workspace=workspace,
                target=target,
            )
        except Exception as exc:
            failed = self.storage.upsert_preview_state(
                job_id=job_id,
                project_id=str(job["project_id"]),
                target=target,
                status="failed",
                generation=generation,
                error=_public_preview_error(exc),
            )
            return self._public(
                dict(failed),
                job_id=job_id,
                workspace_mode="direct",
                supported=True,
            )

        ready = self.storage.upsert_preview_state(
            job_id=job_id,
            project_id=str(job["project_id"]),
            target=target,
            status=str(result.get("status") or "ready"),
            generation=generation,
            frontend_url=result.get("frontend_url"),
            backend_url=result.get("backend_url"),
            integration_note=result.get("integration_note"),
        )
        return self._public(
            dict(ready),
            job_id=job_id,
            workspace_mode="direct",
            supported=True,
        )

    async def status(self, job_id: str) -> dict[str, Any]:
        job = self._job(job_id)
        mode = self._workspace_mode(job)
        project = project_config(str(job["project_id"]))
        supported = (
            mode == "direct"
            and str((project.get("runtime") or {}).get("workspace_mode") or "isolated_clone")
            == "direct"
            and bool(project.get("preview"))
        )
        state = self.storage.preview_state(job_id)
        if not supported:
            return self._public(
                dict(state) if state else None,
                job_id=job_id,
                workspace_mode=mode,
                supported=False,
            )
        if not state:
            return self._public(
                None,
                job_id=job_id,
                workspace_mode=mode,
                supported=True,
            )

        current = dict(state)
        target = str(current.get("target") or "")
        if target not in {"frontend", "backend", "both"}:
            return self._public(
                current,
                job_id=job_id,
                workspace_mode=mode,
                supported=True,
            )

        lease = self.storage.project_lease(str(job["project_id"]))
        lease_valid = bool(
            lease
            and str(lease.get("state") or "") == "active"
            and str(lease.get("owner_job_id") or "") == job_id
        )
        if not lease_valid:
            if str(current.get("status") or "") not in {"stopped", "not_built"}:
                try:
                    await self.ddev.preview_stop(
                        job_id=job_id,
                        project_id=str(job["project_id"]),
                        workspace=str(job.get("workspace") or ""),
                        target=target,
                    )
                except Exception:
                    pass
                current = dict(
                    self.storage.upsert_preview_state(
                        job_id=job_id,
                        project_id=str(job["project_id"]),
                        target=target,
                        status="stopped",
                        generation=int(current.get("generation") or 1),
                        error="Preview retired because the direct project lease is no longer active.",
                        stopped=True,
                    )
                )
            return self._public(
                current,
                job_id=job_id,
                workspace_mode=mode,
                supported=True,
            )

        if str(current.get("status") or "") in {"ready", "starting"}:
            try:
                observed = await self.ddev.preview_status(
                    job_id=job_id,
                    project_id=str(job["project_id"]),
                    workspace=str(job["workspace"]),
                    target=target,
                )
                observed_status = str(observed.get("status") or "stopped")
                if observed_status != str(current.get("status") or ""):
                    current = dict(
                        self.storage.upsert_preview_state(
                            job_id=job_id,
                            project_id=str(job["project_id"]),
                            target=target,
                            status=observed_status,
                            generation=int(current.get("generation") or 1),
                            frontend_url=observed.get("frontend_url"),
                            backend_url=observed.get("backend_url"),
                            integration_note=current.get("integration_note"),
                            stopped=observed_status == "stopped",
                        )
                    )
            except Exception as exc:
                current = dict(
                    self.storage.upsert_preview_state(
                        job_id=job_id,
                        project_id=str(job["project_id"]),
                        target=target,
                        status="failed",
                        generation=int(current.get("generation") or 1),
                        error=_public_preview_error(exc),
                    )
                )

        return self._public(
            current,
            job_id=job_id,
            workspace_mode=mode,
            supported=True,
        )

    async def stop(self, job_id: str) -> dict[str, Any]:
        job = self._job(job_id)
        mode = self._workspace_mode(job)
        state = self.storage.preview_state(job_id)
        if mode != "direct":
            raise RuntimeError("Live preview is supported only for direct-workspace jobs")
        if not state:
            return self._public(
                None,
                job_id=job_id,
                workspace_mode=mode,
                supported=True,
            )
        current = dict(state)
        target = str(current.get("target") or "both")
        workspace = str(job.get("workspace") or "").strip()
        if workspace:
            try:
                await self.ddev.preview_stop(
                    job_id=job_id,
                    project_id=str(job["project_id"]),
                    workspace=workspace,
                    target=target,
                )
            except Exception as exc:
                failed = self.storage.upsert_preview_state(
                    job_id=job_id,
                    project_id=str(job["project_id"]),
                    target=target,
                    status="failed",
                    generation=int(current.get("generation") or 1),
                    error=_public_preview_error(exc),
                )
                return self._public(
                    dict(failed),
                    job_id=job_id,
                    workspace_mode=mode,
                    supported=True,
                )

        stopped = self.storage.upsert_preview_state(
            job_id=job_id,
            project_id=str(job["project_id"]),
            target=target,
            status="stopped",
            generation=int(current.get("generation") or 1),
            stopped=True,
        )
        return self._public(
            dict(stopped),
            job_id=job_id,
            workspace_mode=mode,
            supported=True,
        )


def _project_preview_owner_id(project_id: str) -> str:
    digest = hashlib.sha256(project_id.encode("utf-8")).hexdigest()[:24]
    return f"project-preview-{digest}"


class ProjectPreviewManager:
    """Manage an idle direct-project preview without creating an engineering job."""

    def __init__(self, storage: Any, ddev: Any) -> None:
        self.storage = storage
        self.ddev = ddev
        self._states: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _target_supported(project: dict[str, Any], target: str) -> bool:
        return PreviewManager._target_supported(project, target)

    @staticmethod
    def _eligible(project: dict[str, Any]) -> bool:
        runtime = dict(project.get("runtime") or {})
        return (
            str(runtime.get("workspace_mode") or "isolated_clone") == "direct"
            and bool(project.get("preview"))
        )

    def projects(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        raw_projects = projects_doc().get("projects", {})
        if not isinstance(raw_projects, dict):
            return rows
        for project_id in sorted(str(value) for value in raw_projects):
            try:
                project = project_config(project_id)
            except Exception:
                continue
            if not self._eligible(project):
                continue
            preview = dict(project.get("preview") or {})
            backend = dict(preview.get("backend") or {})
            frontend = dict(preview.get("frontend") or {})
            targets: list[str] = []
            if bool(frontend.get("enabled", False)):
                targets.append("frontend")
            if bool(backend.get("enabled", False)):
                targets.append("backend")
            if {"frontend", "backend"}.issubset(set(targets)):
                targets.append("both")
            rows.append(
                {
                    "project_id": project_id,
                    "workspace_mode": "direct",
                    "base_branch": str(project.get("base_branch") or "main"),
                    "targets": targets,
                }
            )
        return rows

    def _context(
        self,
        project_id: str,
    ) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
        try:
            project = project_config(project_id)
        except (KeyError, ValueError) as exc:
            raise RuntimeError("Unknown or invalid project") from exc
        if not self._eligible(project):
            raise RuntimeError("Project-level preview requires a direct project with preview enabled")
        workspace = str(Path(str(project["path"])).resolve())
        approved = os.getenv("CODING_DIRECT_PROJECT_ROOT", "").strip()
        if approved and Path(workspace) != Path(approved).resolve():
            raise RuntimeError("Project preview path is not mounted as the approved direct project root")
        lease = self.storage.project_lease(project_id)
        return project, workspace, dict(lease) if lease else None

    @staticmethod
    def _repo_state(workspace: str) -> tuple[str | None, bool | None, str | None]:
        branch = subprocess.run(
            ["git", "-C", workspace, "branch", "--show-current"],
            text=True,
            capture_output=True,
        )
        if branch.returncode != 0:
            return None, None, "Direct project repository is unavailable."
        status = subprocess.run(
            ["git", "-C", workspace, "status", "--porcelain"],
            text=True,
            capture_output=True,
        )
        if status.returncode != 0:
            return branch.stdout.strip() or None, None, "Direct project repository status is unavailable."
        return branch.stdout.strip() or None, not bool(status.stdout.strip()), None

    @staticmethod
    def _component(
        observed: dict[str, Any] | None,
        *,
        kind: str,
    ) -> tuple[str, str | None]:
        if not observed:
            return "stopped", None
        ready = str(observed.get("status") or "") == "ready"
        if kind == "frontend":
            return (
                "ready" if ready and observed.get("frontend_url") else "stopped",
                observed.get("frontend_url") if ready else None,
            )
        return (
            "ready" if ready and observed.get("backend_url") else "stopped",
            observed.get("backend_url") if ready else None,
        )

    async def status(self, project_id: str) -> dict[str, Any]:
        project, workspace, lease = self._context(project_id)
        branch, clean, repo_error = self._repo_state(workspace)
        lease_active = bool(lease and str(lease.get("state") or "") == "active")
        state = dict(self._states.get(project_id) or {})
        generation = int(state.get("generation") or 0)
        target = state.get("target")
        error = state.get("error")

        if lease_active:
            return {
                "project_id": project_id,
                "workspace_mode": "direct",
                "supported": True,
                "base_branch": str(project.get("base_branch") or "main"),
                "branch": branch,
                "clean": clean,
                "ownership": "job",
                "active_job_id": lease.get("owner_job_id"),
                "controls_enabled": False,
                "target": target,
                "status": "job_owned",
                "generation": generation,
                "frontend_status": "job_owned",
                "backend_status": "job_owned",
                "frontend_url": None,
                "backend_url": None,
                "error": repo_error,
            }

        backend_observed: dict[str, Any] | None = None
        frontend_observed: dict[str, Any] | None = None
        preview = dict(project.get("preview") or {})
        try:
            if self._target_supported(project, "backend"):
                backend_observed = await self.ddev.preview_status(
                    job_id=_project_preview_owner_id(project_id),
                    project_id=project_id,
                    workspace=workspace,
                    target="backend",
                )
        except Exception:
            backend_observed = None
        try:
            if self._target_supported(project, "frontend"):
                frontend_observed = await self.ddev.preview_status(
                    job_id=_project_preview_owner_id(project_id),
                    project_id=project_id,
                    workspace=workspace,
                    target="frontend",
                )
        except Exception:
            frontend_observed = None

        frontend_status, frontend_url = self._component(
            frontend_observed,
            kind="frontend",
        )
        backend_status, backend_url = self._component(
            backend_observed,
            kind="backend",
        )

        state_status = str(state.get("status") or "")
        if state_status == "starting":
            status = "starting"
        elif state_status == "failed":
            status = "failed"
        elif frontend_status == "ready" and backend_status == "ready":
            status = "ready"
            target = target or "both"
            error = None
        elif frontend_status == "ready":
            status = "ready"
            target = target or "frontend"
            error = None
        elif backend_status == "ready":
            status = "ready"
            target = target or "backend"
            if state_status != "failed":
                error = None
        else:
            status = "stopped"
            if state_status not in {"failed"}:
                error = None

        if state_status == "ready" and status == "stopped":
            self._states[project_id] = {
                **state,
                "status": "stopped",
                "error": None,
            }

        return {
            "project_id": project_id,
            "workspace_mode": "direct",
            "supported": True,
            "base_branch": str(project.get("base_branch") or "main"),
            "branch": branch,
            "clean": clean,
            "ownership": "idle",
            "active_job_id": None,
            "controls_enabled": bool(clean is True and repo_error is None),
            "target": target,
            "status": status,
            "generation": generation,
            "frontend_status": frontend_status,
            "backend_status": backend_status,
            "frontend_url": frontend_url,
            "backend_url": backend_url,
            "error": repo_error or error,
        }

    async def start(self, project_id: str, target: PreviewTarget) -> dict[str, Any]:
        project, workspace, lease = self._context(project_id)
        if lease and str(lease.get("state") or "") == "active":
            raise RuntimeError("Project preview is unavailable while a direct engineering job owns the project")
        if not self._target_supported(project, target):
            raise RuntimeError(f"Preview target {target!r} is not enabled for this project")
        branch, clean, repo_error = self._repo_state(workspace)
        if repo_error or not branch:
            raise RuntimeError(repo_error or "Direct project repository is unavailable")
        if clean is not True:
            raise RuntimeError("Project preview refuses to mutate DDEV while the direct repository is dirty")

        previous = dict(self._states.get(project_id) or {})
        generation = int(previous.get("generation") or 0) + 1
        self._states[project_id] = {
            "target": target,
            "status": "starting",
            "generation": generation,
            "error": None,
        }
        try:
            await self.ddev.preview_start(
                job_id=_project_preview_owner_id(project_id),
                project_id=project_id,
                workspace=workspace,
                target=target,
            )
        except Exception as exc:
            self._states[project_id] = {
                "target": target,
                "status": "failed",
                "generation": generation,
                "error": _public_preview_error(exc),
            }
            return await self.status(project_id)

        self._states[project_id] = {
            "target": target,
            "status": "ready",
            "generation": generation,
            "error": None,
        }
        return await self.status(project_id)

    async def stop(self, project_id: str) -> dict[str, Any]:
        _project, workspace, lease = self._context(project_id)
        if lease and str(lease.get("state") or "") == "active":
            raise RuntimeError("Project preview is owned by an active direct engineering job")
        state = dict(self._states.get(project_id) or {})
        target = str(state.get("target") or "both")
        try:
            await self.ddev.preview_stop(
                job_id=_project_preview_owner_id(project_id),
                project_id=project_id,
                workspace=workspace,
                target=target if target in {"frontend", "backend", "both"} else "both",
            )
        except Exception as exc:
            self._states[project_id] = {
                **state,
                "target": target,
                "status": "failed",
                "error": _public_preview_error(exc),
            }
            return await self.status(project_id)
        self._states[project_id] = {
            **state,
            "target": target,
            "status": "stopped",
            "error": None,
        }
        return await self.status(project_id)

    async def handoff_to_job(self, project_id: str, job_id: str) -> None:
        _project, workspace, lease = self._context(project_id)
        if (
            not lease
            or str(lease.get("state") or "") != "active"
            or str(lease.get("owner_job_id") or "") != job_id
        ):
            raise RuntimeError("Idle preview handoff requires the exact active direct project lease")

        last_error: Exception | None = None
        for attempt in range(60):
            try:
                await self.ddev.preview_stop(
                    job_id=_project_preview_owner_id(project_id),
                    project_id=project_id,
                    workspace=workspace,
                    target="both",
                )
                state = dict(self._states.get(project_id) or {})
                self._states[project_id] = {
                    **state,
                    "status": "stopped",
                    "error": None,
                }
                return
            except Exception as exc:
                last_error = exc
                lower = str(exc).lower()
                busy = "active process" in lower or "busy" in lower
                if busy:
                    if attempt < 59:
                        await asyncio.sleep(1)
                    continue
                # ddev-executor stop_preview may have already stopped the
                # PCP-owned daemon and removed its preview override before the
                # final topology reconciliation fails. One immediate retry is
                # safe and idempotent: if retirement already completed it
                # observes no managed override; if the failure is persistent,
                # the second non-busy failure still stops here.
                if attempt == 0:
                    continue
                break
        raise RuntimeError("Idle project preview could not be retired before direct job handoff") from last_error



async def ready_preview_context(
    storage: Any,
    ddev: Any,
    job_id: str,
) -> dict[str, Any] | None:
    """Return only a currently reconciled, browser-safe Ready preview context."""
    try:
        state = await PreviewManager(storage, ddev).status(job_id)
    except Exception:
        return None
    if state.get("status") != "ready" or not state.get("supported"):
        return None
    context = {
        "status": "ready",
        "target": state.get("target"),
        "frontend_url": state.get("frontend_url"),
        "backend_url": state.get("backend_url"),
        "integration_note": state.get("integration_note"),
        "usage_note": (
            "This URL is available for bounded local review where tooling supports it. "
            "Availability alone is not evidence that visual/browser review occurred."
        ),
    }
    return {
        key: value
        for key, value in context.items()
        if value is not None
    }
