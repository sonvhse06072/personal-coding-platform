"""Real ordinary worker/Executor/Git/PG; synthetic provider/GitHub transports.

No model, live instance or recovery permit. Actual CLI/kernel isolation is a
separate credential-free actual-image probe, not claimed by transport doubles.
"""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import pytest
from app import pcp_local_worker_loop as w, pcp_local_readiness as readiness
from app.adapters import codex
from app.pcp_local_task_queue import REPOSITORY
from app.shell import CommandResult
from app.dashboard_local import build_local_snapshot
from pcp_sparse_fixture import produce_workspace, sparse_verified  # noqa:F401
from test_pcp_local_consolidation import verified  # noqa:F401
from test_pcp_local_consolidation_postgres import database, ownership  # noqa:F401
from test_pcp_local_runtime_dispatch import setup  # noqa:F401
from test_pcp_local_repeatability import lifecycle, ordinary_B, ordinary_successor  # noqa:F401

CODEX_RUN = codex.CodexAdapter.run


def ordinary_execution(b, monkeypatch, *, lost_ack=False):
    calls, remote = [], {}
    task, path = b.task, b.s.root / b.id
    changed = next(p for p in task.allowed_paths if p.startswith('tests/'))
    async def command(argv, **kwargs):
        assert argv[:3] == ['codex', 'exec', '--json'] and kwargs['cwd'] == path and 'env' not in kwargs
        temporary=path/b.s.db.get(b.id)['checkpoint']['pcp_local_temporary']['created']['root']
        assert '--ignore-user-config' in argv and codex.isolated_permissions(path,temporary) in argv
        assert any(v.startswith('shell_environment_policy.set=') and str(temporary) in v
                   and 'PYTEST_ADDOPTS' in v and 'pytest-cache' in v for v in argv)
        (temporary/'ordinary-output').write_text('synthetic private output')
        calls.append('synthetic_provider')
        target = path / changed; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('def test_synthetic_task(): assert 2 + 2 == 4\n')
        return CommandResult(argv, 0, '{"type":"turn.completed","usage":{"input_tokens":0,"output_tokens":0}}', '')
    monkeypatch.setattr(codex.CodexAdapter, 'run', CODEX_RUN)
    monkeypatch.setattr(codex, 'run_command', command)
    # Process-wide hardening is covered by the actual-image probe, not pytest.
    monkeypatch.setattr('app.security.harden_runtime_process_secret_boundary', lambda: None)
    async def create(**kw):
        assert kw['job_id'] == b.id and kw['ref'] == task.base_sha
        calls.append('executor_producer')
        return produce_workspace(b.s.root.parent, task)
    async def phase(**kw):
        calls.append(kw['phase'])
        result = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', changed],
            cwd=path, capture_output=True, text=True, timeout=20)
        return dict(passed=result.returncode == 0, commands=[dict(returncode=result.returncode, stdout=result.stdout)])
    def ci(commit):
        return dict(state='success', repository=REPOSITORY, commit=commit, actions_runs=[dict(
            source='github_actions', run_id=9, id=9, head_sha=commit, name='tests', status='completed',
            conclusion='success', details_url=f'https://github.com/{REPOSITORY}/actions/runs/9')])
    async def publish(**kw):
        calls.append('synthetic_publish'); remote['commit'] = kw['expected_commit']
        return {'commit': remote['commit']}
    async def pr(**kw):
        calls.append('synthetic_pr')
        remote['pr'] = dict(number=7, head=kw['expected_commit'], head_ref=kw['branch'], base_ref='main',
            repository=REPOSITORY, state='open', merged=False)
        if lost_ack: raise ConnectionError('synthetic acknowledgement loss after publication')
        return remote['pr']
    async def checks(**kw): calls.append('synthetic_ci'); return ci(kw['commit'])
    async def reconcile(**kw):
        calls.append('synthetic_reconcile'); assert kw['expected_commit'] == remote['commit']
        return dict(reconciled=True, delivery={**remote['pr'], 'ci': ci(remote['commit'])})
    b.engine.ddev = SimpleNamespace(create_workspace=create, phase=phase, publish_branch=publish,
        upsert_pull_request=pr, github_ci=checks, github_reconcile_delivery=reconcile)
    observe = w.TrustedReaders.executor
    async def executor(self, endpoint, payload):
        if endpoint != '/v1/pcp-local/pm-review': return await observe(self, endpoint, payload)
        row = b.s.db.get(b.id)
        return dict(job_id=b.id, expected_head=remote['commit'], activation_digest=w.digest(b.activation),
            report={'verdict': 'pass', 'diff_hash': row['result']['diff']['diff_hash']},
            pr=remote['pr'], ci=ci(remote['commit']))
    monkeypatch.setattr(w.TrustedReaders, 'executor', executor)
    return calls, path


