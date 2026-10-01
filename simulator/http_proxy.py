"""Static HTTP data plane. Backends never cross the generator API boundary."""
import json
import platform
from pathlib import Path
import re
import time
import uuid

import requests

from simulator import config


class ProxyIntegrityError(RuntimeError):
    pass


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def nginx_config(backends):
    if not backends or any(not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', name) for name in backends):
        raise ValueError('expected nonempty valid Docker backend names')
    servers = '\n'.join(f'        server {name}:80 max_fails=0;' for name in backends)
    return '''worker_processes 1;
error_log /artifacts/proxy_error.log notice;
pid /tmp/nginx.pid;
events { worker_connections 4096; }
http {
    log_format operational escape=json
      '{"timestamp":"$msec","request":"$request","status":$status,'
      '"upstream":"$upstream_addr","upstream_status":"$upstream_status",'
      '"request_time":"$request_time","upstream_time":"$upstream_response_time",'
      '"connect_time":"$upstream_connect_time","phase":"$http_x_edos_phase",'
      '"request_id":"$http_x_edos_request_id","connection":"$connection",'
      '"connection_requests":"$connection_requests"}';
    access_log /artifacts/proxy_access.log operational;
    upstream victims {
''' + servers + '''
        keepalive 32;
        keepalive_timeout 60s;
        keepalive_requests 1000;
    }
    server {
        listen 80;
        keepalive_timeout 60s;
        keepalive_requests 1000;
        location / {
            proxy_pass http://victims;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_next_upstream off;
            proxy_next_upstream_tries 1;
            proxy_cache off;
            proxy_buffering off;
            proxy_request_buffering off;
            proxy_connect_timeout 5s;
            proxy_read_timeout 60s;
            proxy_send_timeout 60s;
        }
    }
}
'''


class HttpProxy:
    def __init__(self, client, directory):
        self.client = client
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.container = None
        self.expected_id = None
        self.identity = {}
        self.checks = 0
        self.run_id = None

    def start(self, victims):
        info = self.client.info()
        if info['OperatingSystem'].startswith('Docker Desktop') or info['KernelVersion'] != platform.release():
            raise ProxyIntegrityError('proxy requires native local Linux Engine matching host kernel')
        inventory = []
        for victim in victims:
            victim.reload()
            if victim.attrs['HostConfig'].get('PortBindings'):
                raise ProxyIntegrityError('proxy victims must not publish host ports')
            inventory.append(dict(id=victim.id, name=victim.name,
                                  hostname=victim.attrs['Config']['Hostname'],
                                  ip=victim.attrs['NetworkSettings']['Networks'][config.DOCKER_NETWORK_NAME]['IPAddress'],
                                  port_bindings=victim.attrs['HostConfig'].get('PortBindings'),
                                  image_id=victim.image.id))
        write_json(self.directory / 'backend_inventory.json', inventory)
        (self.directory / 'proxy_config.conf').write_text(nginx_config([v['name'] for v in inventory]))
        image_ref = config.PROXY_IMAGE.split(':')[0] + '@' + config.PROXY_IMAGE_DIGEST
        image = self.client.images.get(image_ref)
        self.identity = dict(image=config.PROXY_IMAGE, tag=config.PROXY_IMAGE.split(':', 1)[1],
                             digest=config.PROXY_IMAGE_DIGEST, image_id=image.id,
                             repo_digests=image.attrs.get('RepoDigests', []), daemon_id=info['ID'],
                             daemon_os=info['OperatingSystem'], daemon_kernel=info['KernelVersion'],
                             service_endpoint=config.SERVICE_ENDPOINT, network=config.DOCKER_NETWORK_NAME)
        write_json(self.directory / 'proxy_identity.json', self.identity)
        self.container = self.client.containers.run(
            image_ref, detach=True, name='edos_http_proxy_' + uuid.uuid4().hex[:12],
            network=config.DOCKER_NETWORK_NAME,
            ports={'80/tcp': ('127.0.0.1', config.PROXY_HOST_PORT)},
            restart_policy={'Name': 'no'},
            volumes={str(self.directory): {'bind': '/artifacts', 'mode': 'rw'}},
            command=['sh', '-c', 'nginx -t -c /artifacts/proxy_config.conf && exec nginx -c /artifacts/proxy_config.conf -g "daemon off;"'])
        self.expected_id = self.container.id
        self.identity.update(id=self.expected_id, name=self.container.name)
        write_json(self.directory / 'proxy_identity.json', self.identity)
        deadline = time.monotonic() + 10
        seen = set()
        with requests.Session() as session:
            session.trust_env = False
            while time.monotonic() < deadline:
                self.verify()
                try:
                    response = session.get(config.SERVICE_ENDPOINT + '/?work=0&sleep=0',
                                           headers={'X-Edos-Phase': 'setup'}, timeout=.5)
                    response.raise_for_status()
                    hostname = response.text.split()[0].removeprefix('host=')
                    seen.add(hostname)
                    if seen == {v['hostname'] for v in inventory}:
                        break
                except requests.RequestException:
                    pass
                time.sleep(.05)
            else:
                raise ProxyIntegrityError('proxy HTTP readiness could not confirm all backends')
        write_json(self.directory / 'readiness.json', dict(hostnames=sorted(seen), phase='setup'))

    def bind_run(self, run_id):
        self.run_id = run_id
        self.identity['run_id'] = run_id
        self.identity['checks'] = self.checks
        write_json(self.directory / 'proxy_identity.json', self.identity)

    def verify(self):
        try:
            container = self.client.containers.get(self.expected_id)
            if container.id != self.expected_id or container.status != 'running':
                raise ProxyIntegrityError('proxy identity/state changed: ' + str(container.status))
        except ProxyIntegrityError:
            raise
        except Exception as exc:
            raise ProxyIntegrityError('unable to verify proxy: ' + str(exc)) from exc
        self.checks += 1
        return container

    def close(self, drained):
        """Preserve mounted evidence even if inspect/removal fails. Never recreate."""
        if self.container is None:
            return
        try:
            if drained:
                self.container.stop(timeout=5)
            (self.directory / 'container_output.log').write_bytes(self.container.logs())
            self.container.reload()
            self.identity.update(final_state=self.container.status, checks=self.checks,
                                 run_id=self.run_id)
            write_json(self.directory / 'proxy_identity.json', self.identity)
            if drained:
                self.container.remove()
        finally:
            for name in ('proxy_access.log', 'proxy_error.log'):
                if not (self.directory / name).exists():
                    raise ProxyIntegrityError('missing proxy artifact: ' + name)
