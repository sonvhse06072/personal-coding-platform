from __future__ import annotations
import asyncio
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import subprocess
import pytest
from app import pcp_local_readiness as readiness, pcp_local_recovery as recovery
from app.pcp_local_worker_loop import normalized_budget, stable_job_id
from app.pcp_local_task_queue import TaskStop
from app.repo import diff_state, commit_changes
from app.storage import Storage
from test_pcp_local_worker_loop import fixture


def test_budget_redundant_limit_is_canonical_and_enforced():
    limits = {'max_changed_files':2,'model_calls':1}
    assert normalized_budget(limits,3)==limits and limits['max_changed_files']==2
    assert normalized_budget({'model_calls':1},3)['max_changed_files']==3
    for v in (0,-1,4,True,'3'):
        with pytest.raises(TaskStop): normalized_budget({'max_changed_files':v},3)


class Schema:
    def __init__(self, missing=False): self.trace=[];self.missing=missing;self.rows=[]
    def connect(self):return self
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def commit(self): self.trace.append('COMMIT')
    def execute(self, sql, params=None):
        self.trace.append(sql)
        self.rows = ([dict(name=n,present=not self.missing,permitted=not self.missing) for n in readiness.TABLES]
                     if 'FROM unnest' in sql else [])
        return self
    def fetchall(self): return deepcopy(self.rows)


def test_schema_only_repeat_has_all_runtime_ddl_without_recovery_or_dml():
    db=Schema()
    readiness.initialize_schema(db);readiness.initialize_schema(db)
    assert sum('CREATE TABLE IF NOT EXISTS cp_task_telemetry' in s for s in db.trace)==2
    assert sum('CREATE TABLE IF NOT EXISTS cp_pcp_local_source_receipts' in s for s in db.trace)==2
    assert not any(s.lstrip().startswith(('UPDATE','DELETE','INSERT','DROP','TRUNCATE')) for s in db.trace)


def test_schema_readiness_collects_missing_tables_without_writes():
    db=Schema(True); blockers=readiness.schema_readiness(db)
    assert len(blockers)==len(readiness.TABLES)
    assert all(b['actor']=='operator' for b in blockers)
    assert all(s.startswith(('SET TRANSACTION','SELECT')) for s in db.trace)


def test_readiness_aggregates_no_identity_schema_provider_and_switches(monkeypatch):
    from app import shell, quota_telemetry
    calls=[]
    async def command(*a,**kw):calls.append('identity');return SimpleNamespace(returncode=128,stdout='')
    async def quota(*a):calls.append('quota');raise RuntimeError('private credential failure')
    monkeypatch.setattr(shell,'run_command',command)
    monkeypatch.setattr(quota_telemetry.CodexQuotaCollector,'collect',quota)
    for key in ('PCP_LOCAL_TASK_SOURCE_ENABLED','PCP_LOCAL_TASK_WORKER_ENABLED','PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION'):
        monkeypatch.delenv(key,raising=False)
    async def source():raise TaskStop('pcp_local_source_revoked')
    view=asyncio.run(readiness.collect_readiness(SimpleNamespace(storage=Schema(True)),SimpleNamespace(source=source)))
    assert {'activation','identity','schema','provider','trusted_sources'} <= {b['component'] for b in view['blockers']}
    assert view['model_invocations']==view['job_registrations']==0
    assert 'private credential' not in str(view) and calls==['identity','quota']


