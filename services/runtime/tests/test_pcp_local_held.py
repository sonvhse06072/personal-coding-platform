"""Held verification against real Git/PostgreSQL, synthetic external authority."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import pytest
from app import pcp_local_recovery as h
from app import pcp_local_worker_loop as w
from app.engine import RuntimeEngine
from app.pcp_local_task_queue import TaskStop
from app.pcp_local_readiness import initialize_schema
from test_pcp_local_consolidation_postgres import database,seed,ownership
from test_pcp_local_consolidation import verified


@pytest.fixture
def held(database,verified,monkeypatch):
    db,v=database,verified
    v.task=replace(v.task,allowed_paths=('new.py',),baseline_source_commit=v.task.base_sha)
    row=v.store.row
    row['checkpoint']['pcp_local_source']['receipt']=w.claimed_source_receipt(v.task)
    row['checkpoint']['pcp_local_execution']={
        'state':'held','attempt':1,'lease_generation':1,'authority_digest':'a'*64}
    row['progress']={'model_calls':1,'test_runs':0,'delivery_attempts':0,'input_tokens':99,
        'agent_attempts':[{'returncode':0,'failure_kind':None,'adapter':'codex_cli','usage':{'input_tokens':99}}]}
    row['error']=h.ERROR
    # The production review path now requires immutable goal/baseline context.
    # Supply real fixture authority rather than bypassing Composer in delivery.
    import json
    from test_pcp_local_worker_loop import fixture as source_fixture
    goal=json.loads(source_fixture()[1]['body'].split('\n',1)[1])['goal']
    row['task']={'title':'Synthetic held task','description':goal}
    row['checkpoint']['project_baseline']=dict(project_id='pcp-local',revision=v.task.baseline_revision,
        source_commit=v.task.base_sha,status='approved',references={k:[dict(path='policy.md')] for k in
            ('goals','non_goals','requirements','architecture_constraints','quality_policy','security_policy','budget_policy','roadmap_frame')})
    seed(db,v)
    with db.connect() as c:
        c.execute('UPDATE cp_project_leases SET generation=2')
    cp=deepcopy(db.get(row['id'])['checkpoint']);cp['pcp_local_execution']['lease_generation']=2
    db.update(row['id'],checkpoint=cp)
    before=h.snapshot(db,SimpleNamespace(value={'before':{'job':row}}))
    att=dict(kind='independent_pm_legacy_returned',attempt=1,progress_sha256=h.digest(before['job']['progress']),
        returned_log_sha256='d'*64,shutdown_sha256='e'*64,returncode=0,provider_failed=False)
    permit=SimpleNamespace(value=dict(before=before,candidate=h.candidate(v.path,v.task),
        invocation_attestation=att,verification_seconds=60),task=v.task,sha256='b'*64,require_fresh=lambda:None)
    h.validate_eligibility(before,v.task,att)
    e=object.__new__(RuntimeEngine);e.storage=db;e._project_operation_locks={}
    reader=v.reader
    async def refresh(task):assert task==v.task
    reader.refresh_delivery=refresh
    reader.authority=lambda:({'ddev':{'enabled':True,'targeted_tests':['new.py'],'full_tests':['new.py']}},None)
    async def prepare(engine):return permit,reader
    monkeypatch.setattr(h,'prepare',prepare)
    calls=[]
    async def phase(**kw):
        calls.append(kw['phase'])
        import subprocess,sys
        r=subprocess.run([sys.executable,'-c',"exec(open('new.py').read()); assert answer==42; print('1 passed')"],cwd=v.path,capture_output=True,text=True)
        return {'passed':r.returncode==0,'commands':[dict(returncode=r.returncode,stdout=r.stdout,timed_out=False)]}
    e.ddev=SimpleNamespace(phase=phase)
    async def deliver(*args):calls.append('delivery')
    e.deliver_pcp_local=deliver
    async def forbidden(*a,**k):pytest.fail('developer model reached')
    monkeypatch.setattr('app.adapters.codex.CodexAdapter.run',forbidden)
    return SimpleNamespace(db=db,v=v,permit=permit,e=e,calls=calls)


def execute(s):
    return h.operate(s.e,apply=True,expected={'job_id':s.permit.value['before']['job']['id'],'permit_sha256':s.permit.sha256})


def test_held_plan_verify_commit_no_model(held):
    s=held;before=h.snapshot(s.db,s.permit)
    assert asyncio.run(h.operate(s.e))['ready']
    assert h.snapshot(s.db,s.permit)==before
    result=asyncio.run(execute(s));after=s.db.get(s.v.store.row['id'])
    assert result['state']=='verified_uncommitted'
    assert s.calls==['targeted_tests','full_tests','delivery']
    assert after['progress']['model_calls']==1 and after['progress']['test_runs']==2
    assert after['checkpoint']['pcp_local_execution']['state']=='verified'
    assert after['checkpoint'][h.HELD_KEY]['original']==before
    assert h.snapshot(s.db,s.permit)['receipt']==before['receipt']
    assert h.snapshot(s.db,s.permit)['lease']==before['lease']
    asyncio.run(execute(s));assert len(s.calls)==3


@pytest.mark.parametrize('drift',['mode','content','git_config','receipt','lease','progress','error','missing_attempt','expiry'])
def test_held_rejects_drift_before_tests(held,drift):
    s=held
    if drift=='mode':(s.v.path/'new.py').chmod(0o755)
    elif drift=='content':(s.v.path/'new.py').write_text('bad')
    elif drift=='git_config':s.v.git('config','core.fsmonitor','touch SHOULD_NEVER_EXIST')
    elif drift in ('receipt','lease'):
        with s.db.connect() as c:c.execute('UPDATE '+('cp_project_leases' if drift=='lease' else 'cp_pcp_local_source_receipts')+' SET generation=generation+1')
    elif drift=='expiry':
        def expired():raise TaskStop('held_authority_expired')
        s.permit.require_fresh=expired
    else:
        row=s.db.get(s.v.store.row['id'])
        if drift=='error':s.db.update(row['id'],error='other_error')
        else:
            progress=row['progress'];progress['model_calls']=2
            if drift=='missing_attempt':progress['agent_attempts']=[]
            s.db.update(row['id'],progress=progress)
    with pytest.raises(TaskStop):asyncio.run(execute(s))
    assert s.calls==[] and not (s.v.path/'SHOULD_NEVER_EXIST').exists()


def test_crash_after_test_intent_cannot_repeat(held,monkeypatch):
    s=held
    async def crash(*a,**k):raise ConnectionError('test result unknown')
    monkeypatch.setattr(s.e,'verify_pcp_local',crash)
    with pytest.raises(ConnectionError):asyncio.run(execute(s))
    assert asyncio.run(execute(s))['state']=='verifying'
    assert s.calls==[]


def test_failed_verifier_no_commit_or_model(held):
    s=held
    async def failed(**kw):
        s.calls.append(kw['phase']);return {'passed':False,'commands':[dict(returncode=1,stdout='1 failed',timed_out=False)]}
    s.e.ddev.phase=failed
    assert asyncio.run(execute(s))['state']=='verification_failed'
    assert s.calls==['targeted_tests'] and s.v.git('rev-parse','HEAD')==s.v.task.base_sha
    assert s.db.get(s.v.store.row['id'])['progress']['test_runs']==1
    asyncio.run(execute(s));assert len(s.calls)==1


def test_concurrent_full_row_cas_only_one_verifier(held):
    from concurrent.futures import ThreadPoolExecutor
    s=held;before=h.snapshot(s.db,s.permit)
    def claim():
        try:return h.transition(s.db,s.permit,before,state='verifying')['job']['id']
        except TaskStop:return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:claim(),range(2)))
    assert sorted(results)==sorted([before['job']['id'],'stale'])
    assert h.snapshot(s.db,s.permit)['receipt']==before['receipt']


@pytest.mark.parametrize('fault',['rollback','lost_ack'])
def test_intent_transaction_ack_reconciliation(held,monkeypatch,fault):
    s=held;before=h.snapshot(s.db,s.permit);connect=s.db.connect
    class Wrapped:
        def __enter__(self):self.c=connect();return self
        def __exit__(self,*a):return self.c.__exit__(*a)
        def execute(self,sql,params=None):return self.c.execute(sql,params)
        def commit(self):
            if fault=='lost_ack':self.c.commit()
            raise ConnectionError('synthetic commit acknowledgement')
    monkeypatch.setattr(s.db,'connect',Wrapped)
    with pytest.raises(ConnectionError):h.transition(s.db,s.permit,before,state='verifying')
    monkeypatch.setattr(s.db,'connect',connect)
    state=h.classify(h.snapshot(s.db,s.permit),s.permit)
    assert state==('verifying' if fault=='lost_ack' else 'eligible')
    assert s.calls==[]


def test_partial_verification_is_durable_and_never_replayed(held):
    s=held;original=s.e.ddev.phase
    async def phase(**kw):
        if kw['phase']=='full_tests':raise ConnectionError('unknown full phase')
        return await original(**kw)
    s.e.ddev.phase=phase
    with pytest.raises(ConnectionError):asyncio.run(execute(s))
    row=s.db.get(s.v.store.row['id'])
    assert row['progress']['test_runs']==1
    assert row['checkpoint'][h.HELD_KEY]['phases'][0]['result']['passed']
    assert row['checkpoint'][h.HELD_KEY]['phases'][1]['result'] is None
    assert asyncio.run(execute(s))['state']=='verifying'
    assert s.calls==['targeted_tests']


@pytest.mark.parametrize('kind',['hook','hardlink','symlink','index','worktree_config'])
def test_candidate_rejects_unsafe_reads_and_commands(held,kind):
    s=held
    if kind=='hook':
        hook=s.v.path/'.git/hooks/pre-commit';hook.write_text('#!/bin/sh\ntouch '+str(s.v.path/'BAD'));hook.chmod(0o755)
    elif kind=='hardlink':
        import os
        os.link(s.v.path/'original',s.v.path/'linked')
    elif kind=='symlink':(s.v.path/'escape').symlink_to('/etc/passwd')
    elif kind=='index':s.v.git('update-index','--assume-unchanged','original')
    else:(s.v.path/'.git/config.worktree').write_text('[core]\nfsmonitor = touch BAD\n')
    with pytest.raises(TaskStop):asyncio.run(execute(s))
    assert s.calls==[] and not (s.v.path/'BAD').exists()


def test_drift_after_targeted_result_blocks_checkpoint(held):
    s=held;original=s.e.ddev.phase
    async def phase(**kw):
        r=await original(**kw)
        if kw['phase']=='full_tests':(s.v.path/'new.py').write_text('answer=43')
        return r
    s.e.ddev.phase=phase
    with pytest.raises(TaskStop,match='candidate_drift'):asyncio.run(execute(s))
    row=s.db.get(s.v.store.row['id'])
    assert row['progress']['test_runs']==2 and 'verified_tree' not in row['checkpoint']['pcp_local_execution']
    assert 'delivery' not in s.calls and s.v.git('rev-parse','HEAD')==s.v.task.base_sha


@pytest.fixture
def private_permit(held,tmp_path,monkeypatch):
    import json,time,hashlib
    s=held;p=s.permit
    original={k:getattr(p.task,k) for k in ('issue_number','base_sha','body_sha256','baseline_revision','baseline_source_commit')}
    original.update(verification_image='sha256:'+'1'*64,runtime_image_id='sha256:'+'1'*64)
    original_path=tmp_path/'original.json';original_path.write_text(json.dumps(original));original_path.chmod(0o600)
    p.value.update(version=1,decision_id='fixture-held-verification',
        execution_record='https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-1',
        not_before=time.time()-1,expires_at=time.time()+600,
        original_activation_sha256=hashlib.sha256(original_path.read_bytes()).hexdigest(),
        repair_source='c'*40,repair_commits=['c'*40],repair_paths=['services/runtime/app/pcp_local_held.py'],
        roles={role:dict(image_id='sha256:'+str(i)*64,source_commit='c'*40 if role in ('runtime','executor') else p.task.base_sha,
            **({} if role=='verifier' else dict(configuration_sha256='d'*64)))
            for i,role in enumerate(('verifier','runtime','executor','router'),1)})
    path=tmp_path/'permit.json'
    def save():path.write_text(h.canonical(p.value));path.chmod(0o600)
    save();monkeypatch.setattr(h,'HELD_PERMIT',path);monkeypatch.setattr(h,'HELD_ORIGINAL',original_path)
    monkeypatch.setenv('PCP_LOCAL_HELD_VERIFY_ENABLED','owner-approved')
    return s,path,original_path,save


@pytest.mark.parametrize('change',['none','expiry','usage','missing_log','failed_invocation','verifier','image_label','hardlink','symlink','duplicate','revoke'])
def test_private_authority_full_preimage_and_revocation(private_permit,change):
    import os,time
    s,path,original,save=private_permit
    if change=='none':
        p=h.HeldPermit();assert p.task==s.v.task and p.value['before']==s.permit.value['before'];return
    if change=='expiry':s.permit.value['expires_at']=time.time()-10
    elif change=='usage':s.permit.value['before']['job']['progress']['input_tokens']+=1
    elif change=='missing_log':s.permit.value['invocation_attestation'].pop('returned_log_sha256')
    elif change=='failed_invocation':s.permit.value['before']['job']['progress']['agent_attempts'][0]['returncode']=1
    elif change=='verifier':s.permit.value['roles']['verifier']['image_id']='sha256:'+'9'*64
    elif change=='image_label':s.permit.value['roles']['runtime']['source_commit']=s.v.task.base_sha
    save()
    if change=='hardlink':os.link(path,path.with_suffix('.link'))
    elif change=='symlink':
        path.rename(path.with_suffix('.original'));path.symlink_to(path.with_suffix('.original'))
    elif change=='duplicate':path.write_text(path.read_text()[:-1]+',"version":1}')
    elif change=='revoke':
        p=h.HeldPermit();s.permit.value['decision_id']='different-decision';save()
        with pytest.raises(TaskStop):p.require_fresh()
        return
    with pytest.raises(TaskStop):h.HeldPermit()


def test_commit_lost_ack_reconciles_without_testing_again(held,monkeypatch):
    from app import repo
    from app.pcp_local_recovery import recover_verified_job
    s=held;original=repo.commit_changes
    def lost(*a,**kw):original(*a,**kw);raise ConnectionError('commit acknowledgement lost')
    monkeypatch.setattr(repo,'commit_changes',lost)
    with pytest.raises(ConnectionError):asyncio.run(execute(s))
    row=s.db.get(s.v.store.row['id']);assert row['checkpoint']['pcp_local_execution']['state']=='commit_uncertain'
    monkeypatch.setattr(repo,'commit_changes',lambda *a,**k:pytest.fail('duplicate commit'))
    recovered=asyncio.run(recover_verified_job(s.e,s.v.reader,s.v.task,row))
    assert recovered['checkpoint']['pcp_local_execution']['state']=='verified'
    assert s.calls==['targeted_tests','full_tests']
    assert recovered['progress']['model_calls']==1 and recovered['progress']['test_runs']==2


def test_cross_process_operation_lock_rejects_parallel_side_effects(held):
    s=held
    with h.operation_lock(s.db):
        with pytest.raises(TaskStop,match='operation_busy'):
            with h.operation_lock(s.db):pytest.fail('second process entered')
    with h.operation_lock(s.db):pass


@pytest.mark.parametrize('lost_ack',[False,True])
def test_actual_delivery_path_reconciles_synthetic_remote_without_model(held,monkeypatch,lost_ack):
    from app.delivery import DeliveryError
    from app.pcp_local_task_queue import REPOSITORY
    s=held;del s.e.deliver_pcp_local
    reader=object.__new__(w.TrustedReaders);reader.engine=s.e;reader.authority_digest='a'*64
    reader.route=s.v.store.row['route'];reader.activation={'budget':{'max_wall_seconds':900}}
    async def refresh(task):h.classify(h.snapshot(s.db,s.permit),s.permit)
    reader.refresh_delivery=refresh
    project={'ddev':{'enabled':True,'targeted_tests':['new.py'],'full_tests':['new.py']},
        'autonomy':dict(allow_commit=True,allow_push_ai_branch=True,allow_create_pr=True,allow_production_deploy=False)}
    reader.authority=lambda:(project,None)
    async def prepare(e):return s.permit,reader
    monkeypatch.setattr(h,'prepare',prepare)
    remote={};calls=[]
    def ci(commit):return dict(state='success',repository=REPOSITORY,commit=commit,
        actions_runs=[dict(source='github_actions',run_id=9,id=9,head_sha=commit,name='tests',status='completed',conclusion='success',
            details_url='https://github.com/'+REPOSITORY+'/actions/runs/9')])
    async def publish(**kw):calls.append('publish');remote['commit']=kw['expected_commit'];return {'commit':remote['commit']}
    async def pr(**kw):
        calls.append('pr');remote['pr']=dict(number=7,head=kw['expected_commit'],head_ref=kw['branch'],base_ref='main',repository=REPOSITORY,state='open',merged=False)
        if lost_ack:raise ConnectionError('synthetic PR acknowledgement lost')
        return remote['pr']
    async def checks(**kw):calls.append('ci');return ci(kw['commit'])
    async def reconcile(**kw):
        calls.append('reconcile');assert kw['expected_commit']==remote['commit']
        return dict(reconciled=True,delivery={**remote['pr'],'ci':ci(remote['commit'])})
    s.e.ddev.publish_branch=publish;s.e.ddev.upsert_pull_request=pr;s.e.ddev.github_ci=checks;s.e.ddev.github_reconcile_delivery=reconcile
    if lost_ack:
        with pytest.raises(DeliveryError):asyncio.run(execute(s))
        asyncio.run(s.e.deliver_pcp_local(s.v.store.row['id'],reader,s.v.task))
        assert calls==['publish','pr','reconcile']
    else:
        asyncio.run(execute(s));assert calls==['publish','pr','ci']
    row=s.db.get(s.v.store.row['id'])
    assert row['progress']['model_calls']==1 and row['progress']['test_runs']==2
    assert row['progress']['delivery_attempts']==(2 if lost_ack else 1)
    assert row['result']['delivery']['state']=='ci_success' and not row['result']['delivery_finalized']
    with pytest.raises(TaskStop,match='already_complete'):
        asyncio.run(s.e.deliver_pcp_local(row['id'],reader,s.v.task))


from test_pcp_local_repeatability import lifecycle, ordinary_B  # noqa:F401,E402
from test_pcp_local_runtime_dispatch import setup  # noqa:F401,E402
from pcp_sparse_fixture import sparse_verified  # noqa:F401,E402


@pytest.mark.parametrize('recovery_kind,lost_ack',[('config',False),('artifact',False),('artifact',True)])
def test_completed_A_ordinary_B_readers_to_held_verification(ordinary_B,monkeypatch,recovery_kind,lost_ack):
    """Original all-eight/registrar path followed by non-provider recovery readers."""
    import subprocess
    b=ordinary_B;s=b.s
    a_before=s.db.get(s.id);manifest=w._retained_snapshot(s.path)
    asyncio.run(b.dispatch());assert set(b.reads)==w.OBSERVER_PARTS
    row=s.db.get(b.id)
    b.queue.advance(b.task,expected_state='claimed',expected_generation=1,target_state='running',job_id=b.id,worker_authorized=True)
    lease=s.db.acquire_project_lease('pcp-local',b.id);assert lease['generation']==2
    path=s.root/b.id
    subprocess.run(['git','clone','--no-hardlinks',str(s.path),str(path)],check=True,capture_output=True)
    def git(*args):return subprocess.check_output(['git','-C',str(path),*args],text=True).strip()
    git('checkout','-B','ai/'+b.id[:12],b.task.base_sha);git('config','user.name','PCP Local');git('config','user.email','pcp-local@localhost')
    # Synthetic edits from the fixture's returned invocation, not a real model.
    changed=next(p for p in b.task.allowed_paths if p.startswith('tests/'))
    file=path/changed;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('def test_answer(): assert 2+2==4\n')
    cp=deepcopy(row['checkpoint']);cp['pcp_local_execution']=dict(state='held',attempt=1,lease_generation=2,authority_digest=b.reader.authority_digest)
    progress={**row['progress'],'model_calls':1,'test_runs':0,'agent_attempts':[dict(returncode=0,failure_kind=None,adapter='codex_cli',usage={})]}
    if recovery_kind=='artifact':
        returned=dict(attempt=1,returncode=0,model_calls=1,provider_failed=False,usage_digest=h.digest({}))
        cp['pcp_local_execution'].update(held_from='invocation_returned',returned_invocation=returned)
        output=path/'synthetic-output';output.mkdir();(output/'data').write_text('preserve output')
        (output/'current').symlink_to('data')
        from app.repo import diff_state
        diff_state(path,750000,base_ref=b.task.base_sha)
    s.db.update(b.id,status='blocked',error='pcp_local_changed_paths_denied' if recovery_kind=='artifact' else h.ERROR,
        workspace=str(path),branch='ai/'+b.id[:12],checkpoint=cp,progress=progress,route=b.reader.route)
    before=h.snapshot(s.db,SimpleNamespace(value={'before':{'job':{'id':b.id}}}))
    att=dict(kind='independent_pm_legacy_returned',attempt=1,progress_sha256=h.digest(before['job']['progress']),returned_log_sha256='d'*64,shutdown_sha256='e'*64,returncode=0,provider_failed=False)
    if recovery_kind=='artifact':
        from app import pcp_local_artifacts as artifacts
        att=dict(kind='durable_returned',progress_sha256=h.digest(before['job']['progress']),returned_invocation_sha256=h.digest(returned))
        plan=artifacts.make_plan(path,b.task,output.name,dict(kind='independent_pm_inventory',evidence_sha256='d'*64))
        candidate=plan['candidate']
    else:candidate=h.candidate(path,b.task)
    h.validate_eligibility(before,b.task,att,artifact=recovery_kind=='artifact')
    permit=SimpleNamespace(task=b.task,sha256='f'*64,value=dict(before=before,candidate=candidate,invocation_attestation=att,verification_seconds=60),require_fresh=lambda:None)
    if recovery_kind=='artifact':permit.value.update(version=2,artifact_plan=plan)
    b.reader.lease_generation=2
    # Actual phase-aware readers now avoid quota/Router/version and retain A.
    def forbidden(*a,**k):pytest.fail('provider or model reached during held verification')
    monkeypatch.setattr('app.quota_telemetry.CodexQuotaCollector.collect',forbidden)
    monkeypatch.setattr('app.adapters.codex.CodexAdapter.run',forbidden)
    # A stopped/restarted dedicated Runtime has no in-memory registrar queue.
    # Never clear/replay the old process queue to make a continuation eligible.
    b.engine=RuntimeEngine(s.db);b.engine.workspace_root=s.root
    b.engine.router=SimpleNamespace(route=forbidden)
    # Exercise actual prepare/readiness/HTTP entrypoints. Private authority and
    # GitHub/Executor transports are synthetic; file parsing/range checks have
    # separate real-file/Git regressions above and in Executor.
    from app.pcp_local_task_queue import verify_issue
    permit.verify_issue=lambda issue:verify_issue(issue,**{k:getattr(b.task,k) for k in
        ('issue_number','body_sha256','base_sha','baseline_revision','baseline_source_commit')})
    if recovery_kind=='artifact':
        monkeypatch.setattr(h,'ArtifactPermit',lambda:permit)
        monkeypatch.setenv('PCP_LOCAL_ARTIFACT_RECOVERY_ENABLED','owner-approved')
        monkeypatch.delenv('PCP_LOCAL_HELD_VERIFY_ENABLED',raising=False)
    else:
        monkeypatch.setattr(h,'HeldPermit',lambda:permit)
        monkeypatch.setenv('PCP_LOCAL_HELD_VERIFY_ENABLED','owner-approved')
    monkeypatch.setattr('app.pm_bridge.PMBridgeGitHubClient',lambda:b.reader.github)
    async def phase(**kw):
        import sys
        result=subprocess.run([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',changed],cwd=path,capture_output=True,text=True)
        return dict(passed=result.returncode==0,commands=[dict(returncode=result.returncode,stdout=result.stdout)])
    b.engine.ddev=SimpleNamespace(phase=phase)
    async def delivered(*a):pass
    if recovery_kind!='artifact':b.engine.deliver_pcp_local=delivered
    else:
        # Actual review-context/publication handoff, only the external remote is synthetic.
        remote={};publications=[]
        async def publish(**kw):publications.append('publish');return dict(commit=kw['expected_commit'])
        async def pr(**kw):
            assert before['job']['task']['description'] in kw['body']
            assert '/blob/'+b.task.baseline_source_commit+'/policy.md' in kw['body']
            assert 'UNRESOLVED' in kw['body']
            publications.append('pr');remote.update(number=7,head=kw['expected_commit'],head_ref=kw['branch'],base_ref='main',repository=b.task.repository,state='open',merged=False)
            if lost_ack:raise ConnectionError('synthetic PR acknowledgement lost')
            return remote
        async def checks(**kw):return dict(state='success',repository=b.task.repository,commit=kw['commit'],actions_runs=[dict(
            source='github_actions',run_id=9,id=9,head_sha=kw['commit'],name='tests',status='completed',conclusion='success',
            details_url='https://github.com/'+b.task.repository+'/actions/runs/9')])
        b.engine.ddev.publish_branch=publish;b.engine.ddev.upsert_pull_request=pr;b.engine.ddev.github_ci=checks
        async def reconcile(**kw):
            publications.append('reconcile');assert kw['expected_commit']==remote['head']
            return dict(reconciled=True,delivery={**remote,'ci':await checks(commit=remote['head'])})
        b.engine.ddev.github_reconcile_delivery=reconcile
    import httpx
    from app import main,pcp_local_readiness
    monkeypatch.setattr(main,'engine',b.engine)
    monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE','pcp_local_worker')
    monkeypatch.setenv('RUNTIME_API_TOKEN','fixture-held-token')
    monkeypatch.setattr(main.app.state,'pcp_local_worker_ready',True,raising=False)
    async def operator():
        before=h.snapshot(s.db,permit)
        ready=await pcp_local_readiness.collect_readiness(b.engine,phase='held-verification',job_id=b.id)
        assert ready['ready'],ready
        assert not ready['authorized'] and h.snapshot(s.db,permit)==before
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test',
                headers={'Authorization':'Bearer fixture-held-token'}) as client:
            plan=await client.get('/v1/pcp-local/held-verification')
            assert plan.status_code==200 and plan.json()['ready']
            expected={k:plan.json()[k] for k in ('job_id','permit_sha256')}
            assert (await client.post('/v1/pcp-local/held-verification',json={})).status_code==422
            if lost_ack:
                from app.delivery import DeliveryError
                with pytest.raises(DeliveryError):await client.post('/v1/pcp-local/held-verification',json=expected)
                observed=await client.get('/v1/pcp-local/held-verification')
                assert not observed.json()['ready']
                result=await client.post('/v1/pcp-local/deliver')
                assert result.status_code==200,result.text
                assert publications==['publish','pr','reconcile']
            else:
                result=await client.post('/v1/pcp-local/held-verification',json=expected)
                assert result.status_code==200,result.text
                assert result.json()['state']=='verified_uncommitted'
            assert (await client.post('/v1/pcp-local/run-once')).status_code==403
            again=await client.post('/v1/pcp-local/held-verification',json=expected)
            assert again.status_code==200 and not again.json()['ready']
    asyncio.run(operator())
    assert s.db.get(s.id)==a_before and w._retained_snapshot(s.path)==manifest
    assert s.db.get(b.id)['progress']['model_calls']==1 and s.db.get(b.id)['progress']['test_runs']==2


@pytest.mark.parametrize('expected',[None,{'job_id':'f'*32,'permit_sha256':'b'*64},
    {'job_id':'f'*32,'permit_sha256':'c'*64}])
def test_apply_requires_exact_observed_request_identity(held,expected):
    s=held;before=h.snapshot(s.db,s.permit)
    if expected is not None and expected['permit_sha256']=='c'*64:
        expected={**expected,'job_id':before['job']['id']}
    with pytest.raises(TaskStop,match='request_identity_changed'):
        asyncio.run(h.operate(s.e,apply=True,expected=expected))
    assert h.snapshot(s.db,s.permit)==before and s.calls==[]


@pytest.mark.parametrize('field,value',[('model_calls',0),('test_runs',0),('elapsed_minutes',0),('required_checks_passed',False)])
def test_verified_counter_drift_blocks_delivery(held,field,value):
    s=held;asyncio.run(execute(s))
    row=s.db.get(s.v.store.row['id']);row['progress'][field]=value
    s.db.update(row['id'],progress=row['progress'])
    with pytest.raises(TaskStop,match='held_verified_'):
        h.classify(h.snapshot(s.db,s.permit),s.permit)


def test_held_recording_is_visible_as_assisted_recovery(held):
    from app.dashboard_local import build_local_snapshot
    s = held
    asyncio.run(execute(s))
    before = h.snapshot(s.db, s.permit)
    view = build_local_snapshot(s.db)
    assert view['observation'] == 'available'
    job = next(j for j in view['jobs'] if j['id'] == before['job']['id'])
    assert job['assisted_recovery'] is True
    assert h.snapshot(s.db, s.permit) == before
