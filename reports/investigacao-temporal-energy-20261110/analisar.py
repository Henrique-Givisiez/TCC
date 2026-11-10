"""Offline only. Reads raw TEST evidence; writes solely beside this script.
Run from repository root: .venv/bin/python -B reports/investigacao-temporal-energy-20261110/analisar.py
"""
from pathlib import Path
import csv, json, hashlib, sys
from collections import defaultdict, Counter
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'experiment_results/scientific-energy-powersaver-20261109'
hashes={}
def read(p):
    b=p.read_bytes(); hashes[str(p.relative_to(ROOT))]=hashlib.sha256(b).hexdigest(); return b.decode()
def js(p): return json.loads(read(p))
def jl(p): return [json.loads(s) for s in read(p).splitlines() if s]
def table(p): return list(csv.DictReader(read(p).splitlines()))
def mean(a): return float(np.mean(a)) if len(a) else np.nan
def quant(a,q): return float(np.quantile(a,q)) if len(a) else np.nan
def count(times): return np.histogram(times,bins=np.arange(391))[0]
def intervals(pairs):
    # Exact integration, peak and two-slot fraction, not sampling approximations.
    changes=defaultdict(int)
    for a,b in pairs:
        assert b>=a
        if b>0 and a<390 and b>a:
            changes[max(0.,a)]+=1; changes[min(390.,b)]-=1
    for i in range(391): changes[float(i)]+=0
    area=np.zeros(390); peak=np.zeros(390); two=np.zeros(390); cur=0; prev=0.
    for t,d in sorted(changes.items()):
        if t>prev:
            i=min(int(prev),389); area[i]+=cur*(t-prev); peak[i]=max(peak[i],cur)
            if cur==2: two[i]+=t-prev
        cur+=d; assert cur>=0; prev=t
    assert cur==0
    return area,peak,two
def find_op(x):
    if isinstance(x,dict):
        if 'recovery_confirmed' in x and 'recovery_windows' in x:return x
        for v in x.values():
            r=find_op(v)
            if r is not None:return r
    if isinstance(x,list):
        for v in x:
            r=find_op(v)
            if r is not None:return r
    return None
def complete(es,ss):
    assert ss['complete'] and not ss['dropped'] and not ss['write_errors'] and ss['written']==len(es)
    assert [e['sequence'] for e in es]==list(range(1,len(es)+1))
def rec15(v,limit):
    for j in range(24-2):
        if all(np.isfinite(v[k]) and v[k]<=limit for k in range(j,j+3)):return j*5
    return np.nan

