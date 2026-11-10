# Investigação temporal da saturação e recuperação HTTP

Campanha `energy-powersaver-20261109`. Análise offline realizada em 10/11/2026. Escopo: 60 execuções TEST, 20 por cenário, nos 20 blocos do plano congelado. Não foram analisados resultados de detectores, executadas coletas, modificados resultados científicos ou realizados commits.

## 1. Resumo executivo

Os dois mecanismos saturaram os dois workers e acumularam trabalho computacional durante ACTIVE. A3 entregou aproximadamente 8 inícios HTTP ofensivos/s, com 256,8 ms de CPU por operação; F96 entregou 50,4/s, com 31,6 ms/operação. A3 produziu maior espera computacional e recuperação mais demorada nesta configuração, sem estabelecer eficiência intrínseca entre mecanismos.

Uma correção conceitual é necessária: os valores de referência 31,65 e 32,25 correspondem a requisições HTTP legítimas pendentes no cliente, e não ao backlog computacional da vítima. Este último chegou, em média, a 549,4 operações no fim de ACTIVE em A3 e 407,45 em F96.

A degradação foi progressiva. A disponibilidade legítima média caiu de 100% em PRE para 9,24% em A3 e 35,06% em F96 nas janelas programadas. Nos últimos 30 s de ACTIVE foi zero nos dois cenários, nas 20 repetições. Em F96, a concorrência ofensiva atingiu o orçamento de 96 envios: em média, 1.264,4 tentativas expiraram antes do início HTTP, resolvidas somente após a fronteira de 270 s.

Após cessarem os inícios HTTP ofensivos, operações ofensivas terminaram até 19,29–37,73 s depois em A3 e 4,81–12,29 s depois em F96. A fila aguardando ficou vazia pela primeira vez após, em média, 37,70 s e 9,01 s, respectivamente. A correlação por identidade comprova trabalho executado depois do timeout do cliente.

H1, H2 e H3 são sustentadas, nos sentidos delimitados neste relatório. Duas execuções não tiveram recuperação operacional confirmada por crescimento de três pendências HTTP na última janela, embora apresentassem 100% de sucesso legítimo final. Isso não demonstra indisponibilidade persistente.

## 2. Fontes e metodologia de análise

### 2.1 Seleção, preservação e reprodução

A seleção usa exclusivamente `partition=TEST` em [plan.json](../../experiments/protocols/energy-powersaver-20261109/plan.json), sem inferir a partição pelo nome L2. As 20 entradas anteriores de BASELINE/CAL_A/CAL_B não integram esta investigação. Os dados vêm de `experiment_results/scientific-energy-powersaver-20261109/collection/<id>/attempt-1/raw/`; a recuperação registrada vem do recibo da mesma tentativa. Não há exclusão retrospectiva de observações.

O contrato de variáveis foi documentado em [metodologia.md](metodologia.md) antes dos cálculos. [manifesto_entradas.json](manifesto_entradas.json) registra os hashes dos 1.261 arquivos de entrada lidos pelo analisador principal, seleção e versões das bibliotecas. Todos esses hashes foram novamente conferidos sem mudança: [verificacao.json](verificacao.json). A integridade por execução está em [integridade_execucoes.json](integridade_execucoes.json). Os eventos observados têm sequências contíguas e resumos completos, sem perdas ou erros de escrita; os ciclos computacionais usados possuem submissão, início e conclusão. Operações de auditoria sem classe declarada ocorreram antes da origem e foram excluídas explicitamente, sem retirar tráfego TEST identificado.

Reprodução a partir da raiz do repositório, usando o ambiente Python existente:

```bash
.venv/bin/python -B reports/investigacao-temporal-energy-20261110/analisar.py
.venv/bin/python -B reports/investigacao-temporal-energy-20261110/fontes.py
.venv/bin/python -B reports/investigacao-temporal-energy-20261110/complementar.py
.venv/bin/python -B reports/investigacao-temporal-energy-20261110/conferir_referencias.py
.venv/bin/python -B reports/investigacao-temporal-energy-20261110/tabelas_finais.py
.venv/bin/python -B reports/investigacao-temporal-energy-20261110/reproduzir_figuras.py
.venv/bin/python -B reports/investigacao-temporal-energy-20261110/verificar_entrega.py
```

Esses scripts têm saídas limitadas ao próprio diretório de relatório. Não chamam coletores, Docker, geradores, exportadores de datasets ou detectores. A reprodução sobrescreve somente os artefatos derivados deste diretório.

### 2.2 Relógios e fronteiras

O protocolo define WARMUP [0,30), PRE [30,150), ACTIVE [150,270) e POST [270,390), em segundos da execução. WARMUP não entra nos resumos científicos; as séries de auditoria também preservam seus eventos. Nas figuras, o tempo zero equivale a 150 s da execução; o fim programado da emissão equivale a +120 s. L2 recebe as mesmas fronteiras nominais.

Os eventos da vítima e das fontes usam `CLOCK_MONOTONIC`. Subtrai-se `diagnostics/metadata.json:origin_monotonic`; os journals das fontes confirmam exatamente essa origem em `run_binding`. Todos os certificados `victim_clock_validation.json` e `source_artifacts/clock_validation.json` declaram comparabilidade, confirmada nas amostras internas. Não se usa igualdade presumida dos relógios UTC: namespaces podem ser distintos, mas a certificação registra comprovação por offsets nativos zero e/ou namespace compartilhado, além do enquadramento da amostra remota entre leituras do host. Os brackets observados variam aproximadamente entre 85 e 132 ms. Esses brackets são duração da consulta de certificação, não erro aplicado como deslocamento. Fonte: [auditoria_relogios.csv](auditoria_relogios.csv).

