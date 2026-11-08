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
    parser.add_argument('--composition',choices=('legitimate','offensive','combined'), help='Required with exploratory-offensive-v1')
    parser.add_argument('--previous-run',type=Path, help='Previous I1 output: essential failures block continuation')
    parser.add_argument('--scientific-pilot-scenario',choices=('L2','A3','F96'),help='Explicit diagnostic pilot, outside campaign; install scientific observer')
    parser.add_argument('--cpu-timing-diagnostic-dir', type=Path,
                        help='Explicit D1 exploratory CPU timing; new directory outside raw/dataset; incompatible with scientific pilots')
    args=parser.parse_args()
    from simulator import config
    from experiments.dataset_run import run_recorded
    from experiments.export_dataset import export_run
    experiment=ExperimentConfig.load(args.config).resolve_seed()
    if (experiment.attack.enabled or experiment.attack.attackers) and not args.operational_policy:
        raise ValueError('offensive execution requires protected policy')
    timing_request = None
    if args.cpu_timing_diagnostic_dir is not None:
        from experiments.cpu_timing_diagnostic import prepare_request
        timing_request = prepare_request(experiment, args.cpu_timing_diagnostic_dir,
            args.output, args.dataset_output, args.operational_policy,
            dict(victim=args.victim_image, source=args.source_image),
            args.composition, args.scientific_pilot_scenario)
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
        if policy.version == 'exploratory-offensive-v1':
            if not args.composition:
                raise ValueError('explicit composition required')
            from simulator.exploratory_operations import validate_composition
            validate_composition(experiment, args.composition)
        identities = dict(victim=args.victim_image,source=args.source_image)
        operational = Operations(policy, identities, args.output)
        operational.nominal_seconds = experiment.duration_seconds
    try:
        if args.scientific_pilot_scenario:
            from experiments.scientific_operations import validate_pilot
            validate_pilot(experiment,args.scientific_pilot_scenario,operational)
        if operational:
            config.DOCKER_IMAGE_NAME, config.SOURCE_IMAGE = identities['victim'], identities['source']
            prepare_attempt(operational, experiment, docker_manager.client, args.composition or 'legitimate')
            if timing_request is not None:
                operational.cpu_timing_request = timing_request
                operational.report['attempt'].update(cpu_timing_exploratory=True, campaign_slot=False)
            if args.scientific_pilot_scenario:
                from experiments.scientific_operations import resource_probe,install_observer
                from experiments.stress_observer import DIRECT_POLICY
                evidence=resource_probe(docker_manager.client,identities['source'])
                operational.report['attempt'].update(scientific_pilot=True,campaign_slot=False,
                    scenario=args.scientific_pilot_scenario,effective_resource_probe=evidence)
                install_observer(evidence,DIRECT_POLICY)
        else:
            from simulator import docker_manager
            from experiments.image_code_evidence import verify_image_code
            identities = {role:docker_manager.client.images.get(ref).id for role,ref in [('victim',args.victim_image),('source',args.source_image)]}
            verify_image_code(docker_manager.client, identities)
            config.DOCKER_IMAGE_NAME, config.SOURCE_IMAGE = identities['victim'], identities['source']
        complete_procedure(lambda: run_recorded(experiment,args.output, operational=operational),
                           lambda: export_run(args.output,args.dataset_output), operational,
                           args.output, args.dataset_output)
    finally:
        config.DOCKER_IMAGE_NAME, config.SOURCE_IMAGE = previous_images


def prepare_attempt(operational, experiment, client, composition):
    """Preflight evidence lives beside the fresh raw run; no overwrite/retry."""
    import hashlib
    import json
    import time
    from dataclasses import asdict
    from simulator.exploratory_operations import Operations, resolve_images, validate_composition
    operational.policy.validate(experiment)
    validate_composition(experiment, composition)
    from experiments.image_code_evidence import verify_image_code
    directory = operational.directory.with_name(operational.directory.name+'.attempt')
    if operational.directory.exists():
        raise ValueError('raw output already exists')
    directory.mkdir(parents=True, exist_ok=False)
    preflight = Operations(operational.policy, operational.images, directory)
    attempt = dict(schema_version=1, composition=composition, status='preflight_started',
                   started_monotonic=time.monotonic(), configuration=json.loads(experiment.to_json()),
                   policy=asdict(operational.policy), images=operational.images)
    def persist():
        (directory/'attempt.json').write_text(json.dumps(attempt,indent=2)+'\n')
    attempt['configuration_sha256'] = hashlib.sha256(experiment.to_json().encode()).hexdigest()
    attempt['phases'] = ({'pre':[0,experiment.attack.start_seconds], 'attack':[experiment.attack.start_seconds,experiment.attack.end_seconds],
                          'post':[experiment.attack.end_seconds,experiment.duration_seconds]} if experiment.attack.enabled else {'legitimate':[0,experiment.duration_seconds]})
    persist()
    timeout = client.api.timeout
    try:
        client.api.timeout = operational.policy.docker_timeout_seconds
        preflight.arm()
        preflight.ready(client)
        resolve_images(client, operational.images['victim'], operational.images['source'])
        attempt['image_code'] = verify_image_code(client, operational.images)
        attempt['preflight_sha256'] = hashlib.sha256((directory/'operational_policy.json').read_bytes()).hexdigest()
        attempt['preflight'] = json.loads((directory/'operational_policy.json').read_text())
        attempt['status'] = 'ready'
        operational.report['attempt'] = attempt
    except BaseException as exc:
        attempt.update(status='preflight_failed',error=repr(exc))
        raise
    finally:
        try:
            preflight.disarm()
        except BaseException as exc:
            attempt.update(status='preflight_failed', restoration_error=repr(exc))
            raise
        finally:
            client.api.timeout = timeout
            persist()


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
