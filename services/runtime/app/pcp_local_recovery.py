"""Same verified job only. No model invocation or generic state-edit interface."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from datetime import datetime, timezone
import os
import shutil
import tempfile
from pathlib import Path
import subprocess

from .pcp_local_task_queue import require, PROJECT_ID, REPOSITORY


def git(workspace, *args):
    return subprocess.check_output(['git', '-C', str(workspace), *args], text=True).strip()


def candidate_tree(workspace):
    """Build Git's complete candidate identity without changing the real index.

    Mirror commit_changes staging, including sparse tracked paths and modes.
    The private index is scratch; the resulting immutable tree is only evidence.
    """
    from .repo import _is_runtime_ignored_untracked
    with tempfile.TemporaryDirectory(prefix='pcp-proof-') as scratch:
        index = Path(scratch) / 'index'
        source = Path(git(workspace, 'rev-parse', '--absolute-git-dir')) / 'index'
        shutil.copyfile(source, index)
        env = {**os.environ, 'GIT_INDEX_FILE': str(index)}
        def run(*args):
            return subprocess.check_output(['git', '-C', str(workspace), '-c',
                'core.filemode=true', *args], env=env)
        run('add', '-u', '--', '.', ':(exclude).ddev/config.coding-platform.yaml')
        untracked = [os.fsdecode(p) for p in run('ls-files', '--others', '--exclude-standard', '-z').split(b'\0')
                     if p and not _is_runtime_ignored_untracked(os.fsdecode(p))]
        if untracked:
            run('add', '--', *untracked)
        return run('write-tree').decode().strip()


def verified_tree(workspace, task, diff):
    """Use the verifier's complete file-manifest contract, not only changed paths."""
    excluded = {'.git', '.ddev', '.venv', '__pycache__', '.pytest_cache'}
    entries = {}
    for path in sorted(Path(workspace).rglob('*')):
        rel = path.relative_to(workspace)
        if rel.parts[0] in excluded:
            continue
        require(not path.is_symlink(), 'pcp_local_verified_symlink')
        if path.is_file():
            entries[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    from .repo import diff_state
    actual = diff_state(Path(workspace), 750000, base_ref=task.base_sha)
    require(actual['diff_hash'] == diff['diff_hash'], 'pcp_local_verified_diff_changed')
    return dict(tree=candidate_tree(workspace), source=task.base_sha, branch=git(workspace, 'branch', '--show-current'),
                parent=git(workspace, 'rev-parse', 'HEAD'), files=entries, diff_hash=actual['diff_hash'])


def commit_verified(engine, job_id, task, workspace, checkpoint):
    from .repo import commit_changes
    proof = checkpoint['pcp_local_execution']
    require(verified_tree(workspace, task, proof['diff']) == proof['verified_tree'],
            'pcp_local_verified_tree_changed')
    # Intent is durable before Git can have an uncertain side effect.
    proof['state'] = 'commit_uncertain'
    engine.storage.update(job_id, checkpoint=checkpoint)
    commit_changes(Path(workspace), f'PCP-local issue #{task.issue_number}')
    return reconcile_commit(dict(workspace=str(workspace), checkpoint=checkpoint), task)


def reconcile_commit(row, task):
    """Read-only reconciliation; an absent/unknown commit is never retried."""
    from .repo import diff_state
    proof = row['checkpoint']['pcp_local_execution']
    workspace = Path(row['workspace'])
    expected = proof['verified_tree']
    current = verified_tree(workspace, task, proof['diff'])
    require(current['files'] == expected['files'] and current['source'] == expected['source']
            and current['branch'] == expected['branch'] and current['tree'] == expected.get('tree'), 'pcp_local_recovery_tree_changed')
    commit = git(workspace, 'rev-parse', 'HEAD')
    require(commit != expected['parent'] and git(workspace, 'show', '-s', '--format=%P', 'HEAD').split() == [expected['parent']]
            and git(workspace, 'rev-parse', 'HEAD^{tree}') == expected.get('tree')
            and not git(workspace, 'status', '--porcelain'), 'pcp_local_commit_outcome_unknown')
    # Clean working tree + exact cumulative diff binds the commit to verification.
    diff = diff_state(workspace, 750000, base_ref=task.base_sha)
    require(diff['diff_hash'] == expected['diff_hash'], 'pcp_local_recovery_diff_changed')
    return commit


async def recover_verified_job(engine, readers, task, row):
    """Called under the existing project operation lock; requires fresh readers.

    This only consumes evidence written by the new successful-verification seam.
    Legacy held/null results need the separately approved forensic procedure.
    """
    from .pcp_local_worker_loop import stable_job_id
    job_id = stable_job_id(task)
    require('pcp_local_retirement' not in (row.get('checkpoint') or {}), 'pcp_local_retired_job')
    cp = deepcopy(row['checkpoint'])
    proof = cp.get('pcp_local_execution') or {}
    require(row['id'] == job_id and row['project_id'] == PROJECT_ID
            and row['source_commit'] == task.base_sha
            and proof.get('state') in {'verified_uncommitted', 'commit_uncertain'}
            and proof.get('authority_digest') == readers.authority_digest
            and proof.get('verification', {}).get('passed') is True
            and proof['verification'].get('test_runs', 0) > 0
            and proof.get('route') == row['route']
            and proof.get('verified_tree', {}).get('source') == task.base_sha
            and row['branch'] == 'ai/' + job_id[:12], 'pcp_local_recovery_evidence_invalid')
    readers.route = row['route']
    readers.lease_generation = proof['lease_generation']
    await readers.refresh(task)
    if proof['state'] == 'verified_uncommitted':
        require(verified_tree(row['workspace'], task, proof['diff']) == proof['verified_tree'],
                'pcp_local_recovery_tree_changed')
        cp['pcp_local_execution']['state'] = 'commit_uncertain'
        engine.storage.cas_local_checkpoint(row, cp, status='blocked', result=row.get('result'))
        from .repo import commit_changes
        commit_changes(Path(row['workspace']), f'PCP-local issue #{task.issue_number}')
        row = engine.storage.get(job_id)
    commit = reconcile_commit(row, task)
    cp = deepcopy(row['checkpoint'])
    cp['pcp_local_execution'].update(state='verified', commit=commit)
    cp['pcp_local_recovery'] = dict(kind='same_job_non_model', commit=commit)
    result = dict(status='accepted', branch=row['branch'], commit=commit, diff=proof['diff'],
                  verification=proof['verification'], route=row['route'], delivery_finalized=False)
    engine.storage.cas_local_checkpoint(row, cp, status='delivering', result=result)
    return engine.storage.get(job_id)


# Operator-only non-delivery retirement. Shared with storage/queue for the exact
# serialization and audit predicate; no worker or HTTP surface can supply APPLY.
LOCK = (5260112, 808)  # Same project serialization as source-job registration.
KEY = 'pcp_local_retirement'
DISPOSITION = 'incomplete_not_delivered'
ATTESTATION = 'I verified the independent PM execution record and exact scope.'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False,
                      default=lambda v: v.astimezone(timezone.utc).isoformat() if isinstance(v, datetime) and v.tzinfo else _unsupported(v))


