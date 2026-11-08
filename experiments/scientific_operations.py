"""Direct collection integration; reuse protections, never fit scientific gates."""
from pathlib import Path
from analysis.detection.inputs import read_json, digest, ContractError

COLLECTION_SECONDS = 480  # Existing scientific subprocess allowance, not a new limit.

def is_direct():
    from analysis.detection.scientific.protocol import SPEC
    return SPEC.get('configuration_contract') == 'complete-direct-b2-v1'

def policy():
    from simulator.exploratory_operations import Policy
    root=Path(__file__).resolve().parents[1]
    from analysis.detection.scientific.protocol import SPEC
    ref=SPEC['operational_policy']['resource_policy']
    path=root/ref['path']
    if digest(path)!=ref['sha256']:raise ContractError('Resource policy changed')
    fields=read_json(path)
    # Reuse the approved B2 resource limits, within the existing scientific budget.
    fields['global_timeout_seconds']=COLLECTION_SECONDS
    return Policy(**fields)

def image_bindings(client, images):
    from analysis.detection.scientific.direct_contract import validate_image_lock
    from experiments.image_code_evidence import verify_image_code
    validate_image_lock(images)
    for role, identity in images.items():
        if client.images.get(identity).id != identity:
            raise ContractError('Frozen image changed: '+role)
    return verify_image_code(client,images)

def readiness(client, directory, images):
    from simulator.exploratory_operations import Operations
    op=Operations(policy(),images,directory)
    op.ready(client)
    return op.report['readiness']

def collection_checks(raw,run):
    from experiments.development_d3 import collection_checks as checks
    result=checks(raw,run,capture_only=True)
    summary=read_json(Path(raw)/'victim_stats.summary.json')
    status=read_json(Path(raw)/'run_status.json')
    result.append(dict(name='cpu_collector_shutdown',passed=(summary.get('run_id')==run
        and summary.get('worker_finished') is True and not summary.get('fatal_error')
        and status.get('cpu_observation_contract')=='victim-cpu-snapshots-v1'),evidence=summary))
    op=read_json(Path(raw)/'operational_policy.json')
    result.append(dict(name='operational_cleanup',passed=(op.get('cleanup_verified') is True
        and op.get('post_cleanup_readiness',{}).get('verified') is True
        and not op.get('actions') and not op.get('failures')),evidence=op))
    return result

def resource_probe(client,source):
    from experiments.stress_runtime import resources
    probe=client.containers.run(source,detach=True,entrypoint=['python','-c'],
        command=['import time;time.sleep(60)'],network_mode='none')
    try:return resources(probe)
    finally:probe.stop(timeout=2);probe.remove()

def install_observer(expected_resources,observer_policy):
    """Same runtime adapter for consumed campaign attempts and explicit pilots."""
    from experiments.stress_runtime import StressManager
    from experiments.stress_observer import SampleFreshness
    from simulator import source_experiment,stats_collector
    StressManager.expected_resources=expected_resources
    StressManager.observer_policy=observer_policy
    original=stats_collector.StatsCollector
    class ProtectedCollector(original):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw);self.samples=SampleFreshness()
            self.fresh=self.samples.fresh;StressManager.collector=self
        def _on_acquisition(self,c,stats,received_monotonic):
            self.samples.update(c.id,stats,received_monotonic)
    source_experiment.SourceManager=StressManager
    stats_collector.StatsCollector=ProtectedCollector

def validate_pilot(experiment,scenario,operational):
    from analysis.detection.scientific.protocol import SPEC
    from analysis.detection.scientific.direct_contract import validate_configuration
    from dataclasses import asdict
    import json
    if not is_direct() or operational is None:
        raise ContractError('Scientific pilot requires explicit direct contract and protection')
    validate_configuration(SPEC,scenario,experiment.id,experiment.seed,json.loads(experiment.to_json()))
    if asdict(operational.policy)!=asdict(policy()):raise ContractError('Scientific pilot policy differs')