@pytest.fixture
def verified(tmp_path):
    task=fixture()[0]
    def git(*args):return recovery.git(tmp_path,*args)
    git('init','-b','ai/'+stable_job_id(task)[:12]);git('config','user.name','PCP Local');git('config','user.email','pcp-local@localhost')
    (tmp_path/'original').write_text('source');git('add','.');git('commit','-m','base')
    task=replace(task,base_sha=git('rev-parse','HEAD'))
    # Stable job includes source identity; branch is assigned after rebinding.
    git('branch','-m','ai/'+stable_job_id(task)[:12])
    (tmp_path/'new.py').write_text('answer=42\n')
    diff=diff_state(tmp_path,750000,base_ref=task.base_sha)
    proof=dict(state='verified_uncommitted',verification={'passed':True,'test_runs':2},
        authority_digest='a'*64,lease_generation=1,diff=diff,route={'strategy':{}},
        verified_tree=recovery.verified_tree(tmp_path,task,diff))
    binding=dict(issue_number=task.issue_number,body_sha256=task.body_sha256,base_sha=task.base_sha,
                 baseline_revision=task.baseline_revision,baseline_source_commit=task.baseline_source_commit,
                 goal_sha256=task.goal_sha256,allowed_paths=list(task.allowed_paths))
    row=dict(id=stable_job_id(task),project_id='pcp-local',source_commit=task.base_sha,
             workspace=str(tmp_path),branch=git('branch','--show-current'),route={'strategy':{}},status='blocked',
             checkpoint={'pcp_local_execution':proof,'pcp_local_source':{'receipt':binding}},progress={'model_calls':1,'input_tokens':99},result=None)
    class Memory:
        def __init__(self):self.row=deepcopy(row);self.transitions=[]
        def get(self,key):assert key==row['id'];return deepcopy(self.row)
        def cas_local_checkpoint(self,expected,cp,*,status,result):
            assert expected==self.row
            self.transitions.append(cp['pcp_local_execution']['state'])
            self.row.update(checkpoint=deepcopy(cp),status=status,result=deepcopy(result))
    store=Memory()
    async def refresh(t): assert t==task
    reader=SimpleNamespace(authority_digest='a'*64,refresh=refresh)
    return SimpleNamespace(task=task,store=store,engine=SimpleNamespace(storage=store),reader=reader,git=git,path=tmp_path)


def test_verified_uncommitted_recovery_has_no_model_and_preserves_usage(verified,monkeypatch):
    from app.adapters.codex import CodexAdapter
    async def forbidden(*a,**kw):pytest.fail('recovery must not call model')
    monkeypatch.setattr(CodexAdapter,'run',forbidden)
    v=verified;before=deepcopy(v.store.row['progress'])
    result=asyncio.run(recovery.recover_verified_job(v.engine,v.reader,v.task,v.store.get(v.store.row['id'])))
    assert result['status']=='delivering' and result['result']['delivery_finalized'] is False
    assert result['progress']==before and v.store.transitions==['commit_uncertain','verified']
    with pytest.raises(TaskStop):asyncio.run(recovery.recover_verified_job(v.engine,v.reader,v.task,result))


@pytest.mark.parametrize('kind',['uncertain_before','uncertain_after','changed_tree','wrong_route','wrong_authority','held'])
def test_recovery_reconciles_only_exact_known_commit(verified,kind):
    v=verified;row=v.store.row
    if kind.startswith('uncertain'):
        row['checkpoint']['pcp_local_execution']['state']='commit_uncertain'
        if kind=='uncertain_after':commit_changes(v.path,'actual commit before lost acknowledgement')
    if kind=='changed_tree':(v.path/'original').write_text('changed after verification')
    if kind=='wrong_route':row['route']={'different':True}
    if kind=='wrong_authority':v.reader.authority_digest='b'*64
    if kind=='held':row['checkpoint']['pcp_local_execution']['state']='held'
    if kind=='uncertain_after':
        result=asyncio.run(recovery.recover_verified_job(v.engine,v.reader,v.task,deepcopy(row)))
        assert result['result']['commit']==v.git('rev-parse','HEAD')
    else:
        with pytest.raises(TaskStop):asyncio.run(recovery.recover_verified_job(v.engine,v.reader,v.task,deepcopy(row)))
        assert not v.store.transitions


def test_telemetry_side_effect_does_not_erase_authoritative_outcome(monkeypatch,caplog):
    from app.telemetry_storage import TelemetryStorage
    row={'id':'one','status':'executing'}
    store=TelemetryStorage();monkeypatch.setattr(store,'get',lambda k:deepcopy(row))
    monkeypatch.setattr(Storage,'update',lambda self,k,**fields:row.update(fields))
    def fail(*args):raise RuntimeError('secret-bearing raw SQL error')
    monkeypatch.setattr(store,'_record_transition_telemetry',fail)
    store.update('one',status='blocked',error='primary_failure')
    assert row['error']=='primary_failure' and row['status']=='blocked'
    assert 'unavailable' in caplog.text and 'secret-bearing' not in caplog.text


