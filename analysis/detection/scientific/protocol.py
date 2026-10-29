"""Closed scientific contract; this is not a materialized campaign or release."""
from pathlib import Path
from ..inputs import ContractError, digest, read_json

ROOT=Path(__file__).resolve().parents[3]
FEATURES=(('network','ingress_packet_count'),('network','ingress_tcp_payload_length_sum_bytes'),
          ('service','request_starts'),('service','mean_duration_ms'),('infrastructure','mean_cpu_percent'))
METHODS=('zscore','cov','ewma','cusum-freeze')
PARTITIONS=('BASELINE','CAL_A','CAL_B','TEST')
TECHNICAL_CODES=('CAPTURE_LOSS','IDENTITY_JOURNAL_MISMATCH','DATASET_INVALID','MISSING_REQUIRED_ARTIFACTS','MONITOR_SUPPORT')
DEFAULT_PROTOCOL_PATH=ROOT/'docs/scientific_protocol_reduced_20261029.json'
DEFAULT_PROTOCOL_SHA256='d4ac35dadcf97a85cecfdaecbdc28bf90ef711fc00cb2874a9872780d7ac9afb'

def load_spec(path,sha256):
    if digest(path)!=sha256:raise ContractError('Campaign specification hash changed')
    spec=read_json(path)['specification']
    if set(spec['scenario_parameters'])!=set(spec['scenarios']) or spec['control_scenario'] not in spec['scenarios']:raise ContractError('Scenario inventory differs')
    if len(spec['test_order'])!=spec['test_blocks'] or any(sorted(row)!=sorted(spec['scenarios']) for row in spec['test_order']):raise ContractError('Invalid block inventory')
    if spec['counts']['TEST']!=spec['test_blocks']*len(spec['scenarios']):raise ContractError('TEST count differs')
    if len(spec['scenario_contrasts'])!=1:raise ContractError('Exactly one operational scenario contrast supported')
    for left,right in spec['scenario_contrasts']:
        if left not in spec['scenarios'] or right not in spec['scenarios']:raise ContractError('Unknown contrast scenario')
    return spec

import os
_override=os.environ.get('SCIENTIFIC_SPEC_PATH');_hash=os.environ.get('SCIENTIFIC_SPEC_SHA256')
if bool(_override)!=bool(_hash):raise ContractError('Explicit specification requires path AND hash')
PROTOCOL_PATH=Path(_override).resolve() if _override else DEFAULT_PROTOCOL_PATH
SPEC=load_spec(PROTOCOL_PATH,_hash or DEFAULT_PROTOCOL_SHA256)
TEST_ORDER=tuple(tuple(row) for row in SPEC['test_order'])


def expected_slots():
    slots=[]
    for partition,count in ((part,SPEC['counts'][part]) for part in PARTITIONS if part!='TEST'):
        slots.extend(dict(partition=partition,block=None,scenario=SPEC['control_scenario'],ordinal=i+1) for i in range(count))
    for i,row in enumerate(TEST_ORDER,1):
        slots.extend(dict(partition='TEST',block=i,scenario=s,ordinal=j+1) for j,s in enumerate(row))
    return slots


def runtime_hashes():
    paths=set()
    for folder in ('analysis/detection','experiments','simulator'):
        paths.update((ROOT/folder).rglob('*.py'))
    paths.update(ROOT/p for p in ('requirements.txt','Dockerfile','docker/Dockerfile.sources','docker/requirements.sources.txt'))
    return {str(p.relative_to(ROOT)):digest(p) for p in sorted(paths)}


