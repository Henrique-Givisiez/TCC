#!/usr/bin/env python3
"""Processamento e figuras da B1 isolada; entradas experimentais somente leitura."""
from __future__ import annotations
import hashlib,json,csv
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'reports/b1_attack_characterization_20261112'
B12=ROOT/'experiment_results/b12-isolated-20261107T200251Z'
B11=ROOT/'experiment_results/b11-integrated-asymmetry-20261107-r1'
PATHS={'A1':B11,**{k:B12/k for k in ['A2','A3','A4','F1','F2','F3','F4','F5']}}
MAIN_A=['A2','A3','A4'];PILOT_A=['A1'];FLOOD=['F1','F2','F3','F4','F5'];ALL=PILOT_A+MAIN_A+FLOOD
COL={'A':'#a12c55','F':'#17698c'}
LINE={'A1':':','A2':'-','A3':'--','A4':'-.','F1':'-','F2':'--','F3':'-.','F4':':','F5':(0,(3,1,1,1))}
plt.rcParams.update({'font.size':10,'axes.titlesize':11,'figure.titlesize':14,'pdf.fonttype':42,'savefig.facecolor':'white'})
FIG=[]
def jl(p):
    with p.open() as f:return [json.loads(x) for x in f if x.strip()]
def h(p):
    z=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):z.update(b)
    return z.hexdigest()
def save(fig,rel):
    p=OUT/'figures'/rel;p.parent.mkdir(parents=True,exist_ok=True);fig.tight_layout()
    for ext in ['png','pdf']:
        q=p.with_suffix('.'+ext);fig.savefig(q,dpi=300,bbox_inches='tight');FIG.append(str(q.relative_to(OUT)))
    plt.close(fig)
def temporal(ax,end=150):
    ax.axvspan(30,60,color='#f5deae',alpha=.55,zorder=-10)
    for t in [30,60]:ax.axvline(t,color='#6a6257',lw=.8,ls=':')
    ax.set_xlim(0,end);ax.set_xlabel('Tempo relativo à execução (s)');ax.grid(alpha=.16)
def active_series(req,end=150):
    events=[]
    for x in req.itertuples():events.extend([(x.elapsed_seconds,1),(x.end_elapsed_seconds,-1)])
    events.sort(key=lambda x:(x[0],x[1]))
    t=[0.];v=[0];a=0
    for x,d in events:a+=d;assert a>=0;t.append(x);v.append(a)
    if t[-1]<end:t.append(end);v.append(a)
    assert a==0
    return np.array(t),np.array(v)
def work_series(work,end=150):
    ev=[]
    for x in work.itertuples():ev.extend([(x.submit,0,1,0),(x.start,1,-1,1),(x.finish,2,0,-1)])
    ev.sort(key=lambda x:(x[0],x[1]));t=[0.];w=[0];r=[0];a=b=0
    for x,_,da,db in ev:a+=da;b+=db;assert a>=0 and 0<=b<=2;t.append(x);w.append(a);r.append(b)
    if t[-1]<end:t.append(end);w.append(a);r.append(b)
    assert a==0 and b==0
    return np.array(t),np.array(w),np.array(r)
def source_concurrency(parts,origin):
    events=[]
    for part in parts:
        started={x['attempt_id']:x['at'] for x in part if x['kind']=='task_started'}
        finished={x['attempt_id']:x['at'] for x in part if x['kind']=='task_finished'}
        assert len(started)==len(finished) and set(started)==set(finished)
        for key,t in started.items():assert finished[key]>=t;events.extend([(t-origin,1),(finished[key]-origin,-1)])
    events.sort(key=lambda x:(x[0],x[1]));t=[0.];v=[0];a=0
    for x,d in events:a+=d;assert 0<=a<=64;t.append(x);v.append(a)
    if t[-1]<150:t.append(150.);v.append(a)
    assert a==0
    return np.array(t),np.array(v)
def fractions(t,r,left=30,right=60):
    z=np.zeros(3)
    for a,b,x in zip(t[:-1],t[1:],r[:-1]):z[int(x)]+=max(0,min(b,right)-max(a,left))
    assert np.isclose(sum(z),right-left)
    return z/(right-left)
