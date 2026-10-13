#!/usr/bin/env python3
"""Emit an exact, one-time F2-only PostgreSQL schema transaction.

NO Docker / database / host writes / credentials / provider calls. SQL is emitted
only on explicit --emit-sql, for a separate Owner-approved F2-only DB operation.
The existing fullpath_schema_bootstrap_source.py audit remains source-only/STOP.
"""
from __future__ import annotations

import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIELDS = {
    "storage": "DDL",
    "plan_orchestrator": "ORCHESTRATOR_DDL",
    "telemetry_storage": "TELEMETRY_DDL",
    "control_actions": "CONTROL_DDL",
    "plan_progress_store": "DDL",
    "job_status_publisher": "DDL",
    "pm_bridge": "BRIDGE_DDL",
    "pm_control": "CONTROL_DDL",
    "pm_late_review": "LATE_REVIEW_DDL",
    "pm_merge_audit": "PM_MERGE_AUDIT_DDL",
    "pm_chat_review": "PM_CHAT_REVIEW_DDL",
    "quota_telemetry": "DDL",
}
OMIT_HISTORICAL_DML = {
    ("control_actions", "UPDATE cp_control_actions SET generation_fingerprint=state_fingerprint WHERE generation_fingerprint IS NULL"),
    ("plan_progress_store", "INSERT INTO cp_plan_progress_meta(singleton) VALUES (TRUE) ON CONFLICT DO NOTHING"),
    ("pm_control", "UPDATE cp_pm_control_events SET updated_at=created_at WHERE updated_at IS NULL"),
}
COUNTS = {"tables": 25, "indexes": 24, "alters": 22, "quarantined_dml": 3}


class C2Stop(ValueError):
    """Never output incomplete/changed DDL."""


def static_assignment(file_path: Path, symbol: str):
    """Read an AST literal, not import/execute an application module."""
    nodes = ast.parse(file_path.read_text(encoding="utf-8")).body
    values = [
        node.value
        for node in nodes
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == symbol
    ]
    if len(values) != 1:
        raise C2Stop("missing_or_duplicate_source_constant:" + symbol)
    try:
        return ast.literal_eval(values[0])
    except (TypeError, ValueError, SyntaxError, MemoryError) as exc:
        raise C2Stop("nonliteral_source_constant:" + symbol) from exc


def pinned_inputs(root: Path = ROOT):
    """Compare module strings to the existing reviewed 12-module SHA manifest."""
    pin = static_assignment(
        root / "services/runtime/app/fullpath_schema_bootstrap_source.py",
        "SOURCE_DDL_SHA256",
    )
    names = static_assignment(
        root / "services/runtime/app/fullpath_fresh_startup.py",
        "POST_SCHEMA_TABLE_SOURCES",
    )
    if not isinstance(pin, dict) or list(pin) != list(SOURCE_FIELDS):
        raise C2Stop("source_module_set_or_order_mismatch")
    if not isinstance(names, dict) or set(names) != set(SOURCE_FIELDS):
        raise C2Stop("source_table_manifest_missing")
    table_allowlist = set()
    for key, group in names.items():
        if not isinstance(group, (tuple, list)) or not group:
            raise C2Stop("invalid_table_manifest")
        for t in group:
            if not isinstance(t, str) or not re.fullmatch(r"cp_[a-z0-9_]+", t):
                raise C2Stop("invalid_table_identifier")
            if t in table_allowlist:
                raise C2Stop("duplicate_table_identifier")
            table_allowlist.add(t)
    if len(table_allowlist) != COUNTS["tables"]:
        raise C2Stop("table_manifest_count_changed")
    sources = {}
    for module, field in SOURCE_FIELDS.items():
        sql = static_assignment(root / f"services/runtime/app/{module}.py", field)
        if not isinstance(sql, str) or sha256(sql.encode()).hexdigest() != pin[module]:
            raise C2Stop("pinned_sql_digest_mismatch:" + module)
        sources[module] = sql
    return sources, pin, table_allowlist