entries=[e for e in js(ROOT/'experiments/protocols/energy-powersaver-20261109/plan.json')['entries'] if e['partition']=='TEST']
assert Counter(e['scenario'] for e in entries)=={'L2':20,'A3':20,'F96':20}
series=[]; phases=[]; runs=[]; recoveries=[]; evidence=[]; source_recs=[]; windows=[]; clocks=[]
for entry in entries:
    rid=entry['id']; sc=entry['scenario']; raw=BASE/'collection'/rid/'attempt-1/raw'
    cfg=js(raw/'effective_config.json'); meta=js(raw/'diagnostics/metadata.json'); origin=meta['origin_monotonic']
    assert cfg['duration_seconds']==390 and cfg['attack']['start_seconds']==150 and cfg['attack']['duration_seconds']==120
    for cp in ('diagnostics/victim_clock_validation.json','source_artifacts/clock_validation.json'):
        cv=js(raw/cp);assert cv['comparable']
        for src in cv['sources']:
            for s in src['samples']:
                assert s['checks']['comparable']
                clocks.append(dict(id=rid,component=cp,bracket_s=s['bracket_width_seconds'],zero_offset=s['checks'].get('zero_offsets_native_process_proof'),namespace_equal=s['checks'].get('namespace_equal')))
    req=table(raw/'request_log.csv'); requests={r['request_id']:r for r in req}; assert len(requests)==len(req)
    for r in req:
        r['h']=float(r['elapsed_seconds']);r['end']=float(r['end_elapsed_seconds']) if r['end_elapsed_seconds'] else np.nan
        r['ok']=bool(r['http_status']) and 200<=int(r['http_status'])<300
        r['timeout']='Timeout' in r['error_type'];r['dur']=float(r['duration_ms']) if r['duration_ms'] else np.nan
    es=jl(raw/'diagnostics/victim/events.jsonl'); ss=js(raw/'diagnostics/victim/events.summary.json');complete(es,ss);assert ss['observation_complete']
    own=defaultdict(dict); handlers=[]
    for e in es:
        if e['kind']=='handler_started' and e.get('traffic_class') in ('benign','attack'): handlers.append(e)
        if e['kind'] in ('work_submitted','work_started','work_completed','work_failed'):
            assert e['kind'] not in own[e['operation_id']]; own[e['operation_id']][e['kind']]=e
    ops=[]; unknown=0
    for oid,d in own.items():
        assert set(d)=={'work_submitted','work_started','work_completed'}
        s,t,u=[d[k] for k in ('work_submitted','work_started','work_completed')]
        if s.get('traffic_class') not in ('benign','attack'):
            unknown+=1;assert u['work_finished_at']<origin;continue
        rr=requests[s['request_id']]
        assert rr['traffic_class']==s['traffic_class'] and rr['run_id']==s['run_id']
        assert s['at']<=t['at']<=u['work_started_at']<=u['work_finished_at']
        o=dict(id=rid,scenario=sc,operation_id=oid,request_id=s['request_id'],cls=s['traffic_class'],s=s['at']-origin,t=t['at']-origin,u=u['work_finished_at']-origin,cpu_ms=u['work_cpu_seconds']*1000)
        o['wait_ms']=(o['t']-o['s'])*1000;o['after_timeout_s']=max(0.,o['u']-max(o['t'],rr['end'])) if rr['timeout'] else 0.
        ops.append(o)
        if o['after_timeout_s']>0 and len([x for x in evidence if x['id']==rid])<5:
            evidence.append(dict(**o,http_start=rr['h'],http_timeout=rr['end']))
    assert len({o['request_id'] for o in ops})==len(ops)
    tasks=[]; admissions=[]; snapshots=[]
    for src in js(raw/'source_inventory.json'):
        folder=raw/'source_artifacts'/src['source_id']/'output';se=jl(folder/'diagnostics/events.jsonl');complete(se,js(folder/'diagnostics/events.summary.json'))
        journal=jl(folder/'journal.jsonl');assert [e['sequence'] for e in journal]==list(range(1,len(journal)+1))
        binding=[e['payload'] for e in journal if e['kind']=='run_binding'][0];assert binding['monotonic']==origin
        expired=set();td=defaultdict(dict)
        for e in journal:
            if e['kind']=='admission':admissions.append(e['payload']['elapsed_seconds'])
            if e['kind']=='task_resolution' and e['payload']['decision']=='expired_before_http':expired.add(str(e['payload']['admission_id']))
            if e['kind']=='event_snapshot':snapshots.append(dict(id=rid,source=src['source_id'],**e['payload']))
        for e in se:
            if e.get('attempt_id') is not None:td[str(e['attempt_id'])][e['kind']]=e
        for aid,d in td.items():
            if set(d)=={'planned'}:continue  # next planned arrival may fall after collection ends
            assert {'submitted','task_started','task_finished'}<=set(d)
            tasks.append(dict(cls=src['traffic_class'],s=d['submitted']['at']-origin,t=d['task_started']['at']-origin,h=d['http_started']['at']-origin if 'http_started' in d else None,expired=aid in expired))
        for kind in ('planned','submitted','task_started','http_started'):
            times=[(e.get('planned_at') if kind=='planned' else e['at'])-origin for e in se if e['kind']==kind]
            ar=count(times)
            for i,n in enumerate(ar):source_recs.append(dict(id=rid,scenario=sc,source=src['source_id'],cls=src['traffic_class'],second=i,kind=kind,count=n))
    # Number of source HTTP starts must equal request log, avoiding task/HTTP conflation.
    assert sum(t['h'] is not None for t in tasks)==len(req)
    a=np.array([o['s'] for o in ops]);t=np.array([o['t'] for o in ops]);u=np.array([o['u'] for o in ops]);oc=np.array([o['cls'] for o in ops])
    pending,pk,_=intervals(zip(a,u));running,rpk,two=intervals(zip(t,u));waiting,wpk,_=intervals(zip(a,t));assert max(rpk)<=2
    frame=pd.DataFrame(dict(id=rid,scenario=sc,second=np.arange(390),relative=np.arange(390)-150,pending=pending,pending_peak=pk,running=running,two_fraction=two,waiting=waiting))
    frame['pending_end']=[int(np.sum((a<b)&(u>=b))) for b in range(1,391)]
    for cls in ('benign','attack'):
        mask=oc==cls
        for name,ar in [('submitted',a),('started',t),('completed',u)]:frame[f'{cls}_{name}']=count(ar[mask])
        frame[f'{cls}_received']=count([e['at']-origin for e in handlers if e['traffic_class']==cls])
        rr=[r for r in req if r['traffic_class']==cls]
        for name,key,pred in [('http_start','h',lambda r:True),('ok','h',lambda r:r['ok']),('timeout','h',lambda r:r['timeout']),('terminal_ok','end',lambda r:r['ok']),('terminal_timeout','end',lambda r:r['timeout'])]:
            frame[f'{cls}_{name}']=count([r[key] for r in rr if pred(r)])
        frame[f'{cls}_success']=frame[f'{cls}_ok']/frame[f'{cls}_http_start'].replace(0,np.nan)
        frame[f'{cls}_duration_2xx_ms']=[mean([r['dur'] for r in rr if r['ok'] and i<=r['h']<i+1]) for i in range(390)]
        frame[f'{cls}_duration_all_ms']=[mean([r['dur'] for r in rr if i<=r['h']<i+1]) for i in range(390)]
        frame[f'{cls}_wait_ms']=[mean([o['wait_ms'] for o in ops if o['cls']==cls and i<=o['s']<i+1]) for i in range(390)]
        frame[f'{cls}_source_submitted']=count([x['s'] for x in tasks if x['cls']==cls])
        frame[f'{cls}_expired']=count([x['s'] for x in tasks if x['cls']==cls and x['expired']])
    frame['attack_admissions']=count(admissions)
    cpu=jl(raw/'victim_stats.jsonl');cs=js(raw/'victim_stats.summary.json')
    frame['cpu_percent']=np.nan
    for i in range(390):frame.loc[i,'cpu_percent']=mean([float(x['cpu_percent']) for x in cpu if x['state']=='valid' and i<=x['received_seconds']<i+1])
    receipt=js(raw.parent/'receipt/manifest.json');op=find_op(receipt);assert op is not None
    for w in op['recovery_windows']:windows.append(dict(id=rid,scenario=sc,**w))
    for name,lo,hi in [('PRE',30,150),('ACTIVE',150,270),('POST',270,390)]:
        f=frame.iloc[lo:hi]
        d=dict(id=rid,scenario=sc,phase=name,pending_mean=mean(f.pending),pending_end=int(np.sum((a<hi)&(u>=hi))),pending_peak=max(f.pending_peak),running_mean=mean(f.running),two_fraction=mean(f.two_fraction),waiting_mean=mean(f.waiting),cpu_percent=mean(f.cpu_percent.dropna()))
        for cls in ('benign','attack'):
            rr=[r for r in req if r['traffic_class']==cls and lo<=r['h']<hi];co=[o for o in ops if o['cls']==cls and lo<=o['s']<hi]
            for col in ('http_start','ok','timeout','received','submitted','started','completed','source_submitted','expired'):d[f'{cls}_{col}']=int(f[f'{cls}_{col}'].sum())
            d[f'{cls}_success']=sum(r['ok'] for r in rr)/len(rr) if rr else np.nan
            d[f'{cls}_duration_2xx_ms']=mean([r['dur'] for r in rr if r['ok']]);d[f'{cls}_duration_all_ms']=mean([r['dur'] for r in rr])
            d[f'{cls}_wait_ms']=mean([o['wait_ms'] for o in co]);d[f'{cls}_wait_p95_ms']=quant([o['wait_ms'] for o in co],.95);d[f'{cls}_cpu_ms']=mean([o['cpu_ms'] for o in co])
        d['attack_admissions']=int(f.attack_admissions.sum());phases.append(d)
    atk=[o for o in ops if o['cls']=='attack'];bt=[r for r in req if r['traffic_class']=='benign'];post=[r for r in bt if 270<=r['h']<390]
    pre_limit=quant(pending[30:150],.95)
    p5=[mean(pending[i:i+5]) for i in range(270,390,5)]
    s5=[sum(r['ok'] for r in post if i<=r['h']<i+5)/max(1,sum(i<=r['h']<i+5 for r in post)) for i in range(270,390,5)]
    qreturn=rec15(p5,pre_limit);sreturn=rec15([1-v for v in s5],.01)
    end_attack=max((o['u'] for o in atk),default=np.nan)
    failures=[r for r in post if not r['ok']]
    zero_candidates=sorted(set([270.]+[float(v) for v in t if 270<=v<390]))
    firstzero=next((v for v in zero_candidates if np.sum((a<=v)&(t>v))==0),np.nan)
    rec=dict(id=rid,scenario=sc,operational_recovery=op['recovery_confirmed'],pre_pending_p95_1s=pre_limit,queue_return_start_s=qreturn,queue_return_confirm_s=qreturn+15,availability_return_start_s=sreturn,availability_return_confirm_s=sreturn+15,first_waiting_zero_s=firstzero-270,
        last_attack_completion_s=end_attack-270,attack_completed_post=sum(o['u']>=270 for o in atk),attack_started_post=sum(o['t']>=270 for o in atk),attack_residual_worker_s=sum(max(0,o['u']-max(270,o['t'])) for o in atk),
        last_attack_http_end_s=max((r['end']-270 for r in req if r['traffic_class']=='attack'),default=np.nan),last_attack_http_start_s=max((r['h']-270 for r in req if r['traffic_class']=='attack'),default=np.nan),
        post_timeout_cohorts=len(failures),last_failed_post_start_s=max((r['h']-270 for r in failures),default=np.nan),last_failed_post_end_s=max((r['end']-270 for r in failures),default=np.nan),
        timeouts_ending_after_first_zero=sum(r['timeout'] and r['end']>firstzero for r in bt),timeouts_starting_after_first_zero=sum(r['timeout'] and r['h']>firstzero for r in bt),
        computed_after_timeout=sum(o['after_timeout_s']>0 for o in ops),worker_seconds_after_timeout=sum(o['after_timeout_s'] for o in ops),
        attack_pending_end=int(np.sum((a<270)&(u>=270)&(oc=='attack'))),pending_peak=float(max(pk)),peak_first_relative_s=int(np.argmax(pk))-150,unknown_setup_ops=unknown)
    recoveries.append(rec);runs.append(dict(id=rid,scenario=sc,block=entry['block'],operations=len(ops),http=len(req),handler_received=len(handlers),cpu_valid=sum(x['state']=='valid' for x in cpu),**{'cpu_summary':cs}))
    series.append(frame)
    # Preserve exact event times for recovery audits without copying full raw data.
    pd.DataFrame(ops).to_csv(OUT/f'operacoes_{rid}.csv',index=False)
    pd.DataFrame(snapshots).to_csv(OUT/f'eventos_ataque_{rid}.csv',index=False)
    print(rid, 'ok',flush=True)

