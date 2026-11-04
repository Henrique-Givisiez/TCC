"""Fixed, unpublished HTTP victim on the source network; no forwarding hop."""
from pathlib import Path
import platform
from simulator import config
from simulator.http_proxy import write_json


def require_empty_network(network):
    network.reload()
    if network.attrs.get('Containers'):
        raise RuntimeError('experimental source network is occupied; refusing ambiguous destination')


class DirectTarget:
    def __init__(self, client, directory):
        self.client = client
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.container = None
        self.identity = {}
        self.expected_id = None

    def start(self, victims, source_network):
        info = self.client.info()
        if info['OperatingSystem'].startswith('Docker Desktop') or info['KernelVersion'] != platform.release():
            raise RuntimeError('direct capture requires native local Linux Engine')
        if len(victims) != 1:
            raise RuntimeError('direct requires one victim')
        self.container = victims[0]
        self.expected_id = self.container.id
        self.container.reload()
        if self.container.attrs['HostConfig'].get('PortBindings'):
            raise RuntimeError('direct victim must not publish host ports')
        source_network.connect(self.container, aliases=['edos_service'])
        self.container.reload()
        self.identity = dict(id=self.expected_id, name=self.container.name,
            hostname=self.container.attrs['Config']['Hostname'], mode='direct',
            source_ip=self.container.attrs['NetworkSettings']['Networks'][source_network.name]['IPAddress'],
            source_network=source_network.name, service_port=config.APP_CONTAINER_PORT,
            service_endpoint=config.SOURCE_SERVICE_ENDPOINT)
        write_json(self.directory/'target_identity.json', self.identity)
        write_json(self.directory/'backend_inventory.json', [dict(self.identity,
            ip=self.container.attrs['NetworkSettings']['Networks'][config.DOCKER_NETWORK_NAME]['IPAddress'])])

    def verify(self):
        container = self.client.containers.get(self.expected_id)
        if container.id != self.expected_id or container.status != 'running':
            raise RuntimeError('direct victim identity/state changed')
        if set(container.attrs['NetworkSettings']['Networks']) != {config.DOCKER_NETWORK_NAME, self.identity['source_network']}:
            raise RuntimeError('direct victim networks changed')
        if container.attrs['HostConfig'].get('PortBindings'):
            raise RuntimeError('direct victim published ports changed')
        return container

    def bind_run(self, run_id):
        self.identity['run_id'] = run_id
        write_json(self.directory/'target_identity.json', self.identity)

    def start_monitoring(self, clock):
        # Victim CPU is collected by StatsCollector, never by a proxy monitor.
        self.verify()

    def close(self, drained):
        self.verify()  # source_experiment owns and removes this victim
