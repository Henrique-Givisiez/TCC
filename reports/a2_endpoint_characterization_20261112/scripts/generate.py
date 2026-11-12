#!/usr/bin/env python3
"""Figuras exploratórias da A2; lê somente os quatro ensaios A2."""
from __future__ import annotations
import hashlib, json
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
SRC=ROOT/'experiment_results/endpoint-characterization-a2-20261106T200836Z'
OUT=ROOT/'reports/a2_endpoint_characterization_20261112'
ORDER=['M_A','M_B','E_A','E_B']
END={'M_A':'/medium','M_B':'/medium','E_A':'/expensive','E_B':'/expensive'}
COLOR={'/medium':'#17698c','/expensive':'#a12c55'}
STYLE={'A':'-','B':'--'}
plt.rcParams.update({'font.size':10,'axes.titlesize':11,'axes.labelsize':10,'figure.titlesize':14,'pdf.fonttype':42,'savefig.facecolor':'white'})

def jsonl(p):
    with p.open() as f:return [json.loads(x) for x in f if x.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def arr(v):return np.asarray(v,dtype=float)
def load(k):
    p=SRC/k/'raw';files=[p/x for x in ['effective_config.json','run_status.json','request_log.csv','rtt_log.csv','victim_stats.jsonl','diagnostics/victim/events.jsonl']]
    files+=sorted((p/'source_artifacts').glob('normal_*/output/diagnostics/events.jsonl'))
    cfg=json.loads(files[0].read_text());st=json.loads(files[1].read_text());r=pd.read_csv(files[2]).fillna({'error_type':''});rtt=pd.read_csv(files[3]);vr=jsonl(files[4]);ev=jsonl(files[5]);src=[jsonl(x) for x in files[6:]]
    assert cfg['duration_seconds']==60 and cfg['normal_traffic']['clients']==2 and cfg['normal_traffic']['rate']==1
    assert cfg['normal_traffic']['endpoint']==END[k] and cfg['normal_traffic']['max_concurrent_sends']==4
    assert cfg['normal_traffic']['request_timeout_seconds']==2 and not cfg['attack']['enabled']
    assert cfg['topology']['mode']=='direct' and cfg['server']['process_pool_workers']==2 and cfg['diagnostics']['enabled']
    assert st['status']=='completed' and st['end_reason']=='simulation_end' and st['errors']==[] and st['producers_drained']
    assert len(r)==101 and r.request_id.nunique()==101 and set(r.run_id)=={st['run_id']}
    assert set(r.traffic_class)=={'benign'} and set(r.target_url.str.extract(r'(/[^/]+)$')[0])=={END[k]}
    assert (r.duration_ms>=0).all() and (r.end_elapsed_seconds>=r.elapsed_seconds).all()
    assert np.allclose(r.end_elapsed_seconds-r.elapsed_seconds,r.duration_ms/1000,atol=.002)
    assert len(rtt)==101 and set(rtt.request_id)==set(r.request_id)
    assert {x['metrics']['name'] for x in vr}=={'target_instance_1'}
    stats=pd.DataFrame([{'t':x['monotonic']-st['experiment_start_monotonic'],'cpu':x['metrics']['cpu_percent'],'mem':x['metrics']['raw_mem_usage']/1048576} for x in vr]).sort_values('t')
    work=[x for x in ev if x['kind']=='handler_finished' and x.get('phase') is None]
    assert len(work)==101 and len({x['request_id'] for x in work})==101 and {x['request_id'] for x in work}==set(r.request_id)
    assert Counter((x['kind'],x.get('phase')) for x in ev)[('handler_finished','capture_audit')]==10
    clocks={(x['worker_clock']['kind'],x['worker_clock']['time_namespace']) for x in work};assert len(clocks)==1 and next(iter(clocks))[0]=='CLOCK_MONOTONIC'
    w=pd.DataFrame([{'request_id':x['request_id'],'submit':x['work_submitted_at']-st['experiment_start_monotonic'],'start':x['work_started_at']-st['experiment_start_monotonic'],'finish':x['work_finished_at']-st['experiment_start_monotonic'],'cpu_ms':x['work_cpu_seconds']*1000} for x in work])
    assert ((w.start>=w.submit)&(w.finish>=w.start)&(w.cpu_ms>0)).all()
    aligned=w.merge(r[['request_id','elapsed_seconds','end_elapsed_seconds']],on='request_id',validate='one_to_one')
    assert ((aligned.elapsed_seconds<=aligned.submit)&(aligned.finish<=aligned.end_elapsed_seconds)).all()
    w['wait_ms']=(w.start-w.submit)*1000
    counts=Counter(x['kind'] for part in src for x in part)
    assert counts['http_started']==counts['http_finished']==counts['submitted']==counts['planned']==101
    ids={x['request_id'] for part in src for x in part if x['kind']=='http_started'};assert ids==set(r.request_id)
    assert all(x['kind'] in {'handler_started','handler_finished'} for x in ev)
    return {'cfg':cfg,'status':st,'req':r.sort_values('elapsed_seconds').reset_index(drop=True),'rtt':rtt,'stats':stats,'works':w,'sources':counts,'hashes':{str(x.relative_to(ROOT)):sha(x) for x in files},'clock':list(clocks)[0]}

def steps(w):
    events=[]
    for row in w.itertuples():events.extend([(row.submit,0,1,0),(row.start,1,-1,1),(row.finish,2,0,-1)])
    events.sort(key=lambda x:(x[0],x[1]))
    x=[0.];wait=[0];run=[0];a=b=0
    for t,_,da,db in events:
        a+=da;b+=db;assert a>=0 and 0<=b<=2
        x.append(t);wait.append(a);run.append(b)
    if x[-1]<60:x.append(60.);wait.append(a);run.append(b)
    return arr(x),arr(wait),arr(run)
def fraction(x,y):
    v=np.zeros(3)
    for left,right,state in zip(x[:-1],x[1:],y[:-1]):v[int(state)]+=max(0,min(right,60)-max(left,0))
    assert np.isclose(sum(v),60)
    return v/60
def setup(ax,ylabel=None):
    ax.set_xlim(0,60);ax.grid(alpha=.18);ax.set_xlabel('Tempo relativo à execução (s)')
    if ylabel:ax.set_ylabel(ylabel)
def save(fig,name,folder):
    target=OUT/'figures'/folder;target.mkdir(parents=True,exist_ok=True)
    if not getattr(fig,'_a2_custom_layout',False):fig.tight_layout()
    for fmt in ['png','pdf']:fig.savefig(target/f'{name}.{fmt}',dpi=300,bbox_inches='tight')
    plt.close(fig)
    return [str((target/f'{name}.{fmt}').relative_to(OUT)) for fmt in ['png','pdf']]
def request_segments(ax,d,color,compact=False):
    r=d['req'];scale=1 if compact else 1
    for i,row in enumerate(r.itertuples()):
        successful=row.outcome=='response' and row.http_status==200
        ax.plot([row.elapsed_seconds,row.end_elapsed_seconds],[i+1,i+1],color=color if successful else '#a32323',lw=1.5 if compact else 2.1,alpha=.8)
        if not successful:ax.plot(row.end_elapsed_seconds,i+1,marker='x',color='#a32323',ms=4)
    ax.set_ylim(0,len(r)+2);ax.set_ylabel('Requisição (ordem de início)');setup(ax)
def panel(k,d,compact=False):
    color=COLOR[END[k]];x,w,r=d['steps'];req=d['req'];s=d['stats']
    fig,axes=plt.subplots(6,1,figsize=(12,12 if compact else 15),sharex=True,gridspec_kw={'height_ratios':[2.4,1.25,1.25,1,1,1.5]})
    request_segments(axes[0],d,color,compact)
    axes[1].plot(s.t,s.cpu,color=color,ls=STYLE[k[-1]],marker='o',ms=3);setup(axes[1],'CPU Docker (%)')
    axes[2].plot(s.t,s.mem,color=color,ls=STYLE[k[-1]],marker='o',ms=3);setup(axes[2],'Memória (MiB)')
    axes[3].step(x,r,where='post',color=color,lw=1.2);axes[3].set_ylim(-.1,2.2);setup(axes[3],'Workers ocupados')
    axes[4].step(x,w,where='post',color=color,lw=1.2);setup(axes[4],'Operações aguardando')
    axes[5].scatter(req.elapsed_seconds,req.duration_ms,color=color,s=20,alpha=.8,marker='o' if k.endswith('A') else '^');setup(axes[5],'Duração HTTP (ms)')
    axes[0].set_title(f'{k} — {END[k]}: segmentos de início até fim HTTP')
    fig.suptitle(f'A2 — Painel temporal integrado: {k} ({END[k]})',y=.995)
    if compact:
        # Leave vertical room while preserving individual requests.
        for ax in axes[:-1]:ax.set_xlabel('')
    return save(fig,f'painel_integrado_{k}'+('_compacto' if compact else ''),'integradas')
def comparative(runs):
    # Rows are the A/B repetitions, columns the endpoint. No representative run is selected.
    fig=plt.figure(figsize=(15,13));outer=GridSpec(2,2,figure=fig,wspace=.20,hspace=.35)
    for row,pair in enumerate([('M_A','E_A'),('M_B','E_B')]):
        for col,k in enumerate(pair):
            d=runs[k];c=COLOR[END[k]];inner=GridSpecFromSubplotSpec(3,1,subplot_spec=outer[row,col],height_ratios=[2.2,1,1],hspace=.17)
            ax=fig.add_subplot(inner[0]);request_segments(ax,d,c,True);ax.set_title(f'{k} — {END[k]}');ax.set_xlabel('')
            ax2=fig.add_subplot(inner[1],sharex=ax);ax2.plot(d['stats'].t,d['stats'].cpu,color=c,ls=STYLE[k[-1]],marker='o',ms=2);setup(ax2,'CPU (%)');ax2.set_ylim(0,100);ax2.set_xlabel('')
            ax3=fig.add_subplot(inner[2],sharex=ax);ax3.scatter(d['req'].elapsed_seconds,d['req'].duration_ms,color=c,s=12,marker='o' if k.endswith('A') else '^');setup(ax3,'HTTP (ms)');ax3.set_ylim(0,400)
    fig.suptitle('A2 — Requisições, CPU e duração HTTP: duas repetições por endpoint',y=.995)
    fig.subplots_adjust(left=.08,right=.98,top=.91,bottom=.06)
    fig._a2_custom_layout=True
    return save(fig,'painel_comparativo_quatro_execucoes','integradas')

def main():
    runs={k:load(k) for k in ORDER};figs=[]
    for k,d in runs.items():
        d['steps']=steps(d['works']);d['fraction']=fraction(d['steps'][0],d['steps'][2]);figs+=panel(k,d);figs+=panel(k,d,True)
    figs+=comparative(runs)
    # V1 direct worker CPU per operation, repetitions separate.
    fig,ax=plt.subplots(figsize=(10,5));vals=[runs[k]['works'].cpu_ms for k in ORDER]
    bp=ax.boxplot(vals,patch_artist=True,showfliers=True)
    for patch,k in zip(bp['boxes'],ORDER):patch.set_facecolor(COLOR[END[k]]);patch.set_alpha(.55)
    for i,k in enumerate(ORDER,1):ax.scatter(i,runs[k]['works'].cpu_ms.median(),marker='D',s=18,color='black')
    ax.set_xticks(range(1,5),[f'{k}\n{END[k]}' for k in ORDER]);ax.set_ylabel('CPU do worker por operação (ms)');ax.grid(axis='y',alpha=.2);ax.set_title('V1 — Tempo de CPU do worker por requisição, por execução');figs+=save(fig,'V1_cpu_por_operacao','comparativas')
    # V2 resource observations; color endpoint and marker repetition.
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,field,label in [(axes[0],'cpu','CPU Docker da vítima (%)'),(axes[1],'mem','Memória do contêiner (MiB)')]:
        for i,k in enumerate(ORDER):
            s=runs[k]['stats'];s=s[(s.t>=0)&(s.t<60)]
            ax.scatter(np.full(len(s),i)+np.linspace(-.08,.08,len(s)),s[field],color=COLOR[END[k]],marker='o' if k.endswith('A') else '^',s=20,alpha=.65)
            ax.scatter(i,s[field].median(),color='black',marker='_',s=350,zorder=4)
        ax.set_xticks(range(4),ORDER);ax.set_ylabel(label);ax.grid(axis='y',alpha=.2)
    axes[0].set_ylim(bottom=0);axes[0].set_title('CPU: amostras e mediana');axes[1].set_title('Memória: amostras e mediana (eixo ampliado)');fig.suptitle('V2 — Recursos Docker da vítima: repetições separadas');figs+=save(fig,'V2_cpu_memoria','comparativas')
    # V3 HTTP distributions; all are confirmed responses, retain separation.
    fig,axes=plt.subplots(1,2,figsize=(12,5));vals=[runs[k]['req'].duration_ms for k in ORDER]
    bp=axes[0].boxplot(vals,patch_artist=True,showfliers=True)
    for patch,k in zip(bp['boxes'],ORDER):patch.set_facecolor(COLOR[END[k]]);patch.set_alpha(.55)
    axes[0].set_xticks(range(1,5),ORDER);axes[0].set_ylabel('Duração HTTP (ms)');axes[0].set_title('Distribuição por execução');axes[0].grid(axis='y',alpha=.2)
    for k in ORDER:
        v=np.sort(runs[k]['req'].duration_ms);axes[1].plot(v,np.arange(1,len(v)+1)/len(v),color=COLOR[END[k]],ls=STYLE[k[-1]],label=k)
    axes[1].set_xlabel('Duração HTTP (ms)');axes[1].set_ylabel('Fração acumulada');axes[1].legend();axes[1].grid(alpha=.2);axes[1].set_title('ECDF por execução')
    fig.suptitle('V3 — Duração das respostas HTTP 200; 101 por execução');figs+=save(fig,'V3_duracao_http','comparativas')
    # V4 worker occupancy, waiting and backlog.
    fig,axes=plt.subplots(1,3,figsize=(15,5));bottom=np.zeros(4)
    for i,hatch,name in [(0,'','Zero'),(1,'//','Um'),(2,'xx','Dois')]:
        v=np.array([runs[k]['fraction'][i] for k in ORDER]);axes[0].bar(range(4),v,bottom=bottom,label=name,hatch=hatch,color=['#c0d5df','#739cb4','#315c79'][i]);bottom+=v
    axes[0].set_ylabel('Fração de [0,60)');axes[0].set_title('Workers ocupados');axes[0].legend(ncol=3,loc='upper center',bbox_to_anchor=(.5,-.12))
    bp=axes[1].boxplot([runs[k]['works'].wait_ms for k in ORDER],patch_artist=True,showfliers=True)
    for patch,k in zip(bp['boxes'],ORDER):patch.set_facecolor(COLOR[END[k]]);patch.set_alpha(.55)
    axes[1].set_yscale('log');axes[1].set_ylabel('Espera por worker (ms; escala log)');axes[1].set_title('Submissão até início no worker')
    axes[2].bar(range(4),[runs[k]['steps'][1].max() for k in ORDER],color=[COLOR[END[k]] for k in ORDER],hatch='//');axes[2].set_ylabel('Operações aguardando (máximo)');axes[2].set_title('Pico observável em [0,60)')
    for ax in axes:ax.set_xticks(range(4),ORDER);ax.grid(axis='y',alpha=.2)
    fig.suptitle('V4 — Ocupação, espera e operações aguardando');figs+=save(fig,'V4_workers_espera','comparativas')
    # Separate nominal versus started rate, useful control for the endpoint comparison.
    fig,ax=plt.subplots(figsize=(8,4));ax.bar(np.arange(4)-.18,[2]*4,.36,label='Nominal',color='#aab8c2');ax.bar(np.arange(4)+.18,[len(runs[k]['req'])/60 for k in ORDER],.36,label='HTTP iniciado',color=[COLOR[END[k]] for k in ORDER],hatch='//');ax.set_xticks(range(4),ORDER);ax.set_ylim(0,2.3);ax.set_ylabel('Requisições iniciadas por segundo (RPS)');ax.legend();ax.grid(axis='y',alpha=.2);ax.set_title('A2 — RPS nominal e HTTP iniciado em [0,60)');figs+=save(fig,'RPS_nominal_efetivo','comparativas')
    records=[];checks={'inputs_sha256':{},'runs':{},'figures':figs}
    for k,d in runs.items():
        r=d['req'];s=d['stats'];s=s[(s.t>=0)&(s.t<60)];w=d['works'];x,waiting,running=d['steps']
        records.append({'run':k,'endpoint':END[k],'n_http':len(r),'rps_nominal':2,'rps_started':len(r)/60,'responses_200':int(((r.outcome=='response')&(r.http_status==200)).sum()),'timeouts':int(r.outcome.astype(str).str.contains('timeout',case=False).sum()),'cpu_worker_mean_ms':w.cpu_ms.mean(),'cpu_worker_median_ms':w.cpu_ms.median(),'cpu_worker_p95_ms':w.cpu_ms.quantile(.95),'cpu_docker_n':len(s),'cpu_docker_mean_pct':s.cpu.mean(),'cpu_docker_median_pct':s.cpu.median(),'cpu_docker_max_pct':s.cpu.max(),'mem_mean_mib':s.mem.mean(),'mem_median_mib':s.mem.median(),'mem_max_mib':s.mem.max(),'http_mean_ms':r.duration_ms.mean(),'http_median_ms':r.duration_ms.median(),'http_p95_ms':r.duration_ms.quantile(.95),'http_max_ms':r.duration_ms.max(),'wait_median_ms':w.wait_ms.median(),'wait_p95_ms':w.wait_ms.quantile(.95),'wait_max_ms':w.wait_ms.max(),'max_waiting':int(waiting.max()),'fraction_0':d['fraction'][0],'fraction_1':d['fraction'][1],'fraction_2':d['fraction'][2]})
        pd.DataFrame({'t_s':x,'aguardando':waiting,'em_execucao':running}).to_csv(OUT/'processed'/f'workers_{k}.csv',index=False)
        pd.DataFrame({'t_s':s.t,'cpu_percent':s.cpu,'mem_mib':s.mem}).to_csv(OUT/'processed'/f'docker_{k}.csv',index=False)
        d['works'].to_csv(OUT/'processed'/f'operacoes_{k}.csv',index=False)
        checks['inputs_sha256'].update(d['hashes'])
        checks['runs'][k]={'run_id':d['status']['run_id'],'request_ids':len(set(r.request_id)),'rtt_ids':len(set(d['rtt'].request_id)),'work_ids':len(set(w.request_id)),'source_events':dict(d['sources']),'clock':d['clock'],'stats_raw_n':len(d['stats']),'stats_in_60_n':len(s),'stats_range_s':[float(d['stats'].t.min()),float(d['stats'].t.max())],'stats_cadence_median_s':float(d['stats'].t.diff().median()),'outcomes':{str(a):int(b) for a,b in Counter(zip(r.outcome,r.http_status)).items()},'max_running':int(running.max()),'min_waiting':int(waiting.min()),'occupation_fraction_sum':float(sum(d['fraction']))}
    pd.DataFrame(records).to_csv(OUT/'processed'/'summary.csv',index=False)
    checks['figure_pairs']=len(figs)//2
    (OUT/'validation'/'checks.json').write_text(json.dumps(checks,indent=2,ensure_ascii=False))
    (OUT/'manifest.json').write_text(json.dumps({'source':str(SRC.relative_to(ROOT)),'runs':ORDER,'period_s':[0,60],'script':'scripts/generate.py','script_sha256':sha(Path(__file__)),'figures':figs,'processed':'processed/summary.csv','validation':'validation/checks.json'},indent=2,ensure_ascii=False))
    print(f'{len(figs)//2} figuras em PNG/PDF')
if __name__=='__main__':main()
