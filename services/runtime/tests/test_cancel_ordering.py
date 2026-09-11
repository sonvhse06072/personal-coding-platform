import asyncio
from datetime import datetime, timezone

import app.main as main


def test_cancel_endpoint_drains_side_effects_before_engine_terminal_transition(monkeypatch):
    events = []
    job_id = "job12345"

    async def cancel_ddev(*, job_id: str):
        events.append(("ddev", job_id))
        return {"cancelled": True}

    async def cancel_engine(job_id: str):
        events.append(("engine", job_id))
        now = datetime.now(timezone.utc)
        return {
            "id": job_id,
            "project_id": "default",
            "status": "cancelled",
            "source_commit": None,
            "branch": None,
            "workspace": None,
            "task": {},
            "repo_analysis": None,
            "route": None,
            "progress": {},
            "checkpoint": {},
            "result": None,
            "error": None,
            "dry_run": False,
            "created_at": now,
            "updated_at": now,
        }

    async def scenario():
        async def active_agent():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                events.append(("agent", job_id))
                raise

        task = asyncio.create_task(active_agent())
        main.engine.active_jobs[job_id] = task
        await asyncio.sleep(0)
        try:
            return await main.cancel_job(job_id)
        finally:
            main.engine.active_jobs.pop(job_id, None)
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    monkeypatch.setattr(main.engine.ddev, "cancel", cancel_ddev)
    monkeypatch.setattr(main.engine, "cancel", cancel_engine)

    result = asyncio.run(scenario())
    assert result.status == "cancelled"
    assert events == [
        ("ddev", job_id),
        ("agent", job_id),
        ("engine", job_id),
    ]
