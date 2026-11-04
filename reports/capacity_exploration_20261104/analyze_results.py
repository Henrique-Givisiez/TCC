"""Offline descriptive tables/figures for this finite exploratory campaign."""
import csv
import json
from pathlib import Path
import statistics

from experiments.capacity_analysis import describe
from experiments.summarize_diagnostics import records,read

ROOT=Path('experiment_results/capacity-exploration-20261104')
OUT=Path('reports/capacity_exploration_20261104')


def temporal_delays(folder,result):
    duration=result['configuration']['duration_seconds']
    origin=read(folder/'raw/run_status.json')['experiment_start_monotonic']
    values=[dict(plan_to_submit=[],submit_to_task=[],task_to_http=[]) for _ in range(int(duration))]
    if result['diagnostics_enabled']:
        for source in read(folder/'raw/source_inventory.json'):
            events=records(folder/'raw/source_artifacts'/source['source_id']/'output/diagnostics/events.jsonl')
            grouped={}
            for e in events:
                if e.get('attempt_id'):grouped.setdefault(e['attempt_id'],{})[e['kind']]=e
            for own in grouped.values():
                for name,a,b in [('plan_to_submit','planned','submitted'),('submit_to_task','submitted','task_started'),
                                 ('task_to_http','task_started','http_started')]:
                    if a in own and b in own:
                        elapsed=own[b]['at']-origin
                        if 0<=elapsed<duration:
                            at=own[a]['planned_at'] if a=='planned' else own[a]['at']
                            delta=(own[b]['at']-at)*1000
                            if delta<0:raise ValueError('negative local diagnostic duration')
                            values[int(elapsed)][name].append(delta)
    return [{name:describe(v) for name,v in row.items()} for row in values]


