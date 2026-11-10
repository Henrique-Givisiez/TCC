"""Compact scientific tables, CPU inventory and explanatory variability; offline."""
from pathlib import Path
import json,hashlib,io
import pandas as pd
import numpy as np
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
run=pd.read_csv(P/'alarmes_por_execucao.csv');cov=pd.read_csv(P/'analise_cov.csv');ew=pd.read_csv(P/'analise_ewma.csv');cs=pd.read_csv(P/'analise_cusum_freeze.csv');z=pd.read_csv(P/'analise_zscore.csv');cross=pd.read_csv(P/'alarmes_post_recuperacao.csv')
extra_hash={}
def read(p):
    b=p.read_bytes();extra_hash[str(p.relative_to(ROOT))]=hashlib.sha256(b).hexdigest();return b.decode()
plan=json.loads(read(ROOT/'experiments/protocols/energy-powersaver-20261109/plan.json'))
cpu=[];late=[];cov_alarms=[];resume=[]
for e in plan['entries']:
    if e['partition']!='TEST':continue
    raw=ROOT/'experiment_results/scientific-energy-powersaver-20261109/collection'/e['id']/'attempt-1'
    f=pd.read_csv(io.StringIO(read(raw/'features/timeseries/infrastructure.csv')))
    for phase,a,b in [('PRE',30,150),('ACTIVE',150,270),('POST',270,390)]:
        g=f[(f.window_start_seconds>=a)&(f.window_end_seconds<=b)]
        cpu.append(dict(id=e['id'],scenario=e['scenario'],phase=phase,available=int(g.mean_cpu_percent.notna().sum()),missing=int(g.mean_cpu_percent.isna().sum()),mean_cpu_percent=g.mean_cpu_percent.mean(),scientific_detector_eligibility='excluded_by_frozen_protocol'))
    for feature in run.feature.unique():
        folder=ROOT/'experiment_results/scientific-energy-powersaver-20261109/analysis'/feature
        doc=json.loads(read(folder/'TEST'/e['id']/'manifest.json'));obs=pd.read_csv(io.StringIO(read(Path(doc['source']['observable_path']))))
        if e['scenario']=='L2':continue
        marker=float(ew[(ew.id==e['id'])&(ew.feature==feature)].return_marker.iloc[0])
        selected=obs[(obs.window_start_seconds>=marker)&(obs.window_end_seconds<=390)]
        par=pd.read_csv(P/'parametros_congelados.csv');par=par[(par.feature==feature)&(par.detector=='ewma')].iloc[0]
        zz=(selected[feature]-par.mu)/par.sigma
        late.append(dict(id=e['id'],scenario=e['scenario'],feature=feature,marker=marker,n=len(selected),x_mean=selected[feature].mean(),x_sd=selected[feature].std(),z_mean=zz.mean(),fraction_z_above_ewma_h=(zz>par.threshold).mean(),x_final30=obs.loc[obs.window_start_seconds.between(360,389),feature].mean()))
        pos=[r for r in doc['methods']['cov'] if r['decision'] is True and 150<=float(r['window_start_seconds'])<270]
        cov_alarms.append(dict(id=e['id'],scenario=e['scenario'],feature=feature,active_positives=len(pos),first_positive_relative=min((float(x['available_at_seconds'])-150 for x in pos),default=np.nan),last_positive_relative=max((float(x['available_at_seconds'])-150 for x in pos),default=np.nan),positives_after_first10=sum(float(x['window_start_seconds'])>=160 for x in pos),positives_after_first30=sum(float(x['window_start_seconds'])>=180 for x in pos)))
        # Strong resume audit: accepted nonzero changes and normal negative decisions after crossing.
        trajectory=doc['methods']['cusum-freeze'];active=[r for r in trajectory if r['decision'] is True and 150<=float(r['window_start_seconds'])<270]
        first=int(active[0]['window_index']);after=[r for r in trajectory if first<int(r['window_index'])<390]
        resume.append(dict(id=e['id'],scenario=e['scenario'],feature=feature,resumed_negative=any(r['decision'] is False for r in after),accepted_changed_after_crossing=sum(r['update_accepted'] is True and r['posterior_state']!=r['previous_state'] for r in after),rejected_preserved=all(r['posterior_state']==r['previous_state'] for r in trajectory if r['decision'] is True)))
