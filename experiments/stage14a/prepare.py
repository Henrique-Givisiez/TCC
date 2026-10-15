"""Deterministic sidecar plan. Never edits or executes the frozen protocol."""
import argparse
import hashlib
import json
from pathlib import Path

from analysis.detection.protocol import load_protocol, materialize_seeds
from simulator.experiment_config import ExperimentConfig
from pilot_stage13.run import configuration

EXPECTED = '79b204d7d781a939de7a95ab77b8e98ccbd15b5fe250fa237e0db1d0e7fa9e13'
PROTOCOL = Path('experiments/protocols/stage14_protocol.json')
SMOKE_NAMESPACE = 'stage14a-smoke-development-v1'


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(encode(value))


def build_plan():
    protocol, _ = load_protocol(PROTOCOL, expected_hash=EXPECTED)
    seeds = materialize_seeds(protocol['seeds']['namespace'])
    used = set(protocol['seeds']['excluded']) | {s for values in seeds.values() for s in values}
    smoke = []
    index = 0
    while len(smoke) < 4:
        value = int.from_bytes(hashlib.sha256(f'{SMOKE_NAMESPACE}:{index}'.encode()).digest()[:4], 'big')
        index += 1
        if value not in used:
            used.add(value)
            smoke.append(value)
    runs = []
    for partition, values in seeds.items():
        for seed in values:
            for scenario in protocol['frozen']['scenarios'][partition]:
                config = configuration(seed, scenario)
                duration = protocol['frozen']['durations'][partition]
                config.update(id=f'stage14_{partition}_{seed}_{scenario}', duration_seconds=duration)
                config['attack']['start_seconds'] = 48
                config['attack']['duration_seconds'] = 36
                ExperimentConfig.from_dict(config)
                runs.append(dict(order=len(runs)+1, partition=partition, seed=seed, scenario=scenario,
                    duration_seconds=duration, scientific=True, executed=False,
                    config=config, config_sha256=hashlib.sha256(encode(config)).hexdigest(),
                    fit_interval=[48,240] if partition=='baseline' else None,
                    paired_positions={'PRE':[0,48], 'ATTACK':[48,84], 'POST':[84,144]} if partition=='test' else None,
                    attack_ground_truth_expected=scenario!='B'))
    return dict(schema_version=1, status='MATERIALIZED_NOT_RELEASED',
        protocol=dict(path=str(PROTOCOL), sha256=EXPECTED, id=protocol['protocol_id'], version=protocol['protocol_version']),
        protocol_unchanged_seeds_status=protocol['seeds']['status'],
        seed_generation=dict(method=protocol['seeds']['method'], namespace=protocol['seeds']['namespace'],
            encoding='UTF-8 namespace:partition:index; index starts at 0 per partition; first four SHA256 bytes big endian unsigned; reject pilot or any previously accepted seed; increment index on every candidate',
            partition_order=['baseline','calibration','test'], external_random_seed=None, outcome_independent=True),
        partitions=seeds, run_count=len(runs), nominal_seconds=sum(r['duration_seconds'] for r in runs), runs=runs,
        smoke_development=dict(namespace=SMOKE_NAMESPACE, method='SHA256 UTF-8 namespace:index, first four bytes big endian; index from 0; reject pilot/scientific/previous smoke seeds',
            seeds=smoke, assignments=dict(zip(['fit_B','score_B','score_C','score_P'],smoke)),
            scientific=False, excluded_from_all_scientific_partitions=True),
        blockers=['Frozen event availability deadline conflicts with requested overlap attribution',
                  'Calibration warm-up selection needs explicit approval',
                  'Protocol still DEFERRED: sidecar is not a released protocol revision',
                  'Scientific executor binding and TEST release remain pending'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    plan=build_plan()
    # All results are new outputs. Existing directories are never overwritten.
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'campaign_plan.json', plan)
    for run in plan['runs']:
        write(args.output/f"configs/{run['order']:02d}_{run['partition']}_{run['seed']}_{run['scenario']}.json",run['config'])
    write(args.output/'hashes.json',{str(p.relative_to(args.output)):sha(p) for p in sorted(args.output.rglob('*')) if p.is_file()})
    print(json.dumps(dict(partitions=plan['partitions'],smoke=plan['smoke_development'],runs=plan['run_count'],seconds=plan['nominal_seconds']),indent=2))

if __name__=='__main__':main()
