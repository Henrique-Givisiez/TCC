import json,hashlib,subprocess,shutil
from pathlib import Path
r=Path('experiment_results/b12-isolated-20261107T200251Z');out=Path('reports')/r.name
records=json.loads((out/'consolidated.json').read_text());checks=[]
for row in records:
 d=Path(row['dataset']);m=json.loads((d/'dataset_manifest.json').read_text());bad=[]
 for e in m['files']:
  p=d/e['path']
  if p.stat().st_size!=e['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=e['sha256']:bad.append(e['path'])
 checks.append(dict(configuration=row['configuration'],files=len(m['files']),hash_errors=bad))
(out/'final_hash_verification.json').write_text(json.dumps(checks,indent=2))
cleanup=dict(containers=subprocess.check_output(['docker','ps','-a','--no-trunc'],text=True),networks=json.loads(subprocess.check_output(['docker','network','inspect','edos_sources','edos_network'],text=True)),disk=shutil.disk_usage('.')._asdict(),git_status=subprocess.check_output(['git','status','--short'],text=True))
(out/'final_environment.json').write_text(json.dumps(cleanup,indent=2))
report='''# B1.2 — Caracterização exploratória ofensiva isolada

## Ambiente, matriz e procedimento

Branch refactor/project-organization; HEAD adf3d42ef341449a1ed8e069a11024811339434c;
working tree inicialmente limpo. Docker Engine 29.9.3; Python 3.12.3. Disco inicial
34.081.382.400 bytes; RAM disponível inicial 9.820.229.632 bytes. Nenhum contêiner
ativo, redes experimentais vazias. Quatro contêineres externos foram preservados.

Matriz planejada: A1=2, A2=4, A3=8, A4=16 RPS no /expensive; F1=32, F2=64,
F3=128, F4=192, F5=256 RPS no /medium. A1 é o piloto anterior, originalmente de
validação de integração, e NÃO foi repetido. Foram realizadas oito execuções novas,
uma por A2–A4 e F1–F5, nessa ordem; todas terminaram completed/simulation_end e
foram certificadas. Não houve B2 ou repetições científicas.

Comuns: composição offensive, zero legítimos, duas fontes, dois workers, 150 s,
pré [0,30), emissão [30,60), pós [60,150), timeout 2 s, diagnóstico/captura ON,
concorrência agregada 64. Templates existentes, alterando somente ID e taxa/fonte
conforme matriz. Semente 20261107 preservada: não implica trajetórias independentes
ou comparações pareadas causais. Ver config.json/effective_config.json de cada run.
Política exploratory-offensive-v1 inalterada: RAM host >=2 GiB, disco >=4 GiB,
vítima <=1 GiB, fonte <=512 MiB, artefatos <=512 MiB, frescor 5 s, Docker 3 s,
limite global 240 s. CPU, fila e resultados HTTP não foram critérios de parada.

Imagens imutáveis verificadas contra o checkout, sem novo build:
- vítima sha256:03a186aa90eec03b874c82a887b245e7190fa45cd7256af3c077cb64943d52b0;
- fontes sha256:b94212edd4d31c34998aea870caebc4ba145c1593d1b8dfdc27fe4917719fe3e.
Ver image_verification*.json. Executor existente diagnostic_run, com preflight,
--previous-run, exportação e certificação; analisador offensive_analysis v2.

## Matriz efetiva e emissão

| Configuração | Nominal RPS | Iniciado RPS | Δ RPS | Admissões/submissões | Inícios | Expirações |
|---|---:|---:|---:|---:|---:|---:|
'''
for x in records:report+=f"| {x['configuration']} | {x['nominal']} | {x['realized']:.3f} | {x['delta']:+.3f} | {x['admissions']}/{x['submitted']} | {x['starts']} | {x['expired']} |\n"
report+='''
RPS realizado = inícios HTTP em [30,60)/30. Admissão, submissão de tarefa,
início do callable, início lógico HTTP, recebimento na vítima e conclusão são
eventos distintos. Todas as janelas ofensivas foram respeitadas. Expiração é descarte
no cliente anterior ao HTTP; não é falha de atendimento da vítima.

## HTTP

| Configuração | Encerradas | Respostas | Erros HTTP | Timeouts | Conexão | Média ms | Mediana ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
'''
for x in records:report+=f"| {x['configuration']} | {x['ended']} | {x['responses']} | {x['http_errors']} | {x['timeouts']} | {x['connections']} | {x['http_mean_ms']:.2f} | {x['http_median_ms']:.2f} | {x['http_p95_ms']:.2f} |\n"
report+='''
Durações acima incluem encerramentos conhecidos, inclusive timeouts; não descrevem
exclusivamente respostas bem-sucedidas. As distribuições somente de respostas estão
em cada summary.json. Não há durações imputadas a censura. Ausência de erro não
implica ausência de degradação: F2 apresenta duração muito maior que F1.

## Computação e persistência

| Configuração | Submetidas/iniciadas/concluídas | CPU/op ms | Espera média/p95 ms | Parede média ms | Aguardando/em execução em E− | Conclusões pós-E | Última conclusão s | Pendentes no corte |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
'''
for x in records:
 ev=x['computational_events'];counts='/'.join(str(ev.get(k,0)) for k in ('work_submitted','work_started','work_completed'))
 report+=f"| {x['configuration']} | {counts} | {x['cpu_op_ms']:.2f} | {x['wait_mean_ms']:.2f}/{x['wait_p95_ms']:.2f} | {x['compute_wall_ms']:.2f} | {x['E_waiting']}/{x['E_running']} | {x['late_completions']} | {x['last_compute']:.6f} | {x['close_pending']} |\n"
report+='''
E− é o estado imediatamente anterior a 60 s. Há filas/esperas observáveis nas
operações, com acúmulo pronunciado em A3/A4 e F2–F5. Espera inclui fila, IPC e
agendamento; qualquer valor positivo isolado não comprova saturação do pool.
A4 mantém trabalho residual até 92,538 s (32,538 s após E). Zero pendente no snapshot
não é por si prova de impossibilidade de ingressos futuros; ingress_closed continua
condição externa. Operações de setup sem identidade permanecem unknown, separadas.
'''
for x in records:
 if x['victim_submissions_at_or_after_E']:
  report+=f"\n{x['configuration']}: {x['victim_submissions_at_or_after_E']} submissão(ões) computacional(is) em/após E, embora o início lógico HTTP estivesse dentro da janela. Isso explica por que conclusões pós-E podem exceder pendências em E−; não é violação de emissão.\n"
report+='''
## Recursos e limitação dos geradores

| Configuração | CPU média/máxima % Docker | Memória máx MiB | Tick CPU mediana/máx s | Coleta bruta mediana/máx s | Pico tarefas não iniciadas/fonte | Despacho fonte média/máx ms |
|---|---:|---:|---:|---:|---:|---:|
'''
for x in records:report+=f"| {x['configuration']} | {x['cpu_mean']:.2f}/{x['cpu_max']:.2f} | {x['memory_max']:.2f} | {x['cpu_tick_median']:.3f}/{x['cpu_tick_max']:.3f} | {x['cpu_raw_median']:.3f}/{x['cpu_raw_max']:.3f} | {x['source_queue_peak_per_source']} | {x['source_dispatch_mean_ms']:.2f}/{x['source_dispatch_max_ms']:.2f} |\n"
report+='''
CPU/memória são médias/máximos de ticks suportados, não médias contínuas ponderadas.
A média inclui pré/pós sem carga e não mede CPU durante o ataque isoladamente.
CPU Docker >100% representa mais de um núcleo. Não houve interpolação; lacunas,
contagens por fase e amostras constam em summary.json. Não há evidência apenas de
CPU usada para afirmar saturação. O pico das fontes é a diferença observada entre
tarefas submetidas e iniciadas, não acesso à fila interna do executor. O primeiro
slot em trânsito pode produzir pico 1 sem backlog relevante. A espera de despacho
inclui tarefas que posteriormente expiraram, não só as convertidas em HTTP.

F3–F5 mostram forte acúmulo no cliente e expirações. A taxa HTTP ficou próxima de
63–67 RPS, apesar de 128–256 nominais. Há evidência direta de limitação do sistema
cliente/executor na carga entregue; a capacidade da vítima também participa do
feedback através da duração das chamadas e da concorrência. Não se atribui toda a
redução à vítima nem se identifica causalmente um único gargalo. Admissões também
ficam abaixo de nominal×30: o gerador usa esperas relativas e tem custo de despacho,
logging e manutenção de Futures. Sem perfilamento, não separar suas contribuições.

## Integridade, certificação e incidente

Todas as execuções novas: dataset válido/elegível, fechamento computacional íntegro,
sem conflitos de identidade, sem início ofensivo fora da janela e captura aceita.
Manifestos foram novamente conferidos por tamanho/SHA256, incluindo A1; resultados
em final_hash_verification.json. Verificações por run em raw/dataset_validation.json,
raw/operational_policy.json e analysis/summary.json (no diretório reports).
Todos os recursos experimentais foram removidos; redes preexistentes ficaram vazias;
quatro contêineres externos foram preservados. final_environment.json registra isso.

A2 teve um erro de invocação OFFLINE: o destino da análise estava dentro da árvore
raw/dataset do run, vedado pelo analisador. O coletor havia terminado com returncode=0
 e certificação completed. A progressão parou, o problema foi diagnosticado e somente
a análise dos mesmos dados foi executada no caminho correto de reports. Após confirmar
integridade e limpeza, a progressão continuou. Não houve repetição experimental,
alteração de código ou flexibilização. analysis.log e progress/finished.initial_stop
preservam a ocorrência; progress.json mantém a mensagem histórica mesmo com status
completed, por rastreabilidade. A tabela consolidada usa a análise válida posterior.

## Conclusões e recomendações para discussão de B2

1. Executadas A2–A4 e F1–F5; A1 reutilizada do piloto. Uma realização por intensidade.
2. Degradação HTTP manifesta por timeouts em A3 e A4. F2–F5 mostram duração/espera
   elevadas sem timeouts. Não se reduz a definição de degradação à taxa de erros.
3. A fila computacional cresce em A3 e principalmente A4; em flooding há acúmulo
   importante de F2 em diante. Valores e limites de observação estão nas tabelas.
4. Residual: A4 é o mais prolongado; nos floodings altos observa-se aproximadamente
   1,2–1,3 s após E. A4 inclui chegada/submissão tardia de tentativa iniciada na janela.
5. A taxa realizada acompanha aproximadamente o nominal em A1–A4 e F1/F2; deixa de
   acompanhar F3–F5, cujas admissões pendentes expiram ao fechar a janela.
6. Filas/atrasos e expirações no cliente sustentam limitação de geração/entrega nos
   floodings altos; não equivalem a medir a capacidade HTTP potencial da vítima.
7. Para discussão posterior: A2/A3 cobrem pressão moderada e transição com timeouts;
   A4 oferece degradação severa. F1/F2 cobrem baixa pressão e transição de espera;
   F3 pode representar uma condição limitada pela entrega. F4/F5 não demonstraram
   aumento correspondente de tráfego realizado, portanto não devem ser escolhidos
   apenas pelo nominal maior. Nenhuma configuração final de B2 foi selecionada.
8. Antes da campanha definitiva: resolver/documentar CPU esparsa; validar cobertura
   e definição de recuperação, dimensionamento/semântica do gerador nas altas taxas,
   delineamento e repetições. Somar tráfego legítimo altera a capacidade disponível;
   resultados isolados não predizem diretamente as intensidades combinadas.

Sem comparação inferencial, seleção automática, detectores ou calibração. Não foram
alterados mecanismos, kernels, workers, timeout, instrumentação ou política.

## Artefatos e IDs

'''
for x in records:report+=f"- {x['configuration']}: run `{x['run_id']}`, dataset `{x['dataset']}`, análise `{x['analysis']}`.\n"
report+=f'''
Matriz e comandos: {r}/plan.json, remaining_plan.json e diretórios por intensidade.
Preflight/attempt, imagem/configuração/proveniência, journals, HTTP/RTT, CPU,
computação, PCAP/CSV, certificado e manifesto estão em cada run. comparison.csv e
progress.json registraram a progressão; consolidated.csv/json incluem também A1 e
as métricas adicionais das fontes. finished.json confirma oito execuções concluídas.
Disco livre final: {cleanup['disk']['free']} bytes. Sem limpeza ampla, commit ou push.
'''
(out/'report.md').write_text(report)
print('hash_checks',checks)
print('report',out/'report.md')