A resolução nominal do relógio é de 1 ns; isso não significa exatidão causal de 1 ns entre processos. Os bins de 1 s são sustentados pelos timestamps dos eventos, com a limitação de escalonamento e instrumentação. Não foram arredondados eventos para decidir fronteiras.

**Fronteira programada versus fechamento registrado:** nenhum novo início HTTP ofensivo ocorre em POST. Em F96, entretanto, `actual_end_seconds` varia entre 270,938 e 271,370 s. O código [ground_truth.py](../../simulator/ground_truth.py:191) só fecha esse campo após resolver admissões pendentes; [ground_truth.py](../../simulator/ground_truth.py:131) impede início HTTP em `elapsed>=270`. Logo, fechamento administrativo, último início HTTP e última conclusão são eventos diferentes. Em A3, o fechamento ocorre entre 270,0004 e 270,0099 s. Fonte: [fronteiras_ofensivas.csv](fronteiras_ofensivas.csv), com snapshots completos em `eventos_ataque_<id>.csv`.

### 2.3 Grandezas e denominadores

| Grandeza | Fonte e inclusão | Unidade / denominador |
|---|---|---|
| Planejamento legítimo | `planned.planned_at` dos eventos da fonte; pode haver próximo evento planejado sem submissão ao terminar a execução | eventos por segundo planejado; não equivale a HTTP |
| Intensidade ofensiva configurada | configuração: A3 2×4 RPS; F96 2×32 RPS, durante 120 s | expectativa nominal, não quantidade observada de requisições planejadas |
| Admissões e tentativas submetidas | `journal:admission` e evento da fonte `submitted`, contados separadamente | eventos/s pelo próprio instante |
| Tarefa despachada | `task_started` da fonte | tarefas/s; pode terminar sem iniciar HTTP |
| HTTP iniciado | `request_log.elapsed_seconds`, conferido contra `http_started` das fontes | inícios/s; denominador do sucesso |
| HTTP recebido | `handler_started` identificado na vítima | recepções/s; não pressupõe operação simultânea ao início cliente |
| Operação submetida/iniciada/concluída | `work_submitted.at`, `work_started.at`, `work_completed.work_finished_at` | operações/s; cada contagem usa seu instante |
| Pendentes | intervalo [submissão, conclusão), aguardando + executando | média temporal de operações; pico instantâneo e snapshot de fronteira separados |
| Aguardando / ocupação | [submissão, início do worker) / [início, conclusão) | operações / slots; integração exata, sem amostrar o estado apenas no fim do segundo |
| Espera e custo | início−submissão; `work_cpu_seconds` | ms, coorte pela submissão computacional |
| Sucesso e timeout | status 2xx; `error_type` contendo Timeout | 2xx/inícios e timeouts/inícios da coorte HTTP |
| Duração HTTP | `duration_ms` | média das terminações conhecidas; média 2xx separada |
| Expiração antes do HTTP | `task_resolution:expired_before_http` | contagem por coorte de submissão e, separadamente, por instante de resolução |
| CPU | `victim_stats.jsonl`, apenas `state=valid` | % Docker; 100% equivale a um núcleo lógico |

Uma operação permanece na coorte de submissão para espera/custo, mesmo concluindo em POST; uma requisição mantém a coorte de início HTTP para sucesso/duração, mesmo terminando fora dela. Taxas de conclusão por janela contam os términos naquela janela, inclusive de coortes anteriores. Os CSV de 1 s também separam terminais HTTP pelo instante final. As poucas conclusões após 390 s são preservadas nos ciclos completos e nas coortes, mas não inventam segundos adicionais de POST. Há também raras submissões computacionais posteriores a 390 s de HTTP iniciado antes da fronteira: [conferencia_caudas.csv](conferencia_caudas.csv).

CPU é atribuída ao segundo de recepção da amostra e não interpolada. Cada valor representa um intervalo entre snapshots, não uma observação pontual pura; amostras junto às fronteiras podem atravessá-las. A CPU total do contêiner inclui threads de atendimento, além dos dois workers, podendo ultrapassar 200% sem existir um terceiro worker computacional.

Cada execução gera sua própria variável antes da agregação. São fornecidos média, mediana, desvio-padrão amostral, quartis, mínimo e máximo entre as 20 execuções. Segundos consecutivos não são réplicas independentes. As figuras mostram média e IQR, sem suavização; disponibilidade usa coortes não sobrepostas de 5 s para legibilidade, com a série de 1 s preservada. Durações sem 2xx ficam ausentes, nunca zero. Médias temporais de duração entre execuções usam somente execuções com resposta 2xx observada, com contagens exportadas.

### 2.4 Conferência dos resultados anteriores

[conferencia_agregados_anteriores.csv](conferencia_agregados_anteriores.csv) reproduz os escalares operacionais persistidos, sem recalcular detectores. Os números de referência são consistentes com esses escalares, mas precisam de duas distinções:

| Indicador | A3 anterior | A3 nesta análise | F96 anterior | F96 nesta análise |
|---|---:|---:|---:|---:|
| Sucesso legítimo ACTIVE | 9,235% | 9,237% | 34,738% | 35,062% |
| Sucesso legítimo POST | 70,537% | 70,532% | 95,698% | 94,766% |
| CPU ACTIVE | 205,70% | 212,09% | 228,20% | 236,04% |
| Pendências computacionais ao fim de ACTIVE | não medidas por aquele escalar | 549,40 | não medidas por aquele escalar | 407,45 |

