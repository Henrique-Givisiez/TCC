"""Evaluation-only truth access and prospective availability/deadline metrics."""
from decimal import Decimal as D
from itertools import combinations
from ..inputs import ContractError,number
from ..artifacts import encoded
from .engine import artifact,validate_run,exact
from .data import load_truth
from .statistics import proportion_ci,mean_ci,paired_detection_ci,paired_mean_ci,delay_summary
from .protocol import METHODS,FEATURES,SPEC,runtime_hashes


@exact
def metrics(rows,truth):
    events=truth['events'];event=events[0] if events else None
    if event:
        start,end=number(event['actual_start_seconds']),number(event['actual_end_seconds'])
    counts=dict(tp=0,fp=0,tn=0,fn=0,boundary=0,unavailable=0,benign_windows=0,attack_windows=0,
        benign_available=0,attack_available=0,post_positive=0,post_available=0,post_windows=0)
    first=None
    for row in rows:
        a,b,available=map(number,(row['window_start_seconds'],row['window_end_seconds'],row['available_at_seconds']))
        decision=row['decision']
        if available<b or (decision is not None and type(decision) is not bool):raise ContractError('Invalid decision availability/type')
        overlap=max(D(0),min(b,end)-max(a,start)) if event else D(0)
        if event and decision is True and overlap>0 and start<=available<=end:
            first=available if first is None else min(first,available)
        if not 30<=a<b<=390:continue
        available_by_horizon=decision is not None and available<=390
        if event and a>=end:
            counts['post_windows']+=1
            if available_by_horizon:
                counts['post_available']+=1;counts['post_positive']+=int(decision)
        if overlap not in (D(0),b-a):counts['boundary']+=1;continue
        positive=bool(overlap);kind='attack' if positive else 'benign';counts[kind+'_windows']+=1
        if not available_by_horizon:counts['unavailable']+=1;continue
        counts[kind+'_available']+=1
        counts['tp' if positive and decision else 'fn' if positive else 'fp' if decision else 'tn']+=1
    ratio=lambda x,y:x/y if y else None
    delay=None if first is None else first-start
    return dict(**counts,fpr=ratio(counts['fp'],counts['benign_available']),
        positives_per_total_benign_window=ratio(counts['fp'],counts['benign_windows']),
        recall=ratio(counts['tp'],counts['tp']+counts['fn']),
        precision=ratio(counts['tp'],counts['tp']+counts['fp']),
        f1=ratio(2*counts['tp'],2*counts['tp']+counts['fp']+counts['fn']),
        post_fpr=ratio(counts['post_positive'],counts['post_available']),
        post_positive_per_total=ratio(counts['post_positive'],counts['post_windows']),
        event_detected=None if event is None else first is not None,
        first_detection_available_at_seconds=first,observed_delay_seconds=delay,
        censor_at_seconds=end if event and first is None else None,
        restricted_undetected_fraction=None if not event else (delay/(end-start) if delay is not None else D(1)),
        event_deadline_seconds=None if not event else end,
        exposure_seconds=None if not event else end-start,early_stop=None if not event else end<D(270),
        availability_basis='simulated_window_closure_or_explicit_recorded_availability_not_measured_processing')


def evaluate(entry,receipt,run,destination,authority):
    if entry['partition']!='TEST':raise ContractError('Final evaluation only accepts TEST')
    doc=validate_run(run)
    if (doc['source']['entry_id']!=entry['id'] or doc['source']['partition']!='TEST'
        or doc['source']['run_id']!=receipt['run_id']
        or doc['source']['feature_manifest_sha256']!=receipt['feature_manifest_sha256']
        or doc['source']['dataset_manifest_sha256']!=receipt['dataset_manifest_sha256']
        or doc['authority']!=authority):raise ContractError('Evaluation source differs')
    truth=load_truth(entry,receipt)
    direct=SPEC.get('configuration_contract')=='complete-direct-b2-v1'
    if direct:
        from .direct_metrics import metrics as direct_metrics
        if bool(truth['events']) != (entry['scenario']!=SPEC['control_scenario']):raise ContractError('Scenario/event mismatch')
        result={method:direct_metrics(doc['methods'][method],truth,doc['method_evaluated'][method],doc['method_unavailable_reason'][method]) for method in METHODS}
    else:result={method:metrics(doc['methods'][method],truth) for method in METHODS}
    if not direct and not doc['evaluated']:
        for row in result.values():
            row.update(event_detected=None,restricted_undetected_fraction=None,scientifically_evaluated=False,reason='secondary_calibration_not_accepted')
    return artifact(destination,'scientific-evaluation',dict(authority=authority,entry=entry,
        run=run.reference,truth=truth['reference'],feature=[doc['source']['family'],doc['source']['feature']],
        results=result,operational=receipt.get('operational'),code=runtime_hashes()))


