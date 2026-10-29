"""Real isolated PostgreSQL/Git retirement; external approval is synthetic.

Opt-in DSN uses the existing disposable-schema infrastructure. No installed V3
rows, provider, Engine startup or model. Authority/quiescence doubles are NOT
physical worker-stop or independent PM acceptance evidence.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from threading import Event
from types import SimpleNamespace

import pytest
from psycopg.types.json import Jsonb

from app import pcp_local_recovery as r
from app.dashboard_local import build_local_snapshot
from app.engine_delivery import DeliveryAwareStorage
from app.pcp_local_recovery import recover_verified_job
from app.pcp_local_task_queue import TaskStop, LocalSourceQueueStore
from app.pcp_local_worker_loop import RuntimeTaskLauncher, claimed_source_receipt, stable_job_id
from app.storage import Storage
from test_pcp_local_consolidation_postgres import database, seed, ownership  # noqa:F401
from test_pcp_local_consolidation import verified  # noqa:F401


@pytest.fixture
def retirement(database, verified, monkeypatch):
    monkeypatch.setenv("PCP_LOCAL_TASK_WORKER_ENABLED", "owner-approved")  # Test process only.
    db,v=database,verified
    # Genuine Git commit and verified proof; counters/error retained in full.
    v.git('add','.');v.git('commit','-m','synthetic assisted commit')
    commit=v.git('rev-parse','HEAD')
    v.store.row['result']={'commit':commit,'verification':{'passed':True,'test_runs':2},'delivery_finalized':False}
    v.store.row['error']='publication_blocked'
    seed(db,v)
    m=r.plan(db,job_id=v.store.row['id'],instance='pcp-local-retirement-fixture',
        database_container='4'*64,workers=['1'*64,'2'*64,'3'*64],decision_id='fixture-retire-001',
        reason='Synthetic incomplete work; preserve evidence without delivery.')
    a=approval(m)
    return SimpleNamespace(db=db,v=v,m=m,a=a)


def approval(m):
    return dict(decision_id=m['decision_id'],action=r.DISPOSITION,manifest_sha256=r.digest(m),
        authority='owner_delegated_independent_pm',approver='fixture-pm',operator='fixture-operator',
        execution_record='FIXTURE: reviewed exact source and explicitly authorized non-delivery disposition',
        accepted_source='c'*40,attestation=r.ATTESTATION)


def state(s):
    return ownership(s.db),s.db.get(s.v.store.row['id'])


def apply(s,**kwargs):
    return r.retire(s.db,s.m,s.a,apply=True,check_quiescent=lambda m:None,**kwargs)


def test_dry_run_apply_exact_retry_git_usage_and_honest_projection(retirement):
    s=retirement;before=state(s)
    assert r.retire(s.db,s.m,s.a)['apply'] is False and state(s)==before
    result=apply(s);assert result==apply(s)
    job=s.db.get(result['job_id']);rec,lease=ownership(s.db)
    assert job['status']=='cancelled' and r.validated_retirement(job,rec[0])
    for key in ('progress','result','error','route','source_commit','created_at'):
        assert job[key]==before[1][key]
    assert job['checkpoint']['pcp_local_execution']==before[1]['checkpoint']['pcp_local_execution']
    assert s.v.git('rev-parse','HEAD')==job['result']['commit']
    assert rec[0]['state']=='blocked' and rec[0]['generation']==3
    assert lease[0]['state']=='released' and lease[0]['generation']==1
    view=build_local_snapshot(s.db)['jobs'][0]
    assert view['terminal_outcome']=='incomplete_not_delivered' and view['elapsed_seconds'] is None
    assert view['commit']==job['result']['commit'] and view['usage']['model_calls']==1


@pytest.mark.parametrize('table,column,value',[
    ('cp_jobs','progress',{'model_calls':2}),('cp_jobs','error','new_error'),
    ('cp_jobs','result',{'commit':'d'*40}),('cp_jobs','task',{'new':'field'}),
    ('cp_jobs','checkpoint',{'drift':True}),('cp_jobs','source_commit','d'*40),
    ('cp_jobs','branch','ai/changed'),('cp_jobs','updated_at','2000-01-01T00:00:00Z'),
    ('cp_pcp_local_source_receipts','body_sha256','d'*64),
    ('cp_pcp_local_source_receipts','base_sha','d'*40),
    ('cp_pcp_local_source_receipts','baseline_revision','different'),
    ('cp_pcp_local_source_receipts','goal_sha256','d'*64),
    ('cp_pcp_local_source_receipts','allowed_paths',['unapproved']),
    ('cp_pcp_local_source_receipts','generation',7),
    ('cp_project_leases','generation',7),('cp_project_leases','state','released'),
    ('cp_project_leases','updated_at','2000-01-01T00:00:00Z')])
def test_full_row_drift_never_refreshes_expected_proof(retirement,table,column,value):
    s=retirement
    from psycopg import sql
    with s.db.connect() as conn:
        conn.execute(sql.SQL('UPDATE {} SET {}=%s').format(sql.Identifier(table),sql.Identifier(column)),
                     (Jsonb(value) if isinstance(value,(dict,list)) else value,))
    before=state(s)
    with pytest.raises(TaskStop,match='preimage_drift'):apply(s)
    assert state(s)==before


@pytest.mark.parametrize('field,value',[('instance','pcp-local-foreign'),('project_id','foreign'),
    ('repository','foreign/repo'),('decision_id','different-decision'),('database',{'name':'foreign'})])
def test_changed_scope_or_authority_fails_closed(retirement,field,value):
    s=retirement;before=state(s);s.m[field]=value
    with pytest.raises(TaskStop):apply(s)
    assert state(s)==before


def test_conflicting_decision_and_post_retirement_drift(retirement):
    s=retirement;apply(s);before=state(s)
    other=deepcopy(s.m);other['decision_id']='conflicting-decision'
    with pytest.raises(TaskStop,match='conflicting_decision'):
        r.retire(s.db,other,approval(other),apply=True,check_quiescent=lambda _:None)
    assert state(s)==before
    with s.db.connect() as conn:conn.execute("UPDATE cp_pcp_local_source_receipts SET generation=generation+1")
    changed=state(s)
    with pytest.raises(TaskStop,match='postimage_drift'):apply(s)
    assert state(s)==changed
    assert not r.validated_retirement(changed[1],changed[0][0][0])


class Fault(Storage):
    def __init__(self,db,where):self.db=db;self.where=where
    def connect(self):
        conn=self.db.connect();where=self.where
        class Wrapped:
            def __enter__(self):conn.__enter__();return self
            def __exit__(self,*args):return conn.__exit__(*args)
            def execute(self,sql,params=None):
                if where=='rollback' and sql.startswith('UPDATE cp_pcp_local_source_receipts'):
                    raise RuntimeError('synthetic second write failure')
                return conn.execute(sql,params)
            def commit(self):
                conn.commit()
                if where=='lost_ack':raise RuntimeError('synthetic acknowledgement loss after COMMIT')
        return Wrapped()


@pytest.mark.parametrize('fault',['rollback','lost_ack'])
def test_atomic_rollback_and_lost_acknowledgement(retirement,fault):
    s=retirement;before=state(s)
    with pytest.raises(RuntimeError):
        r.retire(Fault(s.db,fault),s.m,s.a,apply=True,check_quiescent=lambda _:None)
    if fault=='rollback':assert state(s)==before
    else:
        committed=state(s);result=apply(s)
        assert state(s)==committed and result==committed[1]['checkpoint'][r.KEY]['outcome']


def test_active_worker_and_other_writer(retirement):
    s=retirement;before=state(s)
    def active(_):raise TaskStop('retirement_worker_active')
    with pytest.raises(TaskStop,match='worker_active'):r.retire(s.db,s.m,s.a,apply=True,check_quiescent=active)
    assert state(s)==before
    s.db.create(dict(id='f'*32,project_id='pcp-local',status='queued',task={}))
    with pytest.raises(TaskStop,match='other_writer'):apply(s)
    assert state(s)==before


def test_old_recovery_update_lease_and_receipt_cannot_resurrect(retirement,monkeypatch):
    s=retirement;apply(s);before=state(s);row=before[1]
    for fields in ({'status':'queued'},{'checkpoint':s.m['before']['job']['checkpoint']},{'progress':{}}):
        with pytest.raises(RuntimeError,match='retired_job'):s.db.update(row['id'],**fields)
    with pytest.raises(RuntimeError,match='retired_job'):s.db.acquire_project_lease('pcp-local',row['id'])
    with pytest.raises(TaskStop,match='retired_job'):
        asyncio.run(recover_verified_job(SimpleNamespace(storage=s.db),s.v.reader,s.v.task,row))
    with pytest.raises(TaskStop):
        LocalSourceQueueStore(s.db).advance(s.v.task,expected_state='running',expected_generation=2,
            target_state='delivered',job_id=row['id'],worker_authorized=True)
    assert state(s)==before


def test_stale_recovery_cas_and_retirement_serialize(retirement):
    s=retirement;entered=Event();release=Event()
    def stopped(_):entered.set();assert release.wait(5)
    old=s.db.get(s.v.store.row['id']);cp=deepcopy(old['checkpoint']);cp['pcp_local_execution']['state']='commit_uncertain'
    with ThreadPoolExecutor(2) as pool:
        retiring=pool.submit(r.retire,s.db,s.m,s.a,apply=True,check_quiescent=stopped)
        assert entered.wait(5)
        recovering=pool.submit(s.db.cas_local_checkpoint,old,cp,status='blocked',result=old['result'])
        assert not recovering.done();release.set();retiring.result(timeout=5)
        with pytest.raises(TaskStop):recovering.result(timeout=5)
    assert s.db.get(old['id'])['status']=='cancelled'


def next_registration(s, monkeypatch):
    """Real storage admission; synthetic reviewed authority, not LIVE admission."""
    task=replace(s.v.task,issue_number=1001,task_key='next-independent-task')
    q=LocalSourceQueueStore(s.db);q.record(task)
    q.advance(task,expected_state='pending',expected_generation=0,target_state='claimed',
              job_id=stable_job_id(task),worker_authorized=True)
    lease=s.db.project_lease('pcp-local')
    binding=dict(receipt=claimed_source_receipt(task),observations={'writer':{'value':{
        'lease':{k:lease[k] for k in ('project_id','owner_job_id','generation','state')}}}})
    launcher=object.__new__(RuntimeTaskLauncher)
    launcher.engine=SimpleNamespace(storage=DeliveryAwareStorage(s.db),_delivery_storage_backend=s.db)
    launcher.source_binding=binding
    monkeypatch.setattr(RuntimeTaskLauncher,'require_registration',lambda self:None)
    row=dict(id=stable_job_id(task),project_id='pcp-local',status='queued',source_commit=task.base_sha,
             checkpoint={'pcp_local_source':binding},task={})
    return row,launcher


def test_next_real_registration_only_after_audited_retirement(retirement,monkeypatch):
    s=retirement
    # Arbitrarily marking the old job terminal does not release its receipt.
    s.db.update(s.v.store.row['id'],status='cancelled')
    row,launcher=next_registration(s,monkeypatch)
    with pytest.raises(TaskStop,match='other_claim'):
        s.db.create_local_source_job(row,registration=launcher)
    # Roll back ONLY the synthetic fixture edit/claim before using original proof.
    with s.db.connect() as c:
        c.execute('DELETE FROM cp_pcp_local_source_receipts WHERE issue_number=1001')
        c.execute('UPDATE cp_jobs SET status=%s,updated_at=%s WHERE id=%s',
                  (s.m['before']['job']['status'],s.m['before']['job']['updated_at'],s.v.store.row['id']))
    apply(s)
    row,launcher=next_registration(s,monkeypatch)
    s.db.create_local_source_job(row,registration=launcher)
    assert s.db.get(row['id'])['status']=='queued'
    with pytest.raises(TaskStop):s.db.create_local_source_job(row,registration=launcher)
    assert s.db.get(s.v.store.row['id'])['status']=='cancelled'


def test_concurrent_original_claim_waits_then_fails_without_resurrection(retirement):
    s=retirement;entered=Event();release=Event()
    def stopped(_):entered.set();assert release.wait(5)
    with ThreadPoolExecutor(2) as pool:
        retiring=pool.submit(r.retire,s.db,s.m,s.a,apply=True,check_quiescent=stopped)
        assert entered.wait(5)
        claiming=pool.submit(LocalSourceQueueStore(s.db).advance,s.v.task,expected_state='running',
            expected_generation=2,target_state='delivered',job_id=s.v.store.row['id'],worker_authorized=True)
        assert not claiming.done();release.set();retiring.result(timeout=5)
        with pytest.raises(TaskStop,match='stale'):claiming.result(timeout=5)
    assert ownership(s.db)[0][0]['state']=='blocked'


def test_arbitrary_blocked_receipt_remains_blocking_and_audit_tamper_denies(retirement,monkeypatch):
    s=retirement;apply(s)
    with s.db.connect() as c:
        c.execute("UPDATE cp_jobs SET checkpoint=checkpoint-'pcp_local_retirement'")
    row,launcher=next_registration(s,monkeypatch)
    with pytest.raises(TaskStop,match='other_claim'):
        s.db.create_local_source_job(row,registration=launcher)
    assert s.db.get(row['id']) is None


@pytest.mark.parametrize('part',['job','receipt','lease'])
def test_every_post_row_checked_after_lost_ack(retirement,part):
    s=retirement;apply(s)
    tables={'job':'cp_jobs','receipt':'cp_pcp_local_source_receipts','lease':'cp_project_leases'}
    from psycopg import sql
    with s.db.connect() as c:c.execute(sql.SQL("UPDATE {} SET updated_at=now()").format(sql.Identifier(tables[part])))
    before=state(s)
    with pytest.raises(TaskStop,match='postimage_drift'):apply(s)
    assert state(s)==before


def test_foreign_database_same_content_is_not_target(retirement):
    s=retirement;s.m['database']['system_identifier']='different-cluster';s.a=approval(s.m)
    before=state(s)
    with pytest.raises(TaskStop,match='database_changed'):apply(s)
    assert state(s)==before


def test_old_activation_refresh_denies_before_executor_or_model(retirement,monkeypatch):
    from app.pcp_local_worker_loop import TrustedReaders
    s=retirement;apply(s)
    reader=object.__new__(TrustedReaders);reader.engine=SimpleNamespace(storage=s.db)
    project={'ddev':{'targeted_tests':list(s.v.task.allowed_paths),'full_tests':list(s.v.task.allowed_paths)}}
    monkeypatch.setattr(reader,'authority',lambda:(project,None))
    async def source():return s.v.task,{}
    async def forbidden(*a,**kw):pytest.fail('retired activation reached external operation')
    monkeypatch.setattr(reader,'source',source);monkeypatch.setattr(reader,'executor',forbidden)
    with pytest.raises(TaskStop,match='retired_job'):asyncio.run(reader.refresh(s.v.task))


def test_database_session_timezone_does_not_change_full_row_identity(retirement):
    s=retirement;connect=s.db.connect
    def non_utc():
        conn=connect();conn.execute("SET TIME ZONE 'Asia/Bangkok'");return conn
    s.db.connect=non_utc
    first=apply(s)
    assert first==apply(s) and s.db.get(first['job_id'])['status']=='cancelled'
