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
    result={method:metrics(doc['methods'][method],truth) for method in METHODS}
    if not doc['evaluated']:
        for row in result.values():
            row.update(event_detected=None,restricted_undetected_fraction=None,scientifically_evaluated=False,reason='secondary_calibration_not_accepted')
    return artifact(destination,'scientific-evaluation',dict(authority=authority,entry=entry,
        run=run.reference,truth=truth['reference'],feature=[doc['source']['family'],doc['source']['feature']],
        results=result,code=runtime_hashes()))


def aggregate(evaluations,destination,authority):
    docs=[a.read('scientific-evaluation') for a in evaluations]
    keys=[(d['entry']['id'],tuple(d['feature'])) for d in docs]
    if len(keys)!=320 or len(set(keys))!=320:raise ContractError('Expected 64 TEST runs × five features')
    table={}
    for family,feature in FEATURES:
        for scenario in SPEC['scenarios']:
            subset=sorted([d for d in docs if d['feature']==[family,feature] and d['entry']['scenario']==scenario],key=lambda d:d['entry']['block'])
            if [d['entry']['block'] for d in subset]!=list(range(1,17)):raise ContractError('Incomplete TEST block set')
            for method in METHODS:
                rows=[d['results'][method] for d in subset]
                event=[r['event_detected'] for r in rows]
                values=lambda key:[float(r[key]) for r in rows if r[key] is not None]
                report=dict(n_runs=16,fpr=mean_ci(values('fpr')),recall=mean_ci(values('recall')),
                    f1=mean_ci(values('f1')),post_fpr=mean_ci(values('post_fpr')),
                    undefined_by_metric={key:sum(r[key] is None for r in rows) for key in ('fpr','recall','f1','post_fpr')},
                    any_false_alarm=proportion_ci(sum(r['fp']>0 for r in rows if r.get('scientifically_evaluated',True)),sum(r.get('scientifically_evaluated',True) for r in rows)),
                    detection=None if scenario=='C16' else proportion_ci(sum(x is True for x in event),sum(x is not None for x in event)),
                    unassessed_events=sum(x is None for x in event) if scenario!='C16' else None,
                    misses=None if scenario=='C16' or all(x is None for x in event) else sum(x is False for x in event),
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
                    detection=None if scenario=='C16' else paired_detection_ci(
                        [x['event_detected'] for x,y in zip(a,b) if x['event_detected'] is not None and y['event_detected'] is not None],
                        [y['event_detected'] for x,y in zip(a,b) if x['event_detected'] is not None and y['event_detected'] is not None]),
                    fpr=continuous('fpr'),recall=continuous('recall'),f1=continuous('f1'),restricted=continuous('restricted_undetected_fraction'),
                    conditional_delay_pairs=sum(x['observed_delay_seconds'] is not None and y['observed_delay_seconds'] is not None for x,y in zip(a,b)))
    contrasts={}
    for family,feature in FEATURES:
        for method in METHODS:
            def scenario_rows(s):return sorted([d for d in docs if d['feature']==[family,feature] and d['entry']['scenario']==s],key=lambda d:d['entry']['block'])
            for right in ('M8','E4'):
                a=scenario_rows('E8');b=scenario_rows(right)
                contrasts[f'{feature}/{method}/E8-{right}']=paired_detection_ci(
                    [x['results'][method]['event_detected'] for x,y in zip(a,b) if x['results'][method]['event_detected'] is not None and y['results'][method]['event_detected'] is not None],
                    [y['results'][method]['event_detected'] for x,y in zip(a,b) if x['results'][method]['event_detected'] is not None and y['results'][method]['event_detected'] is not None])
    return artifact(destination,'scientific-summary',dict(authority=authority,evaluations=[a.reference for a in evaluations],
        results=table,paired=paired,scenario_detection_contrasts=contrasts,ci=SPEC['ci'],
        inference='pointwise_conditional_on_frozen_training_technical_valid_runs_no_superiority_or_simultaneous_claim',code=runtime_hashes()))
