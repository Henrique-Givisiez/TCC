"""Native Stage 5 integration: distinct sources, routing, capture and real failure."""
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
from simulator import config, main_orchestrator, source_experiment
from simulator.experiment_config import ExperimentConfig
from experiments.validate_single_victim import ARTIFACTS, scenario_configs

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def validate(root, case):
    inventory = json.loads((root/'source_inventory.json').read_text())
    status = json.loads((root/'run_status.json').read_text())
    requests = rows(root/'request_log.csv')
    packets = rows(root/'traffic_capture.csv')
    metrics = rows(root/'simulation_metrics.csv')
    events = rows(root/'attack_events.csv')
    rtts = rows(root/'rtt_log.csv')
    comparisons = json.loads((root/'source_artifacts/network_audit/comparison.json').read_text())
    isolation = json.loads((root/'source_artifacts/network_audit/isolation.json').read_text())
    clock = json.loads((root/'source_artifacts/clock_validation.json').read_text())
    backend = json.loads((root/'proxy_artifacts/backend_inventory.json').read_text())
    identity = json.loads((root/'proxy_artifacts/proxy_identity.json').read_text())
    access = [json.loads(line) for line in (root/'proxy_artifacts/proxy_access.log').read_text().splitlines()]
    access = [r for r in access if r['request_id']]
    evidence = [json.loads(line) for line in (root/'proxy_artifacts/routing_evidence.jsonl').read_text().splitlines()]
    by_request = {r['request_id']:r for r in requests}
    assert len(by_request)==len(requests) and requests and packets and metrics
    assert clock['comparable']
    assert len({e['source_id'] for e in inventory})==len(inventory)==len({e['ip'] for e in inventory})
    expected_normal = 0 if case=='B' else 4
    expected_attack = 0 if case=='A' else 4
    assert sum(e['source_type']=='normal' for e in inventory)==expected_normal
    assert sum(e['source_type']=='attack' for e in inventory)==expected_attack
    for component,count in [('normal',expected_normal),('attack',expected_attack)]:
        origins = [e for e in inventory if e['source_type']==component]
        if count:
            assert sum(e['send_workers'] for e in origins)==64
            assert all(e['send_workers']==16 for e in origins)
    assert all(e['network']=='edos_sources' and e['service_endpoint']==config.SOURCE_SERVICE_ENDPOINT for e in inventory)
    assert all(e['run_id']==status['run_id'] and e['status_final']['drained'] and not e['status_final']['forced'] for e in inventory)
    assert len(backend)==1 and not backend[0]['port_bindings']
    assert all(r['num_instances']=='1' and r['decision']=='NO_ACTION' for r in metrics)
    assert all(r['run_id']==status['run_id'] for r in requests+packets+metrics+events+rtts)
    decoded = subprocess.run(['tcpdump','-nn','-tt','-S','-r',str(root/'source_artifacts/traffic_capture.pcap')],
                             check=True,capture_output=True,text=True).stdout.splitlines()
    from experiments.source_network_audit import TUPLE
    descriptions = [line[TUPLE.search(line).start():] for line in decoded if TUPLE.search(line)]
    repetitions = len(descriptions)-len(set(descriptions))
    # Report real repeat candidates too; never silently deduplicate scientific packets.
    assert repetitions==0, 'repeated packet descriptions require investigation'
    (root/'source_artifacts/raw_capture_validation.json').write_text(json.dumps(dict(
        packets=len(decoded),repeated_descriptions=repetitions,comparison='tuple, TCP seq/ack, flags, TS options, length'),indent=2)+'\n')
    ips = {e['ip'] for e in inventory}
    source_by_id = {e['source_id']:e for e in inventory}
    proxy_ip = comparisons['proxy_ip']
    observed = {r['src_ip'] for r in packets if r['dst_ip']==proxy_ip and r['dst_port']=='80'}
    returned = {r['dst_ip'] for r in packets if r['src_ip']==proxy_ip and r['src_port']=='80'}
    assert observed==returned==ips
    assert all((r['src_ip'] in ips and r['dst_ip']==proxy_ip and r['dst_port']=='80') or
               (r['src_ip']==proxy_ip and r['src_port']=='80' and r['dst_ip'] in ips) for r in packets)
    assert all(r['traffic_class']=='unknown' for r in packets)
    assert all('CONNECTED' not in p['probes'].values() and p['networks']==['edos_sources'] for p in isolation['probes'])
    source_for_request = {}
    for entry in inventory:
        manifest = json.loads((root/'source_artifacts'/entry['source_id']/'manifest.json').read_text())
        encoded = json.dumps(manifest)
        assert all(v['name'] not in encoded and v['ip'] not in encoded for v in backend)
        for row in requests:
            if row['request_id'].startswith('request_'+entry['source_id']+'_'):
                source_for_request[row['request_id']] = entry
                assert row['worker_id']==str(entry['worker_index'])
                assert row['traffic_class']==entry['traffic_class']
    assert set(source_for_request)==set(by_request)
    assert all(r['target_url'].startswith(config.SOURCE_SERVICE_ENDPOINT+'/') for r in requests)
    assert all(r['event_id']=='event_001' and r['attack_id']=='attack_001' for r in requests if r['generator']=='attack')
    assert all(not r['event_id'] and not r['attack_id'] for r in requests if r['generator']=='normal')
    accesses = {}
    for item in access:
        assert item['request_id'] in by_request
        assert item['remote_addr']==source_for_request[item['request_id']]['ip']
        assert ',' not in item['upstream'] and item['upstream']==backend[0]['ip']+':80'
        accesses.setdefault(item['request_id'],[]).append(item)
    successes = [r for r in requests if r['outcome']=='response']
    bodies = {r['request_id']:r for r in evidence}
    for row in successes:
        assert len(accesses[row['request_id']])==1
        assert bodies[row['request_id']]['response_body'].split()[0]=='host='+backend[0]['hostname']
    for row in rtts:
        assert row['request_id'] in by_request and by_request[row['request_id']]['outcome']=='response'
    for event in events:
        starts = [float(r['elapsed_seconds']) for r in requests if r['event_id']==event['event_id']]
        assert float(event['actual_start_seconds'])==min(starts)
        assert float(event['last_request_start_seconds'])==max(starts)
        assert float(event['actual_end_seconds'])>max(starts)
        assert float(event['drained_end_seconds'])==max(float(r['end_elapsed_seconds']) for r in requests if r['event_id']==event['event_id'])
    for row in requests+packets+metrics:
        expected = int(any(float(e['actual_start_seconds'])<=float(row['elapsed_seconds'])<float(e['actual_end_seconds']) for e in events))
        assert int(row['attack_active'])==expected
    errors = sum(r['outcome']=='transport_error' for r in requests)
    if case=='failure':
        assert status['status']=='incomplete' and errors>0 and status['producers_drained']
    else:
        assert status['status']=='completed' and status['producers_drained']
        assert successes and errors==0
    from simulator import docker_manager
    assert not docker_manager.client.containers.list(all=True,filters={'label':'edos.role=source'})
    assert not docker_manager.client.containers.list(all=True,filters={'name':config.BASE_CONTAINER_NAME})
    assert not docker_manager.client.containers.list(all=True,filters={'name':identity['name']})
    return dict(case=case,status=status['status'],normal_sources=expected_normal,attack_sources=expected_attack,
                requests=len(requests),benign_requests=sum(r['traffic_class']=='benign' for r in requests),
                attack_requests=sum(r['traffic_class']=='attack' for r in requests),successful_requests=len(successes),
                transport_errors=errors,packets=len(packets),raw_packets=len(decoded),repeated_packet_descriptions=repetitions,distinct_source_ips=len(observed),
                capture_interface=comparisons['selected_interface'],capture_comparison=comparisons['candidates'],
                clock_comparable=clock['comparable'],direct_routes_detected=0,
                routing_correlations=len(successes),source_inventory=[dict(ip=e['ip'],source_id=e['source_id'],traffic_class=e['traffic_class']) for e in inventory])


