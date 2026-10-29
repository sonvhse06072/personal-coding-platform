"""Credential-free/no-inference probe for a disposable pinned Runtime container.

Operator MUST first verify network=none, no mounts/ports, non-root/read-only and
resource limits. Run via stdin, not in a live worker. Creates only /tmp/pcp-probe-*
synthetic data, retained until the disposable tmpfs is stopped. No codex exec,
login, auth file, app startup, registration or database connection is performed.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from app.adapters import codex
from app.security import harden_runtime_process_secret_boundary
from app.shell import CommandResult, agent_subprocess_env

root = Path(tempfile.mkdtemp(prefix='pcp-probe-'))
a, b, home = root/'jobs/a', root/'jobs/b', root/'provider'
for path in (a, b, home):
    path.mkdir(parents=True)
(a/'proof').write_text('SYNTHETIC_A')
(b/'current').write_text('SYNTHETIC_B')
(b/'escape').symlink_to(a/'proof')
(home/'provider-placeholder').write_text('SYNTHETIC_PROVIDER')

def git(path, *args):
    return subprocess.check_output(['git','-C',str(path),*args], text=True, stderr=subprocess.DEVNULL).strip()

for path, name in ((a,'proof'),(b,'current')):
    git(path,'init')
    git(path,'add',name)
    git(path,'-c','user.name=Fixture','-c','user.email=fixture@localhost','commit','-m','fixture')
blob = git(a,'rev-parse','HEAD:proof')
(b/'.git/objects/info/alternates').write_text(str(a/'.git/objects')+'\n')
(b/'external').mkdir()
(b/'external/.git').write_text('gitdir: '+str(a/'.git')+'\n')
def hashes(path):
    return {str(p.relative_to(path)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file()}
original_a = hashes(a)
captured = {}
async def capture(argv, **kwargs):
    captured.update(argv=argv, env=agent_subprocess_env(kwargs.get('env')))
    return CommandResult(argv=argv, returncode=0, stdout='{"type":"turn.completed"}', stderr='')

synthetic = dict(PATH=os.environ['PATH'], HOME=str(home), CODEX_HOME=str(home),
                 RUNTIME_API_TOKEN='SYNTHETIC_RUNTIME', GITHUB_DELIVERY_TOKEN='SYNTHETIC_PUBLISHER')
with patch.dict(os.environ, synthetic, clear=True), patch.object(codex,'run_command',capture):
    async def call():
        return await codex.CodexAdapter('fixture-model','low').run(workspace=b,
            prompt='SYNTHETIC_NO_INFERENCE', mode='execute', timeout=30, isolate_workspace=True)
    # Empty override tables do not remove inherited roots: the adapter must refuse.
    (home/'config.toml').write_text('[permissions.pcp_local.workspace_roots]\n'+json.dumps(str(a))+'=true\n')
    try:
        asyncio.run(call())
    except ValueError as exc:
        assert str(exc)=='pcp_local_unreviewed_codex_configuration' and not captured
    else:
        raise AssertionError('Inherited permission configuration was accepted')
    (home/'config.toml').unlink()  # This synthetic fixture only.
    asyncio.run(call())
assert captured['env']=={k:synthetic[k] for k in ('PATH','HOME','CODEX_HOME')}
assert {'--ignore-user-config','--ignore-rules','--strict-config'} <= set(captured['argv'])
assert '--sandbox' not in captured['argv']
assert subprocess.check_output(['codex','--version'],env=captured['env'],text=True).strip() == 'codex-cli '+codex.PCP_ISOLATION_CLI_VERSION
options=[]
for i,arg in enumerate(captured['argv']):
    if arg=='--config': options+=['--config',captured['argv'][i+1]]
# Same Runtime hardening before launching its child; only synthetic env exists.
harden_runtime_process_secret_boundary()
probe = r'''
import json,os,pathlib,socket,subprocess
p=pathlib.Path.cwd();a=p.parent/'a';out={}
def attempt(name,fn):
 try:out[name]={'ok':True,'value':fn()}
 except OSError as e:out[name]={'ok':False,'errno':e.errno}
def git(*args):
 r=subprocess.run(['git',*args],capture_output=True,text=True)
 return {'code':r.returncode,'out':r.stdout}
attempt('current_read',lambda:(p/'current').read_text())
attempt('current_write',lambda:(p/'new').write_text('fixture'))
attempt('python',lambda:subprocess.check_output(['python','--version'],text=True).strip())
attempt('git',lambda:git('-C',str(p),'status','--porcelain'))
attempt('siblings',lambda:[x.name for x in p.parent.iterdir()])
attempt('read',lambda:(a/'proof').read_text())
attempt('stat',lambda:(a/'proof').stat().st_size)
attempt('list',lambda:[x.name for x in a.iterdir()])
attempt('symlink',lambda:(p/'escape').read_text())
attempt('alternate',lambda:git('-C',str(p),'cat-file','-p',BLOB))
attempt('worktree',lambda:git('-C',str(p/'external'),'show','HEAD:proof'))
attempt('git_write',lambda:(p/'.git/config').write_text('untrusted'))
attempt('provider',lambda:pathlib.Path(PROVIDER).read_text())
attempt('privileged_environment',lambda:pathlib.Path('/proc/'+str(PARENT)+'/environ').read_bytes().decode())
attempt('socket',lambda:socket.socket().close())
routes=[]
for pid in pathlib.Path('/proc').iterdir():
 if not pid.name.isdecimal():continue
 for kind in ('root','cwd'):
  target=pid/kind
  target=target/str(a/'proof').lstrip('/') if kind=='root' else target/'proof'
  try:
   if target.read_text()=='SYNTHETIC_A':routes.append([pid.name,kind])
  except OSError:pass
out['process_routes']=routes
print(json.dumps(out,sort_keys=True))
'''.replace('BLOB',repr(blob)).replace('PROVIDER',repr(str(home/'provider-placeholder'))).replace('PARENT',str(os.getpid()))
command = ['codex','sandbox','-P','pcp_local','-C',str(b),*options,'--','python','-c',probe]
result = subprocess.run(command,env=captured['env'],capture_output=True,text=True,timeout=30)
assert result.returncode==0, result.stderr
checks=json.loads(result.stdout)
assert checks['current_read']=={'ok':True,'value':'SYNTHETIC_B'}
assert checks['current_write']['ok'] and checks['python']['ok'] and checks['git']['value']['code']==0
assert checks['siblings']=={'ok':True,'value':['b']}
for name in ('read','stat','list','symlink','git_write','provider','privileged_environment','socket'):
    assert not checks[name]['ok'], (name,checks[name])
assert checks['alternate']['value']['code']!=0 and checks['worktree']['value']['code']!=0
assert checks['process_routes']==[] and hashes(a)==original_a
print(json.dumps(dict(outcome='PASS',model_calls=0,root=str(root),
    adapter_sha256=hashlib.sha256(Path(codex.__file__).read_bytes()).hexdigest(),
    captured=captured,checks=checks),sort_keys=True))
