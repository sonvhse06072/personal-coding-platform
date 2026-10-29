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

TRUSTED_INIT = w.TrustedReaders.__init__
TRUSTED_AUTHORITY = w.TrustedReaders.authority


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
    base_value=dict(project_id='pcp-local', revision=v.task.baseline_revision, source_commit=v.task.baseline_source_commit, status='approved')
    base=SimpleNamespace(**base_value, model_dump=lambda **kw: deepcopy(base_value))
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


@pytest.fixture
def ordinary_B(lifecycle,monkeypatch,tmp_path):
    """Real ordinary queue/registrar and all eight readers; transport facts are doubles."""
    import hashlib,json
    from app import config, engine as engine_module, pcp_local_task_queue as q
    from test_pcp_local_worker_loop import fixture
    s=lifecycle
    asyncio.run(s.engine.finalize_pcp_local_review(SimpleNamespace(**view(s)['identity'])))
    retained=s.db.get(s.id);old_receipt,old_lease=ownership(s.db)
    _,issue,_,facts=fixture();issue=deepcopy(issue)
    payload=json.loads(issue['body'].split(q.MARKER,1)[1]);payload['base_sha']=s.v.task.base_sha
    payload['key']='fixture-ordinary-b'
    issue.update(number=s.v.task.issue_number+1,main_sha=s.v.task.base_sha,
        html_url=f'https://github.com/{q.REPOSITORY}/issues/{s.v.task.issue_number+1}',
        body=q.MARKER+'\n'+json.dumps(payload))
    activation={**s.activation,'issue_number':issue['number'],
        'body_sha256':hashlib.sha256(issue['body'].encode()).hexdigest(),
        'codex_version':'0.160.0','budget':dict(model_calls=1,max_wall_seconds=600,cash_ceiling_usd=0.0)}
    task=q.verify_issue(issue,**{k:activation[k] for k in ('issue_number','body_sha256','base_sha','baseline_revision','baseline_source_commit')})
    project=deepcopy(s.project);project['ddev'].update(targeted_tests=list(task.allowed_paths),full_tests=list(task.allowed_paths))
    monkeypatch.setattr(config,'project_config',lambda _:deepcopy(project))
    monkeypatch.setattr(engine_module,'project_config',lambda _:deepcopy(project))
    monkeypatch.setattr(config,'projects_doc',lambda:{'projects':{'pcp-local':project}})
    def baselines():return {'projects':{'pcp-local':{'active_revision':task.baseline_revision}}}
    baselines.cache_clear=lambda:None
    monkeypatch.setattr(config,'project_baselines_doc',baselines)
    monkeypatch.setattr('app.baseline.resolve_project_baseline',lambda *a:s.base)
    monkeypatch.setattr(engine_module,'resolve_project_baseline',lambda *a:s.base)
    monkeypatch.setattr(w,'read_activation',lambda:deepcopy(activation))
    monkeypatch.setattr(w.TrustedReaders,'__init__',TRUSTED_INIT)
    monkeypatch.setattr(w.TrustedReaders,'authority',TRUSTED_AUTHORITY)
    for key in ('GITHUB_TOKEN','GH_TOKEN','GITHUB_DELIVERY_TOKEN','PCP_LOCAL_CLAIM_RECOVERY_ENABLED'):
        monkeypatch.delenv(key,raising=False)
    home=tmp_path/'synthetic-home';home.mkdir();monkeypatch.setenv('HOME',str(home));monkeypatch.setenv('CODEX_HOME',str(home/'codex'))
    real_exists=w.Path.exists
    monkeypatch.setattr(w.Path,'exists',lambda p:False if str(p)=='/var/run/docker.sock' else real_exists(p))
    async def quota(*a):return [dict(provider='openai',state_key='provider:openai',authoritative=True,available=True)]
    monkeypatch.setattr('app.quota_telemetry.CodexQuotaCollector.collect',quota)
    async def version(argv,**kwargs):
        assert argv==['codex','--version']
        return SimpleNamespace(returncode=0,stdout='codex-cli 0.160.0')
    monkeypatch.setattr('app.shell.run_command',version)
    choice=dict(id='codex_gpt6_luna',adapter='codex_cli',model='gpt-6-luna',reasoning_effort='medium')
    async def route(payload):return {'strategy':{'executor':choice}}
    engine=RuntimeEngine(s.db);engine.workspace_root=s.root;engine.router=SimpleNamespace(route=route)
    async def local_source_issue(*,issue_number):
        assert issue_number == task.issue_number
        return deepcopy(issue)
    github=SimpleNamespace(local_source_issue=local_source_issue);reader=w.TrustedReaders(engine,github)
    async def executor(self,endpoint,payload):
        assert endpoint=='/v1/pcp-local/observe'
        return dict(job_id=w.stable_job_id(task),source_commit=task.base_sha,activation_digest=w.digest(activation),
            isolation={**facts['isolation'],'current_main_sha':task.base_sha},
            provider={k:v for k,v in facts['provider'].items() if k in ('credential_scoped','github_token_in_agent','host_keyring_mounted','provider_network_reviewed')},
            publisher=dict(project_id='pcp-local',repository=q.REPOSITORY,executor_only=True,
                allow_create_pr=True,allow_merge=False,credential_in_agent=False))
    monkeypatch.setattr(w.TrustedReaders,'executor',executor)
    def no_model(*a,**kw):pytest.fail('ordinary registration must not invoke a model')
    monkeypatch.setattr('app.adapters.codex.CodexAdapter.run',no_model)
    queue=q.LocalSourceQueueStore(s.db);assert queue.record(task)
    reads=[]
    readers=reader.readers()
    def recorded(key):
        async def read(t):reads.append(key);return await readers[key](t)
        return read
    async def dispatch():return await engine.dispatch_pcp_local_once(issue_number=task.issue_number,
        github=github,readers={k:recorded(k) for k in w.OBSERVER_PARTS})
    async def restarted():
        fresh=RuntimeEngine(s.db);fresh.workspace_root=s.root;fresh.router=engine.router
        observed=w.TrustedReaders(fresh,github)
        return await fresh.dispatch_pcp_local_once(issue_number=task.issue_number,
            github=github,readers=observed.readers())
    return SimpleNamespace(s=s,task=task,id=w.stable_job_id(task),engine=engine,reader=reader,
        dispatch=dispatch,restarted=restarted,reads=reads,queue=queue,retained=retained,old_receipt=old_receipt,old_lease=old_lease)


