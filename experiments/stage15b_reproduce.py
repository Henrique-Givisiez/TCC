"""Independent frozen-decision evaluator: set counts and exact rational metrics.

Shares hash-bound readers and numeric serialization with the publisher, but does
not call its window/event/post-event/aggregation/summary implementations. Window
truth is independently reconstructed from the frozen original global event.
"""
from collections import defaultdict
from decimal import Decimal, localcontext
from fractions import Fraction
from statistics import median

from experiments.stage15b_evaluation import (CONTEXT,METRIC_NAMES,load_decisions,require)


def ratio_fields(tp,fp,tn,fn):
    return dict(precision=Fraction(tp,tp+fp) if tp+fp else None,
        precision_reason=None if tp+fp else 'no_predicted_positive',
        recall=Fraction(tp,tp+fn) if tp+fn else None,
        recall_reason=None if tp+fn else 'no_available_ground_truth_positive',
        f1=Fraction(2*tp,2*tp+fp+fn) if 2*tp+fp+fn else None,
        f1_reason=None if 2*tp+fp+fn else 'no_ground_truth_positive_or_predicted_positive',
        fpr=Fraction(fp,fp+tn) if fp+tn else None,
        fpr_reason=None if fp+tn else 'no_available_benign_decision')


def independent_window(ds,event,scope):
    indices=set(range(48,144) if scope=='PRIMARY' else range(48))
    selected={d.index:d for d in ds if d.index in indices}
    require(set(selected)==indices,'independent horizon cardinality')
    attack=set();benign=set();boundary=set()
    for i in indices:
        overlap=Fraction(0) if event is None else max(Fraction(0),min(Fraction(i+1),event.end)-max(Fraction(i),event.start))
        if overlap==0:benign.add(i)
        elif overlap==1:attack.add(i)
        else:boundary.add(i)
    positive={i for i,d in selected.items() if d.value is True}
    negative={i for i,d in selected.items() if d.value is False}
    missing=indices-positive-negative
    tp=len(attack&positive);fp=len(benign&positive);tn=len(benign&negative);fn=len(attack&negative)
    return dict(analysis_scope=scope,aggregation='PRIMARY_RUN_SEED' if scope=='PRIMARY' else 'STARTUP_DIAGNOSTIC_RUN_SEED',
        TP=tp,FP=fp,TN=tn,FN=fn,eligible_attack_windows=tp+fn,eligible_benign_windows=fp+tn,
        boundary_excluded_count=len(boundary),unavailable_decision_count=len(missing),unavailable_attack_decisions=len(missing&attack),
        unavailable_benign_decisions=len(missing&benign),unavailable_boundary_decisions=len(missing&boundary),
        candidate_decisions=len(indices),valid_decisions=len(positive|negative),attack_windows=len(attack),benign_windows=len(benign),
        **ratio_fields(tp,fp,tn,fn))


def independent_event(ds,event):
    times=[]
    for d in ds:
        if d.index<48 or d.value is not True:continue
        if d.start>=event.end or d.end<=event.start:continue
        times.append(d.available_at)
    t=min(times) if times else None
    delay=t-event.start if t is not None else None
    require(delay is None or delay>=0,'independent negative delay')
    return dict(analysis_scope='PRIMARY',event_applicable=True,event_id=event.event_id,actual_start=event.start,actual_end=event.end,
        event_detected=bool(times),detection_time=t,detection_delay_seconds=delay,event_profile=event.profile,
        event_definition='GLOBAL_ACTUAL_START_TO_ACTUAL_END',time_unit='seconds_since_experiment_start')


def independent_post(ds,event):
    start=max(Fraction(48),event.end)
    candidates=[d for d in ds if d.start>=start and d.end<=144]
    yes=sum(d.value is True for d in candidates);no=sum(d.value is False for d in candidates)
    return dict(analysis_scope='PRIMARY',metric_role='POST_EVENT_DIAGNOSTIC',interval_start=start,interval_end=144,
        candidate_post_event_decisions=len(candidates),post_event_eligible_windows=yes+no,
        unavailable_post_event_decisions=len(candidates)-yes-no,post_event_positive_decisions=yes,
        post_event_alarm_rate=Fraction(yes,yes+no) if yes+no else None,
        post_event_alarm_rate_reason=None if yes+no else 'no_available_post_event_decision')