def load(k):
    raw=PATHS[k]/'raw';paths=[raw/x for x in ['effective_config.json','run_status.json','request_log.csv','rtt_log.csv','victim_stats.jsonl','diagnostics/victim/events.jsonl','traffic_capture.csv']]
    paths+=sorted((raw/'source_artifacts').glob('attack_*/output/diagnostics/events.jsonl'))
    paths+=sorted((raw/'source_artifacts').glob('attack_*/output/journal.jsonl'))
    assert all(p.exists() for p in paths)
    c=json.loads(paths[0].read_text());st=json.loads(paths[1].read_text());a=c['attack'];r=pd.read_csv(paths[2]).fillna({'error_type':''});rtt=pd.read_csv(paths[3]);statsraw=jl(paths[4]);ve=jl(paths[5]);net=pd.read_csv(paths[6]);src=[jl(x) for x in paths if x.name=='events.jsonl' and 'source_artifacts' in str(x)];journ=[jl(x) for x in paths if x.name=='journal.jsonl']
    assert c['duration_seconds']==150 and a['enabled'] and a['start_seconds']==30 and a['duration_seconds']==30
    assert a['attackers']==2 and a['max_concurrent_sends']==64 and c['normal_traffic']['clients']==0
    assert c['topology']['mode']=='direct' and c['server']['process_pool_workers']==2 and c['diagnostics']['enabled']
    assert a['endpoint']==('/expensive' if k.startswith('A') else '/medium')
    assert a['rate']=={'A1':1,'A2':2,'A3':4,'A4':8,'F1':16,'F2':32,'F3':64,'F4':96,'F5':128}[k]
    assert st['status']=='completed' and st['end_reason']=='simulation_end' and st['errors']==[] and st['producers_drained']
    assert len(r)==r.request_id.nunique() and set(r.run_id)=={st['run_id']} and set(r.traffic_class)=={'attack'}
    assert (r.duration_ms>=0).all() and (r.end_elapsed_seconds>=r.elapsed_seconds).all() and ((r.elapsed_seconds>=30)&(r.elapsed_seconds<60)).all()
    assert np.allclose(r.end_elapsed_seconds-r.elapsed_seconds,r.duration_ms/1000,atol=.002)
    assert len(rtt)==int((r.outcome=='response').sum()) and set(rtt.request_id)==set(r.loc[r.outcome=='response','request_id'])
    assert {x['metrics']['name'] for x in statsraw}=={'target_instance_1'}
    stats=pd.DataFrame([{'t':x['monotonic']-st['experiment_start_monotonic'],'cpu':x['metrics']['cpu_percent'],'mem':x['metrics']['raw_mem_usage']/1048576} for x in statsraw]).sort_values('t')
    active=stats[(stats.t>=30)&(stats.t<60)]
    ev={q:[x for x in ve if x['kind']==q and x.get('traffic_class')=='attack'] for q in ['work_submitted','work_started','work_completed','handler_started','handler_finished']}
    for q in ['work_submitted','work_started','work_completed','handler_finished']:assert len(ev[q])==len(r)
    by={q:{x['operation_id']:x for x in ev[q]} for q in ['work_submitted','work_started','work_completed']}
    assert all(len(by[q])==len(r) for q in by) and set(by['work_submitted'])==set(by['work_started'])==set(by['work_completed'])
    clocks={(x['worker_clock']['kind'],x['worker_clock']['time_namespace']) for x in ev['work_completed']};assert len(clocks)==1 and next(iter(clocks))[0]=='CLOCK_MONOTONIC'
    work=[];ids=set(r.request_id)
    for op,s in by['work_submitted'].items():
        b=by['work_started'][op];f=by['work_completed'][op];assert s['request_id']==b['request_id']==f['request_id'] and s['request_id'] in ids
        work.append({'request_id':s['request_id'],'submit':s['at']-st['experiment_start_monotonic'],'start':b['at']-st['experiment_start_monotonic'],'finish':f['at']-st['experiment_start_monotonic'],'cpu_ms':f['work_cpu_seconds']*1000})
    work=pd.DataFrame(work);assert len(work)==work.request_id.nunique()
    assert ((work.start>=work.submit)&(work.finish>=work.start)&(work.cpu_ms>=0)).all()
    work['wait_ms']=(work.start-work.submit)*1000;work['execution_ms']=(work.finish-work.start)*1000
    joined=work.merge(r[['request_id','elapsed_seconds','end_elapsed_seconds']],on='request_id',validate='one_to_one')
    # Timeout clients may stop before a worker completes; do not assert finish <= HTTP end.
    assert (joined.submit>=joined.elapsed_seconds-0.05).all()
    src_count=Counter(x['kind'] for part in src for x in part);jcount=Counter(x['kind'] for part in journ for x in part)
    assert src_count['http_started']==src_count['http_finished']==len(r)
    assert {x['request_id'] for part in src for x in part if x['kind']=='http_started'}==ids
    assert jcount['request_begin']==jcount['request_finish']==len(r)
    assert src_count['submitted']==jcount['submitted'] and jcount['abandoned_admission']==src_count['submitted']-len(r)
    assert set(net.run_id)=={st['run_id']} and (net.packet_length>=0).all()
    x,y,z=work_series(work);at,ac=active_series(r);sc=source_concurrency(src,st['experiment_start_monotonic'])
    source_times={kind:np.array([e['at']-st['experiment_start_monotonic'] for part in src for e in part if e['kind']==kind]) for kind in ['submitted','task_started','http_started','http_finished','task_finished']}
    return {'cfg':c,'status':st,'req':r.sort_values('elapsed_seconds'),'rtt':rtt,'stats':stats,'active_stats':active,'work':work,'work_step':(x,y,z),'http_active':(at,ac),'source_concurrency':sc,'source_times':source_times,'fractions':fractions(x,z),'src':src_count,'journal':jcount,'net':net,'hashes':{str(p.relative_to(ROOT)):h(p) for p in paths},'clock':list(clocks)[0]}
