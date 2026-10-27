"""Parameterized offline audit for one DEVELOPMENT D1 entry; no detector imports.
Usage: python -m experiments.development_d1_review --entry d1_L03_A
"""
import csv, datetime, hashlib, json, statistics, time
from collections import Counter
from decimal import Decimal as D
from pathlib import Path
from zoneinfo import ZoneInfo
from experiments.summarize_service import quantile

import argparse
ROOT=Path.cwd()
parser=argparse.ArgumentParser();parser.add_argument('--entry',required=True);parser.add_argument('--manifest',default='experiments/protocols/development_d1_20261027/manifest.json');parser.add_argument('--dry-run',action='store_true');parser.add_argument('--preflight-binding-only',action='store_true');ARGS=parser.parse_args();ENTRY_ID=ARGS.entry
MANIFEST=ROOT/ARGS.manifest
plan=json.loads(MANIFEST.read_text());BASE=ROOT/plan.get('results_root','experiment_results/development-d1-20261027');OPS=BASE/'operations'/ENTRY_ID
entry=next(e for e in plan['entries'] if e['id']==ENTRY_ID);RAW=ROOT/entry['outputs']['raw'];DATASET=ROOT/entry['outputs']['dataset'];ANALYSIS=ROOT/entry['outputs']['analysis'];REVIEW=ROOT/entry['outputs']['review']
def read(p):return json.loads(Path(p).read_text())
def csvrows(p):
 with Path(p).open(newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load_bound_preflight():
 attempt_path=OPS/'attempt.json'
 attempt=read(attempt_path)
 required=('preflight_id','preflight_path','preflight_sha256','authorization_scope','manifest_sha256')
 missing=[key for key in required if not attempt.get(key)]
 if missing:raise ValueError(f'attempt.json lacks explicit preflight binding fields: {missing}')
 if attempt['authorization_scope']!=ENTRY_ID:raise ValueError('attempt authorization scope differs from review entry')
 manifest_hash=sha(MANIFEST)
 if attempt['manifest_sha256']!=manifest_hash:raise ValueError('attempt manifest hash differs from review manifest')
 relative=Path(attempt['preflight_path'])
 if relative.is_absolute():raise ValueError('attempt preflight path must be repository-relative')
 path=(ROOT/relative).resolve()
 if not path.is_relative_to(OPS.resolve()):raise ValueError('attempt preflight path escapes this entry operations directory')
 if not path.is_file():raise FileNotFoundError(f'Bound preflight report is missing: {relative}')
 if sha(path)!=attempt['preflight_sha256']:raise ValueError('Bound preflight report hash differs from attempt.json')
 preflight=read(path)
 if preflight.get('preflight_id')!=attempt['preflight_id']:raise ValueError('Bound preflight ID differs from attempt.json')
 if preflight.get('approved_entry')!=ENTRY_ID:raise ValueError('Bound preflight entry differs from review entry')
 if preflight.get('manifest_sha256')!=manifest_hash:raise ValueError('Bound preflight manifest differs from review manifest')
 if preflight.get('ready') is not True:raise ValueError('Bound preflight was not successful')
 return attempt,preflight,path
def stamp(epoch):
 dt=datetime.datetime.fromtimestamp(float(epoch),datetime.timezone.utc)
 return dict(epoch=float(epoch),utc=dt.isoformat(),America_Sao_Paulo=dt.astimezone(ZoneInfo('America/Sao_Paulo')).isoformat())
def stats(values):
 values=[D(str(x)) for x in values if x is not None and x!='']
 return dict(n=len(values),min=min(values) if values else None,max=max(values) if values else None,
             mean=sum(values)/len(values) if values else None,p50=quantile(values,'.5'),p95=quantile(values,'.95'))
def gap(times,a=30,b=150):
 return max([right-left for left,right in zip([D(a)]+sorted(map(lambda x:D(str(x)),times)),sorted(map(lambda x:D(str(x)),times))+[D(b)])],default=None)
def ratio(a,b):return None if not b else D(str(a))/D(str(b))
def default(x):
 if isinstance(x,D):return str(x)
 raise TypeError(type(x).__name__)
assert ARGS.dry_run or not REVIEW.exists(),'Never overwrite review'
attempt,preflight,preflight_path=load_bound_preflight()
if ARGS.preflight_binding_only:
 print(json.dumps({'entry':ENTRY_ID,'preflight_id':attempt['preflight_id'],'preflight_path':str(preflight_path.relative_to(ROOT)),'preflight_sha256':attempt['preflight_sha256'],'manifest_sha256':attempt['manifest_sha256'],'ready':preflight['ready']}))
 raise SystemExit(0)
initial_files={str(p.relative_to(ROOT)):sha(p) for root in (RAW,DATASET) for p in root.rglob('*') if p.is_file()}
status=read(RAW/'run_status.json');validation=read(ROOT/entry['outputs']['validation']);summary=read(ANALYSIS/'service_summary.json');inventory=read(RAW/'source_inventory.json');requests=csvrows(RAW/'request_log.csv');run_id=status['run_id']
post=read(OPS/'postprocess.json');execution=read(OPS/'execution_result.json');cleanup=read(OPS/'cleanup_observation.json')
for path, expected in preflight['checks'].get('operational_code_sha256', {}).items():
 if sha(ROOT/path)!=expected:raise ValueError(f'Operational utility changed after preflight: {path}')
criteria=[]
def criterion(name,passed,observed,limit,category):
 criteria.append(dict(name=name,passed=bool(passed),observed=observed,limit=limit,category=category))

# Full scientific row correspondence, including status/outcome/duration and origin.
begins={};finishes={};local={};mismatches=[];closures=[];source_invariants=[]
numfields={'worker_id','timestamp','elapsed_seconds','end_timestamp','end_elapsed_seconds','duration_ms','http_status','attack_active'}
def equivalent(field,a,b):
 if a in ('',None) or b in ('',None):return a in ('',None) and b in ('',None)
 return D(str(a))==D(str(b)) if field in numfields else str(a)==str(b)
for source in inventory:
 sid=source['source_id'];journal=RAW/'source_artifacts'/sid/'output/journal.jsonl';items=[json.loads(line) for line in journal.read_text().splitlines()]
 sequence_ok=[r['sequence'] for r in items]==list(range(1,len(items)+1))
 identity_ok=all(r['run_id']==run_id and r['source_id']==sid for r in items)
 closed=[r['payload'] for r in items if r['kind']=='source_closed'];closures.extend(dict(source_id=sid,**c) for c in closed)
 for item in items:
  kind=item['kind'];payload=item['payload']
  if kind in ('request_begin','request_finish'):
   table=begins if kind=='request_begin' else finishes
   if payload['request_id'] in table:mismatches.append(dict(request_id=payload['request_id'],field='duplicate '+kind))
   table[payload['request_id']]=(sid,payload)
 localrows=csvrows(RAW/'source_artifacts'/sid/'output/local_requests.csv')
 for r in localrows:
  if r['request_id'] in local:mismatches.append(dict(request_id=r['request_id'],field='duplicate local CSV'))
  local[r['request_id']]=(sid,r)
 final=read(RAW/'source_artifacts'/sid/'output/final_status.json')
 source_invariants.append(dict(source_id=sid,worker_index=source['worker_index'],sequence_ok=sequence_ok,identity_ok=identity_ok,
      final_status=final,inventory_final=source['status_final'],closure_count=len(closed),send_workers=source['send_workers']))
fields_checked=Counter()
startfields=['run_id','request_id','generator','worker_id','target_url','timestamp','elapsed_seconds','traffic_class','attack_id','event_id']
endfields=startfields+['end_timestamp','end_elapsed_seconds','duration_ms','http_status','outcome','error_type']
for row in requests:
 rid=row['request_id'];sid,begin=begins[rid];source=next(s for s in inventory if s['source_id']==sid)
 if (row['generator']!='normal' or row['traffic_class']!='benign' or int(row['worker_id'])!=source['worker_index'] or not rid.startswith('request_'+sid+'_')):
  mismatches.append(dict(request_id=rid,field='source identity'))
 for field in startfields:
  fields_checked['begin.'+field]+=1
  if not equivalent(field,row[field],begin.get(field)):mismatches.append(dict(request_id=rid,field='begin.'+field))
 if rid in finishes:
  fsid,finish=finishes[rid]
  if fsid!=sid:mismatches.append(dict(request_id=rid,field='finish.source_id'))
  for field in endfields:
   fields_checked['finish.'+field]+=1
   if not equivalent(field,row[field],finish.get(field)):mismatches.append(dict(request_id=rid,field='finish.'+field))
 elif row['outcome']!='incomplete' or any(row[k] for k in ('http_status','duration_ms','end_timestamp','end_elapsed_seconds')):
  mismatches.append(dict(request_id=rid,field='incomplete invented end'))
 lsid,localrow=local[rid]
 if lsid!=sid:mismatches.append(dict(request_id=rid,field='local.source_id'))
 for field in endfields:
  fields_checked['local.'+field]+=1
  if not equivalent(field,row[field],localrow.get(field)):mismatches.append(dict(request_id=rid,field='local.'+field))
sets_match=set(begins)==set(local)=={r['request_id'] for r in requests} and set(finishes)=={r['request_id'] for r in requests if r['end_elapsed_seconds']}
correspondence=dict(requests=len(requests),begins=len(begins),finishes=len(finishes),local_rows=len(local),sets_match=sets_match,fields_checked=dict(fields_checked),mismatch_count=len(mismatches),mismatches=mismatches)

measure=next(r for r in summary['rows'] if r['traffic_class']=='benign' and r['phase']=='MEASURE');bins=summary['d1_30s_cohorts'];counts=measure['cohort_outcomes'];failure_count=sum(counts[k] for k in ('http_error','transport_error','client_error'))
start_rate=ratio(measure['starts'],120);offered=entry['aggregate_rps'];adherence=ratio(start_rate,offered);success_ratio=ratio(counts['success_2xx'],measure['starts']);failure_ratio=ratio(failure_count,measure['starts']);success_throughput=ratio(measure['end_outcomes']['success_2xx'],120)
by_source=[]
for source in inventory:
 own=[r for r in requests if int(r['worker_id'])==source['worker_index']];cohort=[r for r in own if D(30)<=D(r['elapsed_seconds'])<D(150)]
 succeeded=[r for r in cohort if r['outcome']=='response' and 200<=int(r['http_status'])<300]
 by_source.append(dict(source_id=source['source_id'],worker_index=source['worker_index'],all_starts=len(own),useful_starts=len(cohort),starts_per_second=ratio(len(cohort),120),achieved_over_nominal=ratio(len(cohort),120*entry['rps_per_client']),
   success_2xx=len(succeeded),outcomes=dict(Counter(r['outcome'] for r in cohort)),http_statuses=dict(Counter(r['http_status'] for r in cohort)),success_duration_ms=stats([r['duration_ms'] for r in succeeded])))
service=dict(useful_interval_seconds=[30,150],exposure_seconds=120,nominal_rps_per_source=entry['rps_per_client'],nominal_aggregate_rps=offered,all_run_starts=len(requests),
 all_run_outcomes=dict(Counter(r['outcome'] for r in requests)),all_run_http_statuses=dict(Counter(r['http_status'] for r in requests)),
 useful_starts=measure['starts'],effective_aggregate_rps=start_rate,adherence=adherence,known_ends_by_start_cohort=measure['cohort_known_ends'],
 terminal_known_ends_in_useful_phase=measure['known_ends'],cohort_outcomes=counts,cohort_open=measure['cohort_open_as_of'],incomplete_no_end=measure['cohort_incomplete_no_end'],
 success_fraction_per_started=success_ratio,failures_per_started=failure_ratio,success_duration_2xx_ms=measure['duration_success_2xx_ms'],
 terminal_successes_in_useful_phase=measure['end_outcomes']['success_2xx'],terminal_successes_per_second=success_throughput,cohort_successes_per_exposure_second=ratio(counts['success_2xx'],120),
 completed_cross_phase=measure['completed_cross_phase'],per_source=by_source,cohorts_30s=bins,late_starts=summary['d1_evidence']['starts_at_or_after_nominal_end'],reconciliation=summary['reconciliation'])
if plan.get('campaign_schema') in {'development-endpoint-comparison/v1','development-endpoint-comparison/v2','development-endpoint-comparison/v3','development-endpoint-comparison/v4'}:
 cutoff=max(D(str(c['elapsed_seconds'])) for c in summary['d1_evidence']['closures'])
 inflight=[]
 for index,binrow in enumerate(bins):
  left=D(30+30*index);right=left+D(30);area=D(0)
  for request in requests:
   start=D(str(request['elapsed_seconds']))
   end=D(str(request['end_elapsed_seconds'])) if request['end_elapsed_seconds'] else cutoff
   area+=max(D(0),min(right,end)-max(left,start))
  inflight.append(dict(phase=binrow['phase'],start_seconds=str(left),end_seconds=str(right),
                       mean_open_requests=str(area/(right-left)),starts=binrow['starts'],
                       known_successes=binrow['duration_success_2xx_ms']['n']))
 service['mean_inflight_requests_by_30s']=inflight

# Victim samples: supported ticks, not falsely reconstructed Docker raw intervals.
metrics=csvrows(RAW/'simulation_metrics.csv');useful=[r for r in metrics if D(30)<=D(r['elapsed_seconds'])<D(150)];supported=[r for r in useful if r['active_containers_names'].strip()]
victim=dict(total_ticks=len(metrics),useful_ticks=len(useful),expected_useful_ticks=120,supported_useful_ticks=len(supported),supported_over_expected=ratio(len(supported),120),
 supported_over_observed=ratio(len(supported),len(useful)),unsupported_elapsed_seconds=[r['elapsed_seconds'] for r in useful if not r['active_containers_names'].strip()],
 max_supported_tick_gap_including_edges_seconds=gap([r['elapsed_seconds'] for r in supported]),
 cpu_docker_percent=stats([r['average_cpu_percent'] for r in supported]),memory_application_mib=stats([r['mem_usage'] for r in supported]),
 instance_counts=dict(Counter(r['num_instances'] for r in useful)),decisions=dict(Counter(r['decision'] for r in useful)),
 limits=['CPU100%=one logical-core equivalent, not utilization of reserved capacity.',
 'Victim values already averaged/cached; no original Docker read timestamps, collector error counters or per-logical-CPU consumption persisted.',
 'Support and tick gaps do not establish fresh Docker sampling; repeated values are not diagnosed as stale.',
 'Memory is historical max(usage-cache,0)/1024^2 convention; not proxy raw memory.'])

samples=[json.loads(line) for line in (RAW/'proxy_artifacts/monitor_samples.jsonl').read_text().splitlines()];monitor_summary=read(RAW/'proxy_artifacts/monitor_summary.json');proxy=dict(total_samples=len(samples),monitor_summary=monitor_summary,sources={})
for source in ('status','docker'):
 observations=[r[source] for r in samples if D(30)<=D(str(r[source]['elapsed_seconds']))<D(150)]
 good=[r for r in observations if r['success'] and r['data'] is not None]
 proxy['sources'][source]=dict(attempted_useful=len(observations),successful_useful=len(good),success_fraction=ratio(len(good),len(observations)),expected_useful_slots=120,
 successful_over_expected_slots=ratio(len(good),120),errors=[dict(elapsed_seconds=r['elapsed_seconds'],error=r['error']) for r in observations if not r['success']],
 all_run_errors=[dict(elapsed_seconds=r[source]['elapsed_seconds'],error=r[source]['error']) for r in samples if not r[source]['success']],
 max_success_gap_including_edges_seconds=gap([r['elapsed_seconds'] for r in good]),collection_duration_seconds=stats([r['duration_seconds'] for r in observations]))
 if source=='docker':
  proxy['sources'][source].update(cpu_docker_percent=stats([r['data']['cpu_percent'] for r in good]),memory_raw_bytes=stats([r['data']['memory_usage_bytes'] for r in good]),
    delta_states=dict(Counter(r['data']['delta_state'] for r in good)),missing_cpu_count=sum(r['data']['cpu_percent'] is None for r in good))
 else:
  proxy['sources'][source]['connections']={key:stats([r['data'][key] for r in good]) for key in ('active_connections','reading_connections','writing_connections','waiting_connections')}
  proxy['sources'][source]['counter_endpoints']={key:dict(first=good[0]['data'][key],last=good[-1]['data'][key],delta=good[-1]['data'][key]-good[0]['data'][key]) if good else None for key in ('accepted_connections_total','handled_connections_total','requests_total')}
proxy['max_scheduling_delay_seconds']=max((r['delay_seconds'] for r in samples),default=None)
proxy['sources_share_expected_proxy_identity']=len({r['container_id'] for r in samples})==1 and all(r['run_id']==run_id for r in samples)
proxy['monitoring_accesses']=[json.loads(line) for line in (RAW/'proxy_artifacts/proxy_access.log').read_text().splitlines() if '"phase":"monitoring"' in line]
proxy['monitoring_access_http_statuses']=dict(Counter(str(r.get('status')) for r in proxy['monitoring_accesses']));proxy['monitoring_access_count']=len(proxy.pop('monitoring_accesses'))
proxy['limits']=['status and Docker acquired sequentially at own timestamps, not atomic.',
 'CPU includes exec/wget monitoring work in the proxy cgroup; raw memory includes Docker-accounted cache.',
 'Monitoring requests affect global NGINX counters and connections. Waiting is not queue length.',
 'Deltas cover observed Docker intervals; not instantaneous utilization, reserved capacity or isolated proxy overhead.']

capture_diagnostics={};capture_reports={};capture_integrity=[]
for name,base,stderr_path in (
    ('csv',RAW/'traffic_capture.csv',RAW/'traffic_capture.stderr'),
    ('pcap',RAW/'source_artifacts/traffic_capture.pcap',RAW/'source_artifacts/traffic_capture.pcap.stderr')):
 report_path=Path(str(base)+'.capture.json')
 if report_path.is_file() and stderr_path.is_file():
  report=read(report_path);diagnostic=stderr_path.read_text();counters=report['capture_counters']
  valid=(report['accepted'] and report['returncode'] in (0,-15) and counters['statistics_complete']
         and counters['packets_dropped_by_kernel']==0 and report['capture_diagnostic_sha256']==hashlib.sha256(diagnostic.encode()).hexdigest())
 else:
  report=None;diagnostic='';valid=False
 capture_reports[name]=report;capture_diagnostics[name]=diagnostic;capture_integrity.append(valid)
capture=capture_diagnostics.get('csv','');log=(OPS/'execution.log').read_text();log_flags=[line for line in log.splitlines() if any(token in line.lower() for token in ('error','failed','traceback','warning','exception'))]
pre_match=all(x['match'] for x in preflight['checks']['image_source_files'])
source_hashes_match=attempt.get('approved_source_hashes')==preflight['checks'].get('operational_code_sha256')
checkout_record=preflight['checks'].get('plan',{}).get('source_checkout',{})
checkout_valid=checkout_record.get('effective_checkout_commit')==preflight['checks'].get('head') and checkout_record.get('source_tree_unchanged') is True
criterion('plan_commit_and_configuration',checkout_valid and source_hashes_match and read(RAW/'effective_config.json')==entry['effective_configuration'],dict(preflight_id=attempt['preflight_id'],preflight_checkout=preflight['checks']['head'],run_checkout=attempt.get('effective_checkout_commit'),approved_anchor=preflight['approved_commit'],source_hashes_match=source_hashes_match,config_sha256=sha(RAW/'effective_config.json')),'successful linked preflight, approved source hashes and exact effective configuration','technical')
criterion('single_execution_completed',execution['returncode']==0 and status['status']=='completed' and status.get('producers_drained') is True and not status.get('errors'),dict(execution=execution,status=status),'one attempt, exit0, completed/drained/errors=[]','technical')
criterion('dataset_valid_and_eligible',validation['dataset_valid'] and validation['analysis_eligible'],dict(dataset_valid=validation['dataset_valid'],analysis_eligible=validation['analysis_eligible'],summary=validation['summary']),'both true; preserve warnings','technical')
criterion('image_code_ready',pre_match,dict(files_checked=len(preflight['checks']['image_source_files'])),'all image source hashes match checkout','technical')
criterion('journal_csv_status_outcome_duration_origin',sets_match and not mismatches,correspondence,'all compared fields and origin identities agree','technical')
closed_ok=len(closures)==4 and all(c['drained'] and c['logger_complete'] for c in closures) and all(s['sequence_ok'] and s['identity_ok'] and s['closure_count']==1 and s['final_status']['drained'] and s['final_status']['logger_complete'] and not s['inventory_final']['forced'] and s['inventory_final']['exit_code']==0 for s in source_invariants)
criterion('four_source_closed_and_drain',closed_ok,dict(closures=closures,evidence=summary['d1_evidence']),'four observed complete closures; no forced termination','technical')
if plan.get('campaign_schema') in {'development-endpoint-comparison/v1','development-endpoint-comparison/v2','development-endpoint-comparison/v3','development-endpoint-comparison/v4'}:
 drain=D(str(summary['d1_evidence']['observed_drain_seconds']))
 criterion('drain_budget',D(0)<=drain<=D(30),drain,'observed drain from nominal 150s through <=180s; no invented cutoff','technical')
criterion('aggregate_start_adherence',adherence is not None and D('.8')<=adherence<=D('1.2'),adherence,[.8,1.2],'generator')
criterion('per_source_start_adherence',all(D('.65')<=r['achieved_over_nominal']<=D('1.35') for r in by_source),by_source,[.65,1.35],'generator')
late_limit=max(D(4),D('.01')*len(requests));criterion('late_starts',service['late_starts']<=late_limit,service['late_starts'],late_limit,'generator')
criterion('success_duration_support',measure['duration_success_2xx_ms']['n']>=200,measure['duration_success_2xx_ms']['n'],'at least200','support')
criterion('success_2xx_fraction',success_ratio is not None and success_ratio>=D('.99'),success_ratio,'>=0.99 per started useful cohort','service')
criterion('failure_fraction',failure_ratio is not None and failure_ratio<=D('.01'),dict(http=counts['http_error'],transport=counts['transport_error'],client=counts['client_error'],fraction=failure_ratio),'<=0.01 per started useful cohort','service')
criterion('no_incomplete_open_cohort',measure['cohort_open_as_of']==0 and measure['cohort_incomplete_no_end']==0 and all(r['outcome']!='incomplete' for r in requests),dict(useful_open=measure['cohort_open_as_of'],all_incomplete=sum(r['outcome']=='incomplete' for r in requests)),'zero; no invented end/duration','service')
criterion('no_other_response',counts['other_response']==0 and all(r['outcome']!='response' or 200<=int(r['http_status'])<300 for r in requests),counts['other_response'],'zero; response is not automatically2xx','service')
criterion('terminal_success_throughput',success_throughput is not None and ratio(success_throughput,offered)>=D('.8'),dict(successes_per_second=success_throughput,over_nominal=ratio(success_throughput,offered)),f">=0.8 of{offered}RPS; ends grouped by end",'service')
p95=measure['duration_success_2xx_ms']['p95']
if plan.get('campaign_schema') not in {'development-endpoint-comparison/v1','development-endpoint-comparison/v2','development-endpoint-comparison/v3','development-endpoint-comparison/v4'}:
 reference_path=BASE/'analysis/d1_L01_reference.json'
 reference=read(reference_path)
 assert reference['p95_ref_ms']=='56.79376310008592650' and reference['next_levels_duration_limit_ms']=='250'
 criterion('success_p95',p95 is not None and D(p95)<=D(reference['next_levels_duration_limit_ms']),dict(p95_ms=p95,p95_reference_ms=reference['p95_ref_ms'],reference_path=str(reference_path.relative_to(ROOT)),reference_sha256=sha(reference_path)),'registered L01 service progression limit250ms, unchanged','service')
first,last=bins[0],bins[-1];fn=first['duration_success_2xx_ms']['n'];ln=last['duration_success_2xx_ms']['n'];fr0=first['rates_per_second']['success_2xx_ends'];lr0=last['rates_per_second']['success_2xx_ends'];fp=first['duration_success_2xx_ms']['p95'];lp=last['duration_success_2xx_ms']['p95'];trend_support=fn>=50 and ln>=50 and fr0 is not None and lr0 is not None and fp is not None and lp is not None;fr=D(str(fr0)) if fr0 is not None else None;lr=D(str(lr0)) if lr0 is not None else None;stop_trend=trend_support and lr<=fr*D('.8') and D(str(lp))>=D(str(fp))*2
criterion('within_run_trend',trend_support and not stop_trend,dict(first_success_n=fn,last_success_n=ln,first_success_rps=fr,last_success_rps=lr,first_p95_ms=fp,last_p95_ms=lp,support_sufficient=trend_support,stop_condition=bool(stop_trend)),'stop if rate falls>=20% AND p95 doubles; n>=50 each. Missing bin support fails closed. Intermediate bins also retained for review','service')
criterion('victim_resource_support',len(supported)>=108 and victim['max_supported_tick_gap_including_edges_seconds']<=5,dict(supported=len(supported),expected=120,max_gap=victim['max_supported_tick_gap_including_edges_seconds']),'>=90% of120 ticks, gap<=5s; cache freshness remains unknown','collection')
for s in ('status','docker'):
 r=proxy['sources'][s]
 criterion('proxy_'+s+'_support',r['success_fraction'] is not None and r['success_fraction']>=D('.9') and r['successful_over_expected_slots']>=D('.9') and r['max_success_gap_including_edges_seconds']<=5,r,'>=90% successful attempts/expected slots and gap<=5s','collection')
criterion('proxy_monitor_identity_and_shutdown',proxy['sources_share_expected_proxy_identity'] and not monitor_summary.get('thread_alive',True) and not monitor_summary.get('fatal_error'),monitor_summary,'stable run/container ID; stopped thread; no fatal error','technical')
criterion('capture', len(capture_integrity)==2 and all(capture_integrity) and not status.get('errors')
      and all(status.get('capture_results',{}).get(key)==value for key,value in capture_reports.items()),
 dict(processes=capture_reports,diagnostics={key:value for key,value in capture_diagnostics.items()},run_status=status.get('capture_results'),
      run_status_matches_reports=all(status.get('capture_results',{}).get(key)==value for key,value in capture_reports.items())),
 'CSV and PCAP exited acceptably, each has complete counters and exactly zero kernel drops','collection')
before_containers={c['id']:c for c in preflight['checks']['containers_before']}
new_containers=[c for c in cleanup['containers'] if c['id'] not in before_containers]
prior_states_preserved=all(c['id'] in before_containers and c['status']==before_containers[c['id']]['status'] for c in cleanup['containers']) and set(before_containers)=={c['id'] for c in cleanup['containers']}
cleanup['preexisting_stopped_containers_preserved']=prior_states_preserved
cleanup['new_containers_remaining']=new_containers
criterion('cleanup',cleanup['no_active_containers'] and cleanup['no_scientific_processes'] and not new_containers and prior_states_preserved and cleanup['port_check_returncode']==0 and len(cleanup['port_8080'].strip().splitlines())==1,cleanup,'current-run containers removed; preexisting stopped containers preserved; no experiment processes or8080 listener','technical')
criterion('postprocess_commands',all(c['returncode']==0 for c in post),post,'validation and summary commands exit0; no retry','technical')
if plan.get('campaign_schema') in {'development-endpoint-comparison/v1','development-endpoint-comparison/v2','development-endpoint-comparison/v3','development-endpoint-comparison/v4'} and entry.get('role')=='capacity_probe':
 first_in,last_in=service['mean_inflight_requests_by_30s'][0],service['mean_inflight_requests_by_30s'][-1]
 first_open=D(first_in['mean_open_requests']);last_open=D(last_in['mean_open_requests'])
 inflight_rise=last_open>=max(first_open*D(2),first_open+D('.5'))
 support_ok=first_in['starts']>=50 and last_in['starts']>=50
 criterion('probe_no_open_request_accumulation',support_ok and not inflight_rise,
   dict(first_bin=first_in,last_bin=last_in,accumulation_signal=inflight_rise),
   'no doubling plus >=0.5 increase in mean in-flight requests; >=50 starts in boundary bins','service')
 probe_base_pass=all(c['passed'] for c in criteria)
 criterion('probe_4rps_adequacy',probe_base_pass,
   dict(prior_criteria_pass=probe_base_pass,mean_inflight_by_30s=service['mean_inflight_requests_by_30s'],
        p95_ms_descriptive=p95),
   'retain 4 aggregate RPS only if all integrity, service, generator, collection and no-accumulation criteria pass; no absolute p95 ceiling','gate')

finished_epoch=time.time();idle=finished_epoch-cleanup['observed_epoch'];all_pass=all(c['passed'] for c in criteria)
raw_inventory={str(p.relative_to(ROOT)):sha(p) for root in (RAW,DATASET) for p in root.rglob('*') if p.is_file()}
assert initial_files==raw_inventory,'Raw/dataset changed during audit'
result=dict(schema_version=1,review_type='single real DEVELOPMENT run; no detectors/calibration/TEST',entry_id=entry['id'],run_id=run_id,
 authority=dict(commit=attempt['effective_checkout_commit'],manifest_path=str(MANIFEST.relative_to(ROOT)),manifest_sha256=sha(MANIFEST),config_path=entry['config'],config_sha256=entry['config_sha256'],preflight_id=attempt['preflight_id'],preflight_path=attempt['preflight_path'],preflight_sha256=attempt['preflight_sha256'],user_authorization=f'Entry-scoped DEVELOPMENT authorization: {ENTRY_ID}; no detectors, calibration or TEST'),
 timing=dict(invocation=stamp(attempt['invoked_epoch']),experiment_anchor=stamp(status['experiment_start_timestamp']),
 nominal_end=stamp(D(str(status['experiment_start_timestamp']))+150),
 source_closed=[dict(source_id=c['source_id'],elapsed_seconds=c['elapsed_seconds'],anchor_derived_wall_time=stamp(D(str(status['experiment_start_timestamp']))+D(str(c['elapsed_seconds']))),wall_conversion='epoch anchor + monotonic elapsed; approximate, not atomic clock sampling') for c in closures],
 command_return=stamp(execution['command_return_observed_epoch']),cleanup_observation=stamp(cleanup['observed_epoch']),review_observation=stamp(finished_epoch),
 elapsed_since_observed_cleanup_seconds=idle,recovery_minimum_idle_seconds=60,recovery_interval_elapsed=idle>=60,
 next_run_started=False,next_start_time=None,drain_observed_seconds=summary['d1_evidence']['observed_drain_seconds']),
 service=service,lifecycle=dict(closures=closures,sources=source_invariants,correspondence=correspondence),
 resources=dict(victim=victim,proxy=proxy),dataset_validation=validation,
 runtime_log_diagnostics=dict(flagged_lines=log_flags,notes='No additional host CPU telemetry collected. Existing runtime host series not analyzed here.'),
 criteria=criteria,classification=dict(service_degradation_observed=any(not c['passed'] for c in criteria if c['category']=='service'),
 technical_or_collection_failure_observed=any(not c['passed'] for c in criteria if c['category'] in ('technical','collection')),
 generator_issue_observed=any(not c['passed'] for c in criteria if c['category']=='generator')),
 decision={f'{ENTRY_ID}_all_criteria_pass':all_pass,'automatic_progression':False,'next_entry_requires_manual_gate':True,'minimum_idle_elapsed_at_review':idle>=60,
 'pending':['Review the next manifest entry only after this entry passes and recovery/readiness pass.','Do not proceed after any failed criterion or result requiring interpretation.'],
 'interpretation':'No claim of measured maximum capacity, final SLO, calibrated CUSUM performance or deployment generalization.'},
 evidence_files_sha256=dict(raw_and_dataset=raw_inventory,analysis={str(p.relative_to(ROOT)):sha(p) for p in ANALYSIS.rglob('*') if p.is_file()},
 validation={entry['outputs']['validation']:sha(ROOT/entry['outputs']['validation'])},operations={str(p.relative_to(ROOT)):sha(p) for p in OPS.rglob('*') if p.is_file() and p.name!='review.py'}),
 preserved_input_hashes_unchanged=True)
prior_hashes=read(OPS/'previous_hashes.json') if (OPS/'previous_hashes.json').exists() else {}
changed_prior=[p for p,h in prior_hashes.items() if sha(ROOT/p)!=h]
result['preserved_prior_files']={'count':len(prior_hashes),'all_hashes_identical':not changed_prior,'changed_paths':changed_prior}
if not ARGS.dry_run:
 with REVIEW.open('x') as f:json.dump(result,f,indent=2,default=default,allow_nan=False);f.write('\n')
print(json.dumps(dict(dry_run=ARGS.dry_run,review=str(REVIEW),all_criteria_pass=all_pass,failed=[c['name'] for c in criteria if not c['passed']],useful_starts=service['useful_starts'],effective_rps=service['effective_aggregate_rps'],p95_ms=service['success_duration_2xx_ms']['p95'],drain_seconds=summary['d1_evidence']['observed_drain_seconds'],idle_since_cleanup=idle),default=default))
