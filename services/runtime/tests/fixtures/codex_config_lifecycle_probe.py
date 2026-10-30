"""Run only in a bounded network-none synthetic Runtime fixture.
No credentials or inference. The sole writer is the actual pinned CLI exec
process, with a loopback synthetic SSE transport; never run in a live worker.
The imported adapter must be the candidate version (record any source overlay).
"""
import asyncio,json,os,pathlib,subprocess,tempfile,threading,ctypes,struct
from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def do_POST(self):
  self.rfile.read(int(self.headers.get("Content-Length",0)))
  events=[{"type":"response.created","response":{"id":"fixture"}},{"type":"response.output_item.done","item":{"type":"message","id":"msg","role":"assistant","content":[{"type":"output_text","text":"synthetic done"}]}},{"type":"response.completed","response":{"id":"fixture","status":"completed","output":[],"usage":{"input_tokens":0,"output_tokens":0,"total_tokens":0}}}]
  data="".join("event: "+e["type"]+"\ndata: "+json.dumps(e)+"\n\n" for e in events).encode()
  self.send_response(200);self.send_header("Content-Type","text/event-stream");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
server=HTTPServer(("127.0.0.1",0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
from unittest.mock import patch
from app.adapters import codex
from app.shell import CommandResult
root=pathlib.Path(tempfile.mkdtemp(prefix='pcp-config-probe-'))
for label,prevent in [('red',False),('green',True),('repeat',True),('next',True)]:
 home=root/('red' if label=='red' else 'green')/'home';ws=root/('green' if label=='repeat' else label)/'workspace';home.mkdir(parents=True,exist_ok=True);ws.mkdir(parents=True,exist_ok=True)
 (home/'auth-refresh-placeholder').write_text(label)
 subprocess.run(['git','init',str(ws)],check=True,capture_output=True)
 env={'PATH':os.environ['PATH'],'HOME':str(home),'CODEX_HOME':str(home)}
 captured=[]
 async def capture(argv,**kwargs):
  captured.extend(argv);return CommandResult(argv,0,'{"type":"turn.completed"}','')
 with patch.dict(os.environ,env,clear=True),patch.object(codex,'run_command',capture):
  asyncio.run(codex.CodexAdapter('fixture','low').run(workspace=ws,prompt='no inference fixture',mode='execute',timeout=30,isolate_workspace=True))
 argv=captured[:-1]
 if not prevent:
  idx=next(i for i,v in enumerate(argv) if v.startswith('projects='));del argv[idx-1:idx+1]
 argv += ['-c','model_provider="fixture"','-c','model_providers.fixture={name="fixture",base_url="http://127.0.0.1:PORT/v1",wire_api="responses",requires_openai_auth=false,supports_websockets=false,request_max_retries=0,stream_max_retries=0}']

 argv=[v.replace('PORT',str(server.server_port)) for v in argv]
 argv+=['no inference; synthetic transport']
 libc=ctypes.CDLL(None,use_errno=True)
 watch=libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
 assert watch>=0
 assert libc.inotify_add_watch(watch,os.fsencode(home),0x100|0x80|0x8)>=0
 process=subprocess.Popen(argv,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 out,err=process.communicate(timeout=40)
 r=type('Result',(),dict(returncode=process.returncode,stdout=out,stderr=err))
 assert r.returncode==0 and '"type":"turn.completed"' in r.stdout, r.stderr
 assert (home/'auth-refresh-placeholder').read_text()==label
 with patch.dict(os.environ,env,clear=True):
  if prevent:codex.require_isolated_configuration(ws)
  else:
   try:codex.require_isolated_configuration(ws)
   except ValueError:pass
   else:raise AssertionError('baseline guard did not reject CLI write')
 events=[]
 try:
  raw=os.read(watch,65536)
 except BlockingIOError:raw=b''
 os.close(watch)
 while raw:
  wd,mask,cookie,length=struct.unpack('iIII',raw[:16]);name=raw[16:16+length].rstrip(b'\0').decode();raw=raw[16+length:]
  events.append(dict(mask=mask,name=name))
 config=home/'config.toml'
 assert config.exists() is (not prevent)
 if not prevent:assert any(e['name']=='config.toml' for e in events)
 print(json.dumps(dict(label=label,code=r.returncode,pid=process.pid,file_events=events,config=config.read_text() if config.exists() else None,stdout=r.stdout[-1500:],stderr=r.stderr[-1500:])),flush=True)
