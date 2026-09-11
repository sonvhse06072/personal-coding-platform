from app.fingerprint import failure_fingerprint


def test_fingerprint_normalizes_numbers():
    assert failure_fingerprint("Expected 123 got 456") == failure_fingerprint("Expected 999 got 888")
