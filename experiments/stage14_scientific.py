"""One planned scientific row per invocation. Default is read-only dry-run.

No TEST release capability. No Stage 11 fitting, thresholds or evaluation.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone
import uuid

from analysis.detection.inputs import ContractError
from analysis.detection.protocol import load_protocol, materialize_seeds, V1_SHA256, V2_BINDINGS
from experiments.stage14a.prepare import encode, sha, write
from simulator.experiment_config import ExperimentConfig

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = Path('experiment_results/stage14-scientific-v2')
PLAN_PATH = 'docs/stage14a/materialized/campaign_plan.json'
PLAN_HASH = 'f50bfe5d71f2246d6dc7c35561eb7872eb3f4e1366bcfc27bcd0016c944423e1'


def now():
    return datetime.now(timezone.utc).isoformat()


def command(*args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ContractError(f'Environment query failed: {args}: {result.stderr.strip()}')
    return result.stdout


def runtime_paths():
    paths = {p for folder in ('simulator', 'analysis', 'experiments')
             for p in (ROOT/folder).rglob('*.py') if '__pycache__' not in p.parts}
    paths.update(p for p in (ROOT/'docker').rglob('*') if p.is_file())
    paths.update(ROOT/p for p in ('Dockerfile', 'requirements.txt'))
    return sorted(paths)


def observe_environment():
    """Strictly observed host fields; no mutation, pulls or image builds."""
    from simulator import config
    os_release = platform.freedesktop_os_release()
    version = json.loads(command('docker','version','--format','{{json .}}'))
    engine = json.loads(command('docker','info','--format','{{json .}}'))
    images = json.loads(command('docker','image','inspect',config.DOCKER_IMAGE_NAME,config.SOURCE_IMAGE,config.PROXY_IMAGE))
    processes = command('ps','-eo','pid,comm,args')
    residual = []
    markers = ('-m simulator.', '-m experiments.dataset_run', '-m experiments.stage14a.smoke',
               '-m pilot_stage13.', '-m experiments.validate_', '-m experiments.stage14_scientific')
    for line in processes.splitlines()[1:]:
        fields = line.split(None,2)
        if len(fields) < 3 or int(fields[0]) == os.getpid():
            continue
        pid, name, args = fields
        if name == 'tcpdump' or (name.startswith('python') and any(m in args for m in markers)):
            residual.append(line)
    stable = dict(os_id=os_release['ID'],os_version=os_release['VERSION_ID'],
        kernel=platform.release(),architecture=platform.machine(),python=platform.python_version(),
        dependencies=sorted(command(sys.executable,'-m','pip','freeze').splitlines()),
        git_head=command('git','rev-parse','HEAD').strip(),
        docker_context=command('docker','context','show').strip(),
        docker_client=version['Client']['Version'],docker_server=version['Server']['Version'],
        daemon_id=engine['ID'],engine_os=engine['OperatingSystem'],engine_kernel=engine['KernelVersion'],
        storage_driver=engine['Driver'],cgroup_version=engine.get('CgroupVersion'),
        images={tag:dict(id=image['Id'],repo_digests=sorted(image.get('RepoDigests') or []))
                for tag,image in zip([config.DOCKER_IMAGE_NAME,config.SOURCE_IMAGE,config.PROXY_IMAGE],images)})
    return dict(captured_at_utc=now(),stable=stable,
        dynamic=dict(branch=command('git','branch','--show-current').strip(),
            git_status=command('git','status','--porcelain=v1','--untracked-files=all'),
            cpu=command('lscpu'),meminfo=Path('/proc/meminfo').read_text(),load_average=os.getloadavg(),
            python_executable=sys.executable),
        active_containers=[json.loads(line) for line in command('docker','ps','--format','{{json .}}').splitlines() if line.strip()],
        residual_processes=residual,processes=processes,
        runtime_sha256={str(p.relative_to(ROOT)):sha(p) for p in runtime_paths()})


def environment_check(lock, current):
    """Fatal: software/source/image/engine identity and concurrent execution.

    Recorded only: branch, dirty paths, CPU, RAM availability/total, load, PID/time.
    Dirty scientific code still fails through runtime hashes. Never updates lock.
    """
    diffs = [f'stable.{key}' for key in set(lock['stable']) | set(current['stable'])
             if lock['stable'].get(key) != current['stable'].get(key)]
    if lock['runtime_sha256'] != current['runtime_sha256']:
        diffs.append('runtime_sha256')
    if current['stable']['os_id'] != 'ubuntu' or current['stable']['docker_context'] != 'default':
        diffs.append('required_native_ubuntu_default_context')
    if 'desktop' in current['stable']['engine_os'].lower():
        diffs.append('Docker Desktop forbidden')
    if current['active_containers'] or current['residual_processes']:
        diffs.append('concurrent_containers_or_traffic_capture')
    return dict(fatal=sorted(diffs), recorded_dynamic=current['dynamic'])


def checked_reference(ref):
    if set(ref) != {'path','sha256'}:
        raise ContractError('Explicit path/hash reference required')
    path = (ROOT/ref['path']).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file() or sha(path) != ref['sha256']:
        raise ContractError(f"Reference hash/path mismatch: {ref['path']}")
    return path, json.loads(path.read_text())


def load_bundle(path, expected_hash):
    if sha(path) != expected_hash:
        raise ContractError('Binding manifest hash mismatch')
    binding = json.loads(Path(path).read_text())
    refs = binding['references']
    _, old = checked_reference(refs['source_stage14a_plan'])
    if refs['source_stage14a_plan'] != dict(path=PLAN_PATH,sha256=PLAN_HASH):
        raise ContractError('Stage14A seed/matrix source identity changed')
    proto_path, _ = checked_reference(refs['protocol'])
    doc, protocol_ref = load_protocol(proto_path,expected_hash=refs['protocol']['sha256'])
    if doc['protocol_version'] != 2 or sha(ROOT/'experiments/protocols/stage14_protocol.json') != V1_SHA256:
        raise ContractError('Requires preserved V1 and explicit V2')
    documents = {}
    for name, required_path in zip(('seed_plan','matrix','environment_lock'),V2_BINDINGS):
        path, documents[name] = checked_reference(refs[name])
        if refs[name]['path'] != required_path or doc['references'].get(required_path) != sha(path):
            raise ContractError(f'Protocol binding mismatch: {name}')
    seeds = documents['seed_plan']
    if (seeds['partitions'] != materialize_seeds(doc['seeds']['namespace'])
            or seeds['partitions'] != old['partitions'] or seeds['partitions'] != doc['seeds']['partitions']
            or seeds['smoke_development'] != old['smoke_development']):
        raise ContractError('Seed plan/partition mismatch')
    expected_rows = [dict(row, role=row['partition']) for row in old['runs']]
    if documents['matrix']['runs'] != expected_rows or len(expected_rows) != 66:
        raise ContractError('Campaign matrix/configuration differs from Stage14A')
    if binding['output_root'] != str(OUTPUT_ROOT) or binding['test_release'] != 'LOCKED':
        raise ContractError('Output root/TEST release contract changed')
    definitive = refs.get('definitive_environment_lock')
    if definitive is not None:
        if binding.get('binding_kind') != 'post_commit_runtime_binding_v1':
            raise ContractError('Explicit definitive binding kind required')
        _, final_lock = checked_reference(definitive)
        reference = final_lock['reference']
        head = reference['stable']['git_head']
        if (reference['dynamic']['git_status'] != ''
                or binding.get('campaign_git_head') != head
                or final_lock['historical_environment_lock'] != refs['environment_lock']):
            raise ContractError('Definitive lock requires matching clean campaign HEAD/history')
        _, historical_binding = checked_reference(final_lock['source_binding'])
        if historical_binding['references'] != {k:v for k,v in refs.items() if k != 'definitive_environment_lock'}:
            raise ContractError('Definitive binding changed historical scientific references')
        documents['historical_environment_lock'] = documents['environment_lock']
        documents['environment_lock'] = final_lock
    elif binding.get('binding_kind') is not None:
        raise ContractError('Definitive binding requires definitive environment lock')
    return binding, doc, protocol_ref, documents


def preflight_entry(binding_path, expected_hash, *, partition, run, role=None, seed=None,
                    scenario=None, configuration=None, environment=None):
    """Administrative validation only, including LOCKED TEST. Never creates runs."""
    binding, doc, ref, documents = load_bundle(binding_path, expected_hash)
    if partition not in ('baseline','calibration','test') or (role is not None and role != partition):
        raise ContractError('Role/partition mismatch')
    rows = [r for r in documents['matrix']['runs'] if r['partition'] == partition and r['order'] == run]
    if len(rows) != 1:
        raise ContractError('No unique planned row for partition/run')
    row = rows[0]
    if (row['role'] != partition or row['seed'] not in doc['seeds']['partitions'][partition]
            or row['scenario'] not in doc['frozen']['scenarios'][partition]
            or (seed is not None and seed != row['seed'])
            or (scenario is not None and scenario != row['scenario'])):
        raise ContractError('Seed/role/scenario mismatch')
    config = row['config']
    if configuration is not None and configuration != config:
        raise ContractError('Configuration differs from frozen matrix')
    if row['config_sha256'] != hashlib.sha256(encode(config)).hexdigest():
        raise ContractError('Configuration hash mismatch')
    experiment = ExperimentConfig.from_dict(config)
    if experiment.seed != row['seed']:
        raise ContractError('Seed/configuration mismatch')
    if partition != 'test' and (experiment.attack.enabled or row['scenario'] != 'B'):
        raise ContractError('BASELINE/CALIBRATION require planned benign configuration')
    destination = ROOT/OUTPUT_ROOT/f"{row['order']:02d}_{partition}_{row['seed']}_{row['scenario']}"
    if destination.exists() or destination.is_symlink():
        raise ContractError('Output collision; replay/overwrite forbidden')
    current = observe_environment() if environment is None else environment
    check = environment_check(documents['environment_lock']['reference'],current)
    if binding.get('binding_kind') == 'post_commit_runtime_binding_v1' and current['dynamic']['git_status']:
        check['fatal'].append('git_tree_not_clean')
    result = dict(schema_version=1,status='preflight_rejected' if check['fatal'] else 'dry_run_ready',
        execution_id=uuid.uuid4().hex,prepared_at_utc=now(),binding=dict(path=str(Path(binding_path).resolve()),sha256=expected_hash),
        references=binding['references'],protocol=ref,row=row,role=partition,
        configuration=config,effective_configuration=json.loads(experiment.to_json()),
        destination=str(destination),environment=current,environment_comparison=check,
        pipeline=['simulation','stage8','stage9','stage10'],test_release='LOCKED')
    if partition == 'test':
        result.update(capability='preflight_only', execution_authorized=False,
                      pipeline=[], test_execution='LOCKED')
    return result


def prepare_entry(binding_path, expected_hash, *, partition, run, **selection):
    """Legacy scientific preparation; TEST can only use preflight_entry."""
    if partition == 'test':
        raise ContractError('TEST locked: scientific preparation forbidden; use preflight_entry')
    return preflight_entry(binding_path, expected_hash, partition=partition, run=run, **selection)


def run_pipeline(config, destination):
    """Lazy imports keep dry-run free of simulator initialization/side effects."""
    from experiments.dataset_run import run_recorded
    from experiments.export_dataset import export_run
    from experiments.validate_dataset import validate_dataset, write_report
    from experiments.extract_features import extract_features
    raw, dataset = destination/'raw', destination/'stage8'
    run_recorded(ExperimentConfig.from_dict(config),raw)
    status = json.loads((raw/'run_status.json').read_text())
    if status['status'] != 'completed':
        raise ContractError('Simulation incomplete')
    # Validate the effective configuration actually persisted by the simulator.
    effective = json.loads((raw/'effective_config.json').read_text())
    if effective != json.loads(ExperimentConfig.from_dict(config).to_json()):
        raise ContractError('Simulator effective configuration mismatch')
    export_run(raw,dataset)
    report = validate_dataset(dataset)
    validation = destination/'stage9/validation_report.json'
    write_report(report,validation,dataset)
    if not report['analysis_eligible'] or not report['dataset_valid']:
        raise ContractError('Stage9 scientific eligibility rejected')
    feature_manifest = extract_features(dataset,validation,destination/'stage10','1')
    manifest = json.loads((dataset/'dataset_manifest.json').read_text())
    if (manifest['run_id'] != status['run_id'] or feature_manifest['source_run_id'] != status['run_id']
            or feature_manifest['dataset_manifest_sha256'] != sha(dataset/'dataset_manifest.json')):
        raise ContractError('Stage8/10 run lineage mismatch')
    if (not feature_manifest['network_direction']['supported']
            or feature_manifest['window']['size_seconds'] != '1'
            or feature_manifest['window']['planned_duration_seconds'] != str(config['duration_seconds'])):
        raise ContractError('Stage10 network/window/planned horizon mismatch')
    return dict(run_id=status['run_id'],simulation_status='completed',analysis_eligible=True,
        effective_configuration_sha256=sha(raw/'effective_config.json'),
        stage8=dict(path=str(dataset),manifest_sha256=sha(dataset/'dataset_manifest.json')),
        stage9=dict(path=str(validation),report_sha256=sha(validation),dataset_manifest_sha256=sha(dataset/'dataset_manifest.json')),
        stage10=dict(path=str(destination/'stage10'),manifest_sha256=sha(destination/'stage10/feature_manifest.json'),
            dataset_manifest_sha256=feature_manifest['dataset_manifest_sha256']))


def execute_entry(binding_path, expected_hash, *, partition, run, execute=False):
    # Dry-run never creates scientific directories or invokes run_pipeline.
    if not execute:
        return preflight_entry(binding_path,expected_hash,partition=partition,run=run)
    # Fatal before locks, metadata preparation, output creation or any backend IO.
    if partition == 'test':
        raise ContractError('TEST locked: scientific execution forbidden (preflight only)')
    # Cross-invocation host lock; automatically released on exit. Evidence file retained.
    lock_path = ROOT/'experiment_results/.stage14-scientific.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as guard:
        try:
            fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ContractError('Concurrent scientific executor') from exc
        metadata = prepare_entry(binding_path,expected_hash,partition=partition,run=run)
        if metadata['environment_comparison']['fatal']:
            write(ROOT/'experiment_results/stage14-preflight-v2'/f"{metadata['execution_id']}.json",metadata)
            return metadata
        destination = Path(metadata['destination'])
        destination.mkdir(parents=True,exist_ok=False)
        metadata.update(status='prepared',started_at_utc=now())
        write(destination/'scientific_run_before.json',metadata)
        # Pin all refs and current runtime again immediately before invocation.
        try:
            load_bundle(binding_path,expected_hash)
            for path, expected in metadata['environment']['runtime_sha256'].items():
                if sha(ROOT/path) != expected:
                    raise ContractError('Runtime changed after preflight')
            lineage = run_pipeline(metadata['configuration'],destination)
            metadata.update(status='completed',lineage=lineage)
        except BaseException as exc:
            metadata.update(status='failed',error=repr(exc))
            raise
        finally:
            metadata['finished_at_utc']=now()
            metadata['outputs_sha256']={str(p.relative_to(destination)):sha(p)
                for p in sorted(destination.rglob('*')) if p.is_file()}
            write(destination/'scientific_run_after.json',metadata)
        return metadata


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binding',type=Path,default=ROOT/'experiments/protocols/stage14_binding_v2.json')
    p.add_argument('--binding-sha256',required=True)
    p.add_argument('--partition',choices=['baseline','calibration','test'],required=True)
    p.add_argument('--run',type=int,required=True,help='Global matrix order, not arbitrary seed')
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--preflight',action='store_true',help='Administrative dry-run only; TEST execution remains LOCKED')
    mode.add_argument('--execute',action='store_true',help='Execute BASELINE/CALIBRATION only; TEST always LOCKED')
    p.add_argument('--audit-output',type=Path)
    args=p.parse_args()
    result=execute_entry(args.binding,args.binding_sha256,partition=args.partition,run=args.run,execute=args.execute)
    if args.audit_output:
        target=args.audit_output.resolve()
        scientific=(ROOT/OUTPUT_ROOT).resolve()
        if args.partition == 'test' and (target == scientific or scientific in target.parents):
            raise ContractError('TEST preflight audit must stay outside scientific output root')
        write(args.audit_output,result)
    print(json.dumps(dict(status=result['status'],run=result['row']['order'],partition=result['role'],
                         fatal=result['environment_comparison']['fatal']),indent=2))
    if result['environment_comparison']['fatal']:raise SystemExit(2)

if __name__=='__main__':main()
