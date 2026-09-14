from app.dashboard_ui import DASHBOARD_HTML


def test_dashboard_uses_provider_neutral_live_activity_labels_and_filters():
    assert ">Live Developer Activity<" in DASHBOARD_HTML
    assert ">Developer activity<" in DASHBOARD_HTML
    assert "model/tool/verification activity across providers" in DASHBOARD_HTML
    assert "runtime_activity" in DASHBOARD_HTML
    assert "activityIdentity" in DASHBOARD_HTML
    assert "d.provider" in DASHBOARD_HTML
    assert "d.model" in DASHBOARD_HTML
    assert "d.adapter" in DASHBOARD_HTML
    assert "raw chain-of-thought and secrets are never exposed" in DASHBOARD_HTML
