"""Short Stage 6 runs; reuse Stage 5 isolation/ground-truth validation unchanged."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
import uuid

from experiments.validate_single_victim import ARTIFACTS
from experiments.validate_source_containers import rows, validate
from simulator import config, main_orchestrator, source_experiment
from simulator.app.simple_server import OPERATION_WORK_UNITS
from simulator.experiment_config import ExperimentConfig

ROOT = Path(__file__).resolve().parents[1]


def probe_queries(directory, errors):
    """Operational probes from an existing source, always via the service alias.

    No request ID: these are validation probes, not generated scientific attempts.
    They remain visible in the NGINX log and packet capture.
    """
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            gt, manager = source_experiment.active_ground_truth, source_experiment.active_manager
            if gt is not None and manager is not None and gt.clock.elapsed() >= 1:
                break
            time.sleep(.02)
        else:
            raise RuntimeError('query probe readiness timeout')
        code = '''import requests,json
s=requests.Session(); s.trust_env=False
results=[]
for path in ('/light','/medium','/expensive'):
    for query in ('','?work=0&sleep=99','?work=999999999999','?work=invalid&sleep=invalid'):
        url='http://edos_service:80'+path+query
        r=s.get(url,headers={'X-Edos-Phase':'stage6_validation'},timeout=5,allow_redirects=False)
        results.append(dict(path=path,query=query,status=r.status_code,body=r.text))
print(json.dumps(results))
'''
        result = manager.containers[0].exec_run(['python', '-c', code])
        if result.exit_code:
            raise RuntimeError(result.output.decode())
        probes = json.loads(result.output)
        for probe in probes:
            assert probe['status'] == 200
            assert f"work={OPERATION_WORK_UNITS[probe['path']]} sleep=0.0000s" in probe['body']
        (directory/'query_probes.json').write_text(json.dumps(probes, indent=2)+'\n')
    except Exception as exc:
        errors.append(str(exc))


def run_case(directory, operation):
    directory.mkdir(parents=True, exist_ok=False)
    for setting, filename in ARTIFACTS.items():
        setattr(config, setting, str(directory/filename))
    config.PROXY_ARTIFACT_DIR = str(directory/'proxy_artifacts')
    config.SOURCE_ARTIFACT_DIR = str(directory/'source_artifacts')
    config.SOURCE_INVENTORY_FILE = str(directory/'source_inventory.json')
    config.BASE_CONTAINER_NAME = 'stage6_victim_'+uuid.uuid4().hex[:8]
    base = ExperimentConfig.load(ROOT/'experiments/configs/application_operations.json')
    # Both origins execute the same operation: class must depend on generator,
    # never on operation cost. Identical seeds/rates/windows across all trials.
    experiment = replace(base, id=base.id+'_'+operation,
                         normal_traffic=replace(base.normal_traffic, endpoint='/'+operation),
                         attack=replace(base.attack, endpoint='/'+operation))
    errors = []
    probe = threading.Thread(target=probe_queries, args=(directory, errors)) if operation == 'light' else None
    if probe:
        probe.start()
    try:
        main_orchestrator.main(experiment)
    finally:
        if probe:
            probe.join(timeout=10)
            assert not probe.is_alive() and not errors, errors
    # Existing validator checks source IDs/worker budgets, proxy routing,
    # raw captures, clocks, isolation, ground truth boundaries and cleanup.
    summary = validate(directory, 'C')
    requests = rows(directory/'request_log.csv')
    evidence = {r['request_id']:r for r in map(json.loads,
                (directory/'proxy_artifacts/routing_evidence.jsonl').read_text().splitlines())}
    access_rows = list(map(json.loads, (directory/'proxy_artifacts/proxy_access.log').read_text().splitlines()))
    access = {r['request_id']:r for r in access_rows if r['request_id']}
    if probe:
        probe_rows = [r for r in access_rows if r['phase'] == 'stage6_validation']
        assert len(probe_rows) == 12 and all(r['status'] == 200 and r['upstream'] for r in probe_rows)
        assert {r['request'] for r in probe_rows} == {
            f"GET {r['path']}{r['query']} HTTP/1.1"
            for r in json.loads((directory/'query_probes.json').read_text())}
    expected_url = config.SOURCE_SERVICE_ENDPOINT+'/'+operation
    for request in requests:
        assert request['target_url'] == expected_url
        assert request['http_status'] == '200' and request['outcome'] == 'response'
        assert access[request['request_id']]['request'] == f'GET /{operation} HTTP/1.1'
        assert f'work={OPERATION_WORK_UNITS["/"+operation]} sleep=0.0000s' in evidence[request['request_id']]['response_body']
    durations = [float(r['duration_ms']) for r in requests]
    metrics = rows(directory/'simulation_metrics.csv')
    summary.update(operation=operation, server_work_units=OPERATION_WORK_UNITS['/'+operation],
                   median_request_ms=statistics.median(durations), mean_request_ms=statistics.mean(durations),
                   mean_victim_cpu_percent=statistics.mean(float(r['average_cpu_percent']) for r in metrics),
                   query_control_probes=12 if probe else 0)
    (directory/'validation.json').write_text(json.dumps(summary, indent=2)+'\n')
    print('VALIDATION '+json.dumps(summary), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--operation', choices=['light', 'medium', 'expensive'])
    args = parser.parse_args()
    if args.operation:
        run_case(args.output.resolve(), args.operation)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for operation in ('light', 'medium', 'expensive'):
        with (args.output/(operation+'_runner.log')).open('w') as stream:
            subprocess.run([sys.executable, '-B', '-m', 'experiments.validate_application_operations',
                            '--output', str(args.output.resolve()/operation), '--operation', operation],
                           cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)
        summaries.append(json.loads((args.output/operation/'validation.json').read_text()))
        (args.output/'validation_summary.json').write_text(json.dumps(summaries, indent=2)+'\n')
        print('VALIDATION '+json.dumps(summaries[-1]), flush=True)
    # Report observed performance; no fragile absolute latency assertions.
    print('Observed median request ms: '+json.dumps({s['operation']:s['median_request_ms'] for s in summaries}))


if __name__ == '__main__':
    main()
