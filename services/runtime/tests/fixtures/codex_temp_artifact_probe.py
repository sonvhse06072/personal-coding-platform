"""Pinned Runtime, network-none/RO/non-root fixture; synthetic local SSE only.

Run in a disposable approved image with candidate app overlay recorded. No auth,
real provider, worker/app startup or original workspace/database mount. This
exercises ACTUAL adapter argv -> CLI -> exec_command -> pytest and denial policy.
"""
import asyncio
from dataclasses import replace
import hashlib
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import tempfile
import threading
from unittest.mock import patch

from app.adapters import codex
from app import shell,pcp_local_artifacts as artifacts
from app.pcp_local_task_queue import LocalSourceTask
from app.pcp_local_worker_loop import stable_job_id
from app.security import harden_runtime_process_secret_boundary

root=Path(tempfile.mkdtemp(prefix='pcp848-cli-temp-'));home=root/'provider';home.mkdir()
sibling=root/'retained-a';sibling.mkdir();(sibling/'proof').write_text('SYNTHETIC_A')
custody=root/'.pcp-artifact-custody';custody.mkdir();(custody/'private').write_text('SYNTHETIC_CUSTODY')
(home/'placeholder').write_text('SYNTHETIC_PROVIDER')
assert subprocess.check_output(['codex','--version'],text=True).strip()=='codex-cli 0.160.0'
parent=os.getpid()


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(request);n=len(self.server.requests)
        if n<=3:
            cmd=self.server.command if n==1 else 'rm -rf pytest-of-node'
            args=dict(cmd=cmd,max_output_tokens=3000,yield_time_ms=1000)
            if n==3:args.update(cmd='python -c '+shlex.quote('from pathlib import Path; print(Path("proof").read_text())'),workdir=str(sibling))
            item=dict(type='function_call',id='fc'+str(n),call_id='c'+str(n),name='exec_command',
                arguments=json.dumps(args))
        else:item=dict(type='message',id='msg',role='assistant',content=[dict(type='output_text',text='synthetic done')])
        events=[dict(type='response.created',response={'id':'fixture'+str(n)}),
            dict(type='response.output_item.done',item=item),dict(type='response.completed',response={
                'id':'fixture'+str(n),'status':'completed','output':[],
                'usage':{'input_tokens':0,'output_tokens':0,'total_tokens':0}})]
        data=''.join('event: '+e['type']+'\ndata: '+json.dumps(e)+'\n\n' for e in events).encode()
        self.send_response(200);self.send_header('Content-Type','text/event-stream')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)


server=HTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
real_run=shell.run_command


async def synthetic(argv,**kwargs):
    override=['--config','model_provider="fixture"','--config',
        'model_providers.fixture={name="fixture",base_url="http://127.0.0.1:'+str(server.server_port)+
        '/v1",wire_api="responses",requires_openai_auth=false,supports_websockets=false,request_max_retries=0,stream_max_retries=0}']
    return await real_run(argv[:-1]+override+argv[-1:],**kwargs)


harden_runtime_process_secret_boundary()
for label in ('baseline','private'):
    workspace=root/label;workspace.mkdir()
    (workspace/'test_temp.py').write_text('def test_temp(tmp_path):\n (tmp_path/"data").write_text("fixture")\n')
    (workspace/'escape').symlink_to(sibling/'proof')
    def git(*args):return subprocess.check_output(['git','-C',str(workspace),*args],text=True).strip()
    git('init');git('-c','user.name=Fixture','-c','user.email=fixture@localhost','add','test_temp.py')
    git('-c','user.name=Fixture','-c','user.email=fixture@localhost','commit','-m','fixture')
    task=LocalSourceTask(repository='sonvhse06072/personal-coding-platform',project_id='pcp-local',
        issue_number=999,task_key='fixture-temp',body_sha256='a'*64,base_sha=git('rev-parse','HEAD'),
        baseline_revision='fixture',baseline_source_commit=git('rev-parse','HEAD'),goal_sha256='b'*64,allowed_paths=('new.py',))
    git('branch','-m','ai/'+stable_job_id(task)[:12])
    claim=artifacts.claim(workspace) if label=='private' else None
    private=workspace/claim['root'] if claim else None
    program='''import json,os,pathlib,socket,tempfile
p=pathlib.Path.cwd();out={}
for label,fn in [('sibling',lambda:pathlib.Path(SIBLING).read_text()),('custody',lambda:pathlib.Path(CUSTODY).read_text()),('escape',lambda:(p/'escape').read_text()),('provider',lambda:pathlib.Path(PROVIDER).read_text()),('shared_tmp',lambda:pathlib.Path('/tmp').iterdir().__next__()),('parent_env',lambda:pathlib.Path('/proc/PARENT/environ').read_bytes()),('socket',lambda:socket.socket())]:
 try:fn();out[label]=True
 except OSError:out[label]=False
assert not any(out.values()),out
(p/'new.py').write_text('answer=42\\n')
print(json.dumps(dict(denials=out,tempfile=tempfile.gettempdir(),TMPDIR=os.getenv('TMPDIR'))))
'''.replace('SIBLING',repr(str(sibling/'proof'))).replace('CUSTODY',repr(str(custody/'private'))).replace('PROVIDER',repr(str(home/'placeholder'))).replace('PARENT',str(parent))
    server.command='python -m pytest -q test_temp.py && python -c '+shlex.quote(program)
    server.requests=[]
    env=dict(PATH=os.environ['PATH'],HOME=str(home),CODEX_HOME=str(home),USER='node',PYTHONDONTWRITEBYTECODE='1')
    with patch.dict(os.environ,env,clear=True),patch.object(codex,'run_command',synthetic):
        result=asyncio.run(codex.CodexAdapter('fixture','low').run(workspace=workspace,
            prompt='synthetic tools; no inference',mode='execute',timeout=60,isolate_workspace=True,tool_tmp=private))
    assert result.returncode==0 and len(server.requests)==4,result.stderr
    outputs=[x['output'] for req in server.requests[1:] for x in req.get('input',[]) if x.get('type')=='function_call_output']
    assert any('1 passed' in x and '"socket": false' in x for x in outputs),outputs
    assert any('rm -f style commands are not permitted' in x for x in outputs),outputs
    foreign=[x['output'] for req in server.requests[1:] for x in req.get('input',[])
             if x.get('type')=='function_call_output' and x.get('call_id')=='c3']
    assert foreign and all('SYNTHETIC_A' not in x for x in foreign),foreign
    assert (sibling/'proof').read_text()=='SYNTHETIC_A'
    assert (workspace/'pytest-of-node').exists() is (label=='baseline')
    (workspace/'escape').unlink()  # Synthetic hostile probe link, never artifact cleanup.
    if private:
        assert (private/'pytest-of-node').is_dir()
        assert (private/'pytest-cache').is_dir()
        assert not (workspace/'.pytest_cache').exists()
        assert not (workspace/'__pycache__').exists()
        plan=artifacts.make_plan(workspace,task,private.name,dict(kind='runtime_created',created=claim,attempt=1))
        assert plan['candidate']['diff']['changed_files']==['new.py']
    print(json.dumps(dict(label=label,result='PASS',cli='0.160.0',real_provider_calls=0,
        adapter_sha256=hashlib.sha256(Path(codex.__file__).read_bytes()).hexdigest(),
        external_transport='synthetic_loopback_SSE',tool_results=outputs,
        artifact_inventory=len(plan['before']) if private else None,workspace=str(workspace))),flush=True)
server.shutdown()
