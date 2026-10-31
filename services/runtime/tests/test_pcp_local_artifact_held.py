"""Same held-class continuation: real PostgreSQL/Git, synthetic external calls."""
import asyncio
from copy import deepcopy
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from app import pcp_local_recovery as h, pcp_local_artifacts as a
from app import pcp_local_worker_loop as w
from app.pcp_local_task_queue import TaskStop
from test_pcp_local_held import held,execute  # noqa:F401
from test_pcp_local_consolidation_postgres import database  # noqa:F401
from test_pcp_local_consolidation import verified  # noqa:F401


@pytest.fixture
def artifact_held(held):
    s=held;row=s.db.get(s.v.store.row['id']);cp=row['checkpoint']
    returned=dict(attempt=1,returncode=0,provider_failed=False,model_calls=1,usage_digest='c'*64)
    cp['pcp_local_execution'].update(held_from='invocation_returned',returned_invocation=returned)
    s.db.update(row['id'],checkpoint=cp,error='pcp_local_changed_paths_denied')
    root=s.v.path/'pytest-of-node';root.mkdir();(root/'run').mkdir()
    (root/'run/data').write_text('synthetic temporary output')
    (root/'current').symlink_to(str(root/'run'))
    # Actual H producer: diff_state stages intent-to-add entries incl. symlinks.
    from app.repo import diff_state
    diff_state(s.v.path,750000,base_ref=s.v.task.base_sha)
    before=h.snapshot(s.db,s.permit)
    att=dict(kind='durable_returned',progress_sha256=h.digest(before['job']['progress']),
        returned_invocation_sha256=h.digest(returned))
    plan=a.make_plan(s.v.path,s.v.task,root.name,dict(kind='independent_pm_inventory',evidence_sha256='d'*64))
    s.permit.value.update(version=2,before=before,candidate=plan['candidate'],artifact_plan=plan,invocation_attestation=att)
    h.validate_eligibility(before,s.v.task,att,artifact=True)
    s.root=root;s.before=before;s.plan=plan
    return s


def test_legacy_scope_error_is_not_accepted_by_old_permit(artifact_held):
    s=artifact_held
    with pytest.raises(TaskStop,match='ineligible'):h.validate_eligibility(s.before,s.v.task,s.permit.value['invocation_attestation'])


def test_same_held_plan_custody_verify_commit_and_idempotence(artifact_held):
    s=artifact_held;manifest=a.capture(s.v.path,artifact_root=s.root.name)
    assert asyncio.run(h.operate(s.e))['ready']
    assert a.capture(s.v.path,artifact_root=s.root.name)==manifest
    result=asyncio.run(execute(s));row=s.db.get(s.before['job']['id'])
    assert result['state']=='verified_uncommitted'
    assert s.calls==['targeted_tests','full_tests','delivery']
    assert row['checkpoint']['pcp_local_execution']['state']=='verified'
    assert row['progress']['model_calls']==1 and row['progress']['test_runs']==2
    assert h.snapshot(s.db,s.permit)['receipt']==s.before['receipt']
    assert h.snapshot(s.db,s.permit)['lease']==s.before['lease']
    assert not s.root.exists() and a.destination(s.plan).is_dir()
    audit=row['checkpoint'][a.KEY][-1]
    assert audit['original']==s.before and audit['plan']['before']==manifest
    assert row['checkpoint'][h.HELD_KEY]['original']==s.before
    assert not asyncio.run(execute(s))['ready'] and len(s.calls)==3


@pytest.mark.parametrize('when',['intent','rename','custody_after','verification'])
def test_crashes_reconcile_custody_but_unknown_verification_never_repeats(artifact_held,monkeypatch,when):
    s=artifact_held
    if when in ('intent','custody_after'):
        original=a.record
        def lost(*args,**kw):
            result=original(*args,**kw)
            if (kw.get('after') is None)==(when=='intent'):raise ConnectionError('lost DB acknowledgement')
            return result
        monkeypatch.setattr(a,'record',lost)
    elif when=='rename':
        original=a.preserve
        def lost(*args):original(*args);raise ConnectionError('lost rename acknowledgement')
        monkeypatch.setattr(a,'preserve',lost)
    else:
        async def unknown(*args,**kw):raise ConnectionError('unknown verifier')
        monkeypatch.setattr(s.e,'verify_pcp_local',unknown)
    with pytest.raises(ConnectionError):asyncio.run(execute(s))
    assert s.calls==[]
    if when=='verification':
        assert asyncio.run(execute(s))['state']=='verifying';return
    monkeypatch.undo()
    async def prepare(engine):return s.permit,s.v.reader
    monkeypatch.setattr(h,'prepare',prepare)
    assert asyncio.run(h.operate(s.e))['ready']
    asyncio.run(execute(s));assert s.calls==['targeted_tests','full_tests','delivery']


