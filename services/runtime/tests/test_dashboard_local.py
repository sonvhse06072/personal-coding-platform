from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import httpx
import pytest
from fastapi import FastAPI
from app.dashboard import create_dashboard_router
from app.dashboard_local import build_local_snapshot, job_projection

NOW=datetime(2026,10,28,17,0,tzinfo=timezone.utc)
JOB='51a11aa704362d84ae5c7b70e85741f1'


def held_row():
    return dict(id=JOB,project_id='pcp-local',status='blocked',source_commit='0c968dd99199c73f3fbc89c0b59da168844e8f73',
        workspace='/private/operator/path',branch='ai/51a11aa70436',created_at=NOW-timedelta(minutes=4),updated_at=NOW,
        error='pcp_local_uncertain_execution_no_retry',route={},result=None,
        progress={'model_calls':1,'test_runs':2,'input_tokens':29474,'output_tokens':3968,'agent_attempts':[{'usage':{'gross_input_tokens':257826,'cached_input_tokens':228352,'input_tokens':29474,'output_tokens':3968}}]},
        checkpoint={'pcp_local_source':{'receipt':{'issue_number':824}},'pcp_local_execution':{'state':'held',
            'model_choice':{'id':'codex_gpt6_luna','model':'gpt-6-luna','reasoning_effort':'low','adapter':'codex_cli'},
            'verification':{'passed':True,'test_runs':2,'passed_tests':213,'failed_tests':0,'skipped_tests':0,
                'phases':[{'phase':'targeted_tests','passed':True,'commands':[{}]},{'phase':'full_tests','passed':True,'commands':[{}]}]}}})


class ReadStore:
    def __init__(self, rows=None, broken=False):self.jobs=[held_row()] if rows is None else rows;self.trace=[];self.broken=broken;self.result=[]
    def connect(self):return self
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def execute(self,sql,params=None):
        self.trace.append((sql,params));assert sql.startswith(('SET TRANSACTION','SELECT'))
        if self.broken:raise RuntimeError('DATABASE_PASSWORD=private')
        if 'FROM cp_jobs' in sql:
            if sql.startswith('SELECT id'):
                assert params[1]=='pcp-local';self.result=[{'id':j['id']} for j in self.jobs if j['id']==params[0] and j['project_id']=='pcp-local']
            else:
                assert params==('pcp-local',);self.result=self.jobs
        elif 'FROM cp_pcp_local_source_receipts' in sql:
            assert params==('pcp-local','sonvhse06072/personal-coding-platform');self.result=[dict(job_id=JOB,state='running',generation=2)]
        elif 'FROM cp_project_leases' in sql:self.result=[dict(owner_job_id=JOB,state='active',generation=1)]
        elif 'FROM cp_job_events' in sql:self.result=[]
        elif 'to_regclass' in sql:self.result=[{'present':None}]
        else:self.result=[]
        return self
    def fetchall(self):return deepcopy(self.result)
    def fetchone(self):return deepcopy(self.result[0]) if self.result else None
    def get(self,key):return next((deepcopy(j) for j in self.jobs if j['id']==key),None)
    def events_after(self,*a,**kw):return []


def test_actual_held_shape_tests_pass_but_delivery_not_accepted(monkeypatch):
    monkeypatch.setenv('PCP_LOCAL_INSTANCE','fixture-local')
    db=ReadStore();v=build_local_snapshot(db,clock=NOW);j=v['jobs'][0]
    assert v['mode']=='pcp_local' and j['stage']=='held' and j['activity']=='blocked'
    assert j['local_verification']['passed_tests']==213 and j['hosted_ci']['observed'] is False
    assert j['pr_url'] is None and j['commit'] is None
    assert j['started_at'] is None and j['elapsed_seconds'] is None
    assert j['usage']['cost_usd'] is None and j['usage']['tool_calls'] is None
    assert j['model']['model']=='gpt-6-luna' and j['model']['reasoning_effort']=='low'
    assert j['receipt']['generation']==2 and j['lease']['generation']==1
    assert 'private/operator' not in str(v) and 'workflow_progress' not in str(v)
    assert all('ensure' not in sql for sql,_ in db.trace)


def test_projection_empty_unavailable_and_unknown_never_zero():
    assert build_local_snapshot(ReadStore([]),clock=NOW)['state']=='empty'
    v=build_local_snapshot(ReadStore(broken=True),clock=NOW)
    assert v['observation']=='unavailable' and v['jobs']==[] and 'PASSWORD' not in str(v)


@pytest.mark.parametrize('status,state', [('queued','queued'),('blocked','blocked'),('waiting_human','blocked'),('completed','completed'),('failed','failed')])
def test_status_projection(status,state):
    row=held_row();row['status']=status
    if status in {'queued','completed'}:row['error']=None
    assert job_projection(row,None,None,[],NOW)['activity']==state