def load_plan(path,expected_hash):
    path=Path(path).resolve()
    if digest(path)!=expected_hash:raise ContractError('Campaign plan hash changed')
    p=read_json(path)
    if set(p)-{'handoff'}!={'protocol','runtime_hashes','environment','seed_audit','entries','results_root'}:
        raise ContractError('Campaign plan fields differ from the closed contract')
    handoff=validate_handoff(p)
    ref=p['protocol']
    if Path(ref['path']).resolve()!=PROTOCOL_PATH or digest(PROTOCOL_PATH)!=ref['sha256'] or read_json(PROTOCOL_PATH)['specification']!=SPEC:
        raise ContractError('Closed protocol binding changed')
    if p['runtime_hashes']!=runtime_hashes():raise ContractError('Scientific code freeze changed')
    for key in ('environment','seed_audit'):
        if digest(p[key]['path'])!=p[key]['sha256']:raise ContractError(key+' binding changed')
    environment=read_json(p['environment']['path'])
    if set(environment)!={'daemon_id','kernel','python','images','packages'} or not environment['daemon_id'] or not environment['kernel'] or not environment['python']:
        raise ContractError('Incomplete environment lock')
    if not {'docker','requests','numpy','pandas','scipy','matplotlib','openpyxl'}<=set(environment['packages']) or len(environment['images'])!=3:
        raise ContractError('Missing dependency/image version locks')
    import sys,importlib.metadata
    if environment['python']!=sys.version.split()[0]:raise ContractError('Analysis Python differs from frozen environment')
    for name,version in environment['packages'].items():
        if importlib.metadata.version(name)!=version:raise ContractError('Analysis dependency version differs: '+name)
    audit=read_json(p['seed_audit']['path']);used=set()
    if not audit['sources']:raise ContractError('Historical seed audit is empty')
    from experiments.development_d1 import collect_seeds
    for item in audit['sources']:
        if digest(item['path'])!=item['sha256']:raise ContractError('Historical seed source changed')
        seeds=sorted(collect_seeds(read_json(item['path'])))
        if seeds!=item['seeds']:raise ContractError('Historical seed audit disagrees')
        if not handoff or Path(item['path']).resolve()!=Path(handoff['old_plan']['path']).resolve():used.update(seeds)
    # Snapshot must cover all pre-existing seed-bearing files, not a chosen subset.
    expected=set()
    config_paths={Path(e['config']).resolve() for e in p['entries']}
    result=Path(p['results_root']).resolve()
    for folder in ('experiments/configs','experiments/protocols','docs/stage14a/materialized','experiment_results'):
        for source in (ROOT/folder).rglob('*.json'):
            if result==source.resolve() or result in source.resolve().parents:continue
            if handoff and Path(handoff['old_root']).resolve() in source.resolve().parents:continue
            if source.resolve() in config_paths:continue
            if source.resolve()==Path(p['seed_audit']['path']).resolve() or source.resolve()==path:continue
            try: values=collect_seeds(read_json(source)) if source.stat().st_size else set()
            except (ValueError, OSError):raise ContractError('Unreadable seed inventory source: '+str(source))
            if values:expected.add(str(source.resolve()))
    if expected!={str(Path(x['path']).resolve()) for x in audit['sources']}:
        raise ContractError('Historical seed inventory coverage changed')
    if len(p['entries'])!=sum(SPEC['counts'].values()):raise ContractError('Specification logical slot count required')
    from simulator.experiment_config import ExperimentConfig
    template_path=ROOT/'experiments/configs/development_d3_origins_20261029/d3_origins_A_N1.json'
    if digest(template_path)!=SPEC['configuration_template_sha256']:raise ContractError('Locked configuration template changed')
    template=read_json(template_path)
    ids=set();seeds_by_group={};paths=set()
    for entry,slot in zip(p['entries'],expected_slots()):
        if set(entry)!={'id','partition','block','scenario','ordinal','seed','config','config_sha256'} or any(entry[k]!=v for k,v in slot.items()):
            raise ContractError('Slot count/order/scenario changed')
        import re
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}',entry['id']):raise ContractError('Unsafe logical ID')
        if entry['id'] in ids:raise ContractError('Duplicate logical ID')
        ids.add(entry['id'])
        if type(entry['seed']) is not int or entry['seed'] in used or entry['seed']==SPEC['ci']['rng_seed']:raise ContractError('Historical seed reused')
        group=('TEST',entry['block']) if entry['partition']=='TEST' else (entry['partition'],entry['ordinal'])
        seeds_by_group.setdefault(group,entry['seed'])
        if seeds_by_group[group]!=entry['seed']:raise ContractError('TEST block seed differs')
        config_path=Path(entry['config']).resolve()
        if config_path in paths:raise ContractError('Config alias')
        paths.add(config_path)
        if digest(config_path)!=entry['config_sha256']:raise ContractError('Configuration hash changed')
        cfg=ExperimentConfig.load(config_path);effective=read_json(config_path)
        attack=dict(template['attack']);scenario=entry['scenario']
        attack.update(enabled=scenario!=SPEC['control_scenario'],attackers=0 if scenario==SPEC['control_scenario'] else 1,
            **SPEC['scenario_parameters'][scenario])
        expected_cfg={**template,'id':entry['id'],'seed':entry['seed'],'attack':attack}
        if effective!=expected_cfg or read_json_text(cfg.to_json())!=expected_cfg:raise ContractError('Configuration differs from closed scientific matrix')
    if len(set(seeds_by_group.values()))!=sum(SPEC['counts'][part] for part in PARTITIONS if part!='TEST')+SPEC['test_blocks']:raise ContractError('Partition or block seeds overlap')
    validate_destination(result)
    return p