def _unsupported(value):
    raise TypeError('unsupported retirement evidence type')


def frozen(value):
    return json.loads(canonical(value))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def project_lock(conn):
    conn.execute('SET LOCAL lock_timeout = \'5s\'')
    conn.execute('SELECT pg_advisory_xact_lock(%s,%s)', LOCK)


def database_identity(conn):
    return dict(conn.execute("SELECT current_database() AS name, "
        "(SELECT oid::text FROM pg_database WHERE datname=current_database()) AS oid, "
        "current_schema() AS schema, (SELECT oid::text FROM pg_namespace WHERE "
        "nspname=current_schema()) AS schema_oid, "
        "(SELECT system_identifier::text FROM pg_control_system()) AS system_identifier").fetchone())


def read_rows(conn, job_id, *, lock=False):
    suffix = ' FOR UPDATE' if lock else ''
    job = conn.execute('SELECT * FROM cp_jobs WHERE id=%s' + suffix, (job_id,)).fetchone()
    require(job is not None and job['project_id'] == PROJECT_ID, 'retirement_job_missing_or_foreign')
    receipt = conn.execute('SELECT * FROM cp_pcp_local_source_receipts WHERE repository=%s '
        'AND project_id=%s AND job_id=%s' + suffix, (REPOSITORY, PROJECT_ID, job_id)).fetchall()
    require(len(receipt) == 1, 'retirement_receipt_not_unique')
    lease = conn.execute('SELECT * FROM cp_project_leases WHERE project_id=%s' + suffix,
                         (PROJECT_ID,)).fetchone()
    return frozen(dict(job=job, receipt=receipt[0], lease=lease))


