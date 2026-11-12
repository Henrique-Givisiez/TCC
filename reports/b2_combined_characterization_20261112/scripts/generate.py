#!/usr/bin/env python3
"""Caracterização B2; lê apenas artefatos primários e escreve exclusivamente no relatório B2."""
from __future__ import annotations
import csv, hashlib, json
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'reports/b2_combined_characterization_20261112'
E=ROOT/'experiment_results'
PATHS={'A1-L2':E/'legitimate-characterization-a1-20261106T202205Z/L2',
       'B1-A3':E/'b12-isolated-20261107T200251Z/A3','B1-F2':E/'b12-isolated-20261107T200251Z/F2',
       'B2-L':E/'b2-l-20261107T232559Z','B2-A':E/'b2-a-20261107T234426Z',
       'B2-F':E/'b2-f-20261108T000313Z','B2-F96':E/'b2-f96-20261108T002312Z'}
B2=['B2-L','B2-A','B2-F','B2-F96']
COL={'B2-L':'#4e6475','B2-A':'#a12c55','B2-F':'#17698c','B2-F96':'#713b91','A1-L2':'#75879a','B1-A3':'#c47491','B1-F2':'#5ca1ba'}
LEG='#287b55';ATT='#ad3650';TO='#282632'
PHASE={'PRE':(0,30),'ACTIVE':(30,60),'POST':(60,150)}
plt.rcParams.update({'font.size':9,'axes.titlesize':10,'figure.titlesize':13,'pdf.fonttype':42,'savefig.facecolor':'white'})
FIG=[];INPUT={}
def jl(p):
    with p.open() as f:return [json.loads(x) for x in f if x.strip()]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def save(fig,rel,question,notes=''):
    p=OUT/'figures'/rel;p.parent.mkdir(parents=True,exist_ok=True)
    fig.tight_layout(rect=(0,0,1,.97))
    for ext in ['png','pdf']:fig.savefig(p.with_suffix('.'+ext),dpi=300,bbox_inches='tight')
    FIG.append({'path':str(p.relative_to(OUT)),'question':question,'notes':notes})
    plt.close(fig)
def shade(ax,k,full=True):
    if D[k]['cfg']['attack']['enabled']:
        ax.axvspan(30,60,color='#ead8aa',alpha=.37,zorder=-10)
        for x in (30,60):ax.axvline(x,c='#777',lw=.65,ls=':')
    ax.set_xlim(0,150 if full else 90);ax.grid(alpha=.16);ax.set_xlabel('Tempo relativo à execução (s)')
def ecdf(ax,v,label,color,ls='-'):
    v=np.sort(np.asarray(v,dtype=float));v=v[np.isfinite(v)]
    if len(v):ax.plot(v,np.arange(1,len(v)+1)/len(v),label=f'{label} (n={len(v)})',color=color,ls=ls)
def outcome(row):
    if row.outcome=='response':return 'HTTP 2xx' if 200<=row.http_status<300 else 'Outro HTTP'
    e=str(row.error_type).lower()
    if 'timeout' in e:return 'Timeout'
    if 'connect' in e:return 'Falha de conexão'
    return 'Outro encerramento'
def work_steps(w):
    ev=[]
    for r in w.itertuples():ev.extend([(r.submit,1,0),(r.start,-1,1),(r.finish,0,-1)])
    ev.sort(key=lambda x:(x[0],x[1],x[2]))
    t=[0.];wait=[0];run=[0];a=b=0
    # Equal timestamps are processed as a batch; the resulting right-hand state is plotted.
    i=0
    while i<len(ev):
        x=ev[i][0];da=db=0
        while i<len(ev) and ev[i][0]==x:
            da+=ev[i][1];db+=ev[i][2];i+=1
        a+=da;b+=db
        assert a>=0 and 0<=b<=2,(a,b,x)
        t.append(x);wait.append(a);run.append(b)
    t.append(max(150.,t[-1]));wait.append(a);run.append(b)
    assert a==0 and b==0
    return np.array(t),np.array(wait),np.array(run)
def fraction(t,r,l=30,h=60):
    return np.array([sum(max(0,min(y,h)-max(x,l)) for x,y,v in zip(t[:-1],t[1:],r[:-1]) if v==i)/(h-l) for i in range(3)])
