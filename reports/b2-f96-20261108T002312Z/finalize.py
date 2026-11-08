"""B2-F96 report and figures from exported data only. No infrastructure actions."""
import pathlib,json,csv,collections,hashlib,sys,datetime
P=pathlib.Path(__file__).resolve().parent;ROOT=P.parents[1];sys.path.insert(0,str(ROOT))
from experiments.exploratory_analysis import describe
S=json.loads((P/'summary.json').read_text());RUN=ROOT/'experiment_results'/P.name
def dump(name,x):(P/name).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def rows(name):return list(csv.DictReader((P/name).open()))
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
H=S['http_rows'];C=S['computation'];W=S['workers'];R=S['resources'];Q=S['queue_peaks']
http=rows('http_attempts.csv');ops=rows('operations.csv');qr=rows('queue_transitions.csv');ten=rows('temporal_10s.csv')
base=json.loads((ROOT/'reports/b2-l-20261107T232559Z/summary.json').read_text())
origin=json.loads((RUN/'raw/diagnostics/metadata.json').read_text())['origin_monotonic']
status=json.loads((RUN/'raw/run_status.json').read_text())
events=[json.loads(l) for l in (RUN/'raw/diagnostics/victim/events.jsonl').read_text().splitlines()]
writer=json.loads((RUN/'raw/diagnostics/victim/events.summary.json').read_text())
close=[e for e in events if e['kind']=='computation_observation_closed']
assert len(close)==1 and writer['complete'] and writer['dropped']==writer['write_errors']==0
assert all(e['at']-origin<0 for e in events if e.get('operation_id') in {o['operation_id'] for o in S['audit_operations']})
lastoff=S['residual']['last_offensive_completion']
firstzero=next(float(q['seconds']) for q in qr if float(q['seconds'])>=60 and int(q['total_pending'])==0)
timeouts=[x for x in http if x['traffic_class']=='benign' and 'Timeout' in x['error_type']]
recovery=dict(last_offensive_completion_seconds=lastoff,first_total_pending_zero_after_60=firstzero,
 last_legitimate_timeout_start=max((float(x['elapsed_seconds']) for x in timeouts),default=None),last_legitimate_timeout_end=max((float(x['end_elapsed_seconds']) for x in timeouts),default=None))
def cohort_metrics(a,b):
 rr=[x for x in http if x['traffic_class']=='benign' and a<=float(x['elapsed_seconds'])<b]
 oo=[o for o in ops if o['traffic_class']=='benign' and o['http_start'] and a<=float(o['http_start'])<b]
 d=describe(float(x['duration_ms']) for x in rr);w=describe(float(o['wait_ms']) for o in oo)
 return dict(interval=[a,b],starts=len(rr),rps=len(rr)/(b-a),success=sum(200<=int(x['http_status'])<300 for x in rr if x['http_status']),timeouts=sum('Timeout' in x['error_type'] for x in rr),http_ms=d,wait_ms=w,cpu_mean_ms=describe(float(o['cpu_ms']) for o in oo)['mean'])
recovery['late_P3_100_150']=cohort_metrics(100,150);dump('recovery.json',recovery)
peaktimes={}
for cls in ('benign','attack','total'):
 peaktimes[cls]={}
 for key in ('waiting','running','pending'):
  peak=max(int(q[cls+'_'+key]) for q in qr if 0<=float(q['seconds'])<150)
  peaktimes[cls][key]=dict(count=peak,first_seconds=next(float(q['seconds']) for q in qr if 0<=float(q['seconds'])<150 and int(q[cls+'_'+key])==peak))
dump('queue_peak_times.json',peaktimes)
eventcounts=[]
for name,a,b in [('P1',0,30),('P2',30,60),('P3',60,150)]:
 for cls in ('benign','attack','unknown'):
  own=[e for e in events if e.get('traffic_class')==cls and a<=e['at']-origin<b]
  eventcounts.append(dict(period=name,traffic_class=cls,**{kind:sum(e['kind']==kind for e in own) for kind in ('work_submitted','work_started','work_completed','work_failed')}))