@pytest.mark.parametrize('change',['none','stale_usage','counter_type','lease_generation','receipt_generation','receipt_body','receipt_owner'])
def test_real_checkpoint_cas_preserves_receipt_lease_counters(verified,change):
    v=verified; expected=deepcopy(v.store.row)
    receipt={**expected['checkpoint']['pcp_local_source']['receipt'],'state':'running','generation':2,'job_id':expected['id']}
    lease=dict(state='active',generation=1,owner_job_id=expected['id'])
    current=deepcopy(expected);writes=[]
    if change=='stale_usage':current['progress']['model_calls']+=1
    if change=='counter_type':current['progress']['model_calls']=True
    if change=='lease_generation':lease['generation']+=1
    if change=='receipt_generation':receipt['generation']+=1
    if change=='receipt_body':receipt['body_sha256']='f'*64
    if change=='receipt_owner':receipt['job_id']='foreign'
    class Conn:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def execute(self,sql,params=None):
            if sql.startswith('SELECT * FROM cp_jobs'):self.value=current
            elif sql.startswith('SELECT * FROM cp_pcp_local_source_receipts'):self.value=receipt
            elif sql.startswith('SELECT * FROM cp_project_leases'):self.value=lease
            elif sql.startswith('UPDATE cp_jobs'):writes.append((sql,params))
            else:assert 'pg_advisory_xact_lock' in sql
            return self
        def fetchone(self):return deepcopy(self.value)
        def commit(self):writes.append('COMMIT')
    db=Storage();db.connect=lambda:Conn()
    before=(deepcopy(current['progress']),deepcopy(receipt),deepcopy(lease))
    target=deepcopy(expected['checkpoint']);target['pcp_local_execution']['state']='commit_uncertain'
    if change=='none':
        db.cas_local_checkpoint(expected,target,status='blocked',result=None)
        assert writes[-1]=='COMMIT' and 'progress=' not in writes[0][0]
    else:
        with pytest.raises(TaskStop):db.cas_local_checkpoint(expected,target,status='blocked',result=None)
        assert writes==[]
    assert before==(current['progress'],receipt,lease)


def test_readiness_success_uses_existing_admission_checks_without_mutation(monkeypatch):
    from app import shell, quota_telemetry
    import importlib.metadata
    task,issue,_,facts=fixture()
    for key in ('PCP_LOCAL_TASK_SOURCE_ENABLED','PCP_LOCAL_TASK_WORKER_ENABLED','PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION'):
        monkeypatch.setenv(key,'owner-approved')
    async def command(*a,**kw):return SimpleNamespace(returncode=0,stdout='PCP Local <pcp-local@localhost> 123 +0000')
    async def quota(*a):return []
    monkeypatch.setattr(shell,'run_command',command)
    monkeypatch.setattr(quota_telemetry.CodexQuotaCollector,'collect',quota)
    monkeypatch.setattr(importlib.metadata,'version',lambda name:{'pytest':'8.4.1','PyYAML':'6.0.2'}[name])
    async def source():return task,issue
    reader=SimpleNamespace(source=source,snapshot=facts)
    async def refresh(actual):assert actual==task
    reader.refresh=refresh
    db=Schema()
    view=asyncio.run(readiness.collect_readiness(SimpleNamespace(storage=db),reader))
    assert view['ready'] is True and not view['blockers']
    assert view['job_registrations']==view['model_invocations']==0
    assert all(s.startswith(('SET TRANSACTION','SELECT')) for s in db.trace)


def test_present_schema_with_incomplete_role_rights_is_not_ready():
    class Denied(Schema):
        def execute(self,sql,params=None):
            super().execute(sql,params)
            for row in self.rows:row['permitted']=False
            return self
    db=Denied();blockers=readiness.schema_readiness(db)
    assert len(blockers)==len(readiness.TABLES)
    assert all(b['code']=='role_permissions' for b in blockers)
    privilege_query=next(s for s in db.trace if 'has_table_privilege' in s)
    # PostgreSQL comma-separated privilege lists mean ANY privilege. Require
    # each one independently so a SELECT-only principal cannot pass admission.
    assert all("name, '"+p+"')" in privilege_query for p in ('SELECT','INSERT','UPDATE','DELETE'))
