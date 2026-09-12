from app.main import app


def test_runtime_version_is_1_0_22():
    assert app.version == "1.0.22"