def validate_manifest(m):
    require(type(m) is dict and set(m) == {'version','repository','project_id','instance',
        'database','database_container','workers','decision_id','reason','before'}, 'retirement_manifest_fields')
    require(m['version'] == 1 and type(m['version']) is int and m['repository'] == REPOSITORY
        and m['project_id'] == PROJECT_ID, 'retirement_scope_invalid')
    require(isinstance(m['instance'], str) and re.fullmatch(r'pcp-local-[a-z0-9-]+',m['instance'])
        and isinstance(m['decision_id'],str) and re.fullmatch(r'[A-Za-z0-9_-]{8,100}',m['decision_id'])
        and isinstance(m['reason'],str) and 10 <= len(m['reason']) <= 2000,
        'retirement_decision_missing')
    require(type(m['database']) is dict and set(m['database']) ==
        {'name','oid','schema','schema_oid','system_identifier'} and
        all(isinstance(v,str) and v for v in m['database'].values()), 'retirement_database_missing')
    require(isinstance(m['database_container'],str) and re.fullmatch('[a-f0-9]{64}',m['database_container']),
            'retirement_database_container_missing')
    require(type(m['workers']) is list and len(m['workers']) >= 3 and
        len(set(m['workers'])) == len(m['workers']) and all(isinstance(v,str) and
        re.fullmatch(r'[0-9a-f]{64}',v) for v in m['workers']), 'retirement_workers_missing')
    b=m['before']
    require(type(b) is dict and set(b)=={'job','receipt','lease'} and
        all(type(v) is dict for v in b.values()), 'retirement_preimages_missing')
    j,r,l=b['job'],b['receipt'],b['lease']
    cp=j.get('checkpoint') or {}; binding=(cp.get('pcp_local_source') or {}).get('receipt') or {}
    require(KEY not in cp and j.get('project_id')==PROJECT_ID and
        re.fullmatch(r'[a-f0-9]{32}',str(j.get('id',''))) and
        j.get('status') not in {'completed','failed','cancelled'} and
        r.get('repository')==REPOSITORY and r.get('project_id')==PROJECT_ID and
        r.get('job_id')==j['id'] and r.get('state') in {'running','claimed','blocked'} and
        type(r.get('generation')) is int and r['generation'] > 0 and
        l.get('project_id')==PROJECT_ID and l.get('owner_job_id')==j['id'] and
        l.get('state')=='active' and type(l.get('generation')) is int and l['generation'] > 0,
        'retirement_ownership_invalid')
    require(j.get('source_commit') == r.get('base_sha') and all(k in binding and
        canonical(binding[k]) == canonical(r.get(k)) for k in ('issue_number','body_sha256',
        'base_sha','baseline_revision','baseline_source_commit','goal_sha256','allowed_paths')),
        'retirement_source_binding_invalid')
    require((cp.get('pcp_local_execution') or {}).get('lease_generation') == l['generation'],
        'retirement_lease_generation_invalid')
    # Commit, proof, error, route, usage, all extra columns and timestamps are
    # protected by the FULL-row comparison, not a whitelist of familiar fields.
    for k in ('base_sha','baseline_source_commit'):
        require(isinstance(r.get(k),str) and re.fullmatch('[a-f0-9]{40}',r[k]), 'retirement_source_invalid')
    for k in ('body_sha256','goal_sha256'):
        require(isinstance(r.get(k),str) and re.fullmatch('[a-f0-9]{64}',r[k]), 'retirement_body_invalid')


def validate_approval(m, a):
    require(type(a) is dict and set(a)=={'decision_id','action','manifest_sha256','authority',
        'approver','execution_record','accepted_source','operator','attestation'}, 'retirement_approval_required')
    require(a['decision_id']==m['decision_id'] and a['action']==DISPOSITION and
        a['manifest_sha256']==digest(m) and a['authority']=='owner_delegated_independent_pm' and
        a['attestation']==ATTESTATION and all(isinstance(a[k],str) and 3<=len(a[k])<=1000
        for k in ('approver','execution_record','operator')) and
        isinstance(a['accepted_source'],str) and re.fullmatch('[a-f0-9]{40}',a['accepted_source']),
        'retirement_approval_binding_invalid')


def outcome(m, at):
    b=m['before']
    return dict(decision_id=m['decision_id'], job_id=b['job']['id'], disposition=DISPOSITION,
        status='cancelled', retired_at=at, manifest_sha256=digest(m),
        receipt_generation=b['receipt']['generation']+1, lease_generation=b['lease']['generation'])


def postimages(m, approval, at):
    b=deepcopy(m['before']);j,r,l=b['job'],b['receipt'],b['lease']
    j.update(status='cancelled',updated_at=at)
    r.update(state='blocked',generation=r['generation']+1,updated_at=at)
    # Release is NOT a new ownership generation (same as normal finalization).
    l.update(state='released',updated_at=at)
    j['checkpoint'][KEY]=dict(version=1, manifest=m, approval=approval, outcome=outcome(m,at))
    return b