def count(t,l=30,h=60):return int(((t>=l)&(t<h)).sum())
def q(v,p):return float(np.percentile(v,p)) if len(v) else None
def load(k):
    raw=PATHS[k]/'raw'
    names=['effective_config.json','run_status.json','request_log.csv','rtt_log.csv','victim_stats.jsonl','diagnostics/victim/events.jsonl','traffic_capture.csv']
    paths=[raw/n for n in names]+sorted((raw/'source_artifacts').glob('*/output/diagnostics/events.jsonl'))+sorted((raw/'source_artifacts').glob('*/output/journal.jsonl'))
    assert all(p.exists() for p in paths)
    for p in paths:INPUT[str(p.relative_to(ROOT))]=sha(p)
    cfg=json.loads(paths[0].read_text());status=json.loads(paths[1].read_text());req=pd.read_csv(paths[2]);rtt=pd.read_csv(paths[3]);statsraw=jl(paths[4]);ve=jl(paths[5]);network=pd.read_csv(paths[6]);src=[jl(p) for p in paths if 'source_artifacts' in str(p) and p.name=='events.jsonl'];journ=[jl(p) for p in paths if p.name=='journal.jsonl']
    assert status['status']=='completed' and status['end_reason']=='simulation_end' and status['producers_drained'] and not status['errors']
    assert cfg['duration_seconds']==150 and cfg['server']['process_pool_workers']==2 and cfg['topology']['mode']=='direct'
    assert len(req)==req.request_id.nunique() and set(req.run_id)=={status['run_id']}
    assert (req.duration_ms>=0).all() and np.allclose(req.end_elapsed_seconds-req.elapsed_seconds,req.duration_ms/1000,atol=.003)
    assert set(rtt.request_id)==set(req.loc[req.outcome=='response','request_id'])
    req['http_status']=pd.to_numeric(req.http_status,errors='coerce')
    req['error_type']=req.error_type.fillna('');req['category']=req.apply(outcome,axis=1)
    assert (req.elapsed_seconds>=0).all() and (req.elapsed_seconds<151).all()
    assert set(x['metrics']['name'] for x in statsraw)=={'target_instance_1'}
    stats=pd.DataFrame([{'t':x['monotonic']-status['experiment_start_monotonic'],'cpu':x['metrics']['cpu_percent'],'mem':x['metrics']['raw_mem_usage']/1048576} for x in statsraw]).sort_values('t')
    assert stats.cpu.notna().all() and stats.mem.notna().all() and (stats.cpu>=0).all() and (stats.mem>=0).all()
    by={z:{x['operation_id']:x for x in ve if x['kind']==z and x.get('traffic_class') in ('benign','attack')} for z in ['work_submitted','work_started','work_completed']}
    if k=='A1-L2':
        v=[x for x in ve if x['kind']=='handler_finished' and x.get('request_id') in set(req.request_id)]
        work=pd.DataFrame([{'request_id':x['request_id'],'class':'benign','submit':x['work_submitted_at']-status['experiment_start_monotonic'],'start':x['work_started_at']-status['experiment_start_monotonic'],'finish':x['work_finished_at']-status['experiment_start_monotonic'],'cpu_ms':x['work_cpu_seconds']*1000} for x in v])
    else:
        assert len(by['work_submitted'])==len(by['work_started'])==len(by['work_completed'])==len(req)
        assert set(by['work_submitted'])==set(by['work_started'])==set(by['work_completed'])
        work=pd.DataFrame([{'request_id':x['request_id'],'class':x['traffic_class'],'submit':x['at']-status['experiment_start_monotonic'],'start':by['work_started'][op]['at']-status['experiment_start_monotonic'],'finish':by['work_completed'][op]['at']-status['experiment_start_monotonic'],'cpu_ms':by['work_completed'][op]['work_cpu_seconds']*1000} for op,x in by['work_submitted'].items()])
        assert all(x['request_id']==by['work_started'][op]['request_id']==by['work_completed'][op]['request_id'] for op,x in by['work_submitted'].items())
    assert len(work)==len(req)==work.request_id.nunique() and set(work.request_id)==set(req.request_id)
    assert ((work.submit<=work.start)&(work.start<=work.finish)&(work.cpu_ms>=0)).all()
    work['wait_ms']=(work.start-work.submit)*1000;work['exec_ms']=(work.finish-work.start)*1000
    merged=work.merge(req[['request_id','elapsed_seconds','traffic_class']],on='request_id',validate='one_to_one')
    assert (merged['class']==merged.traffic_class).all() and (merged.submit>=merged.elapsed_seconds-.05).all()
    src_counts=Counter(x['kind'] for part in src for x in part);journal_counts=Counter(x['kind'] for part in journ for x in part)
    assert src_counts['http_started']==src_counts['http_finished']==len(req)
    assert {x['request_id'] for part in src for x in part if x['kind']=='http_started'}==set(req.request_id)
    assert journal_counts['request_begin']==journal_counts['request_finish']==len(req)
    assert set(network.run_id)=={status['run_id']} and (network.packet_length>=0).all()
    t,w,r=work_steps(work)
    return {'cfg':cfg,'status':status,'req':req,'stats':stats,'work':work,'steps':(t,w,r),'net':network,'source':src_counts,'journal':journal_counts,'src_raw':src,'events':ve}
