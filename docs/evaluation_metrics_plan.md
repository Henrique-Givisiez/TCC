# Consolidação das métricas de avaliação e proposta mínima

Auditoria de 23/10/2026, checkout `0954e68270339597ec9f4326d3d569cf51954f38`.
Escopo exclusivamente documental e de leitura das evidências. Não houve execução
de campanhas, detectores, calibração ou nova avaliação de TEST. Nenhuma definição,
schema, protocolo, threshold ou resultado anterior foi alterado. Sem commit/push.
Os documentos/testes de CPU que já estavam não rastreados foram preservados.

**Para o orientador:** vamos avaliar três aspectos: capacidade de detectar ataques
com poucos falsos alarmes, impacto no serviço benigno e consumo de recursos.
Nos detectores usaremos recall, FPR, precisão/F1, eventos detectados e atraso,
sempre acompanhados da disponibilidade e dos alarmes pós-evento. No serviço,
duração HTTP, vazão e falhas, separando sucessos de erros. Nos recursos, vítimas,
proxy e host separadamente. Os resumos serão por execução e fase, com dispersão
entre seeds e comparações pareadas; as janelas não serão tratadas como repetições
independentes. Parte da análise de serviço e recursos ainda precisa ser definida
ou implementada antes do estresse, sem modificar a avaliação congelada.

## 1. Autoridade, caminhos e evidências conferidas

Foram lidos README, contratos de [dataset](dataset.md),
[features](feature_timeseries.md), [ground truth](ground_truth.md),
[proxy](http_proxy.md), [sources](container_sources.md),
[avaliação pré-TEST](stage14_test_evaluation_protocol_v1.md),
[15B](stage15b_frozen_test_evaluation.md),
[15C](stage15c_descriptive_analysis.md) e as auditorias de
[HTTP](http_timing_audit.md), [CPU](cpu_accounting_audit.md),
[proxy](proxy_observability.md) e [CUSUM](cusum_persistence_audit.md).
Não foi encontrado AGENTS.md no repositório nem na cadeia de diretórios pais.
A autoridade científica é o contrato machine-readable e seus vínculos por hash,
não um default antigo nem a descrição histórica de uma etapa ainda futura.

| Referência efetivamente localizada | Identidade SHA256 | Situação/papel |
|---|---|---|
| `experiments/protocols/stage14_test_evaluation_protocol_v1.json` | `c2e1ab6314ab67c984b6b0e8f505982d72ea4de2f463e8607488e73c2764ef20` | Contrato pré-TEST congelado |
| `experiment_results/stage15a-test-scoring-20261019/stage15a_scoring_manifest.json` | `089a25681dd13810a94a92def805aa9a7e314955ebdcca671d625d959ae3a9d5` | FROZEN; scores/decisões existentes |
| `experiment_results/stage15b-test-evaluation-20261019/stage15b_evaluation_manifest.json` | `2b36134d60f9dd5a4dc5bd721f4c5df194cc8ad695ab5d71c73156b5bb5863ca` | FROZEN; métricas oficiais existentes |
| `experiment_results/stage15c-descriptive-analysis-20261019/stage15c_analysis_manifest.json` | `8cf1340484b89378996d3b29b485e186f2a82074809c025c3ca645be4ce44f9a` | DELIVERED_FOR_SCIENTIFIC_REVIEW, `not_frozen=true`; análise descritiva já entregue |

Os manifests conduzem ao inventário
`experiment_results/stage14d-test-campaign-20261019/test_collection_inventory.json`
(hash `10ab05b24e9896d41e944192909f79b366e8cbbe7e08eb24f695b5d2ad1c2b47`),
aos freezes de coleta/calibração e às saídas relativas de cada etapa. Há 48 runs,
16 seeds pareadas B/C/P, 20 configurações método/feature, uma vítima por run e
sem autoscaling. Horizonte planejado 144 s, ataque nominal [48,84), endpoint
`/medium`; no contínuo, uma fonte atacante a 8 RPS nominais, quatro fontes benignas
a 2 RPS cada. Isso contextualiza a evidência, não define o próximo estresse.
O campo legado work_units não define o custo de `/medium`: esse endpoint usa a
operação fixa documentada. P e C diferem também no duty cycle/volume médio.

Apenas identidade, tamanho, cabeçalhos e cardinalidade foram verificados:
**1.355 arquivos distintos, 23 CSVs publicados e 48 runs**. Foram conferidas todas
as saídas enumeradas dos três manifests e, por run, effective_config, run_status,
request_log, rtt_log, simulation_metrics, attack_events e proxy_access.log, pelos
hashes do inventário. Não foi executada qualquer função de avaliação/reprodução.
Nenhum dos 48 runs referencia monitor_samples.jsonl: a instrumentação recente do
proxy existe no checkout/smokes técnicos, não nessa campanha congelada.

Evidência detalhada e verificador somente de leitura em
[`experiment_results/evaluation-metrics-consolidation-20261023`](../experiment_results/evaluation-metrics-consolidation-20261023/).
A verificação não afirma ter revalidado todos os artefatos intermediários de todos
os runs; o arquivo evidence.json lista exatamente o conjunto conferido.

## 2. Avaliação de detectores já implementada e publicada

