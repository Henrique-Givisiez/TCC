"""Structural direct-80 authority; no collection or calibration release."""
from copy import deepcopy
from collections import Counter
import hashlib
import json
from ..inputs import ContractError, digest, read_json
from simulator.experiment_config import ExperimentConfig


def configuration(spec, scenario, identity, seed):
    if scenario not in spec['scenarios'] or type(seed) is not int or not 0 <= seed < 2**64:
        raise ContractError('Unknown scenario or invalid traffic seed')
    if not isinstance(identity,str) or not identity:
        raise ContractError('Missing configuration identity')
    result = deepcopy(spec['scenario_configurations'][scenario])
    result.update(id=identity, seed=seed)
    if json.loads(ExperimentConfig.from_dict(result).to_json()) != result:
        raise ContractError('Noncanonical effective configuration')
    return result


def validate_configuration(spec, scenario, identity, seed, effective):
    if effective != configuration(spec,scenario,identity,seed):
        raise ContractError('Configuration differs from complete direct matrix')


def validate_image_lock(images):
    if (set(images) != {'victim','source'} or any(not isinstance(v,str) or len(v)!=71
            or not v.startswith('sha256:') or any(c not in '0123456789abcdef' for c in v[7:])
            for v in images.values())):
        raise ContractError('Direct environment requires only immutable victim/source IDs')


def validate_spec(spec, root):
    if (spec['protocol_id']!='single-victim-direct-80-20261108' or spec['version']!=3
            or spec['counts']!=dict(BASELINE=4,CAL_A=8,CAL_B=8,TEST=60)
            or spec['test_blocks']!=20 or spec['scenarios']!=['L2','A3','F96']
            or spec['control_scenario']!='L2' or spec['nominal_seconds']!=390
            or spec['attack_interval']!=[150,270] or spec['drain_seconds']!=30
            or spec['window_seconds']!=1 or spec['feature_schema_version']!=2
            or spec['environment_image_roles']!=['victim','source']
            or spec['replacements']['maximum_total_attempts']!=82):
        raise ContractError('Direct-80 numerical/identity contract differs')
    from .protocol import FEATURES, METHODS, PARTITIONS
    if (spec['features'] != [list(f) for f in FEATURES] or spec['methods'] != list(METHODS)
            or spec['checkpoints'] != list(PARTITIONS)
            or spec['phases'] != dict(WARMUP=[0,30],PRE=[30,150],ATTACK=[150,270],POST=[270,390])
            or spec['selection'] != [30,390]
            or any(spec[k] != v for k,v in dict(cal_a_mean_max='0.01',cal_a_run_max='0.05',
                   cal_b_mean_max='0.02',cal_b_run_max='0.05',minimum_available_fraction='0.95').items())
            or spec['eligibility']['unit'] != 'method_x_feature'
            or spec['eligibility']['global_test_block'] is not False
            or spec['evaluation_contract']['offensive_post']['automatically_benign'] is not False):
        raise ContractError('Approved features/phases/calibration/evaluation contract differs')
    for position in range(3):
        counts=Counter(row[position] for row in spec['test_order'])
        if set(counts)!=set(spec['scenarios']) or sorted(counts.values())!=[6,7,7]:
            raise ContractError('Unbalanced direct TEST positions')
    for scenario in spec['scenarios']:
        source=spec['configuration_sources'][scenario]
        path=root/source['path']
        if digest(path)!=source['sha256']:raise ContractError('B2 configuration source changed')
        original=read_json(path)
        for key in ('id','seed'):original.pop(key)
        original['duration_seconds']=390
        original['attack'].update(start_seconds=150,duration_seconds=120)
        if original!=spec['scenario_configurations'][scenario]:
            raise ContractError('Configuration changes exceed approved B2 transformation')
        configuration(spec,scenario,'structural-validation',0)
    cpu=spec['cpu_contract']
    if cpu!=dict(contract='victim-cpu-snapshots-v1',interval_seconds=1,scheduling_lead_seconds='0.025',
                 boundary_tolerance_seconds='0.05',provisional=True,availability='received_by_window_closure',
                 missing='null',interpolation=False,cache_repetition=False,attack_validation_pending=True):
        raise ContractError('CPU contract changed')
    if spec['execution_release']['allowed'] is not False:
        raise ContractError('Direct specification cannot release collection yet')


def draft_entries(spec, historical_seeds, namespace):
    """Pure prospective draft, not a frozen plan; historical inventory is mandatory.

    Reuse the existing slot and seed grouping rules. No files or seeds are
    materialized by C1.3.1. Caller must audit the full inventory at future freeze.
    """
    from .protocol import expected_slots
    if not namespace or not historical_seeds:
        raise ContractError('Explicit namespace and historical seed inventory required')
    used=set(historical_seeds)|{spec['ci']['rng_seed']}
    groups={};entries=[]
    for i,slot in enumerate(expected_slots(spec),1):
        group=('TEST',slot['block']) if slot['partition']=='TEST' else (slot['partition'],slot['ordinal'])
        if group not in groups:
            counter=0
            while True:
                raw=json.dumps([spec['protocol_id'],namespace,group,counter],separators=(',',':')).encode()
                seed=int.from_bytes(hashlib.sha256(raw).digest()[:8],'big')
                if seed not in used:break
                counter+=1
            groups[group]=seed;used.add(seed)
        entries.append(dict(slot,id=f"direct80_{i:03d}_{slot['scenario']}",seed=groups[group]))
    return entries
