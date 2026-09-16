from pathlib import Path


def test_provider_quota_telemetry_documented():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "project" / "provider-quota-telemetry.md").read_text(encoding="utf-8")
    assert "account/rateLimits/read" in text
    assert "GetUserStatus" in text
    assert "fail-open" in text
    assert "does not consume model/tool/test budgets" in text