Responsável oficial: [stage15b_evaluation.py](../experiments/stage15b_evaluation.py),
funções `window_metrics`, `ratios`, `event_metrics`, `post_event_metrics`, `aggregate`
e `describe`. O framework genérico
[analysis/detection/evaluation](../analysis/detection/evaluation/__init__.py)
é uma interface com callbacks; o dataclass WindowResult não é uma implementação
alternativa de métricas. `events.evaluate_events` suporta políticas versionadas:
a política V2 fixada no protocolo é a vigente nesta campanha; a V1 legada tinha
limite de disponibilidade até actual_end e não deve substituí-la.

Seja W=[a,b) uma janela de 1 s, D sua decisão em {positivo, negativo, null},
O=|W∩E|/|W| e E=[actual_start,actual_end) o evento global. Só entram janelas
inteiramente em [48,144) na análise primária. O=0 é benigno, O=1 é ataque;
0<O<1 é boundary e fica fora da matriz binária. D=null fica fora dos denominadores.
Os estados/decisões foram construídos desde t=0, sem reset em t=48. [0,48) tem
somente diagnóstico de startup, separado da avaliação primária.

| Métrica existente | Definição, numerador/denominador e unidade | População e casos especiais | Saída 15B / função |
|---|---|---|---|
| TP, FN | Contagem de janelas puras de ataque com D positivo/negativo | Somente decisões disponíveis no horizonte; não são números de ataques | window_metrics_per_run.csv / window_metrics |
| FP, TN | Contagem de janelas puras benignas com D positivo/negativo | Inclui benignas após o evento; B inteiro é benigno | Mesmo arquivo/função |
| Sensibilidade/recall | TP/(TP+FN), razão [0,1] por run/configuração | Denominador: janelas de ataque disponíveis; zero denominador → null. Em B, recall null | Mesmo arquivo / ratios |
| FPR | FP/(FP+TN), razão por run/configuração | Denominador: janelas benignas disponíveis; zero → null. Em C/P não equivale necessariamente à taxa apenas POST | Mesmo arquivo / ratios |
| Precisão | TP/(TP+FP), razão por run/configuração | Denominador: predições positivas em janelas puras disponíveis; zero → null | Mesmo arquivo / ratios |
| F1 | 2TP/(2TP+FP+FN), razão por run/configuração | Zero denominador → null. Pode ser zero mesmo com precisão ou recall indefinidos; não se substitui null por zero | Mesmo arquivo / ratios |
| Suporte/disponibilidade | candidate_decisions, valid_decisions, unavailable_decision_count e desagregações por GT | Contagens por run; valid inclui boundary disponível. Não confundir valid com suporte da matriz | Mesmo arquivo / window_metrics |
| Fronteiras | boundary_excluded_count; attack_windows/benign_windows originais; eligible_attack/benign_windows disponíveis | Boundary unavailable aparece no contador de boundary e no de unavailable; não somar ambos sem retirar a interseção | Mesmo arquivo/função |
| Evento detectado | Indicador de existir D positivo com W∩E de duração positiva e W primária | Um evento global por run C/P, inclusive silêncios de P; alarmes repetidos não criam novos ataques | event_metrics_per_run.csv / event_metrics |
| Taxa de eventos detectados | events_detected/events_total por cenário/configuração; 16 eventos | Misses permanecem no denominador; B não recebe evento fictício | event_descriptive_summary.csv / aggregate |
| Instante e atraso de detecção | t_det=min(available_at elegível); atraso=t_det−actual_start, segundos | Só detectados têm atraso; misses null. Pode haver decisão disponível depois de actual_end se sua observação intersecta E; não usa drained_end | event_metrics_per_run.csv / event_metrics |
| Alarmes pós-evento | positivos disponíveis / decisões disponíveis em janelas inteiras de [max(actual_end,48),144) | Razão por run; candidatos, positivos e unavailable registrados; denominador zero → null | post_event_metrics_per_run.csv / post_event_metrics |
| Pooled suplementar | Somar TP/FP/TN/FN entre runs, depois aplicar as razões acima | C/P/B separados; ponderação implícita pelo suporte, não média entre seeds | window_metrics_pooled.csv / aggregate |
| Resumos entre runs | Média, mediana, SD amostral, mínimo/máximo de métricas definidas | Unidade run/seed; n definido/undefined e seeds explícitos; SD null se n<2, todos null se n=0 | run_level_descriptive_summary.csv, startup_descriptive_summary.csv / summaries, describe |

Reconciliação do suporte: candidatos = elegíveis ataque + elegíveis benignas +
boundary total + unavailable ataque + unavailable benignas. A matriz soma somente
os dois primeiros. Uma **proposta nova**, ainda não publicada como razão, é
mostrar disponibilidade bruta valid/candidates e disponibilidade nas janelas puras
(eligible_attack+eligible_benign)/(attack_windows+benign_windows), com denominador
zero → null e também contagens; não chamar nenhuma delas de disponibilidade do serviço.

Disponibilidade temporal do detector é causal/simulada, normalmente no fechamento
da janela, não latência computacional medida do algoritmo. Não há benchmark de
custo/tempo de processamento dos detectores. Acurácia não integra as métricas
primárias publicadas e não será síntese isolada: pode ocultar misses em populações
desbalanceadas. Não se propõe ranking composto de métodos/features.