def run_case(directory,case):
    directory.mkdir(parents=True,exist_ok=False)
    for setting,filename in ARTIFACTS.items():
        setattr(config,setting,str(directory/filename))
    config.PROXY_ARTIFACT_DIR = str(directory/'proxy_artifacts')
    config.SOURCE_ARTIFACT_DIR = str(directory/'source_artifacts')
    config.SOURCE_INVENTORY_FILE = str(directory/'source_inventory.json')
    config.BASE_CONTAINER_NAME = 'stage5_victim_'+uuid.uuid4().hex[:8]
    base = ExperimentConfig.load(ROOT/'experiments/configs/container_sources.json')
    experiment = scenario_configs(base)[case] if case!='failure' else replace(base,duration_seconds=10,
                        attack=replace(base.attack,start_seconds=1,duration_seconds=8))
    applied = threading.Event()
    failures = []
    def stop_proxy():
        deadline = time.monotonic()+60
        while time.monotonic()<deadline:
            gt,proxy = source_experiment.active_ground_truth,source_experiment.active_proxy
            if gt is not None and gt.clock.elapsed()>=3.1:
                try:
                    proxy.container.stop(timeout=1)
                    applied.set()
                except Exception as exc:
                    failures.append(str(exc))
                return
            time.sleep(.02)
        failures.append('fault injection timeout')
    thread = threading.Thread(target=stop_proxy) if case=='failure' else None
    if thread:
        thread.start()
    try:
        main_orchestrator.main(experiment)
    except RuntimeError:
        if case!='failure':
            raise
    finally:
        if thread:
            thread.join(timeout=5)
            assert applied.is_set() and not thread.is_alive() and not failures,failures
    summary = validate(directory,case)
    (directory/'validation.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('VALIDATION '+json.dumps(summary),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case',choices=['A','B','C','failure'])
    args = parser.parse_args()
    if args.case:
        run_case(args.output.resolve(),args.case)
        return
    args.output.mkdir(parents=True,exist_ok=False)
    summaries = []
    for case in ('A','B','C','failure'):
        with (args.output/(case+'_runner.log')).open('w') as stream:
            subprocess.run([sys.executable,'-B','-m','experiments.validate_source_containers',
                            '--output',str(args.output.resolve()/case),'--case',case],cwd=ROOT,
                           stdout=stream,stderr=subprocess.STDOUT,check=True)
        summaries.append(json.loads((args.output/case/'validation.json').read_text()))
        (args.output/'validation_summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
        print('VALIDATION '+json.dumps(summaries[-1]),flush=True)


if __name__=='__main__':
    main()