O resumo operacional usa ACTIVE até `actual_end_seconds` e POST a partir desse instante. Aqui usa-se exatamente 270 s. Em F96, a mudança de aproximadamente 1,16 s transfere coortes fortemente degradadas entre ACTIVE e POST. As médias 2xx ACTIVE coincidem: 934,58 ms e 1.473,27 ms, porque não há novos sucessos nesse trecho transferido. CPU anterior vem de `simulation_metrics.csv`, emitido aproximadamente a cada 5 s e calculado a partir de uma janela de leituras; a análise temporal usa o fluxo nativo de snapshots próximo de 1 s. Não são estimadores idênticos, sobretudo nas transições. Código: [source_experiment.py](../../simulator/source_experiment.py:173) e [stats_collector.py](../../simulator/stats_collector.py:103).

**Os valores 1,10, 31,65 e 32,25 são exatamente `phases.ACTIVE.pending_at_end` da evidência de serviço legítimo no recibo. São pendências HTTP legítimas vistas no cliente, e não operações computacionais da vítima.** O timeout remove a pendência cliente, mas não remove necessariamente a operação computacional; por isso os dois estoques divergem. Essa é uma correção de interpretação, sem alterar qualquer resultado original.

## 3. Evolução temporal do A3

O A3 manteve entrega próxima à configuração: média de 960,2 inícios HTTP ofensivos em 120 s (8,002/s), intervalo entre execuções 882–1.007. Todas essas requisições tiveram operação recebida/submetida em ACTIVE. Não houve expiração antes do HTTP. O custo médio por operação ofensiva, calculado primeiro por execução, foi 256,79 ms de CPU; isso corresponde, descritivamente, a cerca de 2,05 CPU-s/s ofensivos, antes de contabilizar a carga legítima. Não é benchmark de capacidade isolada. Fonte: [metricas_periodo_execucao.csv](metricas_periodo_execucao.csv).

Os dois workers permaneceram ocupados durante 99,31% de ACTIVE, em média; a ocupação média foi 1,9925 slots de dois. A pendência média temporal passou de 0,487 em PRE para 261,42 em ACTIVE. O backlog não encontrou um patamar final: a média nos primeiros 30 s foi 59,63 e nos últimos 30 s 467,06; todas as regressões descritivas por execução tiveram inclinação positiva (3,08–5,53 operações/s). Essa inclinação descreve crescimento líquido e não implica monotonicidade de cada salto de evento. Fontes: [evolucao_active_execucao.csv](evolucao_active_execucao.csv), [series_1s.csv](series_1s.csv).

Nos primeiros e últimos blocos de 10 s, as submissões totais foram, respectivamente, 23,64 e 24,60 operações/s, contra 19,65 e 18,39 conclusões/s. A diferença de fluxo acumula estoque. A espera legítima média por coorte de submissão cresceu de 1,10 s no primeiro bloco para 27,64 s no último; esses valores incluem operações concluídas após ACTIVE. Fonte: [janelas_10s_execucao.csv](janelas_10s_execucao.csv).

O pico instantâneo médio de toda a observação foi 557,2 operações (376–657), e o instante do primeiro pico máximo ocorreu entre +115 e +124 s relativos ao início. Assim, algumas máximas aparecem já no início de POST, mesmo sem novas emissões ofensivas. O pico máximo observado foi 657 em `ps_direct80_030_A3`. No instante imediatamente anterior à fronteira de 270 s, a média era 549,4 pendências computacionais. Fonte: [recuperacao_execucao.csv](recuperacao_execucao.csv).

A perda de disponibilidade começou nas coortes iniciadas entre +2 e +24 s, mediana +9 s. Isso é início da coorte que acabará em timeout, não instante de emissão do timeout. O sucesso médio nos primeiros 30 s foi 37,2%, caindo a zero nos últimos 30 s. Todos os blocos de 10 s a partir de +30 s apresentaram zero sucesso nas 20 execuções. A duração 2xx cresceu de aproximadamente 832 ms no primeiro bloco para 1.679 ms no terceiro; depois deixa de existir observação 2xx. A média de todas as terminações permaneceu em torno de 2.005 ms, refletindo timeout, e não processamento encerrado na vítima. Fontes: [http_legitimo_janelas_10s.csv](http_legitimo_janelas_10s.csv), [evolucao_active_execucao.csv](evolucao_active_execucao.csv).

## 4. Evolução temporal do F96

### 4.1 Saturação e backlog

F96 apresentou custo ofensivo médio de 31,62 ms de CPU/operação, cerca de oito vezes menor que A3. O volume HTTP efetivamente iniciado foi 6.046,5 por execução, em média (50,388/s), contra 64 RPS configurados. A ocupação média dos workers foi 1,9792 slots, com os dois ocupados em 97,95% de ACTIVE. A CPU nativa média foi 236,04%; a carga de atendimento HTTP e instrumentação também pertence ao contêiner, portanto CPU total e ocupação dos workers não são equivalentes. Fontes: [metricas_periodo_execucao.csv](metricas_periodo_execucao.csv), Figura 3.

O backlog teve um ombro inicial: aproximadamente 121,6 operações no bloco +20–30 s e 126,8 em +30–40 s, seguido por novo crescimento até 380,8 no bloco +110–120 s. Não se estabeleceu um patamar duradouro. A média dos primeiros 30 s foi 89,79 e dos últimos 30 s 332,57; todas as inclinações por execução foram positivas (1,40–6,14 operações/s). No fim de ACTIVE havia, em média, 407,45 operações pendentes. O pico médio foi 411,1, com mínimo 280 e máximo 740. Os primeiros picos máximos ocorreram entre +118 e +119 s. Fontes: [janelas_10s_execucao.csv](janelas_10s_execucao.csv), [evolucao_active_execucao.csv](evolucao_active_execucao.csv), [recuperacao_execucao.csv](recuperacao_execucao.csv).

