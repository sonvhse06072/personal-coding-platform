"""Offline observe-path regressions; sanitized inspect data is not live adoption."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import main as executor


def digest_config(row):
    data = {key: row[key] for key in ('Name', 'Config', 'HostConfig', 'Mounts')}
    data['Mounts'] = sorted(data['Mounts'], key=lambda mount: mount['Destination'])
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@pytest.fixture
def topology(tmp_path, monkeypatch):
    saved = json.loads((Path(__file__).parent / 'fixtures/pcp_local_observer_inspect.json').read_text())
    root = tmp_path / 'pcp-local-observer-test'
    root.mkdir()
    data = json.loads(json.dumps(saved).replace(saved['root'], str(root)).replace(
        'pcp-local-adoption825-v4', root.name))
    observer, frontend, network = (data[k] for k in ('observer', 'frontend', 'network'))
    binding = {
        'version': 1, 'network_id': network['Id'],
        'config_root': str(root / 'releases/observer828-51349be/config'),
        'observer': {'container_id': observer['Id'], 'image_id': observer['Image'],
                     'source_commit': '51349be73b54ca2fb827a4becc30e00ba62acd7d',
                     'configuration_sha256': digest_config(observer)},
        'frontend': {'container_id': frontend['Id'], 'image_id': frontend['Image'],
                     'configuration_sha256': digest_config(frontend)},
    }
    image = 'sha256:' + 'a' * 64
    activation = dict(root=str(root), issue_number=888, body_sha256='b'*64,
                      base_sha='c'*40, baseline_revision='fixture-only',
                      runtime_network=network['Name'], runtime_image_id=image,
                      verification_image=image, observer_binding=binding)
    job = hashlib.sha256((f"pcp-local:v1:{executor._PCP_REPOSITORY}:888:"
                          f"{activation['body_sha256']}:{activation['base_sha']}:fixture-only").encode()).hexdigest()[:32]
    project = {'repository': executor._PCP_REPOSITORY, 'registration_status': 'approved',
               'path': str(root / 'sources/personal-coding-platform'),
               'runtime': {'workspace_mode': 'isolated_clone', 'developer_permission_mode': 'bounded'},
               'autonomy': {'allow_create_pr': True}}
    worker = {'Name': '/' + root.name + '-coding-runtime', 'State': {'Running': True}, 'Image': image,
              'HostConfig': {'Tmpfs': {'/tmp': 'rw'}, 'Privileged': False, 'ReadonlyRootfs': True},
              'Mounts': [{'Type': 'bind', 'Source': source, 'Destination': target, 'RW': rw}
                         for target, source, rw in [('/config', str(root/'instance/config'), False),
                         (str(root/'workspaces'), str(root/'workspaces'), True),
                         ('/home/coder', str(root/'runtime-home'), True)]],
              'NetworkSettings': {'Networks': {network['Name']: {'NetworkID': network['Id']}}}}
    # Complete the four legacy peers; observer and frontend remain the captured topology.
    for n, service in enumerate(('coding-runtime', 'router', 'ddev-executor')):
        network['Containers'][str(n+1)*64] = {'Name': root.name+'-'+service}
    worker_image = {'Id': image, 'Config': {'Env': ['PATH=/usr/bin'], 'Labels': {
        'org.pcp.local.instance': root.name, 'org.opencontainers.image.revision': activation['base_sha']}}}
    records = {('network', network['Name']): network,
               ('container', root.name+'-coding-runtime'): worker,
               ('container', observer['Id']): observer, ('container', frontend['Id']): frontend,
               **{('image', k): v for k, v in data['images'].items()}, ('image', image): worker_image}
    inspections, publisher = [], []
    def inspect(kind, identity, **kwargs):
        inspections.append((kind, identity))
        if (kind, identity) not in records:
            raise executor.HTTPException(409, 'pcp_local_resource_unavailable')
        return deepcopy(records[kind, identity])
    class Client:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            publisher.append((url, kwargs))
            return SimpleNamespace(raise_for_status=lambda: None,
                                   json=lambda: {'permissions': {'push': True}})
    delivery = SimpleNamespace(base='https://fixture.invalid', _client=Client)
    monkeypatch.setattr(executor, '_pcp_activation', lambda: deepcopy(activation))
    monkeypatch.setattr(executor, 'project', lambda _: project)
    monkeypatch.setattr(executor, 'load_projects', lambda: {'pcp-local': project})
    monkeypatch.setenv('CODING_WORKSPACES_ROOT', str(root/'workspaces'))
    monkeypatch.setenv('PLATFORM_INTERNAL_TOKEN', 'fixture-internal-token')
    monkeypatch.setattr(executor, 'project_state', lambda _: {'clean': True, 'head': activation['base_sha']})
    monkeypatch.setattr(executor, '_pcp_docker', inspect)
    monkeypatch.setattr(executor, '_github_context', lambda _: (delivery, executor._PCP_REPOSITORY))
    def run(argv, **kwargs):
        assert argv[1:] == ['Username for HTTPS']
        assert kwargs['env'] == {'PATH': '/usr/bin:/bin'}
        return SimpleNamespace(returncode=0, stdout='x-access-token\n')
    monkeypatch.setattr(executor.subprocess, 'run', run)
    return SimpleNamespace(root=root, activation=activation, binding=binding, observer=observer,
                           frontend=frontend, network=network, records=records, worker=worker,
                           worker_image=worker_image, inspections=inspections, publisher=publisher, job=job)


def observe(t, *, auth=True, extra=None):
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=executor.app),
                                     base_url='http://executor.fixture') as client:
            payload = dict(job_id=t.job, source_commit=t.activation['base_sha'],
                           activation_digest=executor._pcp_digest(t.activation))
            payload.update(extra or {})
            return await client.post('/v1/pcp-local/observe', json=payload,
                headers={'Authorization': 'Bearer fixture-internal-token'} if auth else {})
    return asyncio.run(request())


def test_approved_observer_coexists_through_actual_observe_route(topology):
    t = topology
    response = observe(t)
    assert response.status_code == 200, response.text
    assert response.json()['source_commit'] == t.activation['base_sha']
    assert response.json()['publisher']['allow_merge'] is False
    assert len(t.publisher) == 2  # Existing repository/pull permissions still checked.
    assert ('image', t.activation['runtime_image_id']) in t.inspections
    assert t.binding['observer']['source_commit'] != t.activation['base_sha']
    assert t.frontend['Id'] not in t.network['Containers']  # Shared namespace, no extra peer.


def test_observer_without_trusted_binding_still_blocks(topology):
    del topology.activation['observer_binding']
    response = observe(topology)
    assert response.status_code == 409 and response.json()['detail'] == 'pcp_local_foreign_network_peer'
    assert not topology.publisher


def test_unchanged_four_peer_path(topology):
    t = topology
    del t.activation['observer_binding']; del t.network['Containers'][t.observer['Id']]
    assert observe(t).status_code == 200
    assert all(k != ('container', t.observer['Id']) for k in t.inspections)


def test_http_cannot_supply_binding_and_auth_still_required(topology):
    assert observe(topology, auth=False).status_code == 401
    assert observe(topology, extra={'observer_binding': topology.binding}).status_code == 422
    assert not topology.inspections and not topology.publisher


@pytest.mark.parametrize('bad', [None, {}, [], '', True, {'version': 1}])
def test_malformed_binding_cannot_be_ignored(topology, bad):
    topology.activation['observer_binding'] = bad
    assert observe(topology).status_code == 409
    assert not topology.publisher


@pytest.mark.parametrize('change', [
    'short_id', 'image_tag', 'missing_frontend', 'extra_field', 'bool_version',
    'traversal', 'foreign_config_root', 'missing_observer', 'missing_frontend_container',
    'absent_peer', 'unknown_peer', 'copied_name', 'frontend_peer', 'network_replaced',
    'image_source', 'image_owner', 'image_id', 'container_id', 'image_secret',
    'source_env', 'worker_image_source', 'verification_image',
])
def test_identity_provenance_and_default_closed_peer_rules(topology, change):
    t = topology; b = t.binding; o = t.observer; f = t.frontend
    if change == 'short_id': b['observer']['container_id'] = o['Id'][:12]
    elif change == 'image_tag': b['observer']['image_id'] = 'runtime:latest'
    elif change == 'missing_frontend': del b['frontend']
    elif change == 'extra_field': b['allow_extra_peers'] = True
    elif change == 'bool_version': b['version'] = True
    elif change == 'traversal': b['config_root'] = str(t.root)+'/releases/../config'
    elif change == 'foreign_config_root': b['config_root'] = '/foreign/releases/test/config'
    elif change == 'missing_observer': del t.records['container', o['Id']]
    elif change == 'missing_frontend_container': del t.records['container', f['Id']]
    elif change == 'absent_peer': del t.network['Containers'][o['Id']]
    elif change == 'unknown_peer': t.network['Containers']['f'*64] = {'Name': 'foreign-nginx'}
    elif change == 'copied_name': t.network['Containers']['f'*64] = deepcopy(t.network['Containers'][o['Id']])
    elif change == 'frontend_peer': t.network['Containers'][f['Id']] = {'Name': f['Name'][1:]}
    elif change == 'network_replaced': t.network['Id'] = 'f'*64
    elif change == 'image_source': t.records['image', o['Image']]['Config']['Labels']['org.opencontainers.image.revision'] = 'f'*40
    elif change == 'image_owner': t.records['image', o['Image']]['Config']['Labels']['org.pcp.local.instance'] = 'foreign'
    elif change == 'image_id': t.records['image', o['Image']]['Id'] = 'sha256:'+'f'*64
    elif change == 'container_id': o['Id'] = 'f'*64
    elif change == 'image_secret': t.records['image', o['Image']]['Config']['Env'].append('GITHUB_TOKEN=fixture-secret')
    elif change == 'source_env': b['observer']['source_commit'] = 'f'*40
    elif change == 'worker_image_source': t.worker_image['Config']['Labels']['org.opencontainers.image.revision'] = 'f'*40
    elif change == 'verification_image': t.activation['verification_image'] = 'sha256:'+'f'*64
    response = observe(t)
    expected = 403 if change in ('worker_image_source', 'verification_image') else 409
    assert response.status_code == expected
    assert not t.publisher
    assert 'fixture-secret' not in response.text and 'fixture-only-password' not in response.text


@pytest.mark.parametrize('role', ['observer', 'frontend'])
@pytest.mark.parametrize('change', [
    'stopped', 'paused', 'restarting', 'privileged', 'root', 'writable_root',
    'caps', 'security', 'host_pid', 'host_ipc', 'host_network', 'extra_network',
    'public_port', 'published_upstream', 'socket_mount', 'source_mount',
    'writable_mount', 'recursive_mount', 'provider_credential', 'control_credential',
    'worker_mode', 'shell_command', 'entrypoint', 'executable_tmp', 'conflicting_tmp_flags', 'unbounded_memory',
    'healthcheck', 'extra_host', 'image_volume', 'read_role', 'db_query',
])
def test_unsafe_role_configuration_denied_even_if_fingerprint_is_reapproved(topology, role, change):
    """A private fingerprint alone must not legitimize an unsafe role/configuration."""
    t = topology; row = getattr(t, role); c = row['Config']; h = row['HostConfig']
    if change == 'stopped': row['State'].update(Running=False, Status='exited')
    elif change == 'paused': row['State']['Paused'] = True
    elif change == 'restarting': row['State']['Restarting'] = True
    elif change == 'privileged': h['Privileged'] = True
    elif change == 'root': c['User'] = '0:0'
    elif change == 'writable_root': h['ReadonlyRootfs'] = False
    elif change == 'caps': h['CapAdd'] = ['SYS_ADMIN']
    elif change == 'security': h['SecurityOpt'] = ['seccomp=unconfined']
    elif change == 'host_pid': h['PidMode'] = 'host'
    elif change == 'host_ipc': h['IpcMode'] = 'host'
    elif change == 'host_network': h['NetworkMode'] = 'host'
    elif change == 'extra_network': row['NetworkSettings']['Networks']['foreign'] = {'NetworkID':'f'*64}
    elif change == 'public_port': h['PortBindings'] = {'18443/tcp':[{'HostIp':'0.0.0.0','HostPort':'18443'}]}
    elif change == 'published_upstream': h['PortBindings']['18787/tcp'] = [{'HostIp':'127.0.0.1','HostPort':'18787'}]
    elif change in ('socket_mount', 'source_mount'):
        source = '/var/run/docker.sock' if change == 'socket_mount' else str(t.root/'sources')
        row['Mounts'][0]['Source'] = source; h['Mounts'][0]['Source'] = source
    elif change == 'writable_mount': row['Mounts'][0]['RW'] = True
    elif change == 'recursive_mount': h['Mounts'][0]['BindOptions'] = {}
    elif change == 'provider_credential': c['Env'].append('OPENAI_API_KEY=fixture-secret')
    elif change == 'control_credential': c['Env'].append('PLATFORM_INTERNAL_TOKEN=fixture-secret')
    elif change == 'worker_mode': c['Env'] = [v for v in c['Env'] if not v.startswith('PCP_RUNTIME_STARTUP_MODE=')]+['PCP_RUNTIME_STARTUP_MODE=pcp_local_worker']
    elif change == 'shell_command': c['Cmd'] = ['/bin/sh','-c','worker']
    elif change == 'entrypoint': c['Entrypoint'] = ['/bin/sh']
    elif change == 'executable_tmp': h['Tmpfs']['/tmp'] = 'rw,nosuid,nodev'
    elif change == 'conflicting_tmp_flags': h['Tmpfs']['/tmp'] += ',exec,suid,dev'
    elif change == 'unbounded_memory': h['Memory'] = 0
    elif change == 'healthcheck': c['Healthcheck'] = {'Test':['CMD','worker']}
    elif change == 'extra_host': h['ExtraHosts'] = ['db:192.0.2.1']
    elif change == 'image_volume': t.records['image', row['Image']]['Config']['Volumes'] = {'/foreign':{}}
    elif change == 'read_role': c['Env'] = [v.replace('pcp_dashboard_reader:', 'pcp_runtime:') for v in c['Env']]+([] if role=='observer' else ['DATABASE_URL=fixture-secret'])
    elif change == 'db_query': c['Env'] = [v+'?host=foreign' if v.startswith('DATABASE_URL=') else v for v in c['Env']]+([] if role=='observer' else ['DATABASE_URL=fixture-secret'])
    t.binding[role]['configuration_sha256'] = digest_config(row)  # Adversarial test only.
    response = observe(t)
    assert response.status_code == 409, response.text
    assert not t.publisher and 'fixture-secret' not in response.text
    assert 'fixture-only-password' not in response.text


@pytest.mark.parametrize('role', ['observer', 'frontend'])
def test_unapproved_configuration_drift_keeps_expected_proof(topology, role):
    t = topology; before = deepcopy(t.binding)
    getattr(t, role)['Config']['Labels']['unapproved'] = 'drift'
    response = observe(t)
    assert response.status_code == 409
    assert response.json()['detail'] == 'pcp_local_observer_configuration_changed'
    assert t.binding == before and not t.publisher


def test_replacement_requires_fresh_private_binding(topology):
    t = topology; old = t.observer['Id']; new = 'e'*64
    t.observer['Id'] = new
    t.network['Containers'][new] = t.network['Containers'].pop(old)
    t.records['container', new] = t.records.pop(('container', old))
    assert observe(t).status_code == 409
    t.binding['observer']['container_id'] = new
    t.frontend['HostConfig']['NetworkMode'] = 'container:'+new
    assert observe(t).status_code == 409  # Changed frontend configuration not yet approved.
    t.binding['frontend']['configuration_sha256'] = digest_config(t.frontend)
    assert observe(t).status_code == 200


def test_frontend_must_share_exact_full_observer_id(topology):
    t = topology
    t.frontend['HostConfig']['NetworkMode'] = 'container:'+t.observer['Name'][1:]
    t.binding['frontend']['configuration_sha256'] = digest_config(t.frontend)
    assert observe(t).status_code == 409


def test_docker_mount_listing_order_does_not_change_approved_configuration(topology):
    t = topology; before = deepcopy(t.binding)
    assert observe(t).status_code == 200
    # Docker may enumerate its mount map in a different order on each inspect.
    t.frontend['Mounts'].reverse()
    assert observe(t).status_code == 200
    assert t.binding == before  # Same proof; no refresh/adoption after observation.


def test_publisher_failure_is_not_hidden_by_valid_observer(topology, monkeypatch):
    def denied(_): raise executor.HTTPException(403, 'publisher fixture denial')
    monkeypatch.setattr(executor, '_github_context', denied)
    response = observe(topology)
    assert response.status_code == 403 and response.json()['detail'] == 'publisher fixture denial'