def flatten(folder):
    r=read(folder/'capacity_summary.json');execution=read(folder/'execution_result.json')
    v=r['victim'];g=r['generators'];cfg=r['configuration'];ph=r['phases']
    watch=records(folder/'watchdog.jsonl');generation=[s for s in watch if s['phase']=='generation']
    cpu=[s['host_busy_percent'] for s in generation if s['host_busy_percent'] is not None]
    source_mem=[sum(c['memory_usage_bytes'] for c in s['containers'] if c['role']=='source')/1024**2 for s in watch]
    victim_mem=[c['memory_usage_bytes']/1024**2 for s in watch for c in s['containers'] if c['role']=='victim']
    origin=read(folder/'raw/run_status.json')['experiment_start_monotonic']
    closure=[]
    for source in read(folder/'raw/source_inventory.json'):
        own=records(folder/'raw/source_artifacts'/source['source_id']/'output/journal.jsonl')
        closure.extend(e['payload']['elapsed_seconds'] for e in own if e['kind']=='source_closed')
    capture=read(folder/'raw/traffic_capture.csv.capture.json')
    capture_stop=capture['timestamps']['process_exit_observed']['monotonic_seconds']-origin
    verification=read(folder/'verification/verification.json')
    assert verification['accepted'] and not r['reliability_errors'],folder
    network=[]
    with (folder/'verification/features/timeseries/network.csv').open() as stream:network=list(csv.DictReader(stream))
    packets=sum(int(row['ingress_packet_count']) for row in network)
    payload=sum(int(row['ingress_tcp_payload_length_sum_bytes']) for row in network)
    row=dict(name=folder.name,run_id=r['run_id'],scenario=folder.name.split('_')[0],
        mode='ON' if r['diagnostics_enabled'] else 'OFF',
        repetition=folder.name.split('_')[-1] if folder.name.startswith('C') else 'pilot',
        status=execution['status'],sources=r['sources'],rps_per_source=cfg['normal_traffic']['rate'],
        nominal_rps=r['nominal_rps'],duration_seconds=cfg['duration_seconds'],seed=cfg['seed'],
        starts_in_plan=ph['starts_in_plan'],starts_tail=ph['starts_tail'],started_rps=ph['started_rps'],
        completions_in_plan=ph['completions_in_plan'],completions_tail=ph['completions_tail'],
        completed_rps_in_plan=ph['completed_rps_in_plan'],cohort_completed_after_plan=ph['cohort_completed_after_plan'],
        unfinished=ph['unfinished'],failures=r['failures'],cancelled=g['cancelled'] if g else None,
        rejected=g['rejected'] if g else None,unresolved=g['unresolved'] if g else None,
        planned_in_plan=g['planned_in_plan'] if g else None,planned_after_plan=g['planned_tail'] if g else None,
        first_unplanned=g['first_unplanned'] if g else None,
        submitted_in_plan=g['submitted_in_plan'] if g else None,submitted_total=g['submitted_total'] if g else None,
        task_started_total=g['task_started_total'] if g else None,task_finished_total=g['task_finished_total'] if g else None,
        http_concurrency_peak=r['http_concurrency']['peak'],http_concurrency_mean=r['http_concurrency']['mean_occupancy'],
        pending_difference_peak_per_source=max((s['pending_difference_peak'] for s in g['per_source']),default=0) if g else None,
        handler_starts=v['handler_starts'] if v else None,handler_finishes=v['handler_finishes'] if v else None,
        handler_peak=v['handler_peak'] if v else None,unmatched_handlers=len(v['unmatched_client_ids']) if v else None,
        work_concurrency_peak=v['work_concurrency']['peak'] if v else None,
        work_mean_occupied_workers=v['work_concurrency']['mean_occupancy'] if v else None,
        host_busy_mean_pct=statistics.mean(cpu) if cpu else None,host_busy_max_pct=max(cpu) if cpu else None,
        host_available_min_mib=min(s['available_bytes'] for s in watch)/1024**2,
        victim_memory_peak_mib=max(victim_mem,default=0),sources_memory_peak_sum_mib=max(source_mem,default=0),
        generation_watch_samples=len(generation),
        preparation_observed_seconds=origin-watch[0]['monotonic'],first_http_start_elapsed=r['first_http_start'],
        last_http_completion_elapsed=r['last_http_completion'],
        last_source_closed_elapsed=max(closure,default=None),capture_exit_elapsed=capture_stop,
        runner_with_export_seconds=execution['observer_elapsed_seconds'],
        ingress_packets_total=packets,ingress_payload_bytes_total=payload,
        tcpdump_csv_drops=capture['capture_counters']['packets_dropped_by_kernel'],
        tcpdump_pcap_drops=read(folder/'raw/source_artifacts/traffic_capture.pcap.capture.json')['capture_counters']['packets_dropped_by_kernel'],
        diagnostics_reliable=True if v else None,all_five_features_verified=verification['accepted'],
        progression_allowed=r['progression']['allowed'])
    summaries={'http_ms':r['http_duration_ms'],'cpu_docker_pct':r['cpu_docker_percent']}
    if v:
        summaries.update(work_wait_ms=v['work_wait_ms'],work_wall_ms=v['work_wall_ms'],work_cpu_ms=v['work_cpu_ms'])
        diagnostic=read(folder/'diagnostic_summary.json')
        for name,summary in diagnostic['victim']['durations_seconds'].items():
            converted={key:(value*1000 if value is not None else None) for key,value in summary.items()}
            converted['sample_sd']=None  # summarize_diagnostics does not retain raw latency samples
            summaries[name+'_ms']=converted
    if g:summaries.update({name+'_ms':value for name,value in g['delays_ms'].items()})
    for prefix,summary in summaries.items():
        for key in ('n','mean','p50','p95','maximum','sample_sd'):row[prefix+'_'+key]=summary[key]
    delays=temporal_delays(folder,r)
    bins=[]
    for b,extra in zip(r['bins'],delays):
        entry=dict(name=folder.name,second=b['second'],starts=b['starts'],completions=b['completions'],
            pending_difference_peak_envelope=b['pending_difference_peak'])
        for name in ('http_duration_ms','cpu_docker_percent','work_wait_ms','work_wall_ms'):
            for key in ('n','mean','p50','p95','maximum'):entry[name+'_'+key]=b[name][key]
        for name,summary in extra.items():
            for key in ('n','mean','p95','maximum'):entry[name+'_ms_'+key]=summary[key]
        bins.append(entry)
    return row,bins


def write_csv(path,rows):
    names=list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=names);writer.writeheader();writer.writerows(rows)


def collect():
    rows=[];bins=[];incomplete=[]
    for folder in sorted(ROOT.iterdir()):
        if not folder.is_dir():continue
        if not (folder/'capacity_summary.json').exists():
            if (folder/'preflight.json').exists():incomplete.append(dict(name=folder.name,preflight=read(folder/'preflight.json'),
                execution=read(folder/'execution_result.json') if (folder/'execution_result.json').exists() else None))
            continue
        row,series=flatten(folder);rows.append(row);bins.extend(series)
    write_csv(OUT/'runs.csv',rows);write_csv(OUT/'temporal_bins.csv',bins)
    (OUT/'runs.json').write_text(json.dumps(rows,indent=2)+'\n')
    (OUT/'incomplete_runs.json').write_text(json.dumps(incomplete,indent=2)+'\n')
    paired=[]
    for scenario in ('C2','C3'):
        for rep in ('r1','r2'):
            on=next((r for r in rows if r['name']==scenario+'_ON_'+rep),None)
            off=next((r for r in rows if r['name']==scenario+'_OFF_'+rep),None)
            if on is None or off is None:continue
            paired.append(dict(scenario=scenario,repetition=rep,nominal_rps=on['nominal_rps'],
                on_run_id=on['run_id'],off_run_id=off['run_id'],
                **{key+'_on_minus_off':on[key]-off[key] for key in ('started_rps','completed_rps_in_plan','http_ms_mean','http_ms_p95','cpu_docker_pct_mean',
                    'ingress_packets_total','ingress_payload_bytes_total')}))
    write_csv(OUT/'instrumentation_pairs.csv',paired)
    return rows,bins,paired