As submissões totais caíram de aproximadamente 77,17/s no primeiro bloco de 10 s para 64,06/s no último; as conclusões caíram de 69,63/s para 58,37/s. A espera legítima média cresceu de 0,58 s para 6,52 s. Portanto, a redução da emissão efetivamente iniciada não impediu a acumulação computacional.

### 4.2 Limitação no gerador e expiração

O planejamento ofensivo não tem uma série independente de eventos `planned`. O produto 64×120=7.680 é apenas expectativa nominal de uma emissão estocástica, não contagem observada. Os journals registram, em média, 7.310,9 admissões/tentativas submetidas e 6.046,5 inícios HTTP. O déficit nominal de admissões não deve ser atribuído integralmente à saturação da fonte: o código usa intervalos exponenciais e incorre em custos de despacho. A limitação observada com evidência direta é a fila interna entre submissão e início de envio e o orçamento de concorrência. Código: [traffic_injectorV0.py](../../simulator/traffic_injectorV0.py:204).

| Intervalo relativo | HTTP ofensivo em voo, média | Pico de concorrência, média dos picos | Espera média submit→task, pela coorte |
|---|---:|---:|---:|
| +0–10 s | 35,75 | 66,7 | 1,65 ms |
| +20–30 s | 94,74 | 96,0 | 1,96 s |
| +50–60 s | 95,89 | 96,0 | 9,32 s |
| +80–90 s | 95,90 | 96,0 | 17,53 s |
| +90–100 s | 95,90 | 96,0 | 19,90 s |

A partir do bloco +20–30 s, todas as execuções atingiram o pico configurado de 96 envios simultâneos; depois a ocupação ficou próxima desse teto. A taxa HTTP caiu de 61,58/s no primeiro bloco para aproximadamente 47,82/s nos últimos blocos, compatível com 96 slots ocupados por chamadas de aproximadamente 2 s. Isso sustenta limitação da entrega pelo orçamento da fonte, sem reduzir a questão à taxa nominal. Fonte: [fontes_janelas_10s.csv](fontes_janelas_10s.csv).

Expiraram antes do início HTTP, em média, 1.264,4 tentativas (1.051–1.484), ou 17,28% das admissões por execução, em média. O instante de resolução dessas expirações ficou entre 270 s e aproximadamente 271,37 s: elas foram admitidas antes, mas só chegaram ao despacho quando a janela já havia encerrado. Pela coorte de submissão, as expirações concentram-se nos últimos 30 s: médias de 83,55, 581,60 e 599,20 nos blocos +90–100, +100–110 e +110–120 s. Uma rara submissão de fonte registrada depois de 270 s explica a diferença de 0,05 tentativa entre o total e a soma de coortes ACTIVE. A queda da espera média de despacho nas últimas coortes reflete essa resolução por expiração, não recuperação da capacidade de emissão. Fontes: [fontes_resumo_execucao.csv](fontes_resumo_execucao.csv), [fontes_janelas_10s.csv](fontes_janelas_10s.csv).

As médias foram 6.046,50 inícios HTTP ofensivos, 6.046,35 operações ofensivas submetidas em ACTIVE e mais 0,15 em POST. A diferença de fronteira é recepção/submissão tardia de HTTP iniciado antes de 270 s; não é emissão ofensiva nova em POST. A série de `attack_received` preserva separadamente a entrada no handler. Em toda a observação, a identidade vincula cada operação ofensiva ao HTTP correspondente. Fonte: [series_1s.csv](series_1s.csv), arquivos `operacoes_<id>.csv`.

### 4.3 Disponibilidade legítima

As primeiras coortes ACTIVE que terminariam em timeout foram iniciadas entre +14 e +48 s, mediana +24 s. O sucesso médio dos primeiros 30 s foi 95,1%, contra zero nos últimos 30 s. Nos blocos +30–40, +40–50, +50–60 e +60–70 s, a média foi aproximadamente 66,4%, 42,6%, 21,9% e 7,0%. A partir de +80 s não houve 2xx legítimo em nenhum bloco de 10 s de ACTIVE nas 20 execuções. Fontes: [evolucao_active_execucao.csv](evolucao_active_execucao.csv), [janelas_10s_execucao.csv](janelas_10s_execucao.csv).

A duração média 2xx passou de 623 ms no primeiro bloco para 1.811 ms no terceiro e aproximou-se do limite cliente entre os sucessos remanescentes. Nos blocos sem sucesso, não existe média 2xx interpretável. A maior disponibilidade média de F96 em ACTIVE decorre principalmente de sua fase inicial menos degradada; não descreve serviço preservado até o fim do ataque. Fonte: [http_legitimo_janelas_10s.csv](http_legitimo_janelas_10s.csv).

## 5. Recuperação pós-ataque

### 5.1 Tempos distintos de encerramento e retorno

Os tempos abaixo são segundos após 270 s da execução, isto é, após o fim programado da emissão. Cada linha usa as 20 repetições de seu cenário. A fila aguardando vazia significa nenhum trabalho esperando worker naquele instante; não significa que não existam workers ocupados ou futuras chegadas legítimas.

