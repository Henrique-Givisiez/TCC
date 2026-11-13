#!/usr/bin/env python3
"""Figuras da campanha definitiva a partir dos CSVs auditados e dos manifests oficiais."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'reports/scientific_campaign_visualization_20261112';PR=OUT/'processed'
INV=pd.read_csv(OUT/'inventario_execucoes.csv');TEST=INV[INV.partition=='TEST'];S=pd.read_csv(PR/'signals.csv');D=pd.read_csv(PR/'detectors.csv');P=pd.read_csv(PR/'performance.csv');I=pd.read_csv(PR/'infrastructure.csv');H=pd.read_csv(PR/'http_phases.csv');CAL=pd.read_csv(PR/'calibration.csv')
F={'ingress_packet_count':'Pacotes TCP/s','ingress_tcp_payload_length_sum_bytes':'Payload TCP (bytes/s)','request_starts':'Inícios HTTP/s','mean_duration_ms':'Duração HTTP média (ms)','mean_cpu_percent':'CPU da vítima (%)'}
M=['zscore','cov','ewma','cusum-freeze'];SC=['L2','A3','F96'];SCNAME={'L2':'Legítimo','A3':'Assimetria','F96':'Flooding'}
C={'L2':'#476b83','A3':'#a12c55','F96':'#7a4998','benign':'#27805b','attack':'#b7464b','alarm':'#252532','threshold':'#ce7b2a'}
plt.rcParams.update({'font.size':9,'axes.titlesize':10,'figure.titlesize':13,'pdf.fonttype':42,'savefig.facecolor':'white'})
CAT=[]
def save(fig,group,name,scenario='',method='',feature='',run='',kind='',question='',sources='',period='[0,390) s',observation='',limitation=''):
 path=OUT/'figures'/group/name;path.parent.mkdir(parents=True,exist_ok=True)
 if not fig.get_constrained_layout():fig.tight_layout(rect=(0,0,1,.97))
 fig.savefig(path.with_suffix('.png'),dpi=300,bbox_inches='tight');fig.savefig(path.with_suffix('.pdf'),bbox_inches='tight');plt.close(fig)
 CAT.append({'id':name,'path':str(path.with_suffix('.png').relative_to(OUT)),'group':group.split('/')[0],'scenario':scenario,'detector':method,'signal':feature,'run':run,'type':kind,'question':question,'sources':sources,'period':period,'observation':observation,'limitation':limitation,'validated':'pending'})
def decorate(ax,sc,limit=(0,390)):
 if sc!='L2':ax.axvspan(150,270,color='#e9d9a8',alpha=.4,zorder=-10);ax.axvline(150,c='#777',ls=':',lw=.7);ax.axvline(270,c='#777',ls=':',lw=.7)
 ax.set_xlim(*limit);ax.grid(alpha=.16)
def label(ax,y):ax.set_ylabel(y);ax.set_xlabel('Tempo relativo à execução (s)')
def signal(e,f):return S[(S.entry_id==e)&(S.feature==f)].sort_values('window_index')
def trace(e,f,m):return D[(D.entry_id==e)&(D.feature==f)&(D.method==m)].sort_values('t')
def per(e,f,m):return P[(P.entry_id==e)&(P.feature==f)&(P.method==m)].iloc[0]
def ids(sc):return TEST.loc[TEST.scenario==sc,'entry_id'].tolist()
def medoid():
 rows=[]
 for sc in SC:
  x=I[(I.scenario==sc)&(I.phase=='ACTIVE')].copy();med=x.cpu_mean.median();x['distance']=(x.cpu_mean-med).abs();z=x.sort_values(['distance','entry_id']).iloc[0];rows.append({'scenario':sc,'entry_id':z.entry_id,'block':int(z.block),'criterion':'CPU média ACTIVE mais próxima da mediana do cenário','active_cpu_mean':z.cpu_mean,'scenario_cpu_median':med})
 pd.DataFrame(rows).to_csv(PR/'selected_runs.csv',index=False)
 return {r['scenario']:r['entry_id'] for r in rows}
REP=medoid()
def ecdf(ax,v,label,color):
 v=np.sort(pd.Series(v).dropna().to_numpy(dtype=float));
 if len(v):ax.plot(v,np.arange(1,len(v)+1)/len(v),label=f'{label} (n={len(v)})',color=color)

def infrastructure_panels():
 for _,r in TEST.iterrows():
  e=r.entry_id;sc=r.scenario;sec=pd.read_csv(PR/f'seconds_{e}.csv');cpu=pd.read_csv(PR/f'docker_{e}.csv');mem=pd.read_csv(PR/f'memory_{e}.csv');htt=pd.read_csv(PR/f'http_{e}.csv');work=pd.read_csv(PR/f'work_{e}.csv')
  fig,axs=plt.subplots(8,1,figsize=(12,17),sharex=True)
  axs[0].step(sec.t,sec.benign_http_started,label='Legítimo',c=C['benign'],where='post');axs[0].step(sec.t,sec.attack_http_started,label='Ofensivo',c=C['attack'],where='post');axs[0].legend(fontsize=7);label(axs[0],'Inícios HTTP/s')
  axs[1].scatter(cpu.t,cpu.cpu,s=6,c=C[sc]);label(axs[1],'CPU Docker (%)')
  axs[2].scatter(mem.t,mem.mem,s=9,c=C[sc]);label(axs[2],'Memória (MiB)')
  axs[3].step(sec.t,sec.workers_mean,c=C[sc],where='post');label(axs[3],'Workers ocupados\n(média/s)')
  axs[4].step(sec.t,sec.waiting_mean,c=C[sc],where='post');label(axs[4],'Operações aguardando\n(média/s)')
  for cl,col,lab in [('benign',C['benign'],'Legítima'),('attack',C['attack'],'Ofensiva')]:
   z=work[work.traffic_class==cl]
   if len(z):axs[5].scatter(z.submit_s,z.cpu_ms,s=3,alpha=.2,c=col,label=lab)
  axs[5].legend(fontsize=7);label(axs[5],'CPU/operação (ms)')
  z=htt[htt.traffic_class=='benign'];a=z[z.category=='http_2xx'];b=z[z.category=='timeout'];axs[6].scatter(a.elapsed_seconds,a.duration_ms,s=3,alpha=.25,c=C['benign'],label='HTTP 2xx');
  if len(b):axs[6].scatter(b.elapsed_seconds,b.duration_ms,s=5,marker='x',c=C['alarm'],label='Timeout')
  axs[6].legend(fontsize=7);label(axs[6],'Duração HTTP\nlegítima (ms)')
  for key,col,lab in [('benign_http_started',C['benign'],'Inícios'),('benign_http_2xx','#55a779','2xx concluídos'),('benign_http_timeout',C['alarm'],'Timeouts')]:axs[7].step(sec.t,sec[key],where='post',c=col,label=lab,lw=1)
  axs[7].legend(fontsize=7,ncol=3);label(axs[7],'Atendimento\n(eventos/s)')
  for ax in axs:decorate(ax,sc)
  fig.suptitle(f'{e} — infraestrutura e atendimento HTTP | bloco {int(r.block)}')
  save(fig,'infraestrutura/individuais',e+'_infraestrutura',sc,run=e,kind='painel temporal',question='Como a vítima e os clientes evoluíram?',sources='request_log; victim_stats; simulation_metrics; eventos work',observation='Séries observadas e estados reconstruídos no mesmo tempo relativo',limitation='Uma execução; CPU e memória com cadências distintas')
  print('infra',e,flush=True)

def signal_panels():
 for _,r in TEST.iterrows():
  e=r.entry_id;sc=r.scenario;fig,axs=plt.subplots(5,1,figsize=(11,11),sharex=True)
  for ax,(f,y) in zip(axs,F.items()):
   z=signal(e,f);ax.plot(z.window_index,z.value,c=C[sc],lw=.8);decorate(ax,sc);label(ax,y)
  fig.suptitle(f'{e} — cinco sinais de 1 s | bloco {int(r.block)}')
  save(fig,'sinais/individuais',e+'_cinco_sinais',sc,run=e,kind='painel temporal',question='Como os cinco sinais evoluíram?',sources='features/timeseries/network, service, infrastructure',observation='CPU é descritiva; quatro sinais foram elegíveis aos detectores',limitation='Janelas nulas preservadas; duração média não é duração individual')
  print('signals',e,flush=True)
 for f in F:
  fig,axs=plt.subplots(3,1,figsize=(11,9),sharex=True,sharey=True)
  for ax,sc in zip(axs,SC):
   for e in ids(sc):
    z=signal(e,f);ax.plot(z.window_index,z.value,lw=.45,alpha=.22,c=C[sc])
   decorate(ax,sc);label(ax,F[f]);ax.set_title(f'{SCNAME[sc]} — 20 execuções')
  fig.suptitle(f'{F[f]} — variabilidade temporal por cenário | escala comum')
  save(fig,'sinais/comparativas',f+'_matriz_cenarios',feature=f,kind='matriz temporal',question='Como as repetições diferem?',sources='features/timeseries',observation='20 trajetórias por cenário, sem interpolação',limitation='Sobreposição visual não representa inferência')
  fig,axs=plt.subplots(1,2,figsize=(12,5))
  vals=[]
  for sc in SC:
   x=S[(S.partition=='TEST')&(S.scenario==sc)&(S.feature==f)&(S.window_index>=150)&(S.window_index<270)].value.dropna();vals.append(x);ecdf(axs[1],x,SCNAME[sc],C[sc])
  bp=axs[0].boxplot(vals,showfliers=False,patch_artist=True,whis=(5,95))
  for box,sc in zip(bp['boxes'],SC):box.set_facecolor(C[sc]);box.set_alpha(.5)
  axs[0].set_xticks([1,2,3],[SCNAME[x] for x in SC]);axs[0].set_ylabel(F[f]);axs[0].grid(axis='y',alpha=.2);axs[1].set_xlabel(F[f]);axs[1].set_ylabel('Fração acumulada');axs[1].legend();axs[1].grid(alpha=.2)
  fig.suptitle(f'{F[f]} — distribuição das janelas [150,270) s')
  save(fig,'sinais/distribuicoes',f+'_box_ecdf',feature=f,kind='boxplot e ECDF',question='Quais níveis foram observados na fase ofensiva?',sources='features/timeseries',period='[150,270) s',observation='Distribuição descritiva de janelas',limitation='Janelas correlacionadas; não são repetições independentes')

def alarm_rasters():
 for _,r in TEST.iterrows():
  e=r.entry_id;sc=r.scenario;x=D[D.entry_id==e];fig,ax=plt.subplots(figsize=(12,6));labels=[]
  for i,(m,f) in enumerate((m,f) for m in M for f in list(F)[:4]):
   z=x[(x.method==m)&(x.feature==f)];t=z.loc[z.decision==True,'t'].to_numpy();ax.vlines(t,i-.38,i+.38,colors=C['alarm'],lw=.7);labels.append(m+' · '+f.replace('ingress_','').replace('_count','').replace('_ms',''))
  ax.set_yticks(range(16),labels,fontsize=7);ax.set_ylim(-.8,15.8);decorate(ax,sc);ax.set_xlabel('Tempo relativo à execução (s)');ax.set_title(f'{e} — raster de alarmes por janela')
  save(fig,'alarmes/individuais',e+'_raster',sc,run=e,kind='raster temporal',question='Quando cada par detector × sinal alarmou?',sources='analysis/<sinal>/TEST/<execução>/manifest.json',observation='Cada marca é uma janela em alarme, não um evento independente',limitation='FPR e detecção seguem avaliação oficial')
  print('alarms',e,flush=True)
 for sc in SC:
  fig,axs=plt.subplots(4,1,figsize=(12,10),sharex=True)
  for ax,m in zip(axs,M):
   for j,f in enumerate(list(F)[:4]):
    z=D[(D.entry_id==REP[sc])&(D.method==m)&(D.feature==f)];ax.vlines(z.loc[z.decision==True,'t'],j-.35,j+.35,colors=C['alarm'],lw=.8)
   ax.set_yticks(range(4),list(F)[:4],fontsize=7);ax.set_title(m);decorate(ax,sc)
  fig.suptitle(f'{SCNAME[sc]} — alarmes dos quatro detectores | {REP[sc]}')
  save(fig,'alarmes/matrizes',sc+'_matriz_detectores_sinais',sc,run=REP[sc],kind='matriz detector × sinal',question='Como os pares reagiram na execução mediana de CPU?',sources='TEST manifests oficiais',observation='Seleção objetiva pelo CPU médio ACTIVE próximo da mediana',limitation='Uma execução ilustrativa por cenário')

def detector_trace(e,sc,f,m,zoom=None):
 z=trace(e,f,m);fig,axs=plt.subplots(3,1,figsize=(11,8),sharex=True,gridspec_kw={'height_ratios':[1.4,1.2,.7]})
 axs[0].plot(z.t,z.value,c=C[sc],lw=.8);label(axs[0],F[f])
 axs[1].plot(z.t,z.score,c='#2d6f9b',lw=.85,label='Estatística / candidato')
 axs[1].axhline(z.threshold.dropna().iloc[0],c=C['threshold'],ls='--',lw=1,label='Limiar calibrado')
 if m=='cusum-freeze':
  axs[1].plot(z.t,z.posterior_state,c='#9163a1',lw=.75,ls=':',label='Estado preservado após rejeição')
  q=z[z.update_accepted==False];axs[1].scatter(q.t,q.score,c=C['alarm'],s=10,marker='x',label='Atualização rejeitada')
 axs[1].legend(fontsize=7,ncol=2);label(axs[1],'Estatística (unid. do método)')
 zz=z.decision.fillna(False).astype(int);axs[2].step(z.t,zz,where='post',c=C['alarm'],lw=.9,label='Alarme por janela');axs[2].set_yticks([0,1]);label(axs[2],'Alarme (0/1)')
 for ax in axs:decorate(ax,sc,zoom if zoom else (0,390))
 fig.suptitle(f'{e} — {m} × {f}'+(f' | recorte {zoom[0]}–{zoom[1]} s' if zoom else ' | execução completa'))
 suffix=f'_{zoom[0]}_{zoom[1]}' if zoom else '_completo'
 save(fig,f'detectores/{m}',e+'_'+f+'_'+m+suffix,sc,m,f,e,'sinal, estatística e alarme','Como a decisão emerge da trajetória oficial?','features/timeseries; TEST manifest; calibration manifest',str(zoom)+' s' if zoom else '[0,390) s','CUSUM: candidato, estado posterior e rejeição separados' if m=='cusum-freeze' else 'Limiar oficial de CAL_A, preservado em TEST','Uma execução; sem recalibração')

def detailed_traces(all_traces=False):
 pairs=[(REP[sc],sc,f,m) for sc in SC for f in list(F)[:4] for m in M]
 if all_traces:pairs=[(e,sc,f,m) for sc in SC for e in ids(sc) for f in list(F)[:4] for m in M]
 for j,(e,sc,f,m) in enumerate(pairs):
  detector_trace(e,sc,f,m)
  if not all_traces:detector_trace(e,sc,f,m,(140,185));detector_trace(e,sc,f,m,(255,300))
  if j%20==0:print('traces',j+1,'/',len(pairs),flush=True)

def detector_matrices():
 for sc in SC:
  e=REP[sc]
  for f in list(F)[:4]:
   fig,axs=plt.subplots(5,1,figsize=(11,10),sharex=True)
   z=signal(e,f);axs[0].plot(z.window_index,z.value,c=C[sc],lw=.8);label(axs[0],F[f]);decorate(axs[0],sc)
   for ax,m in zip(axs[1:],M):
    d=trace(e,f,m);ax.step(d.t,d.decision.fillna(False).astype(int),where='post',c=C['alarm'],lw=.8);ax.set_yticks([0,1]);label(ax,m);decorate(ax,sc)
   fig.suptitle(f'{e} — quatro detectores sobre {f}')
   save(fig,'comparacoes/por_sinal',e+'_'+f+'_quatro_detectores',sc,feature=f,run=e,kind='matriz por sinal',question='Como quatro detectores reagiram ao mesmo sinal?',sources='TEST manifests e features',observation='Execução selecionada por critério de CPU',limitation='Sem comparação inferencial nesta figura')
  for m in M:
   fig,axs=plt.subplots(4,1,figsize=(11,9),sharex=True)
   for ax,f in zip(axs,list(F)[:4]):
    d=trace(e,f,m);ax.step(d.t,d.decision.fillna(False).astype(int),where='post',c=C['alarm'],lw=.8);ax.set_yticks([0,1]);label(ax,f);decorate(ax,sc)
   fig.suptitle(f'{e} — {m} em quatro sinais elegíveis')
   save(fig,'comparacoes/por_detector',e+'_'+m+'_quatro_sinais',sc,m,run=e,kind='matriz por detector',question='Em quais sinais o detector alarmou?',sources='TEST manifests oficiais',observation='CPU não integra a matriz de detectores do protocolo',limitation='Uma execução selecionada objetivamente')

def phase_distribution(field,table,group,ylabel):
 fig,axs=plt.subplots(1,2,figsize=(12,4.5))
 vals=[]
 for sc in SC:
  z=table[(table.scenario==sc)&(table.phase=='ACTIVE')][field].dropna();vals.append(z);ecdf(axs[1],z,SCNAME[sc],C[sc])
 bp=axs[0].boxplot(vals,showfliers=True,patch_artist=True)
 for box,sc in zip(bp['boxes'],SC):box.set_facecolor(C[sc]);box.set_alpha(.5)
 axs[0].set_xticks([1,2,3],[SCNAME[x] for x in SC]);axs[0].set_ylabel(ylabel);axs[1].set_xlabel(ylabel);axs[1].set_ylabel('Fração acumulada');axs[1].legend();
 for ax in axs:ax.grid(alpha=.2)
 fig.suptitle(ylabel+' — distribuição por execução na fase [150,270) s')
 save(fig,group,field+'_por_cenario',kind='boxplot e ECDF',question='Como as execuções variaram entre cenários?',sources='processed/infrastructure.csv ou http_phases.csv',period='[150,270) s',observation='Cada ponto é uma execução; 20 por cenário',limitation='Sem ajuste por diferenças de carga entre mecanismos')

def aggregate_figures():
 for field,label in [('cpu_mean','CPU Docker média (%)'),('mem_mean_mib','Memória média da vítima (MiB)'),('workers_two_fraction','Fração de tempo com 2 workers'),('waiting_mean','Operações aguardando (média)'),('waiting_max_exact','Máximo de operações aguardando')]:phase_distribution(field,I,'infraestrutura/distribuicoes',label)
 for field,label in [('duration_2xx_median_ms','Mediana HTTP 2xx legítima (ms)'),('timeout_cohort','Timeouts legítimos da coorte')]:phase_distribution(field,H[H['class']=='benign'],'infraestrutura/atendimento',label)
 for metric,label in [('cpu_mean','CPU média (%)'),('mem_mean_mib','Memória média (MiB)'),('waiting_mean','Operações aguardando (média)')]:
  fig,axs=plt.subplots(1,3,figsize=(13,4),sharey=True)
  for ax,sc in zip(axs,SC):
   x=I[I.scenario==sc].pivot(index='block',columns='phase',values=metric);ax.plot(x.index,x.PRE,c='#7b9cae',marker='o',ms=3,label='PRE');ax.plot(x.index,x.ACTIVE,c=C[sc],marker='s',ms=3,label='ACTIVE');ax.plot(x.index,x.POST,c='#677a57',marker='^',ms=3,label='POST');ax.set_title(SCNAME[sc]);ax.set_xlabel('Bloco pareado');ax.grid(alpha=.2)
  axs[0].set_ylabel(label);axs[-1].legend(fontsize=7);fig.suptitle(label+' — 20 blocos e três fases')
  save(fig,'pareamento',metric+'_blocos_fases',kind='trajetórias por bloco',question='Como a métrica variou por bloco e fase?',sources='infraestrutura processada',observation='Blocos definidos no plano, não por ordem de arquivo',limitation='PRE/ACTIVE/POST da mesma execução não são independentes')
 # Paired operational differences A3/F96 versus L2.
 for field,label in [('cpu_mean','CPU média (%)'),('mem_mean_mib','Memória média (MiB)'),('waiting_mean','Operações aguardando (média)')]:
  z=I[I.phase=='ACTIVE'].pivot(index='block',columns='scenario',values=field);fig,axs=plt.subplots(1,2,figsize=(10,4),sharey=True)
  for ax,sc in zip(axs,['A3','F96']):
   for b,row in z.iterrows():ax.plot([0,1],[row.L2,row[sc]],c='#999',alpha=.45,lw=.7)
   ax.scatter(np.zeros(len(z)),z.L2,c=C['L2'],s=16,label='L2');ax.scatter(np.ones(len(z)),z[sc],c=C[sc],s=16,label=sc);ax.set_xticks([0,1],['L2',sc]);ax.grid(alpha=.2);ax.set_title(f'{sc} vs L2')
  axs[0].set_ylabel(label);fig.suptitle(label+' — comparação por bloco pareado')
  save(fig,'pareamento',field+'_pareado',kind='pares por bloco',question='Como cada bloco mudou de L2 para a condição ofensiva?',sources='plan.json; infraestrutura processada',period='[150,270) s',observation='20 blocos pareados por contrato experimental',limitation='Diferença entre cenários inclui mecanismo, endpoint e carga')

def heat_metric(metric,sc,unit,group):
 x=P[P.scenario==sc].groupby(['method','feature'])[metric].mean().unstack('feature').reindex(index=M,columns=list(F)[:4]);fig,ax=plt.subplots(figsize=(10,4.5));z=x.to_numpy(dtype=float);im=ax.imshow(z,aspect='auto',cmap='viridis',vmin=0 if metric!='delay_s' else None)
 for (i,j),v in np.ndenumerate(z):ax.text(j,i,'—' if np.isnan(v) else f'{v:.2f}',ha='center',va='center',color='white' if np.isfinite(v) and v>(np.nanmin(z)+np.nanmax(z))/2 else 'black',fontsize=8)
 ax.set_yticks(range(4),M);ax.set_xticks(range(4),['Pacotes TCP','Bytes TCP','Inícios HTTP','Duração média'],rotation=15,ha='right',fontsize=8);fig.colorbar(im,ax=ax,label=unit);fig.suptitle(f'{SCNAME[sc]} — {unit} por detector e sinal')
 save(fig,group,sc+'_'+metric+'_heatmap',sc,kind='heatmap de desempenho',question='Como variou a métrica por detector e sinal?',sources='avaliações TEST oficiais',period='20 execuções TEST por cenário',observation='Média das execuções elegíveis; células sem definição são nulas',limitation='Latência somente entre eventos detectados; consultar detecção')

def performance_figures():
 for sc in SC:
  for metric,unit in ([('pre_fpr','FPR no controle legítimo')] if sc=='L2' else [('pre_fpr','FPR pré-ataque'),('post_positive_fraction','Fração positiva pós-ataque')]):heat_metric(metric,sc,unit,'desempenho')
  if sc!='L2':
   for metric,unit in [('event_detected','Detecção por evento'),('delay_s','Atraso observado (s)')]:heat_metric(metric,sc,unit,'desempenho')
 for sc in ['A3','F96']:
  fig,axs=plt.subplots(1,2,figsize=(12,4.5))
  x=P[P.scenario==sc]
  for i,m in enumerate(M):
   z=x[x.method==m];axs[0].scatter(z.pre_fpr,z.delay_s,c=C[sc],marker=['o','s','^','x'][i],alpha=.5,label=m)
  axs[0].set_xlabel('FPR PRE');axs[0].set_ylabel('Latência detectados (s)');axs[0].legend(fontsize=7);axs[0].grid(alpha=.2)
  by=x.groupby(['method','feature']).agg(detection=('event_detected','mean'),pre_fpr=('pre_fpr','mean')).reset_index()
  for i,m in enumerate(M):
   z=by[by.method==m];axs[1].scatter(z.pre_fpr,z.detection,c=C[sc],marker=['o','s','^','x'][i],s=45,label=m)
  axs[1].set_xlabel('FPR PRE médio');axs[1].set_ylabel('Detecção por evento');axs[1].grid(alpha=.2)
  fig.suptitle(f'{SCNAME[sc]} — compromissos observados em TEST')
  save(fig,'desempenho',sc+'_compromissos',sc,kind='dispersão',question='Como detecção, FPR e latência se combinam?',sources='evaluation manifests oficiais',observation='Latência omite não detectados; painel de detecção mostra proporção',limitation='Sem pontuação global ou ranking')
  for metric,label in [('delay_s','Latência observada (s)'),('pre_fpr','FPR PRE'),('post_positive_fraction','Fração positiva POST')]:
   fig,axs=plt.subplots(1,2,figsize=(12,4.5));vals=[];labs=[]
   for m in M:
    for f in list(F)[:4]:
     z=x[(x.method==m)&(x.feature==f)][metric].dropna();vals.append(z);labs.append(m+'\n'+f.replace('ingress_','')[:12]);ecdf(axs[1],z,m+' · '+f[:10],C[sc])
   axs[0].boxplot(vals,showfliers=False);axs[0].set_xticks(range(1,17),labs,rotation=65,fontsize=6);axs[0].set_ylabel(label);axs[0].grid(axis='y',alpha=.2);axs[1].set_xlabel(label);axs[1].set_ylabel('Fração acumulada');axs[1].grid(alpha=.2)
   fig.suptitle(f'{SCNAME[sc]} — {label} entre execuções TEST')
   save(fig,'desempenho',sc+'_'+metric+'_distribuicao',sc,kind='boxplot e ECDF',question='Como variou a métrica entre 20 repetições?',sources='evaluation manifests oficiais',observation='20 execuções por par quando a métrica é definida',limitation='Latência condicionada à detecção; FPR total ofensivo pode ser indefinido')
 # Distinguish misses from short delays.
 for sc in ['A3','F96']:
  x=P[P.scenario==sc];fig,ax=plt.subplots(figsize=(12,5));labels=[]
  for j,(m,f) in enumerate((m,f) for m in M for f in list(F)[:4]):
   z=x[(x.method==m)&(x.feature==f)].sort_values('block');color=[C[sc] if v is True else '#bbb' for v in z.event_detected];ax.scatter(z.block,np.full(len(z),j),c=color,s=20,marker='s');labels.append(m+' · '+f[:18])
  ax.set_yticks(range(16),labels,fontsize=7);ax.set_xlim(.5,20.5);ax.set_xticks(range(1,21));ax.set_xlabel('Bloco pareado');ax.grid(alpha=.15);ax.set_title(f'{SCNAME[sc]} — detecção (cor) e ausência (cinza) por bloco')
  save(fig,'desempenho',sc+'_deteccao_por_bloco',sc,kind='matriz de detecção',question='Quais blocos não foram detectados?',sources='evaluation manifests oficiais',observation='Cinza representa não detecção, nunca latência zero',limitation='Cada célula é uma execução')

def calibration_figures():
 for f in list(F)[:4]:
  row=CAL[(CAL.feature==f)&(CAL.stage=='calibration')].iloc[0];d=json.loads(row.thresholds);ps=json.loads(row.pair_status)
  fig,axs=plt.subplots(1,2,figsize=(11,4));axs[0].bar(M,[float(d[m]) for m in M],color=['#4d7084','#758a60','#b48059','#7f5894']);axs[0].set_ylabel('Limiar h (unidade do método)');axs[0].set_title('Valores selecionados — escalas não comparáveis')
  axs[1].bar(M,[float(ps[m]['mean_fpr']) if ps[m]['mean_fpr'] is not None else np.nan for m in M],color=['#4d7084','#758a60','#b48059','#7f5894']);axs[1].axhline(.01,c=C['threshold'],ls='--',label='Critério CAL_A (quando aplicável)');axs[1].set_ylabel('FPR médio CAL_A');axs[1].legend(fontsize=7)
  for ax in axs:ax.tick_params(axis='x',rotation=15);ax.grid(axis='y',alpha=.2)
  fig.suptitle(f'{f} — limiares congelados e suporte CAL_A')
  save(fig,'calibracao',f+'_limiares_CAL_A',feature=f,kind='calibração',question='Quais limiares foram selecionados antes de TEST?',sources='baseline/calibration/verification manifests oficiais',observation='Limiar de cada detector tem escala própria',limitation='Não comparar alturas entre métodos como desempenho')
  cand=json.loads(row.candidates)
  if cand:
   fig,ax=plt.subplots(figsize=(9,4.5));xs=[];ys=[];col=[]
   for z in cand:
    if z.get('h') is None:continue
    xs.append(float(z['h']));ys.append(float(np.mean([float(a['fpr']) for a in z.get('support',[]) if a.get('fpr') is not None])) if z.get('support') else np.nan);col.append('#27805b' if z.get('eligible') else '#b7464b')
   if xs:ax.scatter(xs,ys,c=col,s=18);ax.axvline(float(d['cusum-freeze']),c='#333',ls='--',label='h selecionado');ax.legend()
   ax.set_xlabel('h candidato CUSUM-freeze');ax.set_ylabel('FPR médio CAL_A');ax.grid(alpha=.2);ax.set_title(f'{f} — candidatos CUSUM-freeze')
   save(fig,'calibracao',f+'_candidatos_CUSUM',feature=f,method='cusum-freeze',kind='candidatos',question='Como variou a elegibilidade dos candidatos?',sources='calibration manifest oficial',observation='Verde elegível, vermelho inelegível segundo artefato',limitation='Sem uso dos dados TEST')
 # Baseline empirical signals: four runs.
 for f in list(F)[:4]:
  x=S[(S.partition=='BASELINE')&(S.feature==f)&(S.window_index>=30)&(S.window_index<390)];fig,axs=plt.subplots(1,2,figsize=(11,4))
  for eid,z in x.groupby('entry_id'):axs[0].plot(z.window_index,z.value,lw=.6,label=eid[-6:]);ecdf(axs[1],z.value,eid[-6:],'#547889')
  axs[0].set_xlabel('Tempo relativo (s)');axs[0].set_ylabel(F[f]);axs[0].grid(alpha=.2);axs[1].set_xlabel(F[f]);axs[1].set_ylabel('Fração acumulada');axs[1].grid(alpha=.2);fig.suptitle(f'{f} — quatro execuções BASELINE')
  save(fig,'calibracao',f+'_baseline',feature=f,kind='baseline temporal e ECDF',question='Qual era a distribuição de referência?',sources='features/timeseries das 4 BASELINE',observation='Referência independente de CAL_A, CAL_B e TEST',limitation='Amostras temporais correlacionadas')

def integrated_alarm():
 for sc in SC:
  e=REP[sc];sec=pd.read_csv(PR/f'seconds_{e}.csv');cpu=pd.read_csv(PR/f'docker_{e}.csv');mem=pd.read_csv(PR/f'memory_{e}.csv');htt=pd.read_csv(PR/f'http_{e}.csv');htt=htt[htt.traffic_class=='benign']
  for f in ['request_starts','mean_duration_ms']:
   for m in M:
    d=trace(e,f,m);fig,axs=plt.subplots(7,1,figsize=(11,15),sharex=True)
    axs[0].step(sec.t,sec.benign_http_started,c=C['benign'],where='post',label='Legítimo');axs[0].step(sec.t,sec.attack_http_started,c=C['attack'],where='post',label='Ofensivo');axs[0].legend(fontsize=7);label(axs[0],'Inícios HTTP/s')
    axs[1].scatter(cpu.t,cpu.cpu,s=5,c=C[sc]);label(axs[1],'CPU Docker (%)')
    axs[2].scatter(mem.t,mem.mem,s=8,c=C[sc]);label(axs[2],'Memória (MiB)')
    axs[3].step(sec.t,sec.waiting_mean,c=C[sc],where='post');label(axs[3],'Operações aguardando\n(média/s)')
    a=htt[htt.category=='http_2xx'];b=htt[htt.category=='timeout'];axs[4].scatter(a.elapsed_seconds,a.duration_ms,s=3,alpha=.2,c=C['benign'],label='2xx');
    if len(b):axs[4].scatter(b.elapsed_seconds,b.duration_ms,s=5,c=C['alarm'],marker='x',label='Timeout')
    axs[4].legend(fontsize=7);label(axs[4],'Duração HTTP\nlegítima (ms)')
    axs[5].plot(d.t,d.score,c='#2d6f9b',lw=.8);axs[5].axhline(d.threshold.dropna().iloc[0],c=C['threshold'],ls='--');label(axs[5],'Estatística / limiar')
    axs[6].step(d.t,d.decision.fillna(False).astype(int),c=C['alarm'],where='post');axs[6].set_yticks([0,1]);label(axs[6],'Alarme (0/1)')
    for ax in axs:decorate(ax,sc)
    fig.suptitle(f'{e} — infraestrutura, atendimento e {m} × {f}')
    save(fig,'infraestrutura_vs_alarmes',e+'_'+m+'_'+f+'_integrado',sc,m,f,e,'painel integrado',question='Como o alarme coincidiu com infraestrutura e atendimento?',sources='request_log; victim_stats; simulation_metrics; work; TEST manifest',observation='Alinhamento temporal descritivo com decisão oficial',limitation='Coincidência não demonstra causalidade')

def overall_figures():
 for sc in ['A3','F96']:
  x=P[P.scenario==sc];fig,axs=plt.subplots(1,3,figsize=(15,4))
  fields=[('event_detected','Detecção por evento'),('pre_fpr','FPR PRE'),('delay_s','Latência detectados (s)')]
  for ax,(field,labeltext) in zip(axs,fields):
   z=x.groupby('method')[field].mean().reindex(M);ax.bar(M,z,color=['#4d7084','#758a60','#b48059','#7f5894']);ax.set_title(labeltext);ax.tick_params(axis='x',rotation=18);ax.grid(axis='y',alpha=.2)
  fig.suptitle(f'{SCNAME[sc]} — visão geral TEST, quatro sinais elegíveis')
  save(fig,'comparacoes/gerais',sc+'_painel_geral',sc,kind='painel agregado',question='Como se distribuem detecção, FPR e latência?',sources='evaluation manifests oficiais',observation='Médias descritivas entre sinais e 20 execuções',limitation='Sinais não são repetições equivalentes; consultar matrizes detalhadas')
 # A3 vs F96 paired contrast for same detector-feature, preserving blocks.
 for m in M:
  for f in list(F)[:4]:
   x=P[(P.method==m)&(P.feature==f)&(P.scenario.isin(['A3','F96']))];z=x.pivot(index='block',columns='scenario',values='event_detected');fig,ax=plt.subplots(figsize=(7,4))
   for b,row in z.iterrows():ax.plot([0,1],[int(row.A3),int(row.F96)],c='#999',alpha=.5,lw=.7)
   ax.scatter(np.zeros(len(z)),z.A3.astype(int),c=C['A3'],s=14,label='A3');ax.scatter(np.ones(len(z)),z.F96.astype(int),c=C['F96'],s=14,label='F96');ax.set_xticks([0,1],['Assimetria','Flooding']);ax.set_yticks([0,1],['Não','Sim']);ax.set_ylabel('Evento detectado');ax.grid(alpha=.2);fig.suptitle(f'{m} × {f} — detecção nos 20 blocos pareados')
   save(fig,'pareamento/detectores',m+'_'+f+'_A3_F96',method=m,feature=f,kind='pares por bloco',question='Como a detecção diferiu nos cenários pareados?',sources='plan.json; evaluation manifests',observation='Pareamento por bloco científico, não por ordem temporal',limitation='Cenários diferem em mecanismo, endpoint e intensidade')

def selected_cases():
 rows=[]
 for sc in ['A3','F96']:
  for m in M:
   for f in list(F)[:4]:
    x=P[(P.scenario==sc)&(P.method==m)&(P.feature==f)]
    for cat,z in [('rápida',x[x.event_detected==True].sort_values(['delay_s','entry_id']).head(1)),('tardia',x[x.event_detected==True].sort_values(['delay_s','entry_id'],ascending=[False,True]).head(1)),('sem detecção',x[x.event_detected==False].sort_values('entry_id').head(1)),('falso alarme PRE',x[x.pre_positive_windows>0].sort_values(['pre_positive_windows','entry_id'],ascending=[False,True]).head(1))]:
     if len(z):rows.append({'scenario':sc,'method':m,'feature':f,'category':cat,'entry_id':z.iloc[0].entry_id,'block':z.iloc[0].block,'delay_s':z.iloc[0].delay_s,'pre_positive_windows':z.iloc[0].pre_positive_windows,'criterion':'extremo observado; desempate por entry_id'})
 pd.DataFrame(rows).to_csv(PR/'selected_cases.csv',index=False)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--all-traces',action='store_true',help='Adiciona C1/C2 para todos os pares das 60 execuções TEST');ap.add_argument('--section',choices=['all','infrastructure','signals','detectors','aggregate','freeze','confidence','availability','resources','calibrationmore'],default='all');a=ap.parse_args()
 if a.section!='all' and (OUT/'catalogo_figuras.csv').exists():CAT.extend(pd.read_csv(OUT/'catalogo_figuras.csv').fillna('').to_dict('records'))
 if a.section in ('all','infrastructure'):infrastructure_panels()
 if a.section in ('all','signals'):signal_panels()
 if a.section in ('all','detectors'):alarm_rasters();detailed_traces(a.all_traces);detector_matrices();integrated_alarm()
 if a.section in ('all','aggregate'):aggregate_figures();performance_figures();calibration_figures();overall_figures();additional_figures();freeze_details();confidence_figures();official_availability();resource_matrices();calibration_verification()
 if a.section=='freeze':freeze_details()
 if a.section=='confidence':confidence_figures()
 if a.section=='availability':official_availability()
 if a.section=='resources':resource_matrices()
 if a.section=='calibrationmore':calibration_verification()
 selected_cases()
 catalog=pd.DataFrame(CAT).drop_duplicates('path',keep='last');catalog.to_csv(OUT/'catalogo_figuras.csv',index=False)
 print('FIGURES',len(catalog),flush=True)
def additional_figures():
 # Alarm episode duration is not event detection count.
 episodes=[]
 for (e,f,m),z in D.groupby(['entry_id','feature','method']):
  z=z.sort_values('t');a=z.decision.fillna(False).to_numpy(dtype=bool);edges=np.diff(np.r_[False,a,False].astype(int));starts=np.where(edges==1)[0];ends=np.where(edges==-1)[0]
  for start,end in zip(starts,ends):episodes.append({'entry_id':e,'scenario':z.scenario.iloc[0],'feature':f,'method':m,'first_window_end_s':int(z.t.iloc[start]),'last_window_end_s':int(z.t.iloc[end-1]),'length_windows':int(end-start),'phase':'PRE' if z.t.iloc[start]<150 else 'ACTIVE' if z.t.iloc[start]<=270 else 'POST'})
 ep=pd.DataFrame(episodes);ep.to_csv(PR/'alarm_episodes.csv',index=False)
 for sc in SC:
  x=ep[ep.scenario==sc];fig,axs=plt.subplots(1,2,figsize=(12,4.5))
  vals=[x[x.method==m].length_windows for m in M];axs[0].boxplot(vals,showfliers=False);axs[0].set_xticks(range(1,5),M,rotation=15);axs[0].set_ylabel('Janelas consecutivas em alarme');axs[0].grid(alpha=.2)
  phase_counts=x.groupby(['method','phase']).size().unstack(fill_value=0).reindex(index=M,columns=['PRE','ACTIVE','POST'],fill_value=0);phase_counts.plot.bar(ax=axs[1],color=['#7fa3b7','#ba6b7a','#7a8f60']);axs[1].set_ylabel('Episódios (quantidade)');axs[1].tick_params(axis='x',rotation=15);axs[1].legend(fontsize=7);axs[1].grid(alpha=.2)
  fig.suptitle(f'{SCNAME[sc]} — persistência dos alarmes e episódios por fase')
  save(fig,'alarmes/episodios',sc+'_persistencia',sc,kind='episódios de alarme',question='Quanto duram sequências de janelas positivas?',sources='TEST manifests oficiais',observation='Episódios definidos por janelas consecutivas, separadas de detecção por evento',limitation='Uma sequência pode atravessar limite de fase; classificada pelo início')
 # Legitimate availability and nominal-versus-effective rates by scenario.
 z=H[(H['class']=='benign')&(H.phase=='ACTIVE')].copy();z['availability']=z.http_2xx_cohort/z.started;z['rps_started']=z.started/120
 fig,axs=plt.subplots(1,2,figsize=(12,4.5))
 for j,sc in enumerate(SC):
  a=z[z.scenario==sc];axs[0].scatter(np.full(len(a),j)+np.linspace(-.1,.1,len(a)),a.availability,c=C[sc],s=18,label=SCNAME[sc]);axs[1].scatter(np.full(len(a),j)+np.linspace(-.1,.1,len(a)),a.rps_started,c=C[sc],s=18)
 axs[0].set_ylabel('Fração de tentativas legítimas com HTTP 2xx');axs[1].set_ylabel('Inícios HTTP legítimos/s');axs[1].axhline(16,c=C['threshold'],ls='--',label='Nominal 16 RPS');axs[1].legend(fontsize=7)
 for ax in axs:ax.set_xticks(range(3),[SCNAME[x] for x in SC]);ax.grid(alpha=.2)
 fig.suptitle('Atendimento legítimo em [150,270) s — 20 execuções por cenário')
 save(fig,'infraestrutura/atendimento','disponibilidade_e_rps_legitimo',kind='pontos por execução',question='Como taxa iniciada e sucesso legítimo variaram?',sources='request_log primário; configuração efetiva',period='[150,270) s',observation='Disponibilidade HTTP observada, não disponibilidade integral do serviço',limitation='Desfechos atribuídos à coorte iniciada na fase')
 # Signal correlations, computed per execution within ACTIVE, then shown by scenario.
 f4=list(F)[:4];corr=[]
 for e in TEST.entry_id:
  x=S[(S.entry_id==e)&(S.feature.isin(f4))&(S.window_index>=150)&(S.window_index<270)].pivot(index='window_index',columns='feature',values='value');sc=TEST.loc[TEST.entry_id==e,'scenario'].iloc[0]
  for a in f4:
   for b in f4:corr.append({'entry_id':e,'scenario':sc,'signal_a':a,'signal_b':b,'correlation':x[a].corr(x[b])})
 co=pd.DataFrame(corr);co.to_csv(PR/'signal_correlations.csv',index=False)
 for sc in SC:
  x=co[co.scenario==sc].groupby(['signal_a','signal_b']).correlation.median().unstack().reindex(index=f4,columns=f4);fig,ax=plt.subplots(figsize=(7,5));im=ax.imshow(x,cmap='coolwarm',vmin=-1,vmax=1)
  ax.set_xticks(range(4),['Pacotes','Bytes','HTTP','Duração'],rotation=25);ax.set_yticks(range(4),['Pacotes','Bytes','HTTP','Duração'])
  for (i,j),v in np.ndenumerate(x.to_numpy()):ax.text(j,i,'—' if np.isnan(v) else f'{v:.2f}',ha='center',va='center',fontsize=8)
  fig.colorbar(im,ax=ax,label='Correlação de Pearson, mediana das execuções');fig.suptitle(f'{SCNAME[sc]} — relações entre sinais em [150,270) s')
  save(fig,'sinais/correlacoes',sc+'_correlacao_sinais',sc,kind='matriz de correlação',question='Quais sinais variaram juntos dentro das execuções?',sources='features/timeseries',period='[150,270) s',observation='Correlação calculada por execução, mediana entre 20',limitation='Correlação temporal não estabelece causalidade')

def freeze_details():
 for sc in SC:
  e=REP[sc]
  for f in list(F)[:4]:
   d=trace(e,f,'cusum-freeze');h=d.threshold.dropna().iloc[0];fig,axs=plt.subplots(4,1,figsize=(11,10),sharex=True)
   axs[0].plot(d.t,d.value,c=C[sc],lw=.8);label(axs[0],F[f])
   axs[1].plot(d.t,d.candidate,c='#2d6f9b',lw=.8,label='Candidato');axs[1].axhline(h,c=C['threshold'],ls='--',label='h');axs[1].legend(fontsize=7);label(axs[1],'Candidato CUSUM')
   axs[2].plot(d.t,d.posterior_state,c='#9163a1',lw=.9,label='Estado após decisão');axs[2].axhline(h,c=C['threshold'],ls='--',label='h');axs[2].set_ylim(-.05*h,1.15*h);axs[2].legend(fontsize=7);label(axs[2],'Estado preservado')
   axs[3].step(d.t,d.decision.fillna(False).astype(int),c=C['alarm'],where='post');axs[3].set_yticks([0,1]);label(axs[3],'Alarme (0/1)')
   for ax in axs:decorate(ax,sc)
   fig.suptitle(f'{e} — CUSUM-freeze: candidato, estado aceito e alarme | {f}')
   save(fig,'detectores/cusum-freeze',e+'_'+f+'_freeze_estado',sc,'cusum-freeze',f,e,'detalhe de congelamento',question='O que ocorre com o estado após cruzar h?',sources='TEST manifest: candidate, posterior_state, decision',observation='Estado mantém o valor anterior quando candidato > h',limitation='Candidato e estado usam escalas verticais separadas, identificadas')

def confidence_figures():
 official=json.loads((PR/'official_summary.json').read_text())['results']
 for sc in ['A3','F96']:
  for kind in ['detection','delay','pre_fpr']:
   fig,ax=plt.subplots(figsize=(9,7));labels=[]
   for i,(m,f) in enumerate((m,f) for m in M for f in list(F)[:4]):
    d=official[f'{f}/{sc}/{m}'];obj=d['detection'] if kind=='detection' else d['delay'] if kind=='delay' else d['means']['pre_fpr']
    val=obj.get('estimate',obj.get('mean_seconds'));interval=obj.get('interval');labels.append(m+' · '+f[:18])
    if val is None or interval is None:continue
    ax.errorbar(float(val),i,xerr=[[max(0,float(val)-float(interval[0]))],[max(0,float(interval[1])-float(val))]],fmt='o',c=C[sc],capsize=2,ms=3)
   ax.set_yticks(range(16),labels,fontsize=7);ax.grid(axis='x',alpha=.2);ax.set_xlabel({'detection':'Detecção por evento','delay':'Latência média entre detectados (s)','pre_fpr':'FPR PRE médio'}[kind]);ax.set_title(f'{SCNAME[sc]} — estimativas e IC oficiais de 95% ({kind})')
   save(fig,'desempenho/intervalos',sc+'_'+kind+'_IC_oficial',sc,kind='intervalos oficiais',question='Qual é a incerteza entre blocos?',sources='analysis/summary/manifest.json',period='20 blocos TEST',observation='Intervalos oficiais; unidade amostral = bloco/execução',limitation='Latência condicionada à detecção; IC não estimado de janelas temporais')

def official_availability():
 camp=ROOT/'experiment_results/scientific-energy-powersaver-20261109';rows=[]
 for r in TEST.itertuples():
  p=camp/'analysis/request_starts/evaluation'/r.entry_id/'manifest.json';d=json.loads(p.read_text());v=d['operational']['phases']['ACTIVE']
  rows.append({'entry_id':r.entry_id,'scenario':r.scenario,'block':r.block,'success_fraction':float(v['success_fraction']),'starts':v['starts'],'timely_2xx':v['timely_2xx'],'availability_basis':v['availability_basis']})
 x=pd.DataFrame(rows);x.to_csv(PR/'official_availability.csv',index=False)
 fig,axs=plt.subplots(1,2,figsize=(12,4.5))
 for j,sc in enumerate(SC):
  z=x[x.scenario==sc];axs[0].scatter(np.full(len(z),j)+np.linspace(-.1,.1,len(z)),z.success_fraction,c=C[sc],s=18,label=SCNAME[sc]);axs[1].scatter(z.block,z.success_fraction,c=C[sc],s=18,label=SCNAME[sc])
 axs[0].set_xticks(range(3),[SCNAME[z] for z in SC]);axs[0].set_ylabel('Fração de sucesso ACTIVE (operacional)');axs[1].set_xlabel('Bloco pareado');axs[1].set_ylabel('Fração de sucesso ACTIVE');axs[1].legend(fontsize=7)
 for ax in axs:ax.grid(alpha=.2)
 fig.suptitle('Disponibilidade operacional observada — definição oficial do pipeline')
 save(fig,'desempenho','disponibilidade_operacional',kind='pontos por execução',question='Como variou o sucesso legítimo operacional?',sources='evaluation.operational.phases.ACTIVE.success_fraction',period='[150,270) s',observation='Métrica oficial baseada nos journals reconciliados',limitation='Disponibilidade HTTP operacional; não disponibilidade universal do serviço')
 y=P[P.scenario.isin(['A3','F96'])].groupby('entry_id').event_detected.mean().rename('detected_pairs_fraction');z=x.merge(y,left_on='entry_id',right_index=True);fig,ax=plt.subplots(figsize=(8,5))
 for sc in ['A3','F96']:
  a=z[z.scenario==sc];ax.scatter(a.success_fraction,a.detected_pairs_fraction,c=C[sc],label=SCNAME[sc],s=25)
 ax.set_xlabel('Fração de sucesso ACTIVE (operacional)');ax.set_ylabel('Fração de 16 pares que detectaram');ax.legend();ax.grid(alpha=.2);fig.suptitle('Disponibilidade operacional e detecção — execuções ofensivas')
 save(fig,'desempenho','disponibilidade_vs_deteccao',kind='dispersão',question='Como sucesso legítimo e detecção coexistiram?',sources='evaluation.operational e evaluation.results',period='[150,270) s',observation='Cada ponto é uma execução; 16 pares por execução',limitation='Não inferir causalidade nem atribuir cada par a um evento independente')

def resource_matrices():
 for metric,labeltext in [('cpu','CPU Docker (%)'),('mem','Memória da vítima (MiB)')]:
  for shared in [True,False]:
   fig,axs=plt.subplots(3,1,figsize=(11,9),sharex=True,sharey=shared)
   for ax,sc in zip(axs,SC):
    for e in ids(sc):
     p=PR/f'{"docker" if metric=="cpu" else "memory"}_{e}.csv';z=pd.read_csv(p);ax.scatter(z.t,z[metric],s=2,alpha=.13,c=C[sc])
    decorate(ax,sc);label(ax,labeltext);ax.set_title(SCNAME[sc]+' — 20 execuções')
   fig.suptitle(labeltext+' — séries reais por cenário | '+('escala comum' if shared else 'escala individual'))
   save(fig,'infraestrutura/matrizes',metric+('_escala_comum' if shared else '_escala_individual'),kind='matriz temporal',question='Como CPU e memória variaram entre repetições?',sources='victim_stats ou simulation_metrics',observation='Amostras reais; 20 execuções por cenário',limitation='Sobreposição de pontos não implica medidas contínuas')

def calibration_verification():
 features=list(F)[:4];fig,axs=plt.subplots(1,2,figsize=(13,5),sharey=True,constrained_layout=True)
 for ax,stage in zip(axs,['calibration','verification']):
  mat=np.zeros((4,4));elig=np.zeros((4,4),dtype=bool)
  for i,f in enumerate(features):
   d=json.loads(CAL[(CAL.feature==f)&(CAL.stage==stage)].iloc[0].pair_status)
   for j,m in enumerate(M):mat[i,j]=float(d[m]['mean_fpr']) if d[m]['mean_fpr'] is not None else np.nan;elig[i,j]=bool(d[m]['eligible'])
  im=ax.imshow(mat,cmap='Blues',aspect='auto',vmin=0,vmax=max(.05,float(np.nanmax(mat))));ax.set_xticks(range(4),M,rotation=20);ax.set_yticks(range(4),['Pacotes TCP','Bytes TCP','Inícios HTTP','Duração média'])
  for (i,j),v in np.ndenumerate(mat):ax.text(j,i,f'{v:.3f}\n'+('✓' if elig[i,j] else '×'),ha='center',va='center',fontsize=8,color='black')
  ax.set_title('CAL_A: seleção' if stage=='calibration' else 'CAL_B: verificação')
 fig.colorbar(im,ax=axs,label='FPR médio nos 8 controles',orientation='horizontal',shrink=.6,pad=.14);fig.suptitle('Calibração — FPR e elegibilidade dos 16 pares')
 save(fig,'calibracao','CAL_A_CAL_B_elegibilidade',kind='heatmap de calibração',question='Quais pares atenderam aos critérios antes de TEST?',sources='calibration/verification manifests oficiais',observation='Valores e elegibilidade oficiais de cada etapa, sem TEST',limitation='Critérios de CAL_A e CAL_B não são intercambiáveis')

if __name__=='__main__':main()
