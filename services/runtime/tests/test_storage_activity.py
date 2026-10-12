import json
from contextlib import contextmanager

import pytest

from app.storage import DDL, Storage


class _Result:
    def __init__(self, *, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self):
        self.current = {"status": "executing", "route": None, "workspace": "/tmp/job-1"}
        self.events = []
        self.recent_rows = []
        self.queries = []
        self.commits = 0
        self.active_engineering_jobs = 0
        self.prefix_rows = []

    def execute(self, query, params=None):
        compact = " ".join(query.split())
        self.queries.append((compact, params))
        if compact.startswith("SELECT status, route, workspace FROM cp_jobs"):
            return _Result(row=self.current)
        if compact.startswith("SELECT COUNT(*) AS active_engineering_jobs FROM cp_jobs"):
            return _Result(row={"active_engineering_jobs": self.active_engineering_jobs})
        if compact.startswith("SELECT id, project_id, status, workspace FROM cp_jobs WHERE LEFT(id, 10)=%s"):
            return _Result(rows=self.prefix_rows)
        if compact.startswith("INSERT INTO cp_job_events"):
            self.events.append(params)
        if "ROW_NUMBER() OVER (PARTITION BY job_id" in compact:
            return _Result(rows=self.recent_rows)
        return _Result()

    def commit(self):
        self.commits += 1


def _storage(connection):
    storage = Storage()

    @contextmanager
    def connect():
        yield connection

    storage.connect = connect
    return storage


def test_job_event_schema_is_durable_and_indexed_per_job():
    assert "CREATE TABLE IF NOT EXISTS cp_job_events" in DDL
    assert "REFERENCES cp_jobs(id) ON DELETE CASCADE" in DDL
    assert "cp_job_events_job_id_idx" in DDL


def test_active_engineering_count_queries_the_complete_job_table():
    connection = _Connection()
    connection.active_engineering_jobs = 1
    storage = _storage(connection)

    assert storage.count_active_engineering_jobs() == 1

    query, params = connection.queries[-1]
    assert "COUNT(*) AS active_engineering_jobs FROM cp_jobs" in query
    assert "status IS NULL OR status NOT IN (%s, %s, %s, %s)" in query
    assert "LIMIT" not in query
    assert params == ("blocked", "cancelled", "completed", "failed")


def test_create_persists_the_initial_registration_event():
    connection = _Connection()
    storage = _storage(connection)

    storage.create({
        "id": "job-1",
        "project_id": "demo",
        "status": "queued",
        "task": {"description": "PRIVATE TASK"},
        "progress": {},
        "checkpoint": {},
    })

    assert len(connection.events) == 1
    assert connection.events[0][0:5] == (
        "job-1",
        "job_registered",
        "queue",
        "info",
        "Job registered",
    )
    assert json.loads(connection.events[0][5]) == {}


def test_update_records_route_and_real_status_transition_without_raw_route():
    connection = _Connection()
    storage = _storage(connection)
    route = {
        "private_reason": "DO NOT LEAK",
        "strategy": {
            "profile": "complex",
            "executor": {
                "id": "codex_terra",
                "provider": "openai",
                "model": "gpt-5.6-terra",
                "reasoning_effort": "medium",
                "reasons": ["PRIVATE ROUTING DETAIL"],
            },
        },
    }

    storage.update("job-1", status="verifying", route=route)

    assert [params[1] for params in connection.events] == [
        "route_selected",
        "verification_started",
    ]
    route_data = json.loads(connection.events[0][5])
    assert route_data["executor"]["id"] == "codex_terra"
    assert "DO NOT LEAK" not in json.dumps(route_data)
    assert "PRIVATE ROUTING DETAIL" not in json.dumps(route_data)
    assert json.loads(connection.events[1][5]) == {
        "from_status": "executing",
        "to_status": "verifying",
    }


