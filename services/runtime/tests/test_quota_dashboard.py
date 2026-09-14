from app.dashboard_ui import DASHBOARD_HTML


def test_dashboard_exposes_provider_quota_without_guessing_unknown_values():
    assert "Provider quota" in DASHBOARD_HTML
    assert "/v1/dashboard/quota" in DASHBOARD_HTML
    assert "used_percent" in DASHBOARD_HTML
    assert "remaining_percent" in DASHBOARD_HTML
    assert "reset_at" in DASHBOARD_HTML
    assert "fresh" in DASHBOARD_HTML
    assert "unknown/stale values are never inferred" in DASHBOARD_HTML


def test_quota_ui_distinguishes_internal_antigravity_source():
    assert "internal/local API" in DASHBOARD_HTML
    assert "source_supported" in DASHBOARD_HTML
