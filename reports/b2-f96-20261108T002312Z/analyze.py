"""Offline B2-F96 supplement. Reuses existing analyzer, HTTP metrics and queue reducers."""
import sys,pathlib,json,csv,hashlib,collections
OUT=pathlib.Path(__file__).resolve().parent;ROOT=OUT.parents[1];sys.path.insert(0,str(ROOT))
from experiments.offensive_analysis import analyze,http_metrics,classify_operations,state_before,state_at,cadence
from experiments.exploratory_analysis import Reader,describe
from experiments.validate_dataset import validate_dataset
from experiments.export_dataset import placement
RUN=ROOT/'experiment_results'/OUT.name;DS=RUN/'dataset'
def dump(name,data):(OUT/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def table(name,rows):
 if not rows:return
 with (OUT/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
cert=json.loads((RUN/'raw/operational_policy.json').read_text())
assert cert['certification']=='completed' and cert['cleanup_verified'] and cert['procedure_completed']
if not (OUT/'existing_analyzer').exists():analyze(RUN,OUT/'existing_analyzer')
existing=json.loads((OUT/'existing_analyzer/summary.json').read_text())
assert existing['integrity']['computation_complete'] and existing['integrity']['identity_consistent']
assert not existing['integrity']['partial_lifecycles']
r=Reader(DS);cfg=r.json('effective_config.json');status=r.json('run_status.json');origin=r.json('diagnostics/metadata.json')['origin_monotonic']
validation=validate_dataset(DS);dump('dataset_validation.json',validation)
assert validation['dataset_valid'] and validation['analysis_eligible']
assert cert['export']['sha256']==sha(DS/'dataset_manifest.json') and cert['execution']['run_id']==status['run_id']
manifest=json.loads((DS/'dataset_manifest.json').read_text());checks=[];rawchecks=[]
for e in manifest['files']:
 p=DS/e['path'];checks.append(dict(path=e['path'],valid=p.stat().st_size==e['bytes'] and sha(p)==e['sha256']))
assert all(e['valid'] for e in checks);dump('hash_verification.json',checks)
idx={e['path']:e for e in manifest['files']}
for p in (RUN/'raw').rglob('*'):
 if not p.is_file():continue
 rel=str(p.relative_to(RUN/'raw'));dest=placement(pathlib.Path(rel))[0]
 if dest in idx and rel!='operational_policy.json':rawchecks.append(dict(path=rel,unchanged=sha(p)==idx[dest]['sha256']))
assert all(e['unchanged'] for e in rawchecks);dump('raw_export_comparison.json',rawchecks)
req=r.csv('request_log.csv');events=r.lines('diagnostics/victim/events.jsonl');metrics=r.csv('simulation_metrics.csv');rawcpu=r.lines('victim_stats.jsonl')
normalized,classes,corr=classify_operations(events,req);inventory=r.json('source_inventory.json')
sources={};journals=[];sourceevents=[];sourcechecks=[]
for src in inventory:
 sid=src['source_id'];cls='benign' if src['source_type']=='normal' else 'attack';sources[sid]=cls
 prefix='source_artifacts/'+sid+'/output/'
 j=r.lines(prefix+'journal.jsonl');ee=r.lines(prefix+'diagnostics/events.jsonl');ww=r.json(prefix+'diagnostics/events.summary.json');final=r.json(prefix+'final_status.json')
 assert [e['sequence'] for e in ee]==list(range(1,len(ee)+1))
 assert [e['sequence'] for e in j]==list(range(1,len(j)+1))
 assert ww['complete'] and ww['written']==len(ee) and ww['dropped']==ww['write_errors']==0
 assert final['drained'] and final['logger_complete']
 sourcechecks.append(dict(source_id=sid,traffic_class=cls,events=len(ee),journal_events=len(j),summary=ww,final_status=final))
 journals+=j;sourceevents+=ee
dump('source_integrity.json',sourcechecks)
life={}
for e in sourceevents:
 if e.get('attempt_id'):life.setdefault((e['source_id'],e['attempt_id']),collections.Counter())[e['kind']]+=1
submitted={k:v for k,v in life.items() if v['submitted']}
assert all(g['submitted']==g['task_started']==g['task_finished']==1 for g in submitted.values())
assert sum(g['http_started'] for g in submitted.values())==len(req)
assert all(g['http_started']==g['http_finished'] for g in submitted.values())
assert {e['request_id'] for e in sourceevents if e['kind']=='http_started'}=={x['request_id'] for x in req}
dump('emission_reconciliation.json',dict(lifecycles_reconciled=True,
 per_source={sid:dict(collections.Counter(e['kind'] for e in sourceevents if e['source_id']==sid)) for sid in sources},
 planned_only=[dict(source_id=k[0],attempt_id=k[1],events=dict(v)) for k,v in life.items() if not v['submitted']],
 submitted_without_http=[dict(source_id=k[0],attempt_id=k[1],events=dict(v)) for k,v in submitted.items() if not v['http_started']],
 journal_lifecycle=existing['emission']))
def cohort(t):return 'P1' if 0<=t<30 else 'P2' if 30<=t<60 else 'P3' if 60<=t<150 else 'tail'
table('http_attempts.csv',[dict(x,cohort=cohort(float(x['elapsed_seconds']))) for x in req])
opmap={};reqmap={x['request_id']:x for x in req}
for e in normalized:
 if e.get('operation_id'):opmap.setdefault(e['operation_id'],{})[e['kind']]=e
ops=[];audit=[]
for oid,op in opmap.items():
 sub=op.get('work_submitted');start=op.get('work_started');end=op.get('work_completed');fail=op.get('work_failed')
 if not sub:continue
 own=reqmap.get(sub.get('request_id'),{});t=float(own['elapsed_seconds']) if own else None
 if classes[oid]=='unknown':
  handlers=[e for e in op.values() if e['kind'].startswith('handler_')]
  assert len(handlers)==2 and all(e.get('phase')=='capture_audit' and e['endpoint']=='/' for e in handlers)
  audit.append(dict(operation_id=oid,classification='unknown',evidence='handler phase capture_audit, endpoint /',start_seconds=sub['at']-origin,end_seconds=op['handler_finished']['at']-origin))
 ops.append(dict(operation_id=oid,request_id=sub.get('request_id'),traffic_class=classes[oid],cohort=cohort(t) if t is not None else 'unknown',
  http_start=t,http_end=float(own['end_elapsed_seconds']) if own.get('end_elapsed_seconds') else None,
  submitted=sub['at']-origin,started=start['at']-origin if start else None,finished=end['work_finished_at']-origin if end else None,
  failed=bool(fail),wait_ms=(start['at']-sub['at'])*1000 if start else None,cpu_ms=end['work_cpu_seconds']*1000 if end else None,
  wall_ms=(end['work_finished_at']-end['work_started_at'])*1000 if end else None,worker_pid=start.get('worker_clock',{}).get('pid') if start else None))
table('operations.csv',ops);dump('audit_reconciliation.json',audit)
periods=[('Total',0,150),('P1',0,30),('P2',30,60),('P3',60,150)]
hrows=[];hfull={};crows=[];wrows=[]
def http_row(cls,name,a,b):
 own=[x for x in req if x['traffic_class']==cls and a<=float(x['elapsed_seconds'])<b]
 nominal=cfg['normal_traffic']['rate']*cfg['normal_traffic']['clients'] if cls=='benign' else cfg['attack']['rate']*cfg['attack']['attackers'] if name in ('Total','P2') else 0
 lo,hi=(30,60) if cls=='attack' and name=='Total' else (a,b)
 h=http_metrics(own,lo,hi,nominal);success=sum(bool(x.get('http_status')) and 200<=int(x['http_status'])<300 for x in own)
 h.update(success=success,availability=success/len(own) if own else None,numerator=success,denominator=len(own))
 ss=[e for e in sourceevents if sources[e['source_id']]==cls and a<=e['at']-origin<b]
 jj=[e for e in journals if sources[e['source_id']]==cls and a<=e['payload'].get('elapsed_seconds',-1)<b]
 h.update(submissions=sum(e['kind']=='submitted' for e in ss),admissions=sum(e['kind']=='admission' for e in jj) if cls=='attack' else None,
  expired_before_http=sum(e['kind']=='task_resolution' and e['payload'].get('decision')=='expired_before_http' for e in jj))
 row=dict(traffic_class=cls,period=name,nominal_rps=nominal,rate_denominator_seconds=hi-lo,realized_rps=h['realized_start_rps'],submissions=h['submissions'],admissions=h['admissions'],expired_before_http=h['expired_before_http'],
  starts=len(own),known_ends=h['attempts_ended_known'],responses=h['responses_received'],success=success,http_errors=h['http_error_responses'],timeouts=h['timeouts'],connection_errors=h['connection_errors'],unknown_end=h['attempts_without_observed_end'],availability=h['availability'],
  mean_ms=h['duration_ms']['mean'],median_ms=h['duration_ms']['p50'],p95_ms=h['duration_ms']['p95'],min_ms=h['duration_ms']['minimum'],max_ms=h['duration_ms']['maximum'],response_mean_ms=h['response_duration_ms']['mean'],response_median_ms=h['response_duration_ms']['p50'],response_p95_ms=h['response_duration_ms']['p95'])
 return row,h
for cls in ('benign','attack'):
 for name,a,b in periods:
  row,h=http_row(cls,name,a,b);hrows.append(row);hfull[cls+'_'+name]=h
  own=[o for o in ops if o['traffic_class']==cls and o['http_start'] is not None and a<=o['http_start']<b]
  wait=describe(o['wait_ms'] for o in own if o['wait_ms'] is not None)
  crows.append(dict(traffic_class=cls,period=name,cohort_basis='HTTP start',submitted=len(own),started=sum(o['started'] is not None for o in own),completed=sum(o['finished'] is not None for o in own),failed=sum(o['failed'] for o in own),wait_mean_ms=wait['mean'],wait_median_ms=wait['p50'],wait_p95_ms=wait['p95'],cpu_mean_ms=describe(o['cpu_ms'] for o in own if o['cpu_ms'] is not None)['mean'],wall_mean_ms=describe(o['wall_ms'] for o in own if o['wall_ms'] is not None)['mean']))
  for pid in sorted({o['worker_pid'] for o in own if o['worker_pid'] is not None}):
   oo=[o for o in own if o['worker_pid']==pid];w=describe(o['wait_ms'] for o in oo if o['wait_ms'] is not None)
   wrows.append(dict(traffic_class=cls,period=name,worker_pid=pid,operations=len(oo),wait_mean_ms=w['mean'],wait_median_ms=w['p50'],wait_p95_ms=w['p95']))
table('http_by_period.csv',hrows);table('computation_by_period.csv',crows);table('workers_by_period.csv',wrows)
ten=[]
for a in range(0,150,10):
 for cls in ('benign','attack'):
  row,h=http_row(cls,f'{a}-{a+10}',a,a+10)
  row['nominal_rps']=cfg['normal_traffic']['rate']*cfg['normal_traffic']['clients'] if cls=='benign' else cfg['attack']['rate']*cfg['attack']['attackers'] if 30<=a<60 else 0
  own=[o for o in ops if o['traffic_class']==cls and o['http_start'] is not None and a<=o['http_start']<a+10]
  row.update(start=a,end=a+10,wait_mean_ms=describe(o['wait_ms'] for o in own if o['wait_ms'] is not None)['mean'],wait_p95_ms=describe(o['wait_ms'] for o in own if o['wait_ms'] is not None)['p95'],cpu_mean_ms=describe(o['cpu_ms'] for o in own if o['cpu_ms'] is not None)['mean'])
  ten.append(row)
table('temporal_10s.csv',ten)
qcounts={cls:dict(waiting=0,running=0,pending=0) for cls in ('benign','attack','unknown')};qrows=[]
for e in sorted(normalized,key=lambda e:(e['at'],e.get('sequence',0))):
 cls=e.get('traffic_class','unknown');d=qcounts[cls]
 if e['kind']=='work_submitted':d['waiting']+=1
 elif e['kind']=='work_started':d['waiting']-=1;d['running']+=1
 elif e['kind'] in ('work_completed','work_failed'):d['running']-=1
 else:continue
 d['pending']=d['waiting']+d['running']
 assert all(v>=0 for dd in qcounts.values() for v in dd.values())
 row=dict(seconds=e['at']-origin,event=e['kind'],event_class=cls)
 for group,dd in qcounts.items():
  for key,val in dd.items():row[group+'_'+key]=val
 for key in d:row['total_'+key]=sum(dd[key] for dd in qcounts.values())
 qrows.append(row)
table('queue_transitions.csv',qrows)
peaks=[]
for name,a,b in periods:
 prefix=next((q for q in reversed(qrows) if q['seconds']<a),None)
 own=[q for q in qrows if a<=q['seconds']<b]+([prefix] if prefix else [])
 for cls in ('benign','attack','total'):
  peaks.append(dict(period=name,traffic_class=cls,**{key:max((q[cls+'_'+key] for q in own),default=0) for key in ('waiting','running','pending')}))
table('queue_peaks.csv',peaks)
boundaries={str(t):dict(before=state_before(normalized,origin+t,True),after_events_at_boundary=state_at(normalized,origin+t,True)) for t in (30,60,70,80,90,120,150)}
offops=[o for o in ops if o['traffic_class']=='attack'];late_sub=[o for o in offops if o['submitted']>=60]
last_off=max((o['finished'] for o in offops if o['finished'] is not None),default=None)
residual=dict(boundaries=boundaries,last_offensive_completion=last_off,seconds_after_60=last_off-60 if last_off is not None else None,
 offensive_completions_at_or_after_60=sum(o['finished'] is not None and o['finished']>=60 for o in offops),offensive_submissions_at_or_after_60=late_sub,
 final_observed_state=existing['residual']['final_state'],scope='Observed complete lifecycles of identified operations; not universal proof against unobserved future ingress')
dump('queue_residual.json',residual)
resources=[]
for name,a,b in periods:
 mm=[m for m in metrics if m.get('active_containers_names') and a<=float(m['elapsed_seconds'])<b]
 times=[float(m['elapsed_seconds']) for m in mm];cc=cadence(times,{})
 resources.append(dict(period=name,samples=len(mm),first=min(times) if times else None,last=max(times) if times else None,
  cpu_mean=describe(float(m['average_cpu_percent']) for m in mm)['mean'],cpu_max=describe(float(m['average_cpu_percent']) for m in mm)['maximum'],mem_mean_mib=describe(float(m['mem_usage']) for m in mm)['mean'],mem_max_mib=describe(float(m['mem_usage']) for m in mm)['maximum'],
  gap_median=cc['intervals_seconds']['p50'],gap_max=cc['intervals_seconds']['maximum'],raw_samples=sum(a<=x['monotonic']-origin<b for x in rawcpu)))
table('resources_by_period.csv',resources)
baseline=json.loads((ROOT/'reports/b2-l-20261107T232559Z/summary.json').read_text())
comparison=[]
for row in hrows:
 if row['traffic_class']!='benign':continue
 ref=baseline['b2_periods']['Total'];co=next(c for c in crows if c['traffic_class']=='benign' and c['period']==row['period'])
 comparison.append(dict(period=row['period'],rps=row['realized_rps'],rps_b2l=ref['realized_start_rps'],availability=row['availability'],availability_b2l=ref['availability'],http_mean_ms=row['mean_ms'],http_mean_ratio_b2l=row['mean_ms']/ref['duration_ms']['mean'] if row['mean_ms'] else None,http_p95_ms=row['p95_ms'],http_p95_ratio_b2l=row['p95_ms']/ref['duration_ms']['p95'] if row['p95_ms'] else None,worker_wait_ms=co['wait_mean_ms'],cpu_op_ms=co['cpu_mean_ms']))
table('comparison_b2l.csv',comparison)
tail=[x for x in req if not 0<=float(x['elapsed_seconds'])<150]
summary=dict(run_id=status['run_id'],dataset=str(DS),configuration=cfg,certificate=cert,validation=validation,
 existing_analyzer='existing_analyzer/summary.json',integrity=existing['integrity'],audit_operations=audit,source_integrity=sourcechecks,
 http=hfull,http_rows=hrows,computation=crows,workers=wrows,queue_peaks=peaks,residual=residual,resources=resources,
 tail_http=tail,boundary_crossings={str(t):[x['request_id'] for x in req if float(x['elapsed_seconds'])<t and x.get('end_elapsed_seconds') and float(x['end_elapsed_seconds'])>=t] for t in (30,60,150)},
 comparison_b2l=comparison,manifest_sha256=sha(DS/'dataset_manifest.json'),processor_sha256=sha(pathlib.Path(__file__)),baseline_manifest_sha256=baseline['manifest_sha256'])
dump('summary.json',summary)
print(json.dumps(dict(http=hrows,computation=crows,queue_peaks=peaks,residual=residual,resources=resources,tail=tail,audit_operations=len(audit)),indent=2))

# Explicit source-based classification: both classes use the same endpoint.
by_request={x['request_id']:x for x in req}
classification=[]
for e in sourceevents:
 if e['kind']=='http_started':
  own=by_request[e['request_id']]
  assert own['traffic_class']==sources[e['source_id']]
  assert own['generator']==('normal' if sources[e['source_id']]=='benign' else 'attack')
  assert own['run_id']==status['run_id'] and own['target_url'].endswith('/medium')
  classification.append(dict(source_id=e['source_id'],request_id=e['request_id'],traffic_class=own['traffic_class'],basis='source inventory + source diagnostic HTTP event + request_id + declared traffic_class'))
table('classification_evidence.csv',classification)
generator=[]
for sid in sources:
 ee=[e for e in sourceevents if e['source_id']==sid]
 sub={e['attempt_id']:e for e in ee if e['kind']=='submitted'}
 begun={e['attempt_id']:e for e in ee if e['kind']=='task_started'}
 backlog=0;peak=0
 for e in sorted(ee,key=lambda e:(e['at'],e['sequence'])):
  if e['kind']=='submitted':backlog+=1;peak=max(peak,backlog)
  elif e['kind']=='task_started':backlog-=1
 assert backlog==0
 delays=[(begun[k]['at']-v['at'])*1000 for k,v in sub.items() if k in begun]
 planned=[e for e in ee if e['kind']=='planned']
 ownjournal=[e for e in journals if e['source_id']==sid]
 generator.append(dict(source_id=sid,traffic_class=sources[sid],planned_records=len(planned) if planned else None,submitted=len(sub),task_started=len(begun),http_started=sum(e['kind']=='http_started' for e in ee),peak_submitted_not_started=peak,dispatch_ms=describe(delays),expired_before_http=sum(e['kind']=='task_resolution' and e['payload'].get('decision')=='expired_before_http' for e in ownjournal),admissions=sum(e['kind']=='admission' for e in ownjournal) if sources[sid]=='attack' else None))
dump('generator_behavior.json',generator)
for g in generator:
 if g['traffic_class']=='attack':
  assert g['admissions']==g['submitted']==g['http_started']+g['expired_before_http']
summary.update(generator_behavior=generator,classification_basis='source inventory and diagnostic request IDs; endpoint is not a class discriminator',nominal_rates=dict(legitimate=cfg['normal_traffic']['rate']*cfg['normal_traffic']['clients'],offensive=cfg['attack']['rate']*cfg['attack']['attackers']))
dump('summary.json',summary)

# Compare actual occupied task/HTTP positions with the original B2-F.
def occupied(ee,begin,end):
 ordered=sorted((e for e in ee if e['kind'] in (begin,end)),key=lambda e:(e['at'],e['sequence']))
 active=0;peak=0;area=0;last=origin+30
 for e in ordered:
  t=e['at'];delta=1 if e['kind']==begin else -1
  if t>=origin+30:
   area+=max(0,min(t,origin+60)-last)*active
   last=min(t,origin+60)
  active+=delta
  assert active>=0
  if origin+30<=t<origin+60:peak=max(peak,active)
 area+=max(0,origin+60-last)*active
 assert active==0
 return dict(peak_in_attack_window=peak,time_mean_in_attack_window=area/30)
concurrency=[]
references=[('B2-F',ROOT/'experiment_results/b2-f-20261108T000313Z/dataset'),('B2-F96',DS)]
for label,ds in references:
 rr=Reader(ds);meta=rr.json('diagnostics/metadata.json');saved_origin=origin;origin=meta['origin_monotonic']
 cc=rr.json('effective_config.json');inv=rr.json('source_inventory.json')
 for ss in inv:
  sid=ss['source_id'];ee=rr.lines('source_artifacts/'+sid+'/output/diagnostics/events.jsonl')
  cls='benign' if ss['source_type']=='normal' else 'attack'
  limit=cc['normal_traffic' if cls=='benign' else 'attack']['max_concurrent_sends']//2
  tasks=occupied(ee,'task_started','task_finished');http_occupancy=occupied(ee,'http_started','http_finished')
  assert tasks['peak_in_attack_window']<=limit and http_occupancy['peak_in_attack_window']<=limit
  concurrency.append(dict(execution=label,source_id=sid,traffic_class=cls,configured_positions=limit,task_occupancy=tasks,http_occupancy=http_occupancy))
 origin=saved_origin
dump('concurrency_observed.json',concurrency)
previous=json.loads((ROOT/'reports/b2-f-20261108T000313Z/summary.json').read_text())
oldcfg=previous['configuration'];check=json.loads(json.dumps(cfg));check['id']=oldcfg['id'];check['attack']['max_concurrent_sends']=64
assert check==oldcfg
assert cfg['attack']['max_concurrent_sends']==96 and cfg['attack']['rate']==32
assert previous['certificate']['images']==cert['images'] and previous['certificate']['limits']==cert['limits']
summary.update(concurrency_observed=concurrency,comparison_reference=dict(run_id=previous['run_id'],manifest_sha256=previous['manifest_sha256'],path=str(ROOT/'reports/b2-f-20261108T000313Z')),
 configuration_difference={'id':'new traceability identifier','attack.max_concurrent_sends':[64,96]})
dump('summary.json',summary)
