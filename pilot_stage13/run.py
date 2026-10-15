"""Frozen small development pilot: sequential runs through unchanged Stages 0–10."""
import argparse
import contextlib
import csv
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiment_results/stage13-pilot'
ORDERS = {101: 'BCP', 211: 'CPB', 307: 'PBC', 401: 'BPC', 503: 'PCB'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def configuration(seed, scenario):
    return dict(id=f'pilot13_{seed}_{scenario}', seed=seed, duration_seconds=84,
        traffic_sources=dict(execution='containers'), load_balancer=dict(enabled=True),
        infrastructure=dict(initial_instances=1, min_instances=1, max_instances=1),
        autoscaler=dict(enabled=False), server=dict(process_pool_workers=2),
        normal_traffic=dict(clients=4, rate=2, endpoint='/medium',max_concurrent_sends=64,request_timeout_seconds=2),
        attack=dict(enabled=scenario!='B', profile='periodic_burst' if scenario=='P' else 'continuous',
            attackers=1, rate=8, endpoint='/medium', start_seconds=24, duration_seconds=36,
            max_concurrent_sends=64,request_timeout_seconds=2,
            burst=dict(duration_seconds=2,period_seconds=6) if scenario=='P' else None),
        monitoring=dict(interval_seconds=1,stats_poll_interval_seconds=1,history_seconds=30))


def prepare():
    from simulator.experiment_config import ExperimentConfig
    plan_path=OUT/'plan.json'
    if plan_path.exists():
        return json.loads(plan_path.read_text())
    plan=dict(scope='pilot/development only; never final test',seeds=list(ORDERS),
        orders=ORDERS,total_runs=15,nominal_run_seconds=84,pre_seconds=24,
        event_seconds=36,post_seconds=24,operation='/medium',window_seconds=1,
        burst_seconds=2,period_seconds=6,duty_cycle=1/3,cycles=6,
        cov_development_lookbacks=[3,6,12],normal_sources=4,normal_rps_per_source=2,
        attackers=1,attack_active_rps_per_source=8,
        splits='all pilot; provisional independent-run and seed-partition analyses only',
        runner_sha256=sha(__file__))
    for seed,order in ORDERS.items():
        for scenario in order:
            c=configuration(seed,scenario);ExperimentConfig.from_dict(c)
            put(OUT/f'configs/{seed}/{scenario}.json',c)
    plan['config_sha256']={str(p.relative_to(OUT)):sha(p) for p in sorted((OUT/'configs').rglob('*.json'))}
    put(plan_path,plan)
    return plan


def process(seed, scenario):
    from experiments.export_dataset import export_run
    from experiments.validate_dataset import validate_dataset, write_report
    from experiments.extract_features import extract_features
    case=f'{seed}/{scenario}'
    raw=OUT/'raw'/case;dataset=OUT/'datasets'/case
    validation=OUT/'validation'/case/'validation_report.json';features=OUT/'features'/case
    timing={}
    start=time.monotonic();manifest=export_run(raw,dataset);timing['export_seconds']=time.monotonic()-start
    start=time.monotonic();report=validate_dataset(dataset);write_report(report,validation,dataset)
    timing['validation_seconds']=time.monotonic()-start
    if not report['analysis_eligible']:
        raise RuntimeError(f'Run {case} not eligible: {report["summary"]}')
    start=time.monotonic();f=extract_features(dataset,validation,features,'1')
    timing['features_seconds']=time.monotonic()-start
    if not f['network_direction']['supported']:
        raise RuntimeError('Pilot requires observable network')
    from analysis.detection import load_series
    available={}
    for family,feature in [('network','ingress_packet_count'),('network','ingress_tcp_payload_length_sum_bytes'),
            ('service','request_starts'),('service','mean_duration_ms'),('infrastructure','mean_cpu_percent')]:
        s=load_series(features,run_id=f['source_run_id'],family=family,feature=feature,
                      window_size_seconds=1,feature_schema_version=1,role='development')
        available[feature]=dict(windows=len(s.series.observations),nulls=sum(x.value is None for x in s.series.observations))
    return dict(dataset_manifest_sha256=sha(dataset/'dataset_manifest.json'),
        feature_manifest_sha256=sha(features/'feature_manifest.json'),analysis_eligible=True,
        feature_availability=available,processing=timing)


def require_fresh_outputs(seed, scenario):
    """Refuse replay BEFORE writing environment, logs or cost (including failures)."""
    case=f'{seed}/{scenario}'
    paths=[OUT/name/case for name in ['raw','datasets','features','validation']]
    paths += [OUT/f'{name}/{case}{suffix}' for name,suffix in [('cost','.json'),('environment','.json'),('logs','.log')]]
    if any(p.exists() for p in paths):
        raise FileExistsError('Pilot outputs already exist; no replay or overwrite')


def execute(seed, scenario):
    require_fresh_outputs(seed, scenario)
    from experiments.dataset_run import run_recorded
    from simulator.experiment_config import ExperimentConfig
    from simulator import config
    import docker, os, resource
    plan=prepare();cpath=OUT/f'configs/{seed}/{scenario}.json'
    if sha(cpath)!=plan['config_sha256'][str(cpath.relative_to(OUT))] or sha(__file__)!=plan['runner_sha256']:
        raise RuntimeError('Frozen plan/config/runner changed')
    client=docker.DockerClient(base_url=config.DOCKER_ENGINE_SOCKET)
    if client.containers.list():
        raise RuntimeError('Running containers found; refuse experimental interference')
    environment=dict(daemon=client.info(),images={name:client.images.get(name).attrs for name in
                    [config.DOCKER_IMAGE_NAME,config.SOURCE_IMAGE,config.PROXY_IMAGE]},load_average=os.getloadavg())
    client.close()
    raw=OUT/f'raw/{seed}/{scenario}';cost=OUT/f'cost/{seed}/{scenario}.json'
    put(OUT/f'environment/{seed}/{scenario}.json',environment)
    log=OUT/f'logs/{seed}/{scenario}.log';log.parent.mkdir(parents=True,exist_ok=True)
    experiment=ExperimentConfig.load(cpath)
    started=time.time();mono=time.monotonic()
    result=dict(seed=seed,scenario=scenario,nominal_seconds=84,started_epoch=started,
                config_sha256=sha(cpath),runner_sha256=sha(__file__))
    try:
        with log.open('x') as stream, contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
            run_recorded(experiment,raw)
        result['simulation_lifecycle_seconds']=time.monotonic()-mono
        result.update(process(seed,scenario))
        result['result']='completed_eligible'
    except BaseException as exc:
        result['result']='failed';result['exception']=repr(exc)
        raise
    finally:
        status=raw/'run_status.json'
        if status.exists():
            s=json.loads(status.read_text());result.update(run_id=s['run_id'],status=s['status'])
        result['total_wall_seconds']=time.monotonic()-mono
        result['finished_epoch']=time.time()
        result['load_average_end']=os.getloadavg()
        result['runner_maxrss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result['sizes_bytes']={name:sum(p.stat().st_size for p in (OUT/name/str(seed)/scenario).rglob('*') if p.is_file())
                               for name in ['raw','datasets','features','validation']}
        put(cost,result)
    print(json.dumps(result,indent=2))


def compare(seed):
    """Compare canonical config; only intended enabled/profile/burst differ."""
    from copy import deepcopy
    from simulator.experiment_config import ExperimentConfig
    configs={scenario:json.loads(ExperimentConfig.load(OUT/f'configs/{seed}/{scenario}.json').to_json()) for scenario in 'BCP'}
    normalized={}
    for scenario,c in configs.items():
        n=deepcopy(c);n.pop('id');n['attack'].pop('enabled');n['attack'].pop('profile');n['attack'].pop('burst')
        normalized[scenario]=n
    assert normalized['B']==normalized['C']==normalized['P']
    costs=[json.loads((OUT/f'cost/{seed}/{s}.json').read_text()) for s in 'BCP']
    assert all(c['analysis_eligible'] and c['status']=='completed' for c in costs)
    env=[json.loads((OUT/f'environment/{seed}/{s}.json').read_text()) for s in 'BCP']
    assert all({k:v['Id'] for k,v in e['images'].items()}=={k:v['Id'] for k,v in env[0]['images'].items()} for e in env)
    result=dict(seed=seed,nominal_comparability=True,all_analysis_eligible=True,
                intentional_differences=['id','attack.enabled','attack.profile','attack.burst'],
                same_images=True,same_seed=True,warning='same nominal active RPS, different duty cycle and scheduler admission semantics')
    put(OUT/f'comparability/{seed}.json',result);print(json.dumps(result))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',action='store_true')
    p.add_argument('--seed',type=int,choices=list(ORDERS));p.add_argument('--scenario',choices=list('BCP'))
    p.add_argument('--compare',action='store_true');args=p.parse_args()
    if args.prepare:prepare();print(OUT/'plan.json')
    elif args.compare:compare(args.seed)
    elif args.seed is not None and args.scenario:execute(args.seed,args.scenario)
    else:p.error('Use --prepare or explicit seed/scenario or --compare')


if __name__=='__main__':main()
