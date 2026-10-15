"""Descriptive pilot analysis, without thresholds, classification or efficacy metrics."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics as st
import time
import resource
from unittest.mock import patch

from analysis.detection import load_series,fit_baseline,score_run
from analysis.detection.detectors.zscore import ZScore,zscore_spec
from analysis.detection.detectors.cov import CoV,cov_spec
from analysis.detection.artifacts import digest
from .run import OUT,ORDERS,put

FEATURES=[('network','ingress_packet_count'),('network','ingress_tcp_payload_length_sum_bytes'),
          ('service','request_starts'),('service','mean_duration_ms'),('infrastructure','mean_cpu_percent')]


def quantile(values,q):
    x=sorted(values);position=(len(x)-1)*q;i=int(position);fraction=position-i
    return x[i]*(1-fraction)+x[min(i+1,len(x)-1)]*fraction


def describe(values, *, relative=True):
    x=[float(v) for v in values if v is not None]
    if not x:return dict(n=0,mean=None,sd=None,median=None,min=None,max=None,descriptive_relative_sd=None)
    mean=st.mean(x);sd=st.stdev(x) if len(x)>1 else None
    return dict(n=len(x),mean=mean,sd=sd,median=st.median(x),min=min(x),max=max(x),
        descriptive_relative_sd=sd/mean if relative and sd is not None and mean>0 and min(x)>=0 else None,
        **{f'q{int(q*100):02}':quantile(x,q) for q in [.1,.25,.5,.75,.9,.95]})


def phase(start):
    return 'PRE' if start<24 else 'EVENT_POSITION' if start<60 else 'POST' if start<84 else 'TAIL'


def block(start):
    return 'PRE_EARLY' if start<12 else 'PRE_LATE' if start<24 else 'EVENT_POSITION' if start<60 else 'POST_EARLY' if start<72 else 'POST_LATE' if start<84 else 'TAIL'


def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not rows:return
    with path.open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator='\n')
        w.writeheader();w.writerows(rows)


def analyze(destination):
    started_wall=time.monotonic();started_cpu=time.process_time()
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=False)
    seeds=list(ORDERS);sources={};models={};runs=[];parameters=[]
    original=Path.open
    def guard(path,*args,**kwargs):
        if path.name=='labels.csv':raise AssertionError('Labels forbidden before scores finalized')
        return original(path,*args,**kwargs)
    with patch.object(Path,'open',guard):
        for seed in seeds:
            for scenario in 'BCP':
                cost=json.loads((OUT/f'cost/{seed}/{scenario}.json').read_text())
                assert cost['analysis_eligible'] and cost['status']=='completed'
                p=OUT/f'features/{seed}/{scenario}';m=json.loads((p/'feature_manifest.json').read_text())
                for family,feature in FEATURES:
                    source=load_series(p,run_id=m['source_run_id'],family=family,feature=feature,
                        window_size_seconds=1,feature_schema_version=1,role='baseline' if scenario=='B' else 'development')
                    sources[seed,scenario,feature]=source
        for seed in seeds:
            for _,feature in FEATURES:
                model=fit_baseline([sources[seed,'B',feature]],ZScore(),zscore_spec(),destination/f'baseline_single/{seed}/{feature}')
                models[seed,feature]=model
                p=model.read()['parameters']
                parameters.append(dict(seed=seed,feature=feature,mu=float(p['mu']),sigma=float(p['sigma']),
                    n_valid=p['n_valid'],n_missing=p['n_missing'],model_hash=model.manifest_sha256))
        # Exploratory cross-fit: each target uses B of another seed, in a fixed cycle.
        for i,seed in enumerate(seeds):
            baseline_seed=seeds[(i-1)%len(seeds)]
            assert baseline_seed != seed
            for scenario in 'BCP':
                for _,feature in FEATURES:
                    source=sources[seed,scenario,feature]
                    z=score_run(source,ZScore(),zscore_spec(),destination/f'scores/zscore_crossfit/{seed}/{scenario}/{feature}',
                                baseline=models[baseline_seed,feature])
                    runs.append(dict(method='zscore_crossfit',seed=seed,scenario=scenario,feature=feature,lookback=None,
                        baseline_seeds=[baseline_seed],result=z))
                    for lookback in [3,6,12]:
                        r=score_run(source,CoV(),cov_spec(lookback=lookback),destination/f'scores/cov_L{lookback}/{seed}/{scenario}/{feature}')
                        runs.append(dict(method='cov',seed=seed,scenario=scenario,feature=feature,lookback=lookback,
                                         baseline_seeds=[],result=r))
        # Separate illustrative split branch: fitting only B101/B211; all scores from
        # other seeds. No score/label in the inspection branch influences this fit.
        for _,feature in FEATURES:
            model=fit_baseline([sources[s,'B',feature] for s in [101,211]],ZScore(),zscore_spec(),destination/f'baseline_partition/{feature}')
            for seed in [307,401,503]:
                for scenario in 'BCP':
                    r=score_run(sources[seed,scenario,feature],ZScore(),zscore_spec(),destination/f'scores/zscore_partition/{seed}/{scenario}/{feature}',baseline=model)
                    runs.append(dict(method='zscore_partition',seed=seed,scenario=scenario,feature=feature,lookback=None,
                                     baseline_seeds=[101,211],result=r))
        for source in sources.values():source.verify()
    # All fit/scoring finished; labels now enter diagnostic summaries only.
    from .truth import window_truth,event_audit
    truth={(seed,scenario):window_truth(sources[seed,scenario,FEATURES[0][1]]) for seed in seeds for scenario in 'BCP'}
    event_rows=[]
    for seed in seeds:
        for scenario in 'BCP':
            audit=event_audit(OUT/f'datasets/{seed}/{scenario}');audit.update(seed=seed,scenario=scenario)
            event_rows.append(audit)
    put(destination/'event_timing_and_counts.json',event_rows)
    feature_rows=[];block_rows=[]
    for (seed,scenario,feature),source in sources.items():
        for label in ['FULL_PLANNED','PRE','EVENT_POSITION','POST','TAIL']:
            obs=[o for o in source.series.observations if (o.window_end_seconds<=84 if label=='FULL_PLANNED' else phase(float(o.window_start_seconds))==label)]
            feature_rows.append(dict(seed=seed,scenario=scenario,feature=feature,phase=label,
                windows=len(obs),nulls=sum(o.value is None for o in obs),**describe([o.value for o in obs])))
        for label in ['PRE_EARLY','PRE_LATE','POST_EARLY','POST_LATE']:
            obs=[o for o in source.series.observations if block(float(o.window_start_seconds))==label]
            block_rows.append(dict(seed=seed,scenario=scenario,feature=feature,block=label,
                nulls=sum(o.value is None for o in obs),**describe([o.value for o in obs])))
    write_csv(destination/'features_by_run_phase.csv',feature_rows);write_csv(destination/'features_by_run_block.csv',block_rows)
    between=[]
    for scenario in 'BCP':
        for _,feature in FEATURES:
            for label in ['FULL_PLANNED','PRE','EVENT_POSITION','POST']:
                vals=[r['mean'] for r in feature_rows if (r['scenario'],r['feature'],r['phase'])==(scenario,feature,label)]
                between.append(dict(scenario=scenario,feature=feature,phase=label,statistic='between_seed_run_means',**describe(vals)))
    write_csv(destination/'between_seeds.csv',between);write_csv(destination/'zscore_parameters.csv',parameters)
    paired=[];contrasts=[];horizon=[]
    for _,feature in FEATURES:
        for label in ['PRE','EVENT_POSITION','POST']:
            for scenario in 'CP':
                differences=[]
                for seed in seeds:
                    current=next(r['mean'] for r in feature_rows if (r['seed'],r['scenario'],r['feature'],r['phase'])==(seed,scenario,feature,label))
                    control=next(r['mean'] for r in feature_rows if (r['seed'],r['scenario'],r['feature'],r['phase'])==(seed,'B',feature,label))
                    differences.append(current-control)
                paired.append(dict(feature=feature,scenario_minus_control=scenario+'-B',phase=label,**describe(differences,relative=False)))
        for seed in seeds:
            source=sources[seed,'B',feature]
            planned=[o.value for o in source.series.observations if o.window_end_seconds<=84]
            tail=[o.value for o in source.series.observations if o.window_start_seconds>=84]
            p=next(r for r in parameters if r['seed']==seed and r['feature']==feature)
            q=describe(planned)
            horizon.append(dict(seed=seed,feature=feature,artifact_mu_all=p['mu'],artifact_sigma_all=p['sigma'],
                planned_mean=q['mean'],planned_sd=q['sd'],planned_n=q['n'],tail_n_valid=sum(v is not None for v in tail),
                tail_values=str([str(v) if v is not None else None for v in tail])))
            for scenario in 'BCP':
                pre=next(r['mean'] for r in block_rows if (r['seed'],r['scenario'],r['feature'],r['block'])==(seed,scenario,feature,'PRE_LATE'))
                post=next(r['mean'] for r in block_rows if (r['seed'],r['scenario'],r['feature'],r['block'])==(seed,scenario,feature,'POST_LATE'))
                contrasts.append(dict(seed=seed,scenario=scenario,feature=feature,pre_late_mean=pre,post_late_mean=post,
                    difference=post-pre,relative_change=(post-pre)/pre if pre else None))
    write_csv(destination/'paired_scenario_differences.csv',paired)
    write_csv(destination/'within_run_temporal_contrasts.csv',contrasts)
    write_csv(destination/'baseline_horizon_diagnostic.csv',horizon)

    param_summary=[];convergence=[];planning=[]
    for _,feature in FEATURES:
        p=[r for r in parameters if r['feature']==feature]
        for parameter in ['mu','sigma']:
            param_summary.append(dict(feature=feature,parameter=parameter,**describe([r[parameter] for r in p])))
        # Baseline mean planning/convergence uses each benign run mean inside plan,
        # not every correlated time window as if independently replicated.
        benign=[st.mean(float(o.value) for o in sources[seed,'B',feature].series.observations
                        if o.window_end_seconds<=84 and o.value is not None) for seed in seeds]
        for n in range(1,6):convergence.append(dict(feature=feature,seeds=n,order='101,211,307,401,503',**describe(benign[:n])))
        relative_sd=st.stdev(benign)/st.mean(benign)
        # Sensitivity calculation, NOT N selection or claimed confidence guarantee.
        for relative_halfwidth in [.1,.05,.02]:
            planning.append(dict(feature=feature,relative_halfwidth=relative_halfwidth,
                normal_approx_n=max(2,math.ceil((1.96*relative_sd/relative_halfwidth)**2)),
                note='planning-only lower-bound heuristic from n=5, iid run means, ignores t/sigma uncertainty and rare false alarms'))
    write_csv(destination/'baseline_parameter_variability.csv',param_summary)
    write_csv(destination/'incremental_convergence.csv',convergence);write_csv(destination/'repetition_precision_sensitivity.csv',planning)
    score_rows=[];diagnostic=[];summary_refs=[]
    # Seed 307 was chosen by fixed central position in the seed list, not scores.
    for run in runs:
        r=run['result'];source=sources[run['seed'],run['scenario'],run['feature']]
        common={k:v for k,v in run.items() if k not in ['result','baseline_seeds']}
        summary_refs.append(dict(**common,baseline_seeds=run['baseline_seeds'],artifact=r.artifact.reference))
        for label in ['PRE','EVENT_POSITION','POST','TAIL']:
            selected=[x for x in r.records if phase(float(x.window_start_seconds))==label]
            score_rows.append(dict(**common,phase=label,windows=len(selected),unavailable=sum(not x.score_available for x in selected),
                                   **describe([x.score for x in selected],relative=False)))
        for pattern_phase in ['programmed_burst','programmed_silence']:
            selected=[x for x in r.records if 24<=float(x.window_start_seconds)<60
                and ((float(x.window_start_seconds)-24)%6<2)==(pattern_phase=='programmed_burst')]
            if run['scenario']=='P':
                score_rows.append(dict(**common,phase=pattern_phase,windows=len(selected),
                    unavailable=sum(not x.score_available for x in selected),**describe([x.score for x in selected],relative=False)))
        if run['seed']==307 and run['method'] in ['cov','zscore_crossfit']:
            for obs,score,t in zip(source.series.observations,r.records,truth[307,run['scenario']]):
                at=float(obs.window_start_seconds)
                diagnostic.append(dict(**common,run_id=obs.run_id,window_index=obs.window_index,
                    start=obs.window_start_seconds,end=obs.window_end_seconds,phase=phase(at),
                    programmed_phase='burst' if run['scenario']=='P' and 24<=at<60 and (at-24)%6<2 else
                                     'silence' if run['scenario']=='P' and 24<=at<60 else 'not_applicable',
                    value='' if obs.value is None else obs.value,score='' if score.score is None else score.score,
                    reason=score.reason or '',available_at=score.available_at_seconds,
                    overlap_posthoc=t['overlap'],attack_request_starts_posthoc=t['attack_request_starts']))
    write_csv(destination/'scores_by_phase.csv',score_rows);write_csv(destination/'diagnostic_seed307.csv',diagnostic)
    normal_calibration=[]
    for run in runs:
        if run['scenario']!='B' or run['seed']!=307 or run['method'] not in ['zscore_partition','cov']:continue
        v=[x.score for x in run['result'].records if x.window_end_seconds<=84]
        normal_calibration.append(dict(method=run['method'],lookback=run['lookback'],feature=run['feature'],
            scope='benign calibration example only; quantiles are descriptive, not thresholds',**describe(v,relative=False)))
    write_csv(destination/'benign_calibration_score_distributions.csv',normal_calibration)
    costs=[json.loads(p.read_text()) for p in sorted((OUT/'cost').rglob('*.json'))]
    def size(root):return sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    summary=dict(plan_sha256=digest(OUT/'plan.json'),scope='pilot only, no decisions/efficacy metrics/final thresholds',runs=len(costs),
        eligible=sum(c.get('analysis_eligible',False) for c in costs),failures=[c for c in costs if c['result']!='completed_eligible'],
        nominal_seconds=sum(c['nominal_seconds'] for c in costs),
        lifecycle_seconds=sum(c['simulation_lifecycle_seconds'] for c in costs),
        total_run_wall_seconds=sum(c['total_wall_seconds'] for c in costs),
        wall_span_seconds=max(c['finished_epoch'] for c in costs)-min(c['started_epoch'] for c in costs),
        bytes_by_stage={key:sum(c['sizes_bytes'][key] for c in costs) for key in ['raw','datasets','features','validation']},
        pilot_storage_bytes=size(OUT),analysis_storage_bytes=size(destination),
        source_run_manifest_refs=summary_refs,quantile_definition='linear interpolation at (n-1)*q',
        variability_unit='run/seed; within-run windows are not independent repetitions',
        method_config=dict(cov_lookbacks=[3,6,12],zscore_ddof=1,cov_ddof=1),
        diagnostic_seed_rule='third seed in predeclared list (307), not performance-selected',
        analysis_wall_seconds=time.monotonic()-started_wall,analysis_cpu_seconds=time.process_time()-started_cpu,
        analysis_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        analysis_code_sha256={str(p):digest(p) for p in sorted(Path(__file__).parent.glob('*.py'))})
    put(destination/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='source_run_manifest_refs'},indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();analyze(args.output)

if __name__=='__main__':main()