def read_json_text(text):
    import json
    return json.loads(text)


def validate_destination(path):
    path=Path(path).absolute()
    if any(x.is_symlink() for x in (path,*path.parents)):raise ContractError('Symlink result root')
    path=path.resolve()
    tmp=Path('/tmp')
    if not (tmp in path.parents or (path.parent==ROOT/'experiment_results' and path.name.startswith('scientific-'))):
        raise ContractError('New scientific result root required; historical roots are protected')


def validate_handoff(plan):
    if 'handoff' not in plan:return None
    ref=plan['handoff']
    if digest(ref['path'])!=ref['sha256']:raise ContractError('Handoff changed')
    h=read_json(ref['path'])
    for path,expected in h['evidence_hashes'].items():
        if digest(path)!=expected:raise ContractError('Handoff evidence changed: '+path)
    old=read_json(h['old_plan']['path'])
    if digest(h['old_plan']['path'])!=h['old_plan']['sha256']:raise ContractError('Predecessor plan changed')
    if any(plan[k]!=old[k] for k in ('entries','protocol','environment')):raise ContractError('Handoff changes scientific entries/spec/environment')
    if plan['results_root']==old['results_root'] or h['old_root']!=old['results_root']:raise ContractError('Handoff must preserve previous root')
    previous=None;events=[]
    for index,path in enumerate(sorted((Path(h['old_root'])/'journal').glob('*.json')),1):
        event=read_json(path)
        if event['sequence']!=index or event['previous_sha256']!=previous or event['plan_sha256']!=h['old_plan']['sha256']:raise ContractError('Predecessor journal chain changed')
        previous=digest(path);events.append(event)
    kinds=[e['kind'] for e in events]
    if kinds!=['ATTEMPT_CONSUMED','TECHNICAL_FAILURE']:raise ContractError('Predecessor has additional activity')
    attempt=read_json(h['attempt_path']);failure=read_json(h['failure_path']);status=read_json(h['status_path'])
    if (h['original_consumed_attempts']!=1 or h['original_approved_replacements']!=0 or h['corrected_code']!='PRE_RELEASE_CLOCK_FAILURE'
        or failure['code']!='IDENTITY_JOURNAL_MISMATCH' or failure['attempt_number']!=1
        or attempt['entry']['partition']!='BASELINE' or attempt['entry']['scenario']!=SPEC['control_scenario'] or attempt['entry'] not in old['entries'] or attempt['entry']['id']!=h['entry_id']
        or attempt['authority']['plan_sha256']!=h['old_plan']['sha256'] or attempt['authority']['plan_path']!=h['old_plan']['path']
        or events[0]['payload']['sha256']!=digest(h['attempt_path']) or events[1]['payload']['failure_sha256']!=digest(h['failure_path'])
        or failure['entry_id']!=h['entry_id'] or failure['consumed_attempt_sha256']!=digest(h['attempt_path'])
        or not read_json(h['cleanup_path'])['verified'] or read_json(h['execution_path'])['returncode']==0
        or status['status']!='incomplete' or not any('source monotonic clock is not demonstrably comparable' in x for x in status['errors'])
        or not all(e['run_id'] is None for e in read_json(h['inventory_path']))):raise ContractError('Unproven pre-release handoff')
    root=Path(h['old_root'])
    if {str(x.resolve()) for x in root.rglob('*') if x.is_file()}!=set(h['evidence_hashes']):raise ContractError('Predecessor inventory changed')
    if any(root.glob('checkpoints/*')) or any(root.glob('collection/*/attempt-2')):raise ContractError('Handoff already progressed')
    if any(root.glob('collection/*/attempt-1/raw/source_artifacts/*/control/command.json')) or any(root.glob('collection/*/attempt-1/raw/source_artifacts/*/output/journal.jsonl')):raise ContractError('Sources were released')
    diagnosis=read_json(h['diagnosis']['path'])
    if digest(h['diagnosis']['path'])!=h['diagnosis']['sha256'] or diagnosis['diagnostic_reclassification']!=h['corrected_code'] or diagnosis['original_failure_sha256']!=digest(h['failure_path']):raise ContractError('Diagnosis does not bind original symptom')
    return h
