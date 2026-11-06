"""Optional run entrypoint recording provenance before the unchanged simulator."""
import argparse
import json
from pathlib import Path

from experiments.dataset_provenance import capture_provenance
from experiments.export_dataset import export_run

ARTIFACTS = {
    'METRICS_LOG_FILE': 'simulation_metrics.csv', 'RTT_LOG_FILE': 'rtt_log.csv',
    'TCPDUMP_OUTPUT_CSV': 'traffic_capture.csv', 'ATTACK_EVENTS_LOG_FILE': 'attack_events.csv',
    'REQUEST_LOG_FILE': 'request_log.csv', 'RUN_STATUS_FILE': 'run_status.json',
    'ATTACK_SUMMARY_LOG_FILE': 'attack_summary_log.csv',
    'NORMAL_TRAFFIC_SUMMARY_LOG_FILE': 'normal_traffic_summary_log.csv',
}


def run_recorded(experiment, output, operational=None):
    from simulator import config, main_orchestrator
    experiment = experiment.resolve_seed()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    settings = {key: str(output / name) for key, name in ARTIFACTS.items()}
    settings.update(PROXY_ARTIFACT_DIR=str(output / 'proxy_artifacts'),
                    SOURCE_ARTIFACT_DIR=str(output / 'source_artifacts'),
                    SOURCE_INVENTORY_FILE=str(output / 'source_inventory.json'))
    previous = {key: getattr(config, key) for key in settings}
    (output / 'effective_config.json').write_text(experiment.to_json())
    provenance = capture_provenance('execution_before_invocation', docker_endpoint=config.DOCKER_ENGINE_SOCKET)
    provenance['configuration'] = 'effective_config.json'
    (output / 'run_provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    try:
        for key, value in settings.items():
            setattr(config, key, value)
        return main_orchestrator.main(experiment, operational=operational) if operational else main_orchestrator.main(experiment)
    finally:
        for key, value in previous.items():
            setattr(config, key, value)
        status_path = output / 'run_status.json'
        if status_path.exists():
            provenance['run_id'] = json.loads(status_path.read_text()).get('run_id')
            (output / 'run_provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')


def main():
    from simulator.experiment_config import ExperimentConfig
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dataset-output', type=Path)
    args = parser.parse_args()
    experiment = ExperimentConfig.load(args.config)
    try:
        run_recorded(experiment, args.output)
    finally:
        if args.dataset_output and (args.output / 'run_status.json').exists():
            export_run(args.output, args.dataset_output)


if __name__ == '__main__':
    main()
