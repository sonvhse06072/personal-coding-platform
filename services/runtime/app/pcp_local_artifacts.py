"""Exact private execution-output custody. No ignores, deletion or model path.

Only a Runtime-created claim or an independently installed exact inventory may
name output. Filesystem evidence alone never authorizes the database operation.
The existing job checkpoint/CAS owns intent and reconciliation, not a new daemon.
"""
from __future__ import annotations

import ctypes
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import posixpath
import re
import stat
import tempfile

from .pcp_local_task_queue import require

KEY = 'pcp_local_artifacts'
TEMP_KEY = 'pcp_local_temporary'
CUSTODY = '.pcp-artifact-custody'
FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOATIME


def directory(path):
    """Pin every absolute ancestor without following links or listing it."""
    path=Path(path)
    require(path.is_absolute() and '..' not in path.parts,'artifact_path_substitution')
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    fd=os.open('/',flags)
    try:
        for name in path.parts[1:]:
            next_fd=os.open(name,flags,dir_fd=fd);os.close(fd);fd=next_fd
        return fd
    except BaseException:
        os.close(fd);raise


def identity(s):
    return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,
            s.st_size,s.st_mtime_ns,s.st_ctime_ns]


def same(a,b):
    from .pcp_local_recovery import canonical
    return canonical(a)==canonical(b)


def safe_name(name):
    return (isinstance(name,str) and 0<len(name)<=240 and name not in ('.','..')
            and not any(c in name for c in '/\\') and all(ord(c)>=32 and ord(c)!=127 for c in name))


def root_name(name):
    require(isinstance(name,str) and name and not name.startswith('/')
            and all(safe_name(p) and p not in {'.git','.ddev','.codex','.agents',CUSTODY} for p in name.split('/')),
            'artifact_root_invalid')


def roots(plan):
    values=[plan['root'],*plan['extra_roots']]
    for name in values:root_name(name)
    require(len(set(values))==len(values) and plan['extra_roots']==sorted(plan['extra_roots'])
        and not any(x!=y and y.startswith(x+'/') for x in values for y in values),'artifact_roots_overlap')
    return sorted(values)


def capture(path, *, artifact_root=None, destination=None, link_origin=None):
    """Stable descriptor-relative no-atime reads, never follow a link.

    Copies only source when requested. Links are legal ONLY in the explicitly
    inventoried output and must point lexically inside that original output root.
    Their bytes/metadata are retained, never opened, traversed or executed.
    """
    path=Path(path)
    require(path.is_absolute() and path.resolve()==path and not path.is_symlink(), 'artifact_path_substitution')
    out={}
    output_roots=() if artifact_root is None else (artifact_root,) if isinstance(artifact_root,str) else tuple(artifact_root)
    def output(rel):
        return any(r=='' or rel==r or rel.startswith(r+'/') for r in output_roots)
    def visit(parent,name,rel,target):
        require(safe_name(name),'artifact_name_invalid')
        s=os.stat(name,dir_fd=parent,follow_symlinks=False);record=dict(identity=identity(s),sha256=None)
        if stat.S_ISLNK(s.st_mode):
            matched=next((r for r in output_roots if r=='' or rel==r or rel.startswith(r+'/')),None)
            require(matched is not None and rel != matched,'artifact_symlink_denied')
            origin=Path(link_origin) if link_origin else path/matched
            link=os.readlink(name,dir_fd=parent)
            suffix=rel if matched=='' else rel[len(matched)+1:]
            absolute=posixpath.normpath(posixpath.join(str(origin),posixpath.dirname(suffix),link))
            require(absolute.startswith(str(origin)+'/') and all(ord(c)>=32 for c in link), 'artifact_link_escape')
            record['link']=link
        else:
            directory=stat.S_ISDIR(s.st_mode)
            require(directory or (stat.S_ISREG(s.st_mode) and s.st_nlink==1),'artifact_special_or_hardlink')
            fd=os.open(name,FLAGS|(os.O_DIRECTORY if directory else 0),dir_fd=parent)
            try:
                require(identity(os.fstat(fd))==identity(s),'artifact_read_raced')
                if directory:
                    if target is not None:target.mkdir(mode=0o700)
                    for child in sorted(os.listdir(fd)):
                        r=(rel+'/' if rel else '')+child
                        visit(fd,child,r,target/child if target is not None and not output(r) else None)
                else:
                    h=hashlib.sha256();f=target.open('xb') if target is not None else None
                    try:
                        while data:=os.read(fd,1024*1024):
                            h.update(data)
                            if f:f.write(data)
                    finally:
                        if f:f.close();target.chmod(stat.S_IMODE(s.st_mode))
                    record['sha256']=h.hexdigest()
                require(identity(os.fstat(fd))==identity(s),'artifact_read_raced')
            finally:os.close(fd)
        require(identity(os.stat(name,dir_fd=parent,follow_symlinks=False))==identity(s),'artifact_read_raced')
        out[rel]=record
    fd=directory(path.parent)
    try:visit(fd,path.name,'',Path(destination) if destination is not None else None)
    finally:os.close(fd)
    return out