dump('computational_events_by_actual_time.json',eventcounts)
initial=json.loads((P/'initial_environment.json').read_text());final=json.loads((P/'final_environment.json').read_text())
before=[json.loads(l) for l in initial['containers']['stdout'].splitlines() if l];after=[json.loads(l) for l in final['containers']['stdout'].splitlines() if l];networks=json.loads(final['networks']['stdout'])
assert {x['ID'] for x in before}=={x['ID'] for x in after}
assert all(x['State']!='running' for x in after) and all(not n['Containers'] for n in networks)
dump('cleanup_verification.json',dict(experimental_containers_remaining=0,external_containers_preserved=len(after),networks_empty=True,certificate_cleanup_verified=S['certificate']['cleanup_verified']))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
benign=[x for x in ten if x['traffic_class']=='benign'];attack=[x for x in ten if x['traffic_class']=='attack']
x=[float(v['start'])+5 for v in benign]
fig,ax=plt.subplots(4,1,figsize=(12,12),sharex=True)
ax[0].plot(x,[float(v['realized_rps']) for v in benign],marker='o',label='Legítimo iniciado')
ax[0].plot(x,[float(v['realized_rps']) for v in attack],marker='o',label='Ofensivo iniciado');ax[0].axhline(16,color='gray',ls='--');ax[0].set_ylabel('HTTP/s');ax[0].legend()
for key,label in [('mean_ms','Média, encerramentos'),('p95_ms','p95, encerramentos')]:ax[1].plot(x,[float(v[key]) for v in benign],marker='o',label=label)
ax[1].axhline(base['b2_periods']['Total']['duration_ms']['p95'],color='gray',ls='--',label='B2-L p95');ax[1].set_ylabel('HTTP legítimo (ms)');ax[1].legend()
ax[2].plot(x,[100*float(v['availability']) for v in benign],marker='o');ax[2].set_ylabel('Sucesso / inícios (%)');ax[2].set_ylim(-5,105)
qq=[q for q in qr if 0<=float(q['seconds'])<150]
for cls,label in [('benign','Legítimas'),('attack','Ofensivas'),('total','Total')]:ax[3].step([0]+[float(v['seconds']) for v in qq],[0]+[int(v[cls+'_pending']) for v in qq],where='post',label=label)
ax[3].set_ylabel('Operações pendentes');ax[3].set_xlabel('Segundos desde a origem experimental');ax[3].legend()
for a in ax:
 a.axvspan(30,60,color='red',alpha=.08);a.axvline(60,color='gray',ls=':');a.axvline(lastoff,color='purple',ls=':',alpha=.6);a.grid(alpha=.2);a.set_xlim(0,150)
fig.suptitle('B2-F96 — emissão ofensiva [30,60); linha roxa: última conclusão ofensiva')
fig.tight_layout();fig.savefig(P/'temporal.png',dpi=150);fig.savefig(P/'temporal.svg');plt.close(fig)
fig,ax=plt.subplots(2,1,figsize=(12,7),sharex=True)
for cls,label in [('benign','Legítimas'),('attack','Ofensivas'),('total','Total')]:
 ax[0].step([0]+[float(v['seconds']) for v in qq],[0]+[int(v[cls+'_waiting']) for v in qq],where='post',label=label)
 ax[1].step([0]+[float(v['seconds']) for v in qq],[0]+[int(v[cls+'_running']) for v in qq],where='post',label=label)
ax[0].set_ylabel('Aguardando');ax[1].set_ylabel('Executando');ax[1].set_xlabel('Segundos');ax[1].set_ylim(-.1,2.3)
for a in ax:a.axvspan(30,60,color='red',alpha=.08);a.axvline(lastoff,color='purple',ls=':');a.legend();a.grid(alpha=.2);a.set_xlim(0,150)
fig.tight_layout();fig.savefig(P/'queues.png',dpi=150);fig.savefig(P/'queues.svg');plt.close(fig)

