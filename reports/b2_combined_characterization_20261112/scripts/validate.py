#!/usr/bin/env python3
"""Validação independente dos resumos, arquivos e figuras da B2."""
from pathlib import Path
import csv,hashlib,json
import numpy as np,pandas as pd
from PIL import Image,ImageStat
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'reports/b2_combined_characterization_20261112'
M=json.loads((OUT/'manifest.json').read_text());S=pd.read_csv(OUT/'processed/summary.csv');P=pd.read_csv(OUT/'processed/phase_summary.csv');I=pd.read_csv(OUT/'processed/infrastructure_summary.csv');INV=pd.read_csv(OUT/'inventario_execucoes.csv')
checks={};details={}
def check(name,ok,detail=None):
 checks[name]=bool(ok)
 if detail is not None:details[name]=detail
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
check('input_hashes_preserved',all((ROOT/p).exists() and sha(ROOT/p)==v for p,v in M['inputs_sha256'].items()),len(M['inputs_sha256']))
check('script_hashes',all(sha(OUT/p)==v for p,v in M['scripts_sha256'].items()))
check('seven_runs_inventory',len(INV)==7 and set(INV.id)=={'A1-L2','B1-A3','B1-F2','B2-L','B2-A','B2-F','B2-F96'})
check('configs_and_states',all(INV.status=='completed') and all(INV.workers==2) and all(INV.duration_s==150) and list(INV.loc[INV.id.isin(['B2-A','B2-F','B2-F96']),'attack_nominal_rps'])==[8,64,64])
row=[];classes=[];outcomes=[];timing=[];workchecks=[];statschecks=[];phasechecks=[];clockchecks=[]
for _,inv in INV.iterrows():
 k=inv.id;raw=ROOT/inv.path/'raw';r=pd.read_csv(raw/'request_log.csv');w=pd.read_csv(OUT/'processed'/f'work_{k}.csv');st=pd.read_csv(OUT/'processed'/f'stats_{k}.csv');rr=pd.read_csv(OUT/'processed'/f'requests_{k}.csv')
 status=json.loads((raw/'run_status.json').read_text());origin=status['experiment_start_monotonic']
 source_paths=list((raw/'source_artifacts').glob('*/output/diagnostics/events.jsonl'))
 starts={}
 for sp in source_paths:
  for line in sp.open():
   e=json.loads(line)
   if e['kind']=='http_started':starts[e['request_id']]=e['at']-origin
 clockchecks.append(set(starts)==set(r.request_id) and all(abs(starts[z.request_id]-z.elapsed_seconds)<.01 for z in r.itertuples()))
 if k!='A1-L2':
  kinds=set();namespaces=set()
  for line in (raw/'diagnostics/victim/events.jsonl').open():
   e=json.loads(line)
   if e['kind']=='work_completed' and e.get('traffic_class') in ('benign','attack'):
    kinds.add(e['worker_clock']['kind']);namespaces.add(e['worker_clock']['time_namespace'])
  clockchecks.append(kinds=={'CLOCK_MONOTONIC'} and len(namespaces)==1)
 row.append(len(r)==inv.request_rows and len(r)==len(rr)==len(w)==r.request_id.nunique()==w.request_id.nunique())
 classes.append(set(r.traffic_class).issubset({'benign','attack'}) and set(r.request_id)==set(w.request_id) and all(rr.traffic_class==r.traffic_class))
 outcomes.append(all(rr.category.isin(['HTTP 2xx','Outro HTTP','Timeout','Falha de conexão','Outro encerramento'])) and len(rr)==rr.category.value_counts().sum())
 timing.append((r.duration_ms>=0).all() and np.allclose(r.end_elapsed_seconds-r.elapsed_seconds,r.duration_ms/1000,atol=.003))
 workchecks.append(((w['start']>=w.submit)&(w.finish>=w['start'])&(w.cpu_ms>=0)&(w.wait_ms>=0)).all())
 statschecks.append((st.cpu>=0).all() and (st.mem>=0).all() and st.t.is_monotonic_increasing and len(st)==inv.victim_stats_samples)
 for cl in ['benign','attack']:
  sr=S[(S.id==k)&(S['class']==cl)].iloc[0];z=rr[(rr.traffic_class==cl)&(rr.elapsed_seconds>=30)&(rr.elapsed_seconds<60)]
  row.append(sr.total_started==(rr.traffic_class==cl).sum() and sr.started_active==len(z) and np.isclose(sr.rps_started_active,len(z)/30))
  outcomes.append(sr.http_2xx_active_cohort==(z.category=='HTTP 2xx').sum() and sr.timeouts_active_cohort==(z.category=='Timeout').sum() and sr.http_2xx_active_cohort+sr.timeouts_active_cohort+sr.other_active_cohort==len(z))
  classes.append(sr.submitted_not_http>=0)
  for ph,l,h in [('PRE',0,30),('ACTIVE',30,60),('POST',60,150)]:
   pp=P[(P.id==k)&(P['class']==cl)&(P.phase==ph)]
   if len(pp):phasechecks.append(pp.iloc[0].started==((rr.traffic_class==cl)&(rr.elapsed_seconds>=l)&(rr.elapsed_seconds<h)).sum())