def outcomes(r):
    z=Counter()
    for x in r.itertuples():
        if x.outcome=='response':z['HTTP 2xx' if 200<=x.http_status<=299 else 'Erro HTTP']+=1
        elif 'timeout' in str(x.error_type).lower() or 'timeout' in str(x.outcome).lower():z['Timeout']+=1
        elif 'connect' in str(x.error_type).lower():z['Falha de conexão']+=1
        else:z['Outro encerramento']+=1
    assert sum(z.values())==len(r)
    return z
def panel(k,d,compact=False):
    mech='assimetria' if k.startswith('A') else 'flooding';color=COL[k[0]];req=d['req'];stat=d['stats'];xt,waiting,running=d['work_step'];ht,ha=d['http_active'];network=d['net']
    if compact:fig,axes=plt.subplots(5,1,figsize=(12,11),sharex=True,gridspec_kw={'height_ratios':[1.3,1,1,1,1.2]})
    else:fig,axes=plt.subplots(8,1,figsize=(13,18),sharex=True,gridspec_kw={'height_ratios':[1.5,1,1,1,1,1.1,1,1]})
    # Client HTTP interval, including timeout end, never implying server completion.
    if compact:
        axes[0].step(ht,ha,where='post',color=color);axes[0].set_ylabel('HTTP ativos\nno cliente')
    else:
        for i,row in enumerate(req.itertuples()):
            ok=row.outcome=='response' and row.http_status==200
            axes[0].plot([row.elapsed_seconds,row.end_elapsed_seconds],[i+1,i+1],color=color if ok else '#222222',lw=.8,alpha=.55)
            if not ok:axes[0].plot(row.end_elapsed_seconds,i+1,marker='x',color='#111111',ms=2)
        axes[0].set_ylabel('Requisição\n(ordem de início)')
    axes[1].scatter(stat.t,stat.cpu,color=color,s=12);axes[1].set_ylabel('CPU Docker\n(%)')
    axes[2].scatter(stat.t,stat.mem,color=color,s=12);axes[2].set_ylabel('Memória\n(MiB)')
    axes[3].step(xt,running,where='post',color=color,lw=.8);axes[3].set_ylim(-.1,2.2);axes[3].set_ylabel('Workers\nocupados')
    if compact:
        axes[4].scatter(req.elapsed_seconds,req.duration_ms,color=color,s=10,alpha=.45);axes[4].set_ylabel('Duração HTTP\n(ms)')
        timeout=req[req.outcome!='response'];axes[4].scatter(timeout.elapsed_seconds,timeout.duration_ms,marker='x',color='black',s=15,label='Timeout/outro')
    else:
        axes[4].step(xt,waiting,where='post',color=color,lw=.8);axes[4].set_ylabel('Operações\naguardando')
        ok=req[req.outcome=='response'];bad=req[req.outcome!='response']
        axes[5].scatter(ok.elapsed_seconds,ok.duration_ms,color=color,s=10,alpha=.45,label='Resposta HTTP')
        if len(bad):axes[5].scatter(bad.elapsed_seconds,bad.duration_ms,color='black',marker='x',s=14,label='Timeout/outro')
        axes[5].set_ylabel('Duração no\ncliente (ms)');axes[5].legend(fontsize=8)
        counts=np.histogram(req.elapsed_seconds,bins=np.arange(151))[0];axes[6].step(np.arange(150),counts,where='post',color=color);axes[6].set_ylabel('Inícios HTTP\npor segundo')
        counts=np.histogram(network.elapsed_seconds,bins=np.arange(151))[0];axes[7].step(np.arange(150),counts,where='post',color=color);axes[7].set_ylabel('Pacotes TCP\npor segundo')
    for ax in axes:temporal(ax)
    fig.suptitle(f'B1 — {k}: painel temporal {"compacto" if compact else "completo"} ({mech})',y=.997)
    save(fig,f'{mech}/individuais/{k}_painel_{"compacto" if compact else "completo"}')
def simple_box(keys,field,title,ylabel,path,access=lambda d:d['req']):
    fig,ax=plt.subplots(figsize=(max(8,len(keys)*1.2),5));vals=[access(D[k])[field].dropna().to_numpy() for k in keys]
    bp=ax.boxplot(vals,patch_artist=True,showfliers=False,whis=(5,95))
    for p,k in zip(bp['boxes'],keys):p.set_facecolor(COL[k[0]]);p.set_alpha(.5)
    ax.set_xticks(range(1,len(keys)+1),keys);ax.set_ylabel(ylabel);ax.grid(axis='y',alpha=.2);ax.set_title(title+' (bigodes p5–p95)');save(fig,path)
def rateplot(keys,prefix):
    fig,ax=plt.subplots(figsize=(max(8,len(keys)*1.3),5));x=np.arange(len(keys));nom=np.array([S[k]['nominal_rps'] for k in keys]);started=np.array([S[k]['rps_started'] for k in keys]);finished=np.array([S[k]['rps_finished_within'] for k in keys]);bw=.25
    ax.bar(x-bw,nom,bw,label='Nominal',color='#aebac2');ax.bar(x,started,bw,label='HTTP iniciado',color=COL[keys[0][0]],hatch='//');ax.bar(x+bw,finished,bw,label='HTTP encerrado até 60 s',color=COL[keys[0][0]],alpha=.45,hatch='xx')
    ax.set_xticks(x,keys);ax.set_ylabel('Requisições por segundo (RPS)');ax.grid(axis='y',alpha=.2);ax.legend();ax.set_title(f'{prefix} — Taxas em [30,60): inícios e encerramentos por tempo do evento');save(fig,f'{"assimetria" if keys[0].startswith("A") else "flooding"}/comparativas/{prefix}_rps_nominal_efetivo')