@pytest.mark.parametrize('kind',['source','artifact','mode','receipt','lease','usage','new_file','symlink'])
def test_exact_preimage_drift_stops_before_move_and_tests(artifact_held,kind):
    s=artifact_held
    if kind=='source':(s.v.path/'new.py').write_text('drift')
    elif kind=='artifact':(s.root/'run/data').write_text('drift')
    elif kind=='mode':(s.root/'run/data').chmod(0o755)
    elif kind in ('receipt','lease'):
        with s.db.connect() as c:c.execute('UPDATE '+('cp_project_leases' if kind=='lease' else 'cp_pcp_local_source_receipts')+' SET generation=generation+1')
    elif kind=='usage':
        row=s.db.get(s.before['job']['id']);row['progress']['model_calls']=2;s.db.update(row['id'],progress=row['progress'])
    elif kind=='new_file':(s.v.path/'unknown').write_text('unknown source')
    else:(s.root/'escape').symlink_to('/etc/passwd')
    with pytest.raises(TaskStop):asyncio.run(execute(s))
    assert s.root.exists() and not a.destination(s.plan).exists() and s.calls==[]


def test_failed_mandatory_test_retains_custody_without_proof_or_replay(artifact_held):
    s=artifact_held
    async def fail(**kw):s.calls.append(kw['phase']);return dict(passed=False,commands=[dict(returncode=1,stdout='1 failed')])
    s.e.ddev.phase=fail
    assert asyncio.run(execute(s))['state']=='verification_failed'
    row=s.db.get(s.before['job']['id']);assert row['progress']['test_runs']==1
    assert 'verified_tree' not in row['checkpoint']['pcp_local_execution']
    assert row['checkpoint'][a.KEY][-1]['state']=='preserved'
    assert s.v.git('rev-parse','HEAD')==s.v.task.base_sha
    assert asyncio.run(execute(s))['state']=='verification_failed' and s.calls==['targeted_tests']


def test_durable_returned_checkpoint_required_not_agent_test_claim(artifact_held):
    s=artifact_held;before=deepcopy(s.before)
    before['job']['checkpoint']['pcp_local_execution'].pop('returned_invocation')
    with pytest.raises(TaskStop,match='returned_invocation'):h.validate_eligibility(before,s.v.task,s.permit.value['invocation_attestation'],artifact=True)


@pytest.fixture
def private_artifact(artifact_held,tmp_path,monkeypatch):
    import json,time,hashlib
    s=artifact_held;p=s.permit
    original={k:getattr(p.task,k) for k in ('issue_number','base_sha','body_sha256','baseline_revision','baseline_source_commit')}
    original.update(verification_image='sha256:'+'1'*64,runtime_image_id='sha256:'+'1'*64)
    original_path=tmp_path/'original-artifact.json';original_path.write_text(json.dumps(original));original_path.chmod(0o600)
    p.value.update(decision_id='fixture-artifact-verification',
        execution_record='https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-1',
        not_before=time.time()-1,expires_at=time.time()+600,
        original_activation_sha256=hashlib.sha256(original_path.read_bytes()).hexdigest(),
        repair_source='e'*40,repair_commits=['e'*40],repair_paths=['services/runtime/app/pcp_local_artifacts.py'],
        roles={role:dict(image_id='sha256:'+str(i)*64,source_commit='e'*40 if role in ('runtime','executor') else p.task.base_sha,
            **({} if role=='verifier' else dict(configuration_sha256='d'*64)))
            for i,role in enumerate(('verifier','runtime','executor','router'),1)})
    path=tmp_path/'artifact-permit.json'
    def save():path.write_text(h.canonical(p.value));path.chmod(0o600)
    save();monkeypatch.setattr(h,'ARTIFACT_PERMIT',path);monkeypatch.setattr(h,'ARTIFACT_ORIGINAL',original_path)
    monkeypatch.setenv('PCP_LOCAL_ARTIFACT_RECOVERY_ENABLED','owner-approved')
    monkeypatch.delenv('PCP_LOCAL_HELD_VERIFY_ENABLED',raising=False)
    return s,path,original_path,save


