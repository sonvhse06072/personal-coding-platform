"""PCP-only schema installation and read-only prerequisite collection.

Never calls legacy init/recovery, creates a job, or invokes a model.
"""
from __future__ import annotations

import asyncio
import httpx
from pathlib import Path

from .pcp_local_task_queue import RECEIPT_DDL, TaskStop
from .storage import DDL
from .telemetry_storage import TELEMETRY_DDL
from .quota_telemetry import DDL as QUOTA_DDL

TABLES = ('cp_jobs', 'cp_project_leases', 'cp_job_events',
          'cp_pcp_local_source_receipts', 'cp_task_telemetry',
          'cp_attention_events', 'cp_continuity_proposals',
          'cp_quota_snapshots', 'cp_quota_collectors')


def schema_readiness(storage):
    with storage.connect() as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        rows = conn.execute("""SELECT name, to_regclass(name) IS NOT NULL AS present,
            CASE WHEN to_regclass(name) IS NULL THEN false ELSE
            has_table_privilege(current_user, name, 'SELECT')
            AND has_table_privilege(current_user, name, 'INSERT')
            AND has_table_privilege(current_user, name, 'UPDATE')
            AND has_table_privilege(current_user, name, 'DELETE') END AS permitted
            FROM unnest(%s::text[]) AS name""", (list(TABLES),)).fetchall()
        sequences = conn.execute("""SELECT c.relname AS name,
            has_sequence_privilege(current_user,c.oid,'USAGE')
            AND has_sequence_privilege(current_user,c.oid,'SELECT') AS permitted
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=current_schema() AND c.relkind='S'
            AND c.relname = ANY(%s)""", (['cp_job_events_id_seq', 'cp_attention_events_id_seq',
                                         'cp_continuity_proposals_id_seq'],)).fetchall()
    return [dict(component='schema', code='missing_table' if not r['present'] else 'role_permissions',
                 object=r['name'], actor='operator', next_action='Run supported schema-only initialization as the scoped schema owner')
            for r in rows if not r['present'] or not r['permitted']] + [
        dict(component='schema', code='sequence_permissions', object=r['name'], actor='operator',
             next_action='Grant the scoped Runtime role sequence usage') for r in sequences if not r['permitted']]


def initialize_schema(storage):
    """Explicit operator operation. Additive/idempotent, one transaction, no DML."""
    with storage.connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('pcp-local-schema'))")
        for ddl in (DDL, RECEIPT_DDL, TELEMETRY_DDL, QUOTA_DDL):
            conn.execute(ddl)
        conn.commit()
    blockers = schema_readiness(storage)
    if blockers:
        raise TaskStop('pcp_local_schema_permissions_incomplete')


async def collect_readiness(engine, readers=None):
    """Collect independent failures together; no receipt registration/claim."""
    from .pcp_local_worker_loop import operational_flag
    from .shell import run_command
    blockers = []

    async def check(component, operation, action):
        try:
            value = operation()
            if hasattr(value, '__await__'):
                await value
        except Exception as exc:
            # Exception strings can contain URLs/headers/paths. Only stable codes.
            affected = component
            code = getattr(exc, 'code', None) or 'unavailable'
            if isinstance(exc, httpx.HTTPError) and getattr(exc, 'request', None) is not None:
                host = exc.request.url.host
                affected = {'router':'router', 'ddev-executor':'executor',
                            'api.github.com':'github', 'github.com':'github'}.get(host, component)
                code = 'dns_tls_or_transport_failure' if isinstance(exc, httpx.TransportError) else 'http_failure'
            blockers.append(dict(component=affected, code=code,
                                 actor='operator', next_action=action))

    async def identity():
        result = await run_command(['git', '-c', 'user.name=PCP Local', '-c',
            'user.email=pcp-local@localhost', 'var', 'GIT_AUTHOR_IDENT'], cwd='/tmp', timeout=10)
        if result.returncode or 'PCP Local <pcp-local@localhost>' not in result.stdout:
            raise TaskStop('pcp_local_git_identity_unavailable')
        result = await run_command(['git', '-c', 'user.name=PCP Local', '-c',
            'user.email=pcp-local@localhost', 'var', 'GIT_COMMITTER_IDENT'], cwd='/tmp', timeout=10)
        if result.returncode or 'PCP Local <pcp-local@localhost>' not in result.stdout:
            raise TaskStop('pcp_local_git_identity_unavailable')

    async def verifier():
        import importlib.metadata
        import shutil
        if (importlib.metadata.version('pytest') != '8.4.1'
                or importlib.metadata.version('PyYAML') != '6.0.2'
                or not Path('/usr/bin/timeout').is_file() or not shutil.which('git')):
            raise TaskStop('pcp_local_verifier_toolchain_unavailable')

    def schema():
        blockers.extend(schema_readiness(engine.storage))

    async def trusted():
        nonlocal readers
        if readers is None:
            from .pcp_local_worker_loop import TrustedReaders
            from .pm_bridge import PMBridgeGitHubClient
            readers = TrustedReaders(engine, PMBridgeGitHubClient())
        task, _ = await readers.source()
        await readers.refresh(task)
        # Apply the same pure shape/budget checks used by admission before a
        # receipt is created. No fabricated receipt is written or used to launch.
        from .pcp_local_worker_admission import check_worker_admission
        candidate = {**vars(task), 'allowed_paths':list(task.allowed_paths),
                     'state':'pending', 'generation':0, 'job_id':None}
        check_worker_admission(task, receipt=candidate,
            **{k:readers.snapshot[k] for k in ('project','baseline','isolation','provider','budget')})

    async def provider():
        from .quota_telemetry import CodexQuotaCollector
        await CodexQuotaCollector().collect()  # Account metadata only, no inference.


    await asyncio.gather(
        check('activation', operational_flag, 'Enable all approved source/worker/intake switches'),
        check('identity', identity, 'Configure repository-local PCP Local automation identity'),
        check('schema', schema, 'Initialize supported schema with the scoped owner and verify role rights'),
        check('provider', provider, 'Complete scoped Codex login; check provider DNS/TLS and account entitlement'),
        check('verifier', verifier, 'Adopt the reviewed Runtime/verifier image with required tools'),
        check('trusted_sources', trusted, 'Check activation, source, Router, Executor, publisher and provider authentication/connectivity'),
    )
    return dict(ready=not blockers, blockers=blockers, model_invocations=0, job_registrations=0)
