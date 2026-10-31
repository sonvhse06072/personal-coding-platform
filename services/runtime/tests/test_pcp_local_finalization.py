"""Real Git/PostgreSQL; remote review/resources are explicitly synthetic FIXTURE."""
import asyncio
from copy import deepcopy
import hashlib
import json
import time
from types import SimpleNamespace

import pytest
from app import pcp_local_review_repair as repair, pcp_local_recovery as h, pcp_local_worker_loop as w
from app.pcp_local_task_queue import TaskStop
from test_pcp_local_review_repair import local_repair, private_review_permit, execute, ci  # noqa:F401
from test_pcp_local_consolidation import verified  # noqa:F401
from test_pcp_local_consolidation_postgres import database, ownership  # noqa:F401
EXECUTOR_METHOD = w.TrustedReaders.executor


@pytest.fixture
def finalization(private_review_permit, monkeypatch, tmp_path):
    s, old, path, patch, save = private_review_permit
    actual = repair.Permit()
    s.p = actual
    s.reader.local_review = actual
    s.reader.activation = actual.activation
    async def prepare(engine):
        return actual, s.reader
    monkeypatch.setattr(repair, 'prepare', prepare)
    async def refresh(task):
        assert task==s.v.task
        repair.classify(repair.snapshot(s.db,actual),actual)
    s.reader.refresh_delivery=refresh
    assert asyncio.run(execute(s))['state'] == 'awaiting_pm_review'
    # Expire the ORIGINAL window before sealing this fixture's historical bytes.
    # Rebind only this synthetic fixture's audit, never a real/consumed permit.
    # Actual restored-copy coverage uses original expired bytes without rewriting.
    old['not_before'] = time.time() - 1200
    old['expires_at'] = time.time() - 600
    save()
    old_digest = h.digest(old)
    row = s.db.get(s.before['job']['id'])
    cp = deepcopy(row['checkpoint'])
    cp[repair.KEY]['permit_sha256'] = old_digest
    for name, entries in repair.history_entries(old, old_digest).items():
        cp[name] = entries
    s.db.update(row['id'], checkpoint=cp)
    before = h.snapshot(s.db, SimpleNamespace(value={'before': {'job': row}}))
    head = before['job']['result']['commit']
    report = dict(verdict='pass', findings=[], diff_hash=before['job']['result']['diff']['diff_hash'])
    body = 'FIXTURE independent review body'
    authority = dict(version=1, decision_id='fixture-finalization-only',
        execution_record='https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-2',
        not_before=time.time()-1, expires_at=time.time()+600,
        original_repair_raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        original_repair_digest=old_digest, before=before,
        workspace_sha256=h.digest(h.frozen(w._retained_snapshot(s.v.path))),
        expected_head=head, diff_hash=report['diff_hash'], pr_number=7,
        review=dict(id=81, body_sha256=hashlib.sha256(body.encode()).hexdigest(), ci_run_id=9),
        repair_source='e'*40, repair_commits=['e'*40], repair_paths=['services/runtime/app/pcp_local_finalization.py'],
        roles=deepcopy(old['roles']), resources=dict(worker_ids={k: str(i)*64 for i,k in enumerate(('runtime','executor','router'),1)},
            database=dict(container_id='4'*64, image_id='sha256:'+'5'*64, configuration_sha256='6'*64),
            network_id='7'*64, observer_binding_sha256=h.digest(actual.activation.get('observer_binding'))))
    for role in ('runtime', 'executor'):
        authority['roles'][role]['source_commit'] = authority['repair_source']
    file = tmp_path/'finalization.json'
    def seal():
        file.write_text(h.canonical(authority)); file.chmod(0o600)
    seal()
    monkeypatch.setenv('PCP_LOCAL_FINALIZATION_ENABLED', 'owner-approved')
    monkeypatch.delenv(repair.FLAG)
    # Paths are private fixture files. X intentionally has no finalization module.
    import importlib.util
    if importlib.util.find_spec('app.pcp_local_finalization'):
        from app import pcp_local_finalization as f
        monkeypatch.setattr(f, 'PERMIT', file)
    else:
        monkeypatch.setenv(repair.FLAG, 'owner-approved')
    project, baseline = s.reader.authority()
    def authority_reader(reader):
        reader.authority_digest=s.reader.authority_digest
        if getattr(reader, 'finalization', None):
            reader.finalization.require_fresh()
        return project, baseline
    monkeypatch.setattr(w.TrustedReaders, 'authority', authority_reader)
    calls=[]
    async def remote(reader, endpoint, payload):
        assert endpoint == '/v1/pcp-local/pm-review'
        calls.append(endpoint)
        return dict(job_id=before['job']['id'], expected_head=head,
            activation_digest=w.digest(reader.activation), report=deepcopy(report),
            review_id=81, review_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
            ci_run_id=9, ci=ci(head), pr=deepcopy(s.remote))
    monkeypatch.setattr(w.TrustedReaders, 'executor', remote)
    s.e.worker_task=None; s.e.active_jobs=set(); s.e.queue=asyncio.Queue()
    payload=SimpleNamespace(source_commit=s.v.task.base_sha, expected_head=head,
        branch=before['job']['branch'], baseline_revision=s.v.task.baseline_revision, pr_number=7, review_id=81)
    return SimpleNamespace(s=s, value=authority, file=file, seal=seal, before=before, payload=payload, calls=calls,
        original_bytes=path.read_bytes(), old_path=path, old_value=old, report=report)