def test_retained_A_to_ordinary_B_all_eight_readers_and_registrar(ordinary_B):
    import hashlib
    b=ordinary_B;s=b.s
    def files():return {str(p.relative_to(s.path)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in s.path.rglob('*') if p.is_file()}
    original_files=files()
    result=asyncio.run(b.dispatch())
    assert result['runtime_job_state']=='queued' and result['job_id']==b.id and result['model_calls']==0
    row=s.db.get(b.id)
    assert row['status']=='queued' and row['progress']['model_calls']==0
    assert set(row['checkpoint']['pcp_local_source']['observations'])==w.OBSERVER_PARTS
    assert len(b.reads)>=32 and set(b.reads)==w.OBSERVER_PARTS
    assert s.db.get(s.id)==b.retained and ownership(s.db)[0][0]==b.old_receipt[0]
    assert s.path.exists() and ownership(s.db)[1]==b.old_lease
    # The ordinary supported lease operation advances ownership; A is unchanged.
    lease=s.db.acquire_project_lease('pcp-local',b.id)
    assert lease['generation']==2 and lease['owner_job_id']==b.id and lease['state']=='active'
    assert s.db.acquire_project_lease('pcp-local',b.id)['generation']==2
    w.retained_workspaces(s.db,s.root,b.id)
    assert s.db.get(s.id)==b.retained
    with pytest.raises(TaskStop):asyncio.run(b.dispatch())  # queue/receipt already reserved
    assert s.db.get(b.id)==row and s.db.get(s.id)==b.retained and files()==original_files


@pytest.mark.parametrize('fault',['before_commit','lost_ack'])
def test_B_registration_crash_preserves_A_and_claim_without_replay(ordinary_B,monkeypatch,fault):
    b=ordinary_B;s=b.s;connect=s.db.connect
    class Wrapped:
        def __init__(self):self.conn=connect();self.insert=False
        def __enter__(self):self.conn.__enter__();return self
        def __exit__(self,*args):return self.conn.__exit__(*args)
        def execute(self,sql,params=None):
            if 'INSERT INTO cp_jobs' in sql:self.insert=True
            return self.conn.execute(sql,params)
        def commit(self):
            if self.insert and fault=='before_commit':raise RuntimeError('fixture rollback')
            self.conn.commit()
            if self.insert and fault=='lost_ack':raise RuntimeError('fixture acknowledgement lost')
    monkeypatch.setattr(s.db,'connect',Wrapped)
    with pytest.raises(TaskStop,match='launch_uncertain'):asyncio.run(b.dispatch())
    monkeypatch.setattr(s.db,'connect',connect)
    after=s.db.get(b.id);receipts,leases=ownership(s.db)
    claim=next(x for x in receipts if x['job_id']==b.id)
    assert (claim['state'],claim['generation'])==('claimed',1)
    assert (after is None)==(fault=='before_commit') and leases==b.old_lease
    assert s.db.get(s.id)==b.retained and next(x for x in receipts if x['job_id']==s.id)==b.old_receipt[0]
    # Ordinary restart does not reinsert/re-enqueue a consumed claim or reset it.
    assert asyncio.run(b.restarted())['status']=='PCP_LOCAL_QUEUE_IDLE_NOT_DISPATCHED'
    assert s.db.get(b.id)==after and ownership(s.db)==(receipts,leases)
    with pytest.raises(TaskStop):b.queue.advance(b.task,expected_state='pending',expected_generation=0,
        target_state='claimed',job_id=b.id,worker_authorized=True)
    assert s.db.get(s.id)==b.retained and ownership(s.db)==(receipts,leases)


def test_concurrent_ordinary_B_requests_register_once_and_preserve_A(ordinary_B):
    from concurrent.futures import ThreadPoolExecutor
    b=ordinary_B;s=b.s
    def attempt():
        try:return asyncio.run(b.restarted())
        except TaskStop as exc:return {'blocked':exc.code}
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(lambda _:attempt(),range(2)))
    assert sum(x.get('runtime_job_state')=='queued' for x in outcomes)==1, outcomes
    row=s.db.get(b.id);receipts,leases=ownership(s.db)
    assert row['status']=='queued' and row['progress']['model_calls']==0
    assert len(receipts)==2 and leases==b.old_lease and s.db.get(s.id)==b.retained
    assert asyncio.run(b.restarted())['status']=='PCP_LOCAL_QUEUE_IDLE_NOT_DISPATCHED'
    assert s.db.get(b.id)==row and ownership(s.db)==(receipts,leases)


