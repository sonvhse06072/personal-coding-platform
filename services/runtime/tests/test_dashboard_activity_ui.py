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



def test_dashboard_exposes_direct_preview_controls_without_internal_runtime_credentials():
    assert 'id="previewCard"' in DASHBOARD_HTML
    assert "Frontend" in DASHBOARD_HTML
    assert "Backend" in DASHBOARD_HTML
    assert "Both" in DASHBOARD_HTML
    assert "Start Preview" in DASHBOARD_HTML
    assert "Rebuild" in DASHBOARD_HTML
    assert "Stop" in DASHBOARD_HTML
    assert "Unlock controls" in DASHBOARD_HTML
    assert "/v1/dashboard/control-session" in DASHBOARD_HTML
    assert "/v1/dashboard/jobs/" in DASHBOARD_HTML
    assert "RUNTIME_API_TOKEN" not in DASHBOARD_HTML
    assert "PLATFORM_INTERNAL_TOKEN" not in DASHBOARD_HTML
    assert "GITHUB_DELIVERY_TOKEN" not in DASHBOARD_HTML