allseries=pd.concat(series,ignore_index=True);ph=pd.DataFrame(phases);rec=pd.DataFrame(recoveries)
allseries.to_csv(OUT/'series_1s.csv',index=False);ph.to_csv(OUT/'metricas_periodo_execucao.csv',index=False);rec.to_csv(OUT/'recuperacao_execucao.csv',index=False)
pd.DataFrame(evidence).to_csv(OUT/'evidencias_timeout_identidade.csv',index=False)
pd.DataFrame(clocks).to_csv(OUT/'auditoria_relogios.csv',index=False)
pd.DataFrame(source_recs).to_csv(OUT/'series_fontes_1s.csv',index=False)
(OUT/'recuperacao_registrada.json').write_text(json.dumps(windows,indent=2))
(OUT/'integridade_execucoes.json').write_text(json.dumps(runs,indent=2))
def aggregate(df,group):
    cols=[c for c in df.select_dtypes(include='number').columns if c not in group and c not in ('second','relative')]
    return df.groupby(group)[cols].agg(['count','mean','median','std',lambda x:x.quantile(.25),lambda x:x.quantile(.75),'min','max']).rename(columns={'<lambda_0>':'q25','<lambda_1>':'q75'})
aggregate(ph,['scenario','phase']).to_csv(OUT/'resumo_periodos.csv')
aggregate(rec,['scenario']).to_csv(OUT/'resumo_recuperacao.csv')
aggregate(allseries,['scenario','second','relative']).to_csv(OUT/'series_agregadas_1s.csv')
# Non-overlapping 5 s cohorts, per execution first.
b=allseries.copy();b['bin']=b.second//5
five=b.groupby(['id','scenario','bin']).agg(second=('second','min'),pending=('pending','mean'),running=('running','mean'),two_fraction=('two_fraction','mean'),starts=('benign_http_start','sum'),ok=('benign_ok','sum')) .reset_index()
five['success']=five.ok/five.starts.replace(0,np.nan);five['relative']=five.second-150;five.to_csv(OUT/'coortes_5s.csv',index=False)
colors={'L2':'#377eb8','A3':'#d95f02','F96':'#228833'}
plt.rcParams.update({'font.size':10,'svg.fonttype':'none'})
def band(ax,data,col,sc):
    z=data[data.scenario==sc].groupby('relative')[col];x=z.mean().index.to_numpy();ax.step(x,z.mean(),where='post',label=f'{sc} (n=20)',color=colors[sc],lw=1.2);ax.fill_between(x,z.quantile(.25),z.quantile(.75),step='post',color=colors[sc],alpha=.17)
