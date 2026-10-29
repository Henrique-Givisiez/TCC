"""Host-only source lifecycle and reproducible origin plans."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import time
import uuid
from simulator import config
from simulator.http_proxy import write_json


def worker_quotas(budget, count):
    if count == 0:
        return []
    if count < 0 or budget < count:
        raise ValueError('source count exceeds send worker budget')
    base, remainder = divmod(budget, count)
    return [base + (index < remainder) for index in range(count)]


def validate_clocks(containers, destination):
    """Same time namespace plus bracketed remote samples, before timeline use."""
    namespace = os.readlink('/proc/self/ns/time')
    evidence = dict(host_time_namespace=namespace, sources=[], comparable=False)
    for container in containers:
        samples = []
        for _ in range(4):
            before = time.monotonic()
            result = container.exec_run(['python', '-c',
                'import time,os,json; print(json.dumps(dict(monotonic=time.monotonic(),epoch=time.time(),namespace=os.readlink("/proc/self/ns/time"))))'])
            after = time.monotonic()
            if result.exit_code:
                raise RuntimeError('unable to audit source clock')
            remote = json.loads(result.output)
            samples.append(dict(host_before=before, host_after=after, **remote))
            if remote['namespace'] != namespace or not before <= remote['monotonic'] <= after:
                write_json(destination, evidence)
                raise RuntimeError('source monotonic clock is not demonstrably comparable; stop before experiment')
        evidence['sources'].append(dict(container_id=container.id, samples=samples))
    evidence['comparable'] = True
    write_json(destination, evidence)
    return evidence


class SourceManager:
    def __init__(self, client, network, directory, inventory_file, experiment):
        self.client, self.network, self.experiment = client, network, experiment
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.inventory_file = Path(inventory_file)
        self.entries = []
        self.containers = []
        self.bindings = {}
        self.plan = []
        self.intentional_stop = False

    def start(self):
        image = self.client.images.get(config.SOURCE_IMAGE)
        repository = Path(__file__).resolve().parents[1]
        for filename in ('Dockerfile.sources','requirements.sources.txt'):
            (self.directory/filename).write_text((repository/'docker'/filename).read_text())
        write_json(self.directory/'image_identity.json', dict(image=config.SOURCE_IMAGE,image_id=image.id,
            digest=image.id,digest_kind='local_image_config',repo_digests=image.attrs.get('RepoDigests',[]),
            base_image='python:3.12.10-slim-bookworm',
            base_digest='sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db'))
        for component, settings, count in [('normal', self.experiment.normal_traffic, self.experiment.normal_traffic.clients),
                                           ('attack', self.experiment.attack, self.experiment.attack.attackers if self.experiment.attack.enabled else 0)]:
            quotas = worker_quotas(settings.max_concurrent_sends, count)
            for index, quota in enumerate(quotas):
                source_id = f'{component}_{index+1}'
                root = self.directory / source_id
                for part in ('control', 'output'):
                    (root / part).mkdir(parents=True)
                values = asdict(settings)
                values['max_concurrent_sends'] = quota
                values['clients' if component=='normal' else 'attackers'] = 1
                manifest = dict(source_id=source_id, source_type=component, traffic_class='benign' if component=='normal' else 'attack',
                    worker_index=index, seed=self.experiment.seed, service_endpoint=config.SOURCE_SERVICE_ENDPOINT,
                    settings=values, aggregate_worker_budget=settings.max_concurrent_sends)
                write_json(root / 'manifest.json', manifest)
                self.plan.append(manifest)
                container = self.client.containers.run(image.id, detach=True,
                    name='edos_source_' + source_id + '_' + uuid.uuid4().hex[:10], hostname=source_id,
                    network=self.network.name, restart_policy={'Name':'no'},
                    labels={'edos.role':'source', 'edos.source_id':source_id},
                    command=['--manifest', '/manifest.json'],
                    volumes={str(root / 'manifest.json'):{'bind':'/manifest.json','mode':'ro'},
                             str(root / 'control'):{'bind':'/control','mode':'ro'},
                             str(root / 'output'):{'bind':'/output','mode':'rw'}})
                self.containers.append(container)
                container.reload()
                entry = dict(source_id=source_id, source_type=component, traffic_class=manifest['traffic_class'],
                    container_id=container.id, container_name=container.name, hostname=container.attrs['Config']['Hostname'],
                    ip=container.attrs['NetworkSettings']['Networks'][self.network.name]['IPAddress'],
                    image=config.SOURCE_IMAGE, tag=config.SOURCE_IMAGE.split(':')[1], image_id=image.id,
                    digest=image.id, digest_kind='local_image_config', repo_digests=image.attrs.get('RepoDigests', []),
                    base_image='python:3.12.10-slim-bookworm',
                    base_digest='sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db',
                    run_id=None, service_endpoint=config.SOURCE_SERVICE_ENDPOINT, network=self.network.name,
                    worker_index=index, send_workers=quota, aggregate_worker_budget=settings.max_concurrent_sends,
                    status_final=None)
                self.entries.append(entry)
        write_json(self.directory / 'source_plan.json', self.plan)
        self.persist()
        deadline = time.monotonic() + 15
        while not all((self.directory/e['source_id']/'output/ready.json').exists() for e in self.entries):
            self.verify(setup=True)
            if time.monotonic() > deadline:
                raise RuntimeError('source readiness timeout')
            time.sleep(.02)
        validate_clocks(self.containers, self.directory / 'clock_validation.json')

    def persist(self):
        write_json(self.inventory_file, self.entries)

    def release(self, ground_truth):
        binding = dict(run_id=ground_truth.run_id, experiment_id=ground_truth.experiment_id,
                       monotonic=ground_truth.clock.monotonic_initial, epoch=ground_truth.clock.epoch_initial,
                       duration_seconds=self.experiment.duration_seconds)
        for entry in self.entries:
            entry['run_id'] = ground_truth.run_id
            self.bindings[entry['source_id']] = binding.copy()
            self.command(entry['source_id'], binding)
        self.persist()

    def command(self, source_id, payload):
        path = self.directory/source_id/'control/command.json'
        temporary = path.with_suffix('.tmp')
        write_json(temporary, payload)
        os.replace(temporary, path)

    def verify(self, setup=False):
        for entry in self.entries:
            container = self.client.containers.get(entry['container_id'])
            if container.id != entry['container_id']:
                raise RuntimeError('source identity changed: ' + entry['source_id'])
            if container.status == 'running':
                continue
            final = self.directory/entry['source_id']/'output/final_status.json'
            # Attack sources intentionally finish after their own event closes.
            if not setup and final.exists():
                result = json.loads(final.read_text())
                journal = final.parent/'journal.jsonl'
                last = json.loads(journal.read_text().splitlines()[-1]) if journal.exists() else {}
                expected_end = (self.experiment.attack.end_seconds if entry['source_type']=='attack'
                                else self.experiment.duration_seconds)
                expected_exit = (last.get('kind')=='source_closed' and
                                 last.get('run_id')==entry['run_id'] and last.get('source_id')==entry['source_id'] and
                                 last.get('payload',{}).get('elapsed_seconds',-1)>=expected_end)
                if (result.get('drained') and result.get('logger_complete') and
                        result.get('run_id')==entry['run_id'] and result.get('source_id')==entry['source_id'] and
                        container.attrs['State']['ExitCode'] == 0 and expected_exit):
                    continue
            raise RuntimeError('source stopped unexpectedly: ' + entry['source_id'])

    def stop(self, reason):
        self.intentional_stop = True
        for entry in self.entries:
            binding = self.bindings.get(entry['source_id'])
            if binding:
                self.command(entry['source_id'], dict(binding, stop=True, reason=reason))
            else:
                self.client.containers.get(entry['container_id']).kill(signal='SIGTERM')
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            states = [self.client.containers.get(c.id).status for c in self.containers]
            if all(s != 'running' for s in states):
                break
            time.sleep(.05)
        complete = True
        for entry in self.entries:
            container = self.client.containers.get(entry['container_id'])
            root = self.directory/entry['source_id']/'output'
            forced = container.status == 'running'
            if forced:
                container.kill()
            container.reload()
            (root/'container_output.log').write_bytes(container.logs())
            final = root/'final_status.json'
            result = json.loads(final.read_text()) if final.exists() else {}
            entry['status_final'] = dict(state=container.status, exit_code=container.attrs['State']['ExitCode'],
                                         forced=forced, **result)
            complete = complete and not forced and container.attrs['State']['ExitCode'] == 0 and result.get('drained', False) and result.get('logger_complete', False)
        self.persist()
        return complete

    def remove(self):
        errors = []
        for container in self.containers:
            try:
                container.remove(force=True)
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError('source cleanup: ' + '; '.join(errors))