def claim(workspace, *, root=None):
    """Caller records a named creation intent, then identity before development."""
    workspace=Path(workspace)
    require(workspace.is_absolute() and workspace.resolve()==workspace and not workspace.is_symlink(),'artifact_path_substitution')
    if root is None:path=Path(tempfile.mkdtemp(prefix='.pcp-temp-',dir=workspace))
    else:
        require(re.fullmatch(r'\.pcp-temp-[0-9a-f]{32}',root) is not None,'artifact_claim_name_invalid')
        fd=directory(workspace)
        try:os.mkdir(root,0o700,dir_fd=fd);os.fsync(fd)
        finally:os.close(fd)
        path=workspace/root
    return dict(root=path.name,identity=identity(path.lstat()))


def claimed_path(workspace,created):
    root_name(created['root']);p=Path(workspace)/created['root'];s=p.lstat()
    require(stat.S_ISDIR(s.st_mode) and not p.is_symlink()
        and identity(s)[:5]==created['identity'][:5] and s.st_mode & 0o077==0,
        'artifact_claim_changed')
    return p


def _candidate(clone,task,home,artifact_root=None):
    from .pcp_local_worker_loop import _retained_validate, _retained_run
    from .pcp_local_recovery import candidate
    output_roots=() if artifact_root is None else (artifact_root,) if isinstance(artifact_root,str) else tuple(artifact_root)
    _retained_validate(clone,home,artifact_roots=output_roots)
    hooks=clone/'.git/hooks'
    require(not hooks.exists() or all(p.is_file() and not p.is_symlink() and p.name.endswith('.sample') for p in hooks.iterdir()),'artifact_git_hooks')
    def git(*args):return _retained_run(['git','-C',str(clone),*args],home).split(b'\0')
    tracked={os.fsdecode(p) for p in git('ls-tree','-r','--name-only','-z',task.base_sha) if p}
    if output_roots:
        # Intent-to-add placeholders from H diff_state are not staged source.
        staged={os.fsdecode(p) for p in git('diff','--cached','--ita-invisible-in-index','--name-only','-z','HEAD','--') if p}
        require(not any(p==r or p.startswith(r+'/') for p in tracked|staged for r in output_roots),'artifact_tracked_root')
        placeholders=[os.fsdecode(p) for p in git('ls-files','-z') if p and
                      any(os.fsdecode(p).startswith(r+'/') for r in output_roots)]
        if placeholders:
            # ONLY the disposable copy: H diff_state produced intent-to-add
            # entries, including symlinks. Real staged/HEAD paths were denied.
            _retained_run(['git','-C',str(clone),'update-index','--force-remove','--',*placeholders],home)
    # Unlike git's ignores, a complete source manifest cannot hide a new file.
    for p in clone.rglob('*'):
        rel=p.relative_to(clone).as_posix()
        if rel=='.git' or rel.startswith('.git/') or p.is_dir():continue
        require(rel in tracked or rel in task.allowed_paths,'artifact_unrecognized_source')
    value=candidate(clone,task)
    return {k:value[k] for k in ('identity','diff')}


def source_candidate(path,task,artifact_root=None):
    with tempfile.TemporaryDirectory(prefix='pcp-artifact-source-') as scratch:
        home=Path(scratch);clone=home/'source';before=capture(path,destination=clone)
        result=_candidate(clone,task,home,artifact_root)
        require(capture(path)==before,'artifact_workspace_drift')
        return result


