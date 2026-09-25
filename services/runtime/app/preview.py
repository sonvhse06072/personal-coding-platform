from __future__ import annotations

from typing import Any, Literal

from .config import project_config


PreviewTarget = Literal["frontend", "backend", "both"]


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
                error=str(exc)[-2000:],
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
                        error=str(exc)[-2000:],
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
                    error=str(exc)[-2000:],
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