@pytest.mark.parametrize('change',['none','old_flag','version','candidate','returned','usage','verifier','expiry','marker','revocation'])
def test_separate_exact_private_artifact_authority(private_artifact,monkeypatch,change):
    import time
    s,path,original,save=private_artifact;p=s.permit
    if change=='none':
        loaded=h.load_held_permit();assert type(loaded) is h.ArtifactPermit
        assert loaded.task==p.task and loaded.activation['verification_image']=='sha256:'+'1'*64
        with pytest.raises(TaskStop):h.HeldPermit()
        return
    if change=='old_flag':monkeypatch.setenv('PCP_LOCAL_HELD_VERIFY_ENABLED','owner-approved')
    elif change=='version':p.value['version']=1
    elif change=='candidate':p.value['candidate']={'identity':{},'diff':{}}
    elif change=='returned':p.value['before']['job']['checkpoint']['pcp_local_execution'].pop('returned_invocation')
    elif change=='usage':p.value['before']['job']['progress']['model_calls']=2
    elif change=='verifier':p.value['roles']['verifier']['source_commit']=p.value['repair_source']
    elif change=='expiry':p.value['expires_at']=time.time()-1
    elif change=='marker':p.value['artifact_plan']['provenance']={'kind':'marker'}
    else:
        loaded=h.load_held_permit();p.value['decision_id']='another-exact-decision';save()
        with pytest.raises(TaskStop):loaded.require_fresh()
        return
    save()
    with pytest.raises((TaskStop,KeyError)):h.load_held_permit()


def test_concurrent_custody_intent_full_row_cas_has_one_winner(artifact_held):
    from concurrent.futures import ThreadPoolExecutor
    s=artifact_held
    def request():
        try:a.record(s.db,s.before,s.plan,s.permit.sha256);return 'intent'
        except TaskStop:return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(lambda _:request(),range(2)))==['intent','stale']
    assert s.root.exists() and s.calls==[]


@pytest.mark.parametrize('commit',[False,True])
def test_custody_transaction_rollback_or_lost_ack_is_reconciled_read_only(artifact_held,monkeypatch,commit):
    s=artifact_held;connect=s.db.connect
    class Wrapped:
        def __enter__(self):self.c=connect();return self
        def __exit__(self,*args):return self.c.__exit__(*args)
        def execute(self,*args):return self.c.execute(*args)
        def commit(self):
            if commit:self.c.commit()
            raise ConnectionError('lost acknowledgement')
    monkeypatch.setattr(s.db,'connect',Wrapped)
    with pytest.raises(ConnectionError):a.record(s.db,s.before,s.plan,s.permit.sha256)
    monkeypatch.setattr(s.db,'connect',connect)
    assert h.classify(h.snapshot(s.db,s.permit),s.permit)==('custody_intent' if commit else 'eligible')
    assert s.calls==[] and s.root.exists()


def test_metadata_only_drift_after_tests_never_creates_verified_proof(artifact_held):
    s=artifact_held;phase=s.e.ddev.phase
    async def changed(**kw):
        result=await phase(**kw)
        if kw['phase']=='full_tests':os.utime(s.v.path/'new.py',ns=(1,1))
        return result
    s.e.ddev.phase=changed
    with pytest.raises(TaskStop,match='artifact_source_drift'):asyncio.run(execute(s))
    row=s.db.get(s.before['job']['id']);assert row['progress']['test_runs']==2 and row['progress']['model_calls']==1
    assert 'verified_tree' not in row['checkpoint']['pcp_local_execution']
    assert asyncio.run(execute(s))['state']=='verifying'


def test_new_class_commit_lost_ack_uses_existing_read_only_reconciliation(artifact_held,monkeypatch):
    from test_pcp_local_held import test_commit_lost_ack_reconciles_without_testing_again
    test_commit_lost_ack_reconciles_without_testing_again(artifact_held,monkeypatch)