def test_expired_repair_separate_finalization_through_atomic_cas(finalization):
    f=finalization; s=f.s; snapshot=w._retained_snapshot(s.v.path)
    ready=asyncio.run(s.e.finalize_pcp_local_review(f.payload, dry_run=True))
    assert ready['status']=='ready_for_pm_finalization'
    assert h.snapshot(s.db,SimpleNamespace(value={'before':{'job':f.before['job']}}))==f.before
    result=asyncio.run(s.e.finalize_pcp_local_review(f.payload))
    assert result['status']=='completed'
    row=s.db.get(f.before['job']['id']); receipts,leases=ownership(s.db)
    assert row['progress']==f.before['job']['progress'] and row['checkpoint']==f.before['job']['checkpoint']
    assert [row['progress'][k] for k in ('model_calls','test_runs','delivery_attempts')]==[1,4,2]
    assert (receipts[0]['state'],receipts[0]['generation'],leases[0]['state'],leases[0]['generation'])==('delivered',3,'released',4)
    assert asyncio.run(s.e.finalize_pcp_local_review(f.payload))['status']=='completed'
    assert s.db.get(row['id'])==row
    assert f.old_path.read_bytes()==f.original_bytes and w._retained_snapshot(s.v.path)==snapshot


@pytest.mark.parametrize('fault', ['absent','disabled','expired','future','bool_time','revoked',
    'original_raw','original_digest','history','proof','head','diff','review','ci','verifier','role',
    'resource','lease','receipt','rows','usage','workspace','unknown_fields','duplicate'])
