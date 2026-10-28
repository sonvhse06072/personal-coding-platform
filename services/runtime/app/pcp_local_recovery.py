"""Same verified job only. No model invocation or generic state-edit interface."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import os
import shutil
import tempfile
from pathlib import Path
import subprocess

from .pcp_local_task_queue import require, PROJECT_ID


def git(workspace, *args):
    return subprocess.check_output(['git', '-C', str(workspace), *args], text=True).strip()


def candidate_tree(workspace):
    """Build Git's complete candidate identity without changing the real index.

    Mirror commit_changes staging, including sparse tracked paths and modes.
    The private index is scratch; the resulting immutable tree is only evidence.
    """
    from .repo import _is_runtime_ignored_untracked
    with tempfile.TemporaryDirectory(prefix='pcp-proof-') as scratch:
        index = Path(scratch) / 'index'
        source = Path(git(workspace, 'rev-parse', '--absolute-git-dir')) / 'index'
        shutil.copyfile(source, index)
        env = {**os.environ, 'GIT_INDEX_FILE': str(index)}
        def run(*args):
            return subprocess.check_output(['git', '-C', str(workspace), '-c',
                'core.filemode=true', *args], env=env)
        run('add', '-u', '--', '.', ':(exclude).ddev/config.coding-platform.yaml')
        untracked = [os.fsdecode(p) for p in run('ls-files', '--others', '--exclude-standard', '-z').split(b'\0')
                     if p and not _is_runtime_ignored_untracked(os.fsdecode(p))]
        if untracked:
            run('add', '--', *untracked)
        return run('write-tree').decode().strip()


def verified_tree(workspace, task, diff):
    """Use the verifier's complete file-manifest contract, not only changed paths."""
    excluded = {'.git', '.ddev', '.venv', '__pycache__', '.pytest_cache'}
    entries = {}
    for path in sorted(Path(workspace).rglob('*')):
        rel = path.relative_to(workspace)
        if rel.parts[0] in excluded:
            continue
        require(not path.is_symlink(), 'pcp_local_verified_symlink')
        if path.is_file():
            entries[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    from .repo import diff_state
    actual = diff_state(Path(workspace), 750000, base_ref=task.base_sha)
    require(actual['diff_hash'] == diff['diff_hash'], 'pcp_local_verified_diff_changed')
    return dict(tree=candidate_tree(workspace), source=task.base_sha, branch=git(workspace, 'branch', '--show-current'),
                parent=git(workspace, 'rev-parse', 'HEAD'), files=entries, diff_hash=actual['diff_hash'])


def commit_verified(engine, job_id, task, workspace, checkpoint):
    from .repo import commit_changes
    proof = checkpoint['pcp_local_execution']
    require(verified_tree(workspace, task, proof['diff']) == proof['verified_tree'],
            'pcp_local_verified_tree_changed')
    # Intent is durable before Git can have an uncertain side effect.
    proof['state'] = 'commit_uncertain'
    engine.storage.update(job_id, checkpoint=checkpoint)
    commit_changes(Path(workspace), f'PCP-local issue #{task.issue_number}')
    return reconcile_commit(dict(workspace=str(workspace), checkpoint=checkpoint), task)


def reconcile_commit(row, task):
    """Read-only reconciliation; an absent/unknown commit is never retried."""
    from .repo import diff_state
    proof = row['checkpoint']['pcp_local_execution']
    workspace = Path(row['workspace'])
    expected = proof['verified_tree']
    current = verified_tree(workspace, task, proof['diff'])
    require(current['files'] == expected['files'] and current['source'] == expected['source']
            and current['branch'] == expected['branch'] and current['tree'] == expected.get('tree'), 'pcp_local_recovery_tree_changed')
    commit = git(workspace, 'rev-parse', 'HEAD')
    require(commit != expected['parent'] and git(workspace, 'show', '-s', '--format=%P', 'HEAD').split() == [expected['parent']]
            and git(workspace, 'rev-parse', 'HEAD^{tree}') == expected.get('tree')
            and not git(workspace, 'status', '--porcelain'), 'pcp_local_commit_outcome_unknown')
    # Clean working tree + exact cumulative diff binds the commit to verification.
    diff = diff_state(workspace, 750000, base_ref=task.base_sha)
    require(diff['diff_hash'] == expected['diff_hash'], 'pcp_local_recovery_diff_changed')
    return commit


async def recover_verified_job(engine, readers, task, row):
    """Called under the existing project operation lock; requires fresh readers.

    This only consumes evidence written by the new successful-verification seam.
    Legacy held/null results need the separately approved forensic procedure.
    """
    from .pcp_local_worker_loop import stable_job_id
    job_id = stable_job_id(task)
    cp = deepcopy(row['checkpoint'])
    proof = cp.get('pcp_local_execution') or {}
    require(row['id'] == job_id and row['project_id'] == PROJECT_ID
            and row['source_commit'] == task.base_sha
            and proof.get('state') in {'verified_uncommitted', 'commit_uncertain'}
            and proof.get('authority_digest') == readers.authority_digest
            and proof.get('verification', {}).get('passed') is True
            and proof['verification'].get('test_runs', 0) > 0
            and proof.get('route') == row['route']
            and proof.get('verified_tree', {}).get('source') == task.base_sha
            and row['branch'] == 'ai/' + job_id[:12], 'pcp_local_recovery_evidence_invalid')
    readers.route = row['route']
    readers.lease_generation = proof['lease_generation']
    await readers.refresh(task)
    if proof['state'] == 'verified_uncommitted':
        require(verified_tree(row['workspace'], task, proof['diff']) == proof['verified_tree'],
                'pcp_local_recovery_tree_changed')
        cp['pcp_local_execution']['state'] = 'commit_uncertain'
        engine.storage.cas_local_checkpoint(row, cp, status='blocked', result=row.get('result'))
        from .repo import commit_changes
        commit_changes(Path(row['workspace']), f'PCP-local issue #{task.issue_number}')
        row = engine.storage.get(job_id)
    commit = reconcile_commit(row, task)
    cp = deepcopy(row['checkpoint'])
    cp['pcp_local_execution'].update(state='verified', commit=commit)
    cp['pcp_local_recovery'] = dict(kind='same_job_non_model', commit=commit)
    result = dict(status='accepted', branch=row['branch'], commit=commit, diff=proof['diff'],
                  verification=proof['verification'], route=row['route'], delivery_finalized=False)
    engine.storage.cas_local_checkpoint(row, cp, status='delivering', result=result)
    return engine.storage.get(job_id)
