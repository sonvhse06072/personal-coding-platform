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
    return _inspect_git_proof(row, task, committed=True)


def inspect_verified_tree(row, task):
    """Inspect uncommitted proof without index/object writes in the original."""
    return _inspect_git_proof(row, task, committed=False)


def _inspect_git_proof(row, task, *, committed):
    # Reuse the descriptor-safe reader, configuration/index validator and clean
    # child environment. Git status/add/write-tree may change even existing
    # object metadata; GIT_OPTIONAL_LOCKS=0 alone cannot make this a read.
    from .pcp_local_worker_loop import _retained_snapshot, _retained_validate, _retained_run
    import sys
    path = Path(row['workspace'])
    try:
        with tempfile.TemporaryDirectory(prefix='pcp-inspect-') as scratch:
            home = Path(scratch); clone = home / 'snapshot'
            before = _retained_snapshot(path, clone)
            _retained_validate(clone, home)
            program = '''import json,sys
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1])
from app.pcp_local_recovery import _reconcile_commit_snapshot, verified_tree
value=json.load(sys.stdin);row=value['row'];task=SimpleNamespace(base_sha=value['base'])
result=(_reconcile_commit_snapshot(row,task) if value['committed'] else
        verified_tree(row['workspace'],task,row['checkpoint']['pcp_local_execution']['diff']))
print(json.dumps(result))
'''
            payload = dict(row=dict(workspace=str(clone), checkpoint=row['checkpoint']),
                           base=task.base_sha, committed=committed)
            result = json.loads(_retained_run([sys.executable, '-I', '-B', '-c', program,
                str(Path(__file__).resolve().parent.parent)], home, input=json.dumps(payload).encode()))
            require(_retained_snapshot(path) == before, 'pcp_local_retained_files_changed')
            return result
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        from .pcp_local_task_queue import TaskStop
        if isinstance(exc, TaskStop):
            raise
        raise TaskStop('pcp_local_inspection_invalid') from exc


def _reconcile_commit_snapshot(row, task):
    """Only for the validated disposable snapshot in the clean Git subprocess."""
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
    await readers.refresh_delivery(task)
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


# Held UNVERIFIED work: separate operation and authority from verified recovery.
"""Named held-work verification. No adapter, scheduler, enqueue or coding retry.

All input authority comes from a private independently approved file. A plan is
read-only. The original full rows remain in the audit, never reconstructed.
"""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import json
import os
import re
import tempfile
import time

from .pcp_local_task_queue import (require, LocalSourceTask, PROJECT_ID, REPOSITORY,
    _unique, _verify_issue)

HELD_KEY = 'pcp_local_held_verification'
HELD_PERMIT = Path('/config/pcp-local-held-verification.json')
HELD_ORIGINAL = Path('/config/pcp-local-held-original-activation.json')
ERROR = 'pcp_local_unreviewed_codex_configuration'


