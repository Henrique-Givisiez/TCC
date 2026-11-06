"""Run one explicitly configured scenario with isolated diagnostic image tags."""
import argparse
from pathlib import Path
from simulator.experiment_config import ExperimentConfig


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--dataset-output',type=Path,required=True)
    parser.add_argument('--victim-image',required=True)
    parser.add_argument('--source-image',required=True)
    parser.add_argument('--operational-policy',type=Path, help='Opt-in immutable images and I1 safeguards; JSON Policy fields')
    parser.add_argument('--previous-run',type=Path, help='Previous I1 output: essential failures block continuation')
    args=parser.parse_args()
    from simulator import config
    from experiments.dataset_run import run_recorded
    from experiments.export_dataset import export_run
    config.DOCKER_IMAGE_NAME=args.victim_image
    config.SOURCE_IMAGE=args.source_image
    experiment=ExperimentConfig.load(args.config)
    if experiment.attack.enabled or experiment.attack.attackers:
        raise ValueError('diagnostic validation entrypoint permits benign-only runs')
    operational = None
    previous_images = (config.DOCKER_IMAGE_NAME, config.SOURCE_IMAGE)
    if args.operational_policy:
        import json
        from simulator import docker_manager
        from simulator.exploratory_operations import Policy, Operations, resolve_images, verify_previous
        if args.previous_run:
            verify_previous(args.previous_run)
        policy = Policy(**json.loads(args.operational_policy.read_text()))
        policy.validate(experiment)
        identities = resolve_images(docker_manager.client, args.victim_image, args.source_image)
        config.DOCKER_IMAGE_NAME, config.SOURCE_IMAGE = identities['victim'], identities['source']
        operational = Operations(policy, identities, args.output)
        operational.nominal_seconds = experiment.duration_seconds
    try:
        complete_procedure(lambda: run_recorded(experiment,args.output, operational=operational),
                           lambda: export_run(args.output,args.dataset_output), operational,
                           args.output, args.dataset_output)
    finally:
        config.DOCKER_IMAGE_NAME, config.SOURCE_IMAGE = previous_images


def complete_procedure(run, export, operational, output, destination):
    """Always retain the original failure and attempt export/certification separately."""
    failure = None
    failures = []
    try:
        run()
    except BaseException as exc:
        failure = exc
        failures.append('execution: '+repr(exc))
    try:
        if (Path(output)/'run_status.json').exists():
            export()
        elif operational:
            raise RuntimeError('run_status absent; export not performed')
    except BaseException as exc:
        failures.append('export: '+repr(exc))
        if operational: operational.report['export'] = dict(status='failed', error=repr(exc))
        if failure is None: failure = exc
    if operational:
        try: operational.certify(destination, failures)
        except BaseException as exc:
            if failure is None: failure = exc
        if failure is None and not operational.report['progression_allowed']:
            failure = RuntimeError('operational certification blocked')
    if failure is not None: raise failure


if __name__=='__main__':main()
