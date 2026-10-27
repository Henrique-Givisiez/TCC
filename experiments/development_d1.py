"""Offline D1 plan checks and observed-lifecycle service summaries; never runs traffic."""
import argparse
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from simulator.experiment_config import ExperimentConfig
from experiments.summarize_service import load_requests, number, ratio, summarize, json_default

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def historical_seed_inputs(root=ROOT):
    """Configuration/seed metadata only, not scores, observations or labels."""
    paths = {root / 'effective_config.json'}
    for folder in ('experiments/configs', 'experiments/protocols', 'docs/stage14a/materialized', 'experiment_results'):
        for path in (root / folder).rglob('*.json'):
            relative = path.relative_to(root)
            if any(part in ('development_d1_20261027', 'development-d1-20261027') for part in relative.parts):
                continue
            if (path.name == 'effective_config.json' or 'seed' in path.name.lower()
                    or 'configs' in relative.parts or path.name == 'campaign_plan.json'):
                paths.add(path)
    # Current scientific partition authority is always checked explicitly.
    paths.add(root / 'experiments/protocols/stage14_seed_plan_v2.json')
    return sorted(p for p in paths if p.is_file())


def collect_seeds(value, seed_context=False):
    result = set()
    if isinstance(value, dict):
        for key, child in value.items():
            context = seed_context or 'seed' in key.lower() or key in ('partitions', 'pilot_exclusions', 'assignments')
            result.update(collect_seeds(child, context))
    elif isinstance(value, list):
        for child in value:
            result.update(collect_seeds(child, seed_context))
    elif seed_context and type(value) is int and value >= 0:
        result.add(value)
    return result


def validate_plan(manifest_path, *, check_outputs=True):
    manifest_path = Path(manifest_path)
    plan = json.loads(manifest_path.read_text())
    if plan['partition'] != 'DEVELOPMENT' or plan['automatic_progression'] is not False:
        raise ValueError('D1 requires DEVELOPMENT and gated progression')
    for relative, expected_hash in plan['reviewed_runtime_sources_sha256'].items():
        if digest(ROOT / relative) != expected_hash:
            raise ValueError('Reviewed runtime/summary code changed; review D1 plan')
    audit = json.loads((ROOT / plan['seed_audit']).read_text())
    existing_seeds = set()
    for source in audit['sources']:
        path = ROOT / source['path']
        if digest(path) != source['sha256']:
            raise ValueError('Historical seed metadata changed; review reservation')
        seeds = collect_seeds(json.loads(path.read_text()))
        if sorted(seeds) != source['seeds']:
            raise ValueError('Historical seed extraction differs')
        existing_seeds.update(seeds)
    if {s['path'] for s in audit['sources']} != {p.relative_to(ROOT).as_posix() for p in historical_seed_inputs()}:
        raise ValueError('Historical seed metadata inventory changed; review reservation')
    reserved = set(plan['development_seeds'].values())
    generation = plan['seed_generation']
    generated = {rep: int.from_bytes(hashlib.sha256(
        f"{generation['namespace']}:{rep}:{generation['indices'][rep]}".encode()).digest()[:8], 'big')
        for rep in ('A', 'B')}
    if generated != plan['development_seeds']:
        raise ValueError('Seed derivation differs from reserved namespace/indices')
    if len(reserved) != 2 or reserved & existing_seeds:
        raise ValueError('DEVELOPMENT seed collision')
    paths, identities, configs = set(), set(), []
    entries = plan['entries']
    expected_order = [(rate, rep) for index, rate in enumerate((1, 2, 4, 8, 16))
                      for rep in (('A', 'B') if index % 2 == 0 else ('B', 'A'))]
    if [(e['rps_per_client'], e['replicate']) for e in entries] != expected_order:
        raise ValueError('Unexpected D1 ladder/order')
    for position, entry in enumerate(entries, 1):
        path = ROOT / entry['config']
        config = ExperimentConfig.load(path)
        effective = json.loads(config.to_json())
        if (json.loads(path.read_text()) != effective or effective != entry['effective_configuration'] or digest(path) != entry['config_sha256']
                or config.id != entry['id'] or config.id in identities or entry['order'] != position
                or config.seed != plan['development_seeds'][entry['replicate']]):
            raise ValueError('Configuration/order/seed/hash mismatch')
        identities.add(config.id)
        expected = ExperimentConfig.from_dict(plan['fixed_effective_configuration'])
        # Only ID, seed and benign rate change across the block.
        from dataclasses import replace
        expected = replace(expected, id=config.id, seed=config.seed,
                           normal_traffic=replace(expected.normal_traffic, rate=entry['rps_per_client']))
        if config != expected or entry['aggregate_rps'] != config.normal_traffic.clients * config.normal_traffic.rate:
            raise ValueError('D1 fixed conditions changed')
        for output in entry['outputs'].values():
            if output in paths:
                raise ValueError('Repeated output path')
            paths.add(output)
            if check_outputs and (ROOT / output).exists():
                raise ValueError('Output already exists; never repeat/overwrite automatically: ' + output)
        configs.append(dict(id=config.id, seed=config.seed, configuration_valid=True, complete_fields=True))
    return dict(schema_version=1, manifest_sha256=digest(manifest_path), configuration_count=len(configs),
                historical_seed_files=len(audit['sources']), historical_seeds=len(existing_seeds),
                reserved_development_seeds=sorted(reserved), collisions=[], configurations=configs,
                docker_accessed=False, experiments_executed=False)