def make_plan(path,task,artifact_root,provenance,*,extra_roots=()):
    from .pcp_local_recovery import digest
    from .pcp_local_worker_loop import stable_job_id
    root_name(artifact_root);path=Path(path)
    output_roots=roots(dict(root=artifact_root,extra_roots=list(extra_roots)))
    require(type(provenance) is dict and provenance.get('kind') in
            {'runtime_created','independent_pm_inventory'},'artifact_provenance_required')
    if provenance['kind']=='independent_pm_inventory':
        require(set(provenance)=={'kind','evidence_sha256'} and
            re.fullmatch('[0-9a-f]{64}',provenance['evidence_sha256']),'artifact_provenance_required')
    else:
        require(set(provenance)=={'kind','created','attempt'} and type(provenance['attempt']) is int
            and provenance['attempt']>=1 and provenance['created']['root']==artifact_root,'artifact_provenance_required')
        claimed_path(path,provenance['created'])
        require(not extra_roots,'artifact_runtime_extra_roots')
    with tempfile.TemporaryDirectory(prefix='pcp-artifact-plan-') as scratch:
        home=Path(scratch);clone=home/'source'
        before=capture(path,artifact_root=output_roots,destination=clone)
        require(all(r in before and stat.S_ISDIR(before[r]['identity'][2]) for r in output_roots),'artifact_root_missing')
        candidate=_candidate(clone,task,home,output_roots)
        require(capture(path,artifact_root=output_roots)==before,'artifact_workspace_drift')
    return dict(version=1,workspace=str(path),job_id=stable_job_id(task),task_sha256=digest(vars(task)),
        root=artifact_root,extra_roots=list(extra_roots),provenance=deepcopy(provenance),before=before,candidate=candidate)


def operation_destination(plan):
    from .pcp_local_recovery import digest
    root_name(plan['root'])
    require(re.fullmatch('[a-f0-9]{32}',plan['job_id']) is not None,'artifact_job_invalid')
    return Path(plan['workspace']).parent/CUSTODY/plan['job_id']/digest(plan)


def destination(plan,root=None):
    return operation_destination(plan)/str(roots(plan).index(root or plan['root']))


def _directory(parent,name,*,create=False):
    if create:
        try:os.mkdir(name,0o700,dir_fd=parent);os.fsync(parent)
        except FileExistsError:pass
    fd=os.open(name,FLAGS|os.O_DIRECTORY,dir_fd=parent);s=os.fstat(fd)
    try:require(s.st_uid==os.getuid() and s.st_mode & 0o077==0,'artifact_custody_permissions')
    except BaseException:os.close(fd);raise
    return fd


def _output(plan,root):
    value=capture(destination(plan,root),artifact_root='',link_origin=Path(plan['workspace'])/root)
    expected={k[len(root):].lstrip('/'):v for k,v in plan['before'].items()
              if k==root or k.startswith(root+'/')}
    require(set(value)==set(expected),'artifact_inventory_drift')
    for k,v in expected.items():
        if k=='':require(value[k]['identity'][:-1]==v['identity'][:-1],'artifact_rename_drift')
        else:require(same(value[k],v),'artifact_inventory_drift')
    return value


def inspect_intent(plan):
    """Read-only exact partition, including a crash between multiple renames."""
    path=Path(plan['workspace']);all_roots=roots(plan);moved=[];outputs={}
    op=operation_destination(plan)
    if op.exists() or op.is_symlink():
        fd=directory(op)
        try:present=set(os.listdir(fd))
        finally:os.close(fd)
    else:present=set()
    expected_names=set()
    for root in all_roots:
        src=path/root;dest=destination(plan,root);exists=src.exists() or src.is_symlink()
        if exists:require(dest.name not in present,'artifact_destination_conflict')
        else:
            require(dest.name in present,'artifact_output_missing')
            outputs[root]=_output(plan,root);moved.append(root);expected_names.add(dest.name)
    require(present==expected_names,'artifact_foreign_custody')
    source=capture(path,artifact_root=all_roots)
    expected={k:v for k,v in plan['before'].items()
              if not any(k==r or k.startswith(r+'/') for r in moved)}
    require(set(source)==set(expected),'artifact_source_drift')
    parents={str(Path(r).parent) for r in moved};parents={'' if x=='.' else x for x in parents}
    for k,v in expected.items():
        actual=source[k]
        if k in parents:
            count=sum(('' if str(Path(r).parent)=='.' else str(Path(r).parent))==k for r in moved)
            require(actual['identity'][:5]==v['identity'][:5]
                and actual['identity'][5]==v['identity'][5]-count,'artifact_source_directory_drift')
        else:require(same(actual,v),'artifact_source_drift')
    return dict(source=source,outputs=outputs),moved


