"""C2 DB-only source contract. No Docker, Postgres, host or model calls."""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
C2 = ROOT / "deploy/fullpath/compose.c2-db-only.yml"
SQL = ROOT / "deploy/fullpath/db-c2-init-app-role.sql"
PARKED = ROOT / "deploy/fullpath/compose.source-only.yml"


def _c2():
    return yaml.safe_load(C2.read_text(encoding="utf-8"))


def test_only_new_f2_postgres_resource_without_any_other_service():
    doc = _c2()
    assert doc["name"] == "pcp-f2-fullpath"
    assert set(doc["services"]) == {"fullpath-db"}
    db = doc["services"]["fullpath-db"]
    assert db["container_name"] == "pcp-f2-fullpath-fullpath-db-1"
    assert db["pull_policy"] == "never"
    assert db["restart"] == "no"
    assert db["image"].startswith("${PCP_F2_POSTGRES_IMAGE:?")
    assert "entrypoint" not in db
    assert "command" not in db
    assert db.get("ports") is None
    assert db.get("privileged") is not True
    assert db.get("build") is None
    assert db.get("depends_on") is None
    assert db["networks"] == ["fullpath-private"]
    assert db["mem_limit"] == "512m"
    assert db["labels"]["pcp.scope"] == "f2-c2-db-only"
    assert set(doc["volumes"]) == {"fullpath-db-data"}
    assert doc["volumes"]["fullpath-db-data"]["name"] == (
        "pcp-f2-fullpath-postgres-data"
    )
    assert set(doc["networks"]) == {"fullpath-private"}
    assert doc["networks"]["fullpath-private"]["name"] == (
        "pcp-f2-fullpath-private"
    )
    assert doc["networks"]["fullpath-private"]["internal"] is True


def test_secrets_are_file_only_and_never_exposed_to_other_services():
    doc = _c2()
    db = doc["services"]["fullpath-db"]
    env = db["environment"]
    assert env["POSTGRES_DB"] == "fullpath"
    assert env["POSTGRES_USER"] == "fullpath_bootstrap_admin"
    assert env["POSTGRES_PASSWORD_FILE"] == "/run/secrets/f2_db_admin_password"
    assert all("PASSWORD" not in k or k == "POSTGRES_PASSWORD_FILE" for k in env)
    assert set(doc["secrets"]) == {
        "f2_db_admin_password", "f2_db_app_password",
    }
    assert set(x["source"] for x in db["secrets"]) == set(doc["secrets"])
    assert all(
        val["file"].startswith("${PCP_F2_DB_")
        for val in doc["secrets"].values()
    )
    assert not any(
        "docker.sock" in str(v) or "chonhac" in str(v)
        for v in (str(doc), str(C2.read_text(encoding="utf-8")))
    )


def test_only_new_volume_and_readonly_reviewed_init_sql_are_mounted():
    mounts = _c2()["services"]["fullpath-db"]["volumes"]
    assert len(mounts) == 2
    assert mounts[0] == {
        "type": "volume",
        "source": "fullpath-db-data",
        "target": "/var/lib/postgresql/data",
    }
    assert mounts[1]["type"] == "bind"
    assert mounts[1]["source"] == "./db-c2-init-app-role.sql"
    assert mounts[1]["target"] == (
        "/docker-entrypoint-initdb.d/10-f2-app-role.sql"
    )
    assert mounts[1]["read_only"] is True
    assert mounts[1]["bind"] == {"create_host_path": False}


def test_app_role_is_separate_unprivileged_and_does_not_create_app_schema():
    text = SQL.read_text(encoding="utf-8")
    normalized = " ".join(
        line.strip() for line in text.splitlines()
        if not line.lstrip().startswith("--")
    ).upper()
    assert "CREATE ROLE FULLPATH WITH LOGIN NOINHERIT NOSUPERUSER" in normalized
    for token in ("NOCREATEDB", "NOCREATEROLE", "NOREPLICATION", "NOBYPASSRLS"):
        assert token in normalized
    assert "PASSWORD :'APP_PASSWORD'" in normalized
    assert "GRANT CONNECT ON DATABASE FULLPATH TO FULLPATH;" in normalized
    assert "GRANT USAGE ON SCHEMA PUBLIC TO FULLPATH;" in normalized
    assert "REVOKE ALL PRIVILEGES ON DATABASE FULLPATH FROM PUBLIC;" in normalized
    assert "REVOKE ALL PRIVILEGES ON SCHEMA PUBLIC FROM PUBLIC;" in normalized
    assert "\\SET ON_ERROR_STOP ON" in normalized
    assert "BEGIN;" in normalized and "COMMIT;" in normalized
    assert "CREATE TABLE" not in normalized
    assert "CREATE INDEX" not in normalized
    assert "CP_" not in normalized
    assert "UPDATE " not in normalized and "DELETE " not in normalized
    assert "DROP " not in normalized
    assert "/RUN/SECRETS/F2_DB_APP_PASSWORD" in normalized


def test_source_only_four_service_contract_remains_parked():
    doc = yaml.safe_load(PARKED.read_text(encoding="utf-8"))
    assert set(doc["services"]) == {
        "fullpath-db", "fullpath-runtime", "fullpath-executor",
        "fullpath-router",
    }
    for item in doc["services"].values():
        assert item["entrypoint"] == ["/bin/false"]
    assert doc["x-f2-contract"]["operational_activation_authorized"] is False
