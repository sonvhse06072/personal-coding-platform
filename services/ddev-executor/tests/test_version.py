from app.main import app


def test_ddev_executor_version_is_1_0_15():
    assert app.version == "1.0.15"