@pytest.mark.parametrize('fault',['unknown','symlink','content','mode','git_alternate','git_worktree','git_monitor',
    'receipt','terminal_only','reserved','branch','review_diff','verification','baseline'])
def test_retained_A_rejection_preserves_history_and_blocks_B(ordinary_B,fault):
    b=ordinary_B;s=b.s
    if fault=='unknown':(s.root/('d'*32)).mkdir()
    elif fault=='symlink':(s.root/('d'*32)).symlink_to(s.path,target_is_directory=True)
    elif fault=='content':(s.path/'new.py').write_text('changed after finalization')
    elif fault=='mode':(s.path/'new.py').chmod(0o755)
    elif fault=='git_alternate':(s.path/'.git/objects/info/alternates').write_text('/synthetic/other/objects')
    elif fault=='git_worktree':(s.path/'.git/commondir').write_text('/synthetic/other/git')
    elif fault=='git_monitor':
        with (s.path/'.git/config').open('a') as out:out.write('\n[core]\nfsmonitor = /synthetic/not-executable\n')
    elif fault=='receipt':
        with s.db.connect() as c:c.execute("UPDATE cp_pcp_local_source_receipts SET generation=4 WHERE job_id=%s",(s.id,))
    elif fault=='terminal_only':s.db.update(s.id,result={})
    elif fault=='branch':s.db.update(s.id,branch='ai/foreign')
    elif fault in ('review_diff','verification'):
        result=deepcopy(s.db.get(s.id)['result'])
        if fault=='review_diff':result['review']['report']['diff_hash']='f'*64
        else:result['verification']['test_runs']=999
        s.db.update(s.id,result=result)
    elif fault=='baseline':
        cp=deepcopy(s.db.get(s.id)['checkpoint']);cp['project_baseline']['source_commit']='f'*40
        s.db.update(s.id,checkpoint=cp)
    else:
        with s.db.connect() as c:c.execute("UPDATE cp_project_leases SET state='active'")
    before=s.db.get(s.id);owners=ownership(s.db)
    with pytest.raises((TaskStop,KeyError)):asyncio.run(b.dispatch())
    assert s.db.get(s.id)==before and ownership(s.db)==owners and s.db.get(b.id) is None


