"""B2-A report and figures from exported data only. No infrastructure actions."""
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
 last_legitimate_timeout_start=max(float(x['elapsed_seconds']) for x in timeouts),last_legitimate_timeout_end=max(float(x['end_elapsed_seconds']) for x in timeouts))
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
fig.suptitle('B2-A — emissão ofensiva [30,60); linha roxa: última conclusão ofensiva')
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
def h(cls,period):return next(v for v in H if v['traffic_class']==cls and v['period']==period)
def c(cls,period):return next(v for v in C if v['traffic_class']==cls and v['period']==period)
report=[]
def p(t=''):report.append(t)
p('# B2-A — piloto combinado L2 + A3')
p()
p('**A3 coincidiu com forte perda de atendimento legítimo, formação sustentada de filas e efeitos prolongados após a emissão. A execução foi operacionalmente certificada e íntegra. Houve recuperação descritiva no final de P3; podemos avançar para B2-F como próximo piloto exploratório, preservando as ressalvas abaixo. B2-F não foi executada.**')
p()
p('## 1. Identificação, ambiente e procedimento')
p()
p(f"Run `{S['run_id']}`; dataset `{S['dataset']}`. Checkout `824afd685640e3102ae9e8276287480c290ea1c0`, branch refactor/project-organization, working tree limpo antes da preparação. Uma única execução; returncode 0; completed/simulation_end; certificado completed, outcome completed_with_http_degradation, cleanup_verified=true. A degradação HTTP não acionou interrupção. O certificado está vinculado ao manifesto SHA256 `{S['manifest_sha256']}`. Dataset válido e elegível; exportação após encerramento/limpeza. Não houve repetição, build/pull ou alteração do simulador.")
p()
p('Configuração específica configuration.json (cópia em experiment_results/.../config.json), derivada do template protegido original sem sobrescrevê-lo: somente ID e attack.rate=4 foram alterados. L2: duas fontes × 8 RPS, /medium, nominal 16 RPS durante 150 s. A3: duas fontes × 4 RPS, /expensive, nominal 8 RPS em [30,60), computational_asymmetry continuous. Uma vítima, topologia direta sem NGINX, dois workers, timeout 2 s para ambas as classes, concorrência configurada 64 por classe (32 por fonte), sem autoscaling/balanceamento. Kernel, work_units, instrumentação e monitoramento preservados da infraestrutura atual; seed 20261107. Captura TCP e diagnósticos ON.')
p()
p('Imagens idênticas à B2-L, verificadas contra arquivos/launcher do checkout no preflight:')
p()
p('- Vítima: `sha256:03a186aa90eec03b874c82a887b245e7190fa45cd7256af3c077cb64943d52b0`.')
p('- Quatro fontes: `sha256:b94212edd4d31c34998aea870caebc4ba145c1593d1b8dfdc27fe4917719fe3e`.')
p()
p('Comparabilidade estrutural verificada em compatibility.json: normal_traffic, server, monitoring, diagnostics, topology, autoscaler, infrastructure, load_balancer, traffic_sources e política iguais à B2-L. Docker Engine 29.9.3, Python host 3.12.3; versões/pacotes, Docker info, imagens, recursos e comandos completos em initial_environment.json, image_inspect.json e command.json. Auditoria anterior: aproximadamente 10,5 GB RAM disponível, 37,5 GB disco livre e nenhum contêiner ativo. Host não foi tratado como ambiente de desempenho determinístico.')
p()
p('Política exploratory-offensive-v1 sem alteração: RAM mínima 2 GiB, disco mínimo 4 GiB, memória observada da vítima até 1 GiB e por fonte até 512 MiB, artefatos até 512 MiB, frescor da coleta 5 s, timeout Docker 3 s, orçamento global 240 s. São limites observacionais/proteções existentes, não quotas de CPU/RAM impostas. Foram reutilizados diagnostic_run, preflight e verificação de imagem, encadeamento --previous-run da B2-L, coleta, exportação, certificação e validação existentes. analyze.py apenas complementa offline o offensive_analysis v2, seus http_metrics/classify_operations e redutores de estado; não cria um novo coletor ou detector.')
p()
p('## 2. Emissão e atendimento HTTP')
p()
p('Coortes por instante de início HTTP: P1=[0,30), P2=[30,60), P3=[60,150). Resultados e duração incluem conclusões reais posteriores aos limites, mantendo a coorte original. Total legítimo usa [0,150)/150 s; Total ofensivo usa inícios em [30,60)/30 s, sem diluir a taxa por 150 s.')
p()
p(tab(['Classe','Coorte','Nominal / iniciado RPS','Submissões','Inícios','Respostas / 2xx','Timeouts','Sucessos/inícios'],[[v['traffic_class'],v['period'],f(v['nominal_rps'])+' / '+f(v['realized_rps'],3),v['submissions'],v['starts'],str(v['responses'])+' / '+str(v['success']),v['timeouts'],str(v['success'])+'/'+str(v['starts'])+' ('+f(100*v['availability'])+'%)' if v['availability'] is not None else '0/0; N/D'] for v in H]))
p()
p('Todos os inícios têm encerramento conhecido. Erros HTTP, erros de conexão e tentativas sem encerramento observado: zero em ambas as classes e períodos. Todos os códigos recebidos são 200. Legítimos: 2.385 submissões/inícios, nenhuma expiração pré-HTTP, disponibilidade 1.438/2.385=60,2935%. Ofensivos: 238 admissões, submissões e inícios, nenhuma expiração/rejeição pré-HTTP, 16 respostas e 222 timeouts. Admissões legítimas não têm evento independente: N/D, não zero. O journal ofensivo e os diagnósticos das quatro fontes foram reconciliados com os logs HTTP; planos sem submissão são preservados em emission_reconciliation.json e não são falhas de atendimento.')
p()
p('A taxa legítima iniciada em P2 foi 17,133 RPS, próxima/acima do nominal e sem evidência de colapso de emissão. Entretanto a taxa de respostas bem-sucedidas da coorte foi apenas 43/30=1,433 RPS, com disponibilidade 8,3658%. Essas taxas têm significados diferentes: emissão preservada não equivale a atendimento preservado. A taxa ofensiva realizada foi 7,933 RPS contra 8 nominais (238 contra 240 esperadas por nominal × janela). Não houve início ofensivo fora de [30,60).')
p()
p('Não houve tentativa legítima iniciada após 150 s nesta execução. Tentativas que começaram antes do limite e concluíram após ele permanecem em P3; IDs em summary.json/boundary_crossings e tempos reais em http_attempts.csv. Nenhuma conclusão em P3 reclassifica uma tentativa iniciada em P2.')
p()
p('## 3. Duração HTTP e separação entre encerramento e resposta')
p()
p(tab(['Classe','Coorte','Encerramentos: média / mediana / p95 ms','Respostas: média / mediana / p95 ms'],[[v['traffic_class'],v['period'],' / '.join(f(v[k]) for k in ('mean_ms','median_ms','p95_ms')),' / '.join(f(v[k]) for k in ('response_mean_ms','response_median_ms','response_p95_ms'))] for v in H]))
p()
p('Encerramentos incluem timeouts de aproximadamente 2 s; não são uma distribuição só de respostas. Os tempos de resposta somente dos sobreviventes são condicionais ao recebimento de resposta e não representam todos os inícios. Nenhuma duração foi imputada. Mediana convencional; p95 por posto mais próximo, usando as rotinas existentes. Mínimo/máximo e denominadores completos em http_by_period.csv/summary.json.')
p()
p('## 4. Operações computacionais e workers')
p()
p(tab(['Classe','Coorte HTTP','Subm./inic./concl./falha','CPU/op ms','Parede/op ms','Espera média / mediana / p95 ms'],[[v['traffic_class'],v['period'],' / '.join(str(v[k]) for k in ('submitted','started','completed','failed')),f(v['cpu_mean_ms']),f(v['wall_mean_ms']),' / '.join(f(v[k]) for k in ('wait_mean_ms','wait_median_ms','wait_p95_ms'))] for v in C]))
p()
p('Todas as 2.385 operações legítimas e 238 ofensivas terminaram computacionalmente, inclusive as associadas a timeouts HTTP. Timeout no cliente não representa cancelamento do trabalho já recebido: esse trabalho permaneceu na fila e disputou os dois workers. Essa distinção explica 2.385 conclusões computacionais legítimas contra apenas 1.438 respostas HTTP recebidas. As métricas computacionais das coortes acompanham o início HTTP; computational_events_by_actual_time.json preserva também o instante real de cada evento por período.')
p()
p(tab(['Classe','Coorte','PID','Operações','Espera média / mediana / p95 ms'],[[v['traffic_class'],v['period'],v['worker_pid'],v['operations'],' / '.join(f(v[k]) for k in ('wait_mean_ms','wait_median_ms','wait_p95_ms'))] for v in W]))
p()
p('A espera entre work_submitted e work_started inclui fila, IPC e agendamento; a duração computacional e CPU/op são os campos emitidos pelos workers. Os PIDs identificam os processos nesta execução, não identidades estáveis entre execuções. Operações unknown de auditoria estão separadas e não entram nas distribuições acima.')
p()
p('## 5. Filas, residual e recuperação')
p()
p(tab(['Intervalo','Classe','Pico aguardando','Pico executando','Pico pendente'],[[v['period'],v['traffic_class'],v['waiting'],v['running'],v['pending']] for v in Q]))
p()
p('Os máximos por classe podem ocorrer em instantes diferentes e não devem ser somados. O pico agregado foi 359 aguardando e 361 pendentes, maior já em P3; instantes exatos em queue_peak_times.json. queue_transitions.csv contém todas as transições observadas, sem reduzir o diagnóstico a amostras de um segundo. existing_analyzer/timeseries.csv preserva bins de eventos e estados no limite esquerdo do término de cada segundo.')
p()
br=S['residual']['boundaries']
p(tab(['Instante−','Legítimas aguard./exec./pend.','Ofensivas aguard./exec./pend.','Total pendente'],[[t+' s',' / '.join(str(br[t]['before']['counts']['benign'][k]) for k in ('waiting','running','pending')),' / '.join(str(br[t]['before']['counts']['attack'][k]) for k in ('waiting','running','pending')),sum(br[t]['before']['counts'][cls]['pending'] for cls in ('benign','attack','unknown'))] for t in br]))
p()
p(f"Em 60− s havia 220 legítimas aguardando e 103 ofensivas pendentes (101 aguardando + 2 executando), total 323. O estado em 60 s após os eventos exatamente na fronteira é igual ao anterior: nenhum evento ocorreu exatamente no corte; ambos os snapshots foram preservados. Todas as 238 operações ofensivas foram submetidas antes de 60 s; 103 concluíram a partir de 60 s. A última terminou em {lastoff:.6f} s, isto é, {lastoff-60:.6f} s após o fim da emissão. Isso mede a drenagem observada das operações ofensivas identificadas, não uma garantia universal contra ingressos não observados.")
p()
p(f"A fila legítima continuou aumentando durante o residual ofensivo, mesmo sem novos inícios ofensivos. Após {lastoff:.3f} s não restavam operações ofensivas, mas ainda havia trabalho legítimo acumulado: em 90− s eram 135 pendentes. O primeiro retorno do total pendente a zero após 60 s ocorreu em {firstzero:.6f} s. O último timeout legítimo iniciou em {recovery['last_legitimate_timeout_start']:.6f} s e terminou em {recovery['last_legitimate_timeout_end']:.6f} s. O atendimento pode voltar a caber no timeout antes de a fila inteira zerar; são marcos distintos. As operações não foram artificialmente canceladas ou drenadas por mudança da política.")
p()
p('## 6. Evolução em intervalos de 10 s')
p()
p(tab(['Coorte legítima','Inícios/RPS','2xx/inícios','HTTP média / p95 ms','Espera média ms','CPU/op ms'],[[v['period'],v['starts']+' / '+f(v['realized_rps']),v['success']+'/'+v['starts'],f(v['mean_ms'])+' / '+f(v['p95_ms']),f(v['wait_mean_ms']),f(v['cpu_mean_ms'])] for v in benign]))
p()
late=recovery['late_P3_100_150']
p(f"P3 não é homogêneo: [60,90) mantém 0% de respostas bem-sucedidas; [90,100) tem 154/162=95,06%; cada um dos cinco bins de [100,150) tem 100%. Agregando [100,150): {late['success']}/{late['starts']} sucessos, {late['rps']:.3f} RPS, HTTP médio {late['http_ms']['mean']:.2f} ms, p95 {late['http_ms']['p95']:.2f} ms, espera média {late['wait_ms']['mean']:.2f} ms e CPU/op {late['cpu_mean_ms']:.2f} ms. Essas medidas são próximas da referência interna P1 (53,27 ms de HTTP médio, 90,08 ms de p95, espera 3,16 ms). Há recuperação observada no final de P3; a média de todo P3 ainda reflete o período prolongado de degradação.")
p()
p('![Emissão, duração HTTP legítima, disponibilidade e pendências](temporal.png)')
p()
p('![Operações aguardando e executando](queues.png)')
p()
p('## 7. Comparação descritiva com B2-L e P1 interno')
p()
p(tab(['Referência/coorte','RPS legítimo','Disponibilidade','HTTP média / p95 ms','Espera média ms','CPU/op ms'],[['B2-L [0,150)',15.90,'100%','46,87 / 79,71',2.68,29.82]]+[[v['period'],f(v['realized_rps']),f(100*v['availability'])+'%',f(v['mean_ms'])+' / '+f(v['p95_ms']),f(c('benign',v['period'])['wait_mean_ms']),f(c('benign',v['period'])['cpu_mean_ms'])] for v in H if v['traffic_class']=='benign']))
p()
p(f"Durante P2, disponibilidade legítima caiu 91,63 pontos percentuais em relação a B2-L e a P1 interno (100% → 8,37%). HTTP médio de P2 é {h('benign','P2')['mean_ms']/base['b2_periods']['Total']['duration_ms']['mean']:.2f}× B2-L e {h('benign','P2')['mean_ms']/h('benign','P1')['mean_ms']:.2f}× P1 interno; p95 de P2 é {h('benign','P2')['p95_ms']/base['b2_periods']['Total']['duration_ms']['p95']:.2f}× B2-L. Em todo P3, a disponibilidade ainda é 66,36% e o HTTP médio 746,78 ms, porém os bins finais mostram recuperação. O RPS iniciado total ficou exatamente 15,90, como na B2-L; isso não compensou a perda de respostas.")
p()
p('A referência interna já era mais lenta antes do ataque: P1 tem HTTP médio 53,27 ms e CPU/op legítima 35,27 ms, frente a 46,87 e 29,82 ms da B2-L. No próprio P1 os bins de CPU/op variam de 30,46 a 38,80 ms. As imagens/código são iguais, mas não se pressupõe custo determinístico ou condições idênticas do host. Essa diferença foi registrada sem reabrir investigação ou atribuir causa específica. A presença de timeouts, fila crescente e residual é evidência direta desta execução; diferenças entre campanhas não são demonstração causal definitiva. Uma realização por configuração, sem testes inferenciais ou intervalos de confiança.')
p()
p('## 8. Recursos e integridade')
p()
p(tab(['Período','Ticks','CPU média / máxima % Docker','Memória média / máxima MiB','Cadência mediana / máx s','Amostras brutas'],[[v['period'],v['samples'],f(v['cpu_mean'])+' / '+f(v['cpu_max']),f(v['mem_mean_mib'])+' / '+f(v['mem_max_mib']),f(v['gap_median'],3)+' / '+f(v['gap_max'],3),v['raw_samples']] for v in R]))
p()
p('Na janela nominal foram 20 ticks: primeira observação 10,153 s, última 144,922 s. P1 tem apenas dois ticks e P2 três; intervalos de aproximadamente 10,07 s no início e 6,03 s em P3. Há 50 aquisições brutas na janela; a cadência configurada não equivale à realizada. Detalhes, lacunas e amostras fora da janela permanecem em existing_analyzer/summary.json e nos dados exportados. Sem interpolação ou média contínua ponderada. CPU Docker >100% representa mais de um núcleo lógico; CPU alta não é sozinha um critério de saturação ou interrupção. Aqui o acúmulo sustentado é demonstrado pelos eventos de fila. Telemetria não foi modificada e não foi aberta investigação de cadência.')
p()
cap=status['capture_results']
p(f"PCAP: {cap['pcap']['capture_counters']['packets_captured']} pacotes; CSV: {cap['csv']['capture_counters']['packets_captured']}; ambos aceitos, zero descartes pelo kernel. Diagnóstico da vítima: {writer['written']} eventos, sequência íntegra, zero perdas/erros, fechamento completo. Quatro journals/diagnósticos de fonte completos; todos os 2.623 inícios HTTP correlacionados a submissão computacional, sem conflitos de identidade ou ciclos parciais. Todos os {len(json.loads((P/'hash_verification.json').read_text()))} arquivos do manifesto conferidos por tamanho/SHA256; arquivos brutos exportados comparados sem divergência. Dataset válido/elegível, certificado vinculado ao manifesto. Os snapshots exportados não foram reescritos para incorporar o certificado posterior.")
p()
p('Foram reconciliadas 20 operações unknown de auditoria de captura, todas com handlers phase=capture_audit, endpoint /, anteriores à origem nominal; não são legítimas nem ofensivas. audit_reconciliation.json preserva identidades e intervalos. O analisador offensive_analysis v2, adequado a combined e já existente, mantém essas operações como unknown e as insuficiências de identidade explícitas. Não houve exclusão equivalente à do analisador legítimo A1 da B2-L; não se aplicou A1 a uma composição incompatível nem se forçou elegibilidade. Toda limitação do analisador existente foi preservada em existing_analyzer/.')
p()
p('Estado final computacional observado: zero aguardando/executando/pendente, de todas as classes, após fechamento da observação. Em 150− s ainda havia duas operações legítimas executando; suas conclusões e drenagem foram preservadas. Certificado e final_environment.json confirmam limpeza; quatro contêineres externos preservados e redes preexistentes vazias. Sem limpeza ampla de Docker.')
p()
p('## 9. Respostas e recomendação')
p()
p('1. **A3 reduziu o atendimento legítimo? Sim, nesta realização:** disponibilidade P2 de 8,37%, com 471 timeouts em 514 inícios, apesar de emissão legítima preservada.')
p('2. **Quanto mudaram disponibilidade e duração?** B2-L/P1 tinham 100%; P2 caiu 91,63 pp. HTTP médio passou de 53,27 ms em P1 para 1.939,93 ms em P2, com p95 de 2.006,48 ms.')
p('3. **Houve filas? Sim:** crescimento sustentado durante P2 e residual em P3; pico agregado de 361 pendentes, contra pico 5 em P1.')
p(f'4. **O processamento ofensivo continuou após 60 s? Sim:** 103 operações pendentes em 60−; última conclusão em {lastoff:.3f} s, residual de {lastoff-60:.3f} s.')
p('5. **Houve recuperação em P3? Sim, na parte final:** redução das filas, retorno a zero e disponibilidade 100% com duração próxima de P1 em todos os bins de [100,150). P3 agregado permanece degradado e não deve ser chamado integralmente recuperado.')
p('6. **Integridade/observabilidade suficientes? Sim para essas conclusões exploratórias:** captura, eventos, relógios, dataset e encerramento certificados; CPU esparsa limita conclusões sobre utilização contínua, sem impedir a observação direta de HTTP/fila.')
p()
p('**Recomenda-se avançar a B2-F como próximo piloto exploratório**, após seu preflight normal e nova autorização de execução. Preservar imagens, L2, workers, configuração computacional, timeout, concorrência, instrumentação e política; manter separação entre emissão, atendimento e processamento residual. A3 já produziu degradação severa combinada e não precisa ser repetido automaticamente. As condições de referência e limitações devem acompanhar a comparação com B2-F; não há seleção de detectores, calibração ou início da campanha definitiva. A CPU esparsa permanece pendência para antes da campanha científica.')
p()
p('## 10. Artefatos')
p()
p('Configuração, attempt/preflight, imagens/proveniência, captura, HTTP, CPU, diagnósticos, certificado e dataset estão em experiment_results/'+P.name+'/. Neste diretório: command.json, configuration.json, compatibility.json, execution.log/result, ambientes inicial/final, image_inspect.json, existing_analyzer/, summary.json, dataset_validation.json, hash_verification.json, raw_export_comparison.json, emission_reconciliation.json, source_integrity.json, audit_reconciliation.json, http_by_period.csv, http_attempts.csv, computation_by_period.csv, computational_events_by_actual_time.json, workers_by_period.csv, operations.csv, temporal_10s.csv, comparison_b2l.csv, queue_transitions.csv, queue_peaks.csv, queue_peak_times.json, queue_residual.json, recovery.json, resources_by_period.csv, cleanup_verification.json, figuras PNG/SVG, scripts e logs offline. analysis_manifest.json vincula os artefatos por SHA256; manifestos brutos/dataset permanecem em seus caminhos originais. Commit local solicitado; nenhum push.')
(P/'report.md').write_text('\n'.join(report)+'\n')
dump('analysis_manifest.json',dict(dataset_manifest_sha256=S['manifest_sha256'],baseline_manifest_sha256=S['baseline_manifest_sha256'],files=[dict(path=str(f.relative_to(P)),bytes=f.stat().st_size,sha256=sha(f)) for f in sorted(P.rglob('*')) if f.is_file() and f.name not in ('analysis_manifest.json','finalization.log')]))
print(json.dumps(dict(report=str(P/'report.md'),recovery=recovery,cleanup='verified',raw_export_unchanged=True),indent=2))
