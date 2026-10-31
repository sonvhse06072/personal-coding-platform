"""Real Git/filesystem artifact contract; no filename/marker grants authority."""
from dataclasses import replace
import os
from pathlib import Path
import pytest
from app import pcp_local_artifacts as a
from app.pcp_local_task_queue import TaskStop
from test_pcp_local_consolidation import make_verified


@pytest.fixture
def output(tmp_path):
    path=tmp_path/'workspaces'/'job';path.mkdir(parents=True)
    v=make_verified(path);v.task=replace(v.task,allowed_paths=('new.py',))
    root=v.path/'pytest-of-node';root.mkdir();(root/'run').mkdir()
    (root/'run/data').write_bytes(b'preserve exact synthetic bytes\x00')
    (root/'current').symlink_to('run',target_is_directory=True)
    provenance=dict(kind='independent_pm_inventory',evidence_sha256='a'*64)
    return v,root,provenance


def test_plan_and_atomic_custody_preserve_complete_candidate_and_inventory(output):
    v,root,p=output;plan=a.make_plan(v.path,v.task,root.name,p)
    assert plan['candidate']['diff']['changed_files']==['new.py']
    assert plan['before'][root.name+'/current']['link']=='run'
    before=a.capture(v.path,artifact_root=root.name)
    assert plan['before']==before
    after=a.preserve(plan)
    assert not root.exists() and a.destination(plan).is_dir()
    assert (a.destination(plan)/'run/data').read_bytes()==b'preserve exact synthetic bytes\x00'
    assert os.readlink(a.destination(plan)/'current')=='run'
    assert a.preserve(plan)==after  # Lost rename acknowledgement, no second move.
    a.check_preserved(plan,after,source=True)
    assert a.source_candidate(v.path,v.task)==plan['candidate']


@pytest.mark.parametrize('attack',['outside_link','hardlink','root_link','source_link',
    'unknown','ignored_unknown','tracked_name','tracked_source','staged_output','config','index','forged_marker'])
def test_unsafe_output_or_source_is_not_disposable(output,attack):
    v,root,p=output
    if attack=='outside_link':(root/'evil').symlink_to(v.path.parent/'foreign')
    elif attack=='hardlink':os.link(v.path/'original',root/'linked')
    elif attack=='root_link':root.rename(v.path/'saved');root.symlink_to(v.path/'saved')
    elif attack=='source_link':(v.path/'extra').symlink_to(root/'run/data')
    elif attack=='unknown':(v.path/'extra.txt').write_text('not output')
    elif attack=='ignored_unknown':
        (v.path/'.git/info/exclude').write_text('extra.txt\n');(v.path/'extra.txt').write_text('not output')
    elif attack=='tracked_name':v.git('add','pytest-of-node');v.git('commit','-m','tracked tmp name')
    elif attack=='tracked_source':(v.path/'original').write_text('extra source edit')
    elif attack=='staged_output':v.git('add','pytest-of-node')
    elif attack=='config':v.git('config','core.fsmonitor','touch BAD')
    elif attack=='index':v.git('update-index','--assume-unchanged','original')
    else:p=dict(kind='marker',evidence_sha256='a'*64)
    with pytest.raises((TaskStop,OSError)):a.make_plan(v.path,v.task,root.name,p)
    assert not (v.path/'BAD').exists()


@pytest.mark.parametrize('drift',['content','mode','mtime','source','root','new_output'])
def test_plan_drift_never_refreshes_candidate_or_moves(output,drift):
    v,root,p=output;plan=a.make_plan(v.path,v.task,root.name,p)
    if drift=='content':(root/'run/data').write_bytes(b'changed')
    elif drift=='mode':(root/'run/data').chmod(0o755)
    elif drift=='mtime':os.utime(root/'run/data',ns=(1,1))
    elif drift=='source':(v.path/'new.py').write_text('different')
    elif drift=='root':root.rename(v.path/'old');root.mkdir()
    else:(root/'new').write_text('new output')
    with pytest.raises(TaskStop):a.preserve(plan)
    assert root.exists() and not a.destination(plan).exists()


