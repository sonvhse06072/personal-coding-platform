"""Real Git/PostgreSQL finalization and phase checks; external authority is stubbed."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from app import pcp_local_readiness as r, pcp_local_worker_loop as w
from app.engine import RuntimeEngine
from app.pcp_local_recovery import recover_verified_job
from app.pcp_local_task_queue import TaskStop
from test_pcp_local_consolidation_postgres import database, seed, ownership  # noqa:F401
from test_pcp_local_consolidation import verified  # noqa:F401
from test_pcp_local_runtime_dispatch import setup  # noqa:F401


@pytest.fixture
def lifecycle(database, verified, setup, monkeypatch, tmp_path):
    db,v,s=database,verified,setup
    seed(db,v)
    row=asyncio.run(recover_verified_job(SimpleNamespace(storage=db),v.reader,v.task,db.get(v.store.row['id'])))
    # Fixture repositories move to their final isolated path before use by the session.
    root=tmp_path/'retained';root.mkdir();path=root/row['id']
    # verified fixture lives at tmp_path itself; clone its exact committed Git tree.
    import subprocess
    subprocess.run(['git','clone','--no-hardlinks',str(v.path),str(path)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(path),'config','user.name','PCP Local'],check=True)
    subprocess.run(['git','-C',str(path),'config','user.email','pcp-local@localhost'],check=True)
    base=SimpleNamespace(revision=v.task.baseline_revision, model_dump=lambda **kw: {'revision':v.task.baseline_revision})
    cp=deepcopy(row['checkpoint']);cp['project_baseline']=base.model_dump()
    cp['canonical_intake']={'mode':'direct','bounded_direct':True}
    cp['pcp_local_source']['receipt']=w.claimed_source_receipt(v.task)
    result=deepcopy(row['result']);head=result['commit'];branch=row['branch']
    pr={'number':123,'repository':v.task.repository,'state':'open','merged':False,'head':head,'head_ref':branch,'base_ref':'main'}
    ci={'state':'success','commit':head}
    result['delivery']={'state':'ci_success','pull_request':pr,'ci':ci}
    progress={**row['progress'],'model_calls':1,'test_runs':2,'delivery_attempts':1,'required_checks_passed':True}
    db.update(row['id'],workspace=str(path),checkpoint=cp,result=result,progress=progress,status='blocked',error='awaiting_independent_pm_review')
    engine=object.__new__(RuntimeEngine);engine.storage=db;engine.workspace_root=root
    activation={k:getattr(v.task,k) for k in ('issue_number','body_sha256','base_sha','baseline_revision','baseline_source_commit')}
    monkeypatch.setattr(w.TrustedReaders,'__init__',lambda self,engine,github:self.__dict__.update(engine=engine,activation=activation))
    monkeypatch.setattr(w.TrustedReaders,'authority',lambda self:(s.project,base))
    async def executor(self,endpoint,payload):
        assert endpoint=='/v1/pcp-local/pm-review'
        return dict(job_id=row['id'],expected_head=head,activation_digest=w.digest(activation),
            report={'verdict':'pass','diff_hash':result['diff']['diff_hash']},pr=pr,ci=ci)
    monkeypatch.setattr(w.TrustedReaders,'executor',executor)
    return SimpleNamespace(db=db,v=v,engine=engine,id=row['id'],path=path,root=root,base=base,activation=activation,project=s.project)


def view(s,phase='finalization',review=7):
    return asyncio.run(r.collect_readiness(s.engine,phase=phase,job_id=s.id,review_id=review))


def test_phase_finalization_real_git_pg_no_provider_and_exact_retry(lifecycle,monkeypatch):
    s=lifecycle
    def forbidden(*a,**k):pytest.fail('phase must not use provider/Router or model')
    monkeypatch.setattr('app.quota_telemetry.CodexQuotaCollector.collect',forbidden)
    monkeypatch.setattr('app.adapters.codex.CodexAdapter.run',forbidden)
    before=s.db.get(s.id);owners=ownership(s.db)
    readiness=view(s);assert readiness['ready'],readiness
    assert s.db.get(s.id)==before and ownership(s.db)==owners
    request=SimpleNamespace(**readiness['identity'])
    result=asyncio.run(s.engine.finalize_pcp_local_review(request))
    after=s.db.get(s.id);rec,lease=ownership(s.db)
    assert result['status']==after['status']=='completed'
    assert rec[0]['state']=='delivered' and rec[0]['generation']==3
    assert lease[0]['state']=='released' and lease[0]['generation']==1
    assert after['checkpoint']==before['checkpoint'] and after['progress']==before['progress']
    assert asyncio.run(s.engine.finalize_pcp_local_review(request))==result and s.db.get(s.id)==after
    assert view(s)['existing_success'] and not view(s,review=8)['ready']
    # Completed observation does not load even expired/revoked authority.
    monkeypatch.setattr(w.TrustedReaders,'authority',forbidden)
    assert view(s,'status')['ready'] and s.db.get(s.id)==after


@pytest.mark.parametrize('drift',['content','mode','symlink','receipt','lease','authority','review'])
def test_phase_blocks_drift_without_refreshing_evidence(lifecycle,monkeypatch,drift):
    s=lifecycle;before=s.db.get(s.id)
    if drift=='content':(s.path/'new.py').write_text('unverified')
    elif drift=='mode':(s.path/'new.py').chmod(0o755)
    elif drift=='symlink':(s.path/'untrusted').symlink_to('/etc/passwd')
    elif drift in ('receipt','lease'):
        table='cp_pcp_local_source_receipts' if drift=='receipt' else 'cp_project_leases'
        with s.db.connect() as c:c.execute('UPDATE '+table+' SET generation=generation+1')
    elif drift=='authority':
        def revoked(*a):raise TaskStop('claim_recovery_permit_expired')
        monkeypatch.setattr(w.TrustedReaders,'authority',revoked)
    else:
        async def denied(*a):raise TaskStop('pcp_local_pm_report_denied')
        monkeypatch.setattr(w.TrustedReaders,'executor',denied)
    assert not view(s)['ready'] and s.db.get(s.id)==before


def test_retained_completed_workspace_still_blocks_B_pending_read_isolation(lifecycle,monkeypatch):
    s=lifecycle;ready=view(s);asyncio.run(s.engine.finalize_pcp_local_review(SimpleNamespace(**ready['identity'])))
    retained=s.db.get(s.id);owners=ownership(s.db)
    task=replace(s.v.task,issue_number=s.v.task.issue_number+1,task_key='fixture-next-task')
    reader=object.__new__(w.TrustedReaders);reader.engine=s.engine;reader.activation=s.activation;reader.recovery=None
    project=deepcopy(s.project);project['ddev'].update(targeted_tests=list(task.allowed_paths),full_tests=list(task.allowed_paths))
    reader.authority=lambda:(project,s.base)
    async def source():return task,{'body':'fixture'}
    async def executor(endpoint,payload):
        assert endpoint=='/v1/pcp-local/observe'
        return dict(job_id=w.stable_job_id(task),source_commit=task.base_sha,activation_digest=w.digest(reader.activation))
    reader.source=source;reader.executor=executor
    with pytest.raises(TaskStop,match='pcp_local_foreign_workspace'):
        asyncio.run(reader.refresh(task))
    assert s.db.get(s.id)==retained and ownership(s.db)==owners and s.path.is_dir()


def test_delivery_refresh_skips_quota_router_but_keeps_source_and_lease(lifecycle,monkeypatch):
    s=lifecycle;task=s.v.task
    reader=object.__new__(w.TrustedReaders)
    reader.engine=s.engine;reader.activation=s.activation;reader.recovery=None;reader.lease_generation=1
    project=deepcopy(s.project);project['ddev'].update(targeted_tests=list(task.allowed_paths),full_tests=list(task.allowed_paths))
    reader.authority=lambda:(project,s.base)
    async def source():return task,{'body':'fixture'}
    async def executor(endpoint,payload):return dict(job_id=s.id,source_commit=task.base_sha,activation_digest=w.digest(s.activation))
    reader.source=source;reader.executor=executor
    def forbidden(*a,**k):pytest.fail('delivery must not use developer quota or Router')
    monkeypatch.setattr('app.quota_telemetry.CodexQuotaCollector.collect',forbidden)
    s.engine.router=SimpleNamespace(route=forbidden)
    # Host credential/socket availability is a synthetic container observation.
    real_exists=w.Path.exists
    monkeypatch.setattr(w.Path,'exists',lambda p:False if str(p)=='/var/run/docker.sock' or str(p).endswith('/.ssh') else real_exists(p))
    for name in ('GITHUB_DELIVERY_TOKEN','GITHUB_TOKEN','GH_TOKEN'):monkeypatch.delenv(name,raising=False)
    assert asyncio.run(reader.refresh_delivery(task))['job_id']==s.id
    with monkeypatch.context() as patch:
        clock=iter((0,31))
        patch.setattr(w,'time',SimpleNamespace(monotonic=lambda:next(clock)))
        with pytest.raises(TaskStop,match='pcp_local_observation_expired'):
            asyncio.run(reader.refresh_delivery(task))
    with s.db.connect() as conn:conn.execute("UPDATE cp_project_leases SET generation=2")
    with pytest.raises(TaskStop,match='lease_revoked'):asyncio.run(reader.refresh_delivery(task))


@pytest.mark.parametrize('fault',['rollback','lost_ack','progress_drift'])
def test_pm_transaction_uncertainty_and_full_row_race(lifecycle,monkeypatch,fault):
    s=lifecycle;request=SimpleNamespace(**view(s)['identity']);before=s.db.get(s.id);owners=ownership(s.db)
    connect=s.db.connect
    class Wrapped:
        def __init__(self):self.conn=connect();self.updated=False
        def __enter__(self):self.conn.__enter__();return self
        def __exit__(self,*args):return self.conn.__exit__(*args)
        def execute(self,sql,params=None):
            if sql.startswith('SELECT * FROM cp_jobs WHERE id=') and 'FOR UPDATE' in sql and fault=='progress_drift':
                self.conn.execute("UPDATE cp_jobs SET progress=jsonb_set(progress,'{model_calls}','2')")
            if sql.startswith('UPDATE cp_jobs SET status='):
                self.updated=True
                if fault=='rollback':raise RuntimeError('fixture rollback')
            return self.conn.execute(sql,params)
        def commit(self):
            self.conn.commit()
            if self.updated and fault=='lost_ack':raise RuntimeError('fixture lost ack')
    monkeypatch.setattr(s.db,'connect',Wrapped)
    with pytest.raises((RuntimeError,TaskStop)):asyncio.run(s.engine.finalize_pcp_local_review(request))
    monkeypatch.setattr(s.db,'connect',connect)
    after=s.db.get(s.id)
    if fault=='lost_ack':
        assert after['status']=='completed' and view(s)['existing_success']
        assert asyncio.run(s.engine.finalize_pcp_local_review(request))['status']=='completed'
        assert s.db.get(s.id)==after
    else:
        assert after==before and ownership(s.db)==owners
    assert after['progress']==before['progress']


def test_concurrent_finalizers_one_commit_then_reconcile(lifecycle,monkeypatch):
    s=lifecycle;request=SimpleNamespace(**view(s)['identity']);before=s.db.get(s.id)
    original=w.TrustedReaders.executor
    async def exercise():
        arrived=0;both=asyncio.Event()
        async def review(self,*args):
            nonlocal arrived
            arrived+=1
            if arrived==2:both.set()
            await both.wait()
            return await original(self,*args)
        monkeypatch.setattr(w.TrustedReaders,'executor',review)
        return await asyncio.gather(s.engine.finalize_pcp_local_review(request),
            s.engine.finalize_pcp_local_review(request),return_exceptions=True)
    outcomes=asyncio.run(exercise())
    assert sum(isinstance(x,dict) and x['status']=='completed' for x in outcomes)==1
    assert sum(isinstance(x,TaskStop) and x.code=='pcp_local_review_race' for x in outcomes)==1
    after=s.db.get(s.id);rec,lease=ownership(s.db)
    assert after['progress']==before['progress'] and after['checkpoint']==before['checkpoint']
    assert (rec[0]['state'],rec[0]['generation'],lease[0]['state'],lease[0]['generation'])==('delivered',3,'released',1)
    assert view(s)['existing_success'] and s.db.get(s.id)==after


@pytest.mark.parametrize('table,change',[
    ('cp_pcp_local_source_receipts',"task_key='changed-without-generation'"),
    ('cp_project_leases',"updated_at=updated_at+interval '1 second'")])
def test_full_ownership_row_drift_during_review_is_preserved(lifecycle,monkeypatch,table,change):
    s=lifecycle;request=SimpleNamespace(**view(s)['identity']);before=s.db.get(s.id)
    original=w.TrustedReaders.executor;changed=[]
    async def review(self,*args):
        with s.db.connect() as conn:conn.execute('UPDATE '+table+' SET '+change)
        changed.append(ownership(s.db))
        return await original(self,*args)
    monkeypatch.setattr(w.TrustedReaders,'executor',review)
    with pytest.raises(TaskStop,match='pcp_local_review_(receipt|lease)_changed'):
        asyncio.run(s.engine.finalize_pcp_local_review(request))
    assert s.db.get(s.id)==before and ownership(s.db)==changed[0]


def test_completed_status_survives_later_lease_owner_without_rewriting_A(lifecycle):
    s=lifecycle;asyncio.run(s.engine.finalize_pcp_local_review(SimpleNamespace(**view(s)['identity'])))
    before=s.db.get(s.id)
    # Lease storage semantics only: this is not B admission or developer isolation.
    second=deepcopy(before)
    second.update(id='b'*32,status='queued',checkpoint={},result=None)
    s.db.create(second)
    lease=s.db.acquire_project_lease('pcp-local','b'*32)
    assert lease['generation']==2
    assert view(s,'status')['ready'] and view(s)['existing_success']
    assert s.db.get(s.id)==before


def test_aggregates_independent_unknown_and_blocked_without_secret_text(lifecycle,monkeypatch):
    s=lifecycle
    (s.path/'new.py').write_text('drift')
    with s.db.connect() as conn:conn.execute('UPDATE cp_project_leases SET generation=2')
    async def offline(*args):raise OSError('Bearer PRIVATE transport unavailable')
    monkeypatch.setattr(w.TrustedReaders,'executor',offline)
    # Ownership blocks before transport: independently record authority as unknown.
    def unavailable(*args):raise OSError('Bearer PRIVATE')
    monkeypatch.setattr(w.TrustedReaders,'authority',unavailable)
    result=view(s)
    states={c['component']:c['state'] for c in result['checks']}
    assert states['ownership']==states['verified_proof']=='blocked'
    assert states['authority_review_ci']=='unknown' and states['provider']=='not_applicable'
    assert not result['ready'] and 'PRIVATE' not in str(result)


def test_phase_http_authentication_and_observer_boundary(lifecycle,monkeypatch):
    import httpx
    from app import main
    s=lifecycle
    monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE','pcp_local_worker')
    monkeypatch.setenv('RUNTIME_API_TOKEN','fixture-token')
    monkeypatch.setattr(main.app.state,'pcp_local_worker_ready',True,raising=False)
    monkeypatch.setattr(main,'engine',s.engine)
    before=s.db.get(s.id)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
            path='/v1/pcp-local/readiness?phase=status&job_id='+s.id
            assert (await client.get(path)).status_code==401
            headers={'Authorization':'Bearer fixture-token'}
            response=await client.get(path,headers=headers)
            assert response.status_code==200 and response.json()['job']['id']==s.id
            response=await client.get(path.replace('phase=status','phase=unknown'),headers=headers)
            assert not response.json()['ready'] and response.json()['blockers'][0]['code']=='unsupported_phase'
            monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE','pcp_local_dashboard')
            assert (await client.get(path,headers=headers)).status_code==403
    asyncio.run(exercise())
    assert s.db.get(s.id)==before


def test_finalization_rechecks_revocation_after_git_before_commit(lifecycle,monkeypatch):
    from app import pcp_local_recovery
    s=lifecycle;request=SimpleNamespace(**view(s)['identity'])
    before=s.db.get(s.id);owners=ownership(s.db);revoked=False
    reconcile=pcp_local_recovery.reconcile_commit
    authority=w.TrustedReaders.authority
    def proof(*args):
        nonlocal revoked
        result=reconcile(*args);revoked=True
        return result
    def check(self):
        if revoked:raise TaskStop('pcp_local_delegation_revoked')
        return authority(self)
    monkeypatch.setattr(pcp_local_recovery,'reconcile_commit',proof)
    monkeypatch.setattr(w.TrustedReaders,'authority',check)
    with pytest.raises(TaskStop,match='pcp_local_delegation_revoked'):
        asyncio.run(s.engine.finalize_pcp_local_review(request))
    assert s.db.get(s.id)==before and ownership(s.db)==owners