def ecdf(keys,field,title,ylabel,path,access=lambda d:d['req']):
    fig,ax=plt.subplots(figsize=(9,5))
    for k in keys:
        v=np.sort(access(D[k])[field].dropna().to_numpy());
        if len(v):ax.plot(v,np.arange(1,len(v)+1)/len(v),color=COL[k[0]],ls=LINE[k],label=f'{k} (n={len(v)})')
    ax.set_xlabel(ylabel);ax.set_ylabel('Fração acumulada');ax.grid(alpha=.2);ax.legend();ax.set_title(title);save(fig,path)
def metric_matrix(keys,field,title,ylabel,path,source='stats',ylim=None):
    cols=2;rows=int(np.ceil(len(keys)/2));fig,axes=plt.subplots(rows,cols,figsize=(12,rows*3),sharex=True,sharey=ylim is not None)
    for ax,k in zip(np.array(axes).ravel(),keys):
        d=D[k];c=COL[k[0]]
        if source=='stats':ax.scatter(d['stats'].t,d['stats'][field],color=c,s=12)
        elif source=='work':
            x,y,z=d['work_step'];ax.step(x,y if field=='waiting' else z,where='post',color=c,lw=.8)
        elif source=='http':
            r=d['req'];ax.scatter(r.elapsed_seconds,r.duration_ms,color=c,s=6,alpha=.5)
        elif source=='active':
            x,y=d['http_active'];ax.step(x,y,where='post',color=c,lw=.8)
        elif source=='rps':
            x=np.histogram(d['req'].elapsed_seconds,bins=np.arange(151))[0];ax.step(np.arange(150),x,where='post',color=c)
        temporal(ax);ax.set_title(k);ax.set_ylabel(ylabel)
        if ylim:ax.set_ylim(*ylim)
    for ax in np.array(axes).ravel()[len(keys):]:ax.axis('off')
    fig.suptitle(title);save(fig,path)
def occupation(keys,path,title):
    fig,ax=plt.subplots(figsize=(9,5));bottom=np.zeros(len(keys))
    for i,label,hatch,color in [(0,'Zero','', '#c5d8df'),(1,'Um','//','#7799a7'),(2,'Dois','xx','#284b61')]:
        v=np.array([D[k]['fractions'][i] for k in keys]);ax.bar(range(len(keys)),v,bottom=bottom,label=label,hatch=hatch,color=color);bottom+=v
    ax.set_xticks(range(len(keys)),keys);ax.set_ylabel('Fração do tempo [30,60)');ax.legend(title='Workers ocupados',ncol=3,loc='upper center',bbox_to_anchor=(.5,-.12));ax.set_title(title);save(fig,path)
def start_finish(k,d):
    q=d['req'];return int(((q.end_elapsed_seconds>=30)&(q.end_elapsed_seconds<60)).sum())
def summarize(k,d):
    q=d['req'];success=q[(q.outcome=='response')&(q.http_status==200)];a=d['active_stats'];w=d['work'];o=outcomes(q);src=d['src'];j=d['journal']
    return {'id':k,'group':'complementar' if k=='A1' else 'principal','mechanism':'assimetria' if k.startswith('A') else 'flooding','endpoint':d['cfg']['attack']['endpoint'],'sources':2,'rps_per_source':d['cfg']['attack']['rate'],'nominal_rps':2*d['cfg']['attack']['rate'],'rps_started':len(q)/30,'rps_finished_within':start_finish(k,d)/30,'http_started':len(q),'http_ended_observed':len(q),'http_ended_after_attack':int((q.end_elapsed_seconds>=60).sum()),'http_success':o['HTTP 2xx'],'http_error':o['Erro HTTP'],'timeouts':o['Timeout'],'connection_fail':o['Falha de conexão'],'other_outcome':o['Outro encerramento'],'submitted':src['submitted'],'not_http_started':src['submitted']-len(q),'abandoned_admission':j['abandoned_admission'],'planned_observed':src['planned'],'source_concurrency_max':int(d['source_concurrency'][1].max()),'efficiency_rps':len(q)/30/(2*d['cfg']['attack']['rate']),'cpu_n':len(a),'cpu_mean':a.cpu.mean(),'cpu_median':a.cpu.median(),'cpu_max':a.cpu.max(),'mem_mean_mib':a.mem.mean(),'mem_median_mib':a.mem.median(),'mem_max_mib':a.mem.max(),'worker_cpu_mean_ms':w.cpu_ms.mean(),'worker_cpu_median_ms':w.cpu_ms.median(),'worker_cpu_p95_ms':w.cpu_ms.quantile(.95),'worker_exec_mean_ms':w.execution_ms.mean(),'worker_wait_median_ms':w.wait_ms.median(),'worker_wait_p95_ms':w.wait_ms.quantile(.95),'worker_wait_max_ms':w.wait_ms.max(),'waiting_max':int(d['work_step'][1].max()),'running_max':int(d['work_step'][2].max()),'workers_0_fraction':d['fractions'][0],'workers_1_fraction':d['fractions'][1],'workers_2_fraction':d['fractions'][2],'http_mean_ms':success.duration_ms.mean(),'http_median_ms':success.duration_ms.median(),'http_p90_ms':success.duration_ms.quantile(.90),'http_p95_ms':success.duration_ms.quantile(.95),'http_p99_ms':success.duration_ms.quantile(.99),'http_max_ms':success.duration_ms.max(),'net_packets':len(d['net']),'net_bytes_field_sum':int(d['net'].packet_length.sum())}
