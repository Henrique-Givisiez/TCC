"""Finalize B2-L artifacts offline; never invokes collectors or Docker."""
import pathlib,json,csv,hashlib,sys,collections
P=pathlib.Path(__file__).resolve().parent
ROOT=P.parents[1];sys.path.insert(0,str(ROOT))
from experiments.exploratory_analysis import describe
from experiments.export_dataset import placement
RUN=ROOT/'experiment_results'/P.name
S=json.loads((P/'summary.json').read_text())
def dump(name,obj):(P/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def rows(name):return list(csv.DictReader((P/name).open()))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
H=rows('http_by_period.csv');C=rows('computation_by_period.csv');W=rows('worker_wait_by_period.csv');R=rows('resources_by_period.csv')
http=rows('http_attempts.csv');ops=rows('operations.csv');q=rows('queue_transitions.csv')
origin=json.loads((RUN/'raw/diagnostics/metadata.json').read_text())['origin_monotonic']
events=[json.loads(l) for l in (RUN/'raw/diagnostics/victim/events.jsonl').read_text().splitlines()]
unknown={e['operation_id'] for e in events if e['kind']=='work_submitted' and not e.get('request_id')}
audit=[]
for oid in sorted(unknown):
 ee=[e for e in events if e.get('operation_id')==oid]
 handlers=[e for e in ee if e['kind'].startswith('handler_')]
 assert len(handlers)==2 and all(e.get('phase')=='capture_audit' and e['endpoint']=='/' for e in handlers)
 audit.append(dict(operation_id=oid,kinds=dict(collections.Counter(e['kind'] for e in ee)),start_seconds=min(e['at'] for e in ee)-origin,end_seconds=max(e['at'] for e in ee)-origin,classification='unknown / capture_audit',included_in_legitimate=False))
assert len(audit)==10
dump('audit_reconciliation.json',audit)
queuestats=[]
for name,a,b in [('Total',0,150),('P1',0,30),('P2',30,60),('P3',60,150)]:
 state=dict(waiting=0,running=0,pending=0);last=a;weighted=collections.Counter();longest=0;episode=None;zero=0
 for row in q:
  t=float(row['seconds'])
  if t<a:state={k:int(row[k]) for k in state};continue
  if t>=b:break
  for k in state:weighted[k]+=(t-last)*state[k]
  if state['pending'] and episode is None:episode=last
  new={k:int(row[k]) for k in state}
  if not new['pending']:
   if episode is not None:longest=max(longest,t-episode);episode=None
   zero+=1
  state=new;last=t
 for k in state:weighted[k]+=(b-last)*state[k]
 if episode is not None:longest=max(longest,b-episode)
 queuestats.append(dict(period=name,time_mean_waiting=weighted['waiting']/(b-a),time_mean_pending=weighted['pending']/(b-a),longest_observed_continuous_pending_seconds=longest,returns_to_zero=zero))
dump('queue_stability.json',queuestats)
sourcechecks=[]
for source in ('normal_1','normal_2'):
 ee=[json.loads(l) for l in (RUN/f'raw/source_artifacts/{source}/output/diagnostics/events.jsonl').read_text().splitlines()]
 ok=[e['sequence'] for e in ee]==list(range(1,len(ee)+1))
 ww=json.loads((RUN/f'raw/source_artifacts/{source}/output/diagnostics/events.summary.json').read_text())
 assert ok and ww['complete'] and ww['written']==len(ee) and ww['dropped']==ww['write_errors']==0
 sourcechecks.append(dict(source=source,sequence_valid=ok,events=len(ee),complete=True))
dump('source_integrity.json',sourcechecks)
manifest=json.loads((RUN/'dataset/dataset_manifest.json').read_text());idx={e['path']:e for e in manifest['files']}
rawchecks=[]
for p in (RUN/'raw').rglob('*'):
 if not p.is_file():continue
 rel=str(p.relative_to(RUN/'raw'));dest=placement(pathlib.Path(rel))[0]
 if dest not in idx or rel=='operational_policy.json':continue
 rawchecks.append(dict(raw_path=rel,exported_path=dest,unchanged=sha(p)==idx[dest]['sha256']))
assert all(r['unchanged'] for r in rawchecks)
dump('raw_export_comparison.json',rawchecks)
final=json.loads((P/'final_environment.json').read_text());initial=json.loads((P/'initial_environment.json').read_text())
before=[json.loads(l) for l in initial['containers']['stdout'].splitlines() if l]
after=[json.loads(l) for l in final['containers']['stdout'].splitlines() if l]
networks=json.loads(final['networks']['stdout'])
assert {c['ID'] for c in before}=={c['ID'] for c in after}
assert all(c['State']!='running' for c in after) and all(not n['Containers'] for n in networks)
dump('cleanup_verification.json',dict(source='Final environment snapshot after completed execution; resume performs no infrastructure actions',external_containers_preserved=len(after),experimental_containers_remaining=0,networks_empty=True,certificate_cleanup_verified=S['certificate']['cleanup_verified']))
dump('offline_analysis_history.json',dict(experiment_repeated=False,
 previous_failure='AssertionError at attempt lifecycle reconciliation: planned-only attempt IDs were included as submitted attempts.',
 correction='Restrict lifecycle reconciliation to IDs with submitted events; preserve two planned-only IDs separately. Existing generator creates the first submission without a planned event.',
 interruption='User accidentally interrupted before launching the corrected final analysis; analyze.py correction was already persisted.',
 final_analysis='analysis_final.log: completed, exit code 0',raw_data_modified=False,
 legacy_alert='existing_analyzer remains ineligible due to 31 unidentified events. Ten capture audit operations account for 30 work events; one observation closure accounts for the remaining event. No override of legacy output.'))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,ax=plt.subplots(4,1,figsize=(11,11),sharex=True)
bins=[]
for a in range(0,150,10):
 hh=[r for r in http if a<=float(r['elapsed_seconds'])<a+10]
 oo=[o for o in ops if o['traffic_class']=='benign' and o['http_start'] and a<=float(o['http_start'])<a+10]
 bins.append(dict(start=a,rps=len(hh)/10,http_mean=describe(float(r['duration_ms']) for r in hh)['mean'],http_p95=describe(float(r['duration_ms']) for r in hh)['p95'],wait_p95=describe(float(o['wait_ms']) for o in oo)['p95'],cpu_mean=describe(float(o['cpu_ms']) for o in oo)['mean']))
x=[v['start']+5 for v in bins]
ax[0].plot(x,[v['rps'] for v in bins],marker='o');ax[0].axhline(16,color='gray',ls='--');ax[0].set_ylabel('Inícios HTTP/s')
for key,label in [('http_mean','Média'),('http_p95','p95')]:ax[1].plot(x,[v[key] for v in bins],marker='o',label=label)
ax[1].set_ylabel('Duração HTTP (ms)');ax[1].legend()
for key,label in [('wait_p95','Espera p95'),('cpu_mean','CPU/op média')]:ax[2].plot(x,[v[key] for v in bins],marker='o',label=label)
ax[2].set_ylabel('Computação (ms)');ax[2].legend()
qq=[r for r in q if 0<=float(r['seconds'])<150]
ax[3].step([0]+[float(r['seconds']) for r in qq]+[150],[0]+[int(r['pending']) for r in qq]+[0],where='post',lw=.7)
ax[3].set_ylabel('Operações pendentes');ax[3].set_xlabel('Segundos desde a origem experimental')
for a in ax:
 a.axvline(30,color='gray',ls=':');a.axvline(60,color='gray',ls=':');a.grid(alpha=.2);a.set_xlim(0,150)
fig.suptitle('B2-L — intervalos de referência, sem ataque; bins descritivos de 10 s')
fig.tight_layout();fig.savefig(P/'stability.png',dpi=150);fig.savefig(P/'stability.svg');plt.close(fig)
dump('temporal_10s.json',bins)

def fmt(v,n=2):
 if v is None or v=='':return 'N/D'
 return f'{float(v):.{n}f}'
def mdtable(headers,data):return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(str(v) for v in rr)+' |' for rr in data])
report=[]
def p(t=''):report.append(t)
p('# B2-L — validação exploratória legítima L2')
p()
p('**Conclusão: sim. L2 apresentou comportamento suficientemente estável nesta execução exploratória e na infraestrutura atual para servir como referência de B2-A e B2-F. Recomenda-se avançar ao planejamento/execução autorizada de B2-A, preservando as ressalvas de fronteira temporal e observabilidade descritas abaixo. B2-A e B2-F não foram executadas.**')
p()
p('## 1. Ambiente e configuração')
p()
p(f"Run `{S['run_id']}`; início UTC 2026-11-07 23:26:07 (20:26:07 em São Paulo). Branch `refactor/project-organization`; SHA `{S['checkout']}`; working tree limpo na auditoria inicial. Apenas artefatos novos foram acrescentados em reports. Docker Engine 29.9.3; Python host 3.12.3; detalhes de Engine, SO, pacotes, CPU e memória em initial_environment.json e image_inspect.json.")
p()
p('Template `experiments/configs/protected_compositions/pilot-legitimate.json`, copiado sem alteração para config.json: legitimate; topologia direta; duas fontes × 8 RPS; nominal agregado 16 RPS; /medium; nenhuma fonte ofensiva; dois workers; 150 s; timeout 2 s; captura TCP e diagnósticos habilitados. Concorrência configurada 64 agregada, orçamento 32 por fonte. Seed 20261107, autoscaling e balanceador desabilitados; fila diagnóstica 4096. Monitoring: intervalo 5 s, stats_poll 1 s, histórico 30 s; cadência efetiva distinta, documentada adiante. Configuração efetiva completa no dataset.')
p()
p('Imagens reutilizadas, sem build/pull, verificadas contra arquivos e launcher do checkout pelo executor:')
p()
p('- Vítima: `sha256:03a186aa90eec03b874c82a887b245e7190fa45cd7256af3c077cb64943d52b0`.')
p('- Ambas as fontes: `sha256:b94212edd4d31c34998aea870caebc4ba145c1593d1b8dfdc27fe4917719fe3e`.')
p()
p('Política exploratory-offensive-v1 inalterada: RAM host mínima 2 GiB; disco mínimo 4 GiB; memória observada máxima por vítima 1 GiB e por fonte 512 MiB; artefatos 512 MiB; frescor 5 s; timeout Docker 3 s; orçamento global 240 s. São salvaguardas observacionais, não quotas de recursos impostas. Auditoria inicial: RAM disponível 12.019.781.632 bytes e disco 37.532.319.744 bytes no preflight. Recursos e versões completos foram preservados para comparação contemporânea.')
p()
p('## 2. Procedimento e integridade')
p()
p('Foi realizada uma única execução pelo diagnostic_run existente: verificação de composição/política → preflight protegido → verificação de código das imagens → run_recorded → encerramento/drenagem/limpeza → exportação → certificação e validação. Returncode 0; completed/simulation_end; certificado completed, outcome completed_integral; procedure_completed e cleanup_verified verdadeiros. Dataset válido e elegível. Certificado final vinculado ao run e ao SHA256 do manifesto; o snapshot operacional exportado anterior ao certificado não foi reescrito.')
p()
p(f"Todos os {len(manifest['files'])} arquivos do manifesto foram conferidos por tamanho/SHA256. {len(rawchecks)} arquivos brutos exportados também foram comparados ao manifesto; sem divergência. PCAP e CSV aceitos: 12.594 pacotes capturados por cada processo, zero descartados pelo kernel. Eventos da vítima: 11.981, sequência íntegra, zero perdas/erros de escrita, observação fechada e completa. Fontes: 7.015 e 7.303 eventos, sequências completas e zero perdas. Não houve conflitos de identidade ou ciclos computacionais parciais. Relógios da vítima e das fontes certificados como comparáveis pelo procedimento existente.")
p()
p('O analisador legítimo existente foi executado e seu resultado preservado em existing_analyzer/. Ele marcou a execução como não elegível para sua comparação principal por 31 eventos sem request_id. A reconciliação por operation_id identifica dez operações completas com handlers explicitamente marcados capture_audit, endpoint /, mais o fechamento da observação: 30 eventos de trabalho + 1 fechamento. Essas dez operações permanecem unknown e excluídas das métricas legítimas; não foram convertidas artificialmente em tráfego legítimo. audit_reconciliation.json preserva cada ID e intervalo. A exclusão do analisador legado permanece visível; a análise descritiva B2-L usa a classificação e o redutor computacional existentes, com essa reconciliação explícita. Isso não altera o certificado ou os dados.')
p()
p('A última falha offline foi uma asserção que incluía IDs apenas planejados na reconciliação de tarefas submetidas. A correção limita essa checagem a IDs com submissão e preserva dois planos sem submissão (um por fonte). Os 2.386 ciclos submetidos têm, cada um, submissão, início de tarefa, início/fim HTTP e fim de tarefa. Planos não submetidos não são expirações ou falhas da vítima. A interrupção acidental foi retomada somente offline; nenhuma repetição experimental. Histórico em offline_analysis_history.json; log final em analysis_final.log.')
p()
p('## 3. Emissão, atendimento e disponibilidade')
p()
p('P1=[0,30), P2=[30,60), P3=[60,150) são intervalos de referência, sem fases reais de ataque. As coortes são definidas pelo início HTTP; conclusões posteriores permanecem na coorte original. Total abaixo é a janela nominal [0,150).')
p()
p(mdtable(['Coorte','Nominal RPS','RPS iniciado','Δ RPS','Submissões cliente','Inícios','HTTP 2xx / inícios','Disponibilidade'],[[r['period'],16,fmt(r['realized_rps'],3),fmt(r['delta_rps'],3),r['submissions'],r['started'],r['success']+' / '+r['started'],'100%'] for r in H]))
p()
p('A janela entregou 2.385 tentativas versus 2.400 esperadas por nominal × duração: diferença −15 (−0,625%). Por período: −5,00%, +7,29% e −1,81% do nominal. A taxa oscila entre períodos, sem queda progressiva; não se exige igualdade exata com o nominal. Admissões não têm evento independente neste gerador e são N/D; submissões são medidas diretamente nos diagnósticos das fontes. Não se deve apresentar ausência de evento de admissão como zero admissões. Expirações anteriores ao HTTP: zero, sustentado pela reconciliação integral das tarefas submetidas.')
p()
p('Em cada linha, encerramentos conhecidos = respostas recebidas = respostas HTTP 200 = inícios. Erros HTTP, timeouts, erros de conexão e tentativas sem encerramento observado: zero em todos os períodos. A disponibilidade é explicitamente 2.385/2.385=100% na janela nominal; não usa planos ou descartes pré-HTTP como denominador.')
p()
p('**Fronteira final:** há 2.386 tentativas no registro completo, todas HTTP 200, disponibilidade observada 2.386/2.386=100%. Uma começou em 150,002278277 s e terminou em 150,078272235 s (75,993958 ms): request_normal_2_000001217. Está na coorte tail, fora de P3 e do cálculo 2.385/150=15,90 RPS. O total bruto não foi truncado ou ocultado. Outra tentativa iniciou em 149,965043583 s e concluiu em 150,000263984 s: continua em P3. A observação demonstra pequeno início após a fronteira; não se afirma garantia estrita de cessação em 150 s.')
p()
p('A tentativa request_normal_1_000000489 começou em P2 e concluiu em P3. Ela permanece entre as 515 tentativas de P2 e seus resultados/duração integram essa coorte. A submissão/início/conclusão computacional dessa tentativa ocorreu em P3: contagens por instante real de evento computacional são 456/514/1.415, enquanto coortes por início HTTP são 456/515/1.414. Ambos os eixos estão preservados, sem deslocar a coorte HTTP.')
p()
p('## 4. Duração HTTP')
p()
p(mdtable(['Coorte','Média ms','Mediana ms','p95 ms','Mínimo ms','Máximo ms'],[[r['period'],*[fmt(r[k]) for k in ('mean_ms','median_ms','p95_ms','min_ms','max_ms')]] for r in H]))
p()
p('Neste run todas as tentativas encerradas receberam resposta; portanto distribuições de duração de encerramentos conhecidos e de respostas coincidem. No registro completo, incluindo tail, média '+fmt(S['groups']['benign']['known_end_duration_ms']['mean'])+' ms, mediana '+fmt(S['groups']['benign']['known_end_duration_ms']['p50'])+' ms e p95 '+fmt(S['groups']['benign']['known_end_duration_ms']['p95'])+' ms. Nenhuma duração foi imputada. Estatísticas usam rotinas existentes: mediana convencional e p95 por posto mais próximo.')
p()
p('## 5. Processamento computacional e filas')
p()
p(mdtable(['Coorte HTTP','Subm./inic./concl.','Falhas','Espera média/mediana/p95 ms','CPU/op média ms','Parede/op média ms','Aguard./exec./pend. no limite−'],[[r['period'],r['submitted']+'/'+r['started']+'/'+r['completed'],r['failed'],' / '.join(fmt(r[k]) for k in ('wait_mean_ms','wait_median_ms','wait_p95_ms')),fmt(r['cpu_mean_ms']),fmt(r['wall_mean_ms']),r['waiting_at_end']+'/'+r['running_at_end']+'/'+r['pending_at_end']] for r in C]))
p()
p('No registro completo são 2.386 operações legítimas submetidas, iniciadas e concluídas, sem falha; a operação tail é apresentada separadamente das 2.385 da janela. Dez operações de auditoria unknown foram submetidas/iniciadas/concluídas e não entram nesses números. Nenhuma operação ofensiva. Estado final observado: zero aguardando, executando ou pendente. Zero no limite 150− não prova ausência de ingresso posterior: a operação tail foi efetivamente observada após esse limite.')
p()
p(mdtable(['Coorte','PID worker','n','Espera média ms','Mediana ms','p95 ms'],[[r['period'],r['worker_pid'],r['n'],fmt(r['mean_ms']),fmt(r['median_ms']),fmt(r['p95_ms'])] for r in W]))
p()
p('Espera é o intervalo observado entre work_submitted e work_started, incluindo fila, IPC e agendamento; não é uma medida pura de espera na fila interna. Duração computacional de parede e CPU por operação são as medidas emitidas pelo worker. Não houve alteração desses mecanismos.')
p()
p(mdtable(['Intervalo','Pico aguardando','Pico executando','Pico pendente','Maior trecho contínuo pendente s','Retornos a zero'],[[r['period'],3,2,5,fmt(r['longest_observed_continuous_pending_seconds'],4),r['returns_to_zero']] for r in queuestats]))
p()
p('Os picos reais de três aguardando e cinco pendentes repetem-se nos três períodos e são transitórios. queue_transitions.csv contém todas as transições; timeseries_1s.csv contém estados imediatamente antes de cada limite de um segundo, sem confundi-los com picos intrassegundo. Os retornos frequentes a zero e os limites finais vazios não mostram crescimento sustentado de trabalho pendente. Esperas pontuais positivas não foram interpretadas automaticamente como saturação.')
p()
p('## 6. Recursos e observabilidade')
p()
p(mdtable(['Intervalo','Ticks','CPU média / máxima % Docker','Memória média / máxima MiB','Gap mediano / máximo s','Amostras brutas'],[[r['period'],r['ticks'],fmt(r['cpu_mean'])+' / '+fmt(r['cpu_max']),fmt(r['memory_mean_mib'])+' / '+fmt(r['memory_max_mib']),fmt(r['tick_gap_median'],3)+' / '+fmt(r['tick_gap_max'],3),r['raw_samples']] for r in R]))
p()
p('Na janela nominal existem 24 ticks (4/5/15 por período), primeira amostra em 6,138 s e última em 144,839 s; sem observação de tick nos trechos [0,6,138) e (144,839,150). Gap mediano 6,033 s, máximo 6,076 s. São 51 aquisições brutas em [0,150), com gap mediano 3,014 s; a cadência configurada de 1 s não foi realizada. O registro completo inclui um tick após 150 s e uma aquisição bruta adicional: 25 e 52 respectivamente, mantidos em summary.json. Não houve interpolação ou alteração de cadência; CPU média é média das amostras, não integração temporal. CPU Docker 100% equivale aproximadamente a um núcleo lógico, não ao host inteiro.')
p()
p('A memória observada aumentou: média 43,88 → 46,39 → 50,64 MiB; máximo 53,60 MiB na janela e 53,85 MiB incluindo fechamento. Não há OOM/restart ou violação operacional; uma execução de 150 s não permite excluir crescimento de memória em durações maiores. Esse aumento permanece registrado e não foi chamado de memória constante. A pendência da telemetria CPU deve ser tratada antes da campanha definitiva.')
p()
p('## 7. Estabilidade temporal e decisão')
p()
p('RPS realizado: 15,20 → 17,17 → 15,71, sem declínio progressivo; disponibilidade 100% nos três períodos. HTTP médio: 46,69 → 46,64 → 47,02 ms; p95: 78,67 → 78,74 → 80,72 ms. P3 tem média cerca de 0,70% acima de P1 e p95 cerca de 2,61% acima: pequena variação descritiva, sem escalada de latência nesta realização. CPU/op: 29,66 → 29,27 → 30,06 ms, variação aproximada de 2,7% entre menor e maior média de período. É a referência contemporânea deste checkout/imagens; não se reabre a investigação de campanhas antigas.')
p()
p('Espera média agregada: 2,44 → 2,61 → 2,79 ms, aumento absoluto de 0,34 ms entre P1 e P3. A mediana permanece perto de 1,2 ms; no worker 26 o p95 de P3 é menor que o de P2. Há pequena elevação em algumas medidas, que foi preservada, mas ela não vem acompanhada de acúmulo persistente ou aumento relevante da duração HTTP. Assim, não há evidência descritiva de deterioração progressiva do atendimento ou saturação sustentada nesta execução.')
p()
p('![Estabilidade temporal](stability.png)')
p()
p('## 8. Limitações e condições para B2-A/B2-F')
p()
p('Uma realização, uma semente e 150 s: sem testes inferenciais ou afirmação de estabilidade populacional. CPU esparsa limita avaliação contínua; memória cresce moderadamente; admissões não têm medida independente; espera inclui IPC/agendamento; existe um início após 150 s; o analisador legado mantém sua exclusão até a reconciliação explícita aqui apresentada. Esses pontos não são apagados por certificação operacional. Zero pendente ao encerrar é estado observado, não garantia universal de ausência de ingressos futuros.')
p()
p('**Podemos avançar para B2-A como piloto exploratório.** Preservar SHA, IDs imutáveis das imagens, L2=2×8 RPS /medium, dois workers, timeout 2 s, concorrência e instrumentação, política e parâmetros de recursos. Executar o preflight normal no futuro piloto e registrar novamente versões/recursos; alterações de imagem ou infraestrutura exigem nova avaliação de comparabilidade. Aplicar a mesma classificação pelo início HTTP e manter conclusões reais, coortes cruzadas e tail separados. A fronteira legítima atual não deve ser usada como prova de corte exato de tráfego em 150 s. A observabilidade CPU e o contrato temporal devem ser considerados antes da campanha científica definitiva. Esta recomendação não executa B2-A/B2-F e não escolhe automaticamente intensidade ofensiva.')
p()
p('## 9. Artefatos e encerramento')
p()
p('Dataset, configuração, proveniência, imagens, preflight/attempt, journals, HTTP, diagnósticos, CPU e captura: `experiment_results/'+P.name+'/`. Manifesto SHA256: `'+S['manifest_sha256']+'`. Certificado final: raw/operational_policy.json; validação operacional: raw/dataset_validation.json. Os resultados exportados anteriores não foram sobrescritos.')
p()
p('Neste diretório: summary.json, dataset_validation.json, hash_verification.json, raw_export_comparison.json, existing_analyzer/, http_by_period.csv, http_attempts.csv, operations.csv, computation_by_period.csv, worker_wait_by_period.csv, resources_by_period.csv, queue_transitions.csv, queue_peaks_by_period.csv, queue_stability.json, timeseries_1s.csv, temporal_10s.json, stability.png/svg, audit_reconciliation.json, source_integrity.json, cleanup_verification.json e offline_analysis_history.json. Scripts analyze.py/finalize.py tornam a análise rastreável. Logs de execução e comandos, ambientes inicial/final e inspeção das imagens também preservados.')
p()
p('Limpeza verificada pelo executor e pelo snapshot final: nenhum recurso experimental remanescente, redes preexistentes vazias, quatro contêineres externos preservados. A retomada foi exclusivamente offline. Nenhuma modificação do simulador, geradores, vítima, instrumentação, detectores ou política; nenhum novo build, experimento, push ou campanha definitiva.')
(P/'report.md').write_text('\n'.join(report)+'\n')
dump('analysis_manifest.json',dict(files=[dict(path=str(f.relative_to(P)),bytes=f.stat().st_size,sha256=sha(f)) for f in sorted(P.rglob('*')) if f.is_file() and f.name not in ('analysis_manifest.json','finalization.log')],dataset_manifest_sha256=S['manifest_sha256']))
print(json.dumps(dict(report=str(P/'report.md'),queue_stability=queuestats,raw_files_unchanged=len(rawchecks),audit_operations=len(audit),cleanup='verified'),indent=2))