| Evento / medida | A3: média; mediana; mínimo–máximo | F96: média; mediana; mínimo–máximo |
|---|---|---|
| Último término HTTP ofensivo no cliente | 1,883; 1,884; 1,658–2,001 s | 1,986; 1,990; 1,945–2,004 s |
| Última conclusão computacional ofensiva | 29,289; 29,412; 19,291–37,733 s | 6,807; 6,478; 4,811–12,286 s |
| Primeira fila aguardando vazia | 37,699; 37,492; 24,731–47,924 s | 9,009; 8,532; 6,366–16,193 s |
| Início do retorno descritivo das pendências ao nível PRE | 40,0; 40,0; 25–50 s | 11,5; 10,0; 10–20 s |
| Início de três coortes de 5 s com sucesso ≥99% | 37,5; 37,5; 25–50 s | 8,5; 10,0; 5–15 s |
| Último início legítimo POST que terminou em falha | 35,081; 34,820; 21,833–45,441 s | 6,301; 5,834; 3,619–13,388 s |

Fontes: [recuperacao_execucao.csv](recuperacao_execucao.csv), [tabela_variabilidade.csv](tabela_variabilidade.csv). O retorno descritivo das pendências exige média de cada bloco de 5 s abaixo do p95 das médias de 1 s do PRE, por três blocos consecutivos. O sucesso exige três coortes consecutivas ≥99%. Esses são marcadores exploratórios; a confirmação exige esperar mais 15 s a partir do início indicado. Eles não substituem a regra operacional original. Nenhuma das 40 execuções ofensivas ficou censurada para esses dois marcadores até o fim do POST.

Houve, em média, 187,25 operações ofensivas concluídas em POST em A3 e 306,10 em F96; respectivamente 185,50 e 304,75 ainda nem haviam iniciado no worker ao entrar POST. A ocupação ofensiva residual somou 48,48 worker-s por execução em A3 e 10,12 worker-s em F96. A3 deixa menos operações ofensivas residuais, mas cada uma custa mais tempo. O backlog total também contém trabalho legítimo, de modo que a última operação ofensiva termina antes do primeiro esvaziamento da fila total. Esses intervalos explicam por que cessar a emissão não produz recuperação imediata. Fonte: [recuperacao_execucao.csv](recuperacao_execucao.csv).

### 5.2 Relação entre drenagem e disponibilidade

Na média entre execuções, A3 manteve sucesso zero nos primeiros 20 s de POST; nos blocos seguintes de 10 s houve aproximadamente 6,2%, 47,4%, 95,1% e 100%. F96 apresentou aproximadamente 38,8% no primeiro bloco POST, 98,4% no segundo e 100% no terceiro. Essa recuperação agregada é progressiva e acompanha a drenagem, mas combina tempos de transição distintos entre repetições. Não prova recuperação suave ou monotônica em cada execução. Fonte: [janelas_10s_execucao.csv](janelas_10s_execucao.csv), Figura 4.

Não foi observado timeout legítimo terminando depois do primeiro esvaziamento da fila aguardando, nem timeout de requisição iniciada depois dele, nas 40 execuções. Os últimos términos de falha ocorreram, em média, aos +37,086 s em A3 e +8,306 s em F96. A ausência é específica desta campanha; não é propriedade geral do protocolo. Após o último início com falha, ainda foram observados em média 1.344,15 e 1.807,05 inícios legítimos POST com sucesso, respectivamente. Fontes: [recuperacao_execucao.csv](recuperacao_execucao.csv), [conferencia_caudas.csv](conferencia_caudas.csv).

A duração média 2xx POST de aproximadamente 76 ms em A3 e 71 ms em F96 não caracteriza disponibilidade integral durante todo o POST: ela exclui as muitas coortes iniciais que falharam. A recuperação só fica sustentada pela leitura conjunta de sucesso, espera, drenagem e duração. Nos blocos finais, as durações voltam à ordem de dezenas de milissegundos, próxima de PRE.

### 5.3 Execuções sem recuperação operacional confirmada

A recuperação registrada foi confirmada em 19/20 A3 e 19/20 F96. A regra persistida exige, entre outros critérios, duas últimas janelas qualificadas, sucesso ≥99%, limites de latência relativos a PRE, pendências HTTP pequenas, sem envelhecimento e crescimento ≤2. A lógica foi lida apenas para interpretar a evidência de serviço: [evaluation.py](../../analysis/detection/scientific/evaluation.py:161), [development_d3_minimal.py](../../experiments/development_d3_minimal.py:180). Não se executou essa avaliação nem se analisaram resultados de detectores.

| Execução | O que falhou na última janela [360,390) | Disponibilidade e latência nessa janela |
|---|---|---|
| `ps_direct80_043_A3` | `pending_growth`: pendências HTTP legítimas de 0 para 3; limite de crescimento 2 | 100% de sucesso; p95 2xx 78,02 ms, abaixo do limite 95,86 ms |
| `ps_direct80_075_F96` | `pending_growth`: pendências HTTP legítimas de 0 para 3; limite de crescimento 2 | 100% de sucesso; p95 2xx 80,75 ms, abaixo do limite 94,36 ms |

Na A3 043, a janela [330,360) foi qualificada; na F96 075, [300,330) e [330,360) foram qualificadas, mas a última perdeu qualificação. O critério exige as duas finais, portanto os booleanos negativos são consistentes com a regra. São incompatíveis apenas com a interpretação simplificada de que “não confirmado” significa indisponibilidade mantida: a disponibilidade final foi integral nas coortes observadas e os três HTTP de fronteira tiveram término posterior preservado. Não se propõe alterar a regra nesta atividade. Fontes: [janelas_recuperacao_registrada.csv](janelas_recuperacao_registrada.csv), [recuperacao_registrada.json](recuperacao_registrada.json).

### 5.4 Timeout sem cancelamento computacional

