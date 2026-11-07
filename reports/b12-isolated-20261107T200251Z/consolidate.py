import json,csv,statistics,subprocess
from pathlib import Path
root=Path('experiment_results/b12-isolated-20261107T200251Z');out=Path('reports')/root.name
J=lambda p:json.loads(p.read_text())
entries=[('A1-reference',Path('experiment_results/b11-integrated-asymmetry-20261107-r1'),out/'A1-reference')]+[(r['configuration'],Path(r['path']),out/r['configuration']) for r in J(root/'progress.json')]
records=[]
for name,directory,analysis in entries:
 if not (analysis/'summary.json').exists():continue
 s=J(analysis/'summary.json');http=s['groups']['attack'];comp=s['computation']['attack'];res=s['residual'];op=J(directory/'raw/operational_policy.json');status=J(directory/'raw/run_status.json')
 row=dict(configuration=name,mechanism=s['mechanism'],run_id=s['run_id'],dataset=s['dataset'],analysis=str(analysis),nominal=http['nominal_rps'],realized=http['realized_start_rps'],delta=http['realized_minus_nominal'],admissions=s['emission']['events'].get('admission',0),submitted=s['emission']['events'].get('submitted',0),starts=http['attempts_started'],ended=http['attempts_ended_known'],responses=http['responses_received'],http_errors=http['http_error_responses'],timeouts=http['timeouts'],connections=http['connection_errors'],expired=s['emission']['resolutions'].get('expired_before_http',0),http_mean_ms=http['known_end_duration_ms']['mean'],http_median_ms=http['known_end_duration_ms']['median'],http_p95_ms=http['known_end_duration_ms']['p95'],wait_mean_ms=comp['wait_ms']['mean'],wait_p95_ms=comp['wait_ms']['p95'],cpu_op_ms=comp['cpu_operation_ms']['mean'],compute_wall_ms=comp['wall_ms']['mean'],computational_events=comp['events'],cpu_mean=s['cpu']['tick_cpu_percent']['mean'],cpu_max=s['cpu']['tick_cpu_percent']['max'],memory_max=s['cpu']['tick_memory_mib']['max'],cpu_tick_median=s['cpu']['ticks']['intervals_seconds']['median'],cpu_tick_max=s['cpu']['ticks']['intervals_seconds']['max'],cpu_raw_median=s['cpu']['raw']['intervals_seconds']['median'] if s['cpu']['raw'] else None,cpu_raw_max=s['cpu']['raw']['intervals_seconds']['max'] if s['cpu']['raw'] else None,late_completions=res['completions_after_E'],last_compute=res['last_observed_completion'],last_minus_E=res['last_completion_minus_E'],correlated=s['integrity']['correlated_requests'],conflicts=s['integrity']['conflicts'],computation_complete=s['integrity']['computation_complete'],dataset_valid=s['validation']['dataset_valid'],eligible=s['validation']['analysis_eligible'],certification=op['certification'],clean=op['cleanup_verified'],outside_window=s['emission']['outside_window'],capture_accepted=all(v['accepted'] for v in status['capture_results'].values()))
 for label,key in [('E','state_before_E'),('close','final_state')]:
  counts=res[key]['counts']
  for k in ('waiting','running','pending'):row[label+'_'+k]=counts['attack'][k] if counts else None
 meta=J(directory/'raw/diagnostics/metadata.json');origin=meta['origin_monotonic']
 ve=[json.loads(l) for l in (directory/'raw/diagnostics/victim/events.jsonl').read_text().splitlines()]
 row['victim_submissions_at_or_after_E']=sum(e['kind']=='work_submitted' and e.get('traffic_class')=='attack' and e['at']>=origin+60 for e in ve)
 delays=[];peaks=[]
 for source in J(directory/'raw/source_inventory.json'):
  path=directory/'raw/source_artifacts'/source['source_id']/'output/diagnostics/events.jsonl'
  events=[json.loads(l) for l in path.read_text().splitlines()];mapped={}
  for e in events:
   if 'attempt_id' in e:mapped.setdefault(e['attempt_id'],{})[e['kind']]=e
   if 'counts' in e:
    c=e['counts'];peaks.append(c['submitted']-c['task_started']-c['cancelled']-c['rejected'])
  delays += [v['task_started']['at']-v['submitted']['at'] for v in mapped.values() if 'submitted' in v and 'task_started' in v]
 row['source_queue_peak_per_source']=max(peaks,default=0);row['source_dispatch_mean_ms']=statistics.mean(delays)*1000 if delays else None;row['source_dispatch_max_ms']=max(delays)*1000 if delays else None
 records.append(row)
(out/'consolidated.json').write_text(json.dumps(records,indent=2)+'\n')
with (out/'consolidated.csv').open('w',newline='') as f:
 fields=list(records[0]);w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(records)
print(json.dumps([{k:r[k] for k in ['configuration','nominal','realized','responses','timeouts','expired','E_pending','last_compute','source_queue_peak_per_source']} for r in records],indent=2))