D={k:load(k) for k in PATHS}

def phase(t):
    if t<30:return 'PRE'
    if t<60:return 'ACTIVE'
    if t<150:return 'POST'
    return 'APÓS 150 s'
def summarize():
    inv=[];rows=[];ph=[]
    for k,d in D.items():
        c=d['cfg'];r=d['req'];w=d['work'];st=d['stats'];a=c['attack'];n=c['normal_traffic'];source=Counter()
        for part in d['src_raw']:
            if not part:continue
            cls='benign' if part[0]['source_id'].startswith('normal_') else 'attack'
            source[(cls,'submitted')]+=sum(x['kind']=='submitted' for x in part)
            source[(cls,'planned')]+=sum(x['kind']=='planned' for x in part)
        inv.append({'id':k,'path':str(PATHS[k].relative_to(ROOT)),'role':'B2' if k in B2 else 'referência histórica','status':d['status']['status'],'mechanism':a.get('mechanism','nenhum') if a['enabled'] else 'nenhum','legitimate_sources':n['clients'],'legitimate_nominal_rps':n['clients']*n['rate'],'attack_sources':a['attackers'],'attack_nominal_rps':a['attackers']*a['rate'],'attack_concurrency':a['max_concurrent_sends'] if a['enabled'] else None,'legitimate_endpoint':n['endpoint'],'attack_endpoint':a['endpoint'] if a['enabled'] else None,'duration_s':c['duration_seconds'],'attack_interval':'[30,60)' if a['enabled'] else 'não aplicável','workers':c['server']['process_pool_workers'],'request_rows':len(r),'victim_stats_samples':len(st),'worker_events':'explícitos' if k!='A1-L2' else 'handler_finished consolidado','eligibility':'B2 direta' if k in B2 else 'histórica visual, sem controle ambiental'})
        for cls in ['benign','attack']:
            rr=r[r.traffic_class==cls];ww=w[w['class']==cls];den=150 if cls=='benign' else 30
            active=rr[(rr.elapsed_seconds>=30)&(rr.elapsed_seconds<60)]
            aa=ww[(ww.submit>=30)&(ww.submit<60)]
            row={'id':k,'class':cls,'nominal_rps':(n['clients']*n['rate'] if cls=='benign' else a['attackers']*a['rate']),'total_started':len(rr),'started_active':len(active),'rps_started_active':len(active)/30,'finished_active':count(rr.end_elapsed_seconds),'rps_finished_active':count(rr.end_elapsed_seconds)/30,'http_2xx_active_cohort':int((active.category=='HTTP 2xx').sum()),'timeouts_active_cohort':int((active.category=='Timeout').sum()),'other_active_cohort':int((~active.category.isin(['HTTP 2xx','Timeout'])).sum()),'submitted_total':source[(cls,'submitted')],'planned_total':source[(cls,'planned')],'submitted_not_http':source[(cls,'submitted')]-len(rr),'http_success_median_ms':float(active.loc[active.category=='HTTP 2xx','duration_ms'].median()) if (active.category=='HTTP 2xx').any() else None,'http_success_p95_ms':q(active.loc[active.category=='HTTP 2xx','duration_ms'],95),'timeout_median_ms':float(active.loc[active.category=='Timeout','duration_ms'].median()) if (active.category=='Timeout').any() else None,'work_cpu_median_ms':float(aa.cpu_ms.median()) if len(aa) else None,'work_cpu_p95_ms':q(aa.cpu_ms,95),'work_wait_median_ms':float(aa.wait_ms.median()) if len(aa) else None,'work_wait_p95_ms':q(aa.wait_ms,95),'work_exec_median_ms':float(aa.exec_ms.median()) if len(aa) else None}
            rows.append(row)
            for p,(l,h) in PHASE.items():
                if cls=='attack' and p!='ACTIVE':continue
                z=rr[(rr.elapsed_seconds>=l)&(rr.elapsed_seconds<h)];sw=ww[(ww.submit>=l)&(ww.submit<h)]
                ph.append({'id':k,'class':cls,'phase':p,'start_s':l,'end_s':h,'started':len(z),'rps_started':len(z)/(h-l),'http_2xx_start_cohort':int((z.category=='HTTP 2xx').sum()),'timeout_start_cohort':int((z.category=='Timeout').sum()),'other_start_cohort':int((~z.category.isin(['HTTP 2xx','Timeout'])).sum()),'success_median_ms':float(z.loc[z.category=='HTTP 2xx','duration_ms'].median()) if (z.category=='HTTP 2xx').any() else None,'success_p95_ms':q(z.loc[z.category=='HTTP 2xx','duration_ms'],95),'timeout_median_ms':float(z.loc[z.category=='Timeout','duration_ms'].median()) if (z.category=='Timeout').any() else None,'work_cpu_median_ms':float(sw.cpu_ms.median()) if len(sw) else None,'work_wait_median_ms':float(sw.wait_ms.median()) if len(sw) else None})
        ss=st[(st.t>=30)&(st.t<60)];t,waiting,running=d['steps']
        row={'id':k,'stats_n_active':len(ss),'stats_cadence_median_s':float(st.t.diff().median()),'cpu_mean_active_pct':float(ss.cpu.mean()),'cpu_median_active_pct':float(ss.cpu.median()),'cpu_max_active_pct':float(ss.cpu.max()),'mem_mean_active_mib':float(ss.mem.mean()),'mem_median_active_mib':float(ss.mem.median()),'mem_max_active_mib':float(ss.mem.max()),'workers_zero_fraction_active':fraction(t,running)[0],'workers_one_fraction_active':fraction(t,running)[1],'workers_two_fraction_active':fraction(t,running)[2],'waiting_max_active':int(max((v for tt,v in zip(t,waiting) if 30<=tt<60),default=0)),'waiting_max_post':int(max((v for tt,v in zip(t,waiting) if 60<=tt<150),default=0)),'waiting_max_full':int(waiting.max()),'network_packets_active':count(d['net'].elapsed_seconds),'network_packet_length_sum_active':int(d['net'].loc[(d['net'].elapsed_seconds>=30)&(d['net'].elapsed_seconds<60),'packet_length'].sum())}
        pd.DataFrame([row]).to_csv(OUT/'processed'/f'infrastructure_{k}.csv',index=False)
        for name,frame in [('requests',r[['request_id','traffic_class','elapsed_seconds','end_elapsed_seconds','duration_ms','category']]),('work',w),('stats',st)]:frame.to_csv(OUT/'processed'/f'{name}_{k}.csv',index=False)
        d['infra']=row
    pd.DataFrame(inv).to_csv(OUT/'inventario_execucoes.csv',index=False)
    pd.DataFrame(rows).to_csv(OUT/'processed/summary.csv',index=False)
    pd.DataFrame(ph).to_csv(OUT/'processed/phase_summary.csv',index=False)
    pd.DataFrame([d['infra'] for d in D.values()]).to_csv(OUT/'processed/infrastructure_summary.csv',index=False)
    return pd.DataFrame(rows),pd.DataFrame(ph),pd.DataFrame([d['infra'] for d in D.values()])