check('clock_alignment_and_namespace',all(clockchecks));check('request_counts_match_raw',all(row));check('class_and_id_consistency',all(classes));check('exclusive_outcomes_and_timeouts',all(outcomes));check('http_duration_consistency',all(timing));check('worker_event_order_nonnegative',all(workchecks));check('docker_units_and_cadence',all(statschecks));check('phase_boundaries',all(phasechecks))
check('occupancy_range_and_fraction',all((I.workers_zero_fraction_active>=0)&(I.workers_one_fraction_active>=0)&(I.workers_two_fraction_active>=0)&(I.workers_two_fraction_active<=1)&np.isclose(I.workers_zero_fraction_active+I.workers_one_fraction_active+I.workers_two_fraction_active,1)))
check('waiting_nonnegative',all((I.waiting_max_active>=0)&(I.waiting_max_post>=0)&(I.waiting_max_full>=0)))
check('source_http_and_submission_separate',all(S.submitted_not_http>=0) and S.loc[(S.id=='B2-F')&(S['class']=='attack'),'submitted_not_http'].iloc[0]==191 and S.loc[(S.id=='B2-F96')&(S['class']=='attack'),'submitted_not_http'].iloc[0]==308)
check('b2_traffic_classes',all(INV.loc[INV.id.isin(['B2-L','B2-A','B2-F','B2-F96']),'legitimate_sources']==2) and all(INV.loc[INV.id.isin(['B2-L','B2-A','B2-F','B2-F96']),'legitimate_nominal_rps']==16))
check('figure_manifest_count',M['figure_count']==len(M['figures']) and len(M['figures'])>=40)
visual=[]
for f in M['figures']:
 p=OUT/(f['path']+'.png');q=OUT/(f['path']+'.pdf')
 if not p.exists() or not q.exists():visual.append(False);continue
 try:
  with Image.open(p) as im:
   im.verify()
  with Image.open(p) as im:
   width,height=im.size;std=ImageStat.Stat(im.convert('RGB')).stddev
  visual.append(width>=1200 and height>=900 and max(std)>5 and q.stat().st_size>1000 and q.open('rb').read(4)==b'%PDF')
 except Exception:visual.append(False)
check('png_pdf_nonempty_and_decodable',all(visual),{'valid':sum(visual),'total':len(visual)})
check('report_catalog', (OUT/'relatorio.md').exists() and all(Path(f['path']).stem in (OUT/'relatorio.md').read_text() for f in M['figures']))
result={'all_passed':all(checks.values()),'passed':sum(checks.values()),'total':len(checks),'checks':checks,'details':details}
(OUT/'validation/checks.json').write_text(json.dumps(checks,indent=2,ensure_ascii=False)+'\n')
(OUT/'validation/result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(result,indent=2,ensure_ascii=False))
if not result['all_passed']:raise SystemExit(1)
