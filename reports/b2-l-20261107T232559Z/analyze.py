"""B2-L only: offline descriptive supplement using existing validated reducers."""
import sys, pathlib, json, csv, hashlib, collections
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from experiments.exploratory_analysis import Reader, analyze, describe
from experiments.offensive_analysis import characterize, classify_operations, http_metrics, state_before, cadence
from experiments.validate_dataset import validate_dataset

OUT=pathlib.Path(__file__).resolve().parent
RUN=ROOT/'experiment_results'/OUT.name
DS=RUN/'dataset'
def dump(name,data): (OUT/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
def table(name,rows):
 with (OUT/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
validation=validate_dataset(DS);dump('dataset_validation.json',validation)
checks=[]
manifest=json.loads((DS/'dataset_manifest.json').read_text())
for e in manifest['files']:
 p=DS/e['path'];checks.append(dict(path=e['path'],valid=p.is_file() and not p.is_symlink() and p.stat().st_size==e['bytes'] and sha(p)==e['sha256']))
dump('hash_verification.json',checks)
assert all(e['valid'] for e in checks)
assert validation['dataset_valid'] and validation['analysis_eligible']
if not (OUT/'existing_analyzer').exists():
 analyze('a1',[dict(path=str(DS),certification=str(RUN/'raw/operational_policy.json'))],OUT/'existing_analyzer')
r=Reader(DS);config=r.json('effective_config.json');status=r.json('run_status.json')
cert=json.loads((RUN/'raw/operational_policy.json').read_text())
assert cert['export']['sha256']==sha(DS/'dataset_manifest.json')
assert cert['execution']['run_id']==status['run_id']
inventory=r.json('source_inventory.json'); journal=[];source_events=[];source_writers=[]
for s in inventory:
 journal+=r.lines('source_artifacts/'+s['source_id']+'/output/journal.jsonl')
 source_events+=r.lines('source_artifacts/'+s['source_id']+'/output/diagnostics/events.jsonl')
 source_writers.append(r.json('source_artifacts/'+s['source_id']+'/output/diagnostics/events.summary.json'))
requests=r.csv('request_log.csv');events=r.lines('diagnostics/victim/events.jsonl')
meta=r.json('diagnostics/metadata.json');clock=r.json('diagnostics/victim_clock_validation.json')
writer=r.json('diagnostics/victim/events.summary.json');origin=meta['origin_monotonic']
metrics=r.csv('simulation_metrics.csv');rawcpu=r.lines('victim_stats.jsonl')
summary,series=characterize(config,requests,journal,events,metrics,rawcpu,origin,clock['comparable'],writer)
events,classes,correlation=classify_operations(events,requests)
opmap={}
for e in events:
 if e.get('operation_id'):opmap.setdefault(e['operation_id'],{})[e['kind']]=e
reqmap={r['request_id']:r for r in requests}
ops=[]
for oid,op in opmap.items():
 e=next(iter(op.values()));rid=e.get('request_id');req=reqmap.get(rid,{})
 sub=op.get('work_submitted');start=op.get('work_started');end=op.get('work_completed')
 if not sub:continue
 t=float(req['elapsed_seconds']) if req else None
 ops.append(dict(operation_id=oid,request_id=rid,traffic_class=classes[oid],http_start=t,
  cohort=('P1' if t<30 else 'P2' if t<60 else 'P3' if t<150 else 'tail') if t is not None else 'unknown',
  http_end=float(req['end_elapsed_seconds']) if req.get('end_elapsed_seconds') else None,
  submitted=sub['at']-origin,started=start['at']-origin if start else None,
  finished=end['work_finished_at']-origin if end else None,
  wait_ms=(start['at']-sub['at'])*1000 if start else None,
  cpu_ms=end['work_cpu_seconds']*1000 if end else None,
  wall_ms=(end['work_finished_at']-end['work_started_at'])*1000 if end else None,
  worker_pid=start.get('worker_clock',{}).get('pid') if start else None,
  failed='work_failed' in op))
table('operations.csv',ops)
table('http_attempts.csv',[dict(r,cohort='P1' if float(r['elapsed_seconds'])<30 else 'P2' if float(r['elapsed_seconds'])<60 else 'P3' if float(r['elapsed_seconds'])<150 else 'tail') for r in requests])
periods={'Total':(0,150),'P1':(0,30),'P2':(30,60),'P3':(60,150)}
http=[];comp=[];resources=[];workers=[]
for name,(a,b) in periods.items():
 own=[r for r in requests if a<=float(r['elapsed_seconds'])<b]
 h=http_metrics(own,a,b,16)
 success=sum(bool(r.get('http_status')) and 200<=int(r['http_status'])<300 for r in own)
 je=[e for e in source_events if a<=e['at']-origin<b]
 counts=collections.Counter(e['kind'] for e in je)
 h.update(successful_responses=success,availability=success/len(own) if own else None,
  availability_numerator=success,availability_denominator=len(own),admissions=None,submissions=counts['submitted'],
  expirations_before_http=0,admissions_note='No distinct admission event in legitimate generator; submissions counted from source diagnostics. All submitted attempts reconciled with HTTP starts.')
 summary.setdefault('b2_periods',{})[name]=h
 http.append(dict(period=name,seconds=b-a,nominal_rps=16,realized_rps=h['realized_start_rps'],delta_rps=h['realized_minus_nominal'],
  admissions=h['admissions'],submissions=h['submissions'],expired=h['expirations_before_http'],started=len(own),ended=h['attempts_ended_known'],
  responses=h['responses_received'],success=success,http_errors=h['http_error_responses'],timeouts=h['timeouts'],connection_errors=h['connection_errors'],unknown_end=h['attempts_without_observed_end'],availability=h['availability'],
  mean_ms=h['duration_ms']['mean'],median_ms=h['duration_ms']['p50'],p95_ms=h['duration_ms']['p95'],min_ms=h['duration_ms']['minimum'],max_ms=h['duration_ms']['maximum']))
 oo=[o for o in ops if o['traffic_class']=='benign' and o['http_start'] is not None and a<=o['http_start']<b]
 snap=state_before(events,origin+b,summary['integrity']['computation_complete'])['counts']['benign']
 c=dict(period=name,submitted=len(oo),started=sum(o['started'] is not None for o in oo),completed=sum(o['finished'] is not None for o in oo),failed=sum(o['failed'] for o in oo),
  wait_mean_ms=describe(o['wait_ms'] for o in oo if o['wait_ms'] is not None)['mean'],wait_median_ms=describe(o['wait_ms'] for o in oo if o['wait_ms'] is not None)['p50'],wait_p95_ms=describe(o['wait_ms'] for o in oo if o['wait_ms'] is not None)['p95'],
  cpu_mean_ms=describe(o['cpu_ms'] for o in oo if o['cpu_ms'] is not None)['mean'],wall_mean_ms=describe(o['wall_ms'] for o in oo if o['wall_ms'] is not None)['mean'],waiting_at_end=snap['waiting'],running_at_end=snap['running'],pending_at_end=snap['pending'])
 c.update({kind+'_in_interval':sum(e['kind']==kind and e.get('traffic_class')=='benign' and a<=e['at']-origin<b for e in events) for kind in ('work_submitted','work_started','work_completed','work_failed')})
 comp.append(c)
 for pid in sorted({o['worker_pid'] for o in oo if o['worker_pid'] is not None}):
  w=describe(o['wait_ms'] for o in oo if o['worker_pid']==pid and o['wait_ms'] is not None)
  workers.append(dict(period=name,worker_pid=pid,n=w['n'],mean_ms=w['mean'],median_ms=w['p50'],p95_ms=w['p95']))
 mm=[m for m in metrics if m.get('active_containers_names') and a<=float(m['elapsed_seconds'])<b]
 cd=cadence([float(m['elapsed_seconds']) for m in mm],{})
 raw=[m for m in rawcpu if a<=m['monotonic']-origin<b]
 resources.append(dict(period=name,ticks=len(mm),cpu_mean=describe(float(m['average_cpu_percent']) for m in mm)['mean'],cpu_max=describe(float(m['average_cpu_percent']) for m in mm)['maximum'],memory_mean_mib=describe(float(m['mem_usage']) for m in mm)['mean'],memory_max_mib=describe(float(m['mem_usage']) for m in mm)['maximum'],tick_gap_median=cd['intervals_seconds']['p50'],tick_gap_max=cd['intervals_seconds']['maximum'],raw_samples=len(raw),raw_gap_median=cadence([m['monotonic'] for m in raw],{})['intervals_seconds']['p50']))
table('http_by_period.csv',http);table('computation_by_period.csv',comp);table('worker_wait_by_period.csv',workers);table('resources_by_period.csv',resources)
for row in series:row['phase']={'pre':'P1','attack':'P2','post':'P3'}[row['phase']]
table('timeseries_1s.csv',series)
qrows=[];waiting=running=0
for e in sorted(events,key=lambda e:(e['at'],e['sequence'])):
 if e.get('traffic_class')!='benign':continue
 if e['kind']=='work_submitted':waiting+=1
 elif e['kind']=='work_started':waiting-=1;running+=1
 elif e['kind'] in ('work_completed','work_failed'):running-=1
 else:continue
 qrows.append(dict(seconds=e['at']-origin,kind=e['kind'],waiting=waiting,running=running,pending=waiting+running))
table('queue_transitions.csv',qrows)
queue_summary=[]
for name,(a,b) in periods.items():
 qq=[q for q in qrows if a<=q['seconds']<b]
 queue_summary.append(dict(period=name,max_waiting=max((q['waiting'] for q in qq),default=0),max_running=max((q['running'] for q in qq),default=0),max_pending=max((q['pending'] for q in qq),default=0)))
table('queue_peaks_by_period.csv',queue_summary)
srcgroups={}
for e in source_events:
 if e.get('attempt_id'):srcgroups.setdefault((e['source_id'],e['attempt_id']),collections.Counter())[e['kind']]+=1
planned_only={str(k):dict(g) for k,g in srcgroups.items() if not g['submitted']}
srcgroups={k:g for k,g in srcgroups.items() if g['submitted']}
assert all(g['submitted']==g['task_started']==g['http_started']==g['http_finished']==g['task_finished']==1 for g in srcgroups.values())
assert len(srcgroups)==len(requests)
summary['emission']={'source_diagnostic_events':dict(collections.Counter(e['kind'] for e in source_events)),
 'admissions':None,'admissions_note':'Not independently instrumented for legitimate generation',
 'submissions':len(srcgroups),'expirations_before_http':0,'planned_not_submitted':planned_only,'attempt_lifecycles_reconciled':True,'source_writers':source_writers}
tail=[req for req in requests if not 0<=float(req['elapsed_seconds'])<150]
summary['tail_http']=tail
summary['boundary_crossings']={str(b):[req['request_id'] for req in requests if float(req['elapsed_seconds'])<b and req.get('end_elapsed_seconds') and float(req['end_elapsed_seconds'])>=b] for b in (30,60,150)}
summary['legacy_analyzer_reconciliation']={'unidentified_events':dict(collections.Counter(e['kind'] for e in events if not e.get('request_id'))),
 'explanation':'Legacy analyzer counts 30 work events without request_id plus the observation closure as unidentified; ten associated handler pairs explicitly declare capture_audit at endpoint /. Keep legacy exclusion visible; classify ten operations unknown, separate from benign operations.'}
summary.update(run_id=status['run_id'],checkout=json.loads((OUT/'initial_environment.json').read_text())['head']['stdout'].strip(),
 configuration=config,certificate=cert,dataset_validation=validation,computational_periods=comp,resource_periods=resources,worker_periods=workers,
 queue_peaks=queue_summary,manifest_sha256=sha(DS/'dataset_manifest.json'),analyzer_sha256=sha(pathlib.Path(__file__)),cohort_basis='HTTP start; actual completion preserved separately; P1/P2/P3 are reference intervals without attacks')
dump('summary.json',summary)
print(json.dumps(dict(http=http,computation=comp,resources=resources,queue_peaks=queue_summary,integrity=summary['integrity'],certification=cert.get('certification')),indent=2))