S,P,I=summarize()

def series(ax,k,metric,cls=None,legend=False):
    d=D[k];r=d['req'];w=d['work'];st=d['stats'];t,waiting,running=d['steps'];c=COL[k]
    if metric=='rps':
        for cc,col,lab in [('benign',LEG,'Legítimo'),('attack',ATT,'Ofensivo')]:
            x=r[r.traffic_class==cc]
            if len(x):ax.step(np.arange(150),np.histogram(x.elapsed_seconds,bins=np.arange(151))[0],where='post',color=col,label=lab,lw=1.2)
        ax.set_ylabel('Inícios HTTP\n(RPS)')
    elif metric=='cpu':ax.scatter(st.t,st.cpu,s=10,color=c);ax.set_ylabel('CPU Docker\n(%)')
    elif metric=='mem':ax.scatter(st.t,st.mem,s=10,color=c);ax.set_ylabel('Memória\n(MiB)')
    elif metric=='run':ax.step(t,running,where='post',color=c,lw=.75);ax.set_ylabel('Workers\nocupados');ax.set_ylim(-.1,2.2)
    elif metric=='wait':ax.step(t,waiting,where='post',color=c,lw=.75);ax.set_ylabel('Operações\naguardando')
    elif metric=='cpuop':
        for cc,col,lab in [('benign',LEG,'Legítimo'),('attack',ATT,'Ofensivo')]:
            x=w[w['class']==cc]
            if len(x):ax.scatter(x.submit,x.cpu_ms,s=7,alpha=.35,color=col,label=lab)
        ax.set_ylabel('CPU/operação\n(ms)')
    elif metric=='duration':
        cl='benign' if (r.traffic_class=='benign').any() else 'attack';x=r[r.traffic_class==cl];ok=x[x.category=='HTTP 2xx'];bad=x[x.category=='Timeout']
        ax.scatter(ok.elapsed_seconds,ok.duration_ms,s=7,alpha=.4,color=LEG if cl=='benign' else ATT,label='HTTP 2xx')
        if len(bad):ax.scatter(bad.elapsed_seconds,bad.duration_ms,s=12,marker='x',color=TO,label='Timeout')
        ax.set_ylabel('Duração HTTP\n'+('legítima' if cl=='benign' else 'ofensiva')+' (ms)')
    elif metric=='outcomes':
        x=r[r.traffic_class=='benign']
        for col,label,field in [(LEG,'Inícios','elapsed_seconds'),('#3f9e6b','HTTP 2xx','end_elapsed_seconds'),(TO,'Timeout','end_elapsed_seconds')]:
            xx=x if label=='Inícios' else x[x.category==label]
            ax.step(np.arange(150),np.histogram(xx[field],bins=np.arange(151))[0],where='post',color=col,label=label,lw=1.1,ls='--' if label=='HTTP 2xx' else '-')
        ax.set_ylabel('Legítimas\n(eventos/s)')
    elif metric=='waitms':
        for cc,col,lab in [('benign',LEG,'Legítimo'),('attack',ATT,'Ofensivo')]:
            x=w[w['class']==cc]
            if len(x):ax.scatter(x.submit,x.wait_ms,s=7,alpha=.4,color=col,label=lab)
        ax.set_ylabel('Espera worker\n(ms)')
    elif metric=='network':
        ax.step(np.arange(150),np.histogram(d['net'].elapsed_seconds,bins=np.arange(151))[0],where='post',color=c,lw=1);ax.set_ylabel('Pacotes TCP\n(pacotes/s)')
    if legend:
        h,l=ax.get_legend_handles_labels()
        if h:ax.legend(loc='upper right',fontsize=7,ncol=min(3,len(h)))
    shade(ax,k)

