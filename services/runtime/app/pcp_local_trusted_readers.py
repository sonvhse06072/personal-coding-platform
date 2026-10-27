"""PCP-local operational authority, read afresh from service-owned sources.

Nothing here activates a worker on import. The activation document is installed
under the read-only /config mount by the separately authorized operator, never
accepted from an issue or an HTTP request. It names identities and limits; live
facts come from PostgreSQL, Executor, Router and the subscription CLI.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time

import httpx
import yaml

from .pcp_local_task_queue import PROJECT_ID, REPOSITORY, require, verify_issue
from .pcp_local_worker_loop import RuntimeObservation, stable_job_id, OBSERVER_PARTS

ACTIVATION_FILE = Path('/config/pcp-local-activation.json')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_activation():
    """A switch is not authority: require an independently installed document."""
    require(not ACTIVATION_FILE.is_symlink() and ACTIVATION_FILE.is_file(),
            'pcp_local_operational_delegation_missing')
    value = json.loads(ACTIVATION_FILE.read_text())
    require(type(value) is dict and value.get('project_id') == PROJECT_ID
            and value.get('repository') == REPOSITORY
            and type(value.get('expires_at')) in (int, float)
            and time.time() < value['expires_at']
            and type(value.get('issue_number')) is int
            and value['issue_number'] > 0
            and value.get('developer_permission_mode') == 'bounded',
            'pcp_local_operational_delegation_invalid')
    return value


class TrustedReaders:
    """The concrete eight readers. Callables/dictionaries are not wire inputs."""
    def __init__(self, engine, github):
        self.engine, self.github = engine, github
        self.activation = read_activation()
        self.route = None
        self.task = None
        self.snapshot = None
        self.lease_generation = None
        self.authority_digest = None

    async def executor(self, path, payload):
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(self.engine.ddev.base + path,
                json=payload, headers=self.engine.ddev.headers)
            response.raise_for_status()
            return response.json()

    def authority(self):
        from . import config
        from .baseline import resolve_project_baseline
        require(read_activation() == self.activation, 'pcp_local_delegation_revoked')
        # Do not allow cached baseline/model files to survive a revocation.
        config.project_baselines_doc.cache_clear()
        config.models_doc.cache_clear()
        config.routing_policy_doc.cache_clear()
        projects = config.projects_doc().get('projects', {})
        require(set(projects) == {PROJECT_ID}, 'pcp_local_singleton_required')
        project = config.project_config(PROJECT_ID)
        require(project.get('repository') == REPOSITORY
                and project.get('registration_status') == 'approved'
                and project.get('base_branch') == 'main'
                and project['runtime'].get('workspace_mode') == 'isolated_clone'
                and project['runtime'].get('developer_permission_mode') == 'bounded'
                and project.get('ddev', {}).get('enabled') is True,
                'pcp_local_project_not_operational')
        baseline = resolve_project_baseline(PROJECT_ID, self.activation['baseline_revision'])
        active = config.project_baselines_doc()['projects'][PROJECT_ID]['active_revision']
        require(baseline is not None and baseline.revision == active
                and baseline.source_commit == self.activation['baseline_source_commit'],
                'pcp_local_baseline_revoked')
        revision = digest({'project': project, 'baseline': baseline.model_dump(mode='json'),
                           'models': config.models_doc(), 'policy': config.routing_policy_doc()})
        require(self.authority_digest is None or self.authority_digest == revision,
                'pcp_local_authority_changed')
        self.authority_digest = revision
        return project, baseline

    async def source(self):
        self.authority()
        a = self.activation
        issue = await self.github.local_source_issue(issue_number=a['issue_number'])
        task = verify_issue(issue, **{k: a[k] for k in (
            'issue_number', 'body_sha256', 'base_sha', 'baseline_revision', 'baseline_source_commit')})
        require(self.task is None or task == self.task, 'pcp_local_source_revoked')
        self.task = task
        return task, issue

    async def refresh(self, task):
        from .config import model_config
        from .model_capabilities import validate_model_choice
        from .quota_telemetry import CodexQuotaCollector
        from .shell import run_command
        observed_at = time.monotonic()
        project, baseline = self.authority()
        checked, issue = await self.source()
        require(checked == task, 'pcp_local_wrong_task')
        job_id = stable_job_id(task)
        proof = await self.executor('/v1/pcp-local/observe', {
            'job_id': job_id, 'source_commit': task.base_sha,
            'activation_digest': digest(self.activation),
        })
        require(proof.get('job_id') == job_id and proof.get('source_commit') == task.base_sha
                and proof.get('activation_digest') == digest(self.activation),
                'pcp_local_executor_binding_invalid')
        roots = list(self.engine.workspace_root.iterdir())
        require(all(p.name == job_id and p.is_dir() and not p.is_symlink() for p in roots),
                'pcp_local_foreign_workspace')
        require(not Path('/var/run/docker.sock').exists()
                and not any(os.getenv(k) for k in ('GITHUB_DELIVERY_TOKEN', 'GITHUB_TOKEN', 'GH_TOKEN'))
                and not (Path.home() / '.ssh').exists(), 'pcp_local_runtime_credential_boundary')
        with self.engine.storage.connect() as conn:
            foreign = conn.execute('SELECT id FROM cp_jobs WHERE project_id<>%s LIMIT 1', (PROJECT_ID,)).fetchone()
            require(foreign is None, 'pcp_local_database_not_dedicated')
            rows = conn.execute('SELECT id FROM cp_jobs WHERE project_id=%s AND status NOT IN '
                "('completed','failed','cancelled') AND id<>%s", (PROJECT_ID, job_id)).fetchall()
            lease = conn.execute('SELECT * FROM cp_project_leases WHERE project_id=%s',
                                 (PROJECT_ID,)).fetchone()
        require(not rows, 'pcp_local_other_writer')
        if self.lease_generation is None:
            require(lease is None or lease['state'] == 'released', 'pcp_local_writer_busy')
        else:
            require(lease is not None and lease['state'] == 'active'
                    and lease['owner_job_id'] == job_id
                    and lease['generation'] == self.lease_generation,
                    'pcp_local_lease_revoked')
        if self.route is None:
            self.route = await self.engine.router.route({
                'job_id': job_id, 'project_id': PROJECT_ID, 'repository': REPOSITORY,
                'source_commit': task.base_sha,
                'task': {'title': f'PCP-local issue #{task.issue_number}',
                         'description': issue['body'], 'task_type': 'implementation'},
                'repo': {'estimated_files': len(task.allowed_paths), 'tests_available': True},
            })
        strategy = self.route['strategy']
        require(not strategy.get('human_decision', {}).get('required'),
                'pcp_local_protected_decision_pending')
        choice = strategy['executor']
        validate_model_choice(choice)
        require(choice['adapter'] == 'codex_cli'
                and model_config(choice['id']).get('kind') == 'agent',
                'pcp_local_selected_adapter_not_supported')
        version = await run_command(['codex', '--version'], cwd='/tmp', timeout=10)
        require(version.returncode == 0 and version.stdout.strip() ==
                'codex-cli ' + self.activation['codex_version'], 'pcp_local_cli_version_mismatch')
        quota = await CodexQuotaCollector().collect()
        relevant = [q for q in quota if q.get('provider') == 'openai'
                    and q.get('state_key') in ('provider:openai', 'quota:model:' + choice['id'])]
        require(bool(relevant) and all(q.get('authoritative') is True
                and q.get('available') is True for q in relevant), 'pcp_local_provider_unavailable')
        limits = self.activation['budget']
        rights = project['autonomy']
        normalized_lease = None if lease is None else {k: lease[k] for k in (
            'project_id', 'owner_job_id', 'generation', 'state')}
        self.snapshot = {
            'project': dict(project_id=PROJECT_ID, repository=REPOSITORY, base_branch='main',
                            registered=True, allow_create_pr=rights.get('allow_create_pr'),
                            allow_production_deploy=rights.get('allow_production_deploy')),
            'baseline': dict(project_id=PROJECT_ID, revision=baseline.revision,
                             source_commit=baseline.source_commit, active_revision=baseline.revision,
                             status='approved'),
            'isolation': {**proof['isolation'], 'workspace_mode': 'isolated_clone',
                          'workspace_lease_state': 'free', 'active_writers': 0},
            'provider': dict(adapter='codex_cli', model=choice['model'],
                effort=choice['reasoning_effort'], installed_cli_version=self.activation['codex_version'],
                approved_cli_version=self.activation['codex_version'], **proof['provider']),
            'budget': dict(owner_approved=True, provider_quota_verified=True,
                max_changed_files=len(task.allowed_paths), **limits),
            'writer': dict(project_id=PROJECT_ID, workspace_mode='isolated_clone',
                           lease=normalized_lease, other_job_ids=[]),
            'publisher': proof['publisher'],
            'model_choice': {k: choice[k] for k in ('id','adapter','model','reasoning_effort')},
        }
        require(time.monotonic() - observed_at < 30, 'pcp_local_observation_expired')
        self.authority()
        return self.snapshot

    def readers(self):
        # RuntimeTaskAttestor iterates sorted keys: refresh all live sources once
        # per complete observation, rather than collecting quota eight times.
        async def read(key, task):
            if key == min(OBSERVER_PARTS):
                await self.refresh(task)
            require(self.snapshot is not None, 'pcp_local_observation_missing')
            value = deepcopy(self.snapshot[key])
            now = time.monotonic()
            return RuntimeObservation(value, digest({'task': vars(task), 'value': value,
                'activation': self.activation, 'authority': self.authority_digest}), now, now + 30)
        return {k: lambda task, key=k: read(key, task) for k in OBSERVER_PARTS}
