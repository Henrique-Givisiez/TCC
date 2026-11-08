"""E12 review: actual emission bounds, technical integrity independent of service."""
import json
from pathlib import Path
from unittest.mock import patch
from experiments import stress_pilot as pilot, stress_processing as proc
from experiments import development_d3_minimal as base
from experiments.stress_observer import Observer,requires_stop

def replay_observer(raw,run,policy=None):
    directory=Path(raw)/'source_artifacts'
    entries=base.read(Path(raw)/'source_inventory.json')
    from simulator.source_aggregate import records
    items=records(directory,entries)
    engine=Observer(); decisions=[]; previous={}
    for line in (directory/'stress_observer.jsonl').read_text().splitlines():
        tick=json.loads(line)
        if tick.get('policy')!=policy:raise ValueError('observer policy differs')
        if tick['run_id']!=run: raise ValueError('observer run mismatch')
        samples=tick['collection_samples']
        for cid,sample in samples.items():
            if not sample['read'] or sample['received_seconds']>tick['observed_seconds']: raise ValueError('invalid sample acquisition')
            if cid in previous and ((sample['read']==previous[cid]['read'] and sample['received_seconds']!=previous[cid]['received_seconds']) or sample['read']<previous[cid]['read']): raise ValueError('cache falsely refreshed')
        expected_last=min([x['received_seconds'] for x in samples.values()] or [0])
        if expected_last!=tick['last_collection_seconds']:raise ValueError('sample freshness mismatch')
        previous=samples
        seen=[x for x in items if x['sequence']<=tick['journal_sequences'][x['source_id']]]
        actual=engine.evaluate(seen,tick['observed_seconds'],tick['last_collection_seconds'])
        if any(tick[k]!=v for k,v in actual.items()): raise ValueError('observer replay mismatch')
        actionable=tick['observed_seconds']<270 and not any(x['kind']=='emission_closed' for x in seen)
        if tick['actionable']!=actionable: raise ValueError('observer action window mismatch')
        if requires_stop(actual['reason'],policy) and actionable: decisions.append(actual)
    stop=directory/'stress_stop.json'
    if stop.exists():
        record=base.read(stop)
        if record['reason']=='observer_failure': raise ValueError('observer failed')
        if not decisions or any(record[k]!=decisions[0][k] for k in ('reason','observed_seconds')):
            raise ValueError('stop not justified by first causal decision')
    elif decisions: raise ValueError('missing controlled stop command')
    return dict(replayed=True,stop=base.read(stop) if stop.exists() else None)

def assess_raw(raw,config,control_raw,control_review):
    report=dict(technical_checks=[],service=None,generator=None,publication={})
    try:
        life,rawrows,rows=proc.reconcile(raw,config)
        gt=proc.validate_ground_truth(raw,config,rawrows,life['run_id'])
        observer=replay_observer(raw,life['run_id'])
        report['technical_checks']=base.old.collection_checks(raw,life['run_id'])
        report['technical_checks'].append(dict(name='controlled_closure',passed=life['controlled_closure']))
        report['technical_checks'].append(dict(name='observer_collection_support',passed=not observer['stop'] or observer['stop']['reason']!='collection_stale'))
        start,end,_=gt['actual_emission_intervals'][0]
        benign=[r for r in rows if r['traffic_class']=='benign'];attack=[r for r in rows if r['traffic_class']=='attack']
        primary=base.reference(benign,30,150,life['cutoff'])
        active=[];post=[]
        for a in range(150,390,30):
            b=min(base.D(a+30),end)
            if base.D(a)<b:
                active.append(base.assess_window(benign,attack,a,b,life['cutoff'],primary,primary,post=False))
            left=max(base.D(a),end)
            if left<a+30:
                post.append(base.assess_window(benign,attack,left,a+30,life['cutoff'],primary,primary,post=True))
        for w in active:
            m=w['metrics'];p=primary['duration_2xx']['p95']
            w['strong_compromise']=bool(w['outcome_support'] and ((m['success_fraction'] is not None and m['success_fraction']<base.D('.95')) or (w['duration_support'] and p is not None and m['duration_2xx']['p95']>2*p)))
        pairs=[(a,b) for a,b in zip(post,post[1:]) if a['qualified'] and b['qualified'] and b['metrics']['pending_at_end']-a['metrics']['pending_at_start']<=2]
        impaired=any(x['service_impairment_observed'] for x in active) or bool(observer['stop'] and observer['stop']['reason']=='service_compromise')
        first=pairs[0][1]['metrics'] if pairs else None
        with patch.object(base.old,'PHASES',[('WARMUP',0,30),('PRE',30,150),('ACTIVE',start,end),('POST',end,390)]):
            resources=base.old.resource_summary(raw)
        resources['interval_basis']='actual offensive emission; Docker samples may repeat, freshness audited separately'
        service=dict(primary_PRE=primary,active_windows=active,post_windows=post,
            actual_emission_end=end,first_post_compatibility=first,
            recovery_event=first if impaired else None,state=('recovery_observed' if impaired else 'post_compatible') if pairs else 'not_confirmed',
            loss_of_qualification_after_confirmation=[w['metrics']['bin_end_seconds'] for w in post if first and w['metrics']['bin_end_seconds']>first['bin_end_seconds'] and not w['qualified']],
            strong_compromise_requires_review=any(x['strong_compromise'] for x in active),
            saturation_proven=False,maximum_capacity_estimated=False,
            last_two_post_windows_qualified=bool(pairs and pairs[-1][1] is post[-1]))
        report.update(lifecycle=life,ground_truth=gt,observer=observer,service=service,
            resources=resources,generator=dict(full_scheduled_load_verified=False,
            actual_offensive_starts=len(attack),actual_emission_seconds=end-start,
            offensive_actual_active=base.measure(attack,start,end,life['cutoff']),
            offensive_actual_post=base.measure(attack,end,390,life['cutoff']),
            actual_offensive_rps=base.ratio(len(attack),end-start),nominal_full_ACTIVE_starts=1440,
            timeout_cancels_server_work=False))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        report['technical_checks'].append(dict(name='integrity',passed=False,evidence=str(exc)))
    valid=bool(report['service']) and all(x['passed'] for x in report['technical_checks'])
    report['classification']=dict(technical_integrity=valid,service_observation_valid=valid,
        service_state=report['service']['state'] if valid else 'unassessable_collection',continued_execution_authorized=False)
    return report

def publish():
    # Reuse append-only publication, dataset/hash correspondence and operation gates.
    with patch.object(base,'validate_plan',pilot.validate_plan),patch.object(base,'assess_raw',assess_raw),patch.object(base,'verify_reference',lambda plan: {}):
        report=base.review_entry(pilot.DEFAULT_MANIFEST)
    return report['classification']