def test_retained_row_race_is_not_promoted_to_fresh_proof(ordinary_B,monkeypatch):
    b=ordinary_B;s=b.s;snapshot=r.operation_snapshot;changed=False
    def racing(storage,job_id):
        nonlocal changed
        value=snapshot(storage,job_id)
        if not changed:
            changed=True
            s.db.update(s.id,progress={**value[0]['progress'],'model_calls':2})
        return value
    monkeypatch.setattr(r,'operation_snapshot',racing)
    with pytest.raises(TaskStop,match='retained_evidence_changed'):asyncio.run(b.dispatch())
    after=s.db.get(s.id)
    assert after['progress']['model_calls']==2 and after['checkpoint']==b.retained['checkpoint']
    assert s.db.get(b.id) is None and ownership(s.db)[1]==b.old_lease


def test_unrelated_blocked_receipt_without_workspace_still_blocks_B(ordinary_B):
    b=ordinary_B;s=b.s
    extra=replace(b.task,issue_number=b.task.issue_number+1,task_key='fixture-blocked')
    assert b.queue.record(extra)
    with s.db.connect() as conn:
        conn.execute("UPDATE cp_pcp_local_source_receipts SET state='blocked' WHERE issue_number=%s",(extra.issue_number,))
    before=ownership(s.db)
    with pytest.raises(TaskStop):asyncio.run(b.dispatch())
    assert s.db.get(b.id) is None and s.db.get(s.id)==b.retained
    assert next(r for r in ownership(s.db)[0] if r['issue_number']==extra.issue_number)==next(r for r in before[0] if r['issue_number']==extra.issue_number)


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


@pytest.mark.parametrize('delivery,attempts,expected,eligible', [
    ('ci_success',1,'awaiting_pm_review',False),
    ('ci_waiting',1,'ci_pending',False),
    ('uncertain',1,'reconcile_publication',False),
    ('missing',1,'reconcile_publication',False),
    ('missing',0,'delivery_needed',True),
    ('completed',1,'completed',False),
])
def test_delivery_readiness_distinguishes_health_from_eligibility(lifecycle,delivery,attempts,expected,eligible):
    s=lifecycle
    if delivery=='completed':
        asyncio.run(s.engine.finalize_pcp_local_review(SimpleNamespace(**view(s)['identity'])))
    else:
        row=s.db.get(s.id);result=deepcopy(row['result']);progress=deepcopy(row['progress'])
        if delivery=='missing':result.pop('delivery')
        else:
            result['delivery']['state']='publishing' if delivery=='uncertain' else delivery
            if delivery=='uncertain':result['delivery']['uncertain']=True
        result['acceptance_phase']='awaiting_independent_pm_review'
        progress['delivery_attempts']=attempts
        s.db.update(s.id,result=result,progress=progress)
    before=s.db.get(s.id);owners=ownership(s.db);reads=[]
    async def source():return s.v.task,{}
    async def refresh(task):
        assert task==s.v.task;reads.append('authoritative_dependency_checks')
    readers=SimpleNamespace(source=source,refresh_delivery=refresh)
    result=asyncio.run(r.collect_readiness(s.engine,readers,phase='delivery',job_id=s.id))
    assert result['dependencies_ready'] and result['ready'] is eligible
    assert result['operation']['state']==expected and result['operation']['eligible'] is eligible
    assert result['authorized'] is False
    if delivery=='ci_success':assert result['operation']['actor']=='PM'
    assert s.db.get(s.id)==before and ownership(s.db)==owners


def test_already_delivered_mutation_cannot_increment_or_publish(lifecycle,monkeypatch):
    s=lifecycle;before=s.db.get(s.id);owners=ownership(s.db)
    reader=object.__new__(w.TrustedReaders);reader.engine=s.engine
    async def refresh(self,task):pass
    monkeypatch.setattr(w.TrustedReaders,'refresh_delivery',refresh)
    with pytest.raises(TaskStop,match='pcp_local_delivery_already_complete'):
        asyncio.run(s.engine.deliver_pcp_local(s.id,reader,s.v.task))
    assert s.db.get(s.id)==before and ownership(s.db)==owners