Alpha=0,01 é alvo nominal de janelas benignas na **calibração**. Em
[empirical.py](../analysis/detection/empirical.py), `quantile_index`/política upper-tail,
o limiar é o quantil empírico higher de índice ceil((N−1)(1−alpha)), comparação
estrita score>limiar, empates negativos. Dados finitos, empates, dependência temporal,
estado dos detectores e mudanças de distribuição impedem concluir FPR_TEST=alpha.
Alpha também não é probabilidade de pelo menos um alarme em uma execução.
Não haverá ajuste de limiar usando o TEST já examinado.

### O que a análise descritiva 15C já acrescenta

Em [stage15c_analysis.py](../experiments/stage15c_analysis.py):

| Medida já entregue | Fórmula/população/unidade | Limites e saídas em `tables/` |
|---|---|---|
| Quartis das métricas por seed | Q(p) por interpolação linear type 7, h=(n−1)p, valores definidos; Q1/Q3, mediana, média e SD | Não são ICs; n<2 torna SD null. primary_descriptive.csv, startup_descriptive.csv, post_event_descriptive.csv; describe/quantile/summarize |
| Distribuição dos delays e eventos | Mesmo indicador/rate 15B; quartis/estatísticas dos delays definidos | Misses explícitos, não atrasos zero; event_descriptive.csv / build_tables |
| Contrastes pareados P−C | m_P,s−m_C,s para recall, F1, FPR e taxa pós-evento; apenas pares definidos | Seeds incluídas/excluídas explícitas; paired_p_minus_c.csv, paired_descriptive.csv / paired_results |
| Contraste de delay P−C | delay_P,s−delay_C,s apenas se ambos detectados | Seleção condicional; não comparar como resultado de todos os eventos; paired_delay_detected_both.csv |
| Resíduo observacional POST vs B | Média das observações definidas POST menos média B nas mesmas janelas; por run/feature | Denominadores próprios post_observed_n e matched_B_observed_n, podem diferir com ausências; diferença null se uma média ausente; não é necessariamente média de diferenças em pares completos. persistence_per_run.csv / persistence |
| Score e decisão na cauda | Primeiro/último score disponível, mínimo/máximo entre scores POST definidos; última decisão/observação primárias; contagens de runs positivos/unavailable ao fim | Extremos não são tempos de recuperação. Score ausente não vira zero; última decisão pode ser null. persistence_per_run.csv, persistence_mechanism_summary.csv |
| Positivos com observação ≤ média baseline | Contagem entre positivos POST com observação definida que satisfaz x≤mu; resumo suplementar low/pos | O denominador implementado pos é todos os positivos, não somente os com x definido; há contagem separada de positivos com observação. pos=0 → null. Diagnóstico de memória, não causalidade; persistence/persistence_mechanism_summary.csv |
| Série ilustrativa | Observações/scores/decisões já armazenados, seed mínima elegível 171864802 | temporal_example.csv; exemplo não representa distribuição de seeds nem nova avaliação |

Estes diagnósticos não medem formalmente **tempo de recuperação**. Alarme POST pode
refletir memória acumulada, observações ainda elevadas ou ambas; tampouco prova
que o serviço continua degradado. O acompanhamento finito pode terminar com alarme.
Uma futura recuperação precisa de definição prévia distinta para detector e
serviço: por exemplo, permanência por q janelas válidas abaixo de critério
pré-especificado, com q/critério/horizonte definidos fora do TEST atual. Ausências
não satisfazem permanência nem autorizam conectar períodos; registrar lacunas.
Registrar recuperado, não recuperado até T ou indeterminado por falta de suporte,
com último acompanhamento válido. Não impor reset, teto ou vazamento para melhorar
curvas; isso criaria outro detector.

## 3. Serviço benigno: observações existentes e análises propostas

Autoridade de classe: `traffic_class=benign`, inclusive durante o ataque.
Não selecionar benignos por attack_active=false. Há tentativas benignas em C/P.
Fonte canônica: request_log global reconciliado, identificado por run_id/request_id;
logs locais/journals servem de evidência e não devem duplicar a população.

| Medida atual | Relógio, limites, população e unidade | Uso recomendado |
|---|---|---|
| request_log.duration_ms | 1000·(end_elapsed−elapsed), monotônico do experimento; do begin no cliente até corpo completo ou exceção; inclui journal síncrono após o timestamp inicial, exclui espera no executor anterior ao begin e persistência posterior ao fim | Base para novas análises estratificadas; preservar o nome/contrato histórico e declarar esses limites |
| rtt_log.rtt | Mesmo duration_ms, somente outcome=response; atribuição temporal pela conclusão; inclui ambas as classes | Duração HTTP no cliente, não RTT TCP. Filtrar benign; não contém HTTP≥400, transporte ou incompletas |
| simulation_metrics.avg_rtt_ms | Duração do gerador, início depois de begin/logging e fim monotônico distinto; inclui retornos HTTP de erro, exclui exceções | No fluxo sources, média das amostras novas ingeridas no tick, escolhendo ataque no intervalo nominal e benign fora; outra classe descartada, vazio vira 0. Não é série contínua de latência benigna nem mean_duration_ms |
| Stage10 mean_duration_ms | Média de duration_ms de TODAS as conclusões na janela, ambas classes e sucessos/falhas; janela por end_elapsed | Ausente sem conclusões; feature histórica permanece assim. Não usar como percentil ou latência benigna de sucesso |
| Stage10 starts/completions/failures | Contagens por elapsed inicial / end_elapsed; failures soma http_error, transport_error, client_error | São contagens por janela, não automaticamente taxas; dividir pela duração coberta explicitamente. Incomplete conta início, não conclusão/falha inventada |
| NGINX request_time/upstream_time/connect_time | Segundos; timestamp epoch msec no fechamento do log; limites do servidor, distintos do relógio/limites do cliente | Evidência complementar por request_id/status/upstream; excluir setup/capture_audit/monitoring. Campo ausente ou '-' não é zero. Não chamar request_time−upstream_time de latência pura do proxy |

