"""Only four dedicated development runs. No scientific execution API or decisions."""
import argparse
import contextlib
import json
from pathlib import Path
from unittest.mock import patch
from .prepare import build_plan,configuration,write,sha

FEATURES=[('network','ingress_packet_count'),('network','ingress_tcp_payload_length_sum_bytes'),
          ('service','request_starts'),('service','mean_duration_ms'),('infrastructure','mean_cpu_percent')]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=a.output.resolve()
    plan=build_plan()
    from simulator import config
    import docker
    client=docker.DockerClient(base_url=config.DOCKER_ENGINE_SOCKET)
    try:
        if client.containers.list():raise RuntimeError('Containers active: refuse concurrent execution')
    finally:client.close()
    root.mkdir(parents=True,exist_ok=False)
    assignments=plan['smoke_development']['assignments']
    configs={}
    for name,seed in assignments.items():
        scenario=name[-1]
        c=configuration(seed,scenario)
        c.update(id=f'stage14a_smoke_development_{name}_{seed}',duration_seconds=30)
        c['attack'].update(start_seconds=8,duration_seconds=12)
        configs[name]=c
    write(root/'smoke_plan.json',dict(scope='smoke/development ONLY; excluded from scientific campaign',
        assignments=assignments,configs=configs,fit_interval=[4,30],order=list(assignments),
        timing='30s = PRE8 + EVENT_POSITION12 + POST10; fitting development only',
        no_thresholds_or_decisions=True))
    from experiments.dataset_run import run_recorded
    from simulator.experiment_config import ExperimentConfig
    from experiments.export_dataset import export_run
    from experiments.validate_dataset import validate_dataset,write_report
    from experiments.extract_features import extract_features
    from analysis.detection import load_series,fit_baseline,score_run
    from analysis.detection.detectors.zscore import ZScore,zscore_spec
    from analysis.detection.detectors.cov import CoV,cov_spec
    sources={};report=[]
    for name,c in configs.items():
        print('START development',name,c['seed'],flush=True)
        write(root/f'configs/{name}.json',c)
        with (root/f'{name}.log').open('x') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
            run_recorded(ExperimentConfig.from_dict(c),root/'raw'/name)
        ds=root/'datasets'/name;export_run(root/'raw'/name,ds)
        r=validate_dataset(ds);validation=root/'validation'/name/'validation_report.json'
        write_report(r,validation,ds)
        if not r['analysis_eligible']:raise RuntimeError(f'{name}: Stage9 ineligible')
        fm=extract_features(ds,validation,root/'features'/name,'1')
        if not fm['network_direction']['supported']:raise RuntimeError('Network unavailable')
        for family,feature in FEATURES:
            sources[name,feature]=load_series(root/'features'/name,run_id=fm['source_run_id'],family=family,
                feature=feature,window_size_seconds=1,feature_schema_version=1,role='baseline' if name=='fit_B' else 'development')
        report.append(dict(name=name,seed=c['seed'],analysis_eligible=True,dataset_sha256=sha(ds/'dataset_manifest.json'),
            feature_sha256=sha(root/'features'/name/'feature_manifest.json')))
        print('DONE development',name,flush=True)
    # Truth files are forbidden during fitting/scoring, including accidental reads.
    original=Path.open
    def guard(path,*args,**kwargs):
        if path.name in ('labels.csv','attack_events.csv'):raise AssertionError('Truth IO during fitting/scoring')
        return original(path,*args,**kwargs)
    score_reports=[]
    with patch.object(Path,'open',guard):
        for _,feature in FEATURES:
            model=fit_baseline([sources['fit_B',feature]],ZScore(),zscore_spec(),root/'models'/feature,
                fit_start_seconds=4,fit_end_seconds=30)
            for name in ['score_B','score_C','score_P']:
                s=sources[name,feature]
                outputs=[('zscore',score_run(s,ZScore(),zscore_spec(),root/'scores'/name/feature/'zscore',baseline=model))]
                for lookback in [6,3,12]:
                    outputs.append((f'cov_L{lookback}',score_run(s,CoV(),cov_spec(lookback=lookback),root/'scores'/name/feature/f'cov_L{lookback}')))
                for method,result in outputs:
                    count=sum(r.score_available for r in result.records)
                    if not count:raise RuntimeError(f'No available scores: {name}/{feature}/{method}')
                    score_reports.append(dict(name=name,feature=feature,method=method,available=count,
                        windows=len(result.records),artifact=result.artifact.reference))
    # Posthoc event verification only. No event detection metric or labels for scores.
    from analysis.detection.evaluation.events import load_event_truth
    events=[]
    for name in configs:
        source=sources[name,'request_starts']
        truth=load_event_truth(source.root,source.reference,stage8_dataset=root/'datasets'/name)
        truth.verify()
        expected=1 if name[-1] in 'CP' else 0
        if len(truth.events)!=expected:raise RuntimeError('Unexpected global event count')
        events.append(dict(name=name,count=len(truth.events),reference=truth.reference,
            events=[{k:str(v) for k,v in vars(e).items()} for e in truth.events]))
    write(root/'summary.json',dict(scope='FUNCTIONAL DEVELOPMENT ONLY; no scientific inference',runs=report,
        scores=score_reports,ground_truth=events,scientific_runs_executed=0,
        thresholds_selected=False,decisions_generated=False,event_attribution_frozen_conflict_unmodified=True))
    print('Development pipeline complete',flush=True)

if __name__=='__main__':main()
