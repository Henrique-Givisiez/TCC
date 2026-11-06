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
        self.timer_changed = False
        self.handler_changed = False
        self.report = dict(version=policy.version, limits=asdict(policy), images=images,
                           observations=[], actions=[], cleanup=[], readiness=None,
                           cleanup_verified=None, progression_allowed=False,
                           certification='pending', execution=None, records='pending', export='pending',
                           failures=[],
                           limitations=['Process readiness uses the existing known-process filter; not universal.',
                                        'No proof of host/kernel quiescence or completed victim computation.'])

    def persist(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        tmp = self.directory/'operational_policy.tmp'
        tmp.write_text(json.dumps(self.report, indent=2)+'\n')
        tmp.replace(self.directory/'operational_policy.json')

    def ready(self, client):
        from experiments.development_d1_ops import process_rows
        result = dict(verified=False, reasons=[], active_external=[], residual=[], processes=[], networks={})
        self.report.setdefault('readiness_history', []).append(result)
        self.report['readiness'] = result
        try:
            result['processes'] = process_rows()
            active = {c.id for c in client.containers.list()}
            residual = client.containers.list(all=True, filters={'label': 'edos.role=source'})
            residual += client.containers.list(all=True, filters={'name': 'target_instance'})
            result['residual'] = sorted({c.id for c in residual})
            result['active_external'] = sorted(active-set(result['residual']))
            if result['processes']: result['reasons'].append('known_processes')
            if result['residual']: result['reasons'].append('simulator_residual')
            if result['active_external']: result['reasons'].append('external_active_containers')
            for name in ('edos_sources', 'edos_network'):
                try:
                    n = client.networks.get(name); n.reload()
                    result['networks'][name] = list(n.attrs.get('Containers', {}))
                except Exception as exc:
                    if getattr(exc, 'status_code', None) != 404: raise
            if any(result['networks'].values()): result['reasons'].append('occupied_networks')
            self.observe(client, None, include_owned=False)
            result['verified'] = not result['reasons']
        except Exception as exc:
            result['reasons'].append('insufficient_resources' if str(exc).startswith('operational protection:') else 'verification_failed')
            result['error'] = repr(exc)
            raise
        finally:
            self.persist()
        if not result['verified']: raise RuntimeError('operational readiness blocked: '+','.join(result['reasons']))

    def own(self, container, role):
        self.owned[container.id] = role  # own before verifying, so mismatch still gets cleaned
        verify_image(container, self.images[role])

    def observe(self, client, collector, include_owned=True):
        from experiments.capacity_exploration import host_snapshot, tree_bytes
        snapshot = host_snapshot()
        snapshot.update(disk_free_bytes=shutil.disk_usage(self.directory).free,
                        artifact_bytes=tree_bytes(self.directory), containers=[])
        for cid, role in (self.owned.items() if include_owned else []):
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
        self.started = time.monotonic()
        self.old_handler = signal.getsignal(signal.SIGALRM)
        def timeout(*_):
            self.report['actions'].append(dict(reasons=['global_timeout'], action='stop_all', at=time.monotonic()))
            raise TimeoutError('exploratory global timeout')
        self.handler_changed = True
        signal.signal(signal.SIGALRM, timeout)
        self.timer_changed = True
        signal.setitimer(signal.ITIMER_REAL, self.policy.global_timeout_seconds)

    def disarm(self):
        failures = []
        if self.timer_changed:
            try:
                signal.setitimer(signal.ITIMER_REAL, 0)
                self.timer_changed = False
            except Exception as exc: failures.append('disable timer: '+repr(exc))
        if self.handler_changed:
            try:
                signal.signal(signal.SIGALRM, self.old_handler)
                self.handler_changed = False
            except Exception as exc: failures.append('restore handler: '+repr(exc))
        if self.started is not None:
            self.report['elapsed_before_cleanup_seconds'] = time.monotonic()-self.started
        if failures:
            self.report['failures'].extend(failures)
            raise RuntimeError('; '.join(failures))

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
        cleanup_errors = [r for r in self.report['cleanup'] if 'error' in r]
        for cid in self.owned:
            try:
                client.containers.get(cid)
                cleanup_errors.append(dict(container=cid, error='still exists after removal'))
            except Exception as exc:
                if getattr(exc, 'status_code', None) != 404:
                    cleanup_errors.append(dict(container=cid, error=repr(exc)))
        for name in self.report.get('temporary_networks', []):
            try:
                client.networks.get(name)
                cleanup_errors.append(dict(network=name, error='temporary network remains'))
            except Exception as exc:
                if getattr(exc, 'status_code', None) != 404:
                    cleanup_errors.append(dict(network=name, error=repr(exc)))
        failed_stops = [r for r in self.report.get('shutdown_steps', [])
                        if r.get('component') in ('raw_capture', 'capture', 'stats') and not r.get('complete')]
        self.report['cleanup_checks'] = cleanup_errors + failed_stops
        for check in cleanup_errors + failed_stops:
            errors.append('cleanup verification: '+str(check))
        self.report['cleanup_verified'] = not cleanup_errors and not failed_stops
        self.report['progression_allowed'] = False  # only certify() after status AND export
        self.report['errors'] = list(errors)
        try:
            self.ready(client)
        except Exception as exc:
            errors.append('post-cleanup readiness: '+repr(exc))
        self.report['post_cleanup_readiness'] = self.report.get('readiness')
        self.report['errors'] = list(errors)
        self.persist()

    def certify(self, export_path, failures):
        """Final procedure certificate refers to canonical run_status, never replaces it.

        The dataset contains the pre-certificate operational snapshot; this final raw
        report binds the exported manifest after export rather than rewriting history.
        """
        import hashlib
        self.report['progression_allowed'] = False
        self.report['certification'] = 'pending'
        self.report['failures'].extend(failures)
        try:
            status_path = self.directory/'run_status.json'
            status = json.loads(status_path.read_text())
            self.report['execution'] = dict(path=str(status_path), status=status['status'],
                end_reason=status['end_reason'], run_id=status['run_id'],
                sha256=hashlib.sha256(status_path.read_bytes()).hexdigest())
            required = ['effective_config.json', 'run_provenance.json', 'source_inventory.json',
                        'request_log.csv', 'traffic_capture.csv', 'simulation_metrics.csv']
            for name in required:
                if not (self.directory/name).is_file() or not (self.directory/name).stat().st_size:
                    raise RuntimeError('missing essential record: '+name)
            for name in ('effective_config.json', 'run_provenance.json', 'source_inventory.json'):
                json.loads((self.directory/name).read_text())
            if not all(status.get('capture_results', {}).get(k, {}).get('accepted') is True for k in ('pcap','csv')):
                raise RuntimeError('capture closure not certified')
            config = json.loads((self.directory/'effective_config.json').read_text())
            inventory = json.loads((self.directory/'source_inventory.json').read_text())
            for source in inventory:
                root = self.directory/'source_artifacts'/source['source_id']/'output'
                if not (root/'journal.jsonl').is_file() or not (root/'journal.jsonl').stat().st_size:
                    raise RuntimeError('source journal missing')
                final = json.loads((root/'final_status.json').read_text())
                if not final.get('drained') or not final.get('logger_complete'):
                    raise RuntimeError('source closure incomplete')
                if config.get('diagnostics', {}).get('enabled'):
                    summary = json.loads((root/'diagnostics/events.summary.json').read_text())
                    if summary.get('complete') is not True: raise RuntimeError('source diagnostics incomplete')
            if config.get('diagnostics', {}).get('enabled'):
                summary = json.loads((self.directory/'diagnostics/victim/events.summary.json').read_text())
                if summary.get('complete') is not True: raise RuntimeError('victim diagnostics incomplete')
            self.report['records'] = 'persisted_basic_checks'
            manifest = Path(export_path)/'dataset_manifest.json'
            data = json.loads(manifest.read_text())
            if data.get('run_id') != status['run_id']: raise RuntimeError('export run identity mismatch')
            if self.report['export'] != 'pending': raise RuntimeError('export did not complete cleanly')
            self.report['export'] = dict(status='completed', manifest=str(manifest),
                sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
            ok = (status['status']=='completed' and status.get('end_reason')=='simulation_end'
                  and status.get('producers_drained') is True
                  and not status.get('errors') and not self.report['failures']
                  and self.report.get('cleanup_verified') is True
                  and self.report.get('post_cleanup_readiness', {}).get('verified') is True)
            self.report['procedure_completed'] = ok
            self.report['progression_allowed'] = ok
            self.report['certification'] = 'completed' if ok else 'blocked'
        except Exception as exc:
            self.report['failures'].append('certification: '+repr(exc))
            self.report['certification'] = 'blocked'
            self.report['procedure_completed'] = False
        try:
            self.persist()
        except Exception:
            self.report['progression_allowed'] = False
            self.report['certification'] = 'pending'
            raise


def verify_previous(directory):
    import hashlib
    directory = Path(directory)
    previous = json.loads((directory/'operational_policy.json').read_text())
    if (previous.get('certification') != 'completed' or previous.get('procedure_completed') is not True
            or previous.get('progression_allowed') is not True):
        raise RuntimeError('previous essential failure or pending certification; progression blocked')
    status = directory/'run_status.json'
    if hashlib.sha256(status.read_bytes()).hexdigest() != previous['execution']['sha256']:
        raise RuntimeError('previous run_status changed; progression blocked')
