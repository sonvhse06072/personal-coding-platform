"""Transport uncertainty and narrow client capability; no real HTTP/model."""
import json
import pytest
from app import pcp_local_task_queue as s

JOB='a'*32

def ready():
    return {'ready':True,'job':{'id':JOB,'lease':{'state':'active','generation':2}},
        'identity':{'review_id':7,'source_commit':'b'*40,'expected_head':'c'*40,
                    'branch':'ai/fixture','baseline_revision':'fixture','pr_number':1}}

def completed():
    return {'ready':True,'job':{'id':JOB,'status':'completed','finalized':True,'review_id':7,
        'receipt':{'state':'delivered','generation':3},'lease':{'state':'released','generation':2}}}

@pytest.mark.parametrize('lost',[False,True])
def test_one_post_then_reconcile_lost_ack_without_replay(monkeypatch,capsys,lost):
    calls=[]
    def request(path,payload=None):
        calls.append((path,payload))
        if payload is not None:
            if lost:raise TimeoutError('secret transport message')
            return {'status':'completed'}
        if len(calls)==1:return ready()
        return completed()
    monkeypatch.setattr(s,'session_request',request)
    assert s.session_main(['finalize','--job-id',JOB,'--review-id','7','--json'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['outcome']=='completed' and result['mutation_requests']==1
    assert len(calls)==3 and 'secret' not in json.dumps(result)

@pytest.mark.parametrize('view',[{'ready':False}, {'ready':True,'existing_success':True}, {'ready':True,'job':{'id':'b'*32}}])
def test_blocked_completed_and_wrong_identity_never_post(monkeypatch,capsys,view):
    calls=[]
    def request(path,payload=None):
        assert payload is None;calls.append(path);return view
    monkeypatch.setattr(s,'session_request',request)
    s.session_main(['finalize','--job-id',JOB,'--review-id','7','--json'])
    assert len(calls)==1
    assert json.loads(capsys.readouterr().out)['mutation_requests']==0


def test_default_status_is_read_only_and_no_url_shell_sql_capability(monkeypatch,capsys):
    calls=[]
    monkeypatch.setattr(s,'session_request',lambda path: calls.append(path) or completed())
    assert s.session_main(['--job-id',JOB,'--json'])==0
    assert 'phase=status' in calls[0]
    for bad in ('run-once','execute','deliver','sql','https://example.invalid'):
        with pytest.raises(SystemExit):s.session_main([bad,'--job-id',JOB])


def test_unknown_after_post_never_retries(monkeypatch,capsys):
    calls=[]
    def request(path,payload=None):
        calls.append(path)
        if len(calls)==1:return ready()
        raise OSError('Bearer PRIVATE')
    monkeypatch.setattr(s,'session_request',request)
    assert s.session_main(['finalize','--job-id',JOB,'--review-id','7','--json'])==2
    value=capsys.readouterr().out
    assert len(calls)==3 and 'PRIVATE' not in value
    assert json.loads(value)['mutation_requests']==1


@pytest.mark.parametrize('mutation',['wrong_after_job','wrong_after_review','stale_review','bad_identity','bad_shape'])
def test_malformed_or_stale_identity_never_claims_success(monkeypatch,capsys,mutation):
    calls=[]
    def request(path,payload=None):
        calls.append(path)
        first=ready()
        if mutation=='stale_review':first['identity']['review_id']=8
        if mutation=='bad_identity':first['identity']['extra_url']='https://example.invalid'
        if mutation=='bad_shape':first['identity']=None
        if len(calls)==1:return first
        if payload is not None:return {'status':'completed'}
        after=completed()
        if mutation=='wrong_after_job':after['job']['id']='b'*32
        if mutation=='wrong_after_review':after['job']['review_id']=8
        return after
    monkeypatch.setattr(s,'session_request',request)
    assert s.session_main(['finalize','--job-id',JOB,'--review-id','7','--json'])==2
    result=json.loads(capsys.readouterr().out)
    assert result['outcome'] in ('unobserved','reconcile_before_retry')
    assert len(calls)==(3 if mutation.startswith('wrong_after') else 1)