def aggregate(evaluations,destination,authority,attrition=None):
    docs=[a.read('scientific-evaluation') for a in evaluations]
    keys=[(d['entry']['id'],tuple(d['feature'])) for d in docs]
    if len(keys)!=len(set(keys)) or len(keys)>SPEC['counts']['TEST']*len(FEATURES):raise ContractError('Duplicate or excessive TEST evaluations')
    from ..inputs import read_json
    planned={e['id']:e for e in read_json(authority['plan_path'])['entries'] if e['partition']=='TEST'}
    for d in docs:
        if d['authority']!=authority or d['entry']!=planned.get(d['entry']['id']):raise ContractError('Summary entry differs from authority')
    for eid in {k[0] for k in keys}:
        if {f for i,f in keys if i==eid}!={tuple(f) for f in FEATURES}:raise ContractError('Incomplete feature set for run')
    absent=sorted(set(planned)-{k[0] for k in keys})
    attrition=attrition or {}
    if set(absent)!=set(attrition):raise ContractError('Missing TEST runs require explicit technical attrition')
    from .protocol import TECHNICAL_CODES
    from ..inputs import digest
    for eid,ref in attrition.items():
        if digest(ref['failure_path'])!=ref['failure_sha256'] or digest(ref['cleanup_path'])!=ref['cleanup_sha256']:raise ContractError('Attrition reference changed')
        failure=read_json(ref['failure_path'])
        if failure['entry_id']!=eid or failure['code'] not in TECHNICAL_CODES or failure['authority']!=authority or not read_json(ref['cleanup_path'])['verified']:raise ContractError('Invalid technical attrition')
    if SPEC.get('configuration_contract')=='complete-direct-b2-v1':
        from .direct_summary import summarize
        summary=summarize(docs,planned,SPEC)
        return artifact(destination,'scientific-summary',dict(authority=authority,evaluations=[a.reference for a in evaluations],
            **summary,ci=SPEC['ci'],missing_runs=absent,technical_attrition=attrition,
            operational=impact_aggregate(docs),inference='paired_operational_configurations_not_isolated_causal_mechanisms',code=runtime_hashes()))
    table={}
    for family,feature in FEATURES:
        for scenario in SPEC['scenarios']:
            subset=sorted([d for d in docs if d['feature']==[family,feature] and d['entry']['scenario']==scenario],key=lambda d:d['entry']['block'])
            if len({d['entry']['block'] for d in subset})!=len(subset):raise ContractError('Duplicate TEST block')
            for method in METHODS:
                rows=[d['results'][method] for d in subset]
                event=[r['event_detected'] for r in rows]
                values=lambda key:[float(r[key]) for r in rows if r[key] is not None]
                report=dict(n_runs=len(rows),fpr=mean_ci(values('fpr')),recall=mean_ci(values('recall')),
                    f1=mean_ci(values('f1')),post_fpr=mean_ci(values('post_fpr')),
                    undefined_by_metric={key:sum(r[key] is None for r in rows) for key in ('fpr','recall','f1','post_fpr')},
                    any_false_alarm=proportion_ci(sum(r['fp']>0 for r in rows if r.get('scientifically_evaluated',True)),sum(r.get('scientifically_evaluated',True) for r in rows)),
                    detection=None if scenario==SPEC['control_scenario'] else proportion_ci(sum(x is True for x in event),sum(x is not None for x in event)),
                    unassessed_events=sum(x is None for x in event) if scenario!=SPEC['control_scenario'] else None,
                    misses=None if scenario==SPEC['control_scenario'] or all(x is None for x in event) else sum(x is False for x in event),
                    delay=delay_summary([r['observed_delay_seconds'] for r in rows]),
                    restricted=mean_ci(values('restricted_undetected_fraction')),
                    availability=[dict(benign=r['benign_available'],total_benign=r['benign_windows'],unavailable=r['unavailable']) for r in rows])
                table[f'{feature}/{scenario}/{method}']=report
    paired={}
    for family,feature in FEATURES:
        for scenario in SPEC['scenarios']:
            subset=sorted([d for d in docs if d['feature']==[family,feature] and d['entry']['scenario']==scenario],key=lambda d:d['entry']['block'])
            for left,right in combinations(METHODS,2):
                if (left,right)==('ewma','cusum-freeze'):left,right=right,left
                a=[d['results'][left] for d in subset];b=[d['results'][right] for d in subset]
                def continuous(key):
                    pairs=[(float(x[key]),float(y[key])) for x,y in zip(a,b) if x[key] is not None and y[key] is not None]
                    return paired_mean_ci([x for x,y in pairs],[y for x,y in pairs])
                paired[f'{feature}/{scenario}/{left}-{right}']=dict(
                    detection=None if scenario==SPEC['control_scenario'] else paired_detection_ci(
                        [x['event_detected'] for x,y in zip(a,b) if x['event_detected'] is not None and y['event_detected'] is not None],
                        [y['event_detected'] for x,y in zip(a,b) if x['event_detected'] is not None and y['event_detected'] is not None]),
                    fpr=continuous('fpr'),recall=continuous('recall'),f1=continuous('f1'),restricted=continuous('restricted_undetected_fraction'),
                    conditional_delay_pairs=sum(x['observed_delay_seconds'] is not None and y['observed_delay_seconds'] is not None for x,y in zip(a,b)))
    contrasts={}
    for family,feature in FEATURES:
        for method in METHODS:
            def scenario_rows(s):return sorted([d for d in docs if d['feature']==[family,feature] and d['entry']['scenario']==s],key=lambda d:d['entry']['block'])
            for left,right in SPEC['scenario_contrasts']:
                aa={d['entry']['block']:d for d in scenario_rows(left)};bb={d['entry']['block']:d for d in scenario_rows(right)}
                common=sorted(aa.keys() & bb.keys());a=[aa[k] for k in common];b=[bb[k] for k in common]
                contrasts[f'{feature}/{method}/{left}-{right}']=paired_detection_ci(
                    [x['results'][method]['event_detected'] for x,y in zip(a,b) if x['results'][method]['event_detected'] is not None and y['results'][method]['event_detected'] is not None],
                    [y['results'][method]['event_detected'] for x,y in zip(a,b) if x['results'][method]['event_detected'] is not None and y['results'][method]['event_detected'] is not None])
    return artifact(destination,'scientific-summary',dict(authority=authority,evaluations=[a.reference for a in evaluations],
        results=table,paired=paired,scenario_detection_contrasts=contrasts,ci=SPEC['ci'],
        missing_runs=absent,technical_attrition=attrition,operational=impact_aggregate(docs),
        inference='pointwise_conditional_on_frozen_training_technical_valid_runs_no_superiority_or_simultaneous_claim',code=runtime_hashes()))


