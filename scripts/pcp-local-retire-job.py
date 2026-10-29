#!/usr/bin/env python3
"""Trusted local maintenance; default dry-run. Never load Engine or initialize DB."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import socket
import tempfile
import threading
import re
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'services/runtime'))
from app.pcp_local_recovery import plan, retire, digest
from app.pcp_local_task_queue import TaskStop, require
from app.storage import Storage


def private_file(path):
    p=Path(path)
    require(not p.is_symlink() and not any(x.is_symlink() for x in p.parents), 'retirement_private_symlink')
    st=p.stat();parent=p.parent.stat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o600
        and parent.st_uid==os.getuid() and stat.S_IMODE(parent.st_mode)==0o700,
        'retirement_private_custody_required')
    require(st.st_size<=8*1024*1024, 'retirement_manifest_too_large')
    return p.read_text()


def pairs_unique(pairs):
    result={}
    for k,v in pairs:
        require(k not in result,'retirement_duplicate_json_key');result[k]=v
    return result


def private_json(path):
    return json.loads(private_file(path),object_pairs_hook=pairs_unique)


def stopped_workers(manifest):
    """Actual daemon inspection, under the transaction lock, no docker mutations.

    Fail closed if any non-DB member of the original namespace is running.
    Exact reviewed worker IDs must still belong to that namespace and include
    Runtime/Router/Executor. Never discover or operate on foreign namespaces.
    """
    def docker(*args):
        p=subprocess.run(['docker',*args],capture_output=True,text=True,timeout=15)
        require(p.returncode==0,'retirement_quiescence_unavailable')
        return p.stdout
    instance=manifest['instance']
    ids=docker('ps','-aq','--filter','label=org.pcp.local.instance='+instance).split()
    require(set(manifest['workers'])<=set(ids),'retirement_worker_inventory_changed')
    require(manifest['database_container'] in ids,'retirement_database_container_changed')
    rows=json.loads(docker('inspect',*ids))
    roles=set()
    for row in rows:
        labels=row['Config'].get('Labels') or {}
        require(labels.get('org.pcp.local.instance')==instance,'retirement_worker_namespace_changed')
        name=row['Name'].removeprefix('/')
        db=name==instance+'-db'
        if db:
            require(row['Id']==manifest['database_container'] and row['State']['Status']=='running',
                    'retirement_database_container_changed')
            control=docker('exec',row['Id'],'sh','-c','exec pg_controldata "$PGDATA"')
            require(any(line.split(':',1)[0].strip()=='Database system identifier' and
                line.split(':',1)[1].strip()==manifest['database']['system_identifier']
                for line in control.splitlines() if ':' in line),'retirement_database_cluster_changed')
        require(db or row['State']['Status'] in {'exited','created'},'retirement_worker_active')
        if row['Id'] in manifest['workers']:
            require(not db and row['State']['Status']=='exited','retirement_worker_not_stopped')
            for role in ('coding-runtime','router','ddev-executor'):
                if name==instance+'-'+role: roles.add(role)
    require(roles=={'coding-runtime','router','ddev-executor'},'retirement_worker_roles_missing')


@contextmanager
def database_channel(container):
    """Private, one-connection PostgreSQL transport; no listener on host TCP.

    The fixed command connects only to port5432 of the exact DB container. It
    takes no SQL/command input. PG authentication/authorization still applies.
    Docker/credentials remain on the trusted operator host, never in Runtime.
    """
    require(isinstance(container,str) and re.fullmatch('[a-f0-9]{64}',container),
            'retirement_database_container_missing')
    with tempfile.TemporaryDirectory(prefix='pcp-retirement-db-') as directory:
        os.chmod(directory,0o700)
        listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        listener.bind(directory+'/.s.PGSQL.5432');os.chmod(directory+'/.s.PGSQL.5432',0o600)
        listener.listen(1);listener.settimeout(15)
        children=[];connections=[];errors=[]
        def serve():
            try:
                client,_=listener.accept();connections.append(client)
                # Two byte streams only. No shell interpolation and no secrets
                # in process arguments or output. Killing exec closes TCP.
                process=subprocess.Popen(['docker','exec','-i',container,'bash','-c',
                    'exec 3<>/dev/tcp/127.0.0.1/5432; cat <&3 & peer=$!; cat >&3; kill "$peer" 2>/dev/null; wait'],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
                children.append(process)
                def to_pg():
                    try:
                        while chunk:=client.recv(65536):
                            process.stdin.write(chunk);process.stdin.flush()
                    except (OSError,ValueError):pass
                    finally:
                        try:process.stdin.close()
                        except OSError:pass
                writer=threading.Thread(target=to_pg,daemon=True);writer.start()
                try:
                    while chunk:=os.read(process.stdout.fileno(),65536):client.sendall(chunk)
                except OSError:pass
                finally:client.close();writer.join(timeout=2)
            except OSError:errors.append('retirement_database_channel_failed')
        thread=threading.Thread(target=serve,daemon=True);thread.start()
        try:yield directory
        finally:
            listener.close()
            for client in connections:
                try:client.shutdown(socket.SHUT_RDWR)
                except OSError:pass
                client.close()
            for child in children:
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=5)
                    except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
            thread.join(timeout=16)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-file',required=True,help='0600 JSON with DATABASE_URL only, in owned 0700 dir')
    parser.add_argument('--manifest');parser.add_argument('--approval')
    parser.add_argument('--apply',action='store_true',help='Only after independent PM postmerge execution checkpoint')
    parser.add_argument('--plan-out',help='Create private full-preimage plan; no business writes')
    parser.add_argument('--job-id');parser.add_argument('--instance');parser.add_argument('--database-container')
    parser.add_argument('--worker',action='append',default=[])
    parser.add_argument('--decision-id');parser.add_argument('--reason')
    args=parser.parse_args(argv)
    require(not args.apply or not args.plan_out,'retirement_plan_cannot_apply')
    config=private_json(args.connection_file)
    require(set(config)=={'DATABASE_URL'} and isinstance(config['DATABASE_URL'],str),'retirement_connection_file_invalid')
    manifest=private_json(args.manifest) if args.manifest else None
    container=manifest.get("database_container") if manifest else args.database_container
    class Maintenance(Storage):
        @contextmanager
        def connect(self):
            import psycopg
            from psycopg.rows import dict_row
            with database_channel(container) as directory:
                with psycopg.connect(config['DATABASE_URL'],host=directory,port=5432,row_factory=dict_row,
                                    application_name='pcp-local-retirement',connect_timeout=10) as conn:
                    yield conn
    storage=Maintenance()
    if args.plan_out:
        require(not args.manifest and not args.approval,'retirement_plan_arguments_conflict')
        m=plan(storage,job_id=args.job_id,instance=args.instance,database_container=args.database_container,workers=args.worker,
               decision_id=args.decision_id,reason=args.reason)
        target=Path(args.plan_out)
        require(target.parent.stat().st_uid==os.getuid() and
                stat.S_IMODE(target.parent.stat().st_mode)==0o700,'retirement_private_custody_required')
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:json.dump(m,f,indent=2);f.write('\n')
        print(json.dumps({'planned':True,'apply':False,'manifest_sha256':digest(m)}));return
    require(bool(args.manifest and args.approval),'retirement_manifest_and_approval_required')
    approval=private_json(args.approval)
    if args.apply:
        root=Path(__file__).resolve().parents[1]
        head=subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
        dirty=subprocess.run(['git','-C',str(root),'status','--porcelain'],capture_output=True,text=True,check=True).stdout
        require(head==approval.get('accepted_source') and not dirty,'retirement_reviewed_source_required')
    result=retire(storage,manifest,approval,
                  apply=args.apply,check_quiescent=stopped_workers)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    try:main()
    except (TaskStop,OSError,ValueError) as exc:
        print(json.dumps({'stopped':getattr(exc,'code','retirement_input_or_custody_invalid')}),file=sys.stderr)
        raise SystemExit(2)
    except Exception:
        # A COMMIT response may have been lost. No connection strings, SQL or
        # raw exception details. Preserve files and reconcile the same decision.
        print(json.dumps({'stopped':'retirement_outcome_uncertain_reconcile_same_manifest'}),file=sys.stderr)
        raise SystemExit(3)
