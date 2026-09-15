from app.main import app


def test_router_version_is_1_0_17():
    assert app.version == "1.0.17"
