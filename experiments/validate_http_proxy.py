"""Native Docker integration validation for Stage 4. Separate process per case."""
import argparse
import csv
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

from simulator import config, main_orchestrator
from simulator.experiment_config import ExperimentConfig
from experiments.validate_single_victim import ARTIFACTS, scenario_configs

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def read_logs(directory):
    return [json.loads(line) for line in (directory / 'proxy_artifacts/proxy_access.log').read_text().splitlines()]


def validate(directory, case, count):
    metrics = rows(directory / 'simulation_metrics.csv')
    requests = rows(directory / 'request_log.csv')
    events = rows(directory / 'attack_events.csv')
    packets = rows(directory / 'traffic_capture.csv')
    rtts = rows(directory / 'rtt_log.csv')
    status = json.loads((directory / 'run_status.json').read_text())
    identity = json.loads((directory / 'proxy_artifacts/proxy_identity.json').read_text())
    inventory = json.loads((directory / 'proxy_artifacts/backend_inventory.json').read_text())
    evidence = [json.loads(s) for s in (directory / 'proxy_artifacts/routing_evidence.jsonl').read_text().splitlines()]
    accesses = [r for r in read_logs(directory) if r['phase'] != 'setup']
    assert metrics and requests and packets and accesses
    assert all(r['num_instances'] == str(count) and r['decision'] == 'NO_ACTION' for r in metrics)
    assert all(identity['name'] not in r['active_containers_names'] for r in metrics)
    assert len(inventory) == count and all(not v['port_bindings'] for v in inventory)
    assert identity['run_id'] == status['run_id'] and identity['checks'] > 0
    assert identity['image'] == config.PROXY_IMAGE and identity['digest'] == config.PROXY_IMAGE_DIGEST
    assert identity['daemon_os'].startswith('Ubuntu')
    assert all(r['target_url'].startswith(config.SERVICE_ENDPOINT + '/') for r in requests)
    assert all(r['src_ip'] == r['dst_ip'] == '127.0.0.1' and
               '8080' in (r['src_port'], r['dst_port']) and r['traffic_class']=='unknown' for r in packets)
    assert all(r['run_id'] == status['run_id'] for r in metrics + requests + events + packets + rtts)
    def active_at(elapsed):
        return int(any(e['actual_start_seconds'] and e['actual_end_seconds'] and
                       float(e['actual_start_seconds']) <= elapsed < float(e['actual_end_seconds']) for e in events))
    for observation in metrics + requests + packets:
        assert int(observation['attack_active']) == active_at(float(observation['elapsed_seconds']))
    normal = [r for r in requests if r['generator']=='normal']
    attack = [r for r in requests if r['generator']=='attack']
    assert all(r['traffic_class']=='benign' and not r['event_id'] and not r['attack_id'] for r in normal)
    assert all(r['traffic_class']=='attack' and r['event_id']=='event_001' and r['attack_id']=='attack_001' for r in attack)
    hostnames = {v['hostname'] for v in inventory}
    upstreams = {v['ip'] + ':80' for v in inventory}
    request_by_id = {r['request_id']:r for r in requests}
    access_by_id = {r['request_id']:r for r in accesses}
    assert len(access_by_id) == len(accesses), 'HTTP attempt was retried at proxy/client'
    assert all(r['request_id'] in request_by_id and r['upstream'] in upstreams and ',' not in r['upstream'] for r in accesses)
    routed = set()
    for sample in evidence:
        if sample['http_status'] == 200:
            hostname = sample['response_body'].split()[0].removeprefix('host=')
            assert hostname in hostnames
            access = access_by_id[sample['request_id']]
            victim = next(v for v in inventory if v['hostname']==hostname)
            assert access['upstream'] == victim['ip'] + ':80'
            routed.add(hostname)
    assert routed == hostnames
    assert any(int(r['connection_requests']) > 1 for r in accesses), 'client keepalive not observed'
    if case == 'failure':
        assert status['status'] == 'incomplete' and any('proxy' in e for e in status['errors'])
    else:
        assert status['status']=='completed' and not status['errors']
        if case in ('A','technical'):
            assert normal and not attack and not events
        elif case == 'B':
            assert attack and not normal and len(events)==1 and events[0]['status']=='completed'
        elif case == 'C':
            assert normal and attack and len(events)==1 and events[0]['status']=='completed'
            assert any(r['attack_active']=='1' for r in normal)
    return dict(case=case, status=status['status'], run_id=status['run_id'], victims=count,
                metrics=len(metrics), requests=len(requests), packets=len(packets), access_rows=len(accesses),
                successful_benign=sum(r['outcome']=='response' for r in normal),
                successful_attack=sum(r['outcome']=='response' for r in attack),
                routed_hostnames=sorted(routed), daemon_id=identity['daemon_id'], errors=status['errors'])