Responsáveis: [RequestLogger.begin/finish/finalize](../simulator/request_logger.py),
`source_aggregate.aggregate`, `source_experiment.run`, geradores e
[extract_features.extract_features](../experiments/extract_features.py), linhas
226–251. A auditoria HTTP detalha conexão/reutilização, corpo, journals e publicação.
NGINX request_time vai dos primeiros bytes recebidos até o envio final registrado;
não comprova chegada do corpo ao cliente. Servidor, proxy e início no cliente são
eventos diferentes; request_starts não mede taxa de transmissão ou recebimento.

**Nova análise proposta, não executada aqui:** para run r e fase F de duração T_F,
definir C_F={tentativas benignas com início em F}. População principal de duração:
S_F⊆C_F com outcome=response, status 2xx e corpo completamente recebido. Para
cada uma, d_j=duration_ms; média=sum(d_j)/|S_F|, mediana Q(.5), p95=Q(.95),
p99=Q(.99). Quantis type 7 explicitamente; população vazia → null, publicar n,
fração de cobertura e número censurado/incompleto. Com n pequeno, p99 tem pouco
suporte e não deve ser anunciado como cauda estável. A escolha 2xx é proposta
operacional nova; response histórico também pode incluir 3xx não seguido. Mostrar
3xx separadamente e nunca excluir silenciosamente resultados inesperados.

HTTP 4xx e 5xx: número e proporção entre respostas HTTP com status conhecido,
mais proporção entre todas as tentativas do coorte para não esconder falhas de
transporte; informar ambos os denominadores. Duração dessas respostas é resumo
separado, não parte de S_F. Transporte/client_error: contagem e fração em C_F,
com duração até falha em população própria. Timeout: subclassificação por error_type
explicitamente reconhecido (Timeout/ConnectTimeout/ReadTimeout), mantendo demais
erros de transporte; encapsulamentos em ConnectionError podem impedir reconhecer
todos os timeouts. Não inferir timeout sem evidência nem rotular transporte como
perda de pacote. Incomplete: |{C_F sem conclusão observada}|/|C_F|, com motivo de
encerramento quando disponível; não imputar duração/falha ou sucesso.
As categorias de outcome do coorte devem reconciliar seu total, mesmo com nulls.

Vazões complementares por eventos temporais distintos:

- Inícios/s = número de begins benignos em F / T_F.
- Conclusões/s = número de términos benignos conhecidos em F / T_F, incluindo
  falhas; discriminar respostas recebidas, sucessos 2xx, erros HTTP e transporte.
- Sucessos/s = número de respostas benignas 2xx concluídas em F / T_F.

São análises novas deriváveis dos logs, não valores já publicados pela 15B.
T_F deve ser tempo observado com cobertura atestada; sem cobertura não declarar
zero tráfego. A grade preenchida da Stage10, sobretudo cauda/padding, não garante
cobertura. Uma contagem zero é defensável apenas com emissão/coleta íntegra naquela
exposição. Se T_F≤0 ou exposição desconhecida, taxa null. Taxa configurada é
parâmetro do gerador e deve aparecer ao lado da taxa iniciada, não substituí-la.

## 4. Recursos e infraestrutura

As definições detalhadas estão nas auditorias referenciadas; os seguintes pontos
são necessários para interpretar a avaliação, sem normalizar ou corrigir a história.

