"""Reconcile previous operational aggregates with exact protocol windows."""
from pathlib import Path
import json
import pandas as pd
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
def find(x):
    if isinstance(x,dict):
        if 'recovery_confirmed' in x and 'recovery_windows' in x:return x
        for v in x.values():
            r=find(v)
            if r is not None:return r
    if isinstance(x,list):
        for v in x:
            r=find(v)
            if r is not None:return r
rows=[];ext=[]
for e in json.loads((ROOT/'experiments/protocols/energy-powersaver-20261109/plan.json').read_text())['entries']:
    if e['partition']!='TEST':continue
    raw=ROOT/'experiment_results/scientific-energy-powersaver-20261109/collection'/e['id']/'attempt-1/raw'
    op=find(json.loads((raw.parent/'receipt/manifest.json').read_text()))
    for phase in ('PRE','ACTIVE','POST'):
        m=op['phases'][phase];rows.append(dict(id=e['id'],scenario=e['scenario'],phase=phase,start=m['start_seconds'],end=m['bin_end_seconds'],success=m['success_fraction'],pending_http_benign=m['pending_at_end'],duration_2xx_ms=m['duration_2xx']['mean'],cpu_5s=op['scalars'][phase+'/mean_cpu_docker_percent']))
    ops=pd.read_csv(P/f'operacoes_{e["id"]}.csv');req=pd.read_csv(raw/'request_log.csv');http_ends=dict(zip(req.request_id,req.end_elapsed_seconds))
    post=req[(req.traffic_class=='benign')&(req.elapsed_seconds>=270)&(req.elapsed_seconds<390)]
    bad=post[post.http_status.fillna(0).astype(int).between(200,299)==False]
    last=bad.elapsed_seconds.max()
    ext.append(dict(id=e['id'],scenario=e['scenario'],last_bad_start_s=last-270,success_after_last_bad=int((post.elapsed_seconds>last).sum()) if len(bad) else len(post),ops_submitted_after_390=int((ops.s>=390).sum()),ops_completed_after_390=int((ops.u>=390).sum()),worker_work_after_timeout_s=ops.after_timeout_s.sum(),ops_worker_started_after_timeout=sum(1 for x in ops.itertuples() if x.after_timeout_s>0 and x.t>http_ends[x.request_id])))
pd.DataFrame(rows).to_csv(P/'conferencia_agregados_anteriores.csv',index=False);pd.DataFrame(ext).to_csv(P/'conferencia_caudas.csv',index=False)
numeric=pd.DataFrame(rows)
for c in ('start','end','success','pending_http_benign','duration_2xx_ms','cpu_5s'):numeric[c]=pd.to_numeric(numeric[c])
print(numeric.groupby(['scenario','phase']).mean(numeric_only=True).to_string())
print(pd.DataFrame(ext).groupby('scenario').mean(numeric_only=True).to_string())
print('LAST WINDOWS');w=pd.read_csv(P/'janelas_recuperacao_registrada.csv');print(w[(w.id.isin(['ps_direct80_043_A3','ps_direct80_075_F96']))].to_string(index=False))
