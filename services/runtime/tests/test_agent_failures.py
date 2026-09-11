from app.adapters.base import classify_provider_failure


def test_usage_limit_is_provider_failure():
    kind, message = classify_provider_failure("You have reached your usage limit. Try again later.")
    assert kind == "quota_exhausted"
    assert "usage limit" in message.lower()


def test_normal_output_is_not_provider_failure():
    kind, message = classify_provider_failure("Implemented test and all checks pass")
    assert kind is None
    assert message is None


def test_antigravity_keyring_failure_is_authentication_failure():
    kind, message = classify_provider_failure("Error: failed to retrieve token: secret keyring is locked")
    assert kind == "authentication"
    assert "keyring" in message.lower()


def test_opencode_unexpected_server_error_is_provider_unavailable():
    kind, message = classify_provider_failure(
        '{"error":{"name":"UnknownError","data":{"message":"Unexpected server error. Check server logs for details."}}}'
    )
    assert kind == "provider_unavailable"
    assert "unexpected server error" in message.lower()