def preserve(plan):
    """After durable CAS intent: no-overwrite renames, never deletion.

    Each root is moved at most once. The complete original inventory validates
    any partial prefix before another rename; unknown tests are never replayed.
    """
    path=Path(plan['workspace']);op=operation_destination(plan)
    parent=directory(path.parent);cust=job=target=None
    try:
        cust=_directory(parent,CUSTODY,create=True);job=_directory(cust,plan['job_id'],create=True)
        target=_directory(job,op.name,create=True)
        _,moved=inspect_intent(plan)
        for root in roots(plan):
            if root in moved:continue
            current,moved=inspect_intent(plan)
            src_parent=path/Path(root).parent;fd=directory(src_parent)
            try:
                rel='' if str(Path(root).parent)=='.' else str(Path(root).parent)
                require(identity(os.fstat(fd))==current['source'][rel]['identity'],'artifact_workspace_drift')
                require(identity(os.stat(Path(root).name,dir_fd=fd,follow_symlinks=False))==plan['before'][root]['identity'],
                        'artifact_workspace_drift')
                libc=ctypes.CDLL(None,use_errno=True)
                if libc.renameat2(fd,os.fsencode(Path(root).name),target,os.fsencode(destination(plan,root).name),1):
                    raise OSError(ctypes.get_errno(),'artifact rename uncertain; reconcile')
                os.fsync(fd);os.fsync(target)
            finally:os.close(fd)
        after,moved=inspect_intent(plan)
        require(moved==roots(plan),'artifact_output_missing')
        return after
    finally:
        for fd in (target,job,cust,parent):
            if fd is not None:os.close(fd)


def check_preserved(plan,after,*,source=False):
    path=Path(plan['workspace'])
    for root in roots(plan):
        require(not (path/root).exists() and not (path/root).is_symlink(),'artifact_source_reappeared')
    fd=directory(path.parent);cust=job=op=None
    try:
        cust=_directory(fd,CUSTODY);job=_directory(cust,plan['job_id'])
        op=_directory(job,operation_destination(plan).name)
        require(set(os.listdir(op))=={destination(plan,r).name for r in roots(plan)},'artifact_foreign_custody')
        require({r:_output(plan,r) for r in roots(plan)}==after['outputs'],'artifact_custody_drift')
        if source:require(capture(path)==after['source'],'artifact_source_drift')
    finally:
        for f in (op,job,cust,fd):
            if f is not None:os.close(f)


def _without_latest(job):
    j=deepcopy(job);history=j['checkpoint'].pop(KEY)
    if len(history)>1:j['checkpoint'][KEY]=history[:-1]
    return j


def original(history):
    """Lossless local reference to earlier audits, never recursive duplication."""
    from .pcp_local_recovery import digest
    audit=history[-1];value=deepcopy(audit['original'])
    if 'previous_sha256' in audit:
        require(digest(history[:-1])==audit['previous_sha256'],'artifact_history_drift')
        value['job']['checkpoint'][KEY]=deepcopy(history[:-1])
    return value


def custody_state(current,before,plan,token):
    from .pcp_local_recovery import canonical,digest
    if canonical(current)==canonical(before):return 'eligible'
    history=current['job']['checkpoint'].get(KEY)
    require(type(history) is list and history,'artifact_audit_missing')
    audit=history[-1]
    require(canonical(original(history))==canonical(before) and audit['plan']==plan
        and audit['token']==token and audit['state'] in ('intent','preserved')
        and current['receipt']==before['receipt'] and current['lease']==before['lease']
        and digest(_without_latest(current['job']))==audit['after_sha256'], 'artifact_audit_drift')
    if audit['state']=='preserved':check_preserved(plan,audit['after'],source=True)
    return 'custody_'+audit['state']