def private_bytes(path):
    import stat
    require(path.is_absolute() and path.resolve()==path,'held_private_path_substitution')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink==1
            and before.st_uid in (0,os.getuid()) and before.st_mode & 0o077==0
            and before.st_size<=2_000_000,'held_private_file_invalid')
        data=b''
        while chunk:=os.read(fd,65536):
            data+=chunk
            require(len(data)<=2_000_000,'held_private_file_invalid')
        def identity(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        require(identity(os.fstat(fd))==identity(before)==identity(path.stat(follow_symlinks=False)),'held_private_file_raced')
        return data
    finally:os.close(fd)


def enabled():
    return os.getenv('PCP_LOCAL_HELD_VERIFY_ENABLED') == 'owner-approved'


class HeldPermit:
    def __init__(self):
        import hashlib
        require(enabled(), 'held_verification_disabled')
        self.raw = private_bytes(HELD_PERMIT)
        self.value = json.loads(self.raw, object_pairs_hook=_unique)
        p = self.value
        original = private_bytes(HELD_ORIGINAL)
        a = json.loads(original, object_pairs_hook=_unique)
        require(set(p) == {'version','decision_id','execution_record','not_before','expires_at',
            'original_activation_sha256','before','candidate','invocation_attestation',
            'repair_source','repair_commits','repair_paths','roles','verification_seconds'}, 'held_permit_shape')
        require(p['version'] == 1 and type(p['version']) is int
            and re.fullmatch('[A-Za-z0-9._-]{8,100}', p['decision_id'])
            and p['execution_record'].startswith('https://github.com/'+REPOSITORY+'/issues/835#issuecomment-')
            and p['original_activation_sha256'] == hashlib.sha256(original).hexdigest(), 'held_authority_invalid')
        b = p['before']; r = b['receipt']
        self.task = LocalSourceTask(**{k: tuple(r[k]) if k == 'allowed_paths' else r[k]
            for k in LocalSourceTask.__dataclass_fields__})
        require(all(a[k] == r[k] for k in ('issue_number','base_sha','body_sha256',
            'baseline_revision','baseline_source_commit')) and self.task.base_sha == self.task.baseline_source_commit,
            'held_original_identity_changed')
        require(re.fullmatch('[0-9a-f]{40}', p['repair_source']) and p['repair_source'] != self.task.base_sha
            and p['repair_commits'] and p['repair_commits'][-1] == p['repair_source']
            and p['repair_paths'] == sorted(set(p['repair_paths']))
            and not set(p['repair_paths']) & set(self.task.allowed_paths), 'held_repair_invalid')
        require(type(p['verification_seconds']) is int and 10 <= p['verification_seconds'] <= 900,
            'held_verification_envelope_invalid')
        require(set(p['roles']) == {'runtime','executor','router','verifier'}, 'held_roles_invalid')
        for role,binding in p['roles'].items():
            require(set(binding)==({'image_id','source_commit'} | (set() if role=='verifier' else {'configuration_sha256'}))
                and re.fullmatch('sha256:[0-9a-f]{64}',binding['image_id'])
                and re.fullmatch('[0-9a-f]{40}',binding['source_commit'])
                and (role=='router' or binding['source_commit']==(self.task.base_sha if role=='verifier' else p['repair_source']))
                and (role=='verifier' or re.fullmatch('[0-9a-f]{64}',binding['configuration_sha256'])), 'held_roles_invalid')
        require(p['roles']['verifier']['image_id']==a['verification_image']==a['runtime_image_id'], 'held_verifier_changed')
        self.sha256 = digest(p)
        self.activation = {**a, 'held_verification': deepcopy(p)}
        validate_eligibility(b, self.task, p['invocation_attestation'])
        self.require_fresh()

    def require_fresh(self):
        import hashlib
        p = self.value
        require(enabled() and all(type(p[k]) in (int,float) for k in ('not_before','expires_at'))
            and p['not_before'] <= time.time() < p['expires_at']
            and 0 < p['expires_at']-p['not_before'] <= 86400, 'held_authority_expired')
        require(private_bytes(HELD_PERMIT) == self.raw and digest(self.value) == self.sha256
            and hashlib.sha256(private_bytes(HELD_ORIGINAL)).hexdigest() == p['original_activation_sha256'],
            'held_authority_revoked')

    def verify_issue(self, issue):
        self.require_fresh()
        task = _verify_issue(issue, expected_main=self.value['repair_source'], **{k:getattr(self.task,k)
            for k in ('issue_number','body_sha256','base_sha','baseline_revision','baseline_source_commit')})
        require(task == self.task, 'held_task_changed')
        return task


def validate_eligibility(b, task, attestation):
    from .pcp_local_worker_loop import stable_job_id, claimed_source_receipt
    j,r,l = b['job'],b['receipt'],b['lease']
    cp = j['checkpoint']; e = cp.get('pcp_local_execution',{})
    require(set(b) == {'job','receipt','lease'} and j['id'] == stable_job_id(task)
        and j['project_id'] == PROJECT_ID and j['source_commit'] == task.base_sha
        and j['status'] == 'blocked' and j['error'] == ERROR and j['result'] is None
        and j['branch'] == 'ai/'+j['id'][:12] and e.get('state') == 'held'
        and type(e.get('attempt')) is int and e['attempt'] == 1 and not {'verified_tree','verification','commit'} & e.keys()
        and 'pcp_local_retirement' not in cp and HELD_KEY not in cp
        and cp['pcp_local_source']['receipt'] == claimed_source_receipt(task), 'held_job_ineligible')
    require(r['state'] == 'running' and type(r['generation']) is int and r['generation'] == 2
        and all(canonical(r[k]) == canonical(v) for k,v in vars(task).items())
        and r['job_id'] == j['id'] and l['state'] == 'active' and l['owner_job_id'] == j['id']
        and type(l['generation']) is int and l['generation'] == e['lease_generation'], 'held_ownership_invalid')
    progress = j['progress']
    require(type(progress.get('model_calls')) is int and progress['model_calls'] == 1
        and progress.get('test_runs',0) == 0 and progress.get('delivery_attempts',0) == 0,
        'held_counters_invalid')
    attempts=progress.get('agent_attempts',[])
    require(len(attempts)==1 and attempts[0].get('returncode')==0
        and attempts[0].get('failure_kind') is None and attempts[0].get('adapter')=='codex_cli'
        and isinstance(attempts[0].get('usage'),dict), 'held_invocation_uncertain')
    # A legacy attestation is explicit PM authority over corroborating evidence,
    # not a retroactive Runtime checkpoint. Hashes identify private retained files.
    require(type(attestation) is dict and set(attestation) == {'kind','attempt','progress_sha256',
        'returned_log_sha256','shutdown_sha256','returncode','provider_failed'}
        and attestation['kind'] == 'independent_pm_legacy_returned'
        and attestation['attempt'] == 1 and attestation['returncode'] == 0
        and attestation['provider_failed'] is False
        and attestation['progress_sha256'] == digest(progress)
        and all(re.fullmatch('[0-9a-f]{64}', attestation[k]) for k in ('returned_log_sha256','shutdown_sha256')),
        'held_invocation_evidence_missing')


def candidate(path, task):
    """Unverified candidate from a validated read-only snapshot, no original Git writes."""
    from .pcp_local_worker_loop import _retained_snapshot, _retained_validate, _retained_run
    import sys
    with tempfile.TemporaryDirectory(prefix='pcp-held-') as scratch:
        home=Path(scratch); clone=home/'snapshot'
        before=_retained_snapshot(Path(path),clone)
        _retained_validate(clone,home)
        hooks=clone/'.git/hooks'
        require(not hooks.exists() or all(p.is_file() and p.name.endswith('.sample') for p in hooks.iterdir()),
                'held_git_hooks_forbidden')
        program='''import sys,json
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1])
from app.repo import diff_state
from app.pcp_local_recovery import verified_tree
p=sys.argv[2];t=SimpleNamespace(base_sha=sys.argv[3])
d=diff_state(__import__('pathlib').Path(p),750000,base_ref=t.base_sha)
print(json.dumps(dict(identity=verified_tree(p,t,d),diff=d)))
'''
        value=json.loads(_retained_run([sys.executable,'-I','-B','-c',program,
            str(Path(__file__).resolve().parent.parent),str(clone),task.base_sha],home))
        require(_retained_snapshot(Path(path)) == before, 'held_candidate_raced')
    identity=value['identity'];diff=value['diff']
    from .pcp_local_worker_loop import stable_job_id
    require(identity['parent'] == task.base_sha and identity['branch'] == 'ai/'+stable_job_id(task)[:12]
        and diff['changed_files'] and set(diff['changed_files']) <= set(task.allowed_paths), 'held_candidate_scope')
    # This is a current UNVERIFIED binding. The key never asserts previous tests.
    value['workspace_manifest_sha256']=digest(before)
    return value


def snapshot(storage, permit):
    with storage.connect() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        return read_rows(c,permit.value['before']['job']['id'])


def classify(current, permit):
    p=permit.value; audit=current['job']['checkpoint'].get(HELD_KEY)
    if not audit:
        require(canonical(current) == canonical(p['before']), 'held_preimage_drift')
        return 'eligible'
    require(audit['permit_sha256'] == permit.sha256 and canonical(audit['original']) == canonical(p['before'])
        and canonical(current['receipt']) == canonical(p['before']['receipt']) and canonical(current['lease']) == canonical(p['before']['lease']),
        'held_conflicting_operation')
    # Recovery/delivery legitimately change job columns after verified handoff.
    if audit['state'] == 'verified_uncommitted':
        original=p['before']['job'];j=current['job'];cp=j['checkpoint'];execution=cp['pcp_local_execution']
        mutable={'checkpoint','progress','status','result','updated_at','error'}
        require(all(j[k]==v for k,v in original.items() if k not in mutable)
            and all(cp.get(k)==v for k,v in original['checkpoint'].items() if k!='pcp_local_execution')
            and all(j['progress'].get(k)==v for k,v in original['progress'].items()
                    if k not in {'test_runs','required_checks_passed','elapsed_minutes','delivery_attempts'})
            and execution.get('verified_tree')==p['candidate']['identity']
            and execution.get('diff')==p['candidate']['diff']
            and execution.get('verification')==audit['history'][-1]['verification']
            and execution.get('route')==original['route'], 'held_verified_evidence_drift')
        require(j['progress'].get('test_runs') == execution['verification']['test_runs']
            and j['progress'].get('required_checks_passed') is True
            and j['progress'].get('elapsed_minutes',0) >= original['progress'].get('elapsed_minutes',0)+audit['history'][-1]['seconds']/60
            and j['progress'].get('delivery_attempts',0) >= original['progress'].get('delivery_attempts',0),
            'held_verified_counter_drift')
    else:
        stripped=deepcopy(current['job']);del stripped['checkpoint'][HELD_KEY]
        require(digest(stripped) == audit['after_sha256'], 'held_afterimage_drift')
    return audit['state']


def transition(storage, permit, expected, *, state, verification=None, seconds=0):
    """Existing project lock plus full three-row CAS; receipt and lease never UPDATE."""
    from .storage import now
    p=permit.value
    with storage.connect() as c:
        project_lock(c); permit.require_fresh()
        current=read_rows(c,expected['job']['id'],lock=True)
        require(canonical(current) == canonical(expected), 'held_stale_preimage')
        old=classify(current,permit)
        require((old,state) in {('eligible','verifying'),('verifying','verification_failed'),
            ('verifying','verified_uncommitted')}, 'held_transition_denied')
        j=deepcopy(current['job']); cp=j['checkpoint']; progress=j['progress']
        audit=deepcopy(cp.get(HELD_KEY) or dict(permit_sha256=permit.sha256,original=p['before'],
            candidate=p['candidate'],invocation_attestation=p['invocation_attestation'],history=[]))
        audit.update(state=state)
        audit['history'].append(dict(state=state,at=now().isoformat(),verification=verification,seconds=seconds))
        if verification is not None:
            require(progress.get('test_runs',0) == verification['test_runs'], 'held_test_accounting_changed')
            progress['elapsed_minutes']=p['before']['job']['progress'].get('elapsed_minutes',0)+seconds/60
            progress['required_checks_passed']=verification['passed']
        if state == 'verified_uncommitted':
            cp['pcp_local_execution'].update(state=state,verification=verification,
                verified_tree=p['candidate']['identity'],diff=p['candidate']['diff'],route=j['route'],
                duration_seconds=progress['elapsed_minutes']*60)
        j['updated_at']=now().isoformat()
        cp.pop(HELD_KEY,None);audit['after_sha256']=digest(j);cp[HELD_KEY]=audit
        c.execute('UPDATE cp_jobs SET checkpoint=%s::jsonb,progress=%s::jsonb,updated_at=%s WHERE id=%s',
            (canonical(cp),canonical(progress),j['updated_at'],j['id']))
        c.commit()
    return snapshot(storage,permit)


def phase_record(storage,permit,expected,phase,result,seconds):
    """Account each returned command before another phase; unknown stays intent."""
    from .storage import now
    with storage.connect() as c:
        project_lock(c);permit.require_fresh()
        current=read_rows(c,expected['job']['id'],lock=True)
        require(canonical(current)==canonical(expected) and classify(current,permit)=='verifying','held_phase_stale')
        j=deepcopy(current['job']);cp=j['checkpoint'];audit=cp.pop(HELD_KEY)
        phases=audit.setdefault('phases',[])
        if result is None:
            require(phase==('targeted_tests' if not phases else 'full_tests')
                and (not phases or phases[-1].get('result') is not None),'held_phase_order')
            phases.append(dict(phase=phase,intent_at=now().isoformat(),result=None))
        else:
            require(phases and phases[-1]['phase']==phase and phases[-1]['result'] is None,'held_phase_duplicate')
            phases[-1]['result']=result
            j['progress']['test_runs']=j['progress'].get('test_runs',0)+len(result.get('commands',[]))
        j['progress']['elapsed_minutes']=permit.value['before']['job']['progress'].get('elapsed_minutes',0)+seconds/60
        j['updated_at']=now().isoformat();audit['after_sha256']=digest(j);cp[HELD_KEY]=audit
        c.execute('UPDATE cp_jobs SET checkpoint=%s::jsonb,progress=%s::jsonb,updated_at=%s WHERE id=%s',
            (canonical(cp),canonical(j['progress']),j['updated_at'],j['id']))
        c.commit()
    return snapshot(storage,permit)


@contextmanager
def operation_lock(storage):
    # Session lock spans verifier/Git/publication awaits; transaction CAS keeps
    # the existing registrar lock. Separate key avoids self-deadlock at CAS.
    with storage.connect() as c:
        require(c.execute('SELECT pg_try_advisory_lock(%s,%s) AS locked',(5260112,809)).fetchone()['locked'],
                'held_operation_busy')
        try:yield
        finally:c.execute('SELECT pg_advisory_unlock(%s,%s)',(5260112,809))


async def prepare(engine):
    from .pcp_local_worker_loop import TrustedReaders
    from .pm_bridge import PMBridgeGitHubClient
    from .pcp_local_readiness import schema_readiness
    require(not schema_readiness(engine.storage), "held_schema_unready")
    permit=HeldPermit(); readers=TrustedReaders(engine,PMBridgeGitHubClient())
    task,_=await readers.source()
    require(task == permit.task and readers.held.sha256 == permit.sha256, 'held_reader_identity')
    project,baseline=readers.authority()
    original=permit.value['before']['job']
    require(canonical(original['checkpoint']['project_baseline'])==canonical(baseline.model_dump(mode='json'))
        and original['checkpoint']['pcp_local_execution']['authority_digest']==readers.authority_digest,
        'held_original_authority_changed')
    readers.route=original['route']
    readers.lease_generation=permit.value['before']['lease']['generation']
    await readers.refresh_delivery(task)
    require(Path(permit.value['before']['job']['workspace']) == engine.workspace_root / permit.value['before']['job']['id'], 'held_workspace_changed')
    require(engine.worker_task is None and not engine.active_jobs and engine.queue.empty(), 'held_active_worker')
    return permit,readers


async def operate(engine, *, apply=False, expected=None):
    """One named verification attempt; repeat/uncertain calls only observe intent.

    No import/call of an adapter is reachable. Failed or unknown verification
    cannot be retried by this permit. Commit and publication use existing seams.
    """
    permit,readers=await prepare(engine)
    if apply:
        require(expected == {'job_id':permit.value['before']['job']['id'], 'permit_sha256':permit.sha256},
                'held_request_identity_changed')
    async with engine.project_operation_lock(PROJECT_ID):
        with operation_lock(engine.storage):
            return await _operate_locked(engine,permit,readers,apply)


async def _operate_locked(engine,permit,readers,apply):
    before=snapshot(engine.storage,permit); state=classify(before,permit)
    if state != 'eligible':
        return dict(job_id=before['job']['id'],permit_sha256=permit.sha256,state=state,ready=False,reconcile=True)
    require(canonical(candidate(before['job']['workspace'],permit.task)) == canonical(permit.value['candidate']), 'held_candidate_drift')
    if not apply:return dict(job_id=before['job']['id'],state=state,ready=True,permit_sha256=permit.sha256)
    current=transition(engine.storage,permit,before,state='verifying')
    # Durable intent BEFORE tests. Crash/lost response cannot repeat tests.
    started=time.monotonic()
    def observe(phase,result):
        nonlocal current
        current=phase_record(engine.storage,permit,current,phase,result,time.monotonic()-started)
    verification=await engine.verify_pcp_local(before['job']['id'],Path(before['job']['workspace']),
        readers.authority()[0],timeout_seconds=permit.value['verification_seconds'],phase_observer=observe)
    await readers.refresh_delivery(permit.task)
    require(canonical(candidate(before['job']['workspace'],permit.task)) == canonical(permit.value['candidate']), 'held_tested_candidate_drift')
    state='verified_uncommitted' if verification['passed'] else 'verification_failed'
    current=transition(engine.storage,permit,current,state=state,verification=verification,seconds=time.monotonic()-started)
    if verification['passed']:
        from .pcp_local_recovery import recover_verified_job
        row=engine.storage.get(before['job']['id'])
        await recover_verified_job(engine,readers,permit.task,row)
        await engine.deliver_pcp_local(row['id'],readers,permit.task)
    return dict(job_id=before['job']['id'],state=state,ready=False,reconcile=True)