def reviewed_statements(
    sources: Mapping[str, str], pin: Mapping[str, str], tables: set[str]
) -> tuple[list[str], dict[str, int]]:
    if set(sources) != set(SOURCE_FIELDS) or list(pin) != list(SOURCE_FIELDS):
        raise C2Stop("module_order_or_set_changed")
    statements = []
    observed_tables, observed_indexes, omitted = set(), set(), set()
    count = {"tables": 0, "indexes": 0, "alters": 0, "quarantined_dml": 0}
    for module in SOURCE_FIELDS:
        raw = sources[module]
        if not isinstance(raw, str) or sha256(raw.encode()).hexdigest() != pin[module]:
            raise C2Stop("pinned_sql_digest_mismatch:" + module)
        for item in raw.split(";"):
            stmt = " ".join(item.split())
            if not stmt:
                continue
            if "--" in stmt or "/*" in stmt or "*/" in stmt:
                raise C2Stop("source_sql_comments_not_reviewed")
            if (module, stmt) in OMIT_HISTORICAL_DML:
                if (module, stmt) in omitted:
                    raise C2Stop("duplicate_historical_dml")
                omitted.add((module, stmt))
                count["quarantined_dml"] += 1
                continue
            table = re.match(r"^CREATE TABLE IF NOT EXISTS (cp_[a-z0-9_]+) \(", stmt)
            index = re.match(
                r"^CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (cp_[a-z0-9_]+) "
                r"ON (cp_[a-z0-9_]+)\(", stmt,
            )
            alter = re.match(
                r"^ALTER TABLE (cp_[a-z0-9_]+) "
                r"(?:ADD COLUMN IF NOT EXISTS [a-z_][a-z0-9_]* .+|"
                r"ALTER COLUMN [a-z_][a-z0-9_]* SET NOT NULL)$", stmt,
            )
            if table:
                name = table[1]
                refs = re.findall(r"\bREFERENCES (cp_[a-z0-9_]+)\s*\(", stmt)
                if (name not in tables or name in observed_tables
                        or any(ref not in observed_tables for ref in refs)):
                    raise C2Stop("foreign_duplicate_or_out_of_order_table")
                observed_tables.add(name)
                count["tables"] += 1
            elif index:
                name, owner = index.groups()
                if name in observed_indexes or owner not in observed_tables:
                    raise C2Stop("duplicate_index_or_owner_missing")
                observed_indexes.add(name)
                count["indexes"] += 1
            elif alter:
                if alter[1] not in observed_tables:
                    raise C2Stop("alter_before_table")
                count["alters"] += 1
            else:
                raise C2Stop("unapproved_sql_statement:" + module)
            statements.append(stmt + ";")
    if (observed_tables != tables or omitted != OMIT_HISTORICAL_DML
            or count != COUNTS or len(statements) != 71):
        raise C2Stop("full_schema_or_quarantine_mismatch")
    return statements, count


PREFIX = """-- C2 ONLY: transaction on one independently attested fresh F2 database.
-- Not a Runtime startup, historical migration or authorization token.
-- Execute with psql -X -v ON_ERROR_STOP=1 inside exact F2 DB container ONLY.
BEGIN;
SET LOCAL statement_timeout = '120s';
SET LOCAL lock_timeout = '5s';
DO $f2_guard$
BEGIN
  IF current_database() <> 'fullpath'
     OR current_user <> 'fullpath_bootstrap_admin'
     OR (SELECT NOT rolsuper FROM pg_roles WHERE rolname=current_user)
  THEN
    RAISE EXCEPTION 'F2 schema install: wrong database/bootstrap identity';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname='fullpath' AND rolcanlogin AND NOT rolsuper
      AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication
      AND NOT rolbypassrls AND NOT rolinherit
  ) THEN
    RAISE EXCEPTION 'F2 schema install: app role not least privilege';
  END IF;
  IF (
    SELECT count(*) FROM pg_namespace
    WHERE nspname !~ '^pg_' AND nspname <> 'information_schema'
  ) <> 1 OR NOT EXISTS (
    SELECT 1 FROM pg_namespace WHERE nspname='public'
  ) OR EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
  ) OR EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
  ) OR EXISTS (
    SELECT 1 FROM pg_stat_activity
    WHERE datname=current_database() AND pid<>pg_backend_pid()
  ) THEN
    RAISE EXCEPTION 'F2 schema install: database not fresh/exclusive';
  END IF;
END
$f2_guard$;
"""
SUFFIX = """-- Grant only application DML, never schema DDL/ownership or TRUNCATE.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO fullpath;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO fullpath;
DO $f2_verify$
BEGIN
  IF (SELECT count(*) FROM pg_class c
      JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relkind='r') <> 25
  THEN
    RAISE EXCEPTION 'F2 schema install: unexpected table count';
  END IF;
  IF has_schema_privilege('fullpath','public','CREATE')
     OR has_database_privilege('fullpath','fullpath','CREATE')
     OR has_database_privilege('fullpath','fullpath','TEMPORARY')
  THEN
    RAISE EXCEPTION 'F2 schema install: app permission boundary changed';
  END IF;
END
$f2_verify$;
COMMIT;
"""


def bundle(root: Path = ROOT) -> tuple[str, dict[str, int]]:
    sources, pin, tables = pinned_inputs(root)
    statements, counts = reviewed_statements(sources, pin, tables)
    sql = PREFIX + "\n".join(statements) + "\n" + SUFFIX
    return sql, counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Print digest/counts, no SQL")
    mode.add_argument("--emit-sql", action="store_true", help="Emit reviewed SQL only")
    args = parser.parse_args()
    try:
        sql, counts = bundle()
    except (C2Stop, OSError, SyntaxError) as exc:
        parser.exit(2, "F2_C2_SCHEMA_STOP: " + str(exc) + "\n")
    if args.check:
        print(json.dumps({
            "status": "SOURCE_READY_NOT_APPLIED",
            "sha256": sha256(sql.encode()).hexdigest(),
            "statements": 71,
            "counts": counts,
            "database_writes": 0,
            "activation_authorized": False,
        }, sort_keys=True))
    else:
        print(sql, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
