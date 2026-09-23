from app import main


def test_active_engineering_count_endpoint_uses_authoritative_storage(monkeypatch):
    monkeypatch.setattr(main.storage, "count_active_engineering_jobs", lambda: 1)

    response = main.active_engineering_work_count()

    assert response.active_engineering_jobs == 1


def test_active_engineering_count_route_precedes_dynamic_job_route():
    paths = [route.path for route in main.app.routes]

    assert paths.index("/v1/jobs/active-count") < paths.index("/v1/jobs/{job_id}")
