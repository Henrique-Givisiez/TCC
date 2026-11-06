"""Opt-in host safeguards. No Docker access at import; no scientific policy changes."""
from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path
import signal
import shutil
import time


@dataclass(frozen=True)
class Policy:
    # None deliberately means not authorized, rather than an invented default.
    min_available_bytes: int | None = None
    min_disk_bytes: int | None = None
    victim_memory_bytes: int | None = None
    source_memory_bytes: int | None = None
    max_artifact_bytes: int | None = None
    collection_max_age_seconds: float | None = None
    global_timeout_seconds: float | None = None
    docker_timeout_seconds: float | None = None
    version: str = 'exploratory-I1-v1'

    def validate(self, experiment):
        for key, value in asdict(self).items():
            if key != 'version' and (type(value) not in (int, float) or not math.isfinite(value) or value <= 0):
                raise ValueError('mandatory operational limit pending: ' + key)
        if self.version != 'exploratory-I1-v1':
            raise ValueError('unsupported operational policy')
        if self.global_timeout_seconds <= experiment.duration_seconds + 35:
            raise ValueError('global timeout must reserve setup and source drain (>35s)')
        if (experiment.topology.mode != 'direct' or experiment.attack.enabled or experiment.attack.attackers
                or not experiment.diagnostics.enabled or experiment.traffic_sources.execution != 'containers'):
            raise ValueError('I1 requires direct diagnostic benign container sources')


def resolve_images(client, victim, source):
    result = {}
    for role, reference in [('victim', victim), ('source', source)]:
        if not reference.startswith('sha256:') or len(reference) != 71:
            raise ValueError('immutable mode requires full sha256 image ID: ' + role)
        image = client.images.get(reference)  # never build or pull
        if image.id != reference:
            raise RuntimeError('image identity differs: ' + role)
        result[role] = image.id
    return result


def verify_image(container, expected):
    container.reload()
    if container.attrs['Image'] != expected:
        raise RuntimeError('container image identity differs: ' + container.id)


def resource_reasons(snapshot, policy):
    reasons = []
    if snapshot['available_bytes'] < policy.min_available_bytes: reasons.append('host_memory')
    if snapshot['disk_free_bytes'] < policy.min_disk_bytes: reasons.append('disk_space')
    if snapshot['artifact_bytes'] > policy.max_artifact_bytes: reasons.append('artifact_budget')
    for c in snapshot['containers']:
        if c['oom'] or c['restarts']: reasons.append('oom_or_restart:' + c['id'])
        if c['memory'] > getattr(policy, c['role'] + '_memory_bytes'):
            reasons.append('container_memory:' + c['id'])
    # CPU, HTTP failures/duration and worker wait intentionally do not decide actions.
    return reasons


