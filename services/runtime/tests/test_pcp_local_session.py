"""Transport uncertainty, including real loopback HTTP; no model or live PCP."""
import json
import http.client
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


@pytest.mark.parametrize('error', [http.client.IncompleteRead(b'PRIVATE'),
    http.client.BadStatusLine('PRIVATE'), http.client.RemoteDisconnected('PRIVATE'),
    ConnectionResetError('PRIVATE')])
@pytest.mark.parametrize('after_available', [True, False])
def test_protocol_error_after_post_always_reconciles_once(monkeypatch,capsys,error,after_available):
    calls=[]
    def request(path,payload=None):
        calls.append((path,payload))
        if len(calls)==1:return ready()
        if payload is not None or not after_available:raise error
        return completed()
    monkeypatch.setattr(s,'session_request',request)
    code=s.session_main(['finalize','--job-id',JOB,'--review-id','7','--json'])
    output=capsys.readouterr().out;report=json.loads(output)
    assert len(calls)==3 and sum(payload is not None for _,payload in calls)==1
    assert code==(0 if after_available else 2) and 'PRIVATE' not in output
    assert report['outcome']==('completed' if after_available else 'reconcile_before_retry')
    assert report['mutation_requests']==1


@pytest.mark.parametrize('fault', ['truncated_body','invalid_status'])
def test_real_loopback_http_committed_post_protocol_failure(monkeypatch,capsys,fault):
    """Real urllib HTTP parser; server commits then loses its response, no provider."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    import urllib.request
    calls=[];committed=False
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            assert self.headers['Authorization']=='Bearer fixture-token'
            calls.append('GET')
            body=json.dumps(completed() if committed else ready()).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            nonlocal committed
            assert self.path=='/v1/pcp-local/pm-review'
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert payload==ready()['identity']
            calls.append('POST');committed=True
            if fault=='invalid_status':self.wfile.write(b'PRIVATE invalid status\r\n\r\n')
            else:
                self.send_response(200);self.send_header('Content-Length','1000');self.end_headers()
                self.wfile.write(b'{"PRIVATE":')
            self.wfile.flush();self.close_connection=True
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def loopback(request,timeout):
        assert request.full_url.startswith('http://127.0.0.1:8787/v1/pcp-local/')
        assert timeout<=300
        local=request.full_url.replace(':8787/',':'+str(server.server_port)+'/')
        return opener.open(urllib.request.Request(local,data=request.data,headers=dict(request.header_items())),timeout=timeout)
    monkeypatch.setenv('RUNTIME_API_TOKEN','fixture-token')
    monkeypatch.setattr(urllib.request,'urlopen',loopback)
    try:
        assert s.main(['session','finalize','--job-id',JOB,'--review-id','7','--json'])==0
        text=capsys.readouterr().out;report=json.loads(text)
        assert committed and calls==['GET','POST','GET']
        assert report['outcome']=='completed' and 'PRIVATE' not in text
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


@pytest.mark.parametrize('as_json',[False,True])
def test_delivery_readiness_reports_PM_action_without_post(monkeypatch,capsys,as_json):
    observed=dict(ready=False,dependencies_ready=True,authorized=False,checks=[],
        operation=dict(state='awaiting_pm_review',actor='PM',eligible=False,
            next_action='Review exact head; do not publish again'))
    calls=[]
    def request(path,payload=None):
        assert payload is None;calls.append(path);return observed
    monkeypatch.setattr(s,'session_request',request)
    args=['readiness','--job-id',JOB,'--phase','delivery']+(['--json'] if as_json else [])
    assert s.session_main(args)==2
    output=capsys.readouterr().out
    assert len(calls)==1 and 'PM' in output and 'do not publish again' in output
    if as_json:assert json.loads(output)['mutation_requests']==0