Houve processamento do worker após o timeout da mesma requisição em todas as 20 execuções de cada ataque. As somas entre execuções foram 63.198 operações em A3 e 100.564 em F96 com interseção temporal positiva entre processamento e período posterior ao timeout. Em 62.971 e 98.548 casos, respectivamente, o próprio worker só começou depois do timeout. O tempo de slots ocupado após timeout somou 5.743,69 worker-s e 3.280,34 worker-s, incluindo ACTIVE e POST; não são CPU-s nem apenas resíduo POST. Fontes: [conferencia_caudas.csv](conferencia_caudas.csv), [recuperacao_execucao.csv](recuperacao_execucao.csv).

Dois exemplos fortes, em segundos da execução:

| Execução / requisição | Início HTTP | Timeout cliente | Início worker | Fim computacional |
|---|---:|---:|---:|---:|
| A3 023 / `request_normal_2_000002058` | 267,394 | 269,399 | 294,283 | 294,312 |
| F96 022 / `request_attack_1_000002970` | 268,616 | 270,623 | 273,757 | 273,789 |

Fonte: [evidencias_timeout_longo.csv](evidencias_timeout_longo.csv), reconstruída por `request_id`, com ciclos em `operacoes_<id>.csv` e HTTP original no respectivo `request_log.csv`. Isso comprova a persistência, inclusive quando o trabalho ainda aguardava worker no timeout. O servidor submete a operação e aguarda `.result()` antes de escrever a resposta; não há cancelamento desse future devido ao timeout remoto no caminho observado: [simple_server.py](../../simulator/app/simple_server.py:271). Não se infere quanto seria economizado sob uma implementação alternativa.

## 6. Comparação dos mecanismos

| Indicador em ACTIVE, média entre execuções | L2 | A3 | F96 |
|---|---:|---:|---:|
| Sucesso legítimo | 100% | 9,24% | 35,06% |
| Timeout legítimo | 0% | 90,76% | 64,94% |
| Duração 2xx legítima | 43,29 ms | 934,58 ms | 1.473,27 ms |
| Inícios HTTP ofensivos/s | 0 | 8,00 | 50,39 |
| CPU ofensiva/operação | — | 256,79 ms | 31,62 ms |
| Ocupação média dos dois slots | 0,4317 | 1,9925 | 1,9792 |
| Fração de tempo com dois slots ocupados | 8,45% | 99,31% | 97,95% |
| Pendência computacional média temporal | 0,468 | 261,42 | 195,93 |
| Pendência computacional ao fim | 0,55 | 549,40 | 407,45 |
| Espera legítima média submit→worker | 2,28 ms | 13.715,11 ms | 3.204,11 ms |
| CPU Docker nativa média | 50,95% | 212,09% | 236,04% |

Fonte: [metricas_periodo_execucao.csv](metricas_periodo_execucao.csv), [resumo_periodos.csv](resumo_periodos.csv). As médias de duração e espera são condicionais às respectivas coortes/observações e não devem ser comparadas como tempos globais equivalentes.

O A3 consome capacidade por requisição cara, com entrega ofensiva pouco limitada pela fonte; F96 entrega muito mais operações baratas, mas sua concorrência HTTP e seus timeouts restringem os inícios efetivos. Os dois excedem o escoamento computacional da vítima e provocam crescimento de fila. Em A3, uma taxa HTTP menor coexistiu com espera e resíduo mais prolongados. Em F96, a CPU total maior não significou maior persistência do backlog.

Essa comparação é condicional a endpoints, custos, dois workers, carga legítima, timeout de 2 s, orçamento de envio e perfil energético desta campanha. Não compara doses iguais, capacidade do atacante, custo monetário ou eficiência intrínseca. Não permite declarar superioridade universal de um mecanismo.

## 7. Variabilidade entre execuções

| Medida | Média | Mediana | DP amostral | Q1–Q3 | Mínimo–máximo |
|---|---:|---:|---:|---:|---:|
| Pico computacional A3, operações | 557,20 | 564,50 | 74,72 | 503,75–615,00 | 376–657 |
| Pico computacional F96, operações | 411,10 | 389,00 | 106,59 | 343,50–450,25 | 280–740 |
| Última conclusão ofensiva A3, s após 270 | 29,29 | 29,41 | 4,51 | 26,46–32,55 | 19,29–37,73 |
| Última conclusão ofensiva F96, s após 270 | 6,81 | 6,48 | 1,72 | 5,70–7,42 | 4,81–12,29 |
| Primeira fila aguardando vazia A3, s após 270 | 37,70 | 37,49 | 5,86 | 34,09–42,56 | 24,73–47,92 |
| Primeira fila aguardando vazia F96, s após 270 | 9,01 | 8,53 | 2,34 | 7,35–9,87 | 6,37–16,19 |

Fonte: [tabela_variabilidade.csv](tabela_variabilidade.csv). Os resumos completos incluem demais variáveis e 20 observações por cenário; o pico desta tabela considera toda a observação, portanto difere ligeiramente do pico limitado a ACTIVE em A3.

O sucesso ACTIVE variou de 1,63% a 23,81% em A3 (DP 5,53 pontos percentuais) e de 18,99% a 51,16% em F96 (DP 9,83 pontos). `ps_direct80_064_A3` teve o menor sucesso A3, 1,63%; `ps_direct80_030_A3` teve o maior pico A3, 657. Esses critérios não selecionam necessariamente a mesma execução. A saturação foi consistente, mas o tempo até a perda de disponibilidade variou bastante.

