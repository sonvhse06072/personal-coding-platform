import asyncio

from app import main as main_module
from app.main import RUNTIME_VERSION, app


def test_runtime_version_is_1_0_115():
    assert RUNTIME_VERSION == "1.0.115"
    assert app.version == RUNTIME_VERSION


def test_runtime_health_reports_same_runtime_version(monkeypatch):
    async def healthy():
        return True

    monkeypatch.setattr(main_module.engine.router, "health", healthy)
    monkeypatch.setattr(main_module.engine.ddev, "health", healthy)

    payload = asyncio.run(main_module.health())

    assert payload.version == RUNTIME_VERSION
