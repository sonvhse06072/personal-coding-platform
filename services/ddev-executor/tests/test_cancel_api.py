from fastapi.testclient import TestClient

import app.main as main


def test_cancel_endpoint_uses_job_id(monkeypatch):
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "test-token")
    seen = []

    def fake_cancel(job_id):
        seen.append(job_id)
        return True

    monkeypatch.setattr(main, "cancel_active", fake_cancel)
    client = TestClient(main.app)
    response = client.post(
        "/v1/cancel",
        headers={"Authorization": "Bearer test-token"},
        json={"job_id": "job12345"},
    )
    assert response.status_code == 200
    assert response.json() == {"job_id": "job12345", "cancelled": True}
    assert seen == ["job12345"]
