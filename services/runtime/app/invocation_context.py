"""Ordinary local integration of the shared Composer. No network or model."""
from pathlib import Path
import hashlib
import re
import time

from .context_memory import ContextCannotProve, compose_invocation_context


def local_invocation_context(row, task, *, role='developer', verification=None):
    started = time.perf_counter()
    from .pcp_local_worker_loop import (stable_job_id, claimed_source_receipt, exact_value,
                                      _retained_repository, _retained_run)
    checkpoint = row.get('checkpoint') or {}
    goal = (row.get('task') or {}).get('description')
    if (not isinstance(goal, str) or hashlib.sha256(goal.encode()).hexdigest() != task.goal_sha256
            or row.get('id') != stable_job_id(task) or row.get('project_id') != task.project_id
            or row.get('source_commit') != task.base_sha
            or not exact_value(checkpoint.get('pcp_local_source', {}).get('receipt'), claimed_source_receipt(task))):
        raise ContextCannotProve('original_task_or_receipt_changed')
    baseline = checkpoint.get('project_baseline') or {}
    if any(not re.fullmatch('[a-f0-9]{40}', value) for value in (task.base_sha, task.baseline_source_commit)):
        raise ContextCannotProve('exact_source_identity_required')
    identity = dict(repository=task.repository, project_id=task.project_id, job_id=row['id'],
        issue_number=task.issue_number, body_sha256=task.body_sha256, goal_sha256=task.goal_sha256,
        source_commit=task.base_sha, baseline_revision=task.baseline_revision,
        baseline_source_commit=task.baseline_source_commit)
    result = row.get('result') or {}
    with _retained_repository(Path(row['workspace'])) as (clone, home):
        def read_source(commit, path):
            raw = _retained_run(['git', '-C', str(clone), 'ls-tree', '-z', commit, '--', path], home)
            entries = [entry for entry in raw.split(b'\0') if entry]
            if len(entries) != 1:
                raise ContextCannotProve('baseline_blob_missing:' + path)
            metadata, name = entries[0].split(b'\t', 1)
            mode, kind, oid = metadata.split()
            if mode not in (b'100644', b'100755') or kind != b'blob' or name.decode() != path:
                raise ContextCannotProve('baseline_blob_not_regular:' + path)
            return _retained_run(['git', '-C', str(clone), 'cat-file', 'blob', oid.decode()], home)
        packet = compose_invocation_context(identity=identity,
            contract=dict(goal=goal, allowed_paths=list(task.allowed_paths)), baseline=baseline,
            read_source=read_source, role=role,
            evidence=dict(verification=verification or result.get('verification') or {},
                          diff=result.get('diff') or {}, commit=result.get('commit')))
    for key in ('invocation_context', 'review_context'):
        previous = checkpoint.get(key) or {}
        if previous and previous.get('authority_sha256') != packet['manifest']['authority_sha256']:
            raise ContextCannotProve('persisted_context_authority_changed')
    packet['manifest']['total_context_ms'] = round((time.perf_counter()-started)*1000, 3)
    return packet