def run_case(directory, case):
    directory.mkdir(parents=True, exist_ok=False)
    for setting, filename in ARTIFACTS.items():
        setattr(config, setting, str(directory / filename))
    config.PROXY_ARTIFACT_DIR = str(directory / 'proxy_artifacts')
    config.BASE_CONTAINER_NAME = 'stage4_victim_' + uuid.uuid4().hex[:8]
    base = ExperimentConfig.load(ROOT / 'experiments/configs/proxy_single_victim.json')
    count = 2 if case=='technical' else 1
    if case in ('A','B','C'):
        experiment = scenario_configs(base)[case]
    else:
        experiment = replace(base, id=base.id+'_'+case, duration_seconds=10,
                             attack=replace(base.attack, enabled=False),
                             infrastructure=replace(base.infrastructure, initial_instances=count, min_instances=count, max_instances=count))
    # Assert no selector survives setup or is used during the live window.
    from simulator import normal_traffic, traffic_injectorV0
    from unittest.mock import patch
    stop_errors = []
    stop_applied = threading.Event()
    def stop_proxy():
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            gt = getattr(main_orchestrator, 'ground_truth', None)
            proxy = getattr(main_orchestrator, 'http_proxy', None)
            if gt is not None and proxy is not None and gt.clock.elapsed() >= 3:
                try:
                    proxy.container.stop(timeout=1)
                    stop_applied.set()
                except Exception as exc:
                    stop_errors.append(str(exc))
                return
            time.sleep(.02)
        stop_errors.append('fault injection timeout')
    thread = threading.Thread(target=stop_proxy) if case=='failure' else None
    with patch('simulator.load_balancer.LoadBalancer', side_effect=AssertionError('client selected a backend')):
        if thread:
            thread.start()
        try:
            main_orchestrator.main(experiment)
        except Exception:
            if case != 'failure':
                raise
        finally:
            if thread:
                thread.join(timeout=5)
                assert not thread.is_alive() and not stop_errors and stop_applied.is_set(), stop_errors
    assert normal_traffic._load_balancer is traffic_injectorV0._load_balancer is None
    assert normal_traffic._service_endpoint == traffic_injectorV0._service_endpoint == config.SERVICE_ENDPOINT
    summary = validate(directory, case, count)
    (directory / 'validation.json').write_text(json.dumps(summary, indent=2)+'\n')
    print('VALIDATION '+json.dumps(summary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=['A','B','C','technical','failure'])
    args = parser.parse_args()
    if args.case:
        run_case(args.output.resolve(), args.case)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for case in ('A','B','C','technical','failure'):
        directory = args.output.resolve()/case
        with (args.output/(case+'_runner.log')).open('w') as log:
            subprocess.run([sys.executable, '-B', '-m', 'experiments.validate_http_proxy',
                            '--output', str(directory), '--case', case], cwd=ROOT, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
        summaries.append(json.loads((directory/'validation.json').read_text()))
        (args.output/'validation_summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
        print('VALIDATION '+json.dumps(summaries[-1]), flush=True)


if __name__ == '__main__':
    main()
