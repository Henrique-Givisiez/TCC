"""Scientific membership and byte-verified scalar IO; no legacy role bypass."""
import csv
from dataclasses import dataclass
from decimal import Decimal as D
from pathlib import Path

from ..contracts import Observation, ObservedSeries
from ..inputs import ContractError, read_json, digest, safe_file, checked_output, number
from experiments.feature_schema import feature_schema
from .protocol import FEATURES,SPEC


@dataclass(frozen=True)
class Source:
    entry_id: str
    partition: str
    series: ObservedSeries
    reference: dict


def verify_receipt(receipt):
    for path,h in receipt['files'].items():
        if digest(path)!=h:raise ContractError('Collected input changed: '+path)
    if not receipt['technical_valid'] or not receipt['cleanup_verified']:
        raise ContractError('Scientifically ineligible collection receipt')


def load_source(entry,receipt,family,feature,*,authority,test_release=None):
    validate_membership(entry,authority)
    if entry['partition']=='TEST':
        validate_test_release(test_release,authority)
    if (family,feature) not in FEATURES:raise ContractError('Unknown observable feature')
    if receipt['entry_id']!=entry['id']:raise ContractError('Source membership changed')
    root=Path(receipt['features']).resolve();dataset=Path(receipt['dataset']).resolve()
    mp=safe_file(root,'feature_manifest.json');m=read_json(mp)
    if digest(mp)!=receipt['feature_manifest_sha256']:raise ContractError('Feature manifest changed')
    version = m['feature_schema_version']
    if m['source_run_id']!=receipt['run_id'] or type(version) is not int or version not in (1,2) or m['window']['size_seconds']!='1' or not 390<=m['window']['windows']<=421:
        raise ContractError('Scientific grid/run mismatch')
    dm=safe_file(dataset,'dataset_manifest.json')
    if digest(dm)!=m['dataset_manifest_sha256'] or digest(dm)!=receipt['dataset_manifest_sha256']:
        raise ContractError('Stage8/10 binding changed')
    schema=read_json(checked_output(root,m,'feature_schema.json'))
    if schema!=feature_schema(version):raise ContractError('Unsupported feature schema')
    status_path = safe_file(dataset, 'metadata/run_status.json')
    dm_doc = read_json(dm)
    status_ref = [r for r in dm_doc['files'] if r['path']=='metadata/run_status.json']
    if len(status_ref)!=1 or digest(status_path)!=status_ref[0]['sha256']:
        raise ContractError('CPU declaration status binding mismatch')
    dataset_status = read_json(status_path)
    if dataset_status.get('cpu_observation_contract') and version != 2:
        raise ContractError('New CPU collection cannot use historical features')
    if version == 1:
        from experiments.cpu_features import PATHS
        files = {r['path'] for r in dm_doc['files']}
        if PATHS[0] in files:
            raise ContractError('CPU snapshot marker cannot use historical features')
        if PATHS[1] in files:
            import json
            with safe_file(dataset, PATHS[1]).open() as stream:
                first = stream.readline()
            if first and json.loads(first).get('contract'):
                raise ContractError('Versioned CPU evidence cannot use historical features')
    if version == 2:
        from experiments.extract_features import Inputs
        from experiments.cpu_features import load_evidence, assign_cpu
        from simulator.cpu_observations import CONTRACT
        if m.get('cpu_observation_contract') != CONTRACT or m.get('cpu_quality_path') != 'cpu_quality.json':
            raise ContractError('CPU feature contract missing')
        quality = read_json(checked_output(root,m,'cpu_quality.json'))
        inputs = Inputs(dataset, checked_output(root,m,'evidence/stage9_validation_report.json'))
        evidence = load_evidence(inputs, dataset_status)
        if evidence is None:raise ContractError('CPU snapshot evidence missing')
        expected_cpu, expected_quality = assign_cpu(*evidence, dataset_status, m['window']['windows'],
                                                  m['cpu_policy']['boundary_tolerance_seconds'])
        if quality != expected_quality or quality['policy'] != m['cpu_policy']:
            raise ContractError('CPU quality replay mismatch')
        if any(item not in m['input_files'] for item in inputs.consumed.values()):
            raise ContractError('CPU evidence provenance missing')
    report_path=checked_output(root,m,'evidence/stage9_validation_report.json');report=read_json(report_path)
    if (not report['dataset_valid'] or not report['analysis_eligible'] or report['run_id']!=receipt['run_id']
        or report['dataset_manifest_sha256']!=digest(dm)
        or m['stage9_validation_report']['sha256']!=digest(report_path)):
        raise ContractError('Validation binding/eligibility changed')
    table=schema['tables'][family];path=checked_output(root,m,table['path'])
    field=next(x for x in table['fields'] if x['name']==feature)
    observations=[]
    with path.open(newline='') as stream:
        reader=csv.DictReader(stream)
        if reader.fieldnames!=[x['name'] for x in table['fields']]:raise ContractError('Scientific feature columns differ')
        for i,row in enumerate(reader):
            if (None in row or any(v is None for v in row.values()) or row['run_id']!=receipt['run_id']
                or int(row['window_index'])!=i or number(row['window_start_seconds'])!=i or number(row['window_end_seconds'])!=i+1):
                raise ContractError('Scientific feature grid changed')
            value=None if row[feature]=='' else number(row[feature])
            if version == 2 and feature == 'mean_cpu_percent' and value != expected_cpu[i]:
                raise ContractError('CPU scalar differs from observation replay')
            if value is None and not field['nullable']:raise ContractError('Required observable missing')
            if value is not None and (value<0 or (field['type']=='integer' and value!=int(value))):
                raise ContractError('Observable domain mismatch')
            # Preserve all-missing secondary inputs as unavailable; never fabricate zero.
            if family=='network' and not m['network_direction']['supported']:value=None
            observations.append(Observation(receipt['run_id'],i,D(i),D(i+1),value))
    if len(observations)!=m['window']['windows']:raise ContractError('Incomplete scientific grid')
    checked_output(root,m,table['path'])
    if digest(mp)!=receipt['feature_manifest_sha256']:raise ContractError('Feature manifest changed during read')
    ref=dict(entry_id=entry['id'],partition=entry['partition'],seed=entry['seed'],run_id=receipt['run_id'],
        feature_manifest=str(mp),feature_manifest_sha256=digest(mp),dataset_manifest=str(dm),
        dataset_manifest_sha256=digest(dm),observable_path=str(path),observable_sha256=digest(path),
        validation_path=str(report_path),validation_sha256=digest(report_path),family=family,feature=feature,
        authority=authority,test_release=test_release)
    if version == 2:
        ref['feature_schema_version'] = version
    return Source(entry['id'],entry['partition'],ObservedSeries(receipt['run_id'],family,feature,D(1),version,tuple(observations)),ref)