| Medida | Fórmula, unidade e população atuais | Disponibilidade, limites e proposta |
|---|---|---|
| CPU de cada vítima | p=100·ΔU/ΔS·n, U=cpu_usage.total_usage, S=system_cpu_usage, n=online_cpus ou len(percpu) ou 1; deltas cpu_stats−precpu_stats do payload Docker | StatsCollector._calc_cpu_percent; ≈100% por núcleo lógico equivalente, pode superar100. Deltas não positivos viram0 histórico; primeira chamada pode já ter par Docker válido. Sem quota/capacidade garantida definida |
| Média exibida/CSV vítimas | soma de TODAS as amostras recentes dos IDs ativos / número dessas amostras; na falta de recentes usa última cache por vítima | get_averages(window_seconds); janela por ingestão monotônica, limite esquerdo inclusivo. Cache pode ser antigo, sem expiração; erros conservam cache. Amostras em quantidades diferentes dão pesos diferentes às vítimas. CSV arredonda2 casas |
| Feature CPU | mean_cpu_percent=sum(average_cpu_percent dos ticks suportados em W)/n_ticks | extract_features; W decimal [a,b), timestamp do tick; nomes vazios excluídos, sem ticks suportados → null. Não reconstrói frescor/intervalo Docker nem média temporal exata |
| Memória vítimas | max(memory_stats.usage−stats.cache,0)/2^20, MiB, depois mesma média de amostras/ticks | Não é RSS garantido; cache v1 pode faltar em cgroupv2. Ausência de campos pode virar0 no coletor histórico. Nome mem_usage não significa bytes |
| CPU host | 100·(1−Δ(idle+iowait)/Δtotal), /proc/stat agregado; primeira chamada/erro retorna0 | host_stats.get_host_cpu_percent; escala do host inteiro, não igual à escala Docker. Soma atual inclui guest já contabilizado em user/nice: defeito aritmético condicional documentado, impacto histórico não demonstrável sem contadores brutos |
| CPU proxy | Mesma convenção Docker, deltas entre snapshots próprios sucessivos, primeira CPU null; fonte Docker com timestamp/intervalo próprios | ProxyMonitor/resources; novo proxy_artifacts/monitor_samples.jsonl, separado. Inválidos/reset/stale/erros explícitos, sem cache velho como novo. Não existe nos48 TEST |
| Memória proxy | memory_stats.usage em bytes, incluindo cache | Não equiparar à memória histórica descontada das vítimas; erro/ausência null |
| NGINX gauges | active_connections, reading, writing, waiting: conexões em cada estado | Waiting é ocioso keepalive, não fila HTTP. active inclui waiting. Fonte status distinta de Docker, timestamps próprios |
| NGINX counters | accepted_connections_total, handled_connections_total, requests_total, acumulados desde início | Deltas válidos/tempo observado permitem taxas novas; reset/primeira leitura ausente. accepted−handled pode indicar limite de recursos, não fornece taxa de erros HTTP nem causa isolada |
| Rede proxy | RX/TX bytes acumulados por interface, taxas Δbytes/Δt observado | Preservar rede/interface; somar entrada/backend duplica percurso. Não é volume único dos clientes nem medição de perda |

Só vítimas entram na média/feature de CPU e nos detectores atuais; proxy, fontes
e host permanecem separados. Coleta das vítimas é sequencial: cada chamada Docker
pode esperar frames e o loop ainda dorme poll_interval; 1 s configurado não garante
1 Hz por vítima. Instantes do tick não são instantes de aquisição simultânea.
Falha sem cache reduz o suporte; todos ausentes retornam zeros e nomes vazios,
excluídos pela Stage10. Cache com nome preservado pode ocultar ausência real.

No proxy, o ciclo executa status via Docker exec wget antes de docker stats;
ambos NGINX e wget pertencem ao cgroup do proxy. A CPU por delta entre snapshots
pode incluir consultas deste e de ciclos anteriores: ordem sequencial das chamadas
não elimina sobreposição do intervalo de CPU com a consulta. O contador global
NGINX também inclui monitoramento. Separar consultas tentadas no resumo das
atendidas efetivamente no access log. Guardar duração/erro/delay/slots pulados.
Nos gráficos, cada fonte usa seus timestamps; CPU por delta é intervalo entre os
reads Docker, desenhado no fim desse intervalo com seus limites declarados;
memória é ponto. Não ligar observações por cima de nulls/falhas.

**Consumo observado** é tempo de CPU/memória/conexões contabilizados. **Saturação**
requer evidência conjunta de limite/pressão e perda de capacidade de atender carga
(vazão em platô, demora/falhas, concorrência, limite efetivo conhecido); CPU alta ou
waiting alto isolados não bastam. **Overhead causal** de monitoramento/proxy exige
experimento controlado com comparador, mesma carga/capacidade e versão: não se
obtém subtraindo tempos NGINX nem comparando consumo bruto entre componentes.
CPU host inclui recursos compartilhados com sources, Docker e demais processos;
ela sozinha não identifica o competidor nem separa contenção do gerador.

### Múltiplas vítimas: proposta, ainda não implementada

Em intervalos comuns e válidos, r_i=ΔU_i/Δt em CPU-s/s (núcleos equivalentes):
individual r_i; total R=sum_i r_i; média por vítima R/N; trabalho total=sum_i ΔU_i
em CPU-s. Distribuição: min/max e CV espacial=SD populacional(r_i)/média(r_i), null
se média zero/sem suporte; publicar N esperado/observado. Não confundir esse CV
entre vítimas com o detector temporal CoV. Comparar coortes de vítimas fixos ou
registrar explicitamente entrada/saída/reinício.

Agregação exige cobertura dos mesmos intervalos: integrar consumo com pesos de
tempo, sem sobrepor deltas nem supor valor constante nas lacunas. Intervalos
parcialmente sobrepostos só podem ser repartidos sob hipótese explícita de taxa
constante; preferir contadores alinhados. Capacidade c_i, se verificável, permitiria
u_i=100r_i/c_i e U=100sum(r_i)/sum(c_i); sem c_i defensável, não calcular utilização
normalizada. Quota é teto, shares prioridade relativa, pool2 não são2 CPUs dedicadas.
O host compartilhado não ganha capacidade física por adicionar containers.

Exemplo: uma vítima consome200%=2núcleos equivalentes; duas em100% cada mantêm
total200%, enquanto a média cai a100%. Isso não demonstra redução da demanda ou
benefício de autoscaling. A média simples é adequada para consumo típico por
vítima com suporte simultâneo e pesos iguais; utilização de orçamentos diferentes
requer pesos por capacidade, integração temporal requer pesos por duração.
A campanha com uma vítima não valida experimentalmente essas medidas multivítima.
Ver [proposta específica](multi_victim_cpu_proposal.md).

