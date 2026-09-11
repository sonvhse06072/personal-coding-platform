import app.main as main


def test_cancel_endpoint_uses_job_id(monkeypatch):
    seen = []

    def fake_cancel(job_id):
        seen.append(job_id)
        return True

    monkeypatch.setattr(main, "cancel_active", fake_cancel)
    result = main.cancel(main.CancelRequest(job_id="job12345"))
    assert result == {"job_id": "job12345", "cancelled": True}
    assert seen == ["job12345"]