class Operations:
    def __init__(self, policy, images, directory):
        self.policy, self.images, self.directory = policy, images, Path(directory)
        self.owned = {}; self.started = None
        self.reads = {}; self.acquired = {}
        self.report = dict(version=policy.version, limits=asdict(policy), images=images,
                           observations=[], actions=[], cleanup=[], readiness=None,
                           limitations=['Process readiness uses the existing known-process filter; not universal.',
                                        'No proof of host/kernel quiescence or completed victim computation.'])

    def persist(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        tmp = self.directory/'operational_policy.tmp'
        tmp.write_text(json.dumps(self.report, indent=2)+'\n')
        tmp.replace(self.directory/'operational_policy.json')

    def ready(self, client):
        from experiments.development_d1_ops import process_rows
        self.report['readiness'] = dict(verified=False, reason='verification_in_progress')
        self.persist()
        processes = process_rows()
        # Read-only: foreign resources are refused, never removed.
        containers = [c.id for c in client.containers.list()]
        residual = client.containers.list(all=True, filters={'label': 'edos.role=source'})
        residual += client.containers.list(all=True, filters={'name': 'target_instance'})
        containers = sorted(set(containers + [c.id for c in residual]))
        networks = {}
        for name in ('edos_sources', 'edos_network'):
            try:
                n = client.networks.get(name); n.reload()
                networks[name] = list(n.attrs.get('Containers', {}))
            except Exception as exc:
                if getattr(exc, 'status_code', None) != 404: raise
        self.report['readiness'] = dict(processes=processes, active_containers=containers, networks=networks,
                                       verified=not processes and not containers and not any(networks.values()))
        self.persist()
        if not self.report['readiness']['verified']: raise RuntimeError('operational readiness blocked')
        self.observe(client, None)

    def own(self, container, role):
        self.owned[container.id] = role  # own before verifying, so mismatch still gets cleaned
        verify_image(container, self.images[role])

    def observe(self, client, collector):
        from experiments.capacity_exploration import host_snapshot, tree_bytes
        snapshot = host_snapshot()
        snapshot.update(disk_free_bytes=shutil.disk_usage(self.directory).free,
                        artifact_bytes=tree_bytes(self.directory), containers=[])
        for cid, role in self.owned.items():
            c = client.containers.get(cid); verify_image(c, self.images[role]); state = c.attrs['State']
            if state['Status'] not in ('running', 'exited'): raise RuntimeError('unexpected container state: '+cid)
            if role == 'victim' and state['Status'] != 'running': raise RuntimeError('victim stopped')
            stats = c.stats(stream=False) if state['Status'] == 'running' else {}
            snapshot['containers'].append(dict(id=cid, role=role, memory=stats.get('memory_stats', {}).get('usage', 0),
                                               oom=state.get('OOMKilled', False), restarts=c.attrs.get('RestartCount', 0)))
        reasons = resource_reasons(snapshot, self.policy)
        if collector:
            now = time.monotonic()
            for cid, sample in collector.get_snapshot().items():
                stamp = sample.get('read_ts')
                if stamp and stamp > self.reads.get(cid, ''):
                    self.reads[cid] = stamp; self.acquired[cid] = now
            for cid, role in self.owned.items():
                if role == 'victim' and now-self.acquired.get(cid, self.collection_started) > self.policy.collection_max_age_seconds:
                    reasons.append('collection_acquisition_stale:' + cid)
            snapshot['collection_acquisitions'] = dict(self.acquired)
            path = Path(collector.evidence_path)
            age = time.time()-path.stat().st_mtime if path.exists() else time.monotonic()-self.collection_started
            snapshot['collection_persistence_age_seconds'] = age
            if age > self.policy.collection_max_age_seconds: reasons.append('collection_persistence_stale')
        self.report['observations'].append(snapshot)
        if reasons: self.report['actions'].append(dict(reasons=reasons, action='stop_all', at=time.monotonic()))
        self.persist()
        if reasons: raise RuntimeError('operational protection: '+','.join(reasons))

    def arm(self):
        if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0): raise RuntimeError('existing process timer')
        self.started = time.monotonic(); self.old_handler = signal.getsignal(signal.SIGALRM)
        def timeout(*_):
            self.report['actions'].append(dict(reasons=['global_timeout'], action='stop_all', at=time.monotonic()))
            raise TimeoutError('exploratory global timeout')
        signal.signal(signal.SIGALRM, timeout)
        signal.setitimer(signal.ITIMER_REAL, self.policy.global_timeout_seconds)

    def disarm(self):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.old_handler)
        self.report['elapsed_before_cleanup_seconds'] = time.monotonic()-self.started

    def finish(self, client, errors):
        # A second best-effort owned-only cleanup also covers partial manager setup.
        for cid in self.owned:
            try:
                c = client.containers.get(cid); c.remove(force=True)
                self.report['cleanup'].append(dict(container=cid, removed=True))
            except Exception as exc:
                if getattr(exc, 'status_code', None) == 404:
                    self.report['cleanup'].append(dict(container=cid, absent=True))
                else:
                    errors.append('owned cleanup: '+str(exc))
                    self.report['cleanup'].append(dict(container=cid, error=str(exc)))
        self.report['cleanup_verified'] = not errors
        self.report['progression_allowed'] = not errors
        self.report['duration_nominal_seconds'] = getattr(self, 'nominal_seconds', None)
        self.report['errors'] = list(errors)
        self.persist()