def test_stale_is_not_active_and_sanitization_is_reused():
    row=held_row();row['status']='executing';row['updated_at']=NOW-timedelta(minutes=9);row['error']=None
    row['task']={'title':'Fixture task','description':'GITHUB_TOKEN=ghp_12345678901234567'}
    row['checkpoint']['pcp_local_source']['receipt']['allowed_paths']=['docs/pcp-light/fixture.md']
    event=dict(id=1,event_type='runtime_activity',phase='blocked',level='error',message='GITHUB_TOKEN=ghp_12345678901234567',created_at=NOW,data={})
    v=job_projection(row,None,None,[event],NOW)
    assert v['activity']=='stale' and v['blocker'] is None
    assert 'ghp_' not in str(v) and v['timeline'][0]['data']=={}
    assert v['title']=='Fixture task' and v['allowed_paths']==['docs/pcp-light/fixture.md']
    assert '<redacted>' in v['goal']


def test_authenticated_router_never_calls_orchestrator_and_rejects_foreign_events(monkeypatch):
    monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE','pcp_local_dashboard');monkeypatch.setenv('DASHBOARD_READ_TOKEN','fixture-read-secret')
    def forbidden():pytest.fail('dashboard must not ensure schema')
    foreign={**held_row(),'id':'a'*32,'project_id':'foreign'}
    store=ReadStore([foreign]);app=FastAPI();app.include_router(create_dashboard_router(store,SimpleNamespace(ensure=forbidden)))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as c:
            assert (await c.get('/v1/dashboard/snapshot')).status_code==401
            assert (await c.post('/v1/dashboard/session',json={'token':'publisher-token'})).status_code==401
            login=await c.post('/v1/dashboard/session',json={'token':'fixture-read-secret'})
            assert login.status_code==200 and 'Secure' in login.headers['set-cookie'] and 'HttpOnly' in login.headers['set-cookie']
            for suffix in ('events','stream'):assert (await c.get('/v1/dashboard/jobs/'+'a'*32+'/'+suffix)).status_code==404
            page=await c.get('/dashboard');assert 'PCP Local Activity' in page.text
            assert 'previewStart' not in page.text
    asyncio.run(run())


def test_dashboard_mode_exact_route_allowlist_and_no_startup_recovery(monkeypatch):
    from app import main
    monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE','pcp_local_dashboard')
    monkeypatch.setattr(main,'projects_doc',lambda:{'projects':{'pcp-local':{}}})
    monkeypatch.setattr(main,'harden_runtime_process_secret_boundary',lambda:None)
    async def forbidden(*a,**kw):pytest.fail('legacy worker/control startup')
    monkeypatch.setattr(main.engine,'start',forbidden)
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='https://test') as c:
                assert (await c.get('/dashboard')).status_code==200
                assert (await c.get('/health')).json()['router']=='not_checked'
                for path in ('/v1/jobs','/v1/dashboard/quota','/v1/dashboard/project-previews'):
                    assert (await c.get(path)).status_code==403
                for path in ('/v1/intake','/v1/pcp-local/run-once','/v1/pcp-local/deliver','/v1/dashboard/control-session'):
                    assert (await c.post(path,json={})).status_code==403
                monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE','normal')
                assert (await c.get('/v1/jobs')).status_code==403
    asyncio.run(run())


def test_default_zero_counters_are_not_tool_or_cost_observations():
    row=held_row();row['progress']['tool_calls']=0;row['progress']['cost_usd']=0
    v=job_projection(row,None,None,[],NOW)
    assert v['usage']['tool_calls'] is None and v['usage']['cost_usd'] is None
    row['status']='delivering'  # Retained assisted salvage has an unresolved error.
    v=job_projection(row,None,None,[],NOW)
    assert v['activity']=='blocked' and v['responsible_actor']=='operator'


@pytest.mark.parametrize('status', ['completed', 'failed', 'cancelled'])
@pytest.mark.parametrize('duration', [None, 45.5])
def test_terminal_outcome_and_duration_do_not_age(status, duration):
    row = held_row(); row['status'] = status
    row['checkpoint']['pcp_local_execution'].update(started_at=(NOW-timedelta(minutes=20)).isoformat())
    if duration is not None:
        row['checkpoint']['pcp_local_execution']['duration_seconds'] = duration
    first = job_projection(row, None, None, [], NOW)
    later = job_projection(row, None, None, [], NOW+timedelta(hours=1))
    assert first['activity'] == later['activity'] == status
    assert first['elapsed_seconds'] == later['elapsed_seconds'] == duration
    assert later['observation_freshness'] == 'stale' and later['terminal_outcome'] == status