Há ainda `cost_calculator.calculate_total_cost_from_intervals`: sum(N_tick·Δconfig/3600·preço)
em moeda fictícia. No fluxo sources soma ticks de intervalo configurado, não lifetime
real auditado nem drenagem; não inclui CPU, proxy/fontes ou faturamento cloud.
Existe como saída operacional impressa, não como métrica científica da15B/15C;
não usá-la para afirmar dano econômico EDoS.

## 5. Fases, fronteiras e requisições que atravessam fases

Proposta operacional para **novos resumos**: PRE=[0,actual_start),
ATIVO=[actual_start,actual_end), POST=[actual_end,T_acompanhamento), usando elapsed
monotônico comum homologado pelo clock audit. Guardar também plano nominal
[48,84), emissão efetiva e drained_end, sem substituir o GT. B não tem evento:
para contraste por seed, aplicar nele os mesmos intervalos elapsed do cenário
atacado pareado, identificados como intervalos de comparação, sem inventar evento B.
C e P podem ter marcos efetivos diferentes, portanto cada contraste com B deve
usar seus próprios limites e suporte comum declarado.

Esse PRE operacional inclui startup! Na avaliação primária histórica [48,144),
o PRE elegível é apenas [48,actual_start), frequentemente sem janela inteira;
resumo vazio é null, não evidência de baseline estável. [0,48) continua diagnóstico,
não se promove a baseline de fitting ou à avaliação primária. Para novos estresses,
planejar warmup e PRE útil separadamente antes de coletar, sem reclassificar o TEST.

| Atribuição proposta | Evento temporal e regra | Travessias e limitações |
|---|---|---|
| Coorte de duração/falhas/incompletas | Pelo begin em [a,b) | Uma requisição iniciada PRE e concluída ATIVO permanece no coorte PRE; duração inteira, com flag de travessia e término preservado. Isso descreve experiência do coorte, não custo exclusivamente consumido PRE |
| Taxa iniciada | Begin em [a,b) | Conclusão tardia nunca é novo início |
| Taxa concluída/sucesso | End em [a,b) | Pode vir de coorte anterior; mostrar cruzamento início→fim e pendentes ao fim, sem exigir igualdade entre starts e ends dentro de cada fase |
| CPU/recursos | Intervalos de aquisição/delta próprios | Não atribuir o intervalo inteiro à fase só porque seu tick está nela sem declarar essa aproximação; histórico permanece por tick |
| Detectores oficiais | Janelas inteiras, overlap puro e política15B | Não fracionar contagens TP/FP nem mudar fronteiras para adequar fases novas |

No contínuo, o fim nominal interrompe admissões; tarefas já enfileiradas podem
começar depois. actual_end certifica emissão encerrada no sentido do protocolo
(admissão fechada e nenhuma admitida aguardando begin), não um timestamp do último
byte transmitido. Tentativas em voo podem terminar depois; drained_end é última
conclusão observada e pode até preceder a certificação. Encerramento operacional
de sources/monitoramento é outro marco. Não supor ordered drain>actual_end em todos
os runs, não usar drenagem para relabeling histórico e não igualar fim de emissão
a recuperação do serviço/detector.

Manter janelas boundary excluídas da matriz. Para novas tabelas de serviço por
fase, preferir tempos individuais [a,b), sem alocar uma média de janela parcial
inteiramente à fase. Exibir número de travessias, tempo observado e limite de
acompanhamento. Se houver truncamento/corte, registrar censura; requests sem fim
não ganham duração zero nem percentil imputado. Cauda além de144 é evidência
operacional potencial para análise nova separada, não extensão retroativa da15B.

## 6. Variabilidade e leitura entre execuções

O desenho existente usa seed/run, com16 triplas pareadas. A15B descreve métricas
por run e publica pooled suplementar; a15C acrescenta quartis e contrastes P−C,
sem bootstrap, IC, p-valores ou ranking. Mantê-los com esse status descritivo.
Não executar novamente esses módulos para produzir este relatório.

Para os próximos experimentos, produzir uma linha run×fase×classe×população,
com contagens, exposição, suporte e métrica. Depois, por condição/fase, mostrar os
pontos por seed, média e SD amostral s=sqrt(sum((x−média)^2)/(n−1)), mediana e
IQR=Q3−Q1, n definido/total, mínimo/máximo quando útil. O IQR como diferença é
proposta de apresentação; a15C já publica Q1/Q3. Ausências não viram zero e não
se omitem as seeds sem suporte. Não usar cada janela correlacionada como réplica.

Comparar ataque−B por seed nas mesmas exposições e populações; reportar diferença
absoluta (ms, req/s, CPU-s/s, pontos percentuais quando multiplicado por100) antes
de razões. Razões exigem B≠0 e suporte válido; caso contrário null com motivo.
P−C existente compara também volume/duty cycle distintos, não efeito causal puro
da periodicidade. Uma execução ilustrativa não substitui essa distribuição.

Exemplo puramente aritmético de pesos, não resultado TEST: runs com1/10 e9/90
resultam média de taxas0,1 e pooled10/100=0,1; se forem1/10 e1/100, média=0,055,
pooled2/110≈0,0182. A média igual por run responde à execução típica; pooled pesa
pela exposição/denominador. Identificar ambos se publicados, sem tratá-los como
intercambiáveis. Nos detectores, mesma distinção para média de FPR e FP total/
benignas totais, ou média de recall e TP total/ataque total.