def integrated(k,compact=False):
    metrics=['rps','cpu','mem','run','wait','cpuop','duration','outcomes'] if not compact else ['rps','cpu','mem','run','duration','outcomes']
    fig,axs=plt.subplots(len(metrics),1,figsize=(12,17 if not compact else 12),sharex=True)
    for ax,m in zip(axs,metrics):series(ax,k,m,legend=m in ('rps','cpuop','duration','outcomes'))
    fig.suptitle(f'{k} — tráfego e infraestrutura: painel temporal {"completo" if not compact else "compacto"}  |  {"ataque" if D[k]["cfg"]["attack"]["enabled"] else "janela de referência"} [30,60) s')
    save(fig,f'b2_individuais/{k}_painel_{"completo" if not compact else "compacto"}','Evolução simultânea da carga e do atendimento legítimo','Eventos alinhados ao relógio monotônico da execução; pontos Docker reais.')
for k in B2:
    integrated(k)
    integrated(k,True)

def composition(mech,b2,base='B2-L',compact=False):
    iso='B1-A3' if mech=='assimetria' else 'B1-F2';keys=[base,iso,b2]
    metrics=['rps','cpu','cpuop','mem','run','wait','duration'] if not compact else ['rps','cpu','mem','duration']
    fig,axs=plt.subplots(len(metrics),3,figsize=(17,18 if not compact else 11),sharex='col',sharey='row')
    for j,k in enumerate(keys):
        for i,m in enumerate(metrics):
            series(axs[i,j],k,m,legend=(j==2 and m in ('rps','cpuop','duration')))
            if j>0:axs[i,j].set_ylabel('')
        axs[0,j].set_title(k+(' — referência histórica' if k.startswith(('B1','A1')) else ''))
    fig.suptitle(f'Composição visual — {mech}: legítimo isolado, ofensivo isolado e combinado'+(' | compacto' if compact else ' | completo'))
    save(fig,f'composicao_cargas/{mech}_{base}_{b2}_{"compacta" if compact else "completa"}','Como as cargas isoladas diferem da execução simultânea','Comparação visual histórica; CPU e memória não são somadas entre campanhas.')
for mech,b2 in [('assimetria','B2-A'),('flooding','B2-F'),('flooding','B2-F96')]:
    for base in ['B2-L','A1-L2']:
        composition(mech,b2,base,False);composition(mech,b2,base,True)

def matrix(metric,title,path,shared=True):
    fig,axs=plt.subplots(2,2,figsize=(13,8),sharex=True,sharey=shared)
    for ax,k in zip(axs.flat,B2):series(ax,k,metric,legend=metric in ('rps','duration','outcomes'));ax.set_title(k)
    fig.suptitle(title+(' | escala comum' if shared else ' | escala individual'))
    save(fig,path,'Comparação temporal das quatro condições B2','Amostras reais e eventos reconstruídos; ataque [30,60) s.')
for m,title in [('rps','RPS iniciado'),('cpu','CPU Docker da vítima'),('mem','Memória da vítima'),('run','Workers ocupados'),('wait','Operações aguardando'),('cpuop','Tempo de CPU por operação'),('waitms','Espera por worker'),('duration','Duração HTTP legítima'),('outcomes','Atendimento legítimo'),('network','Pacotes TCP')]:
    matrix(m,title,f'comparativas/matriz_{m}')
