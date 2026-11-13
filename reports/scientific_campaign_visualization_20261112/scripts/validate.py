#!/usr/bin/env python3
"""Verificações independentes de entradas, processamento, decisões e figuras."""
from pathlib import Path
import hashlib,json
from decimal import Decimal
import numpy as np,pandas as pd
from PIL import Image,ImageStat
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'reports/scientific_campaign_visualization_20261112';PR=OUT/'processed'
INV=pd.read_csv(OUT/'inventario_execucoes.csv');S=pd.read_csv(PR/'signals.csv');D=pd.read_csv(PR/'detectors.csv');P=pd.read_csv(PR/'performance.csv');I=pd.read_csv(PR/'infrastructure.csv');H=pd.read_csv(PR/'http_phases.csv');CAT=pd.read_csv(OUT/'catalogo_figuras.csv');M=json.loads((OUT/'manifest.json').read_text());OFF=json.loads((PR/'official_summary.json').read_text());checks={};details={}
def ck(n,v,detail=None):
 checks[n]=bool(v)
 if detail is not None:details[n]=detail
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
ck('input_files_unchanged',all((ROOT/p).exists() and sha(ROOT/p)==h for p,h in M['input_sha256'].items()),len(M['input_sha256']))
ck('script_hashes',all(sha(OUT/p)==h for p,h in M['script_sha256'].items()))
ck('inventory_80_complete',len(INV)==80 and INV.entry_id.is_unique and set(INV.status)=={'completed'} and INV.groupby('partition').size().to_dict()=={'BASELINE':4,'CAL_A':8,'CAL_B':8,'TEST':60})
ck('test_blocks_20x3',INV[INV.partition=='TEST'].groupby('block').scenario.agg(lambda x:sorted(x)).apply(lambda x:x==['A3','F96','L2']).all())
ck('effective_configs',all(INV.duration_s==390) and all(INV.workers==2) and all(INV.legitimate_nominal_rps==16) and set(INV.loc[INV.scenario=='A3','attack_nominal_rps'])=={8} and set(INV.loc[INV.scenario=='F96','attack_nominal_rps'])=={64})
ck('five_signal_rows',len(S)==80*5*391 and S.groupby(['entry_id','feature']).size().eq(391).all() and set(S.feature)=={'ingress_packet_count','ingress_tcp_payload_length_sum_bytes','request_starts','mean_duration_ms','mean_cpu_percent'})
ck('four_official_detector_signals',len(D)==60*4*4*391 and len(P)==60*4*4 and set(D.feature)==set(S.feature)-{'mean_cpu_percent'} and set(D.method)=={'zscore','cov','ewma','cusum-freeze'})
ck('detector_time_and_threshold',D.groupby(['entry_id','feature','method']).t.agg(['min','max','count']).eq({'min':1,'max':391,'count':391}).all().all() and (D.threshold>=0).all())
x=D[D.decision.notna()].copy();x['decision']=x.decision.astype(bool)
mismatch=x[x.decision.to_numpy()!=(x.score.to_numpy()>x.threshold.to_numpy())]
exact_match=True
for row in mismatch.itertuples():
 source=ROOT/'experiment_results/scientific-energy-powersaver-20261109/analysis'/row.feature/'TEST'/row.entry_id/'manifest.json'
 calibration=ROOT/'experiment_results/scientific-energy-powersaver-20261109/analysis'/row.feature/'calibration/manifest.json'
 try:
  original=json.loads(source.read_text())['methods'][row.method][row.t-1]
  threshold=json.loads(calibration.read_text())['thresholds'][row.method]
  exact_match &= original['decision']==(Decimal(original['score'])>Decimal(threshold))==row.decision
 except (OSError,KeyError,IndexError,ValueError):exact_match=False