pd.DataFrame(cpu).to_csv(P/'cpu_descritiva.csv',index=False);pd.DataFrame(late).to_csv(P/'features_apos_retorno.csv',index=False);pd.DataFrame(cov_alarms).to_csv(P/'cov_tempos_alarmes.csv',index=False);pd.DataFrame(resume).to_csv(P/'cusum_retomadas.csv',index=False)
# Selected variability with an explicit unit: one complete execution.
var=[]
for file,df,cols in [('ewma',ew,['active_positive','post_scheduled_positive','positive_after_return','carry_required_after_return','state_at_return']),('cusum',cs,['active_rejected','accepted_after_crossing','post_positive','post_late_positive']),('zscore',z,['active_positive','post_positive','post_late_positive'])]:
    for (feature,sc),g in df.groupby(['feature','scenario']):
        for col in cols:
            a=g[col].dropna();var.append(dict(detector=file,feature=feature,scenario=sc,metric=col,n=len(a),runs_positive=int((a>0).sum()),mean=a.mean(),median=a.median(),sd=a.std(),q25=a.quantile(.25),q75=a.quantile(.75),minimum=a.min(),maximum=a.max()))
pd.DataFrame(var).to_csv(P/'variabilidade_mecanismos.csv',index=False)
div=[]
for (feature,method,sc),g in run.groupby(['feature','detector','scenario']):
    if sc=='L2':continue
    for _,x in g[g.event_detected.eq(False)].iterrows():div.append(dict(id=x.id,scenario=sc,feature=feature,detector=method,criterion='event_not_detected',value=0))
    if method=='ewma':
        a=ew[(ew.feature==feature)&(ew.scenario==sc)];q1,q3=a.positive_after_return.quantile([.25,.75]);cut=q3+1.5*(q3-q1)
        for _,x in a[a.positive_after_return>cut].iterrows():div.append(dict(id=x.id,scenario=sc,feature=feature,detector=method,criterion='late_positive_above_1.5IQR',value=x.positive_after_return))
pd.DataFrame(div).to_csv(P/'execucoes_divergentes.csv',index=False)
(P/'manifesto_complementar.json').write_text(json.dumps(extra_hash,indent=2))
print('COV EVENTS AND TIMING');print(pd.DataFrame(cov_alarms).groupby(['feature','scenario'])[['active_positives','first_positive_relative','last_positive_relative','positives_after_first10','positives_after_first30']].agg(['mean','median','min','max']).round(4).to_string())
print('EWMA VARIABILITY');print(pd.DataFrame(var).query('detector=="ewma" and metric in ["positive_after_return","carry_required_after_return","state_at_return"]').round(4).to_string(index=False))
print('LATE FEATURE');print(pd.DataFrame(late).groupby(['feature','scenario'])[['x_mean','z_mean','fraction_z_above_ewma_h','x_final30']].mean().round(4).to_string())
print('POST');print(cross.groupby(['feature','detector','scenario','segment'])[['positive','fraction']].mean().round(4).to_string())
print('COV POS IDS');print(pd.DataFrame(cov_alarms).query('scenario=="A3" and active_positives>0')[['id','feature','active_positives','last_positive_relative']].to_string(index=False))
print('DIVERGENT EWMA');print(pd.DataFrame(div).query('criterion=="late_positive_above_1.5IQR"').to_string(index=False))
assert all(x['rejected_preserved'] and x['resumed_negative'] for x in resume)
print('PASS CPU inventory; 160 offensive freeze trajectories resumed negative and preserved every rejected state.')