def record(storage,expected,plan,token,*,after=None,require_fresh=lambda:None):
    """Existing full three-row CAS/project serialization; ownership never UPDATEs."""
    from .pcp_local_recovery import project_lock,read_rows,canonical,digest
    from .storage import now
    with storage.connect() as c:
        project_lock(c);require_fresh();current=read_rows(c,plan['job_id'],lock=True)
        require(canonical(current)==canonical(expected),'artifact_stale_preimage')
        j=deepcopy(current['job']);cp=j['checkpoint'];history=cp.setdefault(KEY,[])
        require(j['workspace']==plan['workspace'] and current['receipt']['state']=='running'
            and current['receipt']['generation']==2 and current['receipt']['job_id']==j['id']
            and current['lease']['state']=='active' and current['lease']['owner_job_id']==j['id']
            and current['lease']['generation']==cp['pcp_local_execution']['lease_generation'],
            'artifact_ownership_changed')
        if after is None:
            require(not history or history[-1]['state']=='preserved','artifact_intent_exists')
            if plan['provenance']['kind']=='runtime_created':
                claim=cp[TEMP_KEY]
                require(claim==dict(attempt=plan['provenance']['attempt'],created=plan['provenance']['created'])
                    and cp['pcp_local_execution']['state']=='invocation_returned','artifact_runtime_claim_changed')
            previous=deepcopy(history);preimage=deepcopy(current)
            if previous:preimage['job']['checkpoint'].pop(KEY)
            history.append(dict(original=preimage,plan=deepcopy(plan),token=token,state='intent',
                **({'previous_sha256':digest(previous)} if previous else {})))
        else:
            require(history and history[-1]['state']=='intent'
                and history[-1]['plan']==plan and history[-1]['token']==token,'artifact_intent_changed')
            check_preserved(plan,after,source=True)
            history[-1].update(state='preserved',after=deepcopy(after))
        j['updated_at']=now().isoformat()
        history[-1]['after_sha256']=digest(_without_latest(j))
        c.execute('UPDATE cp_jobs SET checkpoint=%s::jsonb,updated_at=%s WHERE id=%s',
            (canonical(cp),j['updated_at'],j['id']))
        c.commit()
    with storage.connect() as c:return read_rows(c,plan['job_id'])


def validate_custody_root(storage,root,current_job_id=None):
    """A name or forged on-disk marker grants no retained-workspace exception."""
    from .pcp_local_recovery import frozen
    from .pcp_local_task_queue import PROJECT_ID
    path=Path(root)/CUSTODY
    fd=directory(path);expected={}
    try:
        require(os.fstat(fd).st_uid==os.getuid() and os.fstat(fd).st_mode & 0o077==0,'artifact_custody_permissions')
        with storage.connect() as c:
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            rows=c.execute('SELECT * FROM cp_jobs WHERE project_id=%s AND checkpoint ? %s',(PROJECT_ID,KEY)).fetchall()
        require(bool(rows),'artifact_unowned_custody')
        for j in map(frozen,rows):
            for audit in j['checkpoint'][KEY]:
                p=audit['plan'];dest=operation_destination(p)
                require(p['workspace']==str(Path(root)/j['id']) and p['job_id']==j['id'], 'artifact_custody_identity')
                if audit['state']=='preserved':
                    check_preserved(p,audit['after']);expected.setdefault(j['id'],set()).add(dest.name)
                else:
                    require(audit['state']=='intent' and j['id']==current_job_id,'artifact_custody_unreconciled')
                    inspect_intent(p)
                    job_path=path/j['id']
                    if job_path.exists() or job_path.is_symlink():
                        names=expected.setdefault(j['id'],set())
                        if dest.exists() or dest.is_symlink():names.add(dest.name)
        require(set(os.listdir(fd))==set(expected),'artifact_foreign_custody')
        for name,names in expected.items():
            job=_directory(fd,name)
            try:require(set(os.listdir(job))==names,'artifact_foreign_custody')
            finally:os.close(job)
    finally:os.close(fd)


def finish_future(engine,task,created,attempt,*,require_fresh=lambda:None):
    """Ordinary returned turn only; no model, verification or replay in custody."""
    from .pcp_local_recovery import read_rows,digest
    from .pcp_local_worker_loop import stable_job_id
    with engine.storage.connect() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        before=read_rows(c,stable_job_id(task))
    plan=make_plan(Path(before['job']['workspace']),task,created['root'],
        dict(kind='runtime_created',created=created,attempt=attempt))
    token=digest(dict(kind='ordinary_temporary',before=before,plan=plan))
    current=record(engine.storage,before,plan,token,require_fresh=require_fresh)
    require_fresh()
    after=preserve(plan)
    return record(engine.storage,current,plan,token,after=after,require_fresh=require_fresh)['job']['checkpoint']