def resolve_observation(raw, config):
    """Certify cutoff only from the four source_closed records; never max HTTP end."""
    raw = Path(raw)
    status = json.loads((raw / 'run_status.json').read_text())
    inventory = json.loads((raw / 'source_inventory.json').read_text())
    run_id = status['run_id']
    if (len(inventory) != 4 or {e['source_id'] for e in inventory} != {f'normal_{i}' for i in range(1, 5)}
            or {e['worker_index'] for e in inventory} != set(range(4))
            or any(e['source_type'] != 'normal' or e['run_id'] != run_id for e in inventory)):
        raise ValueError('D1 requires exactly four known benign sources')
    closed, begins, finishes, hashes = [], {}, {}, {}
    for entry in inventory:
        source_id = entry['source_id']
        path = raw / 'source_artifacts' / source_id / 'output/journal.jsonl'
        hashes[str(path.relative_to(raw))] = digest(path)
        closures = []
        lines = path.read_text().splitlines(keepends=True)
        for index, line in enumerate(lines, 1):
            if not line.endswith('\n'):
                raise ValueError('Truncated journal; no invented observation limit')
            item = json.loads(line)
            if (item['sequence'] != index or item['run_id'] != run_id or item['source_id'] != source_id):
                raise ValueError('Journal sequence/identity mismatch')
            payload = item['payload']
            if item['kind'] == 'source_closed':
                if index != len(lines):
                    raise ValueError('Source journal continues after closure')
                closures.append(payload)
            elif item['kind'] in ('request_begin', 'request_finish'):
                table = begins if item['kind'] == 'request_begin' else finishes
                key = payload['request_id']
                if key in table or payload['run_id'] != run_id or payload['worker_id'] != entry['worker_index']:
                    raise ValueError('Duplicate/mismatched journal request')
                table[key] = payload
        if len(closures) != 1:
            raise ValueError('Missing/duplicate source_closed: observation end unknown')
        closure = closures[0]
        end = number(closure['elapsed_seconds'])
        if end <= 0:
            raise ValueError('Invalid closure time')
        own = [r for r in begins.values() if r['worker_id'] == entry['worker_index']]
        if any(number(r['elapsed_seconds']) >= end for r in own):
            raise ValueError('Closure does not strictly follow observed starts')
        own_finishes = [r for r in finishes.values() if r['worker_id'] == entry['worker_index']]
        if any(number(r['end_elapsed_seconds']) > end for r in own_finishes):
            raise ValueError('Request completion after its own source closure')
        closed.append(dict(source_id=source_id, elapsed_seconds=end,
                           drained=closure['drained'], logger_complete=closure['logger_complete']))
    requests = load_requests(raw / 'request_log.csv', run_id)
    if set(begins) != {r['request_id'] for r in requests} or set(finishes) != {r['request_id'] for r in requests if r['end'] is not None}:
        raise ValueError('Journals and request CSV do not reconcile')
    cutoff = max(c['elapsed_seconds'] for c in closed)
    for r in requests:
        if (r['traffic_class'] != 'benign' or r['start'] != number(begins[r['request_id']]['elapsed_seconds'])
                or (r['end'] is not None and (r['end'] > cutoff or r['end'] != number(finishes[r['request_id']]['end_elapsed_seconds'])))):
            raise ValueError('Request interval/class differs from lifecycle evidence')
    phases = [dict(name='WARMUP', start_seconds='0', end_seconds='30'),
              dict(name='MEASURE', start_seconds='30', end_seconds=str(config.duration_seconds))]
    nominal = number(config.duration_seconds)
    if cutoff > nominal:
        phases.append(dict(name='DRAIN', start_seconds=str(nominal), end_seconds=str(cutoff)))
    complete = (status.get('status') == 'completed' and status.get('producers_drained') is True
                and status.get('end_reason') == 'simulation_end' and not status.get('errors')
                and len(begins) == len(finishes) and cutoff >= nominal and all(c['drained'] and c['logger_complete']
                    and c['elapsed_seconds'] >= nominal for c in closed))
    return dict(schema_version=1, run_id=run_id, phases=phases), cutoff, dict(
        technical_status_complete=complete, closures=closed, lifecycle_hashes=hashes,
        observation_end_source='max of four observed source_closed elapsed_seconds',
        nominal_end=nominal, observed_drain_seconds=max(Decimal(0), cutoff - nominal))


