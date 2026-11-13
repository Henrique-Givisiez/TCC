#!/usr/bin/env python3
"""Extrai registros científicos oficiais, séries temporais e resumos; entradas somente leitura."""
from __future__ import annotations
import csv,hashlib,json
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'reports/scientific_campaign_visualization_20261112'
CAMP=ROOT/'experiment_results/scientific-energy-powersaver-20261109'
PLAN=ROOT/'experiments/protocols/energy-powersaver-20261109/plan.json'
FEATURES={'ingress_packet_count':('network','ingress_packet_count','Pacotes TCP/s'),
'ingress_tcp_payload_length_sum_bytes':('network','ingress_tcp_payload_length_sum_bytes','Payload TCP de entrada (bytes/s)'),
'request_starts':('service','request_starts','Inícios HTTP/s'),
'mean_duration_ms':('service','mean_duration_ms','Duração HTTP média (ms)'),
'mean_cpu_percent':('infrastructure','mean_cpu_percent','CPU em janela (%)')}
METHODS=['zscore','cov','ewma','cusum-freeze'];SCS={'L2':'Legítimo','A3':'Assimetria','F96':'Flooding'}
PHASES={'WARMUP':(0,30),'PRE':(30,150),'ACTIVE':(150,270),'POST':(270,390)}
OUT.joinpath('processed').mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def rel(p):return str(p.relative_to(ROOT))
def record(p,hashes):
 assert p.exists(),p
 hashes[rel(p)]=digest(p)
 return p
def number(x):return None if x is None else float(x)
def cls(row):
 if row.outcome=='response':return 'http_2xx' if 200<=row.http_status<300 else 'http_other'
 e=str(row.error_type).lower()
 if 'timeout' in e:return 'timeout'
 if 'connect' in e:return 'connection_failure'
 return 'other'
def phase(t):
 for p,(l,h) in PHASES.items():
  if l<=t<h:return p
 return 'OUTSIDE'
def process_worker(p,origin,ids):
 by=defaultdict(dict);clock=set();counts=Counter()
 with p.open() as f:
  for line in f:
   e=json.loads(line);kind=e.get('kind');cl=e.get('traffic_class')
   if kind not in ('work_submitted','work_started','work_completed') or cl not in ('benign','attack'):continue
   rid=e.get('request_id');op=e.get('operation_id');counts[(kind,cl)]+=1
   if rid not in ids or not op:continue
   by[op][kind]=e
   if kind=='work_completed':clock.add((e['worker_clock']['kind'],e['worker_clock']['time_namespace']))
 rows=[];event=[]
 for op,v in by.items():
  if set(v)!= {'work_submitted','work_started','work_completed'}:continue
  a,b,c=(v[k] for k in ('work_submitted','work_started','work_completed'))
  if not a['request_id']==b['request_id']==c['request_id']:continue
  submit=a['at']-origin;start=b['at']-origin;end=c['at']-origin
  if not (submit<=start<=end):continue
  rows.append((a['request_id'],a['traffic_class'],submit,start,end,1000*c['work_cpu_seconds'],1000*(start-submit),1000*(end-start)))
  event.extend([(submit,1,0),(start,-1,1),(end,0,-1)])
 work=pd.DataFrame(rows,columns=['request_id','traffic_class','submit_s','start_s','end_s','cpu_ms','wait_ms','execution_ms'])
 # Exact interval-integrated occupancy and waiting, summarized in one-second bins.
 event.sort(key=lambda x:x[0]);waiting=running=0;tprev=0.;wi=np.zeros(390);ru=np.zeros(390);two=np.zeros(390);wm=0;phase_max=Counter()
 def integrate(a,b):
  if b<=a:return
  a=max(a,0.);b=min(b,390.)
  while a<b:
   j=int(a);n=min(b,j+1)
   if j<390:
    wi[j]+=waiting*(n-a);ru[j]+=running*(n-a)
    if running==2:two[j]+=n-a
   a=n
 for t,dw,dr in event:
  integrate(tprev,t);waiting+=dw;running+=dr
  assert waiting>=0 and 0<=running<=2,(p,t,waiting,running)
  wm=max(wm,waiting);phase_max[phase(t)]=max(phase_max[phase(t)],waiting);tprev=t
 integrate(tprev,390)
 assert waiting==running==0
 return work,wi,ru,two,wm,phase_max,clock,counts