def impact(raw):
    """Per-execution service summaries; individual percentiles never averaged."""
    from pathlib import Path
    from experiments import development_d3_minimal as base,stress_processing as processing
    from ..inputs import read_json
    cfg=base.ExperimentConfig.load(Path(raw)/'effective_config.json')
    life,rawrows,rows=processing.reconcile(raw,cfg)
    gt=processing.validate_ground_truth(raw,cfg,rawrows,life['run_id'])
    event=gt['events'][0] if gt['events'] else None
    end=number(event['actual_end_seconds']) if event else D(270)
    start=number(event['actual_start_seconds']) if event else None
    phases={};flat={}
    resource_rows=base.old.csv_rows(Path(raw)/'simulation_metrics.csv')
    for name,a,b in [('PRE',D(30),D(150)),('ACTIVE',D(150),end),('POST',end,D(390))]:
        cpu=[number(r['average_cpu_percent']) for r in resource_rows if a<=number(r['elapsed_seconds'])<b and r['active_containers_names'].strip()
             and r['average_cpu_percent'] not in ('',None)]
        flat[name+'/mean_cpu_docker_percent']=base.ratio(sum(cpu),len(cpu))
        own=[r for r in rows if r['traffic_class']=='benign']
        m=base.measure(own,a,b,life['cutoff']);phases[name]=m
        for key in ('start_rps','terminal_rps','terminal_2xx_rps','success_fraction','failure_or_deadline_miss_fraction','pending_at_end','aged_pending_at_end'):
            flat[name+'/'+key]=m[key]
        flat[name+'/mean_2xx_ms']=m['duration_2xx']['mean']
        # All completed outcomes include timeouts, not only successful survivors.
        cohort=[r for r in own if a<=r['start']<b and r['end'] is not None]
        flat[name+'/mean_all_ms']=base.ratio(sum(r['duration'] for r in cohort),len(cohort))
        flat[name+'/timeout_fraction']=base.ratio(sum('Timeout' in rawrows[r['request_id']].get('error_type','') for r in cohort),len(cohort))
    recovery=[]
    if event:
        benign=[r for r in rows if r['traffic_class']=='benign'];attacks=[r for r in rows if r['traffic_class']=='attack']
        pre=base.reference(benign,30,150,life['cutoff'])
        for a in range(150,390,30):
            left=max(D(a),end)
            if left<a+30:recovery.append(base.assess_window(benign,attacks,left,a+30,life['cutoff'],pre,pre,post=True))
    recovered=None if not event else bool(len(recovery)>=2 and all(w['qualified'] for w in recovery[-2:]) and recovery[-1]['metrics']['pending_at_end']-recovery[-2]['metrics']['pending_at_start']<=2)
    stop_path=Path(raw)/'source_artifacts/stress_stop.json'
    flat['exposure_seconds']=None if not event else end-start
    stop=read_json(stop_path) if stop_path.exists() else None
    flat['stop_command_seconds']=None if not stop else stop['command_seconds']
    flat['emission_end_seconds']=None if not event else end
    flat['offensive_start_rps']=None if not event else base.ratio(sum(r['traffic_class']=='attack' for r in rows),end-start)
    return dict(run_id=life['run_id'],exposure_seconds=flat['exposure_seconds'],
        early_stop=None if not event else end<D(270),recovery_confirmed=recovered,recovery_windows=recovery,stop=read_json(stop_path) if stop_path.exists() else None,
        phases=phases,scalars=flat,percentiles='individual_run_only_no_mean_or_CI_of_pooled_percentiles',
        comparison='paired_operational_policy_at_real_exposure_not_equal_dose')


