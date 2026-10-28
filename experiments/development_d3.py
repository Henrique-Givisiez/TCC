"""D3 pilot authority and offline class/phase review. No Docker or execution imports."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

from experiments.development_d1 import collect_seeds, digest
from experiments.summarize_service import number, ratio, summarize, json_default, load_requests, quantile
from simulator.experiment_config import ExperimentConfig
from simulator.request_logger import REQUEST_FIELDS
from simulator.ground_truth import EVENT_FIELDS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / 'experiments/protocols/development_d3_pilots_20261028/manifest.json'
PHASES = [('WARMUP', 0, 30), ('PRE', 30, 150), ('ACTIVE', 150, 270), ('POST', 270, 390)]
RECOVERY = dict(bin_seconds=30, consecutive_bins=2, minimum_starts=200,
                minimum_2xx=200, minimum_success_fraction=0.99,
                success_fraction_tolerance=0.01, minimum_throughput_ratio=0.90,
                maximum_p95_ratio=1.25, maximum_open=0)


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, default=json_default, allow_nan=False)
        stream.write('\n')


def seed_inputs(root=ROOT):
    """Audit seed-bearing JSON, including manifests, D1 and historical partitions.

    A new seed-bearing file invalidates the inventory until explicitly reviewed.
    D3's own reservations/configs/results are excluded and checked separately.
    """
    result = []
    for folder in ('experiments/configs', 'experiments/protocols', 'docs/stage14a/materialized', 'experiment_results'):
        for path in (root / folder).rglob('*.json'):
            if any('development_d3' in part or 'development-d3' in part for part in path.parts):
                continue
            if path.stat().st_size == 0 or collect_seeds(read(path)):
                result.append(path)
    effective = root / 'effective_config.json'
    if effective.exists():
        result.append(effective)
    return sorted(set(result))


def validate_plan(manifest_path=DEFAULT_MANIFEST, *, check_outputs=True):
    p = read(manifest_path)
    if (p['campaign_schema'] != 'development-d3-pilots/v1' or p['partition'] != 'DEVELOPMENT'
            or p['automatic_progression'] is not False or p['maximum_attempts'] != 3
            or p['recovery_rule'] != RECOVERY or p['phases'] != [list(x) for x in PHASES]):
        raise ValueError('D3 pilot authority/phase/recovery contract changed')
    expected_control = dict(aggregate_start_ratio=[.8,1.2],per_source_start_ratio=[.65,1.35],success_fraction_min=.99,
        failure_fraction_max=.01,incomplete_max=0,other_responses_max=0,terminal_2xx_rps_min=12.8,
        minimum_2xx_support_per_phase=200,p95_limit_ms=250,
        within_phase_trend='Boundary bins n>=50; stop if terminal 2xx falls >=20% AND p95 doubles; support absent blocks control')
    if (p['control_criteria'] != expected_control or p['retries'] != 0 or p['scientific_calibration_or_test'] is not False
            or p['drain_budget_seconds'] != 30 or p['minimum_idle_after_cleanup_seconds'] != 60):
        raise ValueError('Control or pilot progression limits changed')
    for item in p['evidence']:
        if digest(ROOT / item['path']) != item['sha256']:
            raise ValueError('Evidence changed: ' + item['path'])
    for name, value in p['runtime_source_hashes'].items():
        if digest(ROOT / name) != value:
            raise ValueError('Bound source changed: ' + name)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.run(['git', 'merge-base', '--is-ancestor', p['instrumentation_commit'], head], cwd=ROOT).returncode:
        raise ValueError('Checkout is outside the recorded code lineage')
    audit = read(ROOT / p['seed_audit_path'])
    if digest(ROOT / p['seed_audit_path']) != p['seed_audit_sha256']:
        raise ValueError('Seed audit changed')
    if {x['path'] for x in audit['sources']} != {str(x.relative_to(ROOT)) for x in seed_inputs()}:
        raise ValueError('Seed-bearing historical inventory changed')
    used = set()
    for source in audit['sources']:
        path = ROOT / source['path']
        if digest(path) != source['sha256'] or sorted(collect_seeds(read(path) if path.stat().st_size else {})) != source['seeds']:
            raise ValueError('Seed history changed: ' + source['path'])
        used.update(source['seeds'])
    reservations = p['seed_reservations']
    if set(reservations) != {'PILOT_C', 'PILOT_E4', 'PILOT_E8', 'MATRIX_A', 'MATRIX_B'}:
        raise ValueError('Pilot/matrix seed reservations differ')
    seeds = []
    for label, item in reservations.items():
        value = int.from_bytes(hashlib.sha256(f"{item['namespace']}:{label}:{item['index']}".encode()).digest()[:8], 'big')
        if value != item['seed'] or value in used or value in seeds:
            raise ValueError('Seed derivation/collision: ' + label)
        seeds.append(value)
    paths = set()
    if [e['id'] for e in p['entries']] != ['d3_pilot_C', 'd3_pilot_E4', 'd3_pilot_E8']:
        raise ValueError('Only C/E4/E8 pilot configurations are permitted')
    config_directory = (ROOT / p['entries'][0]['config']).parent
    if {str(x.relative_to(ROOT)) for x in config_directory.glob('*.json')} != {e['config'] for e in p['entries']}:
        raise ValueError('Unexpected configuration in pilot directory')
    template = read(ROOT / p['configuration_template']['path'])
    if digest(ROOT / p['configuration_template']['path']) != p['configuration_template']['sha256']:
        raise ValueError('Configuration template changed')
    for index, (e, rate) in enumerate(zip(p['entries'], (0, 4, 8))):
        cfg = ExperimentConfig.load(ROOT / e['config'])
        expected = json.loads(json.dumps(template))
        expected.update(id=e['id'], seed=reservations['PILOT_' + e['condition']]['seed'], duration_seconds=390)
        expected['normal_traffic'].update(rate=4, clients=4, endpoint='/medium')
        expected['attack'].update(enabled=bool(rate), attackers=1 if rate else 0, rate=rate,
                                  endpoint='/expensive', start_seconds=150, duration_seconds=120)
        if (read(ROOT / e['config']) != json.loads(cfg.to_json()) or json.loads(cfg.to_json()) != expected
                or e['effective_configuration'] != expected or digest(ROOT / e['config']) != e['config_sha256']
                or e['requires_review_of'] != (p['entries'][index-1]['id'] if index else None)):
            raise ValueError('Incomplete/mismatched pilot config or dependency: ' + e['id'])
        for path in e['outputs'].values():
            resolved = (ROOT / path).resolve()
            if not resolved.is_relative_to((ROOT / p['results_root']).resolve()) or path in paths:
                raise ValueError('Output outside pilot reservation or duplicate')
            paths.add(path)
            if check_outputs and resolved.exists():
                raise FileExistsError(path)
    return dict(manifest_sha256=digest(manifest_path), configurations=3, pilot_seeds=seeds[:3],
                matrix_seeds_reserved_only=seeds[3:], historical_seed_files=len(audit['sources']),
                collisions=[], source_checkout=dict(effective_checkout_commit=head, source_tree_unchanged=True),
                docker_accessed=False, experiments_executed=False)


def csv_rows(path, fields=None):
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('Missing/duplicate CSV header: ' + str(path))
        if fields and not set(fields).issubset(reader.fieldnames):
            raise ValueError('CSV columns missing: ' + str(path))
        rows = list(reader)
        if any(None in r or any(v is None for v in r.values()) for r in rows):
            raise ValueError('Malformed CSV: ' + str(path))
        return rows


NUMERIC = {'worker_id', 'timestamp', 'elapsed_seconds', 'end_timestamp', 'end_elapsed_seconds', 'duration_ms', 'http_status'}
START_FIELDS = ['run_id', 'request_id', 'generator', 'worker_id', 'target_url', 'timestamp', 'elapsed_seconds', 'traffic_class', 'attack_id', 'event_id']
END_FIELDS = START_FIELDS + ['end_timestamp', 'end_elapsed_seconds', 'duration_ms', 'http_status', 'outcome', 'error_type']


def equal(field, a, b):
    if a in ('', None) or b in ('', None):
        return a in ('', None) and b in ('', None)
    return number(a) == number(b) if field in NUMERIC else str(a) == str(b)


def reconcile(raw, config):
    """Missing rows/finishes are not silently converted to open requests.

    Worker indices are scoped by generator (normal_1 and attack_1 both use 0).
    Global attack context is recomputed by aggregation; local context is not
    compared to it. All other scientific fields are reconciled independently.
    """
    raw = Path(raw)
    status, inventory = read(raw / 'run_status.json'), read(raw / 'source_inventory.json')
    run = status['run_id']
    expected = {f'normal_{i+1}': ('normal', 'benign', i) for i in range(4)}
    if config.attack.enabled:
        expected['attack_1'] = ('attack', 'attack', 0)
    if len(inventory) != len(expected) or {s['source_id'] for s in inventory} != set(expected):
        raise ValueError('Expected all four benign sources and, for attacks, attack_1')
    requests = load_requests(raw / 'request_log.csv', run)
    rows = {r['request_id']: r for r in csv_rows(raw / 'request_log.csv', REQUEST_FIELDS)}
    begins, finishes, local, origins, closures, admissions = {}, {}, {}, {}, [], []
    controlled = True
    for source in inventory:
        sid = source['source_id']
        generator, cls, worker = expected[sid]
        if (source['run_id'] != run or source['source_type'] != generator
                or source['traffic_class'] != cls or source['worker_index'] != worker):
            raise ValueError('Inventory class/run/source identity mismatch')
        output = raw / 'source_artifacts' / sid / 'output'
        lines = (output / 'journal.jsonl').read_text().splitlines(keepends=True)
        if not lines or any(not x.endswith('\n') for x in lines):
            raise ValueError('Missing/truncated journal: ' + sid)
        items = [json.loads(x) for x in lines]
        if any(x['sequence'] != i or x['source_id'] != sid or x['run_id'] != run for i, x in enumerate(items, 1)):
            raise ValueError('Journal sequence/run/source mismatch')
        closed = [x['payload'] for x in items if x['kind'] == 'source_closed']
        if len(closed) != 1 or items[-1]['kind'] != 'source_closed':
            raise ValueError('Missing/duplicate/nonfinal source_closed: ' + sid)
        closure = closed[0]
        final, state = read(output / 'final_status.json'), source['status_final']
        if any(final.get(k) != state.get(k) for k in ('source_id', 'run_id', 'drained', 'logger_complete')):
            raise ValueError('Final status disagrees with source inventory')
        if final.get('source_id') != sid or final.get('run_id') != run:
            raise ValueError('Final status identity mismatch')
        if any(closure.get(k) != final.get(k) for k in ('drained', 'logger_complete')):
            raise ValueError('Closure disagrees with final status')
        # logger_complete=False also occurs for persisted incomplete attempts;
        # row/journal reconciliation below decides whether records were lost.
        controlled &= bool(closure['drained'] and closure['logger_complete'] and not state['forced'] and state['exit_code'] == 0)
        end = number(closure['elapsed_seconds'])
        nominal_close = 270 if generator == 'attack' else 390
        if end <= 0:
            raise ValueError('Invalid observed source closure')
        within_budget = nominal_close <= end <= nominal_close + 30
        controlled &= within_budget
        closures.append(dict(source_id=sid, within_reserved_lifecycle=within_budget, **closure))
        own = []
        for item in items:
            kind, payload = item['kind'], item['payload']
            if kind not in ('request_begin', 'request_finish'):
                continue
            rid = payload['request_id']
            table = begins if kind == 'request_begin' else finishes
            if (rid in table or not rid.startswith('request_' + sid + '_') or payload['run_id'] != run
                    or payload['worker_id'] != worker or payload['generator'] != generator or payload['traffic_class'] != cls):
                raise ValueError('Duplicate or mismatched journal request origin')
            if number(payload['elapsed_seconds']) >= end or (kind == 'request_finish' and number(payload['end_elapsed_seconds']) > end):
                raise ValueError('Request after its source closure')
            if kind == 'request_begin':
                origins[rid] = sid
                own.append(payload)
            table[rid] = payload
        local_rows = csv_rows(output / 'local_requests.csv', REQUEST_FIELDS)
        # Validate incomplete and terminal contracts locally as well.
        load_requests(output / 'local_requests.csv', run)
        if {r['request_id'] for r in local_rows} != {r['request_id'] for r in own} or len(local_rows) != len(own):
            raise ValueError('Local CSV lost/duplicated records: ' + sid)
        for row in local_rows:
            if row['request_id'] in local:
                raise ValueError('Duplicate local request')
            local[row['request_id']] = row
        if generator == 'attack':
            admitted = [x['payload'] for x in items if x['kind'] == 'admission']
            abandoned = [x['payload'] for x in items if x['kind'] == 'abandoned_admission']
            net_admissions = Counter(x['event_id'] for x in admitted)
            net_admissions.subtract(Counter(x['event_id'] for x in abandoned))
            if (net_admissions != Counter(r['event_id'] for r in own)
                    or any(number(x['elapsed_seconds']) < 150 for x in admitted)):
                raise ValueError('Attack admission/start correspondence mismatch')
            admissions.append(dict(source_id=sid, admitted=len(admitted), abandoned=len(abandoned), started=len(own)))
    if set(rows) != set(begins) or set(rows) != set(local) or set(finishes) - set(begins):
        raise ValueError('Missing/extra journal or aggregate CSV records')
    for rid, row in rows.items():
        if any(not equal(k, row[k], begins[rid].get(k)) for k in START_FIELDS):
            raise ValueError('Begin and aggregate CSV fields disagree: ' + rid)
        if any(not equal(k, row[k], local[rid].get(k)) for k in END_FIELDS):
            raise ValueError('Local and aggregate CSV fields disagree: ' + rid)
        if (row['outcome'] == 'incomplete') != (rid not in finishes):
            raise ValueError('Missing finish for terminal row or fabricated finish for incomplete')
        if rid in finishes and any(not equal(k, row[k], finishes[rid].get(k)) for k in END_FIELDS):
            raise ValueError('Finish and aggregate CSV fields disagree: ' + rid)
        endpoint = config.normal_traffic.endpoint if row['traffic_class'] == 'benign' else config.attack.endpoint
        if urlsplit(row['target_url']).path != endpoint:
            raise ValueError('Wrong observed endpoint')
    cutoff = max(number(c['elapsed_seconds']) for c in closures)
    return dict(run_id=run, cutoff=cutoff, closures=closures, controlled_closure=controlled,
                starts=len(rows), known_ends=len(finishes), open_without_end=len(rows)-len(finishes),
                records_lost=0, origins=origins, admissions=admissions), rows, requests


def validate_ground_truth(raw, config, rows, run):
    events = csv_rows(Path(raw) / 'attack_events.csv', EVENT_FIELDS)
    status = read(Path(raw) / 'run_status.json')
    if len(events) != int(config.attack.enabled):
        raise ValueError('Ground truth must contain zero/control or one/attack event')
    attack = [r for r in rows.values() if r['traffic_class'] == 'attack']
    intervals = []
    for e in events:
        if (e['run_id'] != run or e['experiment_id'] != config.id or e['profile'] != 'continuous'
                or e['event_id'] != 'event_001' or e['attack_id'] != 'attack_001'
                or number(e['scheduled_start_seconds']) != 150 or number(e['scheduled_end_seconds']) != 270):
            raise ValueError('Ground truth identity/profile/schedule mismatch')
        if (number(e['schema_version']) != 1 or number(e['experiment_start_timestamp']) != number(status['experiment_start_timestamp'])
                or number(e['experiment_start_monotonic']) != number(status['experiment_start_monotonic'])):
            raise ValueError('Ground truth anchors mismatch')
        local_events = csv_rows(Path(raw) / 'source_artifacts/attack_1/output/local_events.csv', EVENT_FIELDS)
        journal = [json.loads(x) for x in (Path(raw) / 'source_artifacts/attack_1/output/journal.jsonl').read_text().splitlines()]
        snapshots = [x['payload'] for x in journal if x['kind'] == 'event_snapshot']
        if len(local_events) != 1 or not snapshots:
            raise ValueError('Missing local event/snapshot evidence')
        if any(number(x['payload']['elapsed_seconds']) > number(e['stop_requested_seconds']) for x in journal if x['kind'] == 'admission'):
            raise ValueError('Offensive admission after certified stop')
        numeric_events = {'schema_version','experiment_start_timestamp','experiment_start_monotonic','scheduled_start_seconds','scheduled_end_seconds','activation_requested_seconds','actual_start_seconds','stop_requested_seconds','actual_end_seconds','last_request_start_seconds','drained_end_seconds'}
        for field in EVENT_FIELDS:
            for observed in (local_events[0], snapshots[-1]):
                a,b = e[field], observed.get(field)
                match = (a in ('',None) and b in ('',None)) if a in ('',None) or b in ('',None) else (number(a)==number(b) if field in numeric_events else str(a)==str(b))
                if not match:
                    raise ValueError('Local/global event snapshot mismatch: ' + field)
        if not attack:
            raise ValueError('Expected offensive event has no starts')
        start, end = number(e['actual_start_seconds']), number(e['actual_end_seconds'])
        if (start != min(number(r['elapsed_seconds']) for r in attack)
                or number(e['last_request_start_seconds']) != max(number(r['elapsed_seconds']) for r in attack)
                or not 150 <= number(e['activation_requested_seconds']) <= start
                or not 270 <= number(e['stop_requested_seconds']) <= end
                or not start < end <= 420 or any(not start <= number(r['elapsed_seconds']) < end for r in attack)):
            raise ValueError('Ground truth emission milestones disagree with requests')
        known = [number(r['end_elapsed_seconds']) for r in attack if r['end_elapsed_seconds']]
        if e['status'] == 'completed':
            if len(known) != len(attack) or number(e['drained_end_seconds']) != max(known):
                raise ValueError('Ground truth drain differs from last offensive completion')
        elif e['status'] != 'incomplete' or e['drained_end_seconds']:
            raise ValueError('Uncertified event drain/status')
        intervals.append((start, end, e['event_id']))
    for r in rows.values():
        t = number(r['elapsed_seconds'])
        ids = sorted(eid for start, end, eid in intervals if start <= t < end)
        if r['attack_active'] != str(int(bool(ids))) or json.loads(r['active_event_ids']) != ids:
            raise ValueError('Global attack context mismatch')
        if r['traffic_class'] == 'attack':
            if r['attack_id'] != 'attack_001' or r['event_id'] != 'event_001':
                raise ValueError('Attack row lacks originating event')
        elif r['attack_id'] or r['event_id']:
            raise ValueError('Benign request incorrectly attributed to attack event')
    return dict(valid=True, events=events, actual_emission_intervals=intervals,
                starts_after_nominal_attack_end=sum(number(r['elapsed_seconds']) >= 270 for r in attack))


def phase_plan(run, cutoff, *, bins=False):
    phases = []
    for name, a, b in PHASES:
        if bins and name != 'WARMUP':
            phases.extend(dict(name=f'{name}_{i+1}', start_seconds=a+i*30, end_seconds=a+(i+1)*30) for i in range(4))
        else:
            phases.append(dict(name=name, start_seconds=a, end_seconds=b))
    if cutoff > 390:
        phases.append(dict(name='DRAIN', start_seconds=390, end_seconds=cutoff))
    return dict(schema_version=1, run_id=run, phases=phases)


def get_row(summary, phase, cls='benign'):
    return next(r for r in summary['rows'] if r['phase'] == phase and r['traffic_class'] == cls)


def supported(row, starts=200, successes=200):
    return (row['starts'] >= starts and row['duration_success_2xx_ms']['n'] >= successes
            and row['duration_success_2xx_ms']['p95'] is not None)


def recovery(summary, bins, control, ground_truth):
    """Exploratory post recovery; never substitutes cleanup or actual readiness."""
    result = dict(rule=RECOVERY, exploratory=True, status='not_evaluable', right_censored=False,
                  recovered_by_seconds=None, censor_at_seconds=None, bins=[])
    if control is None or not control['classification']['control_accepted']:
        result['reason'] = 'Accepted control reference unavailable'
        return result
    pre = get_row(summary, 'PRE')
    cpre = get_row(control['service'], 'PRE')
    if not supported(pre) or not supported(cpre):
        result['reason'] = 'PRE reference lacks duration/start support'
        return result
    emission_end = max((x[1] for x in ground_truth['actual_emission_intervals']), default=number(270))
    streak = 0
    for i in range(1, 5):
        row, crow = get_row(bins, f'POST_{i}'), get_row(control['bins'], f'POST_{i}')
        support = supported(row) and supported(crow) and row['exposure_seconds'] == 30 and number(crow['exposure_seconds']) == 30
        refs = (pre, cpre, crow)
        fraction = row['cohort_fractions']['success_2xx_per_started']
        throughput = row['rates_per_second']['success_2xx_ends']
        p95 = row['duration_success_2xx_ms']['p95']
        passed = support and row['start_seconds'] >= emission_end and row['cohort_open_as_of'] == 0
        if passed:
            passed = (fraction >= number('.99') and all(
                fraction >= number(r['cohort_fractions']['success_2xx_per_started']) - number('.01')
                and throughput >= number(r['rates_per_second']['success_2xx_ends']) * number('.90')
                and p95 <= number(r['duration_success_2xx_ms']['p95']) * number('1.25') for r in refs))
        result['bins'].append(dict(phase=row['phase'], support=bool(support), passed=bool(passed)))
        streak = streak + 1 if passed else 0
        if streak >= 2 and result['recovered_by_seconds'] is None:
            result['recovered_by_seconds'] = row['end_seconds']
    result['qualified_at_end'] = streak >= 2
    result['relapse_after_first_recovery'] = result['recovered_by_seconds'] is not None and not all(x['passed'] for x in result['bins'] if number(x['phase'].split('_')[1])*30+270 > result['recovered_by_seconds'])
    observed = result['recovered_by_seconds'] is not None
    result.update(status='observed' if observed else 'not_observed', right_censored=not observed,
                  censor_at_seconds=None if observed else min(number(390), number(summary['as_of_seconds'])),
                  reason='First two consecutive supported qualifying POST bins; later bins retained for relapse review')
    return result


def collection_checks(raw, run):
    raw = Path(raw)
    results = []
    def add(name, passed, evidence):
        results.append(dict(name=name, passed=bool(passed), evidence=evidence))
    status = read(raw / 'run_status.json')
    for name, artifact, stderr in (
        ('csv', raw / 'traffic_capture.csv', raw / 'traffic_capture.stderr'),
        ('pcap', raw / 'source_artifacts/traffic_capture.pcap', raw / 'source_artifacts/traffic_capture.pcap.stderr')):
        report = read(str(artifact) + '.capture.json')
        counters = report['capture_counters']
        add('capture_' + name, artifact.is_file() and report['accepted'] and report['returncode'] in (0, -15)
            and counters['statistics_complete'] and counters['packets_dropped_by_kernel'] == 0
            and all(counters['statistics_occurrences'].get(k) == 1 for k in ('packets_captured', 'packets_received_by_filter', 'packets_dropped_by_kernel'))
            and report['capture_diagnostic_sha256'] == digest(stderr)
            and status.get('capture_results', {}).get(name) == report, report)
    metrics = csv_rows(raw / 'simulation_metrics.csv')
    samples = [json.loads(x) for x in (raw / 'proxy_artifacts/monitor_samples.jsonl').read_text().splitlines()]
    monitor = read(raw / 'proxy_artifacts/monitor_summary.json')
    add('proxy_identity_shutdown', bool(samples) and monitor['run_id'] == run and not monitor.get('thread_alive', True)
        and not monitor.get('fatal_error') and len({s['container_id'] for s in samples}) == 1
        and all(s['run_id'] == run and s['container_id'] == monitor['container_id'] for s in samples), monitor)
    for phase, a, b in PHASES[1:]:
        times = [number(r['elapsed_seconds']) for r in metrics if a <= number(r['elapsed_seconds']) < b
                 and r['active_containers_names'].strip() and r['run_id'] == run
                 and int(r['num_instances']) == 1 and r['decision'] == 'NO_ACTION'
                 and number(r['average_cpu_percent']) >= 0 and number(r['mem_usage']) >= 0]
        observations = [('victim', times)]
        for source in ('status', 'docker'):
            observations.append(('proxy_' + source, [number(s[source]['elapsed_seconds']) for s in samples
                if a <= number(s[source]['elapsed_seconds']) < b and s[source]['success'] and s[source]['data'] is not None]))
        for name, times in observations:
            ordered = sorted(times)
            gap = max(y-x for x, y in zip([number(a)] + ordered, ordered + [number(b)]))
            slots = len({int(t)-a for t in times})
            add(f'{name}_{phase}', slots >= 108 and gap <= 5, dict(slots=slots, expected=120, max_gap=gap))
    return results


def resource_summary(raw):
    metrics = csv_rows(Path(raw) / 'simulation_metrics.csv')
    samples = [json.loads(line) for line in (Path(raw) / 'proxy_artifacts/monitor_samples.jsonl').read_text().splitlines()]
    def stats(values):
        values = [number(v) for v in values if v is not None and v != '']
        return dict(n=len(values), mean=ratio(sum(values),len(values)), p50=quantile(values,'.5'), p95=quantile(values,'.95'))
    result = {}
    for phase,a,b in PHASES:
        ticks = [r for r in metrics if a <= number(r['elapsed_seconds']) < b and r['active_containers_names'].strip()]
        docker = [s['docker']['data'] for s in samples if a <= number(s['docker']['elapsed_seconds']) < b and s['docker']['success'] and s['docker']['data']]
        status = [s['status']['data'] for s in samples if a <= number(s['status']['elapsed_seconds']) < b and s['status']['success'] and s['status']['data']]
        result[phase] = dict(victim_cpu_docker_percent=stats(r['average_cpu_percent'] for r in ticks),
            victim_memory_application_mib=stats(r['mem_usage'] for r in ticks),
            proxy_cpu_docker_percent=stats(r.get('cpu_percent') for r in docker),
            proxy_memory_raw_bytes=stats(r.get('memory_usage_bytes') for r in docker),
            proxy_connections={k:stats(r.get(k) for r in status) for k in ('active_connections','reading_connections','writing_connections','waiting_connections')})
    return dict(phases=result,limitations=['Victim tick support does not certify fresh Docker reads.',
        'CPU 100% is one logical core equivalent, not reserved utilization.',
        'Victim application MiB and proxy raw bytes have different accounting conventions.',
        'In-flight requests and NGINX connections are not measured server queue length.'])


def build_review(raw, config, *, control=None):
    """Shared real/synthetic processing path; collection errors produce a review."""
    result = dict(schema_version=1, entry_id=config.id, configuration=json.loads(config.to_json()),
                  technical_checks=[], service=None, bins=None, recovery=None)
    checks = result['technical_checks']
    def add(name, passed, evidence):
        checks.append(dict(name=name, passed=bool(passed), evidence=evidence))
    try:
        lifecycle, rows, requests = reconcile(raw, config)
        result['lifecycle'] = lifecycle
        add('journal_csv_all_origins', True, {k:v for k,v in lifecycle.items() if k != 'origins'})
        gt = validate_ground_truth(raw, config, rows, lifecycle['run_id'])
        result['ground_truth'] = gt
        add('ground_truth', True, gt)
        cutoff = lifecycle['cutoff']
        result['service'] = summarize(Path(raw) / 'request_log.csv', phase_plan(lifecycle['run_id'], cutoff), as_of=cutoff)
        result['bins'] = summarize(Path(raw) / 'request_log.csv', phase_plan(lifecycle['run_id'], cutoff, bins=True), as_of=cutoff)
        for report in (result['service'], result['bins']):
            for row in report['rows']:
                a,b = row['start_seconds'], min(row['end_seconds'],cutoff)
                own = [r for r in requests if r['traffic_class'] == row['traffic_class']]
                area = sum(max(number(0), min(b,r['end'] if r['end'] is not None else cutoff)-max(a,r['start'])) for r in own)
                row['mean_inflight_client_requests'] = ratio(area,b-a) if b>a else None
                row['open_at_phase_boundary'] = sum(r['start'] < b and (r['end'] is None or r['end'] > b) for r in own)
        run_status = read(Path(raw) / 'run_status.json')
        consistent = not (run_status.get('producers_drained') is True and lifecycle['open_without_end'] > 0)
        add('run_lifecycle_claims_consistent', consistent, dict(status=run_status.get('status'), errors=run_status.get('errors',[])))
        result['generator_checks'] = []
        for cls, source_type, rate, count, phases in (
                ('benign', 'normal', config.normal_traffic.rate, 4, ('PRE','ACTIVE','POST')),
                ('attack', 'attack', config.attack.rate, 1, ('ACTIVE',) if config.attack.enabled else ())):
            for phase in phases:
                r = get_row(result['service'], phase, cls)
                a, b = number(r['start_seconds']), number(r['end_seconds'])
                adherence = ratio(r['starts'], (b-a)*rate*count)
                per_source = []
                for i in range(count):
                    sid = f'{source_type}_{i+1}'
                    n = sum(lifecycle['origins'][rid] == sid and a <= number(row['elapsed_seconds']) < b for rid,row in rows.items())
                    per_source.append(dict(source_id=sid, starts=n, adherence=ratio(n, (b-a)*rate)))
                result['generator_checks'].append(dict(traffic_class=cls, phase=phase, adherence=adherence, per_source=per_source,
                    passed=number('.8') <= adherence <= number('1.2') and all(number('.65') <= x['adherence'] <= number('1.35') for x in per_source)))
        late = sum(number(r['elapsed_seconds']) >= (270 if r['traffic_class'] == 'attack' else 390) for r in rows.values())
        result['generator_checks'].append(dict(name='late_starts', count=late, limit=max(4,len(rows)*.01), passed=late <= max(4,len(rows)*.01)))
        checks.extend(collection_checks(raw, lifecycle['run_id']))
        result['resources'] = resource_summary(raw)
        if config.attack.enabled:
            result['recovery'] = recovery(result['service'], result['bins'], control, gt)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        add('processing_or_collection_failure', False, str(exc))
    technical = all(x['passed'] for x in checks) and result['service'] is not None
    generator = bool(result.get('generator_checks')) and all(x['passed'] for x in result['generator_checks'])
    service_checks = []
    if result['service']:
        for phase in ('PRE', 'ACTIVE', 'POST'):
            r = get_row(result['service'], phase)
            p95 = r['duration_success_2xx_ms']['p95']
            ok = (supported(r) and r['cohort_fractions']['success_2xx_per_started'] >= number('.99')
                  and r['cohort_fractions']['failures_per_started'] <= number('.01')
                  and r['cohort_open_as_of'] == 0 and r['cohort_outcomes']['other_response'] == 0
                  and r['rates_per_second']['success_2xx_ends'] >= number('12.8') and p95 <= 250)
            first, last = get_row(result['bins'], phase+'_1'), get_row(result['bins'], phase+'_4')
            trend_support = supported(first,50,50) and supported(last,50,50)
            trend = (trend_support and last['rates_per_second']['success_2xx_ends'] <= first['rates_per_second']['success_2xx_ends']*number('.8')
                     and last['duration_success_2xx_ms']['p95'] >= first['duration_success_2xx_ms']['p95']*2)
            service_checks.append(dict(phase=phase, benign_criteria_pass=bool(ok and trend_support and not trend), trend_support=trend_support, adverse_trend=bool(trend)))
    relative = []
    if result['service'] and config.attack.enabled and control is not None:
        pre = get_row(result['service'], 'PRE')
        for phase in ('ACTIVE', 'POST'):
            r, cr = get_row(result['service'], phase), get_row(control['service'], phase)
            references = (pre, cr)
            reference_support = supported(pre) and supported(cr)
            enough = reference_support and supported(r)
            degraded = (any(r['cohort_fractions']['success_2xx_per_started'] < number(ref['cohort_fractions']['success_2xx_per_started'])-number('.01')
                        or r['rates_per_second']['success_2xx_ends'] < number(ref['rates_per_second']['success_2xx_ends'])*number('.9') for ref in references)
                        if r['starts'] and reference_support else not bool(r['starts']))
            if enough:
                degraded |= any(r['duration_success_2xx_ms']['p95'] > number(ref['duration_success_2xx_ms']['p95'])*number('1.25') for ref in references)
            relative.append(dict(phase=phase, reference_support=reference_support, duration_support=enough, degradation_signal=bool(degraded)))
    result['relative_service_outcomes'] = relative
    benign_pass = bool(service_checks) and all(x['benign_criteria_pass'] for x in service_checks)
    result['service_checks'] = service_checks
    controlled = result.get('lifecycle', {}).get('controlled_closure', False)
    control_status = read(Path(raw) / 'run_status.json') if result['service'] else {}
    control_complete = control_status.get('status') == 'completed' and control_status.get('producers_drained') is True and not control_status.get('errors')
    control_accepted = not config.attack.enabled and technical and generator and benign_pass and controlled and control_complete
    result['classification'] = dict(technical_integrity=technical, generator_adherence=generator,
        service_degradation_observed=(bool(service_checks) and not benign_pass) or any(x['degradation_signal'] for x in relative),
        service_criteria_role='descriptive_outcome_only' if config.attack.enabled else 'control_acceptance_gate',
        controlled_closure=controlled, control_accepted=control_accepted,
        valid_service_observation=technical, generator_issue_requires_diagnosis=not generator)
    if not technical and result['recovery']:
        result['recovery'].update(status='unassessable_collection', right_censored=False, recovered_by_seconds=None)
    recovered = bool(result['recovery'] and result['recovery']['status'] == 'observed' and result['recovery'].get('qualified_at_end', False))
    result['progression'] = dict(automatic=False, eligible_for_manual_gate=technical and generator and controlled
        and (recovered if config.attack.enabled else control_accepted),
        requires=['entry-specific authorization', 'review of this report', 'cleanup verified', 'idle >=60s', 'fresh readiness preflight'],
        no_retry=True)
    return result


def operation_checks(plan, entry, manifest):
    """Require explicit preflight binding, effective sources and cleanup evidence."""
    ops = ROOT / plan['results_root'] / 'operations' / entry['id']
    attempt = read(ops / 'attempt.json')
    path = (ROOT / attempt['preflight_path']).resolve()
    if not path.is_relative_to(ops.resolve()):
        raise ValueError('Bound preflight escapes pilot operations path')
    preflight = read(path)
    if (attempt['authorization_scope'] != entry['id'] or attempt['manifest_sha256'] != digest(manifest)
            or digest(path) != attempt['preflight_sha256'] or preflight['manifest_sha256'] != digest(manifest)
            or preflight['approved_entry'] != entry['id'] or not preflight['ready']
            or preflight['preflight_id'] != attempt['preflight_id']
            or attempt['approved_source_hashes'] != preflight['checks']['operational_code_sha256']):
        raise ValueError('Attempt/preflight authority or source binding mismatch')
    if any(attempt['approved_source_hashes'].get(k) != v for k,v in plan['runtime_source_hashes'].items()):
        raise ValueError('Preflight source set does not cover manifest authority')
    for source, expected in attempt['approved_source_hashes'].items():
        if digest(ROOT / source) != expected:
            raise ValueError('Source changed after preflight: ' + source)
    execution, cleanup = read(ops / 'execution_result.json'), read(ops / 'cleanup_observation.json')
    before = {x['id']:x['status'] for x in preflight['checks']['containers_before']}
    after = {x['id']:x['status'] for x in cleanup['containers']}
    cleanup_ok = (before == after and cleanup['no_active_containers'] and cleanup['no_scientific_processes']
                  and cleanup['port_check_returncode'] == 0 and len(cleanup['port_8080'].strip().splitlines()) == 1)
    # A nonzero run exit is recorded separately: it may reflect actual service
    # drain failure, so it is not itself proof of missing records.
    return dict(bound_preflight_path=attempt['preflight_path'], bound_preflight_sha256=attempt['preflight_sha256'],
                execution=execution, cleanup=cleanup, cleanup_verified=cleanup_ok)


def process_entry(manifest, entry_id):
    validate_plan(manifest, check_outputs=False)
    plan = read(manifest)
    e = next(e for e in plan['entries'] if e['id'] == entry_id)
    if any((ROOT / e['outputs'][key]).exists() for key in ('validation','analysis','review')):
        raise FileExistsError('Pilot review outputs already exist; no overwrite/retry')
    config = ExperimentConfig.load(ROOT / e['config'])
    control = None
    if config.attack.enabled:
        c = plan['entries'][0]
        control = read(ROOT / c['outputs']['review'])
        if control['authority']['manifest_sha256'] != digest(manifest) or control['entry_id'] != c['id']:
            raise ValueError('Control review authority mismatch')
    raw = ROOT / e['outputs']['raw']
    before = {str(p):digest(p) for p in raw.rglob('*') if p.is_file()}
    report = build_review(raw, config, control=control)
    report['authority'] = dict(manifest_sha256=digest(manifest), config_sha256=e['config_sha256'])
    try:
        operations = operation_checks(plan, e, manifest)
        report['operations'] = operations
        report['timing'] = dict(cleanup_observation=dict(epoch=operations['cleanup']['observed_epoch']))
        report['classification']['execution_exit_zero'] = operations['execution']['returncode'] == 0
        if operations['execution']['returncode'] != 0:
            report['classification']['control_accepted'] = False
            report['progression']['eligible_for_manual_gate'] = False
        report['technical_checks'].append(dict(name='bound_operations_and_cleanup', passed=operations['cleanup_verified'], evidence=operations))
    except (ValueError, KeyError, OSError) as exc:
        report['technical_checks'].append(dict(name='bound_operations_and_cleanup', passed=False, evidence=str(exc)))
    if not all(x['passed'] for x in report['technical_checks']):
        report['classification'].update(technical_integrity=False, valid_service_observation=False, control_accepted=False)
        report['progression']['eligible_for_manual_gate'] = False
    try:
        effective_matches = read(raw / 'effective_config.json') == e['effective_configuration']
    except (OSError, ValueError):
        effective_matches = False
    if not effective_matches:
        report['technical_checks'].append(dict(name='effective_configuration', passed=False, evidence='Config mismatch'))
        report['classification']['technical_integrity'] = False
        report['classification']['valid_service_observation'] = False
        report['classification']['control_accepted'] = False
        report['progression']['eligible_for_manual_gate'] = False
    # Dataset validator retains its structural/eligibility distinctions. An
    # incomplete service run need not be analysis_eligible to preserve evidence.
    from experiments.validate_dataset import validate_dataset
    validation = validate_dataset(ROOT / e['outputs']['dataset'])
    write_new(ROOT / e['outputs']['validation'], validation)
    report['dataset_validation'] = {k:validation[k] for k in ('dataset_valid','analysis_eligible','structural_valid','summary')}
    from experiments.export_dataset import placement
    dataset = ROOT / e['outputs']['dataset']
    mismatches = []
    for path, expected in before.items():
        relative = Path(path).relative_to(raw)
        target = dataset / placement(relative)[0]
        if not target.is_file() or digest(target) != expected:
            mismatches.append(str(relative))
    report['technical_checks'].append(dict(name='raw_dataset_byte_correspondence', passed=not mismatches, evidence=mismatches))
    if not validation['dataset_valid'] or mismatches:
        report['classification'].update(technical_integrity=False, valid_service_observation=False, control_accepted=False)
        report['progression']['eligible_for_manual_gate'] = False
    if not validation['analysis_eligible']:
        report['progression']['eligible_for_manual_gate'] = False
        report['classification']['control_accepted'] = False
    report['preserved_raw_hashes'] = before
    if before != {str(p):digest(p) for p in raw.rglob('*') if p.is_file()}:
        raise ValueError('Raw evidence changed during processing')
    if not report['classification']['technical_integrity'] and report['recovery']:
        report['recovery'].update(status='unassessable_collection', right_censored=False, recovered_by_seconds=None)
    write_new(ROOT / e['outputs']['analysis'], dict(service=report['service'], bins=report['bins'], lifecycle=report.get('lifecycle'), ground_truth=report.get('ground_truth')))
    write_new(ROOT / e['outputs']['review'], report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('validate-plan')
    proc = sub.add_parser('review')
    proc.add_argument('--entry', choices=('d3_pilot_C','d3_pilot_E4','d3_pilot_E8'), required=True)
    args = parser.parse_args()
    result = validate_plan(args.manifest) if args.action == 'validate-plan' else process_entry(args.manifest, args.entry)
    print(json.dumps(result, default=json_default, allow_nan=False))


if __name__ == '__main__':
    main()