def main():
 hashes={};plan=read(record(PLAN,hashes));protocol=Path(plan['protocol']['path']);record(protocol,hashes)
 assert len(plan['entries'])==80
 inventory=[];signals=[];det=[];perf=[];infra=[];phase_rows=[];worksum=[];cal=[]
 # Freeze artifacts and candidate decisions are read, never fitted again.
 for feature in list(FEATURES)[:4]:
  base=CAMP/'analysis'/feature
  for kind in ['baseline','calibration','verification']:
   p=record(base/kind/'manifest.json',hashes);d=read(p)
   cal.append({'feature':feature,'stage':kind,'path':rel(p),'eligible':d.get('eligible',d.get('approved')),'thresholds':json.dumps(d.get('thresholds',{}),ensure_ascii=False),'pair_status':json.dumps(d.get('pair_status',{}),ensure_ascii=False),'candidates':json.dumps(d.get('candidates',[]),ensure_ascii=False)})
 for entry in plan['entries']:
  eid=entry['id'];part=entry['partition'];sc=entry['scenario'];run=CAMP/'collection'/eid/'attempt-1';ds=run/'dataset';fs=run/'features'
  cfg=read(record(ds/'metadata/effective_config.json',hashes));st=read(record(ds/'metadata/run_status.json',hashes));record(ds/'dataset_manifest.json',hashes);record(fs/'feature_manifest.json',hashes)
  assert cfg['duration_seconds']==390 and cfg['server']['process_pool_workers']==2 and st['status']=='completed' and st['end_reason']=='simulation_end'
  attack=cfg['attack'];normal=cfg['normal_traffic'];assert normal['clients']==2 and normal['rate']==8
  if sc=='L2':assert not attack['enabled']
  if sc=='A3':assert attack['enabled'] and attack['endpoint']=='/expensive' and attack['attackers']*attack['rate']==8
  if sc=='F96':assert attack['enabled'] and attack['endpoint']=='/medium' and attack['attackers']*attack['rate']==64 and attack['max_concurrent_sends']==96
  assert attack['start_seconds']==150 and attack['duration_seconds']==120
  inventory.append({'entry_id':eid,'partition':part,'scenario':sc,'block':entry.get('block'),'seed':entry['seed'],'run_id':st['run_id'],'status':st['status'],'path':rel(run),'duration_s':390,'attack_start_s':150 if attack['enabled'] else None,'attack_end_s':270 if attack['enabled'] else None,'legitimate_sources':2,'legitimate_nominal_rps':16,'attack_sources':attack['attackers'],'attack_nominal_rps':attack['attackers']*attack['rate'],'attack_endpoint':attack['endpoint'] if attack['enabled'] else None,'attack_concurrency':attack['max_concurrent_sends'] if attack['enabled'] else None,'workers':2,'detector_features':4 if part=='TEST' else 0,'cpu_detector_eligible':False})
  tables={}
  for family in ['network','service','infrastructure']:
   p=record(fs/'timeseries'/f'{family}.csv',hashes);x=pd.read_csv(p);assert len(x)>=390 and (x.window_index.to_numpy()==np.arange(len(x))).all();tables[family]=x
  for feature,(family,column,_) in FEATURES.items():
   x=tables[family];values=x[column].to_numpy()
   signals.extend((eid,part,sc,entry.get('block'),feature,int(j),float(v) if pd.notna(v) else None) for j,v in enumerate(values))
  if part!='TEST':continue
  reqpath=record(ds/'raw/service/request_log.csv',hashes);r=pd.read_csv(reqpath);r['http_status']=pd.to_numeric(r.http_status,errors='coerce');r['category']=r.apply(cls,axis=1)
  assert set(r.run_id)=={st['run_id']} and r.request_id.is_unique and (r.duration_ms>=0).all() and np.allclose(r.end_elapsed_seconds-r.elapsed_seconds,r.duration_ms/1000,atol=.003)
  origin=st['experiment_start_monotonic'];vp=record(ds/'evidence/other/diagnostics/victim/events.jsonl',hashes)
  w,waiting,running,two,wmax,phase_max,clocks,counts=process_worker(vp,origin,set(r.request_id));assert len(w)==len(r), (eid,len(w),len(r))
  assert len(clocks)==1 and next(iter(clocks))[0]=='CLOCK_MONOTONIC'
  statsraw=record(ds/'evidence/other/victim_stats.jsonl',hashes)
  stats=pd.DataFrame([{'t':x['received_seconds'],'cpu':number(x['cpu_percent']),'state':x['state']} for x in (json.loads(z) for z in statsraw.open()) if x.get('snapshot_received')])
  assert len(stats)>0 and stats.t.is_monotonic_increasing
  memraw=record(ds/'raw/infrastructure/simulation_metrics.csv',hashes);mem=pd.read_csv(memraw);mem=mem[(mem.num_instances==1)&(mem.active_containers_names=='target_instance_1')][['elapsed_seconds','mem_usage']].rename(columns={'elapsed_seconds':'t','mem_usage':'mem'});assert len(mem)>0 and mem.t.is_monotonic_increasing
  sec=pd.DataFrame({'entry_id':eid,'scenario':sc,'t':np.arange(390),'waiting_mean':waiting,'workers_mean':running})
  for cl in ['benign','attack']:
   z=r[r.traffic_class==cl];u=w[w.traffic_class==cl]
   for key,col,category in [('http_started','elapsed_seconds',None),('http_2xx','end_elapsed_seconds','http_2xx'),('http_timeout','end_elapsed_seconds','timeout'),('http_other','end_elapsed_seconds','other')]:
    zz=z if category is None else z[z.category==category] if category!='other' else z[~z.category.isin(['http_2xx','timeout'])]
    sec[f'{cl}_{key}']=np.histogram(zz[col],bins=np.arange(391))[0]
   for p,(l,h) in PHASES.items():
    rr=z[(z.elapsed_seconds>=l)&(z.elapsed_seconds<h)];ww=u[(u.submit_s>=l)&(u.submit_s<h)]
    phase_rows.append({'entry_id':eid,'scenario':sc,'block':entry['block'],'class':cl,'phase':p,'started':len(rr),'http_2xx_cohort':int((rr.category=='http_2xx').sum()),'timeout_cohort':int((rr.category=='timeout').sum()),'other_cohort':int((~rr.category.isin(['http_2xx','timeout'])).sum()),'duration_2xx_median_ms':rr.loc[rr.category=='http_2xx','duration_ms'].median(),'duration_2xx_p95_ms':rr.loc[rr.category=='http_2xx','duration_ms'].quantile(.95),'timeout_median_ms':rr.loc[rr.category=='timeout','duration_ms'].median(),'work_cpu_median_ms':ww.cpu_ms.median(),'work_wait_median_ms':ww.wait_ms.median(),'work_execution_median_ms':ww.execution_ms.median()})
   worksum.append({'entry_id':eid,'class':cl,'operations':len(u),'cpu_median_ms':u.cpu_ms.median(),'wait_median_ms':u.wait_ms.median(),'execution_median_ms':u.execution_ms.median()})
  for p,(l,h) in PHASES.items():
   z=stats[(stats.t>=l)&(stats.t<h)];zm=mem[(mem.t>=l)&(mem.t<h)];infra.append({'entry_id':eid,'scenario':sc,'block':entry['block'],'phase':p,'cpu_n':len(z),'cpu_mean':z.cpu.mean(),'cpu_median':z.cpu.median(),'cpu_max':z.cpu.max(),'mem_n':len(zm),'mem_mean_mib':zm.mem.mean(),'mem_median_mib':zm.mem.median(),'mem_max_mib':zm.mem.max(),'workers_two_fraction':float(np.mean(two[l:h])),'waiting_mean':float(np.mean(waiting[l:h])),'waiting_max_exact':phase_max[p]})
  sec.to_csv(OUT/'processed'/f'seconds_{eid}.csv',index=False);stats.to_csv(OUT/'processed'/f'docker_{eid}.csv',index=False);mem.to_csv(OUT/'processed'/f'memory_{eid}.csv',index=False)
  # HTTP individual distribution is preserved without raw duplication of identifiers.
  r[['traffic_class','elapsed_seconds','end_elapsed_seconds','duration_ms','category']].to_csv(OUT/'processed'/f'http_{eid}.csv',index=False)
  w[['traffic_class','submit_s','start_s','end_s','cpu_ms','wait_ms','execution_ms']].to_csv(OUT/'processed'/f'work_{eid}.csv',index=False)
  for feature in list(FEATURES)[:4]:
   p=record(CAMP/'analysis'/feature/'TEST'/eid/'manifest.json',hashes);d=read(p);assert d['source']['run_id']==st['run_id']
   ep=record(CAMP/'analysis'/feature/'evaluation'/eid/'manifest.json',hashes);ed=read(ep)
   h=read(CAMP/'analysis'/feature/'calibration/manifest.json')['thresholds']
   for method in METHODS:
    rr=d['methods'][method];assert len(rr)==len(tables[FEATURES[feature][0]])
    det.extend({'entry_id':eid,'scenario':sc,'block':entry['block'],'feature':feature,'method':method,'t':j+1,'value':number(tables[FEATURES[feature][0]].iloc[j][feature]),'score':number(v['score']),'decision':v['decision'],'threshold':number(h[method]),'candidate':number(v.get('candidate')),'posterior_state':number(v.get('posterior_state')),'update_accepted':v.get('update_accepted'),'unavailable_reason':v.get('unavailable_reason')} for j,v in enumerate(rr))
    ev=ed['results'][method]
    perf.append({'entry_id':eid,'scenario':sc,'block':entry['block'],'feature':feature,'method':method,'scientifically_evaluated':ev['scientifically_evaluated'],'event_detected':ev['event_detected'],'first_alarm_s':number(ev['first_detection_available_at_seconds']),'delay_s':number(ev['observed_delay_seconds']),'pre_fpr':number(ev['pre_fpr']),'fpr':number(ev['fpr']),'post_positive_fraction':number(ev['post_positive_fraction']),'post_positive_duration_s':number(ev['post_positive_duration_seconds']),'attack_positive_windows':ev['attack']['positive'],'pre_positive_windows':ev['pre']['positive'],'post_positive_windows':ev['post']['positive'],'decision_coverage':number(ev['decision_coverage'])})
  print(eid,'processed',flush=True)
 for name,rows in [('inventory',inventory),('signals',signals),('detectors',det),('performance',perf),('infrastructure',infra),('http_phases',phase_rows),('work_summary',worksum),('calibration',cal)]:
  if name=='signals':df=pd.DataFrame(rows,columns=['entry_id','partition','scenario','block','feature','window_index','value'])
  else:df=pd.DataFrame(rows)
  df.to_csv(OUT/('inventario_execucoes.csv' if name=='inventory' else 'processed/'+name+'.csv'),index=False)
 summary=read(record(CAMP/'analysis/summary/manifest.json',hashes))
 (OUT/'processed/official_summary.json').write_text(json.dumps({'results':summary['results'],'eligibility':summary['eligibility'],'operational':summary['operational'],'paired':summary['paired'],'ci':summary['ci']},ensure_ascii=False))
 (OUT/'validation/input_hashes.json').write_text(json.dumps(hashes,indent=2,ensure_ascii=False)+'\n')
 print('AUDIT',len(inventory),'runs',len(det),'detector windows',len(hashes),'hashed inputs')
if __name__=='__main__':main()