def test_update_persists_sanitized_block_activity():
    connection = _Connection()
    storage = _storage(connection)
    storage.update(
        "job-1",
        status="blocked",
        result={"reason": "provider_failure_without_fallback"},
    )
    assert [params[1] for params in connection.events] == ["job_blocked", "runtime_activity"]
    activity = connection.events[-1]
    assert activity[2] == "blocked"
    assert activity[3] == "error"
    assert "provider_failure_without_fallback" in activity[4]


def test_update_does_not_duplicate_an_unchanged_status_or_route():
    connection = _Connection()
    route = {"strategy": {"profile": "standard"}}
    connection.current = {"status": "verifying", "route": route, "workspace": "/tmp/job-1"}
    storage = _storage(connection)

    storage.update("job-1", status="verifying", route=route, progress={"test_runs": 2})

    assert connection.events == []
    assert connection.commits == 1


def test_recent_events_uses_per_job_window_and_chronological_order():
    connection = _Connection()
    connection.recent_rows = [{"id": 2, "job_id": "job-1"}]
    storage = _storage(connection)

    rows = storage.recent_events(["job-1", "job-1", "job-2"], per_job_limit=500)

    assert rows == connection.recent_rows
    query, params = connection.queries[-1]
    assert "WHERE job_id = ANY(%s)" in query
    assert "ORDER BY job_id, id" in query
    assert params == (["job-1", "job-2"], 100)


def test_job_prefix_lookup_is_exact_and_unbounded_by_recent_list_limit():
    connection = _Connection()
    connection.prefix_rows = [
        {
            "id": "0123456789abcdef0123456789abcdef",
            "project_id": "demo",
            "status": "completed",
            "workspace": "/tmp/workspace",
        }
    ]
    storage = _storage(connection)

    rows = storage.jobs_with_id_prefix("0123456789")

    assert rows == connection.prefix_rows
    query, params = connection.queries[-1]
    assert "LEFT(id, 10)=%s" in query
    assert "LIMIT" not in query
    assert params == ("0123456789",)


def test_job_prefix_lookup_refuses_non_exact_hex_prefix():
    storage = _storage(_Connection())

    with pytest.raises(ValueError):
        storage.jobs_with_id_prefix("job-prefix")


def test_normal_storage_init_keeps_schema_and_recovery_atomic():
    """Existing normal Runtime still executes the original two SQL steps once."""
    from datetime import datetime, timezone

    connection = _Connection()
    storage = _storage(connection)
    storage.init()

    assert len(connection.queries) == 2
    assert connection.queries[0] == (" ".join(DDL.split()), None)
    statement, params = connection.queries[1]
    assert statement.startswith("UPDATE cp_execution_plans SET status='interrupted'")
    assert "WHERE status='planning'" in statement
    assert params is not None and len(params) == 1
    assert isinstance(params[0], datetime)
    assert params[0].tzinfo is timezone.utc
    assert connection.commits == 1


def test_schema_step_does_not_run_restart_dml_or_commit_on_its_own():
    """Private refactor seam is only DDL; it creates no alternate installer."""
    connection = _Connection()
    Storage._apply_core_schema_on_connection(connection)
    assert connection.queries == [(" ".join(DDL.split()), None)]
    assert connection.commits == 0


@pytest.mark.parametrize("fail_step", ["schema", "recovery"])
def test_legacy_init_failure_cannot_partially_commit(fail_step):
    """A failure still aborts before commit, keeping one legacy transaction."""
    class FailingConnection(_Connection):
        def execute(self, query, params=None):
            compact = " ".join(query.split())
            if fail_step == "schema" and compact == " ".join(DDL.split()):
                raise RuntimeError("schema step failed")
            if fail_step == "recovery" and compact.startswith(
                "UPDATE cp_execution_plans SET status='interrupted'"
            ):
                raise RuntimeError("recovery step failed")
            return super().execute(query, params)

    conn = FailingConnection()
    storage = _storage(conn)
    with pytest.raises(RuntimeError, match="step failed"):
        storage.init()
    assert conn.commits == 0
    statements = [sql for sql, _ in conn.queries]
    if fail_step == "schema":
        assert statements == []
    else:
        assert statements == [" ".join(DDL.split())]
