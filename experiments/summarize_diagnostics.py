"""Descriptive diagnostics, distinct from feature extraction/detector evaluation."""
import argparse
from collections import Counter,defaultdict
import csv
import json
import math
from pathlib import Path
import statistics


def read(path):return json.loads(Path(path).read_text())
def records(path):
    with Path(path).open() as stream:return [json.loads(line) for line in stream if line.strip()]
def csv_rows(path):
    with Path(path).open() as stream:return list(csv.DictReader(stream))


def stats(values):
    values=sorted(values)
    return dict(n=len(values),mean=statistics.mean(values) if values else None,
        minimum=values[0] if values else None,maximum=values[-1] if values else None,
        p50=statistics.median(values) if values else None,
        p95=values[max(0,math.ceil(.95*len(values))-1)] if values else None)


def count_windows(times,origin,duration):
    # Include all complete and final partial bins; tail is reported separately.
    counts=Counter(int(t-origin) for t in times if 0<=t-origin<duration)
    values=[counts[i] for i in range(math.ceil(duration))]
    mean=statistics.mean(values) if values else None
    variance=statistics.variance(values) if len(values)>1 else None
    return dict(counts=values,mean=mean,sample_variance=variance,
                variance_to_mean=variance/mean if variance is not None and mean else None,
                partial_final_bin=duration!=int(duration))