Não calcular percentil global como média dos p95/p99 por run. Reportar distribuição
dos percentis por execução; um percentil de todas as requisições agrupadas é outra
estatística, ponderada pela quantidade de requisições, que exige voltar à população
individual e declarar esse objetivo. Não fazer esse agrupamento no TEST nesta etapa.

Delays: mostrar taxa detectada e misses ao lado da distribuição condicional dos
delays; os pares detectados em ambos podem ser uma subpopulação selecionada.
Recuperação futura: mostrar recuperados, não recuperados até o horizonte e casos
indeterminados; não substituir estes por zero ou pelo fim do acompanhamento como
se fosse recuperação observada. Não propomos ICs/testes inferenciais agora:
o prazo e o desenho sustentam primeiro esses resumos descritivos explícitos.

## 7. Mapa de perguntas, fontes e situação

“Existente” significa que o valor/observação já existe; a coluna distingue o
resumo publicado de uma série bruta. “Derivável” exige nova análise versionada e
não foi calculado nesta entrega, especialmente sobre TEST.

| Pergunta experimental | Métrica principal | Complementares | Fonte | Situação |
|---|---|---|---|---|
| Detecta janelas sob ataque? | Recall por run | Precisão/F1, TP/FN, suporte/boundary |15B window_metrics_per_run|Existente, publicado/congelado |
| Falsos alarmes em benigno? | FPR B por run | FP/TN, FPR C/P, disponibilidade |15B;15C distribuição|Existente; não confundir com alpha nominal |
| Detecta cada ataque e com que atraso? | Proporção eventos detectados + delay dos detectados | Misses, instante de disponibilidade |15B event_*;15C event_descriptive|Existente; um evento global por C/P |
| Persiste depois do evento? | Taxa de alarmes POST | Scores/observações residuais e último alarme |15B post_event_*;15C persistence_*|Existente; tempo de recuperação não implementado |
| Quanto tempo até recuperar? | Tempo com critério sustentado prévio | Censura/indeterminação e suporte |Decisões e serviço observados|Definição futura + nova análise; acompanhamento adicional pode ser necessário |
| Benignos recebem resposta útil? | Sucessos2xx/s + duração benigna2xx p95/mediana | Média/p99/n, erros e incompletas |request_log|Derivável em análise nova; limites HTTP legados declarados |
| Qual carga efetivamente começou/terminou? | Starts/s e conclusões/s benignos | Taxa nominal, travessias, pendentes |request_log + config; Stage10 contagens mistas|Contagens existentes; estratificação por fase/classe e taxas são novas |
| Como falha o serviço? | HTTP4xx/5xx, transporte, timeouts explícitos | Client_error e incompletas; denominadores |request_log outcome/status/error_type|Derivável; classificação completa de timeouts pode exigir instrumentação |
| Quanto consomem as vítimas? | CPU histórica + memória, com ressalva de suporte | Host, N, frescor |simulation_metrics/Stage10|Existente; correção do frescor exige instrumentação futura |
| Onde está o gargalo do proxy? | CPU/memória próprias + vazão/erros/tempos | active/reading/writing/waiting, contadores válidos, NICs |proxy_artifacts/monitor_* e access log|Coleta implementada no checkout/smokes, ausente na campanha TEST; resumo por fase novo |
| Múltiplas vítimas distribuem carga? | Individual e total CPU-s/s | Média por vítima, min/max/CV espacial |Contadores e intervalos individuais alinhados|Dependente de nova instrumentação/contrato; não inferir de média agregada antiga |
| Há contenção no host? | CPU host junto à vazão/qualidade e recursos componentes | Pressão/throttling conforme hipótese |host_stats, vítimas/proxy; dados extras se necessários|CPU host existente com ressalvas; atribuição causal/pressão específica não implementadas |
| Há perda de pacotes? | Métrica de perdas com pontos/denominador definidos | Qualidade da captura, retransmissões separadas |Instrumentação específica de rede|Não medida por timeout/erro; fora do mínimo salvo hipótese explícita |
| Qual overhead causal? | Contraste controlado com/sem componente/coleta | CPU, serviço, carga efetiva e host |Novo desenho experimental|Não identificado pelos resultados atuais |

## 8. Plano mínimo para o futuro estresse e prioridades

Este documento propõe trabalho futuro; não altera/libera o protocolo atual.
Antes de coletar, fixar versões, unidades, populações e fases em contrato novo,
com configuração efetiva, limites/host, seed e identidades. Preservar colunas/modelos
históricos; eventual correção de CPU/HTTP terá série/versão distinta e não alimentará
thresholds antigos sem nova avaliação independente. Não transferir comparabilidade
entre definições apenas porque a unidade ou nome parece o mesmo.

1. **Prioridade imediata: CPU confiável e duração explícita.** Definir registro
   individual de CPU com read/precpu, intervalo, idade, erro e geração do container;
   não aceitar cache antigo como fresco. Especificar tratamento de primeira leitura,
   reset e host guest accounting em versão futura. Para duração, decidir se o
   primeiro estudo usará duration_ms legado com ressalva do journal (mínimo viável)
   ou novo timer junto à chamada HTTP; este muda comparabilidade e não recupera
   retroativamente o tempo de fila/transmissão. Não chamar avg_rtt_ms de QoS benigno.
