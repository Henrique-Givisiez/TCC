"""Frozen campaign design, content-addressed references and partition gates.

No experiment execution, statistical calibration or decision threshold here.
"""
from dataclasses import replace
import hashlib
from pathlib import Path

from .artifacts import encoded
from .inputs import ContractError, digest, read_json

FEATURES = ['ingress_packet_count', 'ingress_tcp_payload_length_sum_bytes',
            'request_starts', 'mean_duration_ms', 'mean_cpu_percent']
FROZEN = dict(seed_counts={'baseline':6,'calibration':12,'test':16},
              scenarios={'baseline':['B'],'calibration':['B'],'test':['B','C','P']},
              operation='/medium', benign_sources=4, benign_rps_per_source=2,
              attackers=1, attacker_rps_per_source=8,
              continuous={'profile':'continuous','active_seconds':36},
              periodic={'profile':'periodic_burst','burst_seconds':2,'period_seconds':6,'duty_cycle':'1/3'},
              durations={'baseline':240,'calibration':360,'test':144,'pre':48,'attack':36,'post':60},
              window_size_seconds=1, features=FEATURES,
              zscore={'signed':True,'ddof':1,'baseline':'pooled_independent_observations'},
              cov={'primary_lookback':6,'sensitivity_lookbacks':[3,12],'ddof':1,
                   'missing':'consecutive_valid_observations','zero_mean':'unavailable'},
              fit_interval={'start_seconds':48,'end_seconds':240,
                            'inclusion':'whole_windows_contained_in_half_open_interval'},
              calibration_strategy='benign_only',
              window_truth={'primary':'pure_windows_only','benign_overlap':0,'attack_overlap':1,
                            'boundary':'excluded_from_primary','complementary':'continuous_overlap'},
              event_truth={'source':'verified_stage8_attack_events','primary':'global_actual_start_to_actual_end',
                           'policy':'global_overlap_and_availability_within_event_v1',
                           'availability_deadline':'actual_end_inclusive_no_post_event_grace'},
              detection_delay='first_valid_detection_available_time_minus_actual_start',
              seed_policy='disjoint_partitions_independent_runs_no_pilot_seed_reuse',
              test_isolation='locked_until_models_features_parameters_and_policies_frozen',
              false_alarm_reporting=['benign_windows','benign_exposure_seconds','false_positives',
                                     'fpr','alarms_per_time','uncertainty_when_appropriate'],
              topology={'execution':'containers','victims':1,'proxy':'nginx','autoscaling':False,
                        'pool':2,'send_workers_per_class':64,'request_timeout_seconds':2,
                        'monitor_interval_seconds':1,'parallel_runs':False},
              scoring_horizon='full_feature_series_preserved',
              primary_evaluation_horizon='whole_windows_within_planned_run_duration')
UNRESOLVED = ('numerical_thresholds','decision_directions','false_positive_operating_budget',
              'uncertainty_reporting_details','exact_image_and_environment_lock')


V1_SHA256 = '79b204d7d781a939de7a95ab77b8e98ccbd15b5fe250fa237e0db1d0e7fa9e13'
EVENT_POLICY_V2 = 'global_observation_overlap_decision_availability_v2'

# V1 remains immutable and readable. Version 2 changes only the approved blockers.
from copy import deepcopy
FROZEN_V2 = deepcopy(FROZEN)
FROZEN_V2['event_truth'] = dict(source='verified_stage8_attack_events',
    primary='global_actual_start_to_actual_end', policy=EVENT_POLICY_V2,
    availability_deadline='none_eligibility_by_positive_half_open_observation_overlap',
    miss_censoring='not_detected_in_supplied_series_no_finite_decision_deadline')
FROZEN_V2['temporal_selections'] = dict(
    baseline=[48,240], calibration=[48,360], test=[0,144],
    inclusion='whole_windows_contained_in_half_open_interval',
    causal_history='preserved_from_run_start_no_reset_at_selection_start')
UNRESOLVED_V2 = tuple(k for k in UNRESOLVED if k != 'exact_image_and_environment_lock') + (
    'test_pre_region_false_positive_metric_roles', 'confirmation_hysteresis')
V2_BINDINGS = ('experiments/protocols/stage14_seed_plan_v2.json',
               'experiments/protocols/stage14_matrix_v2.json',
               'experiments/protocols/stage14_environment_lock_v2.json')


def frozen_for_version(version):
    if type(version) is not int or version not in (1,2):
        raise ContractError('Unsupported protocol version')
    return FROZEN if version == 1 else FROZEN_V2


