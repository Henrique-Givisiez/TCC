#!/usr/bin/env python3
"""Análise complementar, somente leitura nas fontes da campanha."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'reports/investigacao_recuperacao_pos_ataque_20261113'
SRC = ROOT / 'reports/scientific_campaign_visualization_20261112'
CAMP = ROOT / 'experiment_results/scientific-energy-powersaver-20261109'
POST = [(f'POST-{j+1}', 270+30*j, 300+30*j) for j in range(4)]
PHASES = [('WARMUP',0,30),('PRE',30,150),('ACTIVE',150,270),('POST',270,390)]
COLORS = {'L2':'#4277aa','A3':'#c75537','F96':'#6a9b50'}
METRICS = ['ingress_packet_count','ingress_tcp_payload_length_sum_bytes','request_starts',
           'mean_duration_ms','cpu_feature_mean','cpu_snapshot_mean','workers_two_fraction',
           'waiting_mean','waiting_max_exact','benign_started','benign_completed',
           'attack_started','attack_completed']

def save(frame, name):
    frame.to_csv(OUT/'processed'/name, index=False, float_format='%.10g')

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''): h.update(chunk)
    return h.hexdigest()

def exact_queue(work, lo, hi):
    """Maximum at event times, including left edge; completed records provide full lifecycle."""
    events=[]
    for x in work.itertuples():
        events.extend(((x.submit_s,1,0),(x.start_s,-1,1),(x.end_s,0,-1)))
    events.sort(key=lambda e:e[0]); w=r=0
    maximum=int(((work.submit_s<lo)&(work.start_s>=lo)).sum());at270=None
    for at,dw,dr in events:
        if at >= lo and at270 is None: at270=(w,r)
        if at >= hi: break
        w+=dw;r+=dr
        if at>=lo:maximum=max(maximum,w)
    return maximum,at270

def recovery(seconds):
    # PRE-specific threshold fixed before examining POST: 95th percentile of
    # one-second time-integrated PRE queue, at least one operation.
    baseline=max(1.,float(np.quantile(seconds.loc[seconds.t.between(30,149),'waiting_mean'],.95)))
    post=seconds.loc[seconds.t.between(270,389),'waiting_mean'].to_numpy()
    candidates=[i for i in range(111) if np.all(post[i:i+10]<=baseline)]
    return baseline, (270+candidates[0] if candidates else np.nan), not bool(candidates)

def main():
    (OUT/'processed').mkdir(parents=True,exist_ok=True)
    (OUT/'figures').mkdir(parents=True,exist_ok=True)
    inventory=pd.read_csv(SRC/'inventario_execucoes.csv')
    inv=inventory[inventory.partition.eq('TEST')].copy()
    assert len(inv)==60 and set(inv.scenario)=={'L2','A3','F96'}
    assert inv.groupby('block').scenario.nunique().eq(3).all() and inv.block.nunique()==20
    signals=pd.read_csv(SRC/'processed/signals.csv')
    signals=signals[signals.partition.eq('TEST')]
    sig={(eid,feature):g.set_index('window_index').value.reindex(range(390))
         for (eid,feature),g in signals.groupby(['entry_id','feature'])}
    input_paths=[SRC/'inventario_execucoes.csv', SRC/'processed/signals.csv']
    rows=[]; queue_rows=[]; legit_rows=[]; cpu_rows=[]; daily=[]; cpu_rejections=[]
    for e in inv.itertuples():
        eid=e.entry_id; base=SRC/'processed'; raw=CAMP/'collection'/eid/'attempt-1/features/cpu_quality.json'
        paths=[base/f'{kind}_{eid}.csv' for kind in ('seconds','work','http','docker')]+[raw]
        input_paths.extend(paths)
        sec,work,http,docker=(pd.read_csv(p) for p in paths[:4])
        quality=json.loads(raw.read_text())
        assert len(sec)==390 and len(sig[eid,'request_starts'])==390
        assert len(work)==len(http)
        work['traffic_class']=work.traffic_class.astype(str)
        for cl in ('benign','attack'):
            w=work[work.traffic_class.eq(cl)]
            queue_rows.append(dict(entry_id=eid,scenario=e.scenario,block=int(e.block),
                point='270',traffic_class=cl,waiting=int(((w.submit_s<270)&(w.start_s>=270)).sum()),
                running=int(((w.start_s<270)&(w.end_s>=270)).sum()),
                active_submitted_post_waiting=int(((w.submit_s>=150)&(w.submit_s<270)&(w.start_s>=270)).sum()),
                active_submitted_post_running=int(((w.submit_s>=150)&(w.submit_s<270)&(w.start_s<270)&(w.end_s>=270)).sum()),
                active_started_post_running=int(((w.start_s>=150)&(w.start_s<270)&(w.end_s>=270)).sum())))
            for point in (300,330,360,390):
                queue_rows.append(dict(entry_id=eid,scenario=e.scenario,block=int(e.block),point=str(point),traffic_class=cl,
                    waiting=int(((w.submit_s<point)&(w.start_s>=point)).sum()),
                    running=int(((w.start_s<point)&(w.end_s>=point)).sum())))
        threshold,rt,censored=recovery(sec)
        daily.append(dict(entry_id=eid,scenario=e.scenario,block=int(e.block),pre_p95_waiting=threshold,
                          recovery_s=rt,recovery_delay_s=rt-270 if not censored else np.nan,
                          right_censored=censored,waiting_at_390=int(((work.submit_s<390)&(work.start_s>=390)).sum())))
        for name,lo,hi in POST:
            ss=sec.iloc[lo:hi]; hh=http; dd=docker[docker.t.ge(lo)&docker.t.lt(hi)]
            qmax,_=exact_queue(work,lo,hi)
            d=dict(entry_id=eid,scenario=e.scenario,block=int(e.block),interval=name,start_s=lo,end_s=hi,
                   waiting_mean=ss.waiting_mean.mean(),waiting_max_exact=qmax)
            # Recompute exact fraction of two workers from interval overlap,
            # via union of pairwise worker execution segments.
            active=work[(work.start_s<hi)&(work.end_s>lo)]
            ev=[]
            for x in active.itertuples(): ev.extend([(max(lo,x.start_s),1),(min(hi,x.end_s),-1)])
            ev.sort(); running=0;last=lo;two=0.
            for at,change in ev:
                if running==2: two+=at-last
                running+=change;last=at
            d['workers_two_fraction']=two/(hi-lo)
            for feature in ('ingress_packet_count','ingress_tcp_payload_length_sum_bytes','request_starts','mean_duration_ms','mean_cpu_percent'):
                vals=sig[eid,feature].iloc[lo:hi]
                key='cpu_feature_mean' if feature=='mean_cpu_percent' else feature
                d[key]=vals.mean() if feature in ('mean_duration_ms','mean_cpu_percent') else vals.sum(min_count=1)
                d[key+'_valid_windows']=int(vals.notna().sum())
                d[key+'_coverage']=float(vals.notna().mean())
            valid=dd.cpu.dropna();d['cpu_snapshot_mean']=valid.mean();d['cpu_snapshot_valid']=len(valid)
            d['cpu_snapshot_coverage']=len(valid)/30 # snapshots per nominal 30 s; can exceed 1
            for cl in ('benign','attack'):
                z=hh[hh.traffic_class.eq(cl)]
                d[cl+'_started']=int(z.elapsed_seconds.ge(lo).mul(z.elapsed_seconds.lt(hi)).sum())
                d[cl+'_completed']=int(z.end_elapsed_seconds.ge(lo).mul(z.end_elapsed_seconds.lt(hi)).sum())
            rows.append(d)
            for cl in ('benign','attack'):
                z=hh[hh.traffic_class.eq(cl)]
                cohort=z[z.elapsed_seconds.ge(lo)&z.elapsed_seconds.lt(hi)]
                finished=z[z.end_elapsed_seconds.ge(lo)&z.end_elapsed_seconds.lt(hi)]
                n2=int(cohort.category.eq('http_2xx').sum())
                legit_rows.append(dict(entry_id=eid,scenario=e.scenario,block=int(e.block),interval=name,
                    traffic_class=cl,started=len(cohort),completed=len(finished),
                    cohort_completed=int(cohort.end_elapsed_seconds.notna().sum()),median_ms=cohort.duration_ms.median(),
                    p95_ms=cohort.duration_ms.quantile(.95),http_2xx=n2,
                    rate_2xx=n2/len(cohort) if len(cohort) else np.nan,
                    timeouts=int(cohort.category.eq('timeout').sum()),
                    other_errors=int((~cohort.category.isin(['http_2xx','timeout'])).sum()),
                    active_started_post_completed=int(((z.elapsed_seconds>=150)&(z.elapsed_seconds<270)&
                                                       (z.end_elapsed_seconds>=lo)&(z.end_elapsed_seconds<hi)).sum())))
        for phase,lo,hi in PHASES:
            feat=sig[eid,'mean_cpu_percent'].iloc[lo:hi]
            snap=docker[docker.t.ge(lo)&docker.t.lt(hi)]
            cpu_rows.append(dict(entry_id=eid,scenario=e.scenario,block=int(e.block),phase=phase,
                feature_valid=int(feat.notna().sum()),feature_coverage=feat.notna().mean(),
                feature_mean=feat.mean(),snapshot_count=int(snap.cpu.notna().sum()),
                snapshot_mean=snap.cpu.mean(),snapshots_total=int(len(snap)),
                attempts=quality['attempts'],fresh=quality['fresh_snapshots'],
                valid_deltas=quality['valid_deltas'],missed_opportunities=quality['missed_opportunities']))
        for item in quality['rejected']:
            ix=item.get('window_index'); phase=next((p for p,a,b in PHASES if ix is not None and a<=ix<b),'OUTSIDE')
            cpu_rejections.append(dict(entry_id=eid,scenario=e.scenario,block=int(e.block),phase=phase,
                                       window_index=ix,reason=item['reason']))
        # Five-second run summaries keep independent-run variability in figures.
        for lo in range(140,390,5):
            s=sec.iloc[lo:lo+5]; hz=http[(http.traffic_class=='benign')&
                http.elapsed_seconds.ge(lo)&http.elapsed_seconds.lt(lo+5)]
            daily.append(dict(entry_id=eid,scenario=e.scenario,block=int(e.block),kind='trace',t=lo+2.5,
                waiting_mean=s.waiting_mean.mean(),benign_median_ms=hz.duration_ms.median(),
                workers_two_fraction=np.nan))
    per=pd.DataFrame(rows);legit=pd.DataFrame(legit_rows);queue=pd.DataFrame(queue_rows)
    rec=pd.DataFrame([r for r in daily if 'recovery_s' in r]); trace=pd.DataFrame([r for r in daily if r.get('kind')=='trace'])
    # Add completion-window mean duration from scientific features and exact occupancy.
    for e in inv.itertuples():
        eid=e.entry_id; sec=pd.read_csv(SRC/'processed'/f'seconds_{eid}.csv')
        for lo in range(140,390,5):
            ix=(trace.entry_id==eid)&(trace.t==lo+2.5)
            trace.loc[ix,'mean_duration_ms']=sig[eid,'mean_duration_ms'].iloc[lo:lo+5].mean()
            w=pd.read_csv(SRC/'processed'/f'work_{eid}.csv') if lo==140 else w
            events=[]
            for x in w[(w.start_s<lo+5)&(w.end_s>lo)].itertuples():
                events.extend(((max(lo,x.start_s),1),(min(lo+5,x.end_s),-1)))
            events.sort();run=0;last=lo;two=0
            for at,delta in events:
                if run==2:two+=at-last
                run+=delta;last=at
            trace.loc[ix,'workers_two_fraction']=two/5
    save(per,'post_por_execucao.csv');save(legit,'http_por_execucao.csv')
    http_summary=[]
    for (sc,interval,cl),g in legit.groupby(['scenario','interval','traffic_class']):
        for metric in ('started','completed','median_ms','p95_ms','rate_2xx','timeouts','other_errors',
                       'active_started_post_completed'):
            z=g[metric].dropna()
            http_summary.append(dict(scenario=sc,interval=interval,traffic_class=cl,metric=metric,
                                     mean=z.mean(),sd=z.std(ddof=1),n_valid=len(z),coverage=len(z)/20))
    save(pd.DataFrame(http_summary),'http_resumo.csv')
    save(queue,'filas_instantes_por_execucao.csv');save(rec,'recuperacao_por_execucao.csv')
    save(trace,'tracos_5s_por_execucao.csv')
    cpu=pd.DataFrame(cpu_rows);reject=pd.DataFrame(cpu_rejections)
    save(cpu,'cpu_cobertura_por_execucao_fase.csv');save(reject,'cpu_rejeicoes.csv')
    summary=[]
    for (scenario,interval),g in per.groupby(['scenario','interval']):
        for metric in METRICS:
            z=g[metric].dropna()
            coverage=g[metric+'_coverage'].mean() if metric+'_coverage' in g else (g.cpu_snapshot_coverage.mean() if metric=='cpu_snapshot_mean' else 1.)
            summary.append(dict(scenario=scenario,interval=interval,metric=metric,mean=z.mean(),sd=z.std(ddof=1),
                                n_valid=len(z),coverage=coverage))
    save(pd.DataFrame(summary),'post_resumo.csv')
    contrasts=[];pairs=[]
    for interval in per.interval.unique():
        p=per[per.interval.eq(interval)].set_index(['block','scenario'])
        for metric in METRICS:
            for a,b in [('A3','L2'),('F96','L2'),('A3','F96')]:
                x=p.xs(a,level='scenario')[metric]-p.xs(b,level='scenario')[metric]
                z=x.dropna();n=len(z);se=z.std(ddof=1)/np.sqrt(n) if n>1 else np.nan
                mean=z.mean(); margin=student_t.ppf(.975,n-1)*se if n>1 else np.nan
                contrasts.append(dict(interval=interval,metric=metric,contrast=f'{a} − {b}',n=n,mean=mean,
                                      sd=z.std(ddof=1),ci95_low=mean-margin,ci95_high=mean+margin))
                pairs.extend(dict(interval=interval,metric=metric,contrast=f'{a} − {b}',block=int(k),difference=v)
                             for k,v in z.items())
    save(pd.DataFrame(contrasts),'contrastes_pareados.csv');save(pd.DataFrame(pairs),'contrastes_por_bloco.csv')
    # CPU coverage and rejection summaries, including acquisition versus assignment.
    save(cpu.groupby(['scenario','phase'],as_index=False).agg(feature_coverage_mean=('feature_coverage','mean'),
        feature_coverage_sd=('feature_coverage','std'),feature_mean_between_runs=('feature_mean','mean'),
        snapshot_mean_between_runs=('snapshot_mean','mean'),snapshot_count_mean=('snapshot_count','mean'),
        n=('entry_id','count')),'cpu_resumo.csv')
    save(reject.groupby(['scenario','phase','reason'],as_index=False).size().rename(columns={'size':'n'}),'cpu_rejeicoes_resumo.csv')
    # Figure A: three aligned axes; each point is the run mean over five seconds.
    plt.rcParams.update({'font.size':10,'axes.grid':True,'grid.alpha':.2})
    fig,axes=plt.subplots(3,1,figsize=(11,10),sharex=True,layout='constrained')
    for ax,(col,label) in zip(axes,[('mean_duration_ms','Duração HTTP média das conclusões (ms)'),
                                    ('waiting_mean','Operações aguardando (média)'),
                                    ('workers_two_fraction','Tempo com dois workers ocupados (fração)')]):
        for sc in ('L2','A3','F96'):
            z=trace[trace.scenario.eq(sc)].groupby('t')[col].agg(['mean','std','count'])
            ax.plot(z.index,z['mean'],color=COLORS[sc],label=sc)
            sem=z['std']/np.sqrt(z['count']);ax.fill_between(z.index,z['mean']-1.96*sem,z['mean']+1.96*sem,
                                                               color=COLORS[sc],alpha=.15)
        ax.axvline(270,color='black',ls='--',lw=1);ax.set_ylabel(label);ax.legend(ncol=3)
    axes[-1].set_xlabel('Tempo desde o início da execução (s)')
    fig.suptitle('B1-A — Recuperação pós-ataque; média de 20 execuções ± 1,96 erro padrão')
    for ext in ('png','pdf'):fig.savefig(OUT/'figures'/f'b1_a_recuperacao.{ext}',dpi=180)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,4.5),layout='constrained')
    for sc in ('L2','A3','F96'):
        z=trace[trace.scenario.eq(sc)].groupby('t').benign_median_ms.agg(['mean','std','count'])
        ax.plot(z.index,z['mean'],label=sc,color=COLORS[sc]);sem=z['std']/np.sqrt(z['count'])
        ax.fill_between(z.index,z['mean']-1.96*sem,z['mean']+1.96*sem,color=COLORS[sc],alpha=.15)
    ax.axvline(270,color='black',ls='--',label='Fim do ataque');ax.set(xlabel='Tempo desde o início da execução (s)',
        ylabel='Mediana da duração legítima por execução (ms)',title='B1-B — Atendimento legítimo por instante de início')
    ax.legend(ncol=4)
    for ext in ('png','pdf'):fig.savefig(OUT/'figures'/f'b1_b_legitimo.{ext}',dpi=180)
    plt.close(fig)
    # CPU figure: acquisition cadence versus conservative feature assignment.
    c=cpu.groupby(['scenario','phase'],as_index=False).agg(feature=('feature_coverage','mean'),snapshots=('snapshot_count','mean'))
    c['snapshots_per_second']=c.snapshots/c.phase.map({p:b-a for p,a,b in PHASES})
    fig,ax=plt.subplots(figsize=(9,4.5),layout='constrained')
    labels=['WARMUP','PRE','ACTIVE','POST'];x=np.arange(4)
    for i,sc in enumerate(('L2','A3','F96')):
        z=c[c.scenario.eq(sc)].set_index('phase').loc[labels]
        ax.plot(x,z.feature,marker='o',color=COLORS[sc],label=f'{sc}: série temporal')
        ax.plot(x,z.snapshots_per_second,marker='x',ls='--',color=COLORS[sc],label=f'{sc}: snapshots/s')
    ax.set(xticks=x,xticklabels=labels,ylabel='Cobertura ou frequência relativa',
           title='B2 — Snapshots da vítima e valores aceitos na série temporal')
    ax.set_ylim(0,1.1);ax.legend(ncol=2)
    ax.axvline(2.5,color='black',ls=':',lw=1,label='Fim do ataque (270 s)')
    for ext in ('png','pdf'):fig.savefig(OUT/'figures'/f'b2_cpu_cobertura.{ext}',dpi=180)
    plt.close(fig)
    # Input hashes are recorded after analysis to certify source immutability.
    hashes={str(p.relative_to(ROOT)):digest(p) for p in input_paths}
    (OUT/'processed/input_hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print('OK',len(inv),'TEST;',inv.block.nunique(),'blocos;',len(per),'POST rows;',len(legit),'HTTP rows')

if __name__=='__main__':main()
