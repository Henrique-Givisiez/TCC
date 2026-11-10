"""Additional offline source task/HTTP concurrency audit."""
from pathlib import Path
from collections import defaultdict
import json
import numpy as np
import pandas as pd
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
plan=json.loads((ROOT/'experiments/protocols/energy-powersaver-20261109/plan.json').read_text())
rows=[];per=[];timelines=[]
for e in plan['entries']:
    if e['partition']!='TEST':continue
    raw=ROOT/'experiment_results/scientific-energy-powersaver-20261109/collection'/e['id']/'attempt-1/raw'
    origin=json.loads((raw/'diagnostics/metadata.json').read_text())['origin_monotonic'];tasks=[]
    for src in json.loads((raw/'source_inventory.json').read_text()):
        folder=raw/'source_artifacts'/src['source_id']/'output';groups=defaultdict(dict);expires={}
        for line in (folder/'diagnostics/events.jsonl').open():
            v=json.loads(line)
            if v.get('attempt_id') is not None:groups[str(v['attempt_id'])][v['kind']]=v
        for line in (folder/'journal.jsonl').open():
            v=json.loads(line)
            if v['kind']=='task_resolution' and v['payload']['decision']=='expired_before_http':expires[str(v['payload']['admission_id'])]=v['payload']['elapsed_seconds']
        for aid,d in groups.items():
            if 'submitted' not in d:continue
            tasks.append(dict(cls=src['traffic_class'],source=src['source_id'],s=d['submitted']['at']-origin,t=d['task_started']['at']-origin,h=d['http_started']['at']-origin if 'http_started' in d else np.nan,u=d['task_finished']['at']-origin,he=d['http_finished']['at']-origin if 'http_finished' in d else np.nan,planned=d.get('planned',{}).get('planned_at',np.nan)-origin,expired=aid in expires,expired_at=expires.get(aid,np.nan)))
    df=pd.DataFrame(tasks);df['dispatch_ms']=(df.t-df.s)*1000;df['plan_to_http_ms']=(df.h-df.planned)*1000
    for cls,g in df.groupby('cls'):
        for lo in range(30,390,10):
            co=g[(g.s>=lo)&(g.s<lo+10)];hi=lo+10
            inflight=float(np.maximum(0,np.minimum(g.he,hi)-np.maximum(g.h,lo)).sum()/10)
            # peak with half-open intervals and grouped simultaneous deltas
            changes=defaultdict(int)
            for x in g.itertuples():
                if np.isfinite(x.h) and x.h<hi and x.he>lo:changes[max(lo,x.h)]+=1;changes[min(hi,x.he)]-=1
            peak=cur=0
            for _,delta in sorted(changes.items()):cur+=delta;peak=max(peak,cur)
            rows.append(dict(id=e['id'],scenario=e['scenario'],cls=cls,start=lo,relative=lo-150,submitted=len(co),http_cohort=int(co.h.notna().sum()),dispatch_ms=co.dispatch_ms.mean(),dispatch_p95_ms=co.dispatch_ms.quantile(.95),plan_to_http_ms=co.plan_to_http_ms.mean(),expired_cohort=int(co.expired.sum()),expired_in_window=int(((g.expired_at>=lo)&(g.expired_at<hi)).sum()),http_inflight_mean=inflight,http_inflight_peak=peak))
        per.append(dict(id=e['id'],scenario=e['scenario'],cls=cls,total_tasks=len(g),expired=int(g.expired.sum()),http=int(g.h.notna().sum()),first_expiry=g.expired_at.min(),last_expiry=g.expired_at.max(),max_dispatch_ms=g.dispatch_ms.max()))
    print(e['id'],flush=True)
pd.DataFrame(rows).to_csv(P/'fontes_janelas_10s.csv',index=False);pd.DataFrame(per).to_csv(P/'fontes_resumo_execucao.csv',index=False)
print(pd.DataFrame(per).groupby(['scenario','cls']).mean(numeric_only=True).round(3).to_string())
print(pd.DataFrame(rows).query('cls=="attack"').groupby(['scenario','relative'])[['dispatch_ms','expired_cohort','expired_in_window','http_inflight_mean','http_inflight_peak']].mean().round(3).to_string())
