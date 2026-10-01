"""Sequential real-Docker validation; archive every scenario before starting another."""
import argparse
import csv
from dataclasses import replace
import json
from pathlib import Path
import uuid

from experiments.result_archive import move_result
from simulator import config, main_orchestrator
from simulator.experiment_config import ExperimentConfig

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = {
    'METRICS_LOG_FILE': 'simulation_metrics.csv', 'RTT_LOG_FILE': 'rtt_log.csv',
    'TCPDUMP_OUTPUT_CSV': 'traffic_capture.csv', 'ATTACK_EVENTS_LOG_FILE': 'attack_events.csv',
    'REQUEST_LOG_FILE': 'request_log.csv', 'RUN_STATUS_FILE': 'run_status.json',
    'ATTACK_SUMMARY_LOG_FILE': 'attack_summary_log.csv',
    'NORMAL_TRAFFIC_SUMMARY_LOG_FILE': 'normal_traffic_summary_log.csv',
}


def scenario_configs(base):
    return {
        'A': replace(base, id=base.id + '_A', attack=replace(base.attack, enabled=False)),
        'B': replace(base, id=base.id + '_B', normal_traffic=replace(base.normal_traffic, clients=0)),
        'C': replace(base, id=base.id + '_C'),
    }


def read(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def validate(directory, scenario):
    metrics = read(directory / 'metrics_run.csv')
    requests = read(directory / 'request_log_run.csv')
    events = read(directory / 'attack_events_run.csv')
    packets = read(directory / 'traffic_capture.csv')
    status = json.loads((directory / 'run_status_run.json').read_text())
    integrity = status['topology_integrity']
    assert metrics and all(r['num_instances'] == '1' and r['decision'] == 'NO_ACTION' for r in metrics)
    assert integrity['checks'] >= len(metrics) and integrity['verified_victim_ids'] == [integrity['expected_victim_id']]
    assert all(r['target_url'].startswith('http://localhost:8080/') for r in requests)
    assert all(r['run_id'] == status['run_id'] for r in metrics + requests + events + packets)
    assert all(p['traffic_class'] == 'unknown' for p in packets)
    def active_at(elapsed):
        return int(any(e['actual_start_seconds'] and e['actual_end_seconds'] and
                       float(e['actual_start_seconds']) <= elapsed < float(e['actual_end_seconds'])
                       for e in events))
    for observation in metrics + requests + packets:
        assert int(observation['attack_active']) == active_at(float(observation['elapsed_seconds']))
    for e in events:
        assert e['scheduled_start_seconds'] == '10' and e['scheduled_end_seconds'] == '20'

    successes = [r for r in requests if r['outcome'] == 'response']
    classes = {r['traffic_class'] for r in requests}
    if scenario == 'A':
        assert classes == {'benign'} and not events
        assert all(r['attack_active'] == '0' for r in requests + metrics)
        assert successes
    else:
        assert len(events) == 1 and events[0]['status'] == 'completed'
        assert any(r['traffic_class'] == 'attack' and r['attack_active'] == '1' for r in successes)
        assert all(r['attack_active'] == '1' for r in requests if r['traffic_class'] == 'attack')
        assert any(r['attack_active'] == '0' for r in metrics if float(r['elapsed_seconds']) < 10)
        assert any(r['attack_active'] == '0' for r in metrics if float(r['elapsed_seconds']) >= 21)
        if scenario == 'B':
            assert classes == {'attack'}
        else:
            assert classes == {'benign', 'attack'}
            assert any(r['traffic_class'] == 'benign' and r['attack_active'] == '1' for r in successes)
    # Capture failure remains a failure of overall execution, separately reported.
    errors = status['errors']
    assert status['producers_drained'] and status['end_reason'] == 'simulation_end'
    assert not errors or all('tcpdump' in e.lower() for e in errors), errors
    if status['status'] == 'completed':
        assert packets, 'No packets captured: cannot validate capture'
        if scenario != 'A':
            assert any(p['attack_active'] == '1' for p in packets)
    return dict(scenario=scenario, run_id=status['run_id'], status=status['status'],
                errors=errors, metrics=len(metrics), requests=len(requests), packets=len(packets),
                successful_benign=sum(r['traffic_class']=='benign' for r in successes),
                successful_attack=sum(r['traffic_class']=='attack' for r in successes),
                benign_during_attack=sum(r['traffic_class']=='benign' and r['attack_active']=='1' for r in requests),
                victim_id=integrity['expected_victim_id'], integrity_checks=integrity['checks'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New output directory (never overwrite)')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    base = ExperimentConfig.load(ROOT / 'experiments/configs/single_victim.json')
    # Isolate cleanup from historical/default container names; preserve host port 8080.
    config.BASE_CONTAINER_NAME = 'single_victim_validation_' + uuid.uuid4().hex[:8]
    summaries = []
    for scenario, experiment in scenario_configs(base).items():
        directory = args.output / scenario
        directory.mkdir()
        work = directory / 'pending'
        work.mkdir()
        for setting, filename in ARTIFACTS.items():
            setattr(config, setting, str(work / filename))
        (directory / 'effective_config.json').write_text(experiment.to_json())
        try:
            main_orchestrator.main(experiment)
        finally:
            move_result(work / 'simulation_metrics.csv', directory / 'metrics_run.csv')
            for filename in ['rtt_log.csv', 'traffic_capture.csv', 'attack_summary_log.csv', 'normal_traffic_summary_log.csv']:
                move_result(work / filename, directory / filename)
            work.rmdir()
        summary = validate(directory, scenario)
        summaries.append(summary)
        (args.output / 'validation_summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
        print('VALIDATION ' + json.dumps(summary))


if __name__ == '__main__':
    main()
