"""Actual registrar/transactions and concurrency in disposable PostgreSQL.

External provider/GitHub observations are fixtures, never live authority.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from app import pcp_local_task_queue as r
from app import pcp_local_worker_loop as w
from app.engine_delivery import DeliveryAwareStorage
from app.pcp_local_readiness import initialize_schema
from app.pcp_local_task_queue import LocalSourceQueueStore, TaskStop, MARKER
from test_pcp_local_claim_recovery import permit  # noqa:F401
from test_pcp_local_consolidation_postgres import database  # noqa:F401
from test_pcp_local_runtime_dispatch import setup  # noqa:F401


@pytest.fixture
def recovery(database, setup, permit, monkeypatch, tmp_path):
    db,s,p=database,setup,permit
    initialize_schema(db)
    s.task=p.task;s.baseline.source_commit=p.task.base_sha
    s.facts['baseline']['source_commit']=p.task.base_sha
    s.facts['isolation']['current_main_sha']=p.value['repair_source']
    s.github.source={**p.issue,'main_sha':p.value['repair_source']}
    s.engine.storage=DeliveryAwareStorage(db);s.engine._delivery_storage_backend=db
    s.engine.queue=asyncio.Queue();s.engine.workspace_root=tmp_path/'workspaces';s.engine.workspace_root.mkdir()
    q=LocalSourceQueueStore(db);q.record(p.task)
    q.advance(p.task,expected_state='pending',expected_generation=0,target_state='claimed',
        job_id=w.stable_job_id(p.task),worker_authorized=True)
    with db.connect() as conn:
        p.value['receipt_before']=conn.execute('SELECT to_jsonb(r) AS value FROM cp_pcp_local_source_receipts r').fetchone()['value']
    p.save()
    async def prepare(engine):
        permit=p.load()
        def read(key):
            return lambda task:w.RuntimeObservation(deepcopy(s.facts[key]),'d'*64,100,130)
        attestor=w.RuntimeTaskAttestor(issue_number=p.task.issue_number,
            readers={k:read(k) for k in w.OBSERVER_PARTS},clock=lambda:101)
        launcher=w.RuntimeTaskLauncher(engine=engine,attestor=attestor,github=s.github,
            receipts=LocalSourceQueueStore(db))
        launcher.recovery=permit;launcher.task=p.task;launcher.attempted=True
        await launcher._recheck(p.task)
        launcher.source_binding=attestor.binding(p.task)
        async def executor(path,payload):
            assert path=='/v1/pcp-local/claim-recovery-preflight' and payload=={}
            return {'permit_sha256':permit.sha256,'side_effects':'absent'}
        return permit,SimpleNamespace(executor=executor),launcher,json.loads(p.issue['body'].strip()[len(MARKER):])['goal']
    monkeypatch.setattr(r,'prepare',prepare)
    s.db=db;s.permit=p
    return s


def snapshot(s):
    with s.db.connect() as conn:
        return {table:conn.execute(sql.SQL('SELECT to_jsonb(r) AS value FROM {} r').format(sql.Identifier(table))).fetchall()
            for table in ('cp_jobs','cp_pcp_local_source_receipts','cp_project_leases','cp_job_events')}


def register(s):return asyncio.run(r.register(s.engine))


def test_plan_real_registration_preserves_receipt_and_all_counters(recovery):
    s=recovery;before=snapshot(s)
    assert r.plan(s.db,s.permit.load())['state']=='unregistered' and snapshot(s)==before
    result=register(s);after=snapshot(s)
    assert result['state']=='registered_not_started' and register(s)==result and snapshot(s)==after
    from app.dashboard_local import build_local_snapshot
    view = build_local_snapshot(s.db)
    assert view['observation'] == 'available' and view['jobs'][0]['assisted_recovery'] is True
    assert snapshot(s) == after
    assert after['cp_pcp_local_source_receipts']==before['cp_pcp_local_source_receipts']
    assert after['cp_project_leases']==[] and len(after['cp_jobs'])==len(after['cp_job_events'])==1
    job=after['cp_jobs'][0]['value'];audit=job['checkpoint'][r.KEY]
    assert job['progress']['model_calls']==job['progress']['test_runs']==0
    assert job['checkpoint']['pcp_local_source']['receipt']==w.claimed_source_receipt(s.task)
    stripped=deepcopy(job);del stripped['checkpoint'][r.KEY]
    assert audit['registered_preimage']==stripped
    assert audit['authorization']==s.permit.load().audit()
    assert s.engine.queue.empty()


@pytest.mark.parametrize('column,value', [('generation',2),('updated_at','2026-01-01T00:00:00Z'),
    ('created_at','2026-01-01T00:00:00Z'),('task_key','changed-task-key'),('goal_sha256','d'*64),
    ('allowed_paths',['tests/test_pcp_light_changed.py'])])
def test_full_receipt_preimage_drift_never_refreshed(recovery,column,value):
    s=recovery
    with s.db.connect() as conn:
        conn.execute(sql.SQL('UPDATE cp_pcp_local_source_receipts SET {}=%s').format(sql.Identifier(column)),
            (Jsonb(value) if isinstance(value,list) else value,))
    before=snapshot(s)
    with pytest.raises(TaskStop,match='preimage_drift'):register(s)
    assert snapshot(s)==before and s.engine.queue.empty()


@pytest.mark.parametrize('column,value',[('progress',{'model_calls':1}),('error','uncertain'),
    ('updated_at','2026-01-01T00:00:00Z'),('status','executing'),('result',{'commit':'d'*40})])
def test_committed_job_drift_blocks_replay_and_fence(recovery,column,value):
    s=recovery;register(s)
    with s.db.connect() as conn:
        conn.execute(sql.SQL('UPDATE cp_jobs SET {}=%s').format(sql.Identifier(column)),
            (Jsonb(value) if isinstance(value,dict) else value,))
    before=snapshot(s)
    for op in (lambda:register(s),lambda:r.fence(s.db,s.permit.load())):
        with pytest.raises(TaskStop,match='preimage_drift'):op()
    assert snapshot(s)==before


def test_concurrent_duplicate_registration_inserts_once(recovery):
    s=recovery
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:register(s),range(2)))
    assert results[0]==results[1]
    state=snapshot(s)
    assert len(state['cp_jobs'])==len(state['cp_job_events'])==1 and not state['cp_project_leases']
    assert s.engine.queue.empty()


@pytest.mark.parametrize('fault',['rollback','lost_ack'])
def test_transaction_crash_and_lost_ack_reconcile_exactly(recovery,monkeypatch,fault):
    s=recovery;before=snapshot(s);connect=s.db.connect
    class Wrapped:
        def __init__(self):self.conn=connect();self.inserted=False
        def __enter__(self):self.conn.__enter__();return self
        def __exit__(self,*args):return self.conn.__exit__(*args)
        def execute(self,statement,params=None):
            if isinstance(statement,str) and statement.startswith('INSERT INTO cp_jobs'):self.inserted=True
            if fault=='rollback' and isinstance(statement,str) and statement.startswith('UPDATE cp_jobs SET checkpoint='):
                raise RuntimeError('fixture audit write failed')
            return self.conn.execute(statement,params)
        def commit(self):
            self.conn.commit()
            if fault=='lost_ack' and self.inserted:raise RuntimeError('fixture commit acknowledgement lost')
    monkeypatch.setattr(s.db,'connect',Wrapped)
    with pytest.raises(RuntimeError):register(s)
    monkeypatch.setattr(s.db,'connect',connect)
    after=snapshot(s)
    if fault=='rollback':assert after==before
    else:
        assert r.plan(s.db,s.permit.load())['state']=='registered_not_started'
        register(s);assert snapshot(s)==after
    assert s.engine.queue.empty()


@pytest.mark.parametrize('competitor',['writer','blocked_receipt','lease'])
def test_competing_ownership_not_bypassed(recovery,competitor):
    s=recovery
    if competitor=='blocked_receipt':
        from dataclasses import replace
        other=replace(s.task,issue_number=1001,task_key='other-blocked-task')
        q=LocalSourceQueueStore(s.db);q.record(other)
        q.advance(other,expected_state='pending',expected_generation=0,target_state='blocked',
            job_id=w.stable_job_id(other),worker_authorized=True)
    else:
        s.db.create({'id':'f'*32,'project_id':'pcp-local','task':{},'status':'executing'})
        if competitor=='lease':s.db.acquire_project_lease('pcp-local','f'*32)
    before=snapshot(s)
    with pytest.raises(TaskStop):register(s)
    assert snapshot(s)==before


def test_fence_crash_cannot_requeue_or_replay(recovery):
    s=recovery;register(s);before=snapshot(s)
    r.fence(s.db,s.permit.load())
    after=snapshot(s)
    assert after['cp_jobs']==before['cp_jobs'] and after['cp_project_leases']==[]
    assert r.plan(s.db,s.permit.load())['state']=='execution_fenced_no_replay'
    assert register(s)['state']=='execution_fenced_no_replay'
    with pytest.raises(TaskStop,match='already_fenced'):r.fence(s.db,s.permit.load())
    assert snapshot(s)==after


def test_conflicting_decision_cannot_adopt_committed_registration(recovery):
    s=recovery;register(s);before=snapshot(s)
    s.permit.value['decision_id']='another-approved-decision';s.permit.save()
    with pytest.raises(TaskStop,match='conflicting_job_or_decision'):register(s)
    assert snapshot(s)==before


@pytest.mark.parametrize('where',['before_enqueue','after_enqueue','after_running'])
def test_execution_queue_ack_and_running_crash_boundaries(recovery,monkeypatch,where):
    s=recovery;register(s);before=snapshot(s);calls=[]
    reader=object.__new__(w.TrustedReaders)
    reader.engine=s.engine;reader.recovery=s.permit.load()
    async def source(self):return s.task,s.github.source
    async def refresh(self,task):assert task==s.task
    async def executor(self,path,payload):
        return {'permit_sha256':s.permit.load().sha256,'side_effects':'absent'}
    monkeypatch.setattr(w.TrustedReaders,'source',source)
    monkeypatch.setattr(w.TrustedReaders,'refresh',refresh)
    monkeypatch.setattr(w.TrustedReaders,'executor',executor)
    # Preserve the concrete type check in run_admitted_job; replace only reader initialization/I/O.
    monkeypatch.setattr(w.TrustedReaders,'__init__',lambda self,engine,github:
        self.__dict__.update(engine=engine,recovery=s.permit.load()))
    from app import pcp_local_readiness
    async def ready(*args):return {'ready':True}
    monkeypatch.setattr(pcp_local_readiness,'collect_readiness',ready)
    async def enqueue(job):
        calls.append(job)
        if where=='before_enqueue' and len(calls)==1:raise RuntimeError('fixture before enqueue')
        await s.engine.queue.put(job)
        if where=='after_enqueue' and len(calls)==1:raise RuntimeError('fixture lost enqueue ack')
    monkeypatch.setattr(s.engine,'enqueue',enqueue)
    def crash(*args):raise RuntimeError('fixture after durable running CAS, before lease')
    monkeypatch.setattr(s.db,'acquire_project_lease',crash)
    with pytest.raises(RuntimeError):asyncio.run(r.execute(s.engine))
    if where!='after_running':
        assert snapshot(s)==before
        with pytest.raises(RuntimeError,match='durable running'):asyncio.run(r.execute(s.engine))
    after=snapshot(s)
    assert r.plan(s.db,s.permit.load())['state']=='execution_fenced_no_replay'
    assert asyncio.run(r.execute(s.engine))['state']=='execution_fenced_no_replay'
    assert snapshot(s)==after and after['cp_jobs']==before['cp_jobs']
    assert after['cp_project_leases']==[] and s.engine.queue.empty()
    assert len(calls)==(2 if where=='before_enqueue' else 1)


@pytest.mark.parametrize('status,execution,expected',[
    ('executing','invocation_started','execution_fenced_no_replay'),
    ('blocked','verified_uncommitted','verified_delivery_only'),
    ('delivering','verified','verified_delivery_only'),
    ('completed','verified','terminal_observe_only'),
    ('failed','held','terminal_observe_only'),
    ('cancelled','held','terminal_observe_only')])
def test_advanced_states_are_observation_only_and_counters_never_reset(recovery,status,execution,expected):
    s=recovery;register(s);r.fence(s.db,s.permit.load())
    job=s.db.get(w.stable_job_id(s.task));cp=deepcopy(job['checkpoint'])
    cp['pcp_local_execution']={'state':execution};progress={**job['progress'],'model_calls':1,'input_tokens':91}
    s.db.update(job['id'],status=status,checkpoint=cp,progress=progress,error='retained fixture error')
    before=snapshot(s)
    assert r.plan(s.db,s.permit.load())['state']==expected and register(s)['state']==expected
    assert asyncio.run(r.execute(s.engine))['state']==expected
    assert snapshot(s)==before and s.engine.queue.empty()


@pytest.mark.parametrize('fault',['rollback','lost_ack'])
def test_running_fence_transaction_uncertainty_never_replays(recovery,monkeypatch,fault):
    s=recovery;register(s);before=snapshot(s);connect=s.db.connect
    class Wrapped:
        def __init__(self):self.conn=connect();self.fenced=False
        def __enter__(self):self.conn.__enter__();return self
        def __exit__(self,*args):return self.conn.__exit__(*args)
        def execute(self,statement,params=None):
            if isinstance(statement,str) and statement.startswith("UPDATE cp_pcp_local_source_receipts SET state='running'"):
                self.fenced=True
                if fault=='rollback':raise RuntimeError('fixture fence before commit')
            return self.conn.execute(statement,params)
        def commit(self):
            self.conn.commit()
            if self.fenced:raise RuntimeError('fixture fence lost ack')
    monkeypatch.setattr(s.db,'connect',Wrapped)
    with pytest.raises(RuntimeError):r.fence(s.db,s.permit.load())
    monkeypatch.setattr(s.db,'connect',connect)
    after=snapshot(s)
    if fault=='rollback':assert after==before
    else:
        assert asyncio.run(r.execute(s.engine))['state']=='execution_fenced_no_replay'
        assert snapshot(s)==after and after['cp_jobs']==before['cp_jobs']
    assert not after['cp_project_leases'] and s.engine.queue.empty()
