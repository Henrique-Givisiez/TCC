"""Publication tables and HTTP duration cohorts, offline."""
from pathlib import Path
import json
import pandas as pd
import numpy as np
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
r=pd.read_csv(P/'recuperacao_execucao.csv');p=pd.read_csv(P/'metricas_periodo_execucao.csv');rows=[]
for x in r.itertuples():
    raw=ROOT/'experiment_results/scientific-energy-powersaver-20261109/collection'/x.id/'attempt-1/raw'
    q=pd.read_csv(raw/'request_log.csv');q=q[q.traffic_class=='benign'];ok=q.http_status.between(200,299)
    for lo in range(30,390,10):
        co=q[q.elapsed_seconds.between(lo,lo+10,inclusive='left')];good=co[co.http_status.between(200,299)]
        rows.append(dict(id=x.id,scenario=x.scenario,start=lo,relative=lo-150,starts=len(co),ok=len(good),success=len(good)/len(co),duration_2xx_ms=good.duration_ms.mean(),duration_all_ms=co.duration_ms.mean(),duration_2xx_p95_ms=good.duration_ms.quantile(.95)))
pd.DataFrame(rows).to_csv(P/'http_legitimo_janelas_10s.csv',index=False)
tables=[]
for sc,g in r.groupby('scenario'):
    for c in ('pending_peak','first_waiting_zero_s','last_attack_completion_s','queue_return_start_s','availability_return_start_s','last_failed_post_start_s'):
        a=g[c].dropna()
        tables.append(dict(scenario=sc,variable=c,n=len(a),mean=a.mean(),median=a.median(),sd=a.std(),q25=a.quantile(.25),q75=a.quantile(.75),min=a.min(),max=a.max()))
pd.DataFrame(tables).to_csv(P/'tabela_variabilidade.csv',index=False)
print(pd.DataFrame(rows).query('relative>=0').groupby(['scenario','relative'])[['duration_2xx_ms','duration_all_ms']].mean().round(2).to_string())
print('SOURCE RATES');f=pd.read_csv(P/'fontes_resumo_execucao.csv').query('cls=="attack"');f['expired_fraction']=f.expired/f.total_tasks
print(f.groupby('scenario')[['total_tasks','http','expired','expired_fraction','max_dispatch_ms']].agg(['mean','median','std','min','max']).round(4).to_string())