def validate_membership(entry,authority):
    if digest(authority['plan_path'])!=authority['plan_sha256']:raise ContractError('Scientific authority changed')
    plan=read_json(authority['plan_path'])
    from .protocol import runtime_hashes
    if plan['runtime_hashes']!=runtime_hashes():raise ContractError('Code changed after scientific freeze')
    match=[e for e in plan['entries'] if e['id']==entry['id']]
    if len(match)!=1 or any(match[0][key]!=entry[key] for key in ('partition','seed')):
        raise ContractError('Source does not belong to designated scientific partition')


def validate_test_release(ref,authority):
    from ..artifacts import open_artifact
    if ref is None:raise ContractError('TEST source locked until accepted CAL-B checkpoint')
    cp=open_artifact(ref,'scientific-checkpoint').read()
    if cp['partition']!='CAL_B' or cp['authority']!=authority:raise ContractError('Wrong TEST analysis release')
    if SPEC.get('configuration_contract') == 'complete-direct-b2-v1':
        from .engine import verification_metadata
        cal_a=open_artifact(cp['previous_checkpoint'],'scientific-checkpoint').read()
        if cal_a['partition']!='CAL_A' or cal_a['authority']!=authority:
            raise ContractError('Wrong CAL-A checkpoint ancestry')
        if set(cp['artifacts'])!={f for _,f in FEATURES}:
            raise ContractError('Incomplete CAL-B feature inventory')
        for _,feature in FEATURES:
            v=verification_metadata(open_artifact(cp['artifacts'][feature],'scientific-verification'))
            if v['authority']!=authority or v['calibration']!=cal_a['artifacts'][feature]:
                raise ContractError('CAL-B verification/calibration ancestry differs')
        return
    v=open_artifact(cp['artifacts']['request_starts'],'scientific-verification').read()
    from .protocol import METHODS
    if not v['approved'] or v['authority']!=authority or not all(v['method_accepted'].get(method) is True for method in METHODS):
        raise ContractError('TEST locked after CAL-B rejection')
    cal_a=open_artifact(cp['previous_checkpoint'],'scientific-checkpoint').read()
    if cal_a['partition']!='CAL_A' or cal_a['artifacts']['request_starts']!=v['calibration']:
        raise ContractError('TEST release calibration checkpoint differs')


