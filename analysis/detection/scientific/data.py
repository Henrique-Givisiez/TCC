"""Scientific membership and byte-verified scalar IO; no legacy role bypass."""
import csv
from dataclasses import dataclass
from decimal import Decimal as D
from pathlib import Path

from ..contracts import Observation, ObservedSeries
from ..inputs import ContractError, read_json, digest, safe_file, checked_output, number
from experiments.feature_schema import feature_schema
from .protocol import FEATURES


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
    if m['source_run_id']!=receipt['run_id'] or m['feature_schema_version']!=1 or m['window']['size_seconds']!='1' or not 390<=m['window']['windows']<=421:
        raise ContractError('Scientific grid/run mismatch')
    dm=safe_file(dataset,'dataset_manifest.json')
    if digest(dm)!=m['dataset_manifest_sha256'] or digest(dm)!=receipt['dataset_manifest_sha256']:
        raise ContractError('Stage8/10 binding changed')
    schema=read_json(checked_output(root,m,'feature_schema.json'))
    if schema!=feature_schema():raise ContractError('Unsupported feature schema')
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
    return Source(entry['id'],entry['partition'],ObservedSeries(receipt['run_id'],family,feature,D(1),1,tuple(observations)),ref)


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
    if len(events)!=int(entry['scenario']!='C16'):raise ContractError('Wrong scientific event count')
    for event in events:
        if (event['run_id']!=receipt['run_id'] or event['experiment_id']!=entry['id'] or event['profile']!='continuous'
            or number(event['experiment_start_timestamp'])!=number(status['experiment_start_timestamp'])
            or number(event['experiment_start_monotonic'])!=number(status['experiment_start_monotonic'])
            or number(event['scheduled_start_seconds'])!=150 or number(event['scheduled_end_seconds'])!=270
            or not 150<=number(event['actual_start_seconds'])<number(event['actual_end_seconds'])<=300):
            raise ContractError('Scientific event identity/times differ')
    return dict(events=events,reference=dict(path=str(path),sha256=digest(path),run_id=receipt['run_id']))