def test_exact_finalization_authority_rejects_drift_without_mutation(finalization, monkeypatch, fault):
    f=finalization; s=f.s; a=f.value
    if fault=='absent': f.file.unlink()
    elif fault=='disabled': monkeypatch.delenv('PCP_LOCAL_FINALIZATION_ENABLED')
    elif fault=='expired': a['expires_at']=time.time()-1; f.seal()
    elif fault=='future': a['not_before']=time.time()+10; f.seal()
    elif fault=='bool_time': a['not_before']=True; f.seal()
    elif fault=='revoked':
        from app.pcp_local_finalization import Authority
        cached=Authority(); f.file.unlink()
        with pytest.raises((TaskStop,OSError)): cached.require_fresh()
    elif fault in ('original_raw','original_digest'):
        a['original_repair_raw_sha256' if fault=='original_raw' else 'original_repair_digest']='0'*64; f.seal()
    elif fault=='history':
        cp=deepcopy(s.db.get(f.before['job']['id'])['checkpoint']); cp[repair.KEY]['original']['job']['progress']['input_tokens']=0
        s.db.update(f.before['job']['id'],checkpoint=cp)
    elif fault=='proof':
        cp=deepcopy(s.db.get(f.before['job']['id'])['checkpoint']); cp['pcp_local_execution']['verification']['passed']=False
        s.db.update(f.before['job']['id'],checkpoint=cp)
    elif fault=='head': f.payload.expected_head='0'*40
    elif fault=='diff': f.report['diff_hash']='0'*64
    elif fault=='review': f.payload.review_id=80
    elif fault=='ci': a['review']['ci_run_id']=10; f.seal()
    elif fault=='verifier': a['roles']['verifier']['image_id']='sha256:'+'0'*64; f.seal()
    elif fault=='role': a['roles']['executor']['source_commit']='0'*40; f.seal()
    elif fault=='resource': a['resources']['worker_ids']['executor']='bad'; f.seal()
    elif fault in ('lease','receipt'):
        with s.db.connect() as c: c.execute('UPDATE '+('cp_project_leases' if fault=='lease' else 'cp_pcp_local_source_receipts')+' SET generation=generation+1')
    elif fault=='rows': s.db.update(f.before['job']['id'],error='unapproved change')
    elif fault=='usage':
        progress=deepcopy(f.before['job']['progress']); progress['model_calls']=2; s.db.update(f.before['job']['id'],progress=progress)
    elif fault=='workspace': (s.v.path/'new.py').write_text('extra unverified edit')
    elif fault=='unknown_fields': a['run']=True; f.seal()
    else: f.file.write_text(f.file.read_text()[:-1]+',"version":1}')
    before=h.snapshot(s.db,SimpleNamespace(value={'before':{'job':f.before['job']}}))
    with pytest.raises((TaskStop,OSError,KeyError,ValueError,TypeError)):
        asyncio.run(s.e.finalize_pcp_local_review(f.payload))
    assert h.snapshot(s.db,SimpleNamespace(value={'before':{'job':f.before['job']}}))==before
    assert s.calls==['targeted_tests','full_tests','publish','pr']


@pytest.mark.parametrize('fault',['revoke','remote','git','expiry'])
def test_revalidate_after_remote_and_under_lock(finalization,monkeypatch,fault):
    f=finalization;s=f.s; actual=w.TrustedReaders.executor;calls=[]
    async def remote(reader,endpoint,payload):
        result=await actual(reader,endpoint,payload); calls.append(endpoint)
        if len(calls)==2:
            if fault=='revoke':f.file.unlink()
            elif fault=='remote':result['review_body_sha256']='0'*64
            elif fault=='git':(s.v.path/'new.py').write_text('drift immediately before CAS')
            else:
                f.value['expires_at']=time.time()-1; f.seal()
        return result
    monkeypatch.setattr(w.TrustedReaders,'executor',remote)
    with pytest.raises((TaskStop,OSError)):asyncio.run(s.e.finalize_pcp_local_review(f.payload))
    assert h.snapshot(s.db,SimpleNamespace(value={'before':{'job':f.before['job']}}))==f.before
    assert len(calls)==2


