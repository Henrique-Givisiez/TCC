"""Derived summaries and audits; run after analisar.py; writes only here."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
s=pd.read_csv(P/'series_1s.csv');r=pd.read_csv(P/'recuperacao_execucao.csv');p=pd.read_csv(P/'metricas_periodo_execucao.csv')
rows=[];bounds=[];checks=[];atyp=[]
for rid,f in s.groupby('id',sort=False):
    sc=f.scenario.iloc[0];o=pd.read_csv(P/f'operacoes_{rid}.csv')
    raw=ROOT/'experiment_results/scientific-energy-powersaver-20261109/collection'/rid/'attempt-1/raw'
    ev=pd.read_csv(raw/'attack_events.csv')
    if len(ev):bounds.append(dict(id=rid,scenario=sc,**ev.iloc[0].to_dict()))
    for lo in range(30,390,10):
        g=f[(f.second>=lo)&(f.second<lo+10)];co=o[(o.s>=lo)&(o.s<lo+10)]
        d=dict(id=rid,scenario=sc,start=lo,relative=lo-150,pending_mean=g.pending.mean(),pending_end=g.pending_end.iloc[-1],running=g.running.mean(),two_fraction=g.two_fraction.mean(),success=g.benign_ok.sum()/g.benign_http_start.sum(),benign_starts=g.benign_http_start.sum(),benign_ok=g.benign_ok.sum(),benign_timeouts=g.benign_timeout.sum(),attack_admissions=g.attack_admissions.sum(),attack_source_submitted=g.attack_source_submitted.sum(),attack_expired=g.attack_expired.sum(),attack_http=g.attack_http_start.sum(),attack_received=g.attack_received.sum(),attack_operations=g.attack_submitted.sum(),completed=g.benign_completed.sum()+g.attack_completed.sum(),submitted=g.benign_submitted.sum()+g.attack_submitted.sum())
        for cls in ('benign','attack'):
            own=co[co.cls==cls];d[cls+'_wait_ms']=own.wait_ms.mean();d[cls+'_wait_p95_ms']=own.wait_ms.quantile(.95)
        rows.append(d)
    ac=f[(f.second>=150)&(f.second<270)]
    first=ac.iloc[:30];last=ac.iloc[-30:]
    checks.append(dict(id=rid,scenario=sc,pending_first30=first.pending.mean(),pending_last30=last.pending.mean(),pending_slope=np.polyfit(ac.second,ac.pending,1)[0],success_first30=first.benign_ok.sum()/first.benign_http_start.sum(),success_last30=last.benign_ok.sum()/last.benign_http_start.sum(),expired_first30=first.attack_expired.sum(),expired_last30=last.attack_expired.sum(),http_first30=first.attack_http_start.sum(),http_last30=last.attack_http_start.sum(),first_failed_second_relative=next((int(x.second)-150 for x in ac.itertuples() if x.benign_timeout>0),np.nan)))
    assert int(f.benign_submitted.sum()+f.attack_submitted.sum())==int(((o.s>=0)&(o.s<390)).sum())
    assert int(f.benign_completed.sum()+f.attack_completed.sum())==int(((o.u>=0)&(o.u<390)).sum())
    assert np.allclose(f.pending, f.waiting+f.running)
pd.DataFrame(rows).to_csv(P/'janelas_10s_execucao.csv',index=False)
pd.DataFrame(bounds).to_csv(P/'fronteiras_ofensivas.csv',index=False)
pd.DataFrame(checks).to_csv(P/'evolucao_active_execucao.csv',index=False)
for sc,g in r.groupby('scenario'):
    for metric in ('pending_peak','last_attack_completion_s','queue_return_start_s','availability_return_start_s','last_failed_post_start_s'):
        vals=g[metric].dropna()
        if not len(vals):continue
        q1,q3=vals.quantile([.25,.75]);iqr=q3-q1
        for _,x in g[(g[metric]<q1-1.5*iqr)|(g[metric]>q3+1.5*iqr)].iterrows():atyp.append(dict(id=x.id,scenario=sc,metric=metric,value=x[metric],q1=q1,q3=q3,lower=q1-1.5*iqr,upper=q3+1.5*iqr))
pd.DataFrame(atyp).to_csv(P/'atipicas_iqr.csv',index=False)
bad=r[r.operational_recovery==False]
ws=json.loads((P/'recuperacao_registrada.json').read_text());out=[]
for w in ws:
    m=w['metrics'];out.append(dict(id=w['id'],scenario=w['scenario'],start=m['start_seconds'],end=m['bin_end_seconds'],qualified=w['qualified'],success=m['success_fraction'],p95_ms=m['duration_2xx']['p95'],p95_limit=w['limits']['p95_ms_max'],failed_checks=','.join(k for k,v in w['service_checks'].items() if v is False),outcome_support=w['outcome_support'],duration_support=w['duration_support']))
pd.DataFrame(out).to_csv(P/'janelas_recuperacao_registrada.csv',index=False)
print('PERIOD MEANS');print(p.groupby(['scenario','phase'])[['benign_success','benign_duration_2xx_ms','pending_mean','pending_end','running_mean','two_fraction','cpu_percent','attack_http_start','attack_submitted','attack_admissions','attack_expired','attack_cpu_ms','benign_wait_ms']].mean().round(4).to_string())
print('RECOVERY');print(r.groupby('scenario').agg({c:['mean','median','min','max','std'] for c in ['pending_peak','peak_first_relative_s','last_attack_completion_s','last_attack_http_end_s','queue_return_start_s','availability_return_start_s','last_failed_post_start_s','last_failed_post_end_s','computed_after_timeout','worker_seconds_after_timeout','attack_completed_post','attack_started_post','attack_residual_worker_s','timeouts_ending_after_first_zero','timeouts_starting_after_first_zero']}).round(3).to_string())
print('UNCONFIRMED');print(bad.to_string(index=False));print('ATYPICAL');print(pd.DataFrame(atyp).to_string(index=False))
print('EVOLUTION');print(pd.DataFrame(checks).groupby('scenario').mean(numeric_only=True).round(3).to_string())
print('BOUNDARIES');print(pd.DataFrame(bounds).groupby('scenario')[['actual_end_seconds','stop_requested_seconds','last_request_start_seconds','drained_end_seconds']].agg(['mean','min','max']).to_string())
print('10S');print(pd.DataFrame(rows).groupby(['scenario','relative'])[['pending_mean','success','benign_wait_ms','attack_admissions','attack_http','attack_expired','submitted','completed']].mean().round(3).to_string())
manifest=json.loads((P/'manifesto_entradas.json').read_text()); changed=[]
for name,digest in manifest['inputs_sha256'].items():
    if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:changed.append(name)
assert not changed
(P/'verificacao.json').write_text(json.dumps(dict(input_hashes_rechecked=len(manifest['inputs_sha256']),changed=changed,executions=len(r),scenarios=r.scenario.value_counts().to_dict(),conservation=True,pending_equals_waiting_plus_running=True),indent=2))