def inventory():
    rows=[]
    for k in ALL:
        d=D[k];s=S[k];rows.append({'id':k,'campaign':str(PATHS[k].relative_to(ROOT)),'mechanism':s['mechanism'],'endpoint':s['endpoint'],'offensive_sources':2,'nominal_rps_per_source':s['rps_per_source'],'nominal_rps_aggregate':s['nominal_rps'],'effective_started_rps':s['rps_started'],'concurrency':64,'duration_s':150,'attack_interval':'[30,60)','status':'completed/simulation_end','instrumentation':'HTTP; RTT; fonte; vítima; Docker; TCP','classification':s['group'],'comparability':'B1.1 piloto' if k=='A1' else 'B1.2 assimetria' if k.startswith('A') else 'B1.2 flooding','notes':'Piloto separado reutilizado como A1-reference' if k=='A1' else 'Série B1.2 isolada; sem tráfego legítimo'})
    # Adjacent experiments are audited as candidates, but not pooled into isolated B1.
    candidates=[('B11_raw.attempt',B11/'raw.attempt','Tentativa preparatória sem conjunto raw completo'),('B2-A',ROOT/'experiment_results/b2-a-20261107T234426Z','Composição com tráfego legítimo; pergunta B2 distinta'),('B2-F',ROOT/'experiment_results/b2-f-20261108T000313Z','Composição com tráfego legítimo; pergunta B2 distinta'),('B2-F96',ROOT/'experiment_results/b2-f96-20261108T002312Z','Composição; concorrência ofensiva 96'),('09-A3',ROOT/'experiment_results/pilots-energy-powersaver-20261109/A3','Piloto ambiental posterior com tráfego legítimo'),('09-F96',ROOT/'experiment_results/pilots-energy-powersaver-20261109/F96','Piloto ambiental posterior; composição e concorrência 96')]
    for id,p,note in candidates:
        q=p/'raw';cfgp=q/'effective_config.json';stp=q/'run_status.json';cfg=json.loads(cfgp.read_text()) if cfgp.exists() else {};st=json.loads(stp.read_text()) if stp.exists() else {};at=cfg.get('attack',{})
        rows.append({'id':id,'campaign':str(p.relative_to(ROOT)),'mechanism':at.get('mechanism','não determinado'),'endpoint':at.get('endpoint',''),'offensive_sources':at.get('attackers',''),'nominal_rps_per_source':at.get('rate',''),'nominal_rps_aggregate':at.get('attackers',0)*at.get('rate',0) if at else '', 'effective_started_rps':'não calculado fora do escopo B1 isolado','concurrency':at.get('max_concurrent_sends',''),'duration_s':cfg.get('duration_seconds',''),'attack_interval':f"[{at.get('start_seconds','')},{at.get('start_seconds',0)+at.get('duration_seconds',0)})" if at else '', 'status':st.get('status','sem status final'),'instrumentation':'raw disponível' if q.exists() else 'tentativa sem raw final','classification':'excluído do processamento B1','comparability':'não comparável ao B1 isolado','notes':note})
    pd.DataFrame(rows).to_csv(OUT/'inventario_execucoes.csv',index=False)
