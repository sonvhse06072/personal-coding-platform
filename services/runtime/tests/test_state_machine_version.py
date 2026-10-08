import asyncio

from app import main as main_module
from app.main import RUNTIME_VERSION, app


def test_runtime_version_is_1_0_141():
    assert RUNTIME_VERSION == "1.0.141"
    assert app.version == RUNTIME_VERSION


def test_runtime_health_reports_same_runtime_version(monkeypatch):
    async def healthy():
        return True

    monkeypatch.setattr(main_module.engine.router, "health", healthy)
    monkeypatch.setattr(main_module.engine.ddev, "health", healthy)

    payload = asyncio.run(main_module.health())

    assert payload.version == RUNTIME_VERSION


def test_guardian_active_engineering_count_includes_claimed_late_reviews(monkeypatch):
    monkeypatch.setattr(main_module.storage, "count_active_engineering_jobs", lambda: 1)
    monkeypatch.setattr(main_module.plan_orchestrator.late_reviews.store, "active_count", lambda: 2)

    result = main_module.active_engineering_work_count()

    assert result.active_engineering_jobs == 3
