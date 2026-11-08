"""Per-run aggregation and metric-specific paired block sets for direct-80."""
from itertools import combinations
from .statistics import mean_ci,proportion_ci,paired_mean_ci,paired_detection_ci,delay_summary,unbounded_mean_ci
from ..inputs import ContractError

KEYS=('fpr','pre_fpr','recall','precision','f1','decision_coverage','post_positive_fraction','restricted_undetected_fraction')


def summarize(docs,planned,spec):
    results={};paired={};contrasts={};eligibility={}
    methods=spec['methods']
    for family,feature in spec['features']:
        for method in methods:
            states={d['results'][method]['scientifically_evaluated'] for d in docs if d['feature']==[family,feature]}
            if len(states)>1:raise ContractError('Frozen method/feature eligibility changed across TEST')
            eligibility[f'{feature}/{method}']=next(iter(states)) if states else None
        for scenario in spec['scenarios']:
            subset=sorted([d for d in docs if d['feature']==[family,feature] and d['entry']['scenario']==scenario],key=lambda d:d['entry']['block'])
            expected=sum(e['scenario']==scenario for e in planned.values())
            for method in methods:
                rows=[d['results'][method] for d in subset];assessed=[r for r in rows if r['scientifically_evaluated']]
                values=lambda key:[float(r[key]) for r in assessed if r[key] is not None]
                result=dict(n_planned=expected,n_technical_valid=len(rows),n_scientifically_evaluated=len(assessed),n_ineligible=len(rows)-len(assessed),
                    undefined_by_metric={k:sum(r[k] is None for r in rows) for k in KEYS},
                    denominators={k:len(values(k)) for k in KEYS},
                    means={k:mean_ci(values(k)) for k in KEYS},
                    detection=None if scenario==spec['control_scenario'] else proportion_ci(sum(r['event_detected'] is True for r in assessed),len(assessed)),
                    misses=sum(r['event_detected'] is False for r in assessed),
                    delay=delay_summary([r['observed_delay_seconds'] for r in assessed]),
                    post_positive_duration_seconds=unbounded_mean_ci(values('post_positive_duration_seconds')),
                    per_run=[dict(entry=d['entry']['id'],block=d['entry']['block'],metrics=d['results'][method]) for d in subset])
                results[f'{feature}/{scenario}/{method}']=result
            for left,right in combinations(methods,2):
                pair={}
                for key in (*KEYS,'event_detected','observed_delay_seconds'):
                    group=[d for d in subset if d['results'][left][key] is not None and d['results'][right][key] is not None
                           and d['results'][left]['scientifically_evaluated'] and d['results'][right]['scientifically_evaluated']]
                    a=[d['results'][left][key] for d in group];b=[d['results'][right][key] for d in group]
                    if key=='event_detected':estimate=paired_detection_ci(a,b)
                    elif key=='observed_delay_seconds':
                        estimate=unbounded_mean_ci([float(x)-float(y) for x,y in zip(a,b)])
                        if len(group)<spec['ci']['minimum_delay_detections']:
                            estimate.update(interval=None,reason='conditional_pair_support_below_8')
                    else:estimate=paired_mean_ci([float(x) for x in a],[float(y) for y in b])
                    pair[key]=dict(blocks=[d['entry']['block'] for d in group],n_pairs=len(group),estimate=estimate)
                paired[f'{feature}/{scenario}/{left}-{right}']=pair
        for left,right in spec['scenario_contrasts']:
            a={d['entry']['block']:d for d in docs if d['feature']==[family,feature] and d['entry']['scenario']==left}
            b={d['entry']['block']:d for d in docs if d['feature']==[family,feature] and d['entry']['scenario']==right}
            for method in methods:
                table={}
                for key in (*KEYS,'event_detected','observed_delay_seconds'):
                    blocks=[i for i in sorted(a.keys()&b.keys()) if a[i]['results'][method][key] is not None and b[i]['results'][method][key] is not None
                            and a[i]['results'][method]['scientifically_evaluated'] and b[i]['results'][method]['scientifically_evaluated']]
                    x=[a[i]['results'][method][key] for i in blocks];y=[b[i]['results'][method][key] for i in blocks]
                    if key=='event_detected':estimate=paired_detection_ci(x,y)
                    elif key=='observed_delay_seconds':
                        estimate=unbounded_mean_ci([float(v)-float(w) for v,w in zip(x,y)])
                        if len(blocks)<spec['ci']['minimum_delay_detections']:
                            estimate.update(interval=None,reason='conditional_pair_support_below_8')
                    else:estimate=paired_mean_ci([float(v) for v in x],[float(w) for w in y])
                    table[key]=dict(blocks=blocks,n_pairs=len(blocks),estimate=estimate)
                contrasts[f'{feature}/{method}/{left}-{right}']=table
    return dict(results=results,paired=paired,scenario_contrasts=contrasts,
                eligibility=dict(unit='method_x_feature',candidates=len(eligibility),
                    eligible=sum(v is True for v in eligibility.values()),ineligible=sum(v is False for v in eligibility.values()),
                    unknown=sum(v is None for v in eligibility.values()),combinations=eligibility))
