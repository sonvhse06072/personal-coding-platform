"""Real Git/PostgreSQL/verifier, synthetic remote authority; no model/live job."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import hashlib
import subprocess
import sys
from types import SimpleNamespace
import pytest
from app import pcp_local_review_repair as repair, pcp_local_recovery as h, pcp_local_worker_loop as w
from app.engine import RuntimeEngine
from app.pcp_local_task_queue import TaskStop, REPOSITORY
from app.repo import diff_state,commit_changes
from test_pcp_local_consolidation import verified  # noqa:F401
from test_pcp_local_consolidation_postgres import database,seed,ownership  # noqa:F401
TARGET='tests/test_pcp_light_repair.py'


def ci(head,success=True):
    return dict(state='success' if success else 'failure',failure_class=None if success else 'engineering',repository=REPOSITORY,commit=head,actions_runs=[dict(
        source='github_actions',run_id=9,id=9,head_sha=head,name='tests',status='completed',conclusion='success' if success else 'failure',details_url=f'https://github.com/{REPOSITORY}/actions/runs/9')])


@pytest.fixture
def local_repair(database,verified,monkeypatch):
    db,v=database,verified;v.task=replace(v.task,allowed_paths=('new.py',TARGET),baseline_source_commit=v.task.base_sha)
    old=v.path;root=old.parent/(old.name+'-jobs');root.mkdir();v.path=root/w.stable_job_id(v.task)
    old.rename(v.path);old.mkdir();v.git=lambda *args:h.git(v.path,*args);v.store.row['workspace']=str(v.path)
    path=v.path/TARGET;path.parent.mkdir();path.write_text('def test_answer(): assert 6 * 7 == 42\n')
    row=v.store.row;row['checkpoint']['pcp_local_source']['receipt']=w.claimed_source_receipt(v.task)
    diff=diff_state(v.path,750000,base_ref=v.task.base_sha);proof=row['checkpoint']['pcp_local_execution']
    proof.update(diff=diff,verified_tree=h.verified_tree(v.path,v.task,diff),lease_generation=4)
    commit_changes(v.path,'original verified task');head=v.git('rev-parse','HEAD');proof.update(state='verified',commit=head)
    row.update(error='pcp_local_hosted_ci_not_passed',progress=dict(model_calls=1,test_runs=2,delivery_attempts=1,input_tokens=99,
        agent_attempts=[dict(adapter='codex_cli',returncode=0,usage={'input_tokens':99})],required_checks_passed=True))
    baseline=dict(project_id='pcp-local',revision=v.task.baseline_revision,source_commit=v.task.base_sha,status='approved',references={k:[dict(path='policy.md')] for k in (
        'goals','non_goals','requirements','architecture_constraints','quality_policy','security_policy','budget_policy','roadmap_frame')})
    row['checkpoint']['project_baseline']=baseline
    row['checkpoint']['canonical_intake']=dict(mode='direct',bounded_direct=True)
    from test_pcp_local_worker_loop import fixture as source_fixture
    row['task']=dict(title='Fixture exact test repair',description=json.loads(source_fixture()[1]['body'].split('\n',1)[1])['goal'])
    remote=dict(number=7,head=head,head_ref=row['branch'],base_ref='main',repository=REPOSITORY,state='open',merged=False)
    row['result']=dict(status='accepted',branch=row['branch'],commit=head,diff=diff,verification=proof['verification'],route=row['route'],delivery_finalized=False,
        delivery=dict(state='ci_failure',pull_request=deepcopy(remote),ci=ci(head,False)))
    seed(db,v)
    with db.connect() as c:c.execute('UPDATE cp_project_leases SET generation=4')
    before=h.snapshot(db,SimpleNamespace(value={'before':{'job':row}}));row=before['job']
    patch=b'--- a/tests/test_pcp_light_repair.py\n+++ b/tests/test_pcp_light_repair.py\n@@ -1 +1,2 @@\n def test_answer(): assert 6 * 7 == 42\n+def test_commutative(): assert 7 * 6 == 42\n'
    plan,_=repair.make_patch_plan(row,v.task,patch,TARGET)
    p=SimpleNamespace(value=dict(before=before,expected_head=head,pr_number=7,patch_plan=plan,verification_seconds=60,review_id=80,review_body_sha256=hashlib.sha256(b'Independent fixture finding').hexdigest()),task=v.task,patch=patch,sha256='b'*64,require_fresh=lambda:None)
    repair.eligibility(p.value,p.task)
    e=object.__new__(RuntimeEngine);e.storage=db;e._project_operation_locks={};e.workspace_root=v.path.parent
    project=dict(ddev=dict(enabled=True,targeted_tests=[TARGET],full_tests=[TARGET]),autonomy=dict(allow_commit=True,allow_push_ai_branch=True,allow_create_pr=True,allow_production_deploy=False))
    reader=object.__new__(w.TrustedReaders);reader.engine=e;reader.authority_digest='a'*64;reader.route=row['route'];reader.local_review=p
    reader.activation={k:getattr(v.task,k) for k in ('issue_number','body_sha256','base_sha','baseline_revision','baseline_source_commit')}
    reader.activation['budget']={'max_wall_seconds':900};reader.activation['pm_login']='fixture-reviewer'
    p.activation=reader.activation
    reader.authority=lambda:(project,SimpleNamespace(revision=v.task.baseline_revision,model_dump=lambda **kw:deepcopy(baseline)))
    async def refresh(task):assert task==v.task;repair.classify(repair.snapshot(db,p),p)
    reader.refresh_delivery=refresh
    async def prepare(engine):assert engine is e;return p,reader
    monkeypatch.setattr(repair,'prepare',prepare)
    calls=[];published=[]
    async def phase(**kw):
        calls.append(kw['phase']);r=subprocess.run([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',TARGET],cwd=v.path,capture_output=True,text=True,timeout=20)
        return dict(passed=r.returncode==0,commands=[dict(returncode=r.returncode,stdout=r.stdout,timed_out=False)])
    async def pr_read(**kw):assert kw==dict(project_id='pcp-local',pr_number=7);return deepcopy(remote)
    async def review_read(**kw):return dict(id=80,pr_number=7,repository=REPOSITORY,commit_id=head,author='fixture-reviewer',state='COMMENTED',body='Independent fixture finding')
    async def checks(**kw):return ci(kw['commit'],kw['commit']!=head)
    async def publish(**kw):
        assert kw['review_repair_pr_number']==7 and kw['review_repair_previous_commit']==head
        assert v.git('show','-s','--format=%P','HEAD').split()==[head]
        published.append(kw['expected_commit']);remote['head']=kw['expected_commit'];calls.append('publish');return dict(commit=remote['head'])
    async def upsert(**kw):assert kw['expected_pr_number']==7;calls.append('pr');return deepcopy(remote)
    async def reconcile(**kw):return dict(reconciled=False)
    e.ddev=SimpleNamespace(phase=phase,github_pull_request=pr_read,github_pull_request_review=review_read,github_ci=checks,publish_branch=publish,upsert_pull_request=upsert,github_reconcile_delivery=reconcile)
    async def forbidden(*a,**k):pytest.fail('developer model reached')
    monkeypatch.setattr('app.adapters.codex.CodexAdapter.run',forbidden)
    return SimpleNamespace(db=db,v=v,p=p,e=e,reader=reader,before=before,calls=calls,remote=remote,published=published)


def execute(s):return repair.operate(s.e,apply=True,expected=dict(job_id=s.before['job']['id'],permit_sha256=s.p.sha256,expected_head=s.p.value['expected_head'],pr_number=7,patch_sha256=s.p.value['patch_plan']['patch_sha256']))


def test_copied_repair_through_same_pr_and_latest_proof(local_repair):
    s=local_repair;before=deepcopy(s.before);assert asyncio.run(repair.operate(s.e))['ready'];assert repair.snapshot(s.db,s.p)==before
    outcome=asyncio.run(execute(s));after=repair.snapshot(s.db,s.p);j=after['job']
    assert outcome['state']=='awaiting_pm_review' and s.calls==['targeted_tests','full_tests','publish','pr']
    assert [j['progress'][k] for k in ('model_calls','test_runs','delivery_attempts')]==[1,4,2]
    assert j['checkpoint'][repair.KEY]['original']==before and j['checkpoint']['pcp_local_execution']['verified_tree']['parent']==before['job']['result']['commit']
    assert h.reconcile_commit(j,s.v.task)==j['result']['commit']!=before['job']['result']['commit']
    assert after['receipt']==before['receipt'] and after['lease']==before['lease']
    assert j['result']['delivery']['pull_request']['number']==7 and j['result']['delivery']['state']=='ci_success'
    assert j['progress']['agent_attempts']==before['job']['progress']['agent_attempts'];asyncio.run(execute(s));assert len(s.calls)==4


@pytest.mark.parametrize('kind',['row','receipt','lease','patch_path','patch_hash','remote_head','mode','content','config','index','worktree_config','hook'])
def test_repair_rejects_preflight_drift_before_mutation(local_repair,kind):
    s=local_repair
    if kind=='row':s.db.update(s.before['job']['id'],error='new drift')
    elif kind in ('receipt','lease'):
        with s.db.connect() as c:c.execute('UPDATE '+('cp_project_leases' if kind=='lease' else 'cp_pcp_local_source_receipts')+' SET generation=generation+1')
    elif kind=='patch_path':s.p.value['patch_plan']['path']='../escape'
    elif kind=='patch_hash':s.p.patch+=b'\n'
    elif kind=='remote_head':s.remote['head']='e'*40
    elif kind=='mode':(s.v.path/TARGET).chmod(0o755)
    elif kind=='content':(s.v.path/TARGET).write_text('changed')
    elif kind=='config':s.v.git('config','core.fsmonitor','touch BAD')
    elif kind=='index':s.v.git('update-index','--assume-unchanged',TARGET)
    elif kind=='worktree_config':(s.v.path/'.git/config.worktree').write_text('[core]\nfsmonitor = touch BAD\n')
    else:
        p=s.v.path/'.git/hooks/pre-commit';p.write_text('#!/bin/sh\ntouch '+str(s.v.path/'BAD'));p.chmod(0o755)
    with pytest.raises((TaskStop,OSError,subprocess.SubprocessError)):asyncio.run(execute(s))
    assert s.calls==[] and not (s.v.path/'BAD').exists();assert s.v.git('rev-parse','HEAD')==s.p.value['expected_head']


def test_unknown_verification_never_replays(local_repair):
    s=local_repair
    async def unknown(**kw):s.calls.append(kw['phase']);raise ConnectionError('unknown verifier')
    s.e.ddev.phase=unknown
    with pytest.raises(ConnectionError):asyncio.run(execute(s))
    assert asyncio.run(execute(s))['state']=='verifying' and s.calls==['targeted_tests']
    assert s.db.get(s.before['job']['id'])['progress']['test_runs']==2


@pytest.mark.parametrize('fault',['patch_after','commit_after','pr_after'])
def test_lost_ack_reconciliation_no_test_or_write_replay(local_repair,monkeypatch,fault):
    s=local_repair
    if fault=='patch_after':
        actual=repair.write_patch
        def once(*a):actual(*a);raise ConnectionError('patch acknowledgement')
        monkeypatch.setattr(repair,'write_patch',once)
    elif fault=='commit_after':
        from app import repo
        actual=repo.commit_changes
        def once(*a):actual(*a);raise ConnectionError('commit acknowledgement')
        monkeypatch.setattr(repo,'commit_changes',once)
    else:
        actual=s.e.ddev.upsert_pull_request
        async def once(**kw):await actual(**kw);raise ConnectionError('PR acknowledgement')
        s.e.ddev.upsert_pull_request=once
    with pytest.raises(Exception):asyncio.run(execute(s))
    if fault=='patch_after':monkeypatch.setattr(repair,'write_patch',lambda *a:pytest.fail('patch replay'))
    if fault=='commit_after':monkeypatch.setattr('app.repo.commit_changes',lambda *a:pytest.fail('commit replay'))
    outcome=asyncio.run(execute(s));assert outcome['state']=='awaiting_pm_review' and s.calls==['targeted_tests','full_tests','publish','pr']
    assert len(s.published)==1 and [s.db.get(s.before['job']['id'])['progress'][k] for k in ('model_calls','test_runs','delivery_attempts')]==[1,4,2]


def test_concurrent_intent_full_row_cas(local_repair):
    from concurrent.futures import ThreadPoolExecutor
    s=local_repair
    def claim():
        try:repair.transition(s.db,s.p,s.before,'patch_intent');return 'intent'
        except TaskStop:return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(lambda _:claim(),range(2)))==['intent','stale']
    assert s.calls==[]


@pytest.mark.parametrize('commit',[False,True])
def test_intent_rollback_and_lost_commit_ack(local_repair,monkeypatch,commit):
    s=local_repair;connect=s.db.connect
    class Wrapped:
        def __enter__(self):self.c=connect();return self
        def __exit__(self,*args):return self.c.__exit__(*args)
        def execute(self,*args):return self.c.execute(*args)
        def commit(self):
            if commit:self.c.commit()
            raise ConnectionError('transaction acknowledgement')
    monkeypatch.setattr(s.db,'connect',Wrapped)
    with pytest.raises(ConnectionError):repair.transition(s.db,s.p,s.before,'patch_intent')
    monkeypatch.setattr(s.db,'connect',connect)
    assert repair.classify(repair.snapshot(s.db,s.p),s.p)==('patch_intent' if commit else 'eligible') and s.calls==[]


@pytest.mark.parametrize('fault',['none','old_head','old_diff','false_ci','history','proof'])
def test_latest_proof_finalization_compatibility(local_repair,monkeypatch,fault):
    from app.pcp_local_readiness import operation_readiness
    s=local_repair;asyncio.run(execute(s));id=s.before['job']['id'];before=s.db.get(id);workspace=w._retained_snapshot(s.v.path)
    monkeypatch.setattr(w.TrustedReaders,'__init__',lambda self,engine,github:self.__dict__.update(s.reader.__dict__))
    async def independent_review(self,endpoint,payload):
        assert endpoint=='/v1/pcp-local/pm-review' and payload['review_id']==81
        row=s.db.get(id);head=row['result']['commit']
        report=dict(verdict='pass',diff_hash=row['result']['diff']['diff_hash'])
        if fault=='old_diff':report['diff_hash']=s.before['job']['result']['diff']['diff_hash']
        evidence=ci(head) if fault!='false_ci' else dict(state='success',commit=head)
        return dict(job_id=id,expected_head=head,activation_digest=w.digest(s.reader.activation),report=report,pr=deepcopy(s.remote),ci=evidence)
    monkeypatch.setattr(w.TrustedReaders,'executor',independent_review)
    if fault in ('proof','history'):
        cp=deepcopy(before['checkpoint'])
        if fault=='proof':cp['pcp_local_execution']['verified_tree']=s.before['job']['checkpoint']['pcp_local_execution']['verified_tree']
        else:cp[repair.KEY]['original']['job']['progress']['input_tokens']=0
        s.db.update(id,checkpoint=cp)
    payload=SimpleNamespace(source_commit=s.v.task.base_sha,expected_head=before['result']['commit'],branch=before['branch'],baseline_revision=s.v.task.baseline_revision,pr_number=7,review_id=81)
    if fault=='old_head':payload.expected_head=s.before['job']['result']['commit']
    if fault!='none':
        with pytest.raises(TaskStop):asyncio.run(s.e.finalize_pcp_local_review(payload))
        assert s.db.get(id)['result']['delivery_finalized'] is False
        assert ownership(s.db)[0][0]['state']=='running'
    else:
        # Repair execution authority no longer implies PM finalization authority.
        ready=asyncio.run(operation_readiness(s.e,phase='finalization',job_id=id,review_id=81))
        assert not ready['ready']
        with pytest.raises(TaskStop,match='local_repair_finalization_authority_required'):
            asyncio.run(s.e.finalize_pcp_local_review(payload))
        assert s.db.get(id)==before and ownership(s.db)[0][0]['state']=='running'
    assert w._retained_snapshot(s.v.path)==workspace


def test_phase_failure_preserves_old_proof_and_fences_finalization(local_repair):
    s=local_repair
    async def failed(**kw):s.calls.append(kw['phase']);return dict(passed=False,commands=[dict(returncode=1,stdout='1 failed',timed_out=False)])
    s.e.ddev.phase=failed
    assert asyncio.run(execute(s))['state']=='verification_failed'
    row=s.db.get(s.before['job']['id'])
    assert row['checkpoint']['pcp_local_execution']==s.before['job']['checkpoint']['pcp_local_execution']
    assert row['result']==s.before['job']['result'] and row['progress']['test_runs']==3
    assert asyncio.run(execute(s))['state']=='verification_failed' and s.calls==['targeted_tests']


def test_cross_process_operation_lock_no_second_writer(local_repair):
    s=local_repair
    with h.operation_lock(s.db):
        with pytest.raises(TaskStop,match='operation_busy'):asyncio.run(execute(s))
    assert s.calls==[]


@pytest.fixture
def private_review_permit(local_repair,tmp_path,monkeypatch):
    import time
    import hashlib
    s=local_repair;a={**s.reader.activation,'verification_image':'sha256:'+'1'*64,'runtime_image_id':'sha256:'+'1'*64}
    original=tmp_path/'original.json';original.write_text(json.dumps(a));original.chmod(0o600)
    value={**s.p.value,'version':1,'decision_id':'fixture-local-review-repair','execution_record':'https://github.com/'+REPOSITORY+'/issues/835#issuecomment-1',
        'not_before':time.time()-1,'expires_at':time.time()+600,'original_activation_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
        'repair_source':'c'*40,'repair_commits':['c'*40],'repair_paths':['services/runtime/app/pcp_local_review_repair.py'],
        'roles':{role:dict(image_id='sha256:'+str(i)*64,source_commit='c'*40 if role in ('runtime','executor') else s.v.task.base_sha,
            **({} if role=='verifier' else dict(configuration_sha256='d'*64))) for i,role in enumerate(('verifier','runtime','executor','router'),1)}}
    permit=tmp_path/'permit.json';patch=tmp_path/'exact.patch';patch.write_bytes(s.p.patch);patch.chmod(0o600)
    def save():permit.write_text(h.canonical(value));permit.chmod(0o600)
    save();monkeypatch.setattr(repair,'PERMIT',permit);monkeypatch.setattr(repair,'ORIGINAL',original);monkeypatch.setattr(repair,'PATCH',patch)
    monkeypatch.setenv(repair.FLAG,'owner-approved')
    return s,value,permit,patch,save


@pytest.mark.parametrize('change',['none','expiry','old_flag','null','wrong_job','wrong_patch','wrong_path','wrong_proof','wrong_parent','usage','ownership','duplicate','revoke'])
def test_private_approval_exact_bytes_and_bindings(private_review_permit,monkeypatch,change):
    import time
    s,v,path,patch,save=private_review_permit
    if change=='none':
        p=repair.Permit();assert p.task==s.v.task and p.value['before']==s.before;return
    if change=='expiry':v['expires_at']=time.time()-1
    elif change=='old_flag':monkeypatch.setenv('PCP_LOCAL_ARTIFACT_RECOVERY_ENABLED','owner-approved')
    elif change=='null':v['version']=None
    elif change=='wrong_job':v['before']['job']['id']='e'*32
    elif change=='wrong_patch':patch.write_bytes(patch.read_bytes()+b'\n')
    elif change=='wrong_path':v['patch_plan']['path']='scripts/escape.py'
    elif change=='wrong_proof':v['before']['job']['checkpoint']['pcp_local_execution']['commit']='e'*40
    elif change=='wrong_parent':v['patch_plan']['candidate']['identity']['parent']='e'*40
    elif change=='usage':v['before']['job']['progress']['model_calls']=0
    elif change=='ownership':v['before']['lease']['generation']=5
    elif change=='revoke':
        p=repair.Permit();v['decision_id']='different-independent-decision';save()
        with pytest.raises(TaskStop):p.require_fresh()
        return
    save()
    if change=='duplicate':path.write_text(path.read_text()[:-1]+',"version":1}')
    with pytest.raises((TaskStop,KeyError,TypeError)):repair.Permit()


def test_private_umask_does_not_change_approved_test_mode(local_repair):
    import os,stat
    s=local_repair;before=stat.S_IMODE((s.v.path/TARGET).stat().st_mode);old=os.umask(0o077)
    try:assert asyncio.run(execute(s))['state']=='awaiting_pm_review'
    finally:os.umask(old)
    assert stat.S_IMODE((s.v.path/TARGET).stat().st_mode)==before


@pytest.mark.parametrize('header',['mode','symlink'])
def test_patch_cannot_change_file_type_or_executability(local_repair,header):
    s=local_repair
    patch=(b'diff --git a/'+TARGET.encode()+b' b/'+TARGET.encode()+b'\nold mode 100644\nnew mode 100755\n') if header=='mode' else (
        b'diff --git a/'+TARGET.encode()+b' b/'+TARGET.encode()+b'\nold mode 100644\nnew mode 120000\n--- a/'+TARGET.encode()+b'\n+++ b/'+TARGET.encode()+b'\n@@ -1 +1 @@\n-def test_answer(): assert 6 * 7 == 42\n+/etc/passwd\n')
    with pytest.raises((TaskStop,subprocess.SubprocessError)):repair.make_patch_plan(s.before['job'],s.v.task,patch,TARGET)
    assert not (s.v.path/TARGET).is_symlink() and s.calls==[]


@pytest.mark.parametrize('fault',['before_patch','before_commit','after_verification_record','after_publish'])
def test_crash_windows_preserve_epoch_and_never_blindly_replay(local_repair,monkeypatch,fault):
    s=local_repair
    if fault=='before_patch':
        actual=repair.write_patch
        monkeypatch.setattr(repair,'write_patch',lambda *a:(_ for _ in ()).throw(ConnectionError('before patch')))
    elif fault=='before_commit':
        from app import repo
        monkeypatch.setattr(repo,'commit_changes',lambda *a:(_ for _ in ()).throw(ConnectionError('before commit')))
    elif fault=='after_verification_record':
        actual=repair.transition
        def step(*a,**k):
            result=actual(*a,**k)
            if a[3]=='verified_uncommitted':raise ConnectionError('verified record acknowledgement')
            return result
        monkeypatch.setattr(repair,'transition',step)
    else:
        actual=s.e.ddev.publish_branch
        async def publish(**kw):await actual(**kw);raise ConnectionError('publish acknowledgement')
        s.e.ddev.publish_branch=publish
    with pytest.raises(Exception):asyncio.run(execute(s))
    if fault=='before_patch':monkeypatch.setattr(repair,'write_patch',actual)
    elif fault=='before_commit':
        # Snapshot subprocess errors retain the existing sanitized public code.
        with pytest.raises(TaskStop,match='pcp_local_inspection_invalid'):asyncio.run(execute(s))
        assert s.db.get(s.before['job']['id'])['checkpoint']['pcp_local_execution']['state']=='commit_uncertain'
        assert s.calls==['targeted_tests','full_tests'] and not s.published
        return
    elif fault=='after_verification_record':monkeypatch.setattr(repair,'transition',actual)
    assert asyncio.run(execute(s))['state']=='awaiting_pm_review'
    assert s.calls.count('targeted_tests')==s.calls.count('full_tests')==1
    assert len(s.published)==1


@pytest.mark.parametrize('change',['author','body','head','id','state'])
def test_exact_independent_finding_is_required(local_repair,change):
    s=local_repair;old=s.e.ddev.github_pull_request_review
    async def review(**kw):
        value=await old(**kw)
        field={'head':'commit_id','id':'id'}.get(change,change)
        value[field]='wrong' if change!='id' else 79
        return value
    s.e.ddev.github_pull_request_review=review
    with pytest.raises(TaskStop,match='review_identity_changed'):asyncio.run(execute(s))
    assert s.calls==[] and repair.snapshot(s.db,s.p)==s.before


@pytest.mark.parametrize('kind',['symlink','hardlink','bool_usage'])
def test_no_unsafe_read_or_full_row_type_coercion(local_repair,kind):
    import os
    s=local_repair
    if kind=='symlink':(s.v.path/'outside').symlink_to('/etc/passwd')
    elif kind=='hardlink':os.link(s.v.path/'original',s.v.path/'foreign_alias')
    else:
        progress=deepcopy(s.before['job']['progress']);progress['model_calls']=True;s.db.update(s.before['job']['id'],progress=progress)
    with pytest.raises(TaskStop):asyncio.run(execute(s))
    assert not s.calls


def test_legacy_execution_stays_fenced_during_local_review(local_repair):
    s=local_repair;before=s.db.get(s.before['job']['id'])
    with pytest.raises(RuntimeError,match='PCP-local|pcp_local'):
        asyncio.run(s.e.run_job(before['id']))
    assert s.db.get(before['id'])==before and not s.calls
