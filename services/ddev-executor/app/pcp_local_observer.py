"""Read-only validation of a privately approved PCP observer Docker binding.

No discovery, adoption, mutation, credential output or caller-supplied policy.
Configuration digests belong to the trusted activation, never to HTTP input.
They pin Docker configuration, not the contents of trusted host-mounted files;
those files, TLS and database grants remain separately reviewed rollout inputs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit

from fastapi import HTTPException


_ID = r'[0-9a-f]{64}'
_SHA = r'[0-9a-f]{40}'
_PORTS = {'18443/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '18443'}]}
_RUNTIME_ENV = {'PATH', 'NODE_VERSION', 'YARN_VERSION', 'PYTHONUNBUFFERED', 'LANG'}
_NGINX_ENV = {'PATH', 'NGINX_VERSION', 'NJS_VERSION', 'NJS_RELEASE', 'PKG_RELEASE', 'DYNPKG_RELEASE'}


def configuration_digest(row):
    """Offline approval fingerprint. Do not refresh an expected digest on drift."""
    value = {key: row[key] for key in ('Name', 'Config', 'HostConfig', 'Mounts')}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _require(condition, code='pcp_local_observer_configuration_invalid'):
    if not condition:
        raise HTTPException(409, code)


def _shape(value, keys):
    _require(type(value) is dict and set(value) == set(keys), 'pcp_local_observer_binding_invalid')


def _match(pattern, value):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def _environment(values):
    _require(type(values) is list and len(values) <= 64)
    result = {}
    for value in values:
        _require(isinstance(value, str) and '=' in value)
        key, content = value.split('=', 1)
        _require(key not in result)
        result[key] = content
    return result


def _container(binding, role, instance, inspect):
    row = inspect('container', binding['container_id'])
    image = inspect('image', binding['image_id'])
    config, host, state = row['Config'], row['HostConfig'], row['State']
    _require(row['Id'] == binding['container_id'] and row['Image'] == binding['image_id']
             and config['Image'] == binding['image_id'] and image['Id'] == binding['image_id'])
    prefix = 'observer' if role == 'observer' else 'https'
    _require(_match(re.escape('/'+instance+'-'+prefix)+r'[a-z0-9-]*', row['Name']))
    _require(state['Running'] is True and state['Status'] == 'running'
             and all(state[k] is False for k in ('Paused', 'Restarting', 'Dead')))
    _require(config['Labels'].get('org.pcp.local.instance') == instance
             and config['User'] == '1000:1000' and not config.get('Volumes')
             and not image['Config'].get('Volumes') and not config.get('OpenStdin')
             and not config.get('Tty') and not config.get('Healthcheck'))
    _require(host['Privileged'] is False and host['ReadonlyRootfs'] is True
             and host['CapDrop'] == ['ALL'] and not host.get('CapAdd')
             and host['SecurityOpt'] == ['no-new-privileges:true']
             and host['PidMode'] == '' and host['IpcMode'] == 'private'
             and host['CgroupnsMode'] == 'private' and host['UTSMode'] == ''
             and host['UsernsMode'] == '' and host['Runtime'] == 'runc'
             and host['PublishAllPorts'] is False
             and host['RestartPolicy'] == {'Name': 'no', 'MaximumRetryCount': 0})
    _require(not any(host.get(k) for k in ('Binds', 'VolumesFrom', 'Devices',
             'DeviceRequests', 'DeviceCgroupRules', 'Links', 'ExtraHosts', 'GroupAdd',
             'Dns', 'DnsOptions', 'DnsSearch', 'Sysctls', 'ContainerIDFile')))
    _require(set(host['Tmpfs']) == {'/tmp'})
    tmp_options = set(host['Tmpfs']['/tmp'].split(','))
    _require({'rw', 'noexec', 'nosuid', 'nodev'} <= tmp_options
             and not tmp_options.intersection({'exec', 'suid', 'dev'}))
    _require(type(host['Memory']) is int and 0 < host['Memory'] <= 805306368
             and host['MemorySwap'] == host['Memory']
             and type(host['NanoCpus']) is int and 0 < host['NanoCpus'] <= 1000000000
             and type(host['PidsLimit']) is int and 0 < host['PidsLimit'] <= 128)
    # Pin all stable Docker configuration fields as well as the hard role rules.
    # Includes private env values without returning/logging them or their contents.
    _require(configuration_digest(row) == binding['configuration_sha256'],
             'pcp_local_observer_configuration_changed')
    return row, image['Config']


def _mounts(row, expected):
    mounts, declared = row['Mounts'], row['HostConfig']['Mounts']
    _require(type(mounts) is list and type(declared) is list
             and len(mounts) == len(expected) == len(declared))
    _require({m['Destination'] for m in mounts} == set(expected)
             and {m['Target'] for m in declared} == set(expected))
    for mount in mounts:
        _require(mount['Type'] == 'bind' and mount['RW'] is False
                 and mount['Source'] == expected[mount['Destination']]
                 and mount['Propagation'] == 'rprivate')
    for mount in declared:
        _require(mount['Type'] == 'bind' and mount['ReadOnly'] is True
                 and mount['Source'] == expected[mount['Target']]
                 and mount['BindOptions'] == {'NonRecursive': True})


def _approved_observer(binding, root, network, inspect):
    _shape(binding, ('version', 'network_id', 'config_root', 'observer', 'frontend'))
    _require(type(binding['version']) is int and binding['version'] == 1
             and _match(_ID, binding['network_id']), 'pcp_local_observer_binding_invalid')
    config_root = binding['config_root']
    _require(_match(re.escape(str(root))+r'/releases/[A-Za-z0-9][A-Za-z0-9._-]{0,79}/config', config_root),
             'pcp_local_observer_binding_invalid')
    for role in ('observer', 'frontend'):
        keys = {'container_id', 'image_id', 'configuration_sha256'}
        if role == 'observer': keys.add('source_commit')
        part = binding[role]
        _shape(part, keys)
        _require(_match(_ID, part['container_id']) and _match('sha256:'+_ID, part['image_id'])
                 and _match(_ID, part['configuration_sha256']), 'pcp_local_observer_binding_invalid')
    _require(_match(_SHA, binding['observer']['source_commit'])
             and binding['observer']['container_id'] != binding['frontend']['container_id'],
             'pcp_local_observer_binding_invalid')
    _require(network['Id'] == binding['network_id'] and network['Name'] == root.name+'-private')
    observer, image_config = _container(binding['observer'], 'observer', root.name, inspect)
    frontend, frontend_image = _container(binding['frontend'], 'frontend', root.name, inspect)
    source = binding['observer']['source_commit']
    _require(image_config['Labels'].get('org.opencontainers.image.revision') == source
             and image_config['Labels'].get('org.pcp.local.instance') == root.name
             and observer['Config']['Labels'].get('org.opencontainers.image.revision') == source)
    _require(observer['Config']['Entrypoint'] == image_config['Entrypoint']
             and observer['Config']['WorkingDir'] == '/app'
             and observer['Config']['Cmd'] == ['uvicorn', 'app.main:app', '--host',
                 '127.0.0.1', '--port', '18787', '--no-proxy-headers'])
    _require(frontend['Config']['Entrypoint'] == ['nginx']
             and frontend['Config']['Cmd'] == ['-c', '/private/nginx.conf', '-g', 'daemon off;'])
    base_env = _environment(image_config['Env'])
    _require(set(base_env) <= _RUNTIME_ENV)
    env = _environment(observer['Config']['Env'])
    database = urlsplit(env['DATABASE_URL'])
    _require(database.scheme == 'postgresql' and database.username == 'pcp_dashboard_reader'
             and bool(database.password) and database.hostname == 'db' and database.port == 5432
             and database.path == '/pcp_local' and not database.query and not database.fragment)
    expected = {**base_env, 'DATABASE_URL': env['DATABASE_URL'], 'HOME': '/tmp',
        'PYTHONDONTWRITEBYTECODE': '1', 'PCP_RUNTIME_STARTUP_MODE': 'pcp_local_dashboard',
        'PCP_LOCAL_DASHBOARD_AUTH': 'loopback_readonly', 'PCP_LOCAL_INSTANCE': root.name,
        'PCP_LOCAL_SOURCE_COMMIT': source, 'PROJECTS_FILE': '/config/projects.pcp-local.yml',
        'PROJECT_BASELINES_FILE': '/config/project-baselines.pcp-local.yml',
        'MODELS_FILE': '/config/models.yml', 'ROUTING_POLICY_FILE': '/config/routing-policy.yml'}
    _require(env == expected)
    frontend_env = _environment(frontend['Config']['Env'])
    _require(set(frontend_env) <= _NGINX_ENV and frontend_env == _environment(frontend_image['Env']))
    _mounts(observer, {'/config': str(PurePosixPath(config_root)/'registry')})
    _mounts(frontend, {'/private/'+name: str(PurePosixPath(config_root)/name)
                      for name in ('nginx.conf', 'localhost.pem', 'localhost-key.pem')})
    _require(observer['HostConfig']['NetworkMode'] in (network['Name'], network['Id'])
             and observer['HostConfig']['PortBindings'] == _PORTS
             and observer['NetworkSettings']['Ports'] == _PORTS)
    networks = observer['NetworkSettings']['Networks']
    _require(set(networks) == {network['Name']}
             and networks[network['Name']]['NetworkID'] == network['Id'])
    peer = network['Containers'].get(observer['Id'])
    _require(type(peer) is dict and peer['Name'] == observer['Name'].removeprefix('/')
             and peer['EndpointID'] == networks[network['Name']]['EndpointID'])
    _require(frontend['HostConfig']['NetworkMode'] == 'container:'+observer['Id']
             and not frontend['HostConfig']['PortBindings']
             and not frontend['NetworkSettings']['Ports']
             and frontend['NetworkSettings']['Networks'] == {}
             and frontend['Id'] not in network['Containers'])
    return observer['Id'], peer['Name']


def validate_network_peers(activation, root, network, inspect):
    """The four existing peers plus at most one exactly approved observer endpoint."""
    permitted = {root.name+'-'+s for s in ('coding-runtime', 'router', 'ddev-executor', 'db')}
    try:
        approved = None
        # Explicit null/empty/malformed bindings fail; absence retains legacy semantics.
        if 'observer_binding' in activation:
            approved = _approved_observer(activation['observer_binding'], root, network, inspect)
        peers = network['Containers']
        _require(type(peers) is dict, 'pcp_local_foreign_network_peer')
        for identity, peer in peers.items():
            _require(peer.get('Name') in permitted or approved == (identity, peer.get('Name')),
                     'pcp_local_foreign_network_peer')
    except (KeyError, TypeError, ValueError, AttributeError):
        # Never serialize Docker metadata, env/URL values or parser exception text.
        raise HTTPException(409, 'pcp_local_observer_binding_invalid') from None