def verify_reference(ref):
    validate_membership(dict(id=ref['entry_id'],partition=ref['partition'],seed=ref['seed']),ref['authority'])
    if ref['partition']=='TEST':validate_test_release(ref['test_release'],ref['authority'])
    for path_key,hash_key in (('feature_manifest','feature_manifest_sha256'),('dataset_manifest','dataset_manifest_sha256'),
        ('observable_path','observable_sha256'),('validation_path','validation_sha256')):
        if digest(ref[path_key])!=ref[hash_key]:raise ContractError('Scientific source reference changed')


def load_truth(entry,receipt):
    """Only evaluation calls this; events are verified against Stage8, never inferred."""
    dataset=Path(receipt['dataset']);m=read_json(dataset/'dataset_manifest.json')
    if digest(dataset/'dataset_manifest.json')!=receipt['dataset_manifest_sha256']:raise ContractError('Truth source changed')
    def linked(relative):
        records=[x for x in m['files'] if x['path']==relative]
        if len(records)!=1:raise ContractError('Truth file not uniquely bound')
        path=safe_file(dataset,relative);ref=records[0]
        if digest(path)!=ref['sha256'] or path.stat().st_size!=ref['bytes']:raise ContractError('Truth bytes changed')
        return path
    status=read_json(linked(m['run_status']))
    if status['run_id']!=receipt['run_id'] or status['status']!='completed':raise ContractError('Invalid event run/clock')
    config=read_json(linked('metadata/effective_config.json'))
    if config['id']!=entry['id'] or config['seed']!=entry['seed']:raise ContractError('Truth config identity differs')
    path=linked('raw/attacks/attack_events.csv')
    with path.open(newline='') as stream:events=list(csv.DictReader(stream))
    if len(events)!=int(entry['scenario']!=SPEC['control_scenario']):raise ContractError('Wrong scientific event count')
    for event in events:
        if (event['run_id']!=receipt['run_id'] or event['experiment_id']!=entry['id'] or event['profile']!='continuous'
            or number(event['experiment_start_timestamp'])!=number(status['experiment_start_timestamp'])
            or number(event['experiment_start_monotonic'])!=number(status['experiment_start_monotonic'])
            or number(event['scheduled_start_seconds'])!=150 or number(event['scheduled_end_seconds'])!=270
            or not 150<=number(event['actual_start_seconds'])<number(event['actual_end_seconds'])<=300):
            raise ContractError('Scientific event identity/times differ')
    return dict(events=events,reference=dict(path=str(path),sha256=digest(path),run_id=receipt['run_id']))