def describe_independently(values):
    x=sorted(v for v in values if v is not None);n=len(x)
    if n==0:return dict(mean=None,median=None,sample_sd=None,min=None,max=None)
    total=sum(x,Fraction(0));sd=None
    if n>1:
        # Distinct variance algorithm: raw exact moments, not centered deviations.
        variance=(n*sum((v*v for v in x),Fraction(0))-total*total)/(n*(n-1))
        with localcontext(CONTEXT):sd=(Decimal(variance.numerator)/Decimal(variance.denominator)).sqrt()
    return dict(mean=total/n,median=median(x),sample_sd=sd,min=min(x),max=max(x))


def groups(rows):
    result=defaultdict(list)
    for row in rows:result[(row['scenario'],row['method'],row['feature'])].append(row)
    return result


def independent_summary(rows,names,scope):
    result=[]
    for (scenario,method,feature),runs in sorted(groups(rows).items()):
        for name in names:
            good=[r for r in runs if r[name] is not None];bad=[r for r in runs if r[name] is None]
            result.append(dict(scenario=scenario,method=method,feature=feature,analysis_scope=scope,aggregation='RUN_LEVEL_DESCRIPTIVE',
                experimental_unit='run/seed',metric=name,defined_n=len(good),undefined_n=len(bad),
                defined_seeds=[r['seed'] for r in good],undefined_seeds=[r['seed'] for r in bad],**describe_independently([r[name] for r in runs])))
    return result


def independent_tables(docs,ground_truth):
    entries={e['campaign_entry']:e for e in docs['test_inventory']['entries']}
    primary=[];startup=[];events=[];post=[]
    for output in docs['stage15a_manifest']['outputs']:
        entry=entries[output['campaign_entry']];event=ground_truth[entry['campaign_entry']].event
        ds=load_decisions(output,entry)
        info=dict(run_id=entry['run_identity'],campaign_entry=entry['campaign_entry'],seed=entry['seed'],scenario=entry['scenario'],method=output['method'],feature=output['feature'],
            historical_warning_codes=sorted({c['check_id'] for c in entry['stage9_diagnostics'] if not c['passed']}))
        primary.append(dict(**info,**independent_window(ds,event,'PRIMARY')))
        startup.append(dict(**info,**independent_window(ds,event,'STARTUP_DIAGNOSTIC')))
        if event is not None:
            events.append(dict(**info,**independent_event(ds,event)));post.append(dict(**info,**independent_post(ds,event)))
    pooled=[]
    for (scenario,method,feature),runs in sorted(groups(primary).items()):
        count={k:sum(row[k] for row in runs) for k in ('TP','FP','TN','FN','eligible_attack_windows','eligible_benign_windows','boundary_excluded_count','unavailable_decision_count')}
        pooled.append(dict(scenario=scenario,method=method,feature=feature,analysis_scope='PRIMARY',aggregation='SUPPLEMENTARY_POOLED_WINDOWS',
            experimental_unit='run/seed; windows are not independent replicates',runs=16,**count,**ratio_fields(*(count[k] for k in ('TP','FP','TN','FN')))))
    event_summary=[]
    for (scenario,method,feature),runs in sorted(groups(events).items()):
        found=[r for r in runs if r['event_detected']];missed=[r for r in runs if not r['event_detected']]
        stats=describe_independently([r['detection_delay_seconds'] for r in found])
        event_summary.append(dict(scenario=scenario,method=method,feature=feature,analysis_scope='PRIMARY',experimental_unit='run/seed',
            events_total=len(runs),events_detected=len(found),events_missed=len(missed),event_detection_rate=Fraction(len(found),len(runs)),
            detected_n=len(found),missed_n=len(missed),detected_seeds=[r['seed'] for r in found],missed_seeds=[r['seed'] for r in missed],
            **{k+'_delay':v for k,v in stats.items()}))
    return dict(window_metrics_per_run=primary,event_metrics_per_run=events,post_event_metrics_per_run=post,startup_diagnostic_per_run=startup,
        window_metrics_pooled=pooled,
        run_level_descriptive_summary=independent_summary(primary,METRIC_NAMES,'PRIMARY')+independent_summary(post,('post_event_alarm_rate',),'PRIMARY'),
        event_descriptive_summary=event_summary,startup_descriptive_summary=independent_summary(startup,METRIC_NAMES,'STARTUP_DIAGNOSTIC'))