def validate_protocol(document):
    required = {'protocol_id','protocol_version','status','created_at_utc','references',
                'frozen','unresolved','seeds','limitations','provenance','previous_protocol_hash'}
    if not isinstance(document,dict) or set(document) != required:
        raise ContractError('Protocol schema: missing/unknown fields')
    if (document['protocol_id'] != 'stage14-balanced' or type(document['protocol_version']) is not int
            or document['protocol_version'] not in (1,2) or document['status'] != 'FROZEN_DESIGN_PENDING_RELEASE'):
        raise ContractError('Protocol identity/version/status invalid')
    from datetime import datetime
    try:
        timestamp = datetime.fromisoformat(document['created_at_utc'].replace('Z','+00:00'))
        if timestamp.utcoffset().total_seconds() != 0:
            raise ValueError()
    except (ValueError,TypeError,AttributeError) as exc:
        raise ContractError('Protocol UTC timestamp invalid') from exc
    if encoded(document['frozen']) != encoded(frozen_for_version(document['protocol_version'])):
        raise ContractError('FROZEN design differs from approved protocol B')
    unresolved = UNRESOLVED if document['protocol_version'] == 1 else UNRESOLVED_V2
    if set(document['unresolved']) != set(unresolved) or any(
        v != {'status':'UNRESOLVED','value':None} for v in document['unresolved'].values()):
        raise ContractError('Unresolved choices must remain explicitly UNRESOLVED')
    if (not isinstance(document['references'],dict) or not isinstance(document['limitations'],list)
            or not isinstance(document['provenance'],dict)
            or not document['references'] or not document['limitations'] or not document['provenance']):
        raise ContractError('Protocol evidence/provenance required')
    import re
    if not isinstance(document['references'],dict) or any(
        not isinstance(k,str) or not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v)
        for k,v in document['references'].items()):
        raise ContractError('Protocol references require path/SHA256 mappings')
    if not isinstance(document['limitations'],list) or not all(isinstance(x,str) and x for x in document['limitations']):
        raise ContractError('Protocol limitations required')
    if document['provenance'].get('run_count') != 66:
        raise ContractError('Protocol run count mismatch')
    seeds = document['seeds']
    if not isinstance(seeds,dict) or set(seeds) != {'status','method','excluded','namespace','partitions'}:
        raise ContractError('Explicit seed contract fields required')
    if seeds.get('method') != 'sha256_protocol_namespace_partition_index_first32_collision_rejection_v1':
        raise ContractError('Seed generation method missing/unsupported')
    if seeds.get('excluded') != [101,211,307,401,503] or not seeds.get('namespace'):
        raise ContractError('Seed provenance/exclusions invalid')
    if seeds.get('status') == 'DEFERRED':
        if seeds.get('partitions') is not None:
            raise ContractError('Deferred seed sets must be explicit null')
    elif seeds.get('status') == 'MATERIALIZED':
        expected = materialize_seeds(seeds['namespace'])
        if seeds.get('partitions') != expected:
            raise ContractError('Seed assignments do not match deterministic disjoint generator')
    else:
        raise ContractError('Seed materialization status required')
    if document['protocol_version'] == 1:
        if document['previous_protocol_hash'] is not None:
            raise ContractError('Initial protocol cannot reference predecessor')
    elif not isinstance(document['previous_protocol_hash'],str) or not re.fullmatch('[0-9a-f]{64}', document['previous_protocol_hash']):
        raise ContractError('Revised protocol requires predecessor hash')
    if document['protocol_version'] == 2:
        if document['previous_protocol_hash'] != V1_SHA256 or seeds['status'] != 'MATERIALIZED':
            raise ContractError('V2 requires original V1 predecessor and materialized seeds')
        if not all(path in document['references'] for path in V2_BINDINGS):
            raise ContractError('V2 requires seed plan, matrix and environment lock bindings')
    return document


def materialize_seeds(namespace):
    """Pure deterministic proposal, no outputs/runs; rejects pilot and collisions."""
    used = {101,211,307,401,503}
    result = {}
    for partition, count in FROZEN['seed_counts'].items():
        result[partition] = []
        index = 0
        while len(result[partition]) < count:
            value = int.from_bytes(hashlib.sha256(f'{namespace}:{partition}:{index}'.encode()).digest()[:4],'big')
            index += 1
            if value not in used:
                used.add(value); result[partition].append(value)
    return result


def load_protocol(path, *, expected_hash=None):
    path = Path(path).resolve()
    before = digest(path)
    if expected_hash is not None and before != expected_hash:
        raise ContractError('Protocol hash mismatch')
    document = validate_protocol(read_json(path))
    if digest(path) != before:
        raise ContractError('Protocol changed while reading')
    return document, dict(protocol_id=document['protocol_id'], protocol_version=document['protocol_version'],
                          protocol_hash=before, path=str(path))