for m in ['mem','duration','wait']:
    matrix(m,{'mem':'Memória','duration':'Duração HTTP legítima','wait':'Operações aguardando'}[m],f'comparativas/matriz_{m}_escala_individual',False)

def two_column(keys,metrics,title,path):
    fig,axs=plt.subplots(len(metrics),2,figsize=(14,max(10,2.2*len(metrics))),sharex=True,sharey='row')
    for j,k in enumerate(keys):
        for i,m in enumerate(metrics):series(axs[i,j],k,m,legend=m in ('rps','duration','outcomes','cpuop'))
        axs[0,j].set_title(k+(' — concorrência ofensiva 64' if k=='B2-F' else ' — concorrência ofensiva 96'))
    fig.suptitle(title)
    save(fig,path,'Comparação direta F64 versus F96','Uma execução por condição; escalas comuns por linha.')
two_column(['B2-F','B2-F96'],['rps','cpu','mem','run','wait','cpuop','waitms','duration','outcomes'],'Flooding combinado — concorrências 64 e 96 | completo','flooding_64_vs_96/temporal_completo')
two_column(['B2-F','B2-F96'],['rps','cpu','mem','duration','outcomes'],'Flooding combinado — concorrências 64 e 96 | compacto','flooding_64_vs_96/temporal_compacto')

def bars_outcomes(percent=False):
    cats=['HTTP 2xx','Outro HTTP','Timeout','Falha de conexão','Outro encerramento'];colors=[LEG,'#cd9559',TO,'#8d5871','#777']
    fig,ax=plt.subplots(figsize=(9,5));bottom=np.zeros(4)
    for cat,col in zip(cats,colors):
        vals=np.array([int((D[k]['req'].query("traffic_class == 'benign' and elapsed_seconds >= 30 and elapsed_seconds < 60").category==cat).sum()) for k in B2])
        if percent:vals=100*vals/np.array([len(D[k]['req'].query("traffic_class == 'benign' and elapsed_seconds >= 30 and elapsed_seconds < 60")) for k in B2])
        ax.bar(B2,vals,bottom=bottom,color=col,label=cat);bottom+=vals
    ax.set_ylabel('% das tentativas HTTP iniciadas' if percent else 'Tentativas HTTP iniciadas (quantidade)');ax.legend(ncol=3,fontsize=8,loc='upper center',bbox_to_anchor=(.5,-.12));ax.grid(axis='y',alpha=.2)
    ax.set_title('Desfechos legítimos por início em [30,60) s'+(' — proporção' if percent else ' — contagem'))
    save(fig,f'degradacao_legitima/desfechos_{"percentual" if percent else "absoluto"}','Quais tentativas legítimas tiveram resposta ou timeout?','Categorias mutuamente exclusivas; denominador: inícios HTTP legítimos em [30,60) s.')
for b in (False,True):bars_outcomes(b)

def distribution(field,source,keys,path,title,filterfn=None,log=False):
    fig,axs=plt.subplots(1,2,figsize=(13,5));vals=[]
    for k in keys:
        f=D[k][source]
        if filterfn:f=filterfn(f)
        v=f[field].dropna().to_numpy();vals.append(v);ecdf(axs[1],v,k,COL[k])
    bp=axs[0].boxplot(vals,patch_artist=True,showfliers=False,whis=(5,95))
    for p,k in zip(bp['boxes'],keys):p.set_facecolor(COL[k]);p.set_alpha(.58)
    axs[0].set_xticks(range(1,len(keys)+1),keys,rotation=25);axs[0].set_title('Distribuição: bigodes p5–p95')
    axs[1].set_title('ECDF');axs[1].legend(fontsize=7);axs[1].set_ylabel('Fração acumulada')
    for ax in axs:ax.grid(alpha=.17);ax.set_ylabel({'cpu':'CPU Docker (%)','mem':'Memória (MiB)','cpu_ms':'CPU por operação (ms)','wait_ms':'Espera por worker (ms)','exec_ms':'Execução computacional (ms)','duration_ms':'Duração HTTP (ms)'}[field] if ax is axs[0] else 'Fração acumulada')
    if log:
        for ax in axs:ax.set_yscale('log' if ax is axs[0] else 'linear')
        axs[1].set_xscale('log')
    fig.suptitle(title)
    save(fig,path,'Distribuição comparativa entre condições','Amostras temporais e requisições não são repetições independentes.')
for field in ['cpu','mem']:
    distribution(field,'stats',B2,f'{field}/distribuicao_{field}' if field=='cpu' else 'memoria/distribuicao_memoria',f'{field.upper() if field=="cpu" else "Memória"} da vítima — observações em [30,60) s',lambda x:x[(x.t>=30)&(x.t<60)])