def plots():
    for k,d in D.items():panel(k,d);panel(k,d,True)
    # Per-mechanism comparisons. A1 pilot is shown as an explicit extra perspective.
    for keys,tag,mech in [(MAIN_A,'A','assimetria'),(FLOOD,'F','flooding')]:
        folder=f'{mech}/comparativas';rateplot(keys,f'{tag}1')
        simple_box(keys,'cpu',f'{tag}2/F3 — CPU Docker da vítima' if tag=='F' else 'A2 — CPU Docker da vítima','CPU Docker da vítima (%)',f'{folder}/{tag}_cpu_distribuicao',lambda d:d['active_stats'])
        fig,ax=plt.subplots(figsize=(9,5));x=np.arange(len(keys));ax.plot(x,[S[k]['cpu_mean'] for k in keys],marker='o',label='Média',color=COL[tag]);ax.plot(x,[S[k]['cpu_median'] for k in keys],marker='s',ls='--',label='Mediana',color=COL[tag]);ax.plot(x,[S[k]['cpu_max'] for k in keys],marker='^',ls=':',label='Máximo',color=COL[tag]);ax.set_xticks(x,keys);ax.set_ylabel('CPU Docker da vítima (%)');ax.legend();ax.grid(alpha=.2);ax.set_title(f'{tag} — CPU Docker: resumo por execução');save(fig,f'{folder}/{tag}_cpu_resumo')
        simple_box(keys,'cpu_ms',f'{tag}3 — CPU do worker por operação','CPU do worker por operação (ms)',f'{folder}/{tag}_cpu_por_operacao',lambda d:d['work'])
        occupation(keys,f'{folder}/{tag}_fracao_workers',f'{tag} — Fração do tempo por ocupação dos workers')
        simple_box(keys,'wait_ms',f'{tag} — Espera por worker','Espera por worker (ms)',f'{folder}/{tag}_espera_worker',lambda d:d['work'])
        metric_matrix(keys,'waiting',f'{tag} — Operações aguardando ao longo do tempo','Operações aguardando',f'{folder}/{tag}_aguardando_matriz','work', (0,max(S[k]['waiting_max'] for k in keys)+1))
        metric_matrix(keys,'waiting',f'{tag} — Operações aguardando (escala individual por painel)','Operações aguardando',f'{folder}/{tag}_aguardando_matriz_escala_individual','work')
        simple_box(keys,'duration_ms',f'{tag} — Duração de respostas HTTP 200','Duração HTTP (ms)',f'{folder}/{tag}_duracao_http_boxplot',lambda d:d['req'].query('outcome == "response" and http_status == 200'))
        ecdf(keys,'duration_ms',f'{tag} — ECDF de respostas HTTP 200','Duração HTTP (ms)',f'{folder}/{tag}_duracao_http_ecdf',lambda d:d['req'].query('outcome == "response" and http_status == 200'))
        for field,ylabel,source,lim in [('cpu','CPU Docker (%)','stats',(0,max(D[k]['stats'].cpu.max() for k in keys)*1.1)),('running','Workers ocupados','work',(0,2.2)),('waiting','Operações aguardando','work',(0,max(S[k]['waiting_max'] for k in keys)+1)),('duration_ms','Duração no cliente (ms)','http',(0,max(D[k]['req'].duration_ms.max() for k in keys)*1.05))]:
            metric_matrix(keys,field,f'{tag} — {ylabel}: matriz temporal',ylabel,f'{folder}/{tag}_temporal_{field}',source,lim)
        # Descriptive relationships, one point per run.
        fig,axes=plt.subplots(1,3,figsize=(13,4))
        for ax,ycol,ylabel in [(axes[0],'cpu_mean','CPU Docker média (%)'),(axes[1],'workers_2_fraction','Fração com 2 workers'),(axes[2],'http_median_ms','HTTP mediana (ms)')]:
            for k in keys:ax.scatter(S[k]['rps_started'],S[k][ycol],color=COL[tag],marker='o' if k[-1] in '13' else 's');ax.annotate(k,(S[k]['rps_started'],S[k][ycol]),xytext=(4,4),textcoords='offset points')
            ax.set_xlabel('RPS HTTP iniciado');ax.set_ylabel(ylabel);ax.grid(alpha=.2)
        fig.suptitle(f'{tag} — Relações descritivas entre taxa realizada e atendimento');save(fig,f'{folder}/{tag}_relacoes_metricas')
        # Outcome cohorts: mutually exclusive.
        fig,ax=plt.subplots(figsize=(9,5));bottom=np.zeros(len(keys))
        for cat,color,hatch in [('HTTP 2xx','#489487',''),('Timeout','#b34d50','//'),('Erro HTTP','#e0ad43','xx'),('Falha de conexão','#756599','..'),('Outro encerramento','#777777','++')]:
            v=np.array([outcomes(D[k]['req'])[cat] for k in keys]);ax.bar(range(len(keys)),v,bottom=bottom,label=cat,color=color,hatch=hatch);bottom+=v
        ax.set_xticks(range(len(keys)),keys);ax.set_ylabel('Tentativas HTTP iniciadas em [30,60)');ax.legend(ncol=3,loc='upper center',bbox_to_anchor=(.5,-.15));ax.grid(axis='y',alpha=.2);ax.set_title(f'{tag} — Desfechos HTTP mutuamente exclusivos');save(fig,f'{folder}/{tag}_desfechos')
    # Pilot A1 separate, never pooled into the B1.2 intensity series.
    rateplot(['A1']+MAIN_A,'A1_piloto')
    # Flooding-specific generation and degradation.
    keys=FLOOD;folder='flooding/comparativas'
    fig,ax=plt.subplots(figsize=(9,4));ax.bar(keys,[S[k]['efficiency_rps'] for k in keys],color=COL['F'],hatch='//');ax.set_ylim(0,1.12);ax.set_ylabel('RPS iniciado / RPS nominal');ax.grid(axis='y',alpha=.2);ax.set_title('F2 — Fração da taxa nominal realizada em [30,60)');save(fig,f'{folder}/F2_fracao_taxa_nominal')
    fig,axes=plt.subplots(4,1,figsize=(10,11),sharex=True)
    for ax,col,ylabel in [(axes[0],'nominal_rps','RPS nominal'),(axes[1],'rps_started','RPS iniciado'),(axes[2],'http_median_ms','HTTP mediana (ms)'),(axes[3],'cpu_mean','CPU Docker média (%)')]:ax.plot([S[k]['nominal_rps'] for k in keys],[S[k][col] for k in keys],marker='o',color=COL['F']);ax.set_ylabel(ylabel);ax.grid(alpha=.2)
    axes[-1].set_xlabel('Intensidade nominal agregada (RPS)');fig.suptitle('F8 — Intensidade nominal, entrega e duração HTTP');save(fig,f'{folder}/F8_intensidade_degradacao')
    fig,axes=plt.subplots(3,1,figsize=(10,9),sharex=True)
    for ax,col,ylabel in [(axes[0],'submitted','Tarefas submetidas'),(axes[1],'http_started','HTTP iniciados'),(axes[2],'not_http_started','Submetidas sem início HTTP')]:ax.bar(keys,[S[k][col] for k in keys],color=COL['F']);ax.set_ylabel(ylabel);ax.grid(axis='y',alpha=.2)
    fig.suptitle('F10 — Etapas observadas no gerador de Flooding');save(fig,f'{folder}/F10_etapas_gerador')
    fig,ax=plt.subplots(figsize=(10,5));base=np.zeros(len(keys))
    for col,label,color,hatch in [('http_success','HTTP 2xx','#4e988a',''),('timeouts','Timeout','#bc5860','//'),('http_error','Erro HTTP','#e1b45f','xx'),('connection_fail','Falha de conexão','#7466a0','..'),('other_outcome','Outro encerramento','#888888','++'),('not_http_started','Submetida sem início HTTP','#444444','\\\\')]:
        values=np.array([S[k][col] for k in keys]);ax.bar(keys,values,bottom=base,label=label,color=color,hatch=hatch);base+=values
    assert all(base[i]==S[k]['submitted'] for i,k in enumerate(keys))
    ax.set_ylabel('Tarefas submetidas na fonte (quantidade)');ax.set_title('F7 — Partição exclusiva das tarefas submetidas');ax.legend(ncol=3,loc='upper center',bbox_to_anchor=(.5,-.15));ax.grid(axis='y',alpha=.2);save(fig,f'{folder}/F7_fluxo_exclusivo')
    fig,axes=plt.subplots(len(keys),1,figsize=(11,2.4*len(keys)),sharex=True)
    for ax,k in zip(axes,keys):
        d=D[k]
        for kind,label,style in [('submitted','Tarefas submetidas','-'),('http_started','HTTP iniciado','--'),('http_finished','HTTP encerrado',':')]:
            counts=np.histogram(d['source_times'][kind],bins=np.arange(151))[0]
            ax.step(np.arange(150),counts,where='post',color=COL['F'],ls=style,label=label)
        temporal(ax);ax.set_ylabel(f'{k}: eventos/s');ax.legend(fontsize=8,ncol=3)
    fig.suptitle('F10 — Submissão de tarefas e eventos HTTP por segundo');save(fig,f'{folder}/F10_etapas_temporais')
    fig,axes=plt.subplots(len(keys),1,figsize=(11,2.3*len(keys)),sharex=True,sharey=True)
    for ax,k in zip(axes,keys):
        x,y=D[k]['source_concurrency'];ax.step(x,y,where='post',color=COL['F'],lw=.8);temporal(ax);ax.set_ylabel(f'{k}: tarefas');ax.set_ylim(0,66)
    fig.suptitle('F10 — Tarefas ativas no gerador (limite configurado: 64)');save(fig,f'{folder}/F10_concorrencia_gerador')
    # Time-resolved source submission vs HTTP start vs end, and network.
    for keys,mech in [(MAIN_A,'assimetria'),(FLOOD,'flooding')]:
        fig,axes=plt.subplots(len(keys),1,figsize=(11,2.3*len(keys)),sharex=True)
        for ax,k in zip(np.atleast_1d(axes),keys):
            d=D[k];q=d['req'];n=d['net'];x=np.arange(150)
            ax.step(x,np.histogram(q.elapsed_seconds,bins=np.arange(151))[0],where='post',label='HTTP iniciado',color=COL[k[0]])
            ax.step(x,np.histogram(q.end_elapsed_seconds,bins=np.arange(151))[0],where='post',label='HTTP encerrado',color=COL[k[0]],ls='--')
            temporal(ax);ax.set_ylabel(f'{k}: req/s');ax.legend(fontsize=8)
        fig.suptitle(f'{mech.capitalize()} — Inícios e encerramentos HTTP por segundo');save(fig,f'{mech}/comparativas/{mech}_taxas_temporais')
        fig,axes=plt.subplots(len(keys),1,figsize=(11,2.3*len(keys)),sharex=True)
        for ax,k in zip(np.atleast_1d(axes),keys):
            d=D[k];n=d['net'];ax.step(np.arange(150),np.histogram(n.elapsed_seconds,bins=np.arange(151))[0],where='post',color=COL[k[0]]);temporal(ax);ax.set_ylabel(f'{k}: pacotes/s')
        fig.suptitle(f'{mech.capitalize()} — Pacotes TCP capturados por segundo');save(fig,f'{mech}/comparativas/{mech}_rede_pacotes')
        fig,axes=plt.subplots(len(keys),1,figsize=(11,2.3*len(keys)),sharex=True)
        for ax,k in zip(np.atleast_1d(axes),keys):
            n=D[k]['net'];weights=n.packet_length.to_numpy()
            ax.step(np.arange(150),np.histogram(n.elapsed_seconds,bins=np.arange(151),weights=weights)[0],where='post',color=COL[k[0]]);temporal(ax);ax.set_ylabel(f'{k}: bytes/s')
        fig.suptitle(f'{mech.capitalize()} — Soma do campo packet_length por segundo (payload TCP)');save(fig,f'{mech}/comparativas/{mech}_rede_payload')
    # Cross-mechanism: separate visual identities and annotate confounding.
    fig,axes=plt.subplots(1,3,figsize=(14,4))
    for ax,col,ylabel in [(axes[0],'cpu_mean','CPU Docker média (%)'),(axes[1],'http_median_ms','HTTP mediana 200 (ms)'),(axes[2],'workers_2_fraction','Fração com dois workers')]:
        for keys,color,label in [(MAIN_A,COL['A'],'Assimetria /expensive'),(FLOOD,COL['F'],'Flooding /medium')]:
            ax.plot([S[k]['rps_started'] for k in keys],[S[k][col] for k in keys],color=color,marker='o',label=label)
            for i,k in enumerate(keys):ax.annotate(k,(S[k]['rps_started'],S[k][col]),xytext=(3,-12-10*i if k.startswith('F') else 3),textcoords='offset points',fontsize=8)
        ax.set_xlabel('RPS HTTP iniciado');ax.set_ylabel(ylabel);ax.grid(alpha=.2)
        lo,hi=ax.get_ylim();ax.set_ylim(lo,hi+(hi-lo)*.12)
    axes[0].legend(fontsize=8,loc='upper left');fig.suptitle('B1 — Mecanismos distintos: comparação apenas descritiva');save(fig,'entre_mecanismos/comparacao_descritiva')