@pytest.mark.parametrize('raw,expected', [
    (None, (None, None, None)),
    ({'cached_input_tokens':30}, (None,None,None)),
    ({'input_tokens':0,'output_tokens':0,'cost_usd':0}, (0,0,0)),
    ({'input_tokens':10,'cached_input_tokens':30}, (None,None,None)),
    ({'input_tokens':0,'cached_input_tokens':0,'output_tokens':0,'cost_usd':0}, (0,0,0)),
    ({'output_tokens':7}, (None,7,None)),
    ({'input_tokens':100,'output_tokens':7}, (None,7,None)),
    ({'input_tokens':100,'cached_input_tokens':30,'output_tokens':7,'cost_usd':0.1}, (70,7,0.1)),
    ({'nested':{'input_tokens':0,'cached_input_tokens':0,'output_tokens':0,'cost_usd':0}}, (0,0,0)),
])
def test_real_usage_recording_json_storage_projection(raw, expected):
    import json
    from app.engine_core import RuntimeEngineCore as RuntimeEngine
    from app.adapters.base import AgentRun
    row = held_row(); row['progress'] = {'model_calls':1,'input_tokens':0,'output_tokens':0}
    choice = {'id':'codex_gpt6_luna','adapter':'codex_cli','provider':'openai'}
    run = AgentRun(adapter='codex_cli',model='gpt-6-luna',returncode=0,output='',usage=raw)
    RuntimeEngine._record_usage(row['progress'], choice['id'], raw)
    RuntimeEngine._record_agent_attempt(row['progress'], choice, run)
    # Production progress is persisted as JSON, then read by the scoped snapshot.
    row['progress'] = json.loads(json.dumps(row['progress']))
    v = build_local_snapshot(ReadStore([row]), clock=NOW)['jobs'][0]['usage']
    assert (v['input_tokens'],v['output_tokens'],v['cost_usd']) == expected
    if raw is None:
        assert v['estimated_cost_usd'] is None
    if raw and raw.get('cached_input_tokens') == 30 and raw.get('input_tokens',0) < 30:
        assert v['cached_input_tokens'] is None


def test_partial_attempt_coverage_and_legacy_normalized_zero_are_unknown():
    from app.engine_core import RuntimeEngineCore as RuntimeEngine
    from app.adapters.base import AgentRun
    row=held_row(); row['progress']={'model_calls':2}
    for raw in (None, {'output_tokens':0,'cost_usd':0}):
        RuntimeEngine._record_agent_attempt(row['progress'], {'id':'codex_gpt6_luna'},
            AgentRun(adapter='codex_cli',model='gpt-6-luna',returncode=0,output='',usage=raw))
    v=job_projection(row,None,None,[],NOW)['usage']
    assert v['cost_usd'] is None and v['output_tokens'] is None
    assert v['coverage']['output_tokens']=='partial' and v['observed_partial_totals']['output_tokens']==0
    row['progress']['agent_attempts']=[{'usage':{'input_tokens':0,'output_tokens':0,'reported_cost_usd':0}}]
    row['progress']['model_calls']=1
    v=job_projection(row,None,None,[],NOW)['usage']
    assert v['input_tokens'] is v['output_tokens'] is v['cost_usd'] is None


@pytest.mark.parametrize('stage', ['verified_uncommitted','commit_uncertain','verified','held'])
def test_recovery_stage_retains_observed_execution_duration(stage):
    row=held_row();row['checkpoint']['pcp_local_execution'].update(state=stage,duration_seconds=12)
    assert job_projection(row,None,None,[],NOW+timedelta(hours=1))['elapsed_seconds']==12


def test_cost_estimate_never_becomes_reported_cost(monkeypatch):
    from app.engine_core import RuntimeEngineCore
    from app.adapters.base import AgentRun
    monkeypatch.setattr('app.usage.model_config', lambda key: {'pricing_usd_per_million':{'input':2,'output':4}})
    row=held_row();row['progress']={'model_calls':1}
    RuntimeEngineCore._record_agent_attempt(row['progress'],{'id':'synthetic'},
        AgentRun(adapter='codex_cli',model='synthetic',returncode=0,output='',usage={'input_tokens':1000,'output_tokens':500}))
    usage=job_projection(row,None,None,[],NOW)['usage']
    assert usage['cost_usd'] is None and usage['estimated_cost_usd']==0.004
    row['progress']['model_calls']=13  # bounded attempt history cannot prove cumulative totals
    usage=job_projection(row,None,None,[],NOW)['usage']
    assert usage['output_tokens'] is None and usage['coverage']['output_tokens']=='partial'
