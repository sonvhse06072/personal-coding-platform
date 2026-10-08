from types import SimpleNamespace

from app import main


def test_ddev_executor_version_is_1_0_35():
    assert main.app.version == "1.0.35"


def test_ddev_executor_health_reports_1_0_35(monkeypatch):
    monkeypatch.setattr(
        main.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )

    assert main.health()["version"] == "1.0.35"