def validated_retirement(job, receipt):
    """Admission exception for one intact audited receipt, never all blocked rows.

    A later lease owner is legal. The audit retains the exact released pre/post
    generation; idempotent APPLY additionally checks the current lease in full.
    """
    try:
        audit=job['checkpoint'][KEY];m=audit['manifest'];a=audit['approval']
        validate_manifest(m);validate_approval(m,a)
        at=audit['outcome']['retired_at']
        require(datetime.fromisoformat(at).tzinfo is not None, 'retirement_timestamp_invalid')
        expected=postimages(m,a,at)
        return (canonical(job)==canonical(expected['job']) and
                canonical(receipt)==canonical(expected['receipt']))
    except (KeyError,TypeError,ValueError):
        return False


def blocking_receipts(conn, receipts, *, lock=True):
    blockers=[]
    for r in receipts:
        job=conn.execute('SELECT * FROM cp_jobs WHERE id=%s' + (' FOR UPDATE' if lock else ''),(r.get('job_id'),)).fetchone()
        if not job or not validated_retirement(job,r): blockers.append(r)
    return blockers


def plan(storage, *, job_id, instance, database_container, workers, decision_id, reason):
    with storage.connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        m=dict(version=1,repository=REPOSITORY,project_id=PROJECT_ID,instance=instance,
            database=database_identity(conn),database_container=database_container,workers=workers,decision_id=decision_id,reason=reason,
            before=read_rows(conn,job_id))
        validate_manifest(m)
        return m


def retire(storage, manifest, approval, *, apply=False, check_quiescent=None):
    """Full-row CAS, durable audit and exact retry in one atomic transaction.

    Commit exceptions propagate: callers reconcile with SAME manifest/approval,
    never refresh expected proof. Default dry-run has no business writes or DDL.
    """
    m=frozen(manifest);a=frozen(approval)
    validate_manifest(m);validate_approval(m,a)
    with storage.connect() as conn:
        if not apply: conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        else:
            project_lock(conn)
            require(callable(check_quiescent), 'retirement_quiescence_required')
            check_quiescent(m)
        require(database_identity(conn)==m['database'], 'retirement_database_changed')
        current=read_rows(conn,m['before']['job']['id'],lock=apply)
        audit=current['job']['checkpoint'].get(KEY)
        if audit:
            require(canonical(audit['manifest'])==canonical(m) and canonical(audit['approval'])==canonical(a),
                    'retirement_conflicting_decision')
            expected=postimages(m,a,audit['outcome']['retired_at'])
            require(canonical(current)==canonical(expected), 'retirement_postimage_drift')
            return deepcopy(audit['outcome'])
        require(canonical(current)==canonical(m['before']), 'retirement_preimage_drift')
        writers=conn.execute("SELECT id FROM cp_jobs WHERE project_id=%s AND id<>%s "
            "AND status NOT IN ('completed','failed','cancelled')" + (' FOR UPDATE' if apply else ''),
            (PROJECT_ID,current['job']['id'])).fetchall()
        require(not writers,'retirement_other_writer')
        claims=conn.execute("SELECT * FROM cp_pcp_local_source_receipts WHERE repository=%s AND project_id=%s "
            "AND issue_number<>%s AND state NOT IN ('pending','delivered')" + (' FOR UPDATE' if apply else ''),
            (REPOSITORY,PROJECT_ID,current['receipt']['issue_number'])).fetchall()
        require(not blocking_receipts(conn,claims,lock=apply), 'retirement_other_reservation')
        if not apply:
            return dict(apply=False, decision_id=m['decision_id'], manifest_sha256=digest(m),
                        disposition=DISPOSITION, job_id=current['job']['id'])
        at=datetime.now(timezone.utc).isoformat();post=postimages(m,a,at)
        conn.execute("UPDATE cp_jobs SET status='cancelled',checkpoint=%s::jsonb,updated_at=%s WHERE id=%s",
            (canonical(post['job']['checkpoint']),at,current['job']['id']))
        conn.execute("UPDATE cp_pcp_local_source_receipts SET state='blocked',generation=generation+1,updated_at=%s "
            "WHERE repository=%s AND project_id=%s AND issue_number=%s",
            (at,REPOSITORY,PROJECT_ID,current['receipt']['issue_number']))
        conn.execute("UPDATE cp_project_leases SET state='released',updated_at=%s WHERE project_id=%s",
                     (at,PROJECT_ID))
        require(read_rows(conn,current['job']['id'])==post, 'retirement_postimage_invalid')
        conn.commit()
        return deepcopy(post['job']['checkpoint'][KEY]['outcome'])