@pytest.mark.parametrize('name',['../escape','a/b','.git','.codex','.', '/tmp','x\nBAD'])
def test_artifact_root_is_exact_single_safe_directory(output,name):
    v,_,p=output
    with pytest.raises(TaskStop):a.make_plan(v.path,v.task,name,p)


def test_conflicting_destination_and_source_reappearance_stop(output):
    v,root,p=output;plan=a.make_plan(v.path,v.task,root.name,p);after=a.preserve(plan)
    root.mkdir()
    with pytest.raises(TaskStop):a.preserve(plan)
    with pytest.raises(TaskStop):a.check_preserved(plan,after,source=True)


def test_quarantine_path_replacement_never_follows_sibling(output,tmp_path):
    v,root,p=output;plan=a.make_plan(v.path,v.task,root.name,p)
    outer=v.path.parent/a.CUSTODY;outer.symlink_to(v.path)
    with pytest.raises((TaskStop,OSError)):a.preserve(plan)
    assert root.exists()


def test_extra_legacy_output_requires_exact_inventory_not_ignored_filename(output):
    v,root,p=output;cache=v.path/'scripts'/'__pycache__';cache.mkdir(parents=True)
    (cache/'untrusted.pyc').write_bytes(b'opaque preserved bytes, never execute')
    with pytest.raises(TaskStop,match='unrecognized_source'):a.make_plan(v.path,v.task,root.name,p)
    plan=a.make_plan(v.path,v.task,root.name,p,extra_roots=['scripts/__pycache__'])
    before=a.capture(v.path,artifact_root=a.roots(plan));after=a.preserve(plan)
    assert plan['before']==before
    assert (a.destination(plan,'scripts/__pycache__')/'untrusted.pyc').read_bytes()==b'opaque preserved bytes, never execute'
    a.check_preserved(plan,after,source=True)


def test_partial_multiple_rename_ack_is_reconciled_without_repeating_root(output,monkeypatch):
    import ctypes
    v,root,p=output;cache=v.path/'tests'/'cache';cache.mkdir(parents=True);(cache/'data').write_text('fixture')
    plan=a.make_plan(v.path,v.task,root.name,p,extra_roots=['tests/cache'])
    libc=ctypes.CDLL(None,use_errno=True);calls=[]
    class Lost:
        def renameat2(self,*args):
            result=libc.renameat2(*args);calls.append(args[1]);raise ConnectionError('rename acknowledgement')
    monkeypatch.setattr(a.ctypes,'CDLL',lambda *args,**kw:Lost())
    with pytest.raises(ConnectionError):a.preserve(plan)
    assert len(a.inspect_intent(plan)[1])==1
    monkeypatch.setattr(a.ctypes,'CDLL',lambda *args,**kw:libc)
    after=a.preserve(plan);a.check_preserved(plan,after,source=True)
    assert len(calls)==1 and not root.exists() and not cache.exists()


def test_descriptor_capture_never_reads_through_a_replaced_directory(output,tmp_path,monkeypatch):
    v,root,p=output;foreign=tmp_path/'foreign';foreign.mkdir();secret=foreign/'data';secret.write_bytes(b'UNREAD_FOREIGN')
    atime=secret.stat().st_atime_ns;real_read=os.read;changed=[];seen=[]
    def race(fd,count):
        target=os.readlink('/proc/self/fd/'+str(fd))
        if target==str(root/'run/data') and not changed:
            (root/'run').rename(root/'old');(root/'run').symlink_to(foreign);changed.append(True)
        value=real_read(fd,count);seen.append(value);return value
    monkeypatch.setattr(a.os,'read',race)
    with pytest.raises((TaskStop,OSError)):a.capture(v.path,artifact_root=root.name)
    assert changed and not any(b'UNREAD_FOREIGN' in x for x in seen) and secret.stat().st_atime_ns==atime


def test_runtime_named_claim_never_adopts_a_preexisting_directory(tmp_path):
    name='.pcp-temp-'+'a'*32;existing=tmp_path/name;existing.mkdir();(existing/'marker').write_text('forged')
    with pytest.raises(FileExistsError):a.claim(tmp_path,root=name)
    assert (existing/'marker').read_text()=='forged'
