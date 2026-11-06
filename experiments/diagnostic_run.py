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
        from simulator.exploratory_operations import Policy, Operations, resolve_images
        if args.previous_run:
            prior = json.loads((args.previous_run/'operational_policy.json').read_text())
            if prior.get('progression_allowed') is not True:
                raise RuntimeError('previous essential failure unresolved; progression blocked')
        policy = Policy(**json.loads(args.operational_policy.read_text()))
        policy.validate(experiment)
        identities = resolve_images(docker_manager.client, args.victim_image, args.source_image)
        config.DOCKER_IMAGE_NAME, config.SOURCE_IMAGE = identities['victim'], identities['source']
        operational = Operations(policy, identities, args.output)
        operational.nominal_seconds = experiment.duration_seconds
    try:
        run_recorded(experiment,args.output, operational=operational)
    finally:
        config.DOCKER_IMAGE_NAME, config.SOURCE_IMAGE = previous_images
        if (args.output/'run_status.json').exists():
            export_run(args.output,args.dataset_output)


if __name__=='__main__':main()