2. **Prioridade imediata: análise offline mínima de serviço.** Implementar depois,
   fora dos datasets congelados, resumo por run/fase de benignos: starts/s,
   sucessos/s, mediana/p95 e média2xx, n, HTTP erros, transporte/timeouts identificáveis
   e incompletas. p99 é complementar quando houver suporte. Reconciliar contagens,
   travessias e cobertura com testes sintéticos; zero sem cobertura é inválido.
3. **Prioridade antes de coletar: desenho/recuperação.** Definir warmup/PRE útil,
   ATIVO/POST, duração de acompanhamento, pareamento B, fronteiras e critério de
   recuperação se ele for pergunta principal. Fixar sementes e ordem balanceada
   de condições para reduzir deriva; não selecionar parâmetros pelo desempenho
   dos detectores no TEST conhecido. Escolher quantidade de execuções conforme
   orçamento e variabilidade de caracterização independente, sem inventar poder.
4. **Prioridade operacional: aproveitar o proxy existente.** Guardar monitoramento
   separado e sua qualidade, verificar IDs e logs reais, separar sondagens; plotar
   CPU/memória/conexões e vazão/latência benigna com fases. Não exigir novo mecanismo
   de coleta agora. Autoscaling desligado e upstreams estáticos em cada bloco.
5. **Antes do bloco multivítima:** acrescentar consumo individual/total e dispersão
   com suporte alinhado e limites documentados. N permanece fixo dentro de cada
   curva inicial. Pool de processos, quota, cpuset e host são fatores distintos.
6. **Condicional, não obrigatório para o prazo:** perdas de rede, pressão detalhada
   e overhead causal só se a hipótese exigir. Não há perda específica medida hoje;
   resolvê-la requer definição/instrumentação própria antes de alegá-la, não renomear
   falhas HTTP. Se adiada, declarar a lacuna e limitar a conclusão a serviço HTTP.

Primeiro bloco: variar apenas **RPS**, fixando endpoint/custo, N, concorrência,
fontes, timeout, limites e demais políticas. Usar os RPS nominais e realizados;
se houver ataque, variar a carga atacante com benignos fixos. O benigno pareado
retira o ataque e mantém a carga benigna; se o objetivo for capacidade sem ataque,
o controle usa a mesma condição-base declarada. Registrar a dimensão de RPS que
está sendo variada para não confundir carga total, por fonte ou atendida.

Segundo bloco separado: variar apenas **custo computacional do endpoint**, com
RPS nominal por classe/fonte, N e demais controles fixos. Os endpoints existentes
podem definir níveis de custo se seus trabalhos forem declarados; não pressupor
que RPS iniciado permanecerá igual sob custo maior: filas/concorrência podem mudar
esse resultado. Usar parametrização disponível sem mudar geradores para este plano.

Nos dois blocos, mostrar curva carga/custo → sucessos/s e p95/falhas benignas,
CPU vítimas (individual/total quando disponível), proxy e host. Isso ajuda a
localizar limitação nas vítimas, no proxy ou no host; não prova causa isoladamente.
Capacidade/faixas de carga devem vir de caracterização independente, não de tuning
da avaliação TEST. Não há campanha, stress ou nova execução autorizada por este texto.

## 9. Fontes técnicas e limites da fundamentação

As fórmulas científicas acima vêm do protocolo versionado e do código auditado,
não de uma atribuição genérica à literatura. Complementos consultados:

- [Documentação oficial R, Sample Quantiles, seção Types, type7](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/quantile.html):
  fundamenta a convenção de interpolação, já usada pela15C e proposta explicitamente
  para os novos quantis HTTP. Não recomenda por si só p95/p99 nem uma população.
- [Docker, Resource constraints, CPU / Configure the default CFS scheduler](https://docs.docker.com/engine/containers/resource_constraints/#cpu):
  documenta limites/shares; não oferece garantia de reserva por vítima nesta
  configuração. A fórmula de CPU e os deltas concretos são rastreados na auditoria
  de CPU, inclusive suas fontes Engine/CLI e kernel, e não inferidos deste manual.
- [Almes et al., RFC7680, A One-Way Loss Metric for IPPM, §§2.2–2.6 e3–4](https://www.rfc-editor.org/rfc/rfc7680.html):
  define perda IP por observação de envio/recepção e limite temporal, e estatísticas
  de amostra. Sustenta exigir pontos, população de pacotes e critério de perda;
  não transforma HTTP timeout, retransmissão TCP ou drops do capturador em taxa
  de perda do caminho. Eventual medição terá desenho próprio; não foi implementada.

Não se atribui garantia de isolamento, saturação, causalidade ou validade externa
a essas referências. Não foram adicionados testes estatísticos formais.

## 10. Verificação desta entrega

Comando executado na raiz (somente identidade/inventário):

```bash
python3 -B experiment_results/evaluation-metrics-consolidation-20261023/inspect_published.py
```

Saída:

```text
PASS: 1355 distinct files verified; 23 published CSV schemas/cardinalities; 48 runs located by manifest.
No scores, decisions, evaluation metrics, calibration or runtime executed.
```

Não há alteração de código executável do produto; não foram rodados testes que
executem detectores/evaluators ou reavaliem TEST. A inspeção de integridade não é
nova validação experimental. O relatório e o resumo de proposta são os únicos
arquivos de documentação acrescentados por esta tarefa; script/evidence ficam
na nova pasta de auditoria. Dados congelados permaneceram somente leitura.