def plot_results(rows,bins,paired):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    main=[r for r in rows if r['name'].startswith('C') and r['mode']=='ON']
    colors={2:'#1769aa',4:'#d17c00'}
    fig,axes=plt.subplots(2,3,figsize=(14,8),constrained_layout=True)
    ax=axes[0,0]
    legend_sources=set()
    for r in main:
        label=f"{r['sources']} fontes" if r['sources'] not in legend_sources else None
        legend_sources.add(r['sources'])
        ax.scatter(r['nominal_rps'],r['started_rps'],color=colors[r['sources']],marker='o' if r['sources']==2 else 's',label=label)
    ax.plot([0,140],[0,140],'--',color='gray',linewidth=1);ax.set(xlabel='Taxa nominal agregada (req/s)',ylabel='Inícios HTTP / s',title='Taxa nominal e observada')
    ax.legend()
    for axis,key,title,ylabel in [
        (axes[0,1],'http_ms_p95','Duração HTTP p95','ms'),
        (axes[0,2],'work_wait_ms_p95','Espera pelo worker p95','ms'),
        (axes[1,0],'cpu_docker_pct_mean','CPU média do contêiner vítima','% Docker'),
        (axes[1,1],'host_busy_max_pct','CPU máxima observada no host','% host ocupado')]:
        for r in main:
            val=r.get(key)
            if val is not None:axis.scatter(r['nominal_rps'],val,color=colors[r['sources']],marker='o' if r['sources']==2 else 's')
        axis.set(xlabel='Taxa nominal agregada (req/s)',ylabel=ylabel,title=title)
    ax=axes[1,2]
    for p in paired:ax.scatter(p['nominal_rps'],p['http_ms_mean_on_minus_off'],label=f"{p['scenario']} {p['repetition']}")
    ax.axhline(0,color='gray',linewidth=1);ax.set_yscale('symlog',linthresh=1);ax.set(xlabel='Taxa nominal agregada (req/s)',ylabel='Diferença ON − OFF (ms, escala symlog)',title='Duração HTTP média e diagnóstico')
    if paired:ax.legend(fontsize=8)
    fig.suptitle('Caracterização exploratória; pontos são execuções individuais, sem intervalo inferencial')
    fig.savefig(OUT/'capacity_overview.png',dpi=160);fig.savefig(OUT/'capacity_overview.svg');plt.close(fig)

    compare=[r for r in main if r['name'] in ('C2_ON_r1','C4_ON_r1','C3_ON_r1','C5_ON_r1')]
    fig,axes=plt.subplots(4,1,figsize=(13,10),sharex=True,constrained_layout=True)
    for r in compare:
        series=[b for b in bins if b['name']==r['name']]
        label=f"{r['name']} ({r['sources']} fontes, {r['nominal_rps']:.0f} req/s)"
        x=[b['second'] for b in series]
        axes[0].plot(x,[b['starts'] for b in series],label=label)
        axes[0].plot(x,[b['completions'] for b in series],linestyle=':',alpha=.8)
        axes[1].plot(x,[b['http_duration_ms_p95'] for b in series],label=label)
        axes[2].plot(x,[b['work_wait_ms_p95'] for b in series],label=label)
        axes[3].plot(x,[b['cpu_docker_percent_mean'] for b in series],label=label)
    axes[0].set_ylabel('req/s por janela');axes[0].set_title('Inícios (linha cheia) e conclusões (pontilhada)')
    axes[1].set_ylabel('ms');axes[1].set_title('Duração HTTP p95 por segundo de conclusão')
    axes[2].set_ylabel('ms');axes[2].set_title('Espera pelo worker p95 por segundo de encerramento do handler')
    axes[3].set_ylabel('% Docker');axes[3].set_xlabel('Segundo desde a origem experimental');axes[3].set_title('CPU média das amostras válidas por janela')
    axes[0].legend(fontsize=8,ncol=2);fig.suptitle('Séries temporais selecionadas; dados ausentes permanecem como lacunas')
    fig.savefig(OUT/'capacity_time_series.png',dpi=160);fig.savefig(OUT/'capacity_time_series.svg');plt.close(fig)


