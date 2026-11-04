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
    args=parser.parse_args()
    from simulator import config
    from experiments.dataset_run import run_recorded
    from experiments.export_dataset import export_run
    config.DOCKER_IMAGE_NAME=args.victim_image
    config.SOURCE_IMAGE=args.source_image
    experiment=ExperimentConfig.load(args.config)
    if experiment.attack.enabled or experiment.attack.attackers:
        raise ValueError('diagnostic validation entrypoint permits benign-only runs')
    try:
        run_recorded(experiment,args.output)
    finally:
        if (args.output/'run_status.json').exists():
            export_run(args.output,args.dataset_output)


if __name__=='__main__':main()
