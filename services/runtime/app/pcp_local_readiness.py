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
        sequences = conn.execute("""SELECT name,
            CASE WHEN to_regclass(name) IS NULL THEN false ELSE
            has_sequence_privilege(current_user,to_regclass(name),'USAGE')
            AND has_sequence_privilege(current_user,to_regclass(name),'SELECT') END AS permitted
            FROM unnest(%s::text[]) AS name""", (['cp_job_events_id_seq', 'cp_attention_events_id_seq',
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


async def collect_readiness(engine, readers=None, *, phase="admission", job_id=None, review_id=None):
    """Collect independent failures together; no receipt registration/claim."""
    if phase != "admission":
        return await operation_readiness(engine, phase=phase, job_id=job_id, review_id=review_id, readers=readers)
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
        check_worker_admission(task, receipt=candidate, recovery=getattr(readers, "recovery", None),
            **{k:readers.snapshot[k] for k in ('project','baseline','isolation','provider','budget')})

    async def provider():
        from .quota_telemetry import CodexQuotaCollector
        from .adapters.codex import require_isolated_provider_configuration
        # The account collector starts app-server, which also consumes user
        # configuration. The parallel trusted-source check cannot fence it.
        try:
            require_isolated_provider_configuration()
        except (ValueError, OSError) as exc:
            raise TaskStop('pcp_local_unreviewed_codex_configuration') from exc
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


def operation_snapshot(storage, job_id):
    """One read-only snapshot; only this project's requested job, no raw secrets."""
    import re
    from .pcp_local_task_queue import require, PROJECT_ID
    require(isinstance(job_id, str) and re.fullmatch('[0-9a-f]{32}', job_id), 'pcp_local_job_id_required')
    with storage.connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        row = conn.execute('SELECT * FROM cp_jobs WHERE id=%s AND project_id=%s', (job_id, PROJECT_ID)).fetchone()
        require(row is not None, 'pcp_local_job_missing')
        receipt = conn.execute('SELECT * FROM cp_pcp_local_source_receipts WHERE job_id=%s AND project_id=%s', (job_id, PROJECT_ID)).fetchone()
        lease = conn.execute('SELECT * FROM cp_project_leases WHERE owner_job_id=%s AND project_id=%s', (job_id, PROJECT_ID)).fetchone()
    return row, receipt, lease


def review_payload(row, review_id):
    from .pcp_local_task_queue import require
    from .fullpath_pm_review import FullpathPMReviewRequest
    require(type(review_id) is int and review_id > 0, 'pcp_local_review_id_required')
    result = row.get('result') or {}
    return FullpathPMReviewRequest(source_commit=row['source_commit'], expected_head=result.get('commit'),
        branch=row['branch'], baseline_revision=row['checkpoint']['project_baseline']['revision'],
        pr_number=result.get('delivery', {}).get('pull_request', {}).get('number'), review_id=review_id).model_dump()


def finalization_ownership(row, receipt, lease):
    """Check retained receipt identity and the operation's exact lease generation."""
    from .pcp_local_task_queue import require
    cp = row['checkpoint']
    expected = cp['pcp_local_source']['receipt']
    require(receipt is not None and receipt.get('job_id') == row['id']
        and all(receipt.get(k) == v for k, v in expected.items() if k not in ('state', 'generation')),
        'pcp_local_receipt_identity_changed')
    done = row['status'] == 'completed' and (row.get('result') or {}).get('delivery_finalized') is True
    require((receipt['state'], receipt['generation']) == (('delivered', 3) if done else ('running', 2)),
            'pcp_local_receipt_state_changed')
    # A completed job remains completed after a later job legitimately reuses the lease.
    if not done or lease is not None:
        require(lease is not None and lease['owner_job_id'] == row['id']
            and lease['generation'] == cp['pcp_local_execution']['lease_generation']
            and lease['state'] == ('released' if done else 'active'), 'pcp_local_lease_changed')


def delivery_operation(row):
    """Durable disposition only, never remote publication/CI attestation."""
    result = row.get('result') or {}
    delivery = result.get('delivery') or {}
    if row['status'] == 'completed' and result.get('delivery_finalized') is True:
        state, actor, action = 'completed', 'none', 'No delivery is needed; retain completed evidence'
    elif delivery.get('state') == 'ci_success':
        state, actor, action = 'awaiting_pm_review', 'PM', 'Review the exact delivered head/CI, then use finalization readiness; do not publish again'
    elif delivery.get('state') == 'ci_waiting':
        state, actor, action = 'ci_pending', 'operator', 'Observe exact-head remote CI and reconcile before any delivery retry'
    elif delivery or (row.get('progress') or {}).get('delivery_attempts', 0):
        state, actor, action = 'reconcile_publication', 'operator', 'Reconcile the remote branch, all-state PR and CI read-only before any retry'
    else:
        state, actor, action = 'delivery_needed', 'operator', 'Resolve dependency blockers and use the existing delivery endpoint only under installed authority'
    return dict(state=state, eligible=state == 'delivery_needed', actor=actor, next_action=action)


async def operation_readiness(engine, *, phase, job_id, review_id=None, readers=None):
    """Phase prerequisites are observations, never an execution authorization."""
    from types import SimpleNamespace
    from .pcp_local_task_queue import require
    from .pcp_local_worker_loop import TrustedReaders, stable_job_id
    from .pcp_local_recovery import reconcile_commit, inspect_verified_tree
    checks = []
    view = dict(phase=phase, ready=False, authorized=False, checks=checks, blockers=[],
                model_invocations=0, job_registrations=0)

    async def check(name, fn, actor='operator', action='Reconcile this dependency before mutation'):
        try:
            value = fn()
            if hasattr(value, '__await__'):
                value = await value
            checks.append(dict(component=name, state='pass', actor=actor, next_action='none'))
            return value
        except Exception as exc:
            code = getattr(exc, 'code', None)
            checks.append(dict(component=name, state='blocked' if code else 'unknown',
                code=code or 'unobserved', actor=actor, next_action=action))

    def finish():
        view['blockers'] = [c for c in checks if c['state'] in ('blocked', 'unknown')]
        view['dependencies_ready'] = not view['blockers']
        view['ready'] = view['dependencies_ready'] and view.get('operation', {}).get('eligible', True)
        return view

    if phase == 'held-verification':
        from .pcp_local_recovery import operate, HeldPermit
        async def held_plan():
            permit=HeldPermit()
            require(job_id==permit.value['before']['job']['id'],'held_readiness_identity')
            return await operate(engine)
        observed=await check('held_verification',held_plan)
        if observed:
            view['operation']=dict(state=observed['state'],eligible=observed['ready'],actor='operator',
                next_action='Use separately authorized verify-held --apply only if eligible; otherwise reconcile')
            view['identity']={k:observed[k] for k in ('job_id','permit_sha256') if k in observed}
        return finish()

    if phase not in ('status', 'delivery', 'finalization'):
        checks.append(dict(component='phase', state='blocked', code='unsupported_phase',
                           actor='operator', next_action='Choose admission, status, delivery or finalization'))
        return finish()
    data = await check('durable_state', lambda: operation_snapshot(engine.storage, job_id))
    for name in ('provider', 'router', 'fresh_admission'):
        checks.append(dict(component=name, state='not_applicable', actor='none', next_action='none'))
    if data is None:
        return finish()
    row, receipt, lease = data
    result = row.get('result') or {}
    cp = row.get('checkpoint') or {}
    execution = cp.get('pcp_local_execution') or {}
    if phase == 'delivery':
        view['operation'] = delivery_operation(row)
    view['job'] = dict(id=row['id'], status=row['status'], execution=execution.get('state'),
        finalized=result.get('delivery_finalized') is True,
        review_id=result.get('review', {}).get('review_id'),
        receipt=None if receipt is None else {k:receipt[k] for k in ('state','generation')},
        lease=None if lease is None else {k:lease[k] for k in ('state','generation')},
        counters={k:row.get('progress', {}).get(k) for k in ('model_calls','test_runs','delivery_attempts')})
    if phase == 'status':
        return finish()
    payload = await check('identity', lambda: review_payload(row, review_id)) if phase == 'finalization' else None
    if payload:
        view['identity'] = payload
    await check('ownership', lambda: finalization_ownership(row, receipt, lease))
    if row['status'] == 'completed' and result.get('delivery_finalized') is True:
        await check('accepted_review', lambda: require(phase != 'finalization' or
            result.get('review', {}).get('review_id') == review_id, 'pcp_local_review_conflicting_retry'), actor='PM')
        view['existing_success'] = not any(c['state'] in ('blocked','unknown') for c in checks)
        return finish()
    def proof():
        path = Path(row['workspace'])
        require(path == engine.workspace_root / job_id and not path.is_symlink()
            and path.resolve() == path, 'pcp_local_workspace_identity_invalid')
        require(execution.get('state') in ('verified','verified_uncommitted','commit_uncertain')
            and 'pcp_local_retirement' not in cp, 'pcp_local_unverified_job')
        task = SimpleNamespace(base_sha=row['source_commit'])
        if execution['state'] == 'verified_uncommitted':
            require(phase == 'delivery' and inspect_verified_tree(row, task) == execution['verified_tree'], 'pcp_local_verified_tree_changed')
        else:
            commit = reconcile_commit(row, task)
            require(commit == execution.get('commit', commit), 'pcp_local_commit_changed')
    await check('verified_proof', proof)
    if phase == 'finalization':
        if payload:
            await check('authority_review_ci', lambda: engine.finalize_pcp_local_review(SimpleNamespace(**payload), dry_run=True),
                        actor='PM', action='Check installed authority and exact independent review/CI; never renew implicitly')
        else:
            checks.append(dict(component='authority_review_ci', state='unknown', code='identity_unavailable', actor='PM', next_action='Restore exact durable identity evidence'))
    else:
        async def delivery():
            nonlocal readers
            if readers is None:
                from .pm_bridge import PMBridgeGitHubClient
                readers = TrustedReaders(engine, PMBridgeGitHubClient())
            task, _ = await readers.source()
            require(stable_job_id(task) == job_id, 'pcp_local_wrong_task')
            readers.lease_generation = execution['lease_generation']
            readers.route = row.get('route')
            await readers.refresh_delivery(task)
        await check('authority_publisher', delivery)
    return finish()