def decorate(ax,post=False):
    ax.axvline(0,color='k',lw=.7);ax.axvline(120,color='k',lw=.7);ax.axvspan(0,120,color='#aaaaaa',alpha=.08)
    ax.set_xlim((120,240) if post else (-120,240));ax.grid(alpha=.2);ax.set_xlabel('Tempo relativo ao início ofensivo (s)')
    if post:ax.text(.03,.95,'POST',transform=ax.transAxes,va='top')
    else:
        for x,label in [(-60,'PRE'),(60,'ACTIVE'),(180,'POST')]:ax.text(x,.97,label,transform=ax.get_xaxis_transform(),ha='center',va='top')
def save(fig,name):
    fig.tight_layout();fig.savefig(OUT/(name+'.png'),dpi=190);fig.savefig(OUT/(name+'.svg'));plt.close(fig)
fig,ax=plt.subplots(figsize=(10,4));
for sc in colors:band(ax,allseries[allseries.second>=30],'pending',sc)
decorate(ax);ax.set_ylabel('Operações pendentes (média temporal / 1 s)');ax.legend(loc='upper left');fig.suptitle('Pendências computacionais — média entre execuções e IQR');save(fig,'figura1_pendencias')
fig,ax=plt.subplots(figsize=(10,4))
for sc in colors:band(ax,five[five.second>=30],'success',sc)
decorate(ax);ax.set_ylim(-.02,1.08);ax.set_ylabel('2xx / inícios HTTP legítimos (coorte de 5 s)');ax.legend(loc='lower left');fig.suptitle('Disponibilidade por coorte de início — média e IQR');save(fig,'figura2_disponibilidade')
fig,axs=plt.subplots(2,1,figsize=(10,6),sharex=True)
for sc in colors:
    band(axs[0],allseries[allseries.second>=30],'running',sc);band(axs[1],allseries[allseries.second>=30],'cpu_percent',sc)
for ax in axs:decorate(ax)
axs[0].set_ylabel('Slots ocupados / 2');axs[1].set_ylabel('CPU Docker (%)');axs[0].legend(loc='lower left');fig.suptitle('Ocupação e CPU — média e IQR, resolução nativa');save(fig,'figura3_ocupacao')
fig,axs=plt.subplots(2,1,figsize=(10,6),sharex=True)
for sc in ('A3','F96'):
    band(axs[0],allseries[allseries.second>=270],'pending',sc);band(axs[1],five[five.second>=270],'success',sc)
for ax in axs:decorate(ax,True)
axs[0].set_ylabel('Operações pendentes');axs[1].set_ylabel('Sucesso legítimo (coorte 5 s)');axs[1].set_ylim(-.02,1.08);axs[0].legend();fig.suptitle('Recuperação após fim programado da emissão (t=120 s) — média e IQR');save(fig,'figura4_recuperacao')
(OUT/'manifesto_entradas.json').write_text(json.dumps(dict(inputs_sha256=hashes,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),python=sys.version,numpy=np.__version__,pandas=pd.__version__,matplotlib=matplotlib.__version__,runs=entries),indent=2))
print('DONE',len(entries),flush=True)
