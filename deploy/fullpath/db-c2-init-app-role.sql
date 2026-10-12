-- C2 DB bootstrap only. The official postgres:16 entrypoint runs this
-- on a BRAND-NEW PGDATA volume. No PCP application tables or legacy recovery.
-- Secrets are owner-local Compose files, not environment values or Git data.
\set ON_ERROR_STOP on
\set app_password `cat /run/secrets/f2_db_app_password`

BEGIN;
CREATE ROLE fullpath WITH LOGIN NOINHERIT NOSUPERUSER NOCREATEDB
  NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'app_password';
REVOKE ALL PRIVILEGES ON DATABASE fullpath FROM PUBLIC;
REVOKE ALL PRIVILEGES ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE fullpath TO fullpath;
GRANT USAGE ON SCHEMA public TO fullpath;
COMMIT;

\unset app_password