for cls,name in [('benign','legitima'),('attack','ofensiva')]:
    keys=B2 if cls=='benign' else B2[1:]
    for field,path,title in [('cpu_ms',f'cpu/cpu_operacao_{name}',f'Tempo de CPU por operação {name}'),('wait_ms',f'workers/espera_{name}',f'Espera por worker — classe {name}')]:
        distribution(field,'work',keys,path,title,lambda x:x[(x['class']==cls)&(x.submit>=30)&(x.submit<60)])
distribution('duration_ms','req',B2,'degradacao_legitima/duracao_sucessos','Duração HTTP legítima — respostas 2xx iniciadas em [30,60) s',lambda x:x[(x.traffic_class=='benign')&(x.category=='HTTP 2xx')&(x.elapsed_seconds>=30)&(x.elapsed_seconds<60)])
distribution('duration_ms','req',['B2-A','B2-F96'],'degradacao_legitima/tempo_ate_timeout','Tempo até timeout legítimo — inícios em [30,60) s',lambda x:x[(x.traffic_class=='benign')&(x.category=='Timeout')&(x.elapsed_seconds>=30)&(x.elapsed_seconds<60)])

def rate_bars():
    fig,ax=plt.subplots(figsize=(10,5));x=np.arange(4);bw=.19
    for j,(field,label,col) in enumerate([('nominal_rps','Nominal','#aab1b7'),('rps_started_active','Inícios HTTP',LEG),('http_2xx_active_cohort','Respostas 2xx da coorte','#68ae84'),('timeouts_active_cohort','Timeouts da coorte',TO)]):
        vals=[]
        for k in B2:
            a=S[(S.id==k)&(S['class']=='benign')].iloc[0]
            vals.append(a[field]/30 if field.endswith('_cohort') else a[field])
        ax.bar(x+(j-1.5)*bw,vals,bw,label=label,color=col)
    ax.set_xticks(x,B2);ax.set_ylabel('Requisições por segundo (RPS)');ax.legend(ncol=2,fontsize=8);ax.grid(axis='y',alpha=.2);ax.set_title('Taxas legítimas em [30,60) s — desfechos da coorte iniciada')
    save(fig,'degradacao_legitima/taxas_legitimas','Taxa nominal, inícios e desfechos legítimos','Respostas/timeouts atribuídos ao instante de início; conclusão pode ocorrer após 60 s.')
rate_bars()

def phase_bars(metric,title,ylabel,path,source='phase'):
    fig,ax=plt.subplots(figsize=(10,5));x=np.arange(4);bw=.24
    for j,p in enumerate(PHASE):
        vals=[]
        for k in B2:
            if source=='phase':
                row=P[(P.id==k)&(P['class']=='benign')&(P.phase==p)].iloc[0]
                vals.append(row[metric])
            else:
                z=D[k]['stats'];l,h=PHASE[p];z=z[(z.t>=l)&(z.t<h)];vals.append(float(z[metric].median()) if len(z) else np.nan)
        ax.bar(x+(j-1)*bw,vals,bw,label=p,color=['#b4c2ca','#d8aa61','#7c9caf'][j])
    ax.set_xticks(x,B2);ax.set_ylabel(ylabel);ax.legend();ax.grid(axis='y',alpha=.2);ax.set_title(title+' | PRE [0,30), ACTIVE [30,60), POST [60,150)')
    save(fig,path,'Diferenças descritivas por fase','Fases com 30, 30 e 90 s; contagens atribuídas pelo início HTTP.')
for args in [('rps_started','RPS legítimo por fase','Inícios HTTP/s','degradacao_legitima/rps_por_fase'),('timeout_start_cohort','Timeouts legítimos por fase','Timeouts (quantidade)','degradacao_legitima/timeouts_por_fase'),('success_median_ms','Mediana de duração 2xx por fase','Duração HTTP (ms)','degradacao_legitima/duracao_por_fase')]:phase_bars(*args)
phase_bars('cpu','Mediana de CPU Docker por fase','CPU Docker (%)','cpu/cpu_por_fase','stats')
phase_bars('mem','Mediana de memória por fase','Memória (MiB)','memoria/memoria_por_fase','stats')