def summarize(raw):
    raw=Path(raw);config=read(raw/'effective_config.json');status=read(raw/'run_status.json')
    origin=status['experiment_start_monotonic'];duration=config['duration_seconds']
    result=dict(schema_version=1,run_id=status['run_id'],configuration=config,
        collection_status={k:status.get(k) for k in ('status','producers_drained','errors')},
        observation='Descriptive finite-run diagnostics; no statistical approval test',
        diagnostic_enabled=config.get('diagnostics',{}).get('enabled',False),sources=[],victim=None,
        scientific_observations={},reliability_errors=[])
    requests=csv_rows(raw/'request_log.csv')
    result['scientific_observations']=dict(starts=len(requests),starts_in_plan=sum(0<=float(r['elapsed_seconds'])<duration for r in requests),
        completions=sum(bool(r['end_elapsed_seconds']) for r in requests),
        failures=sum(r['outcome'] in ('transport_error','client_error','http_error') for r in requests),
        duration_ms=stats([float(r['duration_ms']) for r in requests if r['duration_ms']]),
        cpu_docker_percent=stats([float(r['average_cpu_percent']) for r in csv_rows(raw/'simulation_metrics.csv') if r['active_containers_names']]))
    if not result['diagnostic_enabled']:return result
    metadata=read(raw/'diagnostics/metadata.json')
    result['metadata']=metadata
    for source in read(raw/'source_inventory.json'):
        folder=raw/'source_artifacts'/source['source_id']/'output/diagnostics'
        summary=read(folder/'events.summary.json');events=records(folder/'events.jsonl')
        if not summary['complete'] or len(events)!=summary['written']:
            result['reliability_errors'].append(source['source_id']+': incomplete diagnostic log')
        grouped=defaultdict(dict)
        for e in events:
            if e.get('attempt_id'):
                if e['kind'] in grouped[e['attempt_id']]:result['reliability_errors'].append('duplicate attempt event')
                grouped[e['attempt_id']][e['kind']]=e
        counts=Counter(e['kind'] for e in events)
        local_requests=csv_rows(raw/'source_artifacts'/source['source_id']/'output/local_requests.csv')
        starts_by_id={e['request_id']:e for e in events if e['kind']=='http_started'}
        ends_by_id={e['request_id']:e for e in events if e['kind']=='http_finished'}
        if set(starts_by_id)!={r['request_id'] for r in local_requests}:
            result['reliability_errors'].append('diagnostic/scientific request starts differ')
        if set(ends_by_id)!={r['request_id'] for r in local_requests if r['end_elapsed_seconds']}:
            result['reliability_errors'].append('diagnostic/scientific request completions differ')
        for r in local_requests:
            if r['request_id'] in starts_by_id and starts_by_id[r['request_id']]['elapsed_seconds']!=float(r['elapsed_seconds']):
                result['reliability_errors'].append('diagnostic/scientific start time differs')
            if r['request_id'] in ends_by_id and ends_by_id[r['request_id']]['elapsed_seconds']!=float(r['end_elapsed_seconds']):
                result['reliability_errors'].append('diagnostic/scientific completion time differs')
        delays=defaultdict(list)
        for attempt in grouped.values():
            for label,a,b in [('plan_to_submit','planned','submitted'),('submit_to_task','submitted','task_started'),
                              ('submit_to_http','submitted','http_started'),('plan_to_http','planned','http_started')]:
                if a in attempt and b in attempt:
                    begin=attempt[a]['planned_at'] if a=='planned' else attempt[a]['at']
                    delta=attempt[b]['at']-begin
                    delays[label].append(delta)
                    if delta<0:result['reliability_errors'].append('negative '+label)
        planned=[e for e in events if e['kind']=='planned']
        submitted=[e for e in events if e['kind']=='submitted']
        starts=[e for e in events if e['kind']=='http_started']
        cancellations=[e for e in events if e['kind']=='cancelled']
        closure=next((e for e in events if e['kind']=='source_closed'),None)
        counters=closure['counts'] if closure else None
        if counters is None:result['reliability_errors'].append('source closure counters unavailable')
        elif any(counters[k]!=counts[k] for k in counters):result['reliability_errors'].append('source counter mismatch')
        if closure is not None and not (closure.get('drained') and closure.get('logger_complete')):
            result['reliability_errors'].append('source closure incomplete')
        active=0;peak=0
        for e in sorted((e for e in events if e['kind'] in ('http_started','http_finished')),key=lambda e:(e['at'],e['kind']!='http_started')):
            active+=1 if e['kind']=='http_started' else -1;peak=max(peak,active)
            if active<0:result['reliability_errors'].append('negative observed HTTP concurrency')
        pending_peak=max((e['counts']['submitted']-e['counts']['task_started']-e['counts']['cancelled']-e['counts']['rejected']
            for e in events if 'counts' in e),default=0)
        result['sources'].append(dict(source_id=source['source_id'],writer=summary,counts=dict(counts),counters=counters,closure=closure,
            nominal_rps=config['normal_traffic']['rate'],theoretical_exponential_mean_seconds=1/config['normal_traffic']['rate'] if config['normal_traffic']['rate'] else None,
            planned_within_plan=sum(0<=p['planned_at']-origin<duration for p in planned),
            planned_after_plan=sum(p['planned_at']-origin>=duration for p in planned),
            planned_not_submitted_in_plan=sum('planned' in a and 0<=a['planned']['planned_at']-origin<duration and 'submitted' not in a for a in grouped.values()),
            submitted_not_started=sum('submitted' in a and 'http_started' not in a for a in grouped.values()),
            unresolved_tasks=sum('submitted' in a and not any(k in a for k in ('task_started','cancelled','rejected')) for a in grouped.values()),
            task_failures=sum(e['kind']=='task_finished' and bool(e.get('error_type')) for e in events),
            cancelled=len(cancellations),http_active_at_end=active,http_peak=peak,
            submitted_not_task_started_peak=pending_peak,
            delays_seconds={k:stats(v) for k,v in delays.items()},
            sampled_intervals_seconds=stats([p['sampled_interval'] for p in planned]),
            empirical_intervals_seconds=[p['sampled_interval'] for p in planned],
            counts_per_second=dict(planned=count_windows([p['planned_at'] for p in planned],origin,duration),
                submitted=count_windows([p['at'] for p in submitted],origin,duration),
                http_started=count_windows([p['at'] for p in starts],origin,duration)),
            first_dispatch_unplanned=sum(e.get('planned_at') is None for e in submitted)))
    folder=raw/'diagnostics/victim'
    writer=read(folder/'events.summary.json');events=records(folder/'events.jsonl')
    if not writer['complete'] or len(events)!=writer['written']:result['reliability_errors'].append('victim diagnostic log incomplete')
    expected={r['request_id'] for r in requests}
    starts=[e for e in events if e['kind']=='handler_started' and e.get('request_id') in expected]
    ends=[e for e in events if e['kind']=='handler_finished' and e.get('request_id') in expected]
    known=Counter(e['request_id'] for e in ends)
    begun=Counter(e['request_id'] for e in starts)
    if any(n!=1 for n in begun.values()) or set(known)-set(begun):
        result['reliability_errors'].append('handler start/end identity inconsistent')
    if any(n!=1 for n in known.values()):result['reliability_errors'].append('duplicate completed handler ID')
    durations=defaultdict(list)
    namespace=writer['clock']['time_namespace']
    for e in ends:
        same_clock=e.get('worker_clock',{}).get('time_namespace')==namespace
        for name,a,b in [('handler_to_submit','handler_started_at','work_submitted_at'),
            ('work_wait','work_submitted_at','work_started_at'),('work_wall','work_started_at','work_finished_at'),
            ('work_result_transport','work_finished_at','work_result_observed_at'),
            ('post_work_handler','work_finished_at','handler_finished_at'),('handler_wall','handler_started_at','handler_finished_at')]:
            if a in e and b in e and (same_clock or name in ('handler_to_submit','handler_wall')):
                delta=e[b]-e[a];durations[name].append(delta)
                if delta<0:result['reliability_errors'].append('negative victim '+name)
        if 'work_cpu_seconds' in e:durations['work_process_cpu'].append(e['work_cpu_seconds'])
        if 'worker_clock' in e and not same_clock:result['reliability_errors'].append('worker/handler clock namespace differs')
    result['victim']=dict(writer=writer,handler_starts=len(starts),handler_finishes=len(ends),
        handler_errors=sum(bool(e['error_type']) for e in ends),matched_request_ids=len(known),
        client_attempts_without_completed_handler=sorted(expected-known.keys()),
        unattributed_setup_handlers=sum(e['kind']=='handler_finished' and e.get('request_id') not in expected for e in events),
        peak_handlers=max((e['active_handlers_at_start'] for e in starts),default=0),
        durations_seconds={k:stats(v) for k,v in durations.items()},
        handler_start_windows=count_windows([e['at'] for e in starts],origin,duration),
        incomplete_handlers_observed=len(starts)-len(ends))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=summarize(args.raw)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    if result['reliability_errors']:raise RuntimeError('diagnostic reliability checks failed; see summary')


if __name__=='__main__':main()