Aplicou-se uma regra descritiva de 1,5×IQR a pico, retorno da fila, última conclusão ofensiva e último início POST com falha, sem excluir observações. `ps_direct80_042_F96` é a divergência mais relevante: pico 740, última conclusão ofensiva +12,286 s e último início POST com falha +13,388 s, acima dos limites dessa regra. Para retorno da fila em blocos de 5 s, também foram sinalizadas `ps_direct80_025_F96`, `ps_direct80_032_F96`, `ps_direct80_046_F96` e `ps_direct80_068_F96` (15 s, contra mediana 10 s), além da 042 (20 s). Essa classificação é sensível à discretização e ao IQR estreito; não é evidência de falha técnica.

Em L2, o IQR do pico total é degenerado em 6 operações. A regra sinaliza 026/054/069 (pico 7) e 036/062/065 (pico 5); diferenças unitárias não indicam comportamento operacional divergente, e todas as 20 L2 mantiveram 100% de sucesso em PRE, ACTIVE e POST. A lista integral, com limites e valores, está em [atipicas_iqr.csv](atipicas_iqr.csv). As duas não confirmações operacionais são discutidas separadamente, pois não equivalem a esses outliers computacionais.

## 8. Hipóteses e evidências

| Hipótese | Classificação | Evidência e alcance |
|---|---|---|
| H1 — Backlog residual | **Sustentada pelas evidências** | Nas 40 execuções ofensivas há operações ofensivas iniciadas e concluídas em POST; médias de 187,25 conclusões A3 e 306,10 F96. Última conclusão ofensiva ocorre vários segundos depois do último término HTTP cliente. [recuperacao_execucao.csv](recuperacao_execucao.csv). |
| H2 — Recuperação progressiva | **Sustentada pelas evidências** | A média por coortes POST melhora enquanto o estoque cai; todos os marcadores descritivos de retorno são observados até o fim do POST. A3 recupera mais lentamente que F96. A sustentação refere-se à trajetória agregada e às transições observadas, sem impor monotonicidade a cada segundo de cada execução. [coortes_5s.csv](coortes_5s.csv), [janelas_10s_execucao.csv](janelas_10s_execucao.csv), Figura 4. |
| H3 — Timeout sem cancelamento computacional | **Sustentada pelas evidências** | Identidades mostram início ou continuação do worker depois do timeout da mesma requisição, em todas as repetições ofensivas; exemplos com espera adicional de vários segundos eliminam dependência de ordenação submilissegundo. [evidencias_timeout_longo.csv](evidencias_timeout_longo.csv), [conferencia_caudas.csv](conferencia_caudas.csv). |

Há evidência mecanística para persistência do trabalho e consistência temporal com a indisponibilidade. Não há intervenção que isole a contribuição causal de cada componente de CPU, rede, fila de atendimento e escalonamento; não se atribui uma fração causal exata da degradação a cada um.

## 9. Figuras e tabelas produzidas

As figuras usam média entre execuções e faixa Q1–Q3, com n=20 por cenário. O traçado em degraus representa bins; não há suavização adicionada. A faixa IQR não é intervalo de confiança e não cobre necessariamente as execuções extremas.

| Figura | Arquivos | Leitura principal |
|---|---|---|
| 1 — Pendências computacionais | [PNG](figura1_pendencias.png), [SVG](figura1_pendencias.svg) | Crescimento durante ACTIVE e drenagem mais prolongada do A3. Valores de L2 próximos de zero na escala ofensiva estão quantificados nas tabelas. |
| 2 — Disponibilidade legítima | [PNG](figura2_disponibilidade.png), [SVG](figura2_disponibilidade.svg) | Coortes de 5 s mostram perda progressiva e recuperação; não são respostas por segundo de conclusão. |
| 3 — Ocupação e CPU | [PNG](figura3_ocupacao.png), [SVG](figura3_ocupacao.svg) | Dois slots saturados nos ataques; CPU do contêiner é medida complementar, com unidade própria. |
| 4 — Recuperação | [PNG](figura4_recuperacao.png), [SVG](figura4_recuperacao.svg) | Painéis temporalmente alinhados relacionam backlog e disponibilidade POST sem sobrepor unidades em dois eixos. O eixo mantém a origem ofensiva, portanto POST começa em +120 s. |

Tabelas essenciais: [series_1s.csv](series_1s.csv), [series_agregadas_1s.csv](series_agregadas_1s.csv), [series_fontes_1s.csv](series_fontes_1s.csv), [metricas_periodo_execucao.csv](metricas_periodo_execucao.csv), [resumo_periodos.csv](resumo_periodos.csv), [janelas_10s_execucao.csv](janelas_10s_execucao.csv), [http_legitimo_janelas_10s.csv](http_legitimo_janelas_10s.csv), [fontes_janelas_10s.csv](fontes_janelas_10s.csv), [recuperacao_execucao.csv](recuperacao_execucao.csv), [tabela_variabilidade.csv](tabela_variabilidade.csv) e [janelas_recuperacao_registrada.csv](janelas_recuperacao_registrada.csv). Os CSV de resumo com cabeçalho multinível incluem contagem, média, mediana, DP, Q1, Q3, mínimo e máximo. Os arquivos `operacoes_<id>.csv` permitem reconstruir os estoques e auditar cada identidade.

## 10. Limitações