def write_protocol(path, document, *, previous=None):
    """Append-only publication; revision requires previous exact version/hash."""
    validate_protocol(document)
    approved = Path(__file__).resolve().parents[2] / 'experiments/protocols/stage14_protocol.json'
    if document['protocol_version'] == 1 and approved.exists() and document != read_json(approved):
        raise ContractError('Changed protocol must use a new version and predecessor hash')
    if document['protocol_version'] > 1:
        if previous is None:
            raise ContractError('Previous protocol reference required')
        old, ref = load_protocol(previous['path'], expected_hash=previous['protocol_hash'])
        if (document['protocol_id'] != old['protocol_id']
                or document['protocol_version'] != old['protocol_version']+1
                or document['previous_protocol_hash'] != ref['protocol_hash']):
            raise ContractError('Changed protocol must increment version and link predecessor')
    elif previous is not None:
        raise ContractError('Revision requires new version')
    path = Path(path)
    with path.open('xb') as stream:
        stream.write(encoded(document).encode())
    return load_protocol(path)[1]


def bind_source(source, protocol_reference, *, partition, seed, scenario):
    """Attach verifiable campaign membership, without exposing it to callbacks.

    The frozen proposal intentionally has no release capability: TEST cannot even
    be bound/read for analysis here. A later reviewed release must unlock final
    scoring/evaluation after actual artifacts/policies are frozen.
    """
    import json
    document, ref = load_protocol(protocol_reference['path'], expected_hash=protocol_reference['protocol_hash'])
    if protocol_reference != ref:
        raise ContractError('Protocol reference identity mismatch')
    if partition not in FROZEN['seed_counts']:
        raise ContractError('Unknown partition')
    if partition == 'test':
        raise ContractError('TEST locked: final release not implemented/approved')
    if document['seeds']['status'] != 'MATERIALIZED':
        raise ContractError('Campaign seeds not materialized')
    if seed not in document['seeds']['partitions'][partition] or scenario not in FROZEN['scenarios'][partition]:
        raise ContractError('Run seed/scenario not assigned to partition')
    if source.role != partition:
        raise ContractError('Source role conflicts with protocol partition')
    source.verify()
    reference = source.reference
    reference['campaign'] = dict(protocol=ref, partition=partition, seed=seed, scenario=scenario)
    return replace(source,reference_json=json.dumps(reference,sort_keys=True))


def guard_reference(reference, operation):
    if reference.get('role') == 'test':
        raise ContractError(f'TEST locked: {operation} forbidden before final release')
    campaign = reference.get('campaign')
    if not campaign:
        return  # Existing historical/development datasets are not scientific campaign inputs.
    document, ref = load_protocol(campaign['protocol']['path'],expected_hash=campaign['protocol']['protocol_hash'])
    if campaign['protocol'] != ref or reference['role'] != campaign['partition']:
        raise ContractError('Campaign identity/role mismatch')
    partition = campaign['partition']
    if partition == 'test':
        raise ContractError(f'TEST locked: {operation} forbidden before final release')
    if (document['seeds']['status'] != 'MATERIALIZED' or partition not in FROZEN['seed_counts']
            or campaign['seed'] not in document['seeds']['partitions'][partition]
            or campaign['scenario'] not in FROZEN['scenarios'][partition]):
        raise ContractError('Invalid campaign assignment')
    if operation == 'fit' and partition != 'baseline':
        raise ContractError('Fitting requires BASELINE')
    if operation in ('calibration','parameter_selection') and partition != 'calibration':
        raise ContractError('Selection/calibration requires CALIBRATION')


def load_campaign_series(dataset, *, protocol_reference, partition, seed, scenario, **selection):
    """Gate TEST before even opening a feature table; no final-release bypass."""
    if partition == 'test':
        raise ContractError('TEST locked: final release required before input access')
    from .inputs import load_series
    if 'role' in selection:
        raise ContractError('Campaign role is determined by partition')
    # Validate protocol before any dataset reads.
    document, ref = load_protocol(protocol_reference['path'], expected_hash=protocol_reference['protocol_hash'])
    if (document['seeds']['status'] != 'MATERIALIZED' or partition not in FROZEN['seed_counts']
            or seed not in document['seeds']['partitions'][partition]
            or scenario not in FROZEN['scenarios'][partition]):
        raise ContractError('Invalid/unmaterialized campaign assignment')
    return bind_source(load_series(dataset, role=partition, **selection), ref,
                       partition=partition, seed=seed, scenario=scenario)


def run_protocol_reference(protocol_reference, *, partition, seed, scenario):
    """Metadata for future run manifests only. Does not read data or unlock TEST."""
    document, ref = load_protocol(protocol_reference['path'], expected_hash=protocol_reference['protocol_hash'])
    if ref != protocol_reference:
        raise ContractError('Protocol reference identity mismatch')
    if (document['seeds']['status'] != 'MATERIALIZED' or partition not in FROZEN['seed_counts']
            or type(seed) is not int or seed not in document['seeds']['partitions'][partition]
            or scenario not in FROZEN['scenarios'][partition]):
        raise ContractError('Run does not belong to materialized protocol assignment')
    return dict(protocol_id=ref['protocol_id'],protocol_version=ref['protocol_version'],
                protocol_hash=ref['protocol_hash'],partition=partition,seed=seed,scenario=scenario)
