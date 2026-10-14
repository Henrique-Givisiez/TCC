"""Short temporal trials using existing request/admission/network evidence only."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import uuid

from experiments.validate_single_victim import ARTIFACTS
from experiments.validate_source_containers import rows
from experiments.source_network_audit import TUPLE
from simulator import config, main_orchestrator
from simulator.attack_patterns import attack_pattern, PeriodicBurst
from simulator.app.simple_server import OPERATION_WORK_UNITS
from simulator.experiment_config import ExperimentConfig
from simulator.source_aggregate import records
from simulator.source_manager import worker_quotas

ROOT = Path(__file__).resolve().parents[1]


def validate(directory, experiment, case):
    def read_json(path):
        return json.loads((directory/path).read_text())
    inventory = read_json('source_inventory.json')
    status = read_json('run_status.json')
    requests, packets, metrics, events = [rows(directory/name) for name in
        ('request_log.csv', 'traffic_capture.csv', 'simulation_metrics.csv', 'attack_events.csv')]
    backend = read_json('proxy_artifacts/backend_inventory.json')
    isolation = read_json('source_artifacts/network_audit/isolation.json')
    comparison = read_json('source_artifacts/network_audit/comparison.json')
    assert read_json('source_artifacts/clock_validation.json')['comparable']
    assert read_json('source_artifacts/aggregation_audit.json')['complete']
    assert status['status'] == 'completed' and status['producers_drained'] and not status['errors']
    assert len(backend) == 1 and not backend[0]['port_bindings']
    assert requests and packets and metrics and len(events) == 1
    assert all(r['num_instances'] == '1' and r['decision'] == 'NO_ACTION' for r in metrics)
    assert all(r['run_id'] == status['run_id'] for r in requests+packets+metrics+events)
    ips = {e['ip'] for e in inventory}
    assert len(ips) == len(inventory)
    assert all(e['network'] == 'edos_sources' and e['service_endpoint'] == config.SOURCE_SERVICE_ENDPOINT
               and e['status_final']['drained'] and not e['status_final']['forced'] for e in inventory)
    assert all('CONNECTED' not in p['probes'].values() and p['networks'] == ['edos_sources'] for p in isolation['probes'])
    proxy_ip = comparison['proxy_ip']
    assert {r['src_ip'] for r in packets if r['dst_ip'] == proxy_ip} == ips
    assert all((r['src_ip'] in ips and r['dst_ip'] == proxy_ip and r['dst_port'] == '80') or
               (r['src_ip'] == proxy_ip and r['src_port'] == '80' and r['dst_ip'] in ips) for r in packets)
    assert all(r['traffic_class'] == 'unknown' for r in packets)
    decoded = subprocess.run(['tcpdump', '-nn', '-tt', '-S', '-r', str(directory/'source_artifacts/traffic_capture.pcap')],
                             check=True, capture_output=True, text=True).stdout.splitlines()
    descriptions = [line[TUPLE.search(line).start():] for line in decoded if TUPLE.search(line)]
    assert len(descriptions) == len(set(descriptions)), 'repeated raw packet descriptions'
    access = [json.loads(s) for s in (directory/'proxy_artifacts/proxy_access.log').read_text().splitlines()]
    access = [r for r in access if r['request_id']]
    assert len(access) == len({r['request_id'] for r in access}) == len(requests)
    by_access = {r['request_id']: r for r in access}
    evidence = {r['request_id']: r for r in map(json.loads,
        (directory/'proxy_artifacts/routing_evidence.jsonl').read_text().splitlines())}
    source_for_request = {}
    for component, settings, count in (('normal', experiment.normal_traffic, experiment.normal_traffic.clients),
                                       ('attack', experiment.attack, experiment.attack.attackers)):
        own = [e for e in inventory if e['source_type'] == component]
        assert len(own) == count
        assert [e['send_workers'] for e in own] == worker_quotas(settings.max_concurrent_sends, count)
        for entry in own:
            manifest = read_json('source_artifacts/'+entry['source_id']+'/manifest.json')
            assert manifest['settings']['rate'] == settings.rate
            encoded = json.dumps(manifest)
            assert backend[0]['ip'] not in encoded and backend[0]['name'] not in encoded
            for request in requests:
                if request['request_id'].startswith('request_'+entry['source_id']+'_'):
                    source_for_request[request['request_id']] = entry
    attack = [r for r in requests if r['generator'] == 'attack']
    assert attack
    for request in requests:
        settings = experiment.attack if request['generator'] == 'attack' else experiment.normal_traffic
        assert request['target_url'] == config.SOURCE_SERVICE_ENDPOINT + settings.endpoint
        assert request['http_status'] == '200' and request['outcome'] == 'response'
        assert request['traffic_class'] == ('attack' if request['generator'] == 'attack' else 'benign')
        assert bool(request['event_id']) == (request['generator'] == 'attack')
        logged = by_access[request['request_id']]
        assert logged['remote_addr'] == source_for_request[request['request_id']]['ip']
        assert logged['upstream'] == backend[0]['ip']+':80'
        assert logged['request'] == f'GET {settings.endpoint} HTTP/1.1'
        body = evidence[request['request_id']]['response_body']
        assert body.startswith('host='+backend[0]['hostname']+' ')
        assert f'work={OPERATION_WORK_UNITS[settings.endpoint]} sleep=0.0000s' in body
    event = events[0]
    starts = [float(r['elapsed_seconds']) for r in attack]
    assert event['profile'] == experiment.attack.profile and event['status'] == 'completed'
    assert float(event['actual_start_seconds']) == min(starts)
    assert float(event['actual_end_seconds']) > max(starts)
    assert float(event['drained_end_seconds']) == max(float(r['end_elapsed_seconds']) for r in attack)
    for row in requests+packets+metrics:
        active = float(event['actual_start_seconds']) <= float(row['elapsed_seconds']) < float(event['actual_end_seconds'])
        assert int(row['attack_active']) == int(active)
    pattern = attack_pattern(experiment.attack)
    assert all(pattern.allows(t) for t in starts), 'request beginning outside an active window'
    benign_silence = [r for r in requests if r['generator'] == 'normal' and
                     float(event['actual_start_seconds']) <= float(r['elapsed_seconds']) < float(event['actual_end_seconds'])
                     and not pattern.allows(float(r['elapsed_seconds']))]
    if isinstance(pattern, PeriodicBurst):
        assert benign_silence and all(r['attack_active'] == '1' for r in benign_silence)
    journal = records(directory/'source_artifacts', inventory)
    admissions = [r for r in journal if r['kind'] == 'admission']
    assert len(admissions) == len(attack)
    assert not any(r['kind'] == 'abandoned_admission' for r in journal)
    if isinstance(pattern, PeriodicBurst):
        assert sorted(r['payload']['elapsed_seconds'] for r in admissions) == sorted(starts)
    windows = []
    cursor = experiment.attack.start_seconds
    while (window := pattern.next_window(cursor)) is not None:
        start, end = window
        own = [r for r in attack if start <= float(r['elapsed_seconds']) < end]
        windows.append(dict(start=start, end=end, starts=[round(float(r['elapsed_seconds']), 6) for r in own],
                            count=len(own), completions_after_window=sum(float(r['end_elapsed_seconds']) >= end for r in own)))
        cursor = end
    active_duration = sum(w['end']-w['start'] for w in windows)
    expected = experiment.attack.rate * experiment.attack.attackers * active_duration
    # Wide stochastic checks detect multiplying/dividing the per-entity rate by
    # four. Capacity-limited trial intentionally has a lower realized rate.
    if case != 'capacity':
        assert .45*expected < len(attack) < 2*expected, (len(attack), expected)
        assert all(w['count'] > 0 for w in windows)
    per_source = {e['source_id']: sum(source_for_request[r['request_id']]['source_id'] == e['source_id'] for r in attack)
                  for e in inventory if e['source_type'] == 'attack'}
    if case == 'multiple':
        assert all(.4 * experiment.attack.rate * active_duration < n < 2 * experiment.attack.rate * active_duration
                   for n in per_source.values())
    carryover = sum(w['completions_after_window'] for w in windows)
    summary = dict(case=case, status=status['status'], profile=experiment.attack.profile,
                   rate_per_attacker=experiment.attack.rate, attackers=experiment.attack.attackers,
                   nominal_aggregate_active_rps=experiment.attack.rate*experiment.attack.attackers,
                   valid_active_window_seconds=active_duration, nominal_expected_opportunities=expected,
                   observed_opportunities=None, admissions=len(admissions), attack_starts=len(attack),
                   requests_total=len(requests), realized_active_rps=len(attack)/active_duration,
                   starts_per_source=per_source, windows=windows, starts_outside_windows=0,
                   completions_after_window=carryover,
                   completions_after_global_end=sum(float(r['end_elapsed_seconds']) >= experiment.attack.end_seconds for r in attack),
                   admission_start_same_sample=isinstance(pattern, PeriodicBurst),
                   benign_silence_observations=len(benign_silence),
                   packet_rows=len(packets), raw_packets=len(decoded), direct_routes_detected=0,
                   actual_start=float(event['actual_start_seconds']), actual_end=float(event['actual_end_seconds']),
                   drained_end=float(event['drained_end_seconds']))
    (directory/'validation.json').write_text(json.dumps(summary, indent=2)+'\n')
    lines = ['# Observed attack beginnings (seconds from experiment anchor)', '',
             '| Valid window | Starts | Beginnings | Completions after window |', '| --- | ---: | --- | ---: |']
    for w in windows:
        lines.append(f"| [{w['start']}, {w['end']}) | {w['count']} | "+
                     ', '.join(f'{t:.3f}' for t in w['starts'])+f" | {w['completions_after_window']} |")
    lines.extend(['', 'Silences have zero attack beginnings. Raw timestamps remain in request_log.csv.',
                  'Opportunity counts are not instrumented; admissions come from the existing journal.'])
    (directory/'timestamps.md').write_text('\n'.join(lines)+'\n')
    from simulator import docker_manager
    assert not docker_manager.client.containers.list(all=True, filters={'label': 'edos.role=source'})
    assert not docker_manager.client.containers.list(all=True, filters={'name': config.BASE_CONTAINER_NAME})
    assert not docker_manager.client.containers.list(all=True, filters={'name': status['proxy_integrity']['name']})
    return summary


def run_case(directory, case):
    directory.mkdir(parents=True, exist_ok=False)
    for setting, filename in ARTIFACTS.items():
        setattr(config, setting, str(directory/filename))
    config.PROXY_ARTIFACT_DIR = str(directory/'proxy_artifacts')
    config.SOURCE_ARTIFACT_DIR = str(directory/'source_artifacts')
    config.SOURCE_INVENTORY_FILE = str(directory/'source_inventory.json')
    config.BASE_CONTAINER_NAME = 'stage7_victim_'+uuid.uuid4().hex[:8]
    experiment = ExperimentConfig.load(ROOT/'experiments/configs/periodic_burst.json')
    if case == 'continuous':
        experiment = replace(experiment, attack=replace(experiment.attack, profile='continuous', burst=None, endpoint='/light'))
    elif case == 'multiple':
        experiment = replace(experiment, attack=replace(experiment.attack, attackers=4, endpoint='/light'))
    elif case == 'capacity':
        experiment = replace(experiment, attack=replace(experiment.attack, max_concurrent_sends=1))
    experiment = replace(experiment, id=experiment.id+'_'+case)
    main_orchestrator.main(experiment)
    summary = validate(directory, experiment, case)
    print('VALIDATION '+json.dumps(summary), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=['continuous', 'periodic', 'multiple', 'capacity'])
    args = parser.parse_args()
    if args.case:
        run_case(args.output.resolve(), args.case)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for case in ('continuous', 'periodic', 'multiple', 'capacity'):
        with (args.output/(case+'_runner.log')).open('w') as stream:
            subprocess.run([sys.executable, '-B', '-m', 'experiments.validate_attack_patterns',
                            '--output', str(args.output.resolve()/case), '--case', case],
                           cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)
        summaries.append(json.loads((args.output/case/'validation.json').read_text()))
        (args.output/'validation_summary.json').write_text(json.dumps(summaries, indent=2)+'\n')
        print('VALIDATION '+json.dumps(summaries[-1]), flush=True)
    assert summaries[-1]['attack_starts'] < summaries[1]['attack_starts']
    assert summaries[1]['completions_after_window'] > 0 or summaries[-1]['completions_after_window'] > 0


if __name__ == '__main__':
    main()