@pytest.mark.parametrize('committed',[False,True])
def test_finalization_transaction_rollback_and_lost_ack(finalization,monkeypatch,committed):
    f=finalization;s=f.s; connect=s.db.connect
    class Connection:
        def __enter__(self):self.c=connect();return self
        def __exit__(self,*args):return self.c.__exit__(*args)
        def execute(self,*args):return self.c.execute(*args)
        def commit(self):
            if committed:self.c.commit()
            raise ConnectionError('FIXTURE uncertain COMMIT acknowledgement')
    monkeypatch.setattr(s.db,'connect',Connection)
    with pytest.raises(ConnectionError):asyncio.run(s.e.finalize_pcp_local_review(f.payload))
    monkeypatch.setattr(s.db,'connect',connect)
    after=h.snapshot(s.db,SimpleNamespace(value={'before':{'job':f.before['job']}}))
    if not committed:assert after==f.before
    else:
        assert after['job']['result']['delivery_finalized']
        calls=len(f.calls)
        assert asyncio.run(s.e.finalize_pcp_local_review(f.payload))['status']=='completed'
        assert h.snapshot(s.db,SimpleNamespace(value={'before':{'job':f.before['job']}}))==after and len(f.calls)==calls
    assert f.old_path.read_bytes()==f.original_bytes


def test_concurrent_exact_requests_and_conflicting_retry(finalization):
    f=finalization;s=f.s
    async def run():return await asyncio.gather(s.e.finalize_pcp_local_review(f.payload),s.e.finalize_pcp_local_review(f.payload))
    assert [r['status'] for r in asyncio.run(run())]==['completed','completed']
    assert len(f.calls)==2 # one initial read + one under CAS; duplicate only reads durable state
    f.payload.review_id=80
    with pytest.raises(TaskStop):asyncio.run(s.e.finalize_pcp_local_review(f.payload))
    row=s.db.get(f.before['job']['id']); result=deepcopy(row['result']);result['delivery']['state']='corrupt'
    s.db.update(row['id'],result=result); f.payload.review_id=81
    with pytest.raises(TaskStop):asyncio.run(s.e.finalize_pcp_local_review(f.payload))


def test_finalization_only_cannot_reach_any_execution_reader(finalization,monkeypatch):
    f=finalization;s=f.s
    from app.pcp_local_finalization import Authority
    authority=Authority(); old=authority.historical
    assert not hasattr(old,'require_fresh')
    for call in (repair.Permit,w.read_activation,w.source_worker_flags):
        with pytest.raises(TaskStop): call()
    with pytest.raises(TaskStop): asyncio.run(repair.operate(s.e,apply=True,expected={}))
    reader=w.TrustedReaders(s.e,SimpleNamespace(),finalization=True)
    with pytest.raises(TaskStop):asyncio.run(reader.source())
    with pytest.raises(TaskStop):asyncio.run(reader.refresh(s.v.task))
    for endpoint in ('/v1/pcp-local/observe','/v1/pcp-local/phase','/v1/github/publish'):
        with pytest.raises(TaskStop):asyncio.run(EXECUTOR_METHOD(reader,endpoint,{}))
    assert h.snapshot(s.db,SimpleNamespace(value={'before':{'job':f.before['job']}}))==f.before


def test_aggregate_finalization_dry_run_inventory(finalization):
    from app.pcp_local_readiness import operation_readiness
    f=finalization;s=f.s
    result=asyncio.run(operation_readiness(s.e,phase='finalization',job_id=f.before['job']['id'],review_id=81))
    assert result['ready'] and result['authorized'] is False
    checks={x['component']:x['state'] for x in result['checks']}
    assert checks['provider']==checks['router']==checks['fresh_admission']=='not_applicable'
    assert checks['authority_review_ci']==checks['verified_proof']==checks['ownership']=='pass'
    assert h.snapshot(s.db,SimpleNamespace(value={'before':{'job':f.before['job']}}))==f.before


def test_finalization_respects_cross_process_operation_lock(finalization):
    f=finalization
    with h.operation_lock(f.s.db):
        with pytest.raises(TaskStop,match='operation_busy'):
            asyncio.run(f.s.e.finalize_pcp_local_review(f.payload))
    assert h.snapshot(f.s.db,SimpleNamespace(value={'before':{'job':f.before['job']}}))==f.before