ck('alarm_matches_score_and_threshold',exact_match,{'float_rounding_ties_checked_against_official_decimal':len(mismatch)})
c=D[D.method=='cusum-freeze'];z=c[c.decision.notna()];ck('cusum_freeze_rejection',bool((z.loc[z.decision==True,'update_accepted']==False).all() and (z.loc[z.decision==False,'update_accepted']==True).all() and (z.loc[z.decision==True,'posterior_state']<=z.loc[z.decision==True,'threshold']).all()))
ck('missing_scores_preserved',D.score.isna().sum()>0 and D.loc[D.score.isna(),'decision'].isna().all() and S[(S.feature=='mean_cpu_percent')].value.isna().sum()>0)
ck('worker_and_http_conservation',all((H.http_2xx_cohort+H.timeout_cohort+H.other_cohort)==H.started) and all(I.workers_two_fraction.between(0,1)) and all(I.waiting_mean>=0) and all(I.waiting_max_exact>=0))
def two_worker_fraction_from_operations(entry_id):
 work=pd.read_csv(PR/f'work_{entry_id}.csv')
 events=[]
 for row in work.itertuples():
  start=max(150.,row.start_s);end=min(270.,row.end_s)
  if end>start:events.extend([(start,1),(end,-1)])
 events.sort();occupied=0;previous=150.;duration=0.
 for time,change in events:
  if occupied==2:duration+=time-previous
  occupied+=change;previous=time
  if not 0<=occupied<=2:return float('nan')
 return duration/120.
selected=pd.read_csv(PR/'selected_runs.csv')
ck('worker_fraction_exact_spotcheck',all(np.isclose(two_worker_fraction_from_operations(e),I[(I.entry_id==e)&(I.phase=='ACTIVE')].workers_two_fraction.iloc[0],atol=1e-8) for e in selected.entry_id),len(selected))
ck('docker_memory_nonnegative',all(I.cpu_mean.dropna()>=0) and all(I.mem_mean_mib.dropna()>=0) and all(I.cpu_n>0) and all(I.mem_n>0))
ck('official_detection_agreement',all(np.isclose(P[(P.scenario==sc)&(P.feature==f)&(P.method==m)].event_detected.mean(),OFF['results'][f'{f}/{sc}/{m}']['detection']['estimate']) for sc in ['A3','F96'] for f in set(D.feature) for m in set(D.method)))
ck('selected_runs_in_inventory',set(pd.read_csv(PR/'selected_runs.csv').entry_id).issubset(set(INV.entry_id)))
ck('catalog_complete',len(CAT)==M['figure_count'] and CAT.path.is_unique and CAT[['id','group','path','question','sources','type']].notna().all().all())
actual_png={str(p.relative_to(OUT)) for p in (OUT/'figures').rglob('*.png')}
actual_pdf={str(p.relative_to(OUT)) for p in (OUT/'figures').rglob('*.pdf')}
ck('catalog_matches_all_figures',set(CAT.path)==actual_png and {str((OUT/p).with_suffix('.pdf').relative_to(OUT)) for p in CAT.path}==actual_pdf,{'catalog':len(CAT),'png':len(actual_png),'pdf':len(actual_pdf)})
visual=[]
for p in CAT.path:
 png=OUT/p;pdf=png.with_suffix('.pdf')
 try:
  with Image.open(png) as im:im.verify()
  with Image.open(png) as im:
   size=im.size;std=ImageStat.Stat(im.convert('RGB')).stddev
  visual.append(size[0]>=1000 and size[1]>=900 and max(std)>3 and pdf.exists() and pdf.stat().st_size>1000 and pdf.open('rb').read(4)==b'%PDF')
 except Exception:visual.append(False)
ck('png_pdf_integrity',all(visual),{'valid':sum(visual),'total':len(visual)})
ck('report_and_readme',(OUT/'relatorio.md').exists() and (OUT/'README.md').exists() and 'CUSUM-freeze' in (OUT/'relatorio.md').read_text())
result={'all_passed':all(checks.values()),'passed':sum(checks.values()),'total':len(checks),'checks':checks,'details':details}
(OUT/'validation/checks.json').write_text(json.dumps(checks,indent=2,ensure_ascii=False)+'\n');(OUT/'validation/result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
if result['all_passed']:
 CAT['validated']='automated_pass'
 CAT.to_csv(OUT/'catalogo_figuras.csv',index=False)
print(json.dumps(result,indent=2,ensure_ascii=False))
if not result['all_passed']:raise SystemExit(1)