def f(v,n=2):return 'N/D' if v is None or v=='' else f'{float(v):.{n}f}'
def tab(headers,rr):return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(str(v) for v in row)+' |' for row in rr])
def get_h(s,cls,period):return next(v for v in s['http_rows'] if v['traffic_class']==cls and v['period']==period)
def get_c(s,cls,period):return next(v for v in s['computation'] if v['traffic_class']==cls and v['period']==period)
previous=json.loads((ROOT/'reports/b2-f-20261108T000313Z/summary.json').read_text())
oldrec=json.loads((ROOT/'reports/b2-f-20261108T000313Z/recovery.json').read_text())
oldoff=get_h(previous,'attack','Total');off=get_h(S,'attack','Total')
oldp2=get_h(previous,'benign','P2');newp2=get_h(S,'benign','P2')
gain=100*(off['realized_rps']/oldoff['realized_rps']-1)
def peak(s):return next(q['pending'] for q in s['queue_peaks'] if q['period']=='Total' and q['traffic_class']=='total')
def pend60(s):return s['residual']['boundaries']['60']['before']['counts']['attack']['pending']
comparison=[
 ('RPS ofensivo nominal',64,64),('Posições ofensivas agregadas',64,96),('Posições por fonte',32,48),
 ('RPS ofensivo iniciado',oldoff['realized_rps'],off['realized_rps']),('Inícios HTTP ofensivos',oldoff['starts'],off['starts']),
 ('Admissões ofensivas',oldoff['admissions'],off['admissions']),('Submissões ofensivas',oldoff['submissions'],off['submissions']),
 ('Expirações pré-HTTP',oldoff['expired_before_http'],off['expired_before_http']),('Respostas ofensivas',oldoff['responses'],off['responses']),
 ('Timeouts ofensivos',oldoff['timeouts'],off['timeouts']),('Disponibilidade legítima P2 %',100*oldp2['availability'],100*newp2['availability']),
 ('Sucessos legítimos P2',oldp2['success'],newp2['success']),('Inícios legítimos P2',oldp2['starts'],newp2['starts']),
 ('Timeouts legítimos P2',oldp2['timeouts'],newp2['timeouts']),('RPS legítimo iniciado P2',oldp2['realized_rps'],newp2['realized_rps']),
 ('HTTP legítimo P2 médio ms',oldp2['mean_ms'],newp2['mean_ms']),('HTTP legítimo P2 p95 ms',oldp2['p95_ms'],newp2['p95_ms']),
 ('Espera legítima P2 média ms',get_c(previous,'benign','P2')['wait_mean_ms'],get_c(S,'benign','P2')['wait_mean_ms']),
 ('Pico agregado de operações pendentes',peak(previous),peak(S)),('Ofensivas pendentes em 60−',pend60(previous),pend60(S)),
 ('Última conclusão ofensiva s',previous['residual']['last_offensive_completion'],lastoff),('Residual ofensivo após 60 s',previous['residual']['seconds_after_60'],lastoff-60),
 ('Primeiro total zero após 60 s',oldrec['first_total_pending_zero_after_60'],firstzero)]
dump('comparison_f64_f96.json',[dict(indicator=k,F64=a,F96=b,difference=b-a) for k,a,b in comparison])
def combined_dispatch(s):
 groups=[g for g in s['generator_behavior'] if g['traffic_class']=='attack']
 return sum(g['dispatch_ms']['sum'] for g in groups)/sum(g['dispatch_ms']['n'] for g in groups)
