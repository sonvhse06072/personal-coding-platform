"""#831: actual readiness/authority/registrar with external I/O doubled.

No PostgreSQL, container, provider inference or live receipt is touched.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.metadata
from types import SimpleNamespace

import pytest

from app import config, pcp_local_readiness, pcp_local_worker_loop as worker
from app import pm_bridge, quota_telemetry, shell
from app.pcp_local_task_queue import TaskStop
from test_pcp_local_runtime_dispatch import setup, claimed


@pytest.fixture
def operational(setup, monkeypatch, tmp_path):
    s = setup
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'synthetic-provider'))
    activation = {key: getattr(s.task, key) for key in (
        'issue_number', 'body_sha256', 'base_sha', 'baseline_revision',
        'baseline_source_commit')}
    monkeypatch.setattr(worker, 'read_activation', lambda: deepcopy(activation))
    monkeypatch.setattr(config, 'projects_doc', lambda: {'projects': {'pcp-local': s.project}})
    # The dispatch fixture replaces this cached reader; retain invalidation API.
    monkeypatch.setattr(config.project_baselines_doc, 'cache_clear', lambda: None, raising=False)
    monkeypatch.setattr(pm_bridge, 'PMBridgeGitHubClient', lambda: s.github)
    monkeypatch.setattr(pcp_local_readiness, 'schema_readiness', lambda storage: [])

    async def identity(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout='PCP Local <pcp-local@localhost> 123 +0000')

    async def quota(*args):
        return []  # Account I/O is external to this project-policy regression.

    async def refresh(reader, task):
        assert task == s.task
        reader.authority()  # Real shared project/baseline/digest checks.
        reader.snapshot = deepcopy(s.facts)

    monkeypatch.setattr(shell, 'run_command', identity)
    monkeypatch.setattr(quota_telemetry.CodexQuotaCollector, 'collect', quota)
    monkeypatch.setattr(worker.TrustedReaders, 'refresh', refresh)
    monkeypatch.setattr(importlib.metadata, 'version',
                        lambda name: {'pytest': '8.4.1', 'PyYAML': '6.0.2'}[name])
    return s


def test_approved_exclusive_project_passes_readiness_and_registers_once(operational):
    s = operational
    assert s.project['runtime']['exclusive_project_lease'] is True
    before = deepcopy((s.db.receipts, s.db.jobs, s.db.lease, s.db.events))
    view = asyncio.run(pcp_local_readiness.collect_readiness(s.engine))
    assert view == dict(ready=True, blockers=[], model_invocations=0, job_registrations=0)
    assert (s.db.receipts, s.db.jobs, s.db.lease, s.db.events) == before
    result = asyncio.run(s.dispatch())
    job_id = worker.stable_job_id(s.task)
    assert result['runtime_job_state'] == 'queued'
    assert list(s.db.jobs) == s.engine.queue.submissions == [job_id]
    assert s.db.jobs[job_id]['progress']['model_calls'] == 0
    assert claimed(s)['state'] == 'claimed' and claimed(s)['generation'] == 1
    # Execution acquires the exclusive lease only after its later running CAS.
    assert s.db.lease is None


@pytest.mark.parametrize('section,key,value', [
    ('runtime', 'exclusive_project_lease', False),
    ('runtime', 'exclusive_project_lease', None),
    ('runtime', 'exclusive_project_lease', 1),
    ('runtime', 'exclusive_project_lease', 'true'),
    ('runtime', 'workspace_mode', 'direct'),
    ('runtime', 'developer_permission_mode', 'unrestricted'),
    ('autonomy', 'allow_commit', False),
    ('autonomy', 'allow_push_ai_branch', False),
    ('autonomy', 'allow_create_pr', False),
    ('autonomy', 'allow_production_deploy', True),
    ('ddev', 'enabled', False),
])
def test_bad_project_is_not_ready_and_run_once_cannot_record_receipt(
        operational, monkeypatch, section, key, value):
    s = operational
    if value is None:
        del s.project[section][key]
    else:
        s.project[section][key] = value
    before = deepcopy((s.db.receipts, s.db.jobs, s.db.lease, s.db.events))

    def forbidden(*args, **kwargs):
        pytest.fail('Invalid operational project reached receipt registration')

    monkeypatch.setattr(worker.LocalSourceQueueStore, 'record', forbidden)
    view = asyncio.run(pcp_local_readiness.collect_readiness(s.engine))
    assert view['ready'] is False
    assert [(b['component'], b['code']) for b in view['blockers']] == [
        ('trusted_sources', 'pcp_local_project_not_operational')]
    assert view['model_invocations'] == view['job_registrations'] == 0
    with pytest.raises(TaskStop, match='pcp_local_readiness_blocked:trusted_sources/pcp_local_project_not_operational'):
        asyncio.run(s.engine.run_pcp_local_once())
    assert (s.db.receipts, s.db.jobs, s.db.lease, s.db.events) == before
    assert not s.engine.queue.submissions and s.github.calls == 0


@pytest.mark.parametrize('section,key,value', [
    ('runtime', 'exclusive_project_lease', False),
    ('runtime', 'exclusive_project_lease', 1),
    ('autonomy', 'allow_commit', False),
    ('autonomy', 'allow_production_deploy', True),
    ('ddev', 'enabled', False),
])
def test_project_drift_at_locked_insert_preserves_claim_without_job(
        operational, section, key, value):
    s = operational
    assert asyncio.run(pcp_local_readiness.collect_readiness(s.engine))['ready']
    s.db.before_registration = lambda: s.project[section].__setitem__(key, value)
    with pytest.raises(TaskStop, match='launch_uncertain') as error:
        asyncio.run(s.dispatch())
    assert error.value.__cause__.code == 'pcp_local_project_not_operational'
    assert claimed(s)['state'] == 'claimed' and claimed(s)['generation'] == 1
    assert not s.db.jobs and not s.db.events and not s.engine.queue.submissions
    assert s.db.lease is None
    retained = deepcopy((s.db.receipts, s.db.jobs, s.db.lease))
    # Correcting policy later does not grant replay of a consumed claim.
    s.project[section][key] = key != 'allow_production_deploy'
    assert asyncio.run(s.dispatch())['status'] == 'PCP_LOCAL_QUEUE_IDLE_NOT_DISPATCHED'
    assert (s.db.receipts, s.db.jobs, s.db.lease) == retained
