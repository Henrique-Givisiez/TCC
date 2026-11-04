"""Exploratory descriptive analysis; never a detector input or acceptance policy."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics

from experiments.summarize_diagnostics import summarize, records, csv_rows, stats, read


def describe(values):
    values=list(values)
    return dict(stats(values),sample_sd=statistics.stdev(values) if len(values)>1 else None)


def interval_sweep(intervals, start, end):
    """Half-open intervals; ends precede starts on equal timestamps."""
    events=[]
    for a,b in intervals:
        if b<a:raise ValueError('negative interval')
        a,b=max(a,start),min(b,end)
        if b>a:events.extend([(a,1),(b,-1)])
    active=peak=0;area=0.;previous=start
    for at,delta in sorted(events):
        area+=(at-previous)*active
        active+=delta;peak=max(peak,active);previous=at
        if active<0:raise ValueError('negative interval concurrency')
    return dict(peak=peak,mean_occupancy=area/(end-start),observed_interval_count=len(events)//2)


def request_phases(requests, duration):
    starts=[r for r in requests if 0<=float(r['elapsed_seconds'])<duration]
    completed=[r for r in requests if r['end_elapsed_seconds']]
    return dict(starts_in_plan=len(starts),starts_tail=sum(float(r['elapsed_seconds'])>=duration for r in requests),
        completions_in_plan=sum(0<=float(r['end_elapsed_seconds'])<duration for r in completed),
        completions_tail=sum(float(r['end_elapsed_seconds'])>=duration for r in completed),
        cohort_completed=sum(bool(r['end_elapsed_seconds']) for r in starts),
        cohort_completed_after_plan=sum(bool(r['end_elapsed_seconds']) and float(r['end_elapsed_seconds'])>=duration for r in starts),
        unfinished=sum(not r['end_elapsed_seconds'] for r in requests),
        started_rps=len(starts)/duration,
        completed_rps_in_plan=sum(0<=float(r['end_elapsed_seconds'])<duration for r in completed)/duration)


def analyze(raw, diagnostic=None):
    raw=Path(raw);diagnostic=diagnostic or summarize(raw)
    cfg=read(raw/'effective_config.json');status=read(raw/'run_status.json')
    duration=cfg['duration_seconds'];origin=status['experiment_start_monotonic']
    requests=csv_rows(raw/'request_log.csv');metrics=csv_rows(raw/'simulation_metrics.csv')
    phases=request_phases(requests,duration)
    failures=[r for r in requests if r['outcome'] in ('transport_error','client_error','http_error')]
    result=dict(run_id=status['run_id'],name=cfg['id'],configuration=cfg,phases=phases,
        nominal_rps=cfg['normal_traffic']['clients']*cfg['normal_traffic']['rate'],
        sources=cfg['normal_traffic']['clients'],diagnostics_enabled=diagnostic['diagnostic_enabled'],
        failures=len(failures),failure_fraction=len(failures)/len(requests) if requests else None,
        outcomes=dict(Counter(r['outcome'] for r in requests)),
        error_types=dict(Counter(r['error_type'] for r in failures)),
        http_duration_ms=describe(float(r['duration_ms']) for r in requests if r['duration_ms']),
        cpu_docker_percent=describe(float(r['average_cpu_percent']) for r in metrics if r['active_containers_names']),
        http_concurrency=interval_sweep([(float(r['elapsed_seconds']),float(r['end_elapsed_seconds']))
            for r in requests if r['end_elapsed_seconds']],0,duration),
        first_http_start=min((float(r['elapsed_seconds']) for r in requests),default=None),
        last_http_completion=max((float(r['end_elapsed_seconds']) for r in requests if r['end_elapsed_seconds']),default=None),
        generators=None,victim=None,bins=[],reliability_errors=diagnostic['reliability_errors'])
    bins=[dict(second=i,starts=0,completions=0,http_durations=[],cpu=[],work_wait=[],work_wall=[],
               pending_by_source={}) for i in range(int(duration))]
    for r in requests:
        i=int(float(r['elapsed_seconds']))
        if 0<=i<len(bins):bins[i]['starts']+=1
        if r['end_elapsed_seconds']:
            i=int(float(r['end_elapsed_seconds']))
            if 0<=i<len(bins):
                bins[i]['completions']+=1
                if r['duration_ms']:bins[i]['http_durations'].append(float(r['duration_ms']))
    for r in metrics:
        i=int(float(r['elapsed_seconds']))
        if 0<=i<len(bins) and r['active_containers_names']:bins[i]['cpu'].append(float(r['average_cpu_percent']))
    if diagnostic['diagnostic_enabled']:
        if not read(raw/'source_artifacts/clock_validation.json')['comparable']:
            raise ValueError('source clock comparability required for origin attribution')
        if not read(raw/'diagnostics/victim_clock_validation.json')['comparable']:
            raise ValueError('victim clock comparability required for origin attribution')
        delays=defaultdict(list);submitted=task_started=task_finished=cancelled=rejected=planned=planned_tail=unresolved=0
        per_source=[]
        for source in diagnostic['sources']:
            events=records(raw/'source_artifacts'/source['source_id']/'output/diagnostics/events.jsonl')
            grouped=defaultdict(dict)
            for e in events:
                if e.get('attempt_id'):grouped[e['attempt_id']][e['kind']]=e
                i=int(e['at']-origin)
                if 0<=i<len(bins) and 'counts' in e and e['kind']!='source_closed':
                    c=e['counts'];pending=c['submitted']-c['task_started']-c['cancelled']-c['rejected']
                    bins[i]['pending_by_source'][source['source_id']]=max(pending,bins[i]['pending_by_source'].get(source['source_id'],0))
            for own in grouped.values():
                for label,a,b in [('plan_to_submit','planned','submitted'),('submit_to_task','submitted','task_started'),
                                  ('task_to_http','task_started','http_started')]:
                    if a in own and b in own:
                        at=own[a]['planned_at'] if a=='planned' else own[a]['at']
                        delta=own[b]['at']-at
                        if delta<0:raise ValueError('negative source delay')
                        delays[label].append(delta*1000)
            c=source['counters'];submitted+=c['submitted'];task_started+=c['task_started'];task_finished+=c['task_finished']
            cancelled+=c['cancelled'];rejected+=c['rejected'];planned+=source['planned_within_plan'];planned_tail+=source['planned_after_plan']
            unresolved+=source['unresolved_tasks']
            per_source.append(dict(source_id=source['source_id'],counters=c,
                pending_difference_peak=source['submitted_not_task_started_peak'],
                active_http_end=source['http_active_at_end'],http_peak=source['http_peak'],
                planned_not_submitted=source['planned_not_submitted_in_plan']))
        result['generators']=dict(submitted_total=submitted,task_started_total=task_started,task_finished_total=task_finished,
            cancelled=cancelled,rejected=rejected,planned_in_plan=planned,planned_tail=planned_tail,
            unresolved=unresolved,delays_ms={k:describe(v) for k,v in delays.items()},per_source=per_source,
            submitted_in_plan=sum(sum(s['counts_per_second']['submitted']['counts']) for s in diagnostic['sources']),
            first_unplanned=sum(s['first_dispatch_unplanned'] for s in diagnostic['sources']))
        expected={r['request_id'] for r in requests}
        ended=[e for e in records(raw/'diagnostics/victim/events.jsonl') if e['kind']=='handler_finished' and e.get('request_id') in expected]
        parent_namespace=read(raw/'diagnostics/victim/events.summary.json')['clock']['time_namespace']
        intervals=[];cpu=[];work_wall=[];work_wait=[]
        for e in ended:
            if e.get('worker_clock',{}).get('time_namespace')!=parent_namespace:
                if 'work_started_at' in e:raise ValueError('incomparable worker clock')
                continue
            a,b=e['work_started_at'],e['work_finished_at'];intervals.append((a-origin,b-origin))
            work_wall.append((b-a)*1000);work_wait.append((a-e['work_submitted_at'])*1000)
            if 'work_cpu_seconds' in e:cpu.append(e['work_cpu_seconds']*1000)
            i=int(e['handler_finished_at']-origin)
            if 0<=i<len(bins):
                bins[i]['work_wait'].append((a-e['work_submitted_at'])*1000)
                bins[i]['work_wall'].append((b-a)*1000)
        result['victim']=dict(handler_starts=diagnostic['victim']['handler_starts'],handler_finishes=len(ended),
            handler_errors=diagnostic['victim']['handler_errors'],handler_peak=diagnostic['victim']['peak_handlers'],
            unmatched_client_ids=diagnostic['victim']['client_attempts_without_completed_handler'],
            work_wait_ms=describe(work_wait),work_wall_ms=describe(work_wall),work_cpu_ms=describe(cpu),
            work_concurrency=interval_sweep(intervals,0,duration),
            work_complete_intervals=len(intervals),handler_wall_seconds=diagnostic['victim']['durations_seconds'].get('handler_wall'))
    for b in bins:
        result['bins'].append(dict(second=b['second'],starts=b['starts'],completions=b['completions'],
            http_duration_ms=describe(b['http_durations']),cpu_docker_percent=describe(b['cpu']),
            work_wait_ms=describe(b['work_wait']),work_wall_ms=describe(b['work_wall']),
            pending_difference_peak=sum(b['pending_by_source'].values()) if result['generators'] else None))
    reasons=[]
    if result['reliability_errors']:reasons.append('diagnostic_integrity')
    if result['failure_fraction'] is not None and result['failure_fraction']>.01:reasons.append('failure_fraction_above_1pct')
    if result['http_duration_ms']['p95'] is not None and result['http_duration_ms']['p95']>500:reasons.append('http_p95_above_500ms')
    if result['victim'] and result['victim']['work_wait_ms']['p95'] is not None and result['victim']['work_wait_ms']['p95']>100:
        reasons.append('worker_wait_p95_above_100ms')
    tail=[b['pending_difference_peak'] for b in result['bins'][-3:]]
    if len(tail)==3 and all(v is not None and v>64 for v in tail) and tail[0]<tail[1]<tail[2]:reasons.append('persistent_pending_growth')
    if result['generators'] and result['generators']['unresolved']:reasons.append('unresolved_tasks')
    result['progression']=dict(allowed=not reasons,reasons=reasons,
        role='exploratory operational guard, not scientific detector criterion')
    return result