def occupancy():
    fig,axs=plt.subplots(1,2,figsize=(13,5));x=np.arange(4);bottom=np.zeros(4)
    for i,(label,col) in enumerate([('0 workers','#c2cbd0'),('1 worker','#78a8b2'),('2 workers','#b54b62')]):
        v=np.array([D[k]['infra'][['workers_zero_fraction_active','workers_one_fraction_active','workers_two_fraction_active'][i]] for k in B2])*100
        axs[0].bar(B2,v,bottom=bottom,label=label,color=col);bottom+=v
    axs[0].set_ylabel('Tempo em [30,60) (%)');axs[0].legend(fontsize=8);axs[0].set_title('Ocupação dos dois workers')
    for j,(field,label) in enumerate([('waiting_max_active','ACTIVE'),('waiting_max_post','POST'),('waiting_max_full','Completa')]):
        axs[1].bar(x+(j-1)*.23,[D[k]['infra'][field] for k in B2],.23,label=label)
    axs[1].set_xticks(x,B2);axs[1].set_ylabel('Operações aguardando (máximo)');axs[1].legend(fontsize=8);axs[1].set_title('Máximos de operações aguardando')
    for ax in axs:ax.grid(axis='y',alpha=.2)
    fig.suptitle('Ocupação e acúmulo computacional — B2')
    save(fig,'workers/ocupacao_e_acumulo','Workers ocupados e operações aguardando','Aguardando = submetidas sem início; não representa a fila interna exata do executor.')
occupancy()

def f_comparison():
    fields=[('attack','rps_started_active','RPS ofensivo iniciado'),('benign','rps_started_active','RPS legítimo iniciado'),('benign','http_2xx_active_cohort','Sucessos legítimos'),('benign','timeouts_active_cohort','Timeouts legítimos'),('benign','http_success_median_ms','Mediana HTTP 2xx (ms)'),('benign','work_cpu_median_ms','CPU operação legítima (ms)'),('benign','work_wait_median_ms','Espera legítima (ms)')]
    fig,axs=plt.subplots(3,4,figsize=(16,9));axs=axs.flat
    for ax,(cl,field,label) in zip(axs,fields):
        vals=[S[(S.id==k)&(S['class']==cl)].iloc[0][field] for k in ['B2-F','B2-F96']]
        ax.bar(['F64','F96'],vals,color=[COL['B2-F'],COL['B2-F96']]);ax.set_title(label);ax.grid(axis='y',alpha=.2)
    fields2=[('cpu_mean_active_pct','CPU Docker média (%)'),('mem_mean_active_mib','Memória média (MiB)'),('workers_two_fraction_active','Fração com 2 workers'),('waiting_max_active','Máximo aguardando')]
    for ax,(field,label) in zip(list(axs)[len(fields):],fields2):
        vals=[D[k]['infra'][field] for k in ['B2-F','B2-F96']];ax.bar(['F64','F96'],vals,color=[COL['B2-F'],COL['B2-F96']]);ax.set_title(label);ax.grid(axis='y',alpha=.2)
    for ax in list(axs)[len(fields)+len(fields2):]:ax.axis('off')
    fig.suptitle('Flooding combinado — indicadores em [30,60) s: concorrências 64 e 96')
    save(fig,'flooding_64_vs_96/indicadores','Como F64 e F96 diferiram na fase ofensiva?','Coorte de início [30,60); uma execução por condição.')
f_comparison()

def cpu_pressure():
    for k in B2:
        fig,axs=plt.subplots(4,1,figsize=(12,10),sharex=True)
        for ax,m in zip(axs,['cpu','run','waitms','duration']):series(ax,k,m,legend=m=='duration')
        fig.suptitle(f'{k} — pressão computacional e duração legítima')
        save(fig,f'cpu/pressao_atendimento_{k}','Coincidência temporal de CPU, workers, espera e atendimento','Coincidência não demonstra causalidade; pontos de operações e Docker têm cadências diferentes.')
        fig,ax=plt.subplots(figsize=(11,4));series(ax,k,'network');fig.suptitle(f'{k} — pacotes TCP capturados por segundo')
        save(fig,f'comparativas/rede_{k}','Volume de pacotes TCP','Captura total; packet_length não equivale a bytes no fio nem identifica classe.')
cpu_pressure()

# Manifesto e documentação são gerados depois das figuras, preservando caminhos relativos.
manifest={'schema_version':1,'code_version':'b2-characterization-v1','inputs_sha256':INPUT,'scripts_sha256':{},'figures':FIG,'figure_count':len(FIG),'figure_files':2*len(FIG),'processed':sorted(str(p.relative_to(OUT)) for p in (OUT/'processed').glob('*.csv')),'parameters':{'duration_s':150,'phase_pre':[0,30],'phase_active':[30,60],'phase_post':[60,150],'rps_bin_s':1,'rps_interval':'[30,60) por tempo do evento; desfechos por coorte de início quando indicado','memory':'raw_mem_usage / 1048576 MiB','cpu':'Docker cpu_percent; pode exceder 100%'}}
for p in (OUT/'scripts').glob('*.py'):manifest['scripts_sha256'][str(p.relative_to(OUT))]=sha(p)
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
print(f'Geradas {len(FIG)} figuras em PNG e PDF.')
