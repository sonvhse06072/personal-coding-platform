from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy

import pytest

from app.storage import DDL, Storage


class Result:
    def __init__(self, row=None, *, rowcount=0):
        self.row = deepcopy(row)
        self.rowcount = rowcount

    def fetchone(self):
        return deepcopy(self.row)


class Connection:
    def __init__(self):
        self.jobs = {
            "job-one": {"id": "job-one", "project_id": "demo", "status": "queued"},
            "job-two": {"id": "job-two", "project_id": "demo", "status": "queued"},
        }
        self.lease = None
        self.commits = 0

    def execute(self, query, params=None):
        compact = " ".join(query.split())
        values = tuple(params or ())

        if compact.startswith("SELECT id, project_id, status FROM cp_jobs"):
            return Result(self.jobs.get(values[0]))
        if compact.startswith("SELECT * FROM cp_project_leases WHERE project_id="):
            return Result(self.lease if self.lease and self.lease["project_id"] == values[0] else None)
        if compact.startswith("SELECT status FROM cp_jobs WHERE id="):
            job = self.jobs.get(values[0])
            return Result({"status": job["status"]} if job else None)
        if compact.startswith("INSERT INTO cp_project_leases"):
            project_id, owner_job_id, acquired_at, updated_at = values
            self.lease = {
                "project_id": project_id,
                "owner_job_id": owner_job_id,
                "generation": 1,
                "state": "active",
                "acquired_at": acquired_at,
                "updated_at": updated_at,
            }
            return Result(rowcount=1)
        if compact.startswith("UPDATE cp_project_leases SET owner_job_id="):
            owner_job_id, generation, acquired_at, updated_at, project_id = values
            assert self.lease and self.lease["project_id"] == project_id
            self.lease.update(
                owner_job_id=owner_job_id,
                generation=generation,
                state="active",
                acquired_at=acquired_at,
                updated_at=updated_at,
            )
            return Result(rowcount=1)
        if compact.startswith("UPDATE cp_project_leases SET state='released'"):
            updated_at, project_id, owner_job_id = values
            if (
                self.lease
                and self.lease["project_id"] == project_id
                and self.lease["owner_job_id"] == owner_job_id
            ):
                self.lease.update(state="released", updated_at=updated_at)
                return Result(rowcount=1)
            return Result(rowcount=0)
        if compact.startswith("UPDATE cp_project_leases lease SET state='released'"):
            updated_at, terminal = values
            terminal_set = set(terminal)
            if self.lease and self.lease["state"] == "active":
                owner = self.jobs.get(self.lease["owner_job_id"])
                if owner and owner["status"] in terminal_set:
                    self.lease.update(state="released", updated_at=updated_at)
                    return Result(rowcount=1)
            return Result(rowcount=0)
        raise AssertionError(f"Unexpected SQL: {compact}")

    def commit(self):
        self.commits += 1


def storage(connection: Connection) -> Storage:
    value = Storage()

    @contextmanager
    def connect():
        yield connection

    value.connect = connect
    return value


def test_project_lease_schema_is_durable_and_indexed():
    assert "CREATE TABLE IF NOT EXISTS cp_project_leases" in DDL
    assert "project_id TEXT PRIMARY KEY" in DDL
    assert "owner_job_id TEXT NOT NULL REFERENCES cp_jobs(id)" in DDL
    assert "cp_project_leases_owner_idx" in DDL


def test_same_job_reacquires_direct_project_lease_idempotently():
    connection = Connection()
    store = storage(connection)

    first = store.acquire_project_lease("demo", "job-one")
    second = store.acquire_project_lease("demo", "job-one")

    assert first["generation"] == 1
    assert first["reused"] is False
    assert second["generation"] == 1
    assert second["reused"] is True
    assert connection.lease["owner_job_id"] == "job-one"
    assert connection.lease["state"] == "active"


def test_second_non_terminal_job_cannot_steal_direct_project_lease():
    connection = Connection()
    store = storage(connection)
    store.acquire_project_lease("demo", "job-one")

    with pytest.raises(RuntimeError, match="leased by active job job-one"):
        store.acquire_project_lease("demo", "job-two")

    assert connection.lease["owner_job_id"] == "job-one"
    assert connection.lease["generation"] == 1


def test_terminal_owner_allows_next_job_to_acquire_new_generation():
    connection = Connection()
    store = storage(connection)
    store.acquire_project_lease("demo", "job-one")
    connection.jobs["job-one"]["status"] = "completed"

    acquired = store.acquire_project_lease("demo", "job-two")

    assert acquired["owner_job_id"] == "job-two"
    assert acquired["generation"] == 2
    assert acquired["state"] == "active"


def test_release_is_exact_and_idempotent():
    connection = Connection()
    store = storage(connection)
    store.acquire_project_lease("demo", "job-one")

    with pytest.raises(RuntimeError, match="owned by a different job"):
        store.release_project_lease("demo", "job-two")

    assert store.release_project_lease("demo", "job-one") is True
    assert store.release_project_lease("demo", "job-one") is False
    assert connection.lease["state"] == "released"


def test_reconcile_releases_only_terminal_owner():
    connection = Connection()
    store = storage(connection)
    store.acquire_project_lease("demo", "job-one")

    assert store.reconcile_terminal_project_leases() == 0
    assert connection.lease["state"] == "active"

    connection.jobs["job-one"]["status"] = "failed"

    assert store.reconcile_terminal_project_leases() == 1
    assert connection.lease["state"] == "released"