report=[]
def p(t=''):report.append(t)
p('# B2-F96 — comparação exploratória de concorrência ofensiva 64 × 96')
p()
p('## Configuração e certificação')
p()
p(f"Uma única execução: run `{S['run_id']}`, checkout `{initial['head']['stdout'].strip()}`, branch refactor/project-organization, working tree inicialmente limpo. Dataset `{S['dataset']}`. Returncode 0; certificado `{S['certificate']['certification']}`, outcome `{S['certificate']['outcome']}`; dataset válido/elegível, limpeza verificada. Manifesto SHA256 `{S['manifest_sha256']}`. Não houve repetição, build/pull ou alteração de código/instrumentação.")
p()
p('A configuração partiu de experiment_results/b2-f-20261108T000313Z/raw/effective_config.json, não do template. Comparação integral confirmou somente novo ID e attack.max_concurrent_sends 64→96 (32→48 por fonte). Foram preservados attack.rate=32, duas fontes ofensivas, 64 RPS agregados /medium em [30,60); L2=2×8 RPS /medium em [0,150); timeout 2 s; pool vítima dois workers; topologia direta; sem autoscaling/NGINX/balanceamento; seed, kernel, instrumentação e política exploratory-offensive-v1. configuration.json e execution_procedure.py preservam a cópia e a comparação.')
p()
p('Imagens imutáveis iguais à B2-F e aceitas pelo preflight: vítima `sha256:03a186aa90eec03b874c82a887b245e7190fa45cd7256af3c077cb64943d52b0`; fontes `sha256:b94212edd4d31c34998aea870caebc4ba145c1593d1b8dfdc27fe4917719fe3e`. Docker Engine 29.9.3, Python host 3.12.3. Auditoria: cerca de 10,4 GB RAM disponível, 37,3 GB de disco, nenhum contêiner ativo. Limites operacionais preservados: host RAM mínima 2 GiB, disco 4 GiB, memória observada vítima 1 GiB/fonte 512 MiB, artefatos 512 MiB, frescor 5 s, timeout Docker 3 s e global 240 s. São salvaguardas existentes, não quotas novas. Detalhes completos em initial_environment.json e no certificado.')
p()
p('## Comparação direta')
p()
p(tab(['Indicador','B2-F / orçamento 64','B2-F96 / orçamento 96'],[[k,f(a,3),f(b,3)] for k,a,b in comparison]))
p()
p(f"A mudança observada na taxa ofensiva iniciada foi {off['realized_rps']-oldoff['realized_rps']:+.3f} RPS ({gain:+.2f}%), ou {off['starts']-oldoff['starts']:+d} inícios dentro de [30,60). Expirações pré-HTTP: {oldoff['expired_before_http']}→{off['expired_before_http']}. Não se usa nominal×30 como contagem de planos registrados. Admissões = submissões = inícios HTTP + expirações foi verificado por fonte. Expiração ocorre antes do HTTP e não é falha de atendimento da vítima.")
p()
p('## Emissão, despacho e concorrência utilizada')
p()
p(tab(['Execução','Fonte ofensiva','Admissões/submissões','Inícios','Expirações','Pico tarefas não iniciadas','Despacho médio / p95 / máximo ms'],[[label,g['source_id'],str(g['admissions'])+'/'+str(g['submitted']),g['http_started'],g['expired_before_http'],g['peak_submitted_not_started'],' / '.join(f(g['dispatch_ms'][k]) for k in ('mean','p95','maximum'))] for label,s in [('64',previous),('96',S)] for g in s['generator_behavior'] if g['traffic_class']=='attack']))
p()
p(f"Despacho médio ofensivo agregado ponderado pelas tarefas: {combined_dispatch(previous):.2f}→{combined_dispatch(S):.2f} ms. A diferença submetidas−iniciadas é observada, não acesso à fila interna do executor; despacho inclui tarefas posteriormente expiradas. Os planos registrados e as tarefas sem HTTP estão preservados em emission_reconciliation.json. Admissão legítima não é medida independentemente (N/D).")
p()
p(tab(['Execução','Fonte ofensiva','Posições configuradas','Pico tarefas executando','Pico HTTP em voo','Ocupação HTTP média P2'],[[v['execution'],v['source_id'],v['configured_positions'],v['task_occupancy']['peak_in_attack_window'],v['http_occupancy']['peak_in_attack_window'],f(v['http_occupancy']['time_mean_in_attack_window'])] for v in S['concurrency_observed'] if v['traffic_class']=='attack']))
p()
p('A concorrência efetiva foi reconstruída offline pelos pares task_started/task_finished e http_started/http_finished dos diagnósticos existentes, em [30,60). Ocupação média usa os tempos reais dos eventos, integrados nessa janela; ela não interpola CPU. Pico de cada fonte pode ocorrer em instantes distintos, portanto não se somam picos como se fossem um pico agregado medido. Tarefa executando inclui trabalho local antes/depois do HTTP. Aumentar o orçamento não comprova ausência de outras limitações de emissão ou da vítima.')
p()
p('## Atendimento legítimo e processamento computacional')
p()
p(tab(['Execução/coorte','RPS legítimo','Sucessos/inícios','Timeouts','HTTP média / mediana / p95 ms','Espera média ms','CPU/op média ms'],[[label+' '+period,f(get_h(s,'benign',period)['realized_rps'],3),str(get_h(s,'benign',period)['success'])+'/'+str(get_h(s,'benign',period)['starts']),get_h(s,'benign',period)['timeouts'],' / '.join(f(get_h(s,'benign',period)[k]) for k in ('mean_ms','median_ms','p95_ms')),f(get_c(s,'benign',period)['wait_mean_ms']),f(get_c(s,'benign',period)['cpu_mean_ms'])] for label,s in [('64',previous),('96',S)] for period in ('P1','P2','P3')]))
p()
p('Disponibilidade é sucessos/inícios HTTP, separada do RPS iniciado. Coortes P1=[0,30), P2=[30,60), P3=[60,150) pelo início HTTP, preservando conclusões reais posteriores e tentativas após 150 s como tail. Encerramentos incluem timeouts; distribuições somente de respostas e denominadores estão em http_by_period.csv/summary.json, sem imputação. Ambas as classes usam /medium e são classificadas pelas identidades das fontes e correlação de IDs, não pelo endpoint.')
p()
p('Dois inícios legítimos tardios, em 150,002832396 s e 150,008035999 s, receberam HTTP 200 e permanecem na coorte tail, fora dos totais [0,150). Por isso as fontes registram 2.385 submissões/inícios legítimos completos, enquanto a janela nominal contém 2.383. Os IDs e tempos reais de conclusão estão preservados em summary.json/tail_http e http_attempts.csv.')
p()
p(tab(['Execução/classe','Subm./inic./concl./falha','CPU/op ms','Parede/op ms','Espera média / mediana / p95 ms'],[[label+' '+cls,' / '.join(str(get_c(s,cls,'Total')[k]) for k in ('submitted','started','completed','failed')),f(get_c(s,cls,'Total')['cpu_mean_ms']),f(get_c(s,cls,'Total')['wall_mean_ms']),' / '.join(f(get_c(s,cls,'Total')[k]) for k in ('wait_mean_ms','wait_median_ms','wait_p95_ms'))] for label,s in [('64',previous),('96',S)] for cls in ('benign','attack')]))
p()
p('Espera computacional inclui fila, IPC e agendamento. Operações concluídas após timeout continuam sendo trabalho executado e não uma resposta HTTP recebida. Distribuição entre workers e seus tempos está em workers_by_period.csv. Comparar CPU/op de P1 ajuda a contextualizar diferenças entre execuções; mesmas imagens não tornam o custo computacional ou o host determinísticos. Não foi aberta investigação adicional.')
p()
p('## Filas, residual e recuperação')
p()
p(f"B2-F96: em 60− s havia {pend60(S)} operações ofensivas e {S['residual']['boundaries']['60']['before']['counts']['benign']['pending']} legítimas pendentes. Última conclusão ofensiva em {lastoff:.6f} s, {lastoff-60:.6f} s após emissão; primeiro total pendente zero após 60 s em {firstzero:.6f} s. Último início/encerramento legítimo com timeout: {f(recovery['last_legitimate_timeout_start'],6)} / {f(recovery['last_legitimate_timeout_end'],6)} s (N/D=nenhum). Snapshots antes/depois de 60 s e conclusões reais estão em queue_residual.json; todas as transições e picos foram preservados.")
p()
p('Fim da emissão, fim do processamento ofensivo, recuperação do atendimento e fila total vazia são marcos distintos. As filas são observadas por eventos completos, sem inferi-las só da CPU. A recuperação é avaliada pelos bins HTTP e pela redução da espera, sem impor como requisito que apareçam timeouts. Não se afirma um instante exato de recuperação sem critério científico previamente definido.')
p()
p(tab(['Coorte B2-F96','RPS legítimo','Sucessos/inícios','HTTP média / p95 ms','Espera média ms'],[[v['period'],f(v['realized_rps'],3),v['success']+'/'+v['starts'],f(v['mean_ms'])+' / '+f(v['p95_ms']),f(v['wait_mean_ms'])] for v in benign]))
p()
late=recovery['late_P3_100_150']
p(f"Na coorte final [100,150), {late['success']}/{late['starts']} respostas bem-sucedidas, HTTP médio {late['http_ms']['mean']:.2f} ms, p95 {late['http_ms']['p95']:.2f} ms, espera média {late['wait_ms']['mean']:.2f} ms. B2-F original nessa mesma coorte: 782/782, 45,32 ms de média, 78,32 ms de p95. São comparações descritivas, não demonstração de estabilidade populacional.")
p()
p('![Evolução HTTP e de operações pendentes](temporal.png)')
p()
p('## Integridade e limitações')
p()
cap=status['capture_results']
p(f"Dataset válido/elegível e hashes verificados; certificado vinculado ao manifesto; raw/export comparados sem divergências. Capturas aceitas PCAP/CSV: {cap['pcap']['capture_counters']['packets_captured']}/{cap['csv']['capture_counters']['packets_captured']} pacotes, descartes pelo kernel {cap['pcap']['capture_counters']['packets_dropped_by_kernel']}/{cap['csv']['capture_counters']['packets_dropped_by_kernel']}. Vítima: {writer['written']} eventos íntegros, perdas/erros {writer['dropped']}/{writer['write_errors']}. Quatro fontes com sequência, journals, fechamento e identidades reconciliados; {S['integrity']['correlated_requests']} inícios correlacionados a operações, conflitos {len(S['integrity']['conflicts'])}, ciclos parciais {len(S['integrity']['partial_lifecycles'])}. Operações unknown de auditoria: {len(S['audit_operations'])}, separadas e não convertidas artificialmente em legítimas/ofensivas. Inícios HTTP fora de [0,150): {len(S['tail_http'])}; detalhes em summary.json. Nenhum início ofensivo fora da janela, verificado pelo analisador.")
p()
p(tab(['Período','Ticks CPU','CPU média/máx % Docker','Memória máx MiB','Gap mediano/máx s'],[[v['period'],v['samples'],f(v['cpu_mean'])+'/'+f(v['cpu_max']),f(v['mem_max_mib']),f(v['gap_median'],3)+'/'+f(v['gap_max'],3)] for v in R]))
p()
p('CPU permanece esparsa: médias de amostras, sem interpolação ou alteração de cadência, não médias contínuas. Gaps e cobertura em resources_by_period.csv/existing_analyzer/summary.json. Duas realizações sequenciais com mesma semente não isolam causalmente a mudança de orçamento; custo por operação e condições do host podem variar. Nenhum teste inferencial, intervalo de confiança ou alegação de gargalo único. O certificado operacional não substitui os critérios de latência/recuperação do protocolo. Limpeza verificada: nenhum contêiner experimental remanescente, redes preexistentes vazias e quatro contêineres externos preservados, sem limpeza ampla.')
p()
p('## Conclusão e decisão')
p()
p('**Recomendação A — manter F2 com orçamento 64 no protocolo.** Nesta comparação, 96 não cumpriu o objetivo de entregar mais inícios e reduzir descartes: 54,067→49,867 RPS (−7,77%; −126 inícios) e 191→308 expirações (+117; +61,26%). A ocupação extra foi real (pico 48/48 por fonte, médias HTTP 44,45/44,94), mas traduziu-se em mais trabalho em voo e espera, não em maior vazão.')
p()
p('A degradação adicional foi relevante: disponibilidade legítima P2 de 100%→19,07% (98/514; 416 timeouts), HTTP médio 1.102,37→1.882,85 ms, espera computacional média 1.060,51→2.521,78 ms; pico total pendente 95→241 e ofensivas pendentes em 60− de 61→166. O residual ofensivo aumentou de 1,199 para 3,699 s. Maior dano não é, isoladamente, o benefício de emissão que motivou o teste; timeouts não eram requisito de sucesso.')
p()
p('O cenário foi operacionalmente aceitável e íntegro, mas não há benefício observado que justifique alterar o protocolo para 96. Isso não demonstra que aumentar concorrência sempre reduz vazão: P1 já tinha CPU/op média de 32,04 ms contra 29,02 ms, e em P2 a CPU/op ofensiva foi 33,08 contra 28,87 ms na B2-F original. As condições não foram isoladas causalmente. A decisão conserva a configuração já caracterizada diante de uma realização adicional sem melhora de entrega, evitando custo de revisão do protocolo sem suporte empírico favorável.')
p()
p('Depois desta única execução adicional, recomenda-se encerrar B2 e consolidar o protocolo científico, registrando orçamento escolhido, carga nominal/efetiva, expirações, critérios de recuperação, custo por operação e pendência da observabilidade CPU. Não executar outros orçamentos, F3, novas investigações ou a campanha definitiva nesta atividade.')
p()
p('Configuração efetiva, preflight/attempt, código/imagens, HTTP, diagnósticos, captura, CPU, dataset e certificado: experiment_results/'+P.name+'/. Aqui estão logs, scripts reutilizados, comparação tabular JSON, medições de concorrência/despacho, tabelas HTTP/computacionais/filas, correlação por identidade, reconciliações, figuras e manifestos. analysis_manifest.json vincula o relatório ao dataset e aos artefatos por SHA256. Commit local solicitado, sem push.')
(P/'report.md').write_text('\n'.join(report)+'\n')
dump('analysis_manifest.json',dict(dataset_manifest_sha256=S['manifest_sha256'],original_f64_manifest_sha256=previous['manifest_sha256'],files=[dict(path=str(v.relative_to(P)),bytes=v.stat().st_size,sha256=sha(v)) for v in sorted(P.rglob('*')) if v.is_file() and v.name not in ('analysis_manifest.json','finalization.log')]))
print(json.dumps(dict(report=str(P/'report.md'),recovery=recovery,rps_change_percent=gain,concurrency=S['concurrency_observed']),indent=2))
