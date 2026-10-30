import json
from http.client import IncompleteRead
import pytest
from app import pcp_local_task_queue as q


@pytest.mark.parametrize('fault',[False,True])
def test_client_one_post_then_bounded_reconciliation(monkeypatch,capsys,fault):
    calls=[];job='a'*32
    def request(path,payload=None):
        calls.append((path,payload))
        if payload is not None:
            if fault:raise IncompleteRead(b'partial',10)
            return {'state':'verified_uncommitted'}
        return dict(job_id=job,permit_sha256='d'*64,ready=len(calls)==1,state='eligible' if len(calls)==1 else 'verifying')
    monkeypatch.setattr(q,'session_request',request)
    assert q.session_main(['verify-held','--job-id',job,'--apply','--json'])==0
    assert calls==[('held-verification',None),('held-verification',{'job_id':job,'permit_sha256':'d'*64}),('held-verification',None)]
    assert json.loads(capsys.readouterr().out)['mutation_requests']==1


def test_client_defaults_read_only_and_wrong_job_never_posts(monkeypatch,capsys):
    calls=[]
    def request(path,payload=None):calls.append((path,payload));return dict(job_id='b'*32,ready=True)
    monkeypatch.setattr(q,'session_request',request)
    assert q.session_main(['verify-held','--job-id','a'*32,'--apply'])==2
    assert calls==[('held-verification',None)]


def test_observer_and_unauthenticated_requests_cannot_verify(monkeypatch):
    import asyncio,httpx
    from app import main
    monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE','pcp_local_worker')
    monkeypatch.setenv('RUNTIME_API_TOKEN','fixture-token')
    monkeypatch.setattr(main.app.state,'pcp_local_worker_ready',True,raising=False)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as c:
            assert (await c.post('/v1/pcp-local/held-verification')).status_code==401
            monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE','pcp_local_dashboard')
            assert (await c.post('/v1/pcp-local/held-verification',headers={'Authorization':'Bearer fixture-token'})).status_code==403
    asyncio.run(run())


@pytest.mark.parametrize('field,value',[('job_id','e'*32),('permit_sha256','f'*64)])
def test_uncertain_post_never_reconciles_another_operation(monkeypatch,capsys,field,value):
    calls=[]
    def request(path,payload=None):
        calls.append((path,payload))
        if payload is not None:raise IncompleteRead(b'partial',10)
        view=dict(job_id='a'*32,permit_sha256='b'*64,ready=True)
        if len(calls)>1:view[field]=value
        return view
    monkeypatch.setattr(q,'session_request',request)
    assert q.session_main(['verify-held','--job-id','a'*32,'--apply'])==2
    assert len(calls)==3 and sum(payload is not None for _,payload in calls)==1
    assert json.loads(capsys.readouterr().out)['outcome']=='reconcile_before_retry'
