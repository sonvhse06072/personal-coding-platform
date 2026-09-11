from app.adapters.base import classify_provider_failure


def test_usage_limit_is_provider_failure():
    kind, message = classify_provider_failure("You have reached your usage limit. Try again later.")
    assert kind == "quota_exhausted"
    assert "usage limit" in message.lower()


def test_normal_output_is_not_provider_failure():
    kind, message = classify_provider_failure("Implemented test and all checks pass")
    assert kind is None
    assert message is None
