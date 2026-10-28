"""One prospective E4, offline review at observed starts; never executes traffic."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal as D, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import subprocess

from experiments import development_d3 as old
from experiments.summarize_service import load_requests, quantile, ratio, number, summarize
from simulator.experiment_config import ExperimentConfig

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / 'experiments/protocols/development_d3_minimal_20261028/manifest.json'
ENTRY_ID = 'd3_minimal_E4_R2'
RULE = dict(window_seconds=30,minimum_exposure_fraction='0.95',minimum_starts=200,
    minimum_duration_2xx_n=200,success_fraction_min='0.99',failure_or_deadline_miss_max='0.01',
    success_reference_tolerance='0.01',p95_reference_factor='1.25',pending_floor=4,
    pending_reference_factor='1.25',pending_age_seconds=3,pending_growth_per_window_max=2,
    pending_growth_per_pair_max=2,confirmation_windows=2,evidence_grace_seconds=3,
    pre_p95_compatibility_ratio=['0.8','1.25'])
COMPATIBLE_FIELDS = ('normal_traffic','infrastructure','autoscaler','server','monitoring',
                     'load_balancer','traffic_sources','duration_seconds')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, value):
    old.write_new(path, value)


def seed_inputs():
    found=set()
    for folder in ('experiments/configs','experiments/protocols','docs/stage14a/materialized','experiment_results'):
        for p in (ROOT/folder).rglob('*.json'):
            if any(x in ('development_d3_minimal_20261028','development-d3-minimal-20261028') for x in p.parts):
                continue
            if p.stat().st_size==0 or old.collect_seeds(read(p)):
                found.add(p)
    if (ROOT/'effective_config.json').exists():found.add(ROOT/'effective_config.json')
    return sorted(found)


def verify_reference(plan):
    ref=plan['secondary_reference']
    for item in ref['files']:
        if sha(ROOT/item['path'])!=item['sha256']:
            raise ValueError('Historical reference changed: '+item['path'])
    if sha(ROOT/ref['review_path'])!=ref['review_sha256']:
        raise ValueError('Historical C review hash mismatch')
    review=read(ROOT/ref['review_path'])
    if review['entry_id']!='d3_pilot_C':raise ValueError('Secondary reference is not the historical C')
    if not review['classification']['control_accepted']:
        raise ValueError('Historical C is not accepted under its own authority')
    for path,digest in review['preserved_raw_hashes'].items():
        if sha(path)!=digest:raise ValueError('Historical C raw changed: '+path)
    return review


def validate_plan(manifest=DEFAULT_MANIFEST, *, check_outputs=True):
    p=read(manifest)
    if (p['schema']!='development-d3-minimal/v1' or p['partition']!='DEVELOPMENT' or p['E8_included'] is not False or len(p['entries'])!=1
        or p['maximum_attempts']!=1 or p['retry']!=0 or p['automatic_progression'] is not False
        or p['rule']!=RULE or p['budget']!=dict(nominal_seconds=390,drain_seconds=30,idle_seconds=60,
            administrative_seconds=600,envelope_seconds=1080)):
        raise ValueError('Minimal authority, rule or budget changed')
    if p['phases']!=[['WARMUP',0,30],['PRE',30,150],['ACTIVE',150,270],['POST',270,390]] or p['primary_reference']['interval']!=[30,150] or p['secondary_reference']['useful_interval']!=[30,390]:
        raise ValueError('Reference or phase intervals changed')
    e=p['entries'][0]
    if e['id']!=ENTRY_ID or e['requires_review_of'] is not None:
        raise ValueError('Only the single prospective E4 belongs to this authority')
    for path,h in p['runtime_source_hashes'].items():
        if sha(ROOT/path)!=h:raise ValueError('Bound source changed: '+path)
    for item in p['evidence']:
        if sha(ROOT/item['path'])!=item['sha256']:raise ValueError('Evidence changed: '+item['path'])
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.run(['git','merge-base','--is-ancestor',p['instrumentation_commit'],head],cwd=ROOT).returncode:
        raise ValueError('Checkout outside recorded source lineage')
    audit=read(ROOT/p['seed_audit']['path'])
    if sha(ROOT/p['seed_audit']['path'])!=p['seed_audit']['sha256']:
        raise ValueError('Seed audit changed')
    if {s['path'] for s in audit['sources']}!={str(x.relative_to(ROOT)) for x in seed_inputs()}:
        raise ValueError('Historical seed inventory changed')
    used=set()
    for s in audit['sources']:
        path=ROOT/s['path'];seeds=old.collect_seeds(read(path) if path.stat().st_size else {})
        if sha(path)!=s['sha256'] or sorted(seeds)!=s['seeds']:raise ValueError('Seed history changed')
        used.update(seeds)
    g=p['seed_generation']
    seed=int.from_bytes(hashlib.sha256(f"{g['namespace']}:{ENTRY_ID}:{g['index']}".encode()).digest()[:8],'big')
    if seed!=p['pilot_seed'] or seed in used:raise ValueError('Seed derivation/collision')
    cfg=ExperimentConfig.load(ROOT/e['config'])
    effective=json.loads(cfg.to_json())
    template=read(ROOT/p['configuration_template']['path'])
    if sha(ROOT/p['configuration_template']['path'])!=p['configuration_template']['sha256']:
        raise ValueError('Original E4 template changed')
    expected={**template,'id':ENTRY_ID,'seed':seed}
    if effective!=expected or read(ROOT/e['config'])!=effective or e['effective_configuration']!=effective or sha(ROOT/e['config'])!=e['config_sha256']:
        raise ValueError('Configuration differs beyond prospective ID/seed')
    if {str(x.relative_to(ROOT)) for x in (ROOT/e['config']).parent.glob('*.json')}!={e['config']}:
        raise ValueError('Unexpected scenario config')
    control=verify_reference(p)
    if any(effective[k]!=control['configuration'][k] for k in COMPATIBLE_FIELDS):
        raise ValueError('Historical C configuration is incompatible')
    paths=list(e['outputs'].values())
    if len(set(paths))!=len(paths) or any(not (ROOT/x).resolve().is_relative_to((ROOT/p['results_root']).resolve()) for x in paths):
        raise ValueError('Output reservation collision/escape')
    if check_outputs and any((ROOT/x).exists() for x in paths):raise FileExistsError('Prospective outputs already exist')
    return dict(manifest_sha256=sha(manifest),configurations=1,entry=ENTRY_ID,seed=seed,seed_collisions=[],
        historical_seed_files=len(audit['sources']),secondary_reference_accepted=True,
        source_checkout=dict(effective_checkout_commit=head,source_tree_unchanged=True),
        docker_accessed=False,experiments_executed=False)


def pending(rows,t):
    return [r for r in rows if r['start']<t and (r['end'] is None or r['end']>=t)]


def measure(rows,a,b,cutoff):
    a,b,cutoff=map(number,(a,b,cutoff));h=b+3
    observed_end=min(b,cutoff)
    cohort=[r for r in rows if a<=r['start']<observed_end]
    entire_window=cutoff>=b
    all_known=entire_window and all(r['end'] is not None and r['end']<=min(h,cutoff) for r in cohort)
    horizon_observed=cutoff>=h
    mature=entire_window and (horizon_observed or all_known)
    known=[r for r in cohort if r['end'] is not None and r['end']<=min(h,cutoff)]
    successes=[r for r in known if r['category']=='success_2xx']
    durations=[r['duration'] for r in successes]
    known_at_b=[r for r in cohort if r['end'] is not None and r['end']<=min(b,cutoff)]
    terminal=[r for r in rows if r['end'] is not None and a<=r['end']<observed_end]
    pa=pending(rows,a) if cutoff>=a else []
    pb=pending(rows,b) if entire_window else []
    conservation=(len(pb)-len(pa)==len(cohort)-len(terminal)) if entire_window else None
    if conservation is False:raise ValueError('Start/end/pending conservation failed')
    n=len(cohort); exposure=max(D(0),observed_end-a)
    end_values=[r['end'] for r in cohort if r['end'] is not None]
    needed=max(b,max(end_values,default=b)) if all_known else h
    return dict(start_seconds=a,bin_end_seconds=b,evidence_horizon_seconds=h,
        observation_cutoff_seconds=cutoff,exposure_seconds=exposure,window_fully_observed=entire_window,
        horizon_observed=horizon_observed,cohort_finalized_early=all_known and not horizon_observed,
        cohort_mature=mature,evidence_used_until_seconds=min(needed,cutoff),
        decision_not_before_seconds=needed if mature else None,
        starts=n,known_terminals_by_horizon=len(known),timely_2xx=len(successes),
        success_fraction=ratio(len(successes),n) if mature else None,
        observed_success_fraction_lower_bound=ratio(len(successes),n),
        failure_or_deadline_miss_fraction=ratio(n-len(successes),n) if mature else None,
        duration_2xx=dict(n=len(durations),mean=ratio(sum(durations),len(durations)),
            p50=quantile(durations,'.5'),p95=quantile(durations,'.95')),
        snapshot_at_bin_end=dict(known_terminals=len(known_at_b),pending_from_cohort=n-len(known_at_b),
            definitive_outcomes=False),
        terminal_ends=len(terminal),terminal_2xx=sum(r['category']=='success_2xx' for r in terminal),
        start_rps=ratio(n,exposure),terminal_rps=ratio(len(terminal),exposure),
        terminal_2xx_rps=ratio(sum(r['category']=='success_2xx' for r in terminal),exposure),
        pending_at_start=len(pa) if cutoff>=a else None,pending_at_end=len(pb) if entire_window else None,
        pending_change=len(pb)-len(pa) if entire_window else None,
        aged_pending_at_end=sum(b-r['start']>3 for r in pb) if entire_window else None,
        conservation_pass=conservation)


def reference(rows,a,b,cutoff):
    r=measure(rows,a,b,cutoff)
    snapshots=[D(len(pending(rows,D(t)))) for t in range(int(a),int(b)) if D(t)<=number(cutoff)]
    r['pending_p95']=quantile(snapshots,'.95')
    r['adequate']=bool(r['cohort_mature'] and r['starts']>=200 and r['duration_2xx']['n']>=200
        and r['success_fraction']>=D('.99') and r['failure_or_deadline_miss_fraction']<=D('.01'))
    return r


def assess_window(rows,attacks,a,b,cutoff,primary,secondary,*,post):
    m=measure(rows,a,b,cutoff)
    refs=[r for r in (primary,secondary) if r['adequate']]
    limits=dict(success_fraction_min=max([D('.99')]+[r['success_fraction']-D('.01') for r in refs]),
        p95_ms_max=min([r['duration_2xx']['p95']*D('1.25') for r in refs],default=None),
        pending_max=max([4]+[int((r['pending_p95']*D('1.25')).to_integral_value(rounding=ROUND_CEILING)) for r in refs]))
    coverage=m['exposure_seconds']/30
    support=m['cohort_mature'] and m['starts']>=200 and coverage>=D('.95')
    latency_support=m['duration_2xx']['n']>=200
    def check(value,predicate):return None if value is None else bool(predicate(value))
    checks=dict(success=check(m['success_fraction'],lambda x:x>=limits['success_fraction_min']),
        conclusions_in_time=check(m['failure_or_deadline_miss_fraction'],lambda x:x<=D('.01')),
        duration=check(m['duration_2xx']['p95'],lambda x:limits['p95_ms_max'] is not None and x<=limits['p95_ms_max']) if latency_support else None,
        pending_quantity=check(m['pending_at_end'],lambda x:x<=limits['pending_max']),
        pending_age=check(m['aged_pending_at_end'],lambda x:x==0),
        pending_growth=check(m['pending_change'],lambda x:x<=2))
    offensive_clear=not pending(attacks,number(b)) if number(cutoff)>=number(b) else None
    primary_checks=dict(checks)
    primary_checks['duration']=check(m['duration_2xx']['p95'],lambda x:primary['duration_2xx']['p95'] is not None and x<=primary['duration_2xx']['p95']*D('1.25')) if latency_support else None
    impaired=bool(support and primary['adequate'] and any(x is False for x in primary_checks.values()))
    secondary_disagreement=bool(support and latency_support and all(x is True for x in primary_checks.values()) and any(x is False for x in checks.values()))
    qualified=bool(support and latency_support and primary['adequate'] and secondary['adequate']
        and all(x is True for x in checks.values()) and (not post or offensive_clear is True))
    return dict(metrics=m,coverage=coverage,outcome_support=bool(support),duration_support=latency_support,
        limits=limits,service_checks=checks,primary_service_checks=primary_checks,secondary_disagreement=secondary_disagreement,offensive_client_pending_cleared=offensive_clear if post else None,
        service_impairment_observed=impaired,qualified=qualified,
        state='compatible' if qualified else 'service_impaired' if impaired else
        'primary_compatible_secondary_disagreement' if secondary_disagreement else
        'offensive_client_pending' if post and offensive_clear is False else 'insufficient_evidence_or_reference')


def service_assessment(rows,attacks,*,cutoff,emission_end,secondary):
    primary=reference(rows,30,150,cutoff)
    p=primary['duration_2xx']['p95'];c=secondary['duration_2xx']['p95']
    pre_ratio=ratio(p,c) if p is not None and c is not None else None
    compatibility=bool(primary['adequate'] and secondary['adequate'] and pre_ratio is not None and D('.8')<=pre_ratio<=D('1.25'))
    active=[assess_window(rows,attacks,a,a+30,cutoff,primary,secondary,post=False) for a in (150,180,210,240)]
    prior=True if any(w['service_impairment_observed'] for w in active) else (
        False if primary['adequate'] and all(w['outcome_support'] and w['duration_support'] and all(x is True for x in w['primary_service_checks'].values()) for w in active) else None)
    post=[];streak=[];first=None; losses=[]
    for a,b in ((270,300),(300,330),(330,360),(360,390)):
        left=max(number(a),number(270),number(emission_end))
        if left>=b:
            post.append(dict(nominal_interval_seconds=[a,b],qualified=False,state='no_post_emission_exposure'))
            streak=[]
            continue
        w=assess_window(rows,attacks,left,b,cutoff,primary,secondary,post=True)
        w['nominal_interval_seconds']=[a,b]
        w['primary_secondary_compatible']=compatibility
        if not compatibility:w.update(qualified=False,state='reference_incompatible')
        streak=streak+[w] if w['qualified'] else []
        if len(streak)>=2:
            growth=streak[-1]['metrics']['pending_at_end']-streak[-2]['metrics']['pending_at_start']
            w['pending_growth_over_confirmation']=growth
            if growth>2:w.update(qualified=False,state='pending_growth_over_confirmation');streak=[]
            elif first is None:
                first=dict(window_end_seconds=D(b),required_evidence_horizon_seconds=D(b)+3,
                    evidence_used_until_seconds=max(x['metrics']['evidence_used_until_seconds'] for x in streak[-2:]),
                    decision_not_before_seconds=max(x['metrics']['decision_not_before_seconds'] for x in streak[-2:]))
        if first is not None and b>first['window_end_seconds'] and not w['qualified']:
            losses.append(dict(bin_end_seconds=b,reason=w['state']))
        post.append(w)
    return dict(scope='service_received_by_started_legitimate_requests',primary_PRE=primary,
        secondary_reference=secondary,reference_compatibility=dict(p95_ratio_PRE_over_C=pre_ratio,
            accepted_ratio=[D('.8'),D('1.25')],compatible=compatibility,
            limitation='Historical C is not contemporaneous or seed-paired; no causal attribution or proof of full scheduled load.'),
        active_windows=active,active_degradation_observed=prior,post_windows=post,
        first_post_compatibility=first,recovery_event=first if prior is True else None,
        state=('recovery_observed' if prior is True else 'post_compatible_no_prior_impairment' if prior is False
               else 'post_compatible_prior_state_unknown') if first else 'not_confirmed',
        last_two_post_windows_qualified=len(streak)>=2,loss_of_qualification_after_confirmation=losses,
        right_censored=first is None,censor_at_seconds=min(D(390),number(cutoff)) if first is None else None)


def generator_evidence(raw,rows,origins):
    phases=[('PRE',30,150),('ACTIVE',150,270),('POST',270,390)]
    rates=[]
    for cls,per_source,count in (('benign',4,4),('attack',4,1)):
        for phase,a,b in phases:
            if cls=='attack' and phase!='ACTIVE':continue
            n=sum(r['traffic_class']==cls and a<=r['start']<b for r in rows)
            rates.append(dict(traffic_class=cls,phase=phase,starts=n,nominal_expected=(b-a)*per_source*count,
                starts_over_nominal_expectation=ratio(n,(b-a)*per_source*count),
                per_origin=[dict(source_id=f"{'normal' if cls=='benign' else 'attack'}_{i+1}",
                    starts=sum(r['traffic_class']==cls and origins[r['request_id']]==f"{'normal' if cls=='benign' else 'attack'}_{i+1}" and a<=r['start']<b for r in rows)) for i in range(count)]))
    items=[json.loads(x) for x in (Path(raw)/'source_artifacts/attack_1/output/journal.jsonl').read_text().splitlines()]
    waiting=[];delays=[];max_pending=0;ambiguous=False;admitted=begun=abandoned=0
    for item in items:
        kind,p=item['kind'],item['payload']
        if kind=='admission':admitted+=1;waiting.append(number(p['elapsed_seconds']));max_pending=max(max_pending,len(waiting))
        elif kind=='request_begin':
            begun+=1
            if len(waiting)==1:delays.append(number(p['elapsed_seconds'])-waiting.pop())
            else:ambiguous=True
        elif kind=='abandoned_admission':abandoned+=1;ambiguous=True
    paired=not ambiguous and not waiting and len(delays)==begun and abandoned==0
    return dict(full_scheduled_load_verified=False,legitimate_opportunity_schedule='not_recorded',
        legitimate_submission_and_queue_delay='not_recorded',nominal_start_adherence=rates,
        attack_admission=dict(admitted=admitted,started=begun,abandoned=abandoned,max_unmatched=max_pending,
            uniquely_paired_in_this_trace=paired,admission_to_begin_ms=dict(n=len(delays),
                p50=quantile([x*1000 for x in delays],'.5') if paired else None,
                p95=quantile([x*1000 for x in delays],'.95') if paired else None) ),
        effect_on_service_validity='Missing scheduling evidence limits load claims; does not invalidate service observations.',
        independent_of_service_qualification=True)


def assess_raw(raw,config,control_raw,control_review):
    result=dict(schema='development-d3-minimal-review/v1',entry_id=config.id,technical_checks=[],service=None,generator=None)
    try:
        life,_,rows=old.reconcile(raw,config)
        gt=old.validate_ground_truth(raw,config,{r['request_id']:r for r in old.csv_rows(Path(raw)/'request_log.csv')},life['run_id'])
        result['technical_checks']=[dict(name='journals_csv_ground_truth',passed=True)]
        result['technical_checks']+=old.collection_checks(raw,life['run_id'])
        cconfig=ExperimentConfig.load(Path(control_raw)/'effective_config.json')
        if any(json.loads(config.to_json())[k]!=json.loads(cconfig.to_json())[k] for k in COMPATIBLE_FIELDS):
            raise ValueError('Historical C configuration mismatch')
        if not control_review['classification']['control_accepted']:raise ValueError('Historical C not accepted')
        clife,_,crows=old.reconcile(control_raw,cconfig)
        cbenign=[r for r in crows if r['traffic_class']=='benign']
        secondary=reference(cbenign,30,390,clife['cutoff'])
        benign=[r for r in rows if r['traffic_class']=='benign'];attack=[r for r in rows if r['traffic_class']=='attack']
        emission=gt['actual_emission_intervals'][0][1]
        result.update(lifecycle=life,ground_truth=gt,resources=old.resource_summary(raw),
            service=service_assessment(benign,attack,cutoff=life['cutoff'],emission_end=emission,secondary=secondary),
            generator=generator_evidence(raw,rows,life['origins']))
        result['class_phase_service']=summarize(Path(raw)/'request_log.csv',old.phase_plan(life['run_id'],life['cutoff']),as_of=life['cutoff'])
    except (OSError,ValueError,KeyError,TypeError) as exc:
        result['technical_checks'].append(dict(name='processing_or_collection_failure',passed=False,evidence=str(exc)))
    technical=bool(result['service']) and all(c['passed'] for c in result['technical_checks'])
    result['classification']=dict(technical_integrity=technical,service_observation_valid=technical,
        service_state=result['service']['state'] if technical else 'unassessable_collection',
        full_scheduled_load_verified=False,continued_execution_authorized=False)
    if not technical and result['service']:
        result['service']['conditional_first_post_compatibility']=result['service']['first_post_compatibility']
        result['service'].update(first_post_compatibility=None,recovery_event=None,state='unassessable_collection',right_censored=False)
    result['publication']=dict(evaluation_published_at_utc=None,offline_only=True,
        semantics='Bin end is a window label; horizon and evidence used are separate. Publication occurs after collection and audit.')
    return result


def review_entry(manifest=DEFAULT_MANIFEST):
    validate_plan(manifest,check_outputs=False);plan=read(manifest);e=plan['entries'][0]
    for key in ('analysis','validation','review'):
        if (ROOT/e['outputs'][key]).exists():raise FileExistsError('No review overwrite/retry')
    control=verify_reference(plan);raw=ROOT/e['outputs']['raw']
    before={str(p):sha(p) for p in raw.rglob('*') if p.is_file()}
    report=assess_raw(raw,ExperimentConfig.load(ROOT/e['config']),ROOT/plan['secondary_reference']['raw'],control)
    report['review_path']=e['outputs']['review']
    report['authority']=dict(manifest_sha256=sha(manifest),config_sha256=e['config_sha256'])
    try:
        operations=old.operation_checks(plan,e,manifest)
        report['operations']=operations
        report['technical_checks'].append(dict(name='linked_operations_cleanup',passed=operations['cleanup_verified']))
        if read(raw/'effective_config.json')!=e['effective_configuration']:raise ValueError('Effective configuration mismatch')
    except (OSError,ValueError,KeyError) as exc:
        report['technical_checks'].append(dict(name='operation_binding_or_configuration',passed=False,evidence=str(exc)))
    from experiments.validate_dataset import validate_dataset
    from experiments.export_dataset import placement
    dataset=ROOT/e['outputs']['dataset'];validation=validate_dataset(dataset)
    mismatches=[str(Path(p).relative_to(raw)) for p,h in before.items()
        if not (dataset/placement(Path(p).relative_to(raw))[0]).is_file() or sha(dataset/placement(Path(p).relative_to(raw))[0])!=h]
    report['dataset_validation']={k:validation[k] for k in ('dataset_valid','analysis_eligible','structural_valid','summary')}
    report['technical_checks'].append(dict(name='dataset_correspondence',passed=validation['dataset_valid'] and not mismatches,evidence=mismatches))
    if not all(c['passed'] for c in report['technical_checks']):
        report['classification'].update(technical_integrity=False,service_observation_valid=False,service_state='unassessable_collection')
    if not report['classification']['technical_integrity'] and report['service']:
        report['service']['conditional_first_post_compatibility']=report['service']['first_post_compatibility']
        report['service'].update(first_post_compatibility=None,recovery_event=None,state='unassessable_collection',right_censored=False)
    report['preserved_raw_hashes']=before
    report['publication']['evaluation_published_at_utc']=datetime.now(timezone.utc).isoformat()
    report['publication']['evaluation_published_at_epoch']=datetime.now(timezone.utc).timestamp()
    if before!={str(p):sha(p) for p in raw.rglob('*') if p.is_file()}:raise ValueError('Raw changed during audit')
    put(ROOT/e['outputs']['validation'],validation)
    put(ROOT/e['outputs']['analysis'],dict(service=report['service'],generator=report['generator'],publication=report['publication']))
    put(ROOT/e['outputs']['review'],report)
    return report


def compact(report):
    return dict(entry=report['entry_id'],technical_integrity=report['classification']['technical_integrity'],
        service=report['classification']['service_state'],full_scheduled_load_verified=False,
        review=report.get('review_path'),review_only=True,continued_execution_authorized=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,default=DEFAULT_MANIFEST)
    sub=p.add_subparsers(dest='action',required=True);sub.add_parser('validate-plan');sub.add_parser('review')
    args=p.parse_args()
    if args.action=='validate-plan':
        r=validate_plan(args.manifest);print(json.dumps({k:r[k] for k in ('entry','configurations','seed','docker_accessed','experiments_executed')}))
    else:print(json.dumps(compact(review_entry(args.manifest))))


if __name__=='__main__':main()
