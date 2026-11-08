import json,csv,hashlib
from pathlib import Path
from collections import Counter
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path('experiment_results/c1-2-cpu3-20261108');out=Path('reports/c1-2-cpu3-20261108')
def read(p):return json.loads(p.read_text())
def stats(v):
 a=np.array(v,dtype=float)
 return dict(n=len(a),min=float(a.min()),mean=float(a.mean()),median=float(np.median(a)),p95=float(np.percentile(a,95)),max=float(a.max())) if len(a) else dict(n=0)
rows=[json.loads(x) for x in (root/'raw/victim_stats.jsonl').read_text().splitlines()]
q=read(root/'features/cpu_quality.json');m=read(root/'features/feature_manifest.json');op=read(root/'raw/operational_policy.json')
with (root/'features/timeseries/infrastructure.csv').open() as f:cpu=[None if r['mean_cpu_percent']=='' else float(r['mean_cpu_percent']) for r in csv.DictReader(f)]
def coverage(a,b):
 v=cpu[a:b]; runs=[];n=0;cov=0;hist=0
 for i,x in enumerate(cpu[:b]):
  hist=hist+1 if x is not None else 0
  if i>=a:cov+=hist>=6
 for x in v+[0]:
  if x is None:n+=1
  elif n:runs.append(n);n=0
 valid=sum(x is not None for x in v)
 return dict(windows=len(v),valid=valid,missing=len(v)-valid,percent=100*valid/len(v),max_missing_run=max(runs,default=0),missing_runs=dict(Counter(runs)),potential=dict(zscore=valid,ewma=valid,cusum_freeze=valid,cov=cov))
with (root/'raw/request_log.csv').open() as f:req=list(csv.DictReader(f))
req=[r for r in req if 0<=float(r['elapsed_seconds'])<120]
with (root/'raw/simulation_metrics.csv').open() as f:ticks=list(csv.DictReader(f))
valid=[r for r in rows if r['state']=='valid'];endpoints=[]
for r in valid:
 a,b=map(float,r['interval_start_bounds']);c,d=map(float,r['interval_end_bounds']);k=round((a+b)/2)
 endpoints.append(dict(sequence=r['sequence'],alignment=max(abs(a-k),abs(b-k),abs(c-k-1),abs(d-k-1))<=.05,late=float(r['received_seconds'])>k+1,long=float(r['observed_interval_seconds'])>1.1))
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('raw','dataset','features') for p in (root/folder).rglob('*') if p.is_file()}
summary=dict(commit='848a8aef0a6809a04995f8217264cf2d1ee20a7b',run_id=m['source_run_id'],attempts=len(rows),snapshots=sum(r['snapshot_received'] for r in rows),fresh=sum(r['fresh'] for r in rows),valid_deltas=len(valid),missed=q['missed_opportunities'],states=dict(Counter(r['state'] for r in rows)),errors=dict(Counter(r['error'] for r in rows if r['error'])),call_seconds=stats([r['duration_seconds'] for r in rows]),calls_le_25ms=sum(r['duration_seconds']<=.025 for r in rows),interval_seconds=stats([r['observed_interval_seconds'] for r in valid]),delay_seconds=stats([r['delay_seconds'] for r in rows]),rejections=dict(Counter(r['reason'] for r in q['rejected'])),independent_alignment=dict(misaligned=sum(not r['alignment'] for r in endpoints),late=sum(r['late'] for r in endpoints),long=sum(r['long'] for r in endpoints)),coverage=dict(grid=coverage(0,len(cpu)),nominal=coverage(0,120),stabilized=coverage(30,120)),cpu=stats([x for x in cpu if x is not None]),above100=sum(x is not None and x>100 for x in cpu),zeros=sum(x==0 for x in cpu),http=dict(starts=len(req),rps=len(req)/120,success=sum(r['http_status'] and 200<=int(r['http_status'])<300 for r in req),outcomes=dict(Counter(r['outcome'] for r in req)),duration_ms=stats([r['duration_ms'] for r in req if r['duration_ms']])),tick_gaps=stats(np.diff([float(r['elapsed_seconds']) for r in ticks])),operational=dict(cleanup_verified=op['cleanup_verified'],progression_allowed=op['progression_allowed'],failures=op['failures'],shutdown=op['shutdown_steps']))
(out/'summary.json').write_text(json.dumps(summary,indent=2));(out/'hashes.json').write_text(json.dumps(hashes,indent=2));(out/'alignment.json').write_text(json.dumps(endpoints,indent=2))
fig,ax=plt.subplots(figsize=(11,3));ax.scatter(range(len(cpu)),[np.nan if x is None else x for x in cpu],s=10,label='CPU válida');missing=[i for i,x in enumerate(cpu) if x is None];ax.plot(missing,[0]*len(missing),'rx',label='Ausente (marcador, não CPU zero)');ax.set(xlabel='Janela (s)',ylabel='CPU % Docker');ax.legend();fig.tight_layout();fig.savefig(out/'cpu.png');print(json.dumps(summary,indent=2))