1. A resolução nominal do relógio não garante ordenação física exata entre processos; a certificação sustenta comparabilidade, não ausência de atraso de instrumentação. Exemplos de H3 com diferenças de segundos são mais fortes que sobreposições inferiores a um milissegundo.
2. O intervalo `work_started` até `work_finished_at` mede ocupação instrumentada do slot, incluindo pequeno custo de entrada e instrumentação; CPU por operação vem do contador CPU do worker e é outra grandeza. Backlog inclui executando e aguardando; fila aguardando é exportada separadamente.
3. Coortes por início/submissão usam desfechos futuros conhecidos. A disponibilidade de um segundo é uma descrição retrospectiva de quem iniciou naquele segundo, não uma métrica disponível online naquele instante.
4. Duração 2xx sofre seleção. Quando o sucesso cai a zero, a duração 2xx fica ausente; uma redução posterior pode refletir mudança dos sobreviventes. Também a média de todas as terminações mede tempo no cliente até timeout, não até fim computacional.
5. Não existe registro ofensivo independente de requisições planejadas. A expectativa nominal não pode ser convertida em contagem factual; admissões, despacho e inícios são observados separadamente.
6. Atribuir CPU pelo instante de recepção não desagrega perfeitamente intervalos de snapshots junto às fronteiras. O log operacional agrega leituras em janelas de aproximadamente 5 s; diferenças com o fluxo nativo não demonstram mudança dos dados originais. Não se estimou frequência efetiva por worker nem custo isolado do observador.
7. Médias e IQR podem esconder extremos; os IDs e tabelas individuais preservam essa variabilidade. Marcadores de retorno de 5 s são exploratórios e possuem discretização de até um bloco; confirmação de três blocos não é garantia fora do horizonte observado.
8. Primeiro esvaziamento não é ausência permanente de fila: a carga legítima continua chegando. Aqui a evidência adicional de sucesso após a última falha sustenta o retorno observado. Ausência de timeout depois do primeiro esvaziamento é observação amostral, não impossibilidade teórica.
9. A campanha é condicional a esta infraestrutura e perfil energético. Não há intervenção que separe causalmente custo por operação, overhead HTTP, escalonamento e filas de transporte. Não se faz teste de superioridade ou generalização de eficiência entre mecanismos.
10. A diferença entre POST programado e POST operacional é material em F96. Comparar percentuais sem explicitar a fronteira altera a interpretação; ambas as versões foram preservadas em tabelas distintas.

## 11. Conclusões aproveitáveis no TCC

1. **Os mecanismos saturam a capacidade computacional por combinações diferentes de custo e volume.** A3: 8,00 inícios ofensivos/s e 256,79 ms CPU/op; F96: 50,39/s e 31,62 ms/op. Os dois slots ficam simultaneamente ocupados em 99,31% e 97,95% de ACTIVE. Evidência: [metricas_periodo_execucao.csv](metricas_periodo_execucao.csv), Figura 3.
2. **A sobrecarga acumula trabalho na vítima e progride até indisponibilidade completa no fim do ataque.** Ao fim de ACTIVE, médias de 549,4 e 407,45 operações computacionais pendentes; zero sucesso legítimo nos últimos 30 s em todas as repetições ofensivas. Evidência: [metricas_periodo_execucao.csv](metricas_periodo_execucao.csv), [evolucao_active_execucao.csv](evolucao_active_execucao.csv).
3. **A intensidade nominal do F96 superestima a entrega HTTP efetiva nesta configuração.** Concorrência atinge 96; 17,28% das admissões, em média por execução, expiram antes do início HTTP; o fluxo efetivo fica em 50,39/s contra 64/s configurados. Evidência: [fontes_janelas_10s.csv](fontes_janelas_10s.csv), [fontes_resumo_execucao.csv](fontes_resumo_execucao.csv).
4. **Cessar a emissão ou observar timeout não encerra o trabalho ofensivo.** Últimas conclusões ofensivas, em média, +29,29 s em A3 e +6,81 s em F96; correlação por identidade comprova início de worker após timeout. Evidência: [recuperacao_execucao.csv](recuperacao_execucao.csv), [evidencias_timeout_longo.csv](evidencias_timeout_longo.csv).
5. **A recuperação é mais lenta no A3 nesta campanha e acompanha a drenagem residual.** Primeira fila aguardando vazia em média +37,70 s versus +9,01 s; variabilidade preservada nas 20 repetições de cada cenário. Isso não estabelece eficiência intrínseca. Evidência: [tabela_variabilidade.csv](tabela_variabilidade.csv), Figura 4.
6. **Pendência HTTP, backlog computacional e confirmação operacional são medidas distintas.** Os cerca de 32 itens anteriores são HTTP legítimo pendente; o estoque computacional tem centenas de operações. As duas não confirmações operacionais finais resultam de crescimento de três HTTP, apesar de sucesso final de 100%. Evidência: [conferencia_agregados_anteriores.csv](conferencia_agregados_anteriores.csv), [janelas_recuperacao_registrada.csv](janelas_recuperacao_registrada.csv).

## 12. Questões pendentes

- Para incorporar números no TCC, o pesquisador precisa escolher e declarar a convenção temporal: períodos programados deste relatório ou períodos encerrados por `actual_end_seconds` do resumo operacional. A diferença é relevante em F96; não se devem misturar percentuais das duas definições. A reconstrução já apresenta ambas, sem exigir nova coleta.
- Os valores de referência 1,10/31,65/32,25 precisam ser identificados no texto do TCC como pendências HTTP legítimas, caso sejam aproveitados. Tratá-los como backlog computacional é incompatível com os eventos da vítima.
- O marcador exploratório de retorno ao patamar PRE deve ser apresentado como definição descritiva, caso seja adotado no TCC; ele não constitui validação de equivalência estatística ou mudança do critério operacional. A distinção não impede as conclusões mecanísticas apoiadas nos eventos.
- Não é possível quantificar com estes dados um ganho causal isolado por cancelamento computacional, nem a eficiência intrínseca relativa dos mecanismos. Tais conclusões ficam fora do alcance desta campanha; não se recomenda regenerar ou alterar seus resultados para preenchê-las.

A investigação de detectores permanece fora desta entrega e depende de autorização em atividade independente.
