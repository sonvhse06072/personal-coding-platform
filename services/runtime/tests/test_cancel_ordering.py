import asyncio
from datetime import datetime, timezone

import app.main as main


def test_cancel_endpoint_drains_ddev_before_engine_terminal_transition(monkeypatch):
    events = []

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

    monkeypatch.setattr(main.engine.ddev, "cancel", cancel_ddev)
    monkeypatch.setattr(main.engine, "cancel", cancel_engine)

    result = asyncio.run(main.cancel_job("job12345"))
    assert result.status == "cancelled"
    assert events == [("ddev", "job12345"), ("engine", "job12345")]
