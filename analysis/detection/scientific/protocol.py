"""Closed scientific contract; this is not a materialized campaign or release."""
from pathlib import Path
from ..inputs import ContractError, digest, read_json

ROOT=Path(__file__).resolve().parents[3]
FEATURES=(('network','ingress_packet_count'),('network','ingress_tcp_payload_length_sum_bytes'),
          ('service','request_starts'),('service','mean_duration_ms'),('infrastructure','mean_cpu_percent'))
METHODS=('zscore','cov','ewma','cusum-freeze')
PARTITIONS=('BASELINE','CAL_A','CAL_B','TEST')
ROWS=(('C16','M16','E16'),('M16','E16','C16'),('E16','C16','M16'),('E16','M16','C16'),('M16','C16','E16'),('C16','E16','M16'))
ORDER_INDICES=(0,1,2,3,4,5,1,2,0,4,5,3)
TEST_ORDER=tuple(ROWS[i] for i in ORDER_INDICES)
TECHNICAL_CODES=('CAPTURE_LOSS','IDENTITY_JOURNAL_MISMATCH','DATASET_INVALID','MISSING_REQUIRED_ARTIFACTS','MONITOR_SUPPORT')
SPEC=dict(configuration_template_sha256='45214ec78e8650ba97b431c60ce83c4c15508f6832c35aa56cccfe81462531f5',protocol_id='single-victim-scientific-reduced-20261029',version=2,
 counts=dict(BASELINE=4,CAL_A=8,CAL_B=8,TEST=36),test_blocks=12,
 scenarios=['C16','M16','E16'],test_order=[list(row) for row in TEST_ORDER],
 methods=list(METHODS),components=dict(zscore=dict(version=1,ddof=1),cov=dict(version=1,lookback=6),
   ewma=dict(version=1,lambda_='0.2'),cusum_freeze=dict(version=1,k='0.5',comparison='>',missing='null_reset')),
 decimal_precision=50,secondary_failure='retain_predeclared_feature_as_unassessed_no_retuning',features=[list(x) for x in FEATURES],primary_feature='request_starts',primary_conditions=dict(detection='E16',false_alarm='C16'),
 primary_contrast=['cusum-freeze','ewma','E16','request_starts'],
 nominal_seconds=390,maximum_feature_windows=421,full_causal_tail_retained=True,selection=[30,390],window_seconds=1,attack_interval=[150,270],
 drain_seconds=30,idle_seconds=60,administrative_seconds=600,entry_envelope_seconds=1080,
 alpha='0.01',minimum_available_fraction='0.95',cal_a_mean_max='0.01',cal_a_run_max='0.05',
 cal_b_mean_max='0.02',cal_b_run_max='0.05',
 h_grid=['0','0.25','0.5','0.75','1','1.5','2','3','4','8','16'],
 no_candidate='PUBLISH_REJECTION_AND_STOP_NO_GRID_EXTENSION',cal_b_failure='STOP_NO_RETUNING_NO_TEST',
 event_rule='positive_observation_overlap_and_window_end_le_decision_availability_le_actual_end',
 missing='no_window_decision_event_operational_miss_delay_null',
 ci=dict(level='0.95',unit='whole_TEST_block',mean_method='BCa',resamples=10000,rng_seed=2026102901,
   degenerate='bounded_Hoeffding',marginal='Wilson_exact_at_extremes',
   paired_event='discordant_exact_97.5_intervals_Bonferroni',minimum_delay_detections=8,bounds=dict(rates=[0,1],paired_differences=[-1,1],conditional_delay_seconds=[0,300]),
   impact=dict(unit='whole_TEST_block',means='BCa_10000_no_CI_if_unbounded_degenerate',rates='BCa_bounded_Hoeffding_if_degenerate',percentiles='individual_run_only_no_averaging',paired='difference_before_resampling_complete_block_pairs_only',attrition='explicit_hash_bound_technical_TEST_closure'),
   multiplicity='pointwise_estimation_no_superiority_tests'),
 replacements=dict(maximum=2,maximum_per_slot=1,maximum_total_attempts=58,
   same_seed_scenario_partition=True,approval='explicit_failure_hash',codes=list(TECHNICAL_CODES),
   prohibit=['CAL_A_REJECTION','CAL_B_REJECTION','MISS','HIGH_FPR','SERVICE_DEGRADATION','LOW_REALIZED_RPS','NO_RECOVERY']),
 protection=dict(poll_seconds='0.25',cohort_width_seconds=10,maturity_seconds=3,minimum_starts=50,unsuccessful_fraction='0.20',queue_threshold=128,queue_sustain_seconds=10,sample_max_age_seconds=5,stop_scope='attack_only_keep_legitimate_and_observation_until_390',valid_service_stop_is_not_replacement=True),
 checkpoints=list(PARTITIONS),test_feedback=False)
PROTOCOL_PATH=ROOT/'docs/scientific_protocol_reduced_20261029.json'


def expected_slots():
    slots=[]
    for partition,count in (('BASELINE',4),('CAL_A',8),('CAL_B',8)):
        slots.extend(dict(partition=partition,block=None,scenario='C16',ordinal=i+1) for i in range(count))
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
    if set(p)!={'protocol','runtime_hashes','environment','seed_audit','entries','results_root'}:
        raise ContractError('Campaign plan fields differ from the closed contract')
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
        used.update(seeds)
    # Snapshot must cover all pre-existing seed-bearing files, not a chosen subset.
    expected=set()
    config_paths={Path(e['config']).resolve() for e in p['entries']}
    result=Path(p['results_root']).resolve()
    for folder in ('experiments/configs','experiments/protocols','docs/stage14a/materialized','experiment_results'):
        for source in (ROOT/folder).rglob('*.json'):
            if result==source.resolve() or result in source.resolve().parents:continue
            if source.resolve() in config_paths:continue
            if source.resolve()==Path(p['seed_audit']['path']).resolve() or source.resolve()==path:continue
            try: values=collect_seeds(read_json(source)) if source.stat().st_size else set()
            except (ValueError, OSError):raise ContractError('Unreadable seed inventory source: '+str(source))
            if values:expected.add(str(source.resolve()))
    if expected!={str(Path(x['path']).resolve()) for x in audit['sources']}:
        raise ContractError('Historical seed inventory coverage changed')
    if len(p['entries'])!=56:raise ContractError('Exactly 56 logical slots required')
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
        attack.update(enabled=scenario!='C16',attackers=0 if scenario=='C16' else 1,
            rate=0 if scenario=='C16' else 16,
            endpoint='/medium' if scenario=='M16' else '/expensive')
        expected_cfg={**template,'id':entry['id'],'seed':entry['seed'],'attack':attack}
        if effective!=expected_cfg or read_json_text(cfg.to_json())!=expected_cfg:raise ContractError('Configuration differs from closed scientific matrix')
    if len(set(seeds_by_group.values()))!=32:raise ContractError('Partition or block seeds overlap')
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