def summarize_entry(manifest_path, entry_id, destination):
    plan = json.loads(Path(manifest_path).read_text())
    if plan.get('campaign_schema') in {'development-endpoint-comparison/v1', 'development-endpoint-comparison/v2', 'development-endpoint-comparison/v3'}:
        if digest(ROOT / plan['d1_evidence']['synthesis_path']) != plan['d1_evidence']['synthesis_sha256']:
            raise ValueError('D2 DEVELOPMENT evidence hash mismatch')
        entry = next(e for e in plan['entries'] if e['id'] == entry_id)
        if digest(ROOT / entry['config']) != entry['config_sha256']:
            raise ValueError('D2 configuration hash mismatch')
    elif plan.get('continuation_schema') in ('development-d1-continuation/v1', 'development-d1-continuation/v2'):
        parent = ROOT / plan['parent_manifest_path']
        if digest(parent) != plan['parent_manifest_sha256']:
            raise ValueError('Continuation parent manifest hash mismatch')
        if digest(ROOT / plan['diagnosis_path']) != plan['diagnosis_sha256']:
            raise ValueError('Continuation diagnosis hash mismatch')
        entry = next(e for e in plan['entries'] if e['id'] == entry_id)
        if digest(ROOT / entry['config']) != entry['config_sha256']:
            raise ValueError('Continuation configuration hash mismatch')
    else:
        validate_plan(manifest_path, check_outputs=False)
        entry = next(e for e in plan['entries'] if e['id'] == entry_id)
    if Path(destination).resolve() != (ROOT / entry['outputs']['analysis']).resolve():
        raise ValueError('Summary destination must match reserved entry analysis path')
    raw = ROOT / entry['outputs']['raw']
    config = ExperimentConfig.load(raw / 'effective_config.json')
    if json.loads(config.to_json()) != entry['effective_configuration']:
        raise ValueError('Observed effective config differs from plan')
    phases, cutoff, evidence = resolve_observation(raw, config)
    report = summarize(raw / 'request_log.csv', phases, as_of=cutoff)
    bin_phases = dict(schema_version=1, run_id=phases['run_id'], phases=[
        dict(name='WARMUP', start_seconds='0', end_seconds='30'),
        *[dict(name=f'MEASURE_{i+1}', start_seconds=str(30+i*30), end_seconds=str(60+i*30)) for i in range(4)]])
    if cutoff > 150:
        bin_phases['phases'].append(dict(name='DRAIN', start_seconds='150', end_seconds=str(cutoff)))
    bins = summarize(raw / 'request_log.csv', bin_phases, as_of=cutoff)
    # Per-source rates and late starts identify possible generator limitation,
    # without pretending benign journals contain admission timestamps (they do not).
    with (raw / 'request_log.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    per_source = []
    for worker in range(4):
        count = sum(int(r['worker_id']) == worker and Decimal(30) <= number(r['elapsed_seconds']) < Decimal(150) for r in rows)
        source_end = next(c['elapsed_seconds'] for c in evidence['closures'] if c['source_id'] == f'normal_{worker+1}')
        per_source.append(dict(worker_index=worker, measure_starts=count, expected_starts=120 * config.normal_traffic.rate,
                               achieved_over_nominal=ratio(count, 120 * config.normal_traffic.rate) if source_end >= 150 else None))
    evidence['per_source_useful_interval'] = per_source
    evidence['starts_at_or_after_nominal_end'] = sum(number(r['elapsed_seconds']) >= Decimal(150) for r in rows)
    evidence['useful_interval_fully_observed'] = cutoff >= Decimal(150)
    report['d1_evidence'] = evidence
    report['d1_30s_cohorts'] = [r for r in bins['rows'] if r['traffic_class'] == 'benign' and r['phase'].startswith('MEASURE_')]
    report['d1_entry_id'] = entry_id
    report['progression'] = 'MANUAL_REVIEW_REQUIRED; never an authorization to execute the next entry'
    destination = Path(destination)
    # No partial published report. Missing closure or inconsistency raises before mkdir.
    destination.mkdir(parents=True, exist_ok=False)
    for name, value in [('phases.json', phases), ('service_summary.json', report)]:
        with (destination / name).open('x') as stream:
            json.dump(value, stream, indent=2, default=json_default, allow_nan=False)
            stream.write('\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    check = sub.add_parser('validate-plan')
    check.add_argument('--manifest', type=Path, required=True)
    check.add_argument('--output', type=Path)
    summary = sub.add_parser('summarize')
    summary.add_argument('--manifest', type=Path, required=True)
    summary.add_argument('--entry', required=True)
    summary.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'validate-plan':
        result = validate_plan(args.manifest)
        if args.output:
            with args.output.open('x') as stream:
                json.dump(result, stream, indent=2)
                stream.write('\n')
        print(json.dumps(result))
    else:
        result = summarize_entry(args.manifest, args.entry, args.output)
        print(json.dumps(dict(entry=args.entry, reconciliation=result['reconciliation'],
            technical_status_complete=result['d1_evidence']['technical_status_complete'],
            progression=result['progression'])))


if __name__ == '__main__':
    main()