def main():
    global D,S
    D={k:load(k) for k in ALL};S={k:summarize(k,D[k]) for k in ALL}
    inventory()
    pd.DataFrame([S[k] for k in ALL]).to_csv(OUT/'processed/summary.csv',index=False)
    for k,d in D.items():
        f='assimetria' if k.startswith('A') else 'flooding';p=OUT/'processed'/f;p.mkdir(exist_ok=True)
        pd.DataFrame({'t_s':d['work_step'][0],'aguardando':d['work_step'][1],'executando':d['work_step'][2]}).to_csv(p/f'{k}_workers.csv',index=False)
        pd.DataFrame({'t_s':d['http_active'][0],'http_ativos_cliente':d['http_active'][1]}).to_csv(p/f'{k}_http_ativos.csv',index=False)
        pd.DataFrame({'t_s':d['source_concurrency'][0],'tarefas_ativas_gerador':d['source_concurrency'][1]}).to_csv(p/f'{k}_concorrencia_gerador.csv',index=False)
        d['work'].to_csv(p/f'{k}_operacoes.csv',index=False)
    plots()
    checks={'input_sha256':{path:sha for d in D.values() for path,sha in d['hashes'].items()},'runs':{},'figure_pairs':len(FIG)//2}
    for k,d in D.items():
        checks['runs'][k]={'run_id':d['status']['run_id'],'request_ids':len(set(d['req'].request_id)),'rtt_responses':len(d['rtt']),'work_ids':len(set(d['work'].request_id)),'source_counts':dict(d['src']),'journal_counts':dict(d['journal']),'outcomes':dict(outcomes(d['req'])),'clock':d['clock'],'stats_n':len(d['stats']),'active_stats_n':len(d['active_stats']),'stats_cadence_median_s':float(d['stats'].t.diff().median()),'max_running':int(d['work_step'][2].max()),'min_waiting':int(d['work_step'][1].min()),'max_source_concurrency':int(d['source_concurrency'][1].max()),'worker_fractions_sum':float(sum(d['fractions'])),'last_work_finish_s':float(d['work'].finish.max()),'last_http_end_s':float(d['req'].end_elapsed_seconds.max()),'network_rows':len(d['net'])}
    (OUT/'validation/checks.json').write_text(json.dumps(checks,indent=2,ensure_ascii=False))
    (OUT/'manifest.json').write_text(json.dumps({'source_runs':{k:str(PATHS[k].relative_to(ROOT)) for k in ALL},'script':'scripts/generate.py','script_sha256':h(Path(__file__)),'attack_interval_s':[30,60],'run_interval_s':[0,150],'figures':FIG,'summary':'processed/summary.csv','inventory':'inventario_execucoes.csv','checks':'validation/checks.json'},indent=2,ensure_ascii=False))
    print(f'{len(FIG)//2} figuras; 9 execuções B1 processadas')
if __name__=='__main__':main()