def main():
    rows,bins,paired=collect()
    plot_results(rows,bins,paired)
    feature_rows=[];capture_rows=[];generator_rows=[]
    for row in rows:
        folder=ROOT/row['name'];verification=read(folder/'verification/verification.json')
        for feature in verification['features']:
            feature_rows.append(dict(run=row['name'],run_id=row['run_id'],**feature))
        csv_capture=read(folder/'raw/traffic_capture.csv.capture.json')['capture_counters']
        pcap_capture=read(folder/'raw/source_artifacts/traffic_capture.pcap.capture.json')['capture_counters']
        capture_rows.append(dict(run=row['name'],run_id=row['run_id'],csv_captured=csv_capture.get('packets_captured'),
            csv_dropped=csv_capture.get('packets_dropped_by_kernel'),pcap_captured=pcap_capture.get('packets_captured'),
            pcap_dropped=pcap_capture.get('packets_dropped_by_kernel'),csv_stats_complete=csv_capture.get('statistics_complete'),
            pcap_stats_complete=pcap_capture.get('statistics_complete'),features_verified=verification['accepted']))
        diagnostic=read(folder/'diagnostic_summary.json')
        for source in diagnostic.get('sources',[]):
            intervals=source['empirical_intervals_seconds']
            planned=source['counts_per_second']['planned']
            started=source['counts_per_second']['http_started']
            generator_rows.append(dict(run=row['name'],source_id=source['source_id'],
                nominal_rps_per_source=source['nominal_rps'],
                theoretical_exponential_interval_mean_seconds=source['theoretical_exponential_mean_seconds'],
                planned_interval_n=len(intervals),planned_interval_mean_seconds=source['sampled_intervals_seconds']['mean'],
                planned_interval_p50_seconds=source['sampled_intervals_seconds']['p50'],
                planned_interval_p95_seconds=source['sampled_intervals_seconds']['p95'],
                planned_interval_sample_variance_seconds2=statistics.variance(intervals) if len(intervals)>1 else None,
                planned_count_mean_per_second=planned['mean'],planned_count_sample_variance=planned['sample_variance'],
                planned_count_variance_to_mean=planned['variance_to_mean'],
                http_start_count_mean_per_second=started['mean'],http_start_count_sample_variance=started['sample_variance'],
                http_start_count_variance_to_mean=started['variance_to_mean']))
    write_csv(OUT/'scientific_feature_integrity.csv',feature_rows)
    write_csv(OUT/'capture_integrity.csv',capture_rows)
    write_csv(OUT/'generator_statistics_by_source.csv',generator_rows)
    selection=read(ROOT/'selected_matrix.json')
    completed={r['name'] for r in rows}
    not_run=[name for name in selection['order'] if name not in completed]
    status_rows=[]
    for name in selection['order']:
        folder=ROOT/name
        if name in completed:
            result=read(folder/'execution_result.json');summary=read(folder/'capacity_summary.json');verification=read(folder/'verification/verification.json')
            status_rows.append(dict(name=name,run_id=summary['run_id'],state=result['status'],integrity='valid' if verification['accepted'] and not summary['reliability_errors'] else 'invalid',
                progression='allowed' if summary['progression']['allowed'] else 'stopped_by_guard',action='preserve; review guard' if not summary['progression']['allowed'] else 'preserve'))
        else:status_rows.append(dict(name=name,run_id='',state='not_run_after_progression_stop',integrity='inconclusive',progression='not_reached',action='do not rerun automatically'))
    write_csv(OUT/'matrix_run_status.csv',status_rows)
    manifest={
        'runs_included':[r['name'] for r in rows],
        'runs_incomplete_or_unexecuted':read(ROOT/'matrix_stop.json'),
        'planned_matrix_entries_not_run':not_run,
        'reason_not_run':'Progression guard stopped after C5_ON_r1 worker_wait_p95_ms exceeded 100 ms; higher-load repetitions were not resumed.',
        'instrumentation_pairs_available':[p['scenario']+'_'+p['repetition'] for p in paired],
        'plots':['capacity_overview.png','capacity_time_series.png'],
        'generator_timing_note':'Exponential theoretical interval mean is 1/rate for each source; empirical interval/count summaries are descriptive finite-window statistics, not a goodness-of-fit test.',
        'interpretation':'Descriptive exploratory results only; absent rows are not imputed and repeated-run conditions stopped by the operational guard remain inconclusive.'}
    (OUT/'analysis_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':main()