def impact_aggregate(docs):
    from .statistics import unbounded_mean_ci
    # Evaluate impact once per run, not once per method or feature.
    primary=[d for d in docs if d['feature']==['service','request_starts']]
    table={};paired={}
    for scenario in SPEC['scenarios']:
        subset=[d for d in primary if d['entry']['scenario']==scenario]
        ops=[d['operational'] for d in subset if d.get('operational') is not None]
        keys=sorted({k for op in ops for k in op['scalars']})
        table[scenario]=dict(n_runs=len(subset),n_operational=len(ops),
            missing_operational=len(subset)-len(ops),individual_runs=[dict(entry=d['entry']['id'],block=d['entry']['block'],operational=d.get('operational')) for d in subset],
            early_stop=proportion_ci(sum(o['early_stop'] is True for o in ops),sum(o['early_stop'] is not None for o in ops)),
            recovery=proportion_ci(sum(o.get('recovery_confirmed') is True for o in ops),sum(o.get('recovery_confirmed') is not None for o in ops)),
            stop_reasons={reason:sum(o.get('stop',{}).get('reason')==reason for o in ops if o.get('stop')) for reason in sorted({o['stop']['reason'] for o in ops if o.get('stop')})},
            means={k:(mean_ci if k.endswith('fraction') else unbounded_mean_ci)([float(o['scalars'][k]) for o in ops if o['scalars'].get(k) is not None]) for k in keys})
    a={d['entry']['block']:d.get('operational') for d in primary if d['entry']['scenario']==SPEC['scenario_contrasts'][0][0]}
    b={d['entry']['block']:d.get('operational') for d in primary if d['entry']['scenario']==SPEC['scenario_contrasts'][0][1]}
    common=[k for k in sorted(a.keys()&b.keys()) if a[k] is not None and b[k] is not None]
    keys=sorted({k for i in common for k in a[i]['scalars']})
    for k in keys:
        pairs=[(float(a[i]['scalars'][k]),float(b[i]['scalars'][k])) for i in common if a[i]['scalars'].get(k) is not None and b[i]['scalars'].get(k) is not None]
        paired[k]=unbounded_mean_ci([x-y for x,y in pairs])
    return dict(by_scenario=table,**{'paired_'+SPEC['scenario_contrasts'][0][0]+'_minus_'+SPEC['scenario_contrasts'][0][1]:paired},paired_blocks=common,
        unit='whole_TEST_block',percentiles='individual_run_descriptions_only',
        inference='exposure_differences_are_part_of_protected_policy_not_causal_equal_dose')
