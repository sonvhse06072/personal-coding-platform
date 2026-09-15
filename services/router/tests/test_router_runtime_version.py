from app.main import app


def test_router_version_is_1_0_19():
    assert app.version == "1.0.19"