@pytest.mark.parametrize('lifecycle', ['executor_sparse'], indirect=True)
@pytest.mark.parametrize('lost_ack', [False, True])
def test_finalized_A_then_ordinary_B_then_ordinary_C(ordinary_B, monkeypatch, tmp_path, lost_ack):
    b = ordinary_B; s = b.s
    retained = {s.id: (s.db.get(s.id), w._retained_snapshot(s.path))}
    all_calls = []
    for label, generation in (('B', 2), ('C', 3)):
        from app import shell, pm_bridge
        monkeypatch.setattr(pm_bridge, 'PMBridgeGitHubClient', lambda: b.reader.github)
        async def tool_identity(argv, **kwargs):
            if argv == ['codex', '--version']:
                return CommandResult(argv, 0, 'codex-cli 0.160.0', '')
            assert argv[0] == 'git' and argv[-2] == 'var'
            result = subprocess.run(argv, cwd=kwargs['cwd'], capture_output=True, text=True, timeout=10)
            return CommandResult(argv, result.returncode, result.stdout, result.stderr)
        monkeypatch.setattr(shell, 'run_command', tool_identity)
        calls, path = ordinary_execution(b, monkeypatch, lost_ack=lost_ack and label == 'B')
        from app.delivery import DeliveryError
        if lost_ack and label == 'B':
            with pytest.raises(DeliveryError): asyncio.run(b.engine.run_pcp_local_once())
            asyncio.run(b.engine.retry_pcp_local_delivery())
            assert calls[-1] == 'synthetic_reconcile'
        else: asyncio.run(b.engine.run_pcp_local_once())
        assert calls.count('synthetic_provider') == calls.count('synthetic_publish') == calls.count('synthetic_pr') == 1
        row = s.db.get(b.id)
        assert set(row['checkpoint']['pcp_local_source']['observations']) == w.OBSERVER_PARTS
        assert row['error'] == 'awaiting_independent_pm_review'
        assert row['progress']['model_calls'] == 1 and row['progress']['test_runs'] == 2
        assert not any(k in row['checkpoint'] for k in ('pcp_local_claim_recovery', 'pcp_local_held_verification'))
        before = w._retained_snapshot(path)
        ready = asyncio.run(readiness.collect_readiness(b.engine, phase='finalization', job_id=b.id, review_id=7))
        assert ready['ready'], ready
        asyncio.run(b.engine.finalize_pcp_local_review(SimpleNamespace(**ready['identity'])))
        after = s.db.get(b.id)
        assert after['status'] == 'completed' and after['progress'] == row['progress']
        receipt = next(r for r in ownership(s.db)[0] if r['job_id'] == b.id)
        lease = ownership(s.db)[1][0]
        assert (receipt['state'], receipt['generation'], lease['state'], lease['generation']) == ('delivered', 3, 'released', generation)
        assert w._retained_snapshot(path) == before
        for job, (original, snapshot) in retained.items():
            assert s.db.get(job) == original and w._retained_snapshot(Path(original['workspace'])) == snapshot
        projected = next(j for j in build_local_snapshot(s.db)['jobs'] if j['id'] == b.id)
        assert projected['assisted_recovery'] is False
        retained[b.id] = (after, before); all_calls.extend(calls)
        if label == 'B':
            successor = SimpleNamespace(db=s.db, v=SimpleNamespace(task=b.task), engine=b.engine, id=b.id,
                path=path, root=s.root, base=s.base, activation=b.activation, project=b.project)
            b = ordinary_successor(successor, monkeypatch, tmp_path)
    assert len(retained) == 3 and all_calls.count('synthetic_provider') == 2


@pytest.mark.parametrize('lifecycle', ['executor_sparse'], indirect=True)
@pytest.mark.parametrize('config_kind', ['retained_trust', 'permissions', 'symlink'])
def test_retained_config_blocks_ordinary_claim_without_mutation(ordinary_B, monkeypatch, config_kind):
    import json, os
    from app.pcp_local_task_queue import TaskStop
    b = ordinary_B; s = b.s
    home = Path(os.environ['CODEX_HOME']); home.mkdir()
    config = home / 'config.toml'
    if config_kind == 'retained_trust':
        config.write_text('[projects.' + json.dumps(str(s.path)) + ']\ntrust_level="trusted"\n')
    elif config_kind == 'permissions':
        config.write_text('[permissions.pcp_local]\nextends=":all"\n')
    else:
        target = home / 'untrusted'; target.write_text('SYNTHETIC_UNREADABLE_CONFIG')
        config.symlink_to(target)
    original = (config.lstat(), config.read_bytes())
    before = s.db.get(s.id), ownership(s.db), w._retained_snapshot(s.path)
    with pytest.raises(TaskStop, match='unreviewed_codex_configuration'):
        asyncio.run(b.dispatch())
    assert s.db.get(b.id) is None
    assert (s.db.get(s.id), ownership(s.db), w._retained_snapshot(s.path)) == before
    assert config.read_bytes() == original[1]
    assert config.lstat().st_mtime_ns == original[0].st_mtime_ns
    assert config.lstat().st_ctime_ns == original[0].st_ctime_ns
