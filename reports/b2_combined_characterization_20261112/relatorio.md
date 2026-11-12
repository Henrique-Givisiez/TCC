# Caracterização experimental B2 — tráfego combinado

## Escopo, inventário e comparabilidade

Foram auditadas quatro execuções B2 completas e três referências isoladas históricas. Todas possuem topologia direta, vítima única, dois workers, duração configurada de 150 s e instrumentação Docker/HTTP. PRE=[0,30), ACTIVE=[30,60) e POST=[60,150) s. A1-L2 não tem fase ofensiva; a janela [30,60) é usada apenas como referência temporal. A B1-A3 é a referência isolada de assimetria a **8 RPS agregados** (2×4); B1-F2 é Flooding a **64 RPS agregados** (2×32). A1-L2 e B2-L são duas execuções legítimas distintas.

| Execução | Papel | Legítimas | Ofensivas | Concorrência ofensiva | Endpoint ofensivo | HTTP observados |
|---|---|---:|---:|---:|---|---:|
| A1-L2 | referência histórica | 16 RPS, 2 fontes | 0 RPS, 0 fontes | — | — | 2340 |
| B1-A3 | referência histórica | 0 RPS, 0 fontes | 8 RPS, 2 fontes | 64 | /expensive | 238 |
| B1-F2 | referência histórica | 0 RPS, 0 fontes | 64 RPS, 2 fontes | 64 | /medium | 1807 |
| B2-L | B2 | 16 RPS, 2 fontes | 0 RPS, 0 fontes | — | — | 2386 |
| B2-A | B2 | 16 RPS, 2 fontes | 8 RPS, 2 fontes | 64 | /expensive | 2623 |
| B2-F | B2 | 16 RPS, 2 fontes | 64 RPS, 2 fontes | 64 | /medium | 4006 |
| B2-F96 | B2 | 16 RPS, 2 fontes | 64 RPS, 2 fontes | 96 | /medium | 3881 |

As referências históricas são elegíveis para comparação **visual descritiva**, não para subtração causal. Memória da A1-L2 difere do patamar B2-L; não se deve atribuir essa diferença à combinação de cargas. B2-F e B2-F96 possuem configuração efetiva igual, salvo a concorrência ofensiva (64 e 96), mas foram executadas uma vez cada em momentos sucessivos.

## Definições e relógios

- `request_log.csv.elapsed_seconds` e `end_elapsed_seconds` são tempos relativos ao início da execução no cliente. RPS iniciado conta inícios no intervalo semiaberto [30,60) e divide por 30 s. RPS encerrado conta encerramentos pelo seu próprio timestamp. Desfechos da coorte ACTIVE classificam tentativas iniciadas em [30,60), mesmo que terminem depois de 60 s.

- `outcome=response` com status 2xx é sucesso HTTP observado; `ReadTimeout` é timeout do cliente. Um timeout não implica encerramento do processamento na vítima. Tarefas submetidas e sem início HTTP são mostradas separadamente.

- CPU Docker é `victim_stats.jsonl.metrics.cpu_percent` da `target_instance_1`; pode exceder 100% em múltiplos núcleos. Memória é `raw_mem_usage/1048576` MiB do contêiner, não do host ou do processo Python. Amostras reais são desenhadas sem interpolação.

- Operações são ligadas por `operation_id` e `request_id`. Espera = `work_started - work_submitted`; execução decorrida = `work_completed - work_started`; CPU/operação = `work_cpu_seconds × 1000`. A A1-L2 usa os timestamps consolidados em `handler_finished`, pois não dispõe dos eventos explícitos de work.

- Workers ocupados e operações aguardando são reconstruídos por eventos de submissão, início e conclusão, com eventos simultâneos agrupados. A quantidade aguardando mede operações submetidas ainda sem início, não a profundidade exata da fila interna. Não há medição direta da espera pré-handler.

- Eventos da vítima e fontes usam `CLOCK_MONOTONIC` do host, com origem `experiment_start_monotonic`; o log HTTP fornece o tempo relativo já calculado pela execução. Eventos de `traffic_class=unknown` antes do tráfego são auditoria/captura e foram excluídos. Captura TCP não separa classes com confiabilidade e `packet_length` não é byte no fio.

## Atendimento legítimo e fase ofensiva

| Condição | Inícios HTTP | RPS iniciado | HTTP 2xx | Timeout | Duração mediana 2xx (ms) | p95 2xx (ms) | Espera mediana (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| B2-L | 515 | 17.17 | 515 | 0 | 37.67 | 78.72 | 1.20 |
| B2-A | 514 | 17.13 | 43 | 471 | 1040.97 | 1988.99 | 10704.93 |
| B2-F | 514 | 17.13 | 514 | 0 | 1177.93 | 1369.37 | 1140.25 |
| B2-F96 | 514 | 17.13 | 98 | 416 | 1461.38 | 1998.59 | 2592.91 |

A taxa legítima iniciada ficou próxima de 17,13–17,17 RPS nas quatro condições, acima do nominal de 16 RPS. B2-A e B2-F96 preservaram os inícios legítimos durante ACTIVE, mas grande parte das tentativas terminou em timeout. B2-F manteve respostas 2xx para toda a coorte ACTIVE, com duração mediana muito superior à B2-L. A mediana dos sucessos sobreviventes em B2-A e B2-F96 não descreve o atendimento global, pois poucos sucessos permaneceram.

## Tráfego ofensivo e processamento

| Condição | RPS nominal | RPS iniciado | HTTP 2xx da coorte | Timeout da coorte | Submetidas sem HTTP | CPU/op mediana (ms) | Espera mediana (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| B1-A3 | 8 | 7.93 | 200 | 38 | 0 | 258.16 | 1406.40 |
| B2-A | 8 | 7.93 | 16 | 222 | 0 | 356.39 | 10646.49 |
| B1-F2 | 64 | 60.23 | 1807 | 0 | 0 | 30.94 | 886.37 |
| B2-F | 64 | 54.07 | 1622 | 0 | 191 | 28.25 | 1117.74 |
| B2-F96 | 64 | 49.87 | 351 | 1145 | 308 | 31.91 | 2483.51 |

A B2-A registrou espera computacional mediana elevada para ambas as classes e 471 timeouts legítimos na fase ACTIVE. O trabalho da vítima pode continuar após o timeout do cliente. B2-F e B2-F96 compartilham o endpoint `/medium` com o tráfego legítimo; a distinção entre classes foi feita pelos IDs e pelo campo `traffic_class`, não pelo endpoint. Em B2-F, 191 tarefas ofensivas submetidas não chegaram ao início HTTP; em B2-F96 foram 308. Essas tarefas não são timeouts HTTP.

## CPU Docker, CPU por operação e memória

| Condição | CPU Docker média ACTIVE (%) | CPU mediana (%) | CPU máxima (%) | Memória média (MiB) | Memória máxima (MiB) | Fração com 2 workers | Máximo aguardando ACTIVE |
|---|---:|---:|---:|---:|---:|---:|---:|
| B2-L | 60.02 | 61.43 | 82.94 | 46.91 | 48.23 | 10.4% | 3 |
| B2-A | 217.76 | 217.83 | 222.80 | 44.27 | 56.62 | 99.3% | 322 |
| B2-F | 229.25 | 228.98 | 234.10 | 41.00 | 45.99 | 98.0% | 93 |
| B2-F96 | 238.19 | 238.18 | 242.88 | 46.84 | 56.66 | 97.6% | 239 |

### Memória por fase

| Condição | PRE mediana (MiB; n) | ACTIVE mediana (MiB; n) | POST mediana (MiB; n) | POST − PRE (MiB) |
|---|---:|---:|---:|---:|
| B2-L | 44.19 (n=11) | 46.86 (n=10) | 50.86 (n=30) | +6.66 |
| B2-A | 27.59 (n=10) | 44.31 (n=10) | 48.94 (n=30) | +21.34 |
| B2-F | 27.84 (n=10) | 42.00 (n=10) | 46.36 (n=30) | +18.52 |
| B2-F96 | 27.46 (n=10) | 47.05 (n=10) | 50.40 (n=30) | +22.95 |

As diferenças POST − PRE são descritivas da memória do contêiner e não identificam a origem da alocação.

A ocupação de dois workers foi observada por menos tempo na B2-L que nas três condições com ataque. As medianas de CPU por operação e de espera são métricas distintas: a espera pode crescer sem aumento equivalente do tempo de CPU individual. A memória medida é a do contêiner inteiro; a comparação por fase e as matrizes mostram a evolução e possíveis resíduos após o ataque sem atribuição a uma classe específica.

## Evolução por fase e recuperação

| Condição | Fase | Inícios legítimos | HTTP 2xx | Timeouts | Duração mediana 2xx (ms) |
|---|---|---:|---:|---:|---:|
| B2-L | PRE | 456 | 456 | 0 | 38.85 |
| B2-L | ACTIVE | 515 | 515 | 0 | 37.67 |
| B2-L | POST | 1414 | 1414 | 0 | 38.42 |
| B2-A | PRE | 456 | 456 | 0 | 45.28 |
| B2-A | ACTIVE | 514 | 43 | 471 | 1040.97 |
| B2-A | POST | 1415 | 939 | 476 | 45.80 |
| B2-F | PRE | 456 | 456 | 0 | 37.32 |
| B2-F | ACTIVE | 514 | 514 | 0 | 1177.93 |
| B2-F | POST | 1414 | 1414 | 0 | 36.67 |
| B2-F96 | PRE | 456 | 456 | 0 | 40.56 |
| B2-F96 | ACTIVE | 514 | 98 | 416 | 1461.38 |
| B2-F96 | POST | 1413 | 1385 | 28 | 37.40 |

### Eventos nos limites da execução

| Condição | Inícios HTTP em ou após 150 s | Encerramentos após 150 s |
|---|---:|---:|
| B2-L | 1 | 2 |
| B2-A | 0 | 3 |
| B2-F | 0 | 2 |
| B2-F96 | 2 | 4 |

Esses registros permanecem nos dados processados. Inícios em ou após 150 s não entram nas taxas por fase; encerramentos posteriores não são deslocados artificialmente para a janela anterior.

As contagens por fase são atribuídas pelo instante de início HTTP. A B2-A registrou 476 timeouts legítimos entre requisições iniciadas em POST, evidenciando persistência da degradação após 60 s; B2-F96 registrou 28 e B2-F, nenhum. Um timeout iniciado próximo do fim de ACTIVE pode ocorrer em POST; os painéis de atendimento mostram encerramentos pelo instante do evento. As séries de CPU e memória preservam a cadência real das amostras Docker.

## F64 versus F96

A comparação específica registra RPS ofensivo iniciado de 54.07 em F64 e 49.87 em F96. Os sucessos legítimos da coorte ACTIVE foram 514 e 98, enquanto os timeouts foram 0 e 416. Esses dados são compatíveis com a observação exploratória de menor atendimento legítimo em F96 sem aumento do RPS ofensivo iniciado. Eles não isolam a concorrência como causa, pois não há repetição nem controle completo das condições ambientais. O relatório histórico da B2-F96 sugeria concorrência 64; a decisão posterior por 96 deve ser documentada cientificamente fora desta caracterização.

## Limitações metodológicas

Há uma realização por condição; amostras temporais e operações dentro da mesma execução não são repetições experimentais independentes. A1 e B1 foram realizadas em campanhas diferentes. B1-A3 e B1-F2 têm apenas tráfego ofensivo, o que muda a composição da carga. As condições ofensivas diferem em endpoint, intensidade e custo por operação. O endpoint `/expensive` não difere do `/medium` apenas por rótulo; parâmetros de trabalho podem variar. A CPU Docker tem cadência de cerca de 3 s e não é atribuível a uma classe. A duração HTTP inclui rede, cliente, espera pré-handler não medida, espera de worker e processamento. Timeouts não equivalem a falha ou interrupção do processamento da vítima. A captura TCP representa tráfego total e não foi atribuída a classes.

## Catálogo de figuras

Cada linha abaixo corresponde a uma figura em PNG de 300 dpi e PDF vetorial. As composições históricas são adequadas para contextualização visual; os painéis B2 e as figuras de degradação são candidatos à seleção posterior, sem seleção nesta etapa.

| Figura | Pergunta | Fonte | Métricas e cálculo | Observação | Limitação | Uso potencial |
|---|---|---|---|---|---|---|
| [B2-L_painel_completo](figures/b2_individuais/B2-L_painel_completo.png) | Evolução simultânea da carga e do atendimento legítimo | B2: request_log, victim_stats, eventos de work | RPS em 1 s; Docker nos timestamps reais; estados de workers por eventos; HTTP individual | B2-L: 515 sucessos e 0 timeouts legítimos em ACTIVE | Uma execução; associação temporal descritiva | Visão integrada |
| [B2-L_painel_compacto](figures/b2_individuais/B2-L_painel_compacto.png) | Evolução simultânea da carga e do atendimento legítimo | B2: request_log, victim_stats, eventos de work | RPS em 1 s; Docker nos timestamps reais; estados de workers por eventos; HTTP individual | B2-L: 515 sucessos e 0 timeouts legítimos em ACTIVE | Uma execução; associação temporal descritiva | Visão integrada |
| [B2-A_painel_completo](figures/b2_individuais/B2-A_painel_completo.png) | Evolução simultânea da carga e do atendimento legítimo | B2: request_log, victim_stats, eventos de work | RPS em 1 s; Docker nos timestamps reais; estados de workers por eventos; HTTP individual | B2-A: 43 sucessos e 471 timeouts legítimos em ACTIVE | Uma execução; associação temporal descritiva | Visão integrada |
| [B2-A_painel_compacto](figures/b2_individuais/B2-A_painel_compacto.png) | Evolução simultânea da carga e do atendimento legítimo | B2: request_log, victim_stats, eventos de work | RPS em 1 s; Docker nos timestamps reais; estados de workers por eventos; HTTP individual | B2-A: 43 sucessos e 471 timeouts legítimos em ACTIVE | Uma execução; associação temporal descritiva | Visão integrada |
| [B2-F_painel_completo](figures/b2_individuais/B2-F_painel_completo.png) | Evolução simultânea da carga e do atendimento legítimo | B2: request_log, victim_stats, eventos de work | RPS em 1 s; Docker nos timestamps reais; estados de workers por eventos; HTTP individual | B2-F: 514 sucessos e 0 timeouts legítimos em ACTIVE | Uma execução; associação temporal descritiva | Visão integrada |
| [B2-F_painel_compacto](figures/b2_individuais/B2-F_painel_compacto.png) | Evolução simultânea da carga e do atendimento legítimo | B2: request_log, victim_stats, eventos de work | RPS em 1 s; Docker nos timestamps reais; estados de workers por eventos; HTTP individual | B2-F: 514 sucessos e 0 timeouts legítimos em ACTIVE | Uma execução; associação temporal descritiva | Visão integrada |
| [B2-F96_painel_completo](figures/b2_individuais/B2-F96_painel_completo.png) | Evolução simultânea da carga e do atendimento legítimo | B2: request_log, victim_stats, eventos de work | RPS em 1 s; Docker nos timestamps reais; estados de workers por eventos; HTTP individual | B2-F: 514 sucessos e 0 timeouts legítimos em ACTIVE | Uma execução; associação temporal descritiva | Visão integrada |
| [B2-F96_painel_compacto](figures/b2_individuais/B2-F96_painel_compacto.png) | Evolução simultânea da carga e do atendimento legítimo | B2: request_log, victim_stats, eventos de work | RPS em 1 s; Docker nos timestamps reais; estados de workers por eventos; HTTP individual | B2-F: 514 sucessos e 0 timeouts legítimos em ACTIVE | Uma execução; associação temporal descritiva | Visão integrada |
| [assimetria_B2-L_B2-A_completa](figures/composicao_cargas/assimetria_B2-L_B2-A_completa.png) | Como as cargas isoladas diferem da execução simultânea | A1-L2 ou B2-L; B1-A3/F2; B2-A/F/F96 | Três colunas de séries temporais; mesma escala vertical por linha | Recursos e atendimento nas cargas isoladas e combinadas | Campanhas históricas; sem soma de CPU/memória | Contexto de cargas |
| [assimetria_B2-L_B2-A_compacta](figures/composicao_cargas/assimetria_B2-L_B2-A_compacta.png) | Como as cargas isoladas diferem da execução simultânea | A1-L2 ou B2-L; B1-A3/F2; B2-A/F/F96 | Três colunas de séries temporais; mesma escala vertical por linha | Recursos e atendimento nas cargas isoladas e combinadas | Campanhas históricas; sem soma de CPU/memória | Contexto de cargas |
| [assimetria_A1-L2_B2-A_completa](figures/composicao_cargas/assimetria_A1-L2_B2-A_completa.png) | Como as cargas isoladas diferem da execução simultânea | A1-L2 ou B2-L; B1-A3/F2; B2-A/F/F96 | Três colunas de séries temporais; mesma escala vertical por linha | Recursos e atendimento nas cargas isoladas e combinadas | Campanhas históricas; sem soma de CPU/memória | Contexto de cargas |
| [assimetria_A1-L2_B2-A_compacta](figures/composicao_cargas/assimetria_A1-L2_B2-A_compacta.png) | Como as cargas isoladas diferem da execução simultânea | A1-L2 ou B2-L; B1-A3/F2; B2-A/F/F96 | Três colunas de séries temporais; mesma escala vertical por linha | Recursos e atendimento nas cargas isoladas e combinadas | Campanhas históricas; sem soma de CPU/memória | Contexto de cargas |
| [flooding_B2-L_B2-F_completa](figures/composicao_cargas/flooding_B2-L_B2-F_completa.png) | Como as cargas isoladas diferem da execução simultânea | A1-L2 ou B2-L; B1-A3/F2; B2-A/F/F96 | Três colunas de séries temporais; mesma escala vertical por linha | Recursos e atendimento nas cargas isoladas e combinadas | Campanhas históricas; sem soma de CPU/memória | Contexto de cargas |
| [flooding_B2-L_B2-F_compacta](figures/composicao_cargas/flooding_B2-L_B2-F_compacta.png) | Como as cargas isoladas diferem da execução simultânea | A1-L2 ou B2-L; B1-A3/F2; B2-A/F/F96 | Três colunas de séries temporais; mesma escala vertical por linha | Recursos e atendimento nas cargas isoladas e combinadas | Campanhas históricas; sem soma de CPU/memória | Contexto de cargas |
| [flooding_A1-L2_B2-F_completa](figures/composicao_cargas/flooding_A1-L2_B2-F_completa.png) | Como as cargas isoladas diferem da execução simultânea | A1-L2 ou B2-L; B1-A3/F2; B2-A/F/F96 | Três colunas de séries temporais; mesma escala vertical por linha | Recursos e atendimento nas cargas isoladas e combinadas | Campanhas históricas; sem soma de CPU/memória | Contexto de cargas |
| [flooding_A1-L2_B2-F_compacta](figures/composicao_cargas/flooding_A1-L2_B2-F_compacta.png) | Como as cargas isoladas diferem da execução simultânea | A1-L2 ou B2-L; B1-A3/F2; B2-A/F/F96 | Três colunas de séries temporais; mesma escala vertical por linha | Recursos e atendimento nas cargas isoladas e combinadas | Campanhas históricas; sem soma de CPU/memória | Contexto de cargas |
| [flooding_B2-L_B2-F96_completa](figures/composicao_cargas/flooding_B2-L_B2-F96_completa.png) | Como as cargas isoladas diferem da execução simultânea | A1-L2 ou B2-L; B1-A3/F2; B2-A/F/F96 | Três colunas de séries temporais; mesma escala vertical por linha | Recursos e atendimento nas cargas isoladas e combinadas | Campanhas históricas; sem soma de CPU/memória | Contexto de cargas |
| [flooding_B2-L_B2-F96_compacta](figures/composicao_cargas/flooding_B2-L_B2-F96_compacta.png) | Como as cargas isoladas diferem da execução simultânea | A1-L2 ou B2-L; B1-A3/F2; B2-A/F/F96 | Três colunas de séries temporais; mesma escala vertical por linha | Recursos e atendimento nas cargas isoladas e combinadas | Campanhas históricas; sem soma de CPU/memória | Contexto de cargas |
| [flooding_A1-L2_B2-F96_completa](figures/composicao_cargas/flooding_A1-L2_B2-F96_completa.png) | Como as cargas isoladas diferem da execução simultânea | A1-L2 ou B2-L; B1-A3/F2; B2-A/F/F96 | Três colunas de séries temporais; mesma escala vertical por linha | Recursos e atendimento nas cargas isoladas e combinadas | Campanhas históricas; sem soma de CPU/memória | Contexto de cargas |
| [flooding_A1-L2_B2-F96_compacta](figures/composicao_cargas/flooding_A1-L2_B2-F96_compacta.png) | Como as cargas isoladas diferem da execução simultânea | A1-L2 ou B2-L; B1-A3/F2; B2-A/F/F96 | Três colunas de séries temporais; mesma escala vertical por linha | Recursos e atendimento nas cargas isoladas e combinadas | Campanhas históricas; sem soma de CPU/memória | Contexto de cargas |
| [matriz_rps](figures/comparativas/matriz_rps.png) | Comparação temporal das quatro condições B2 | B2: request_log.csv | Eventos HTTP em janelas de 1 s pelo timestamp próprio | Inícios legítimos persistiram; respostas e timeouts diferiram | Taxas de início e encerramento têm critérios distintos | Atendimento temporal |
| [matriz_cpu](figures/comparativas/matriz_cpu.png) | Comparação temporal das quatro condições B2 | B2: registros primários conforme manifesto | Série ou distribuição descritiva indicada pelo eixo | Comparação temporal entre quatro condições | Uma execução por condição | Inspeção exploratória |
| [matriz_mem](figures/comparativas/matriz_mem.png) | Comparação temporal das quatro condições B2 | B2: victim_stats.raw_mem_usage | Conversão bytes/1048576; amostras reais e distribuições | Memória variou em todas as execuções, inclusive B2-L | Memória do contêiner, não atribuível a classe | Uso de memória |
| [matriz_run](figures/comparativas/matriz_run.png) | Comparação temporal das quatro condições B2 | B2: work_submitted/started/completed | Reconstrução orientada a eventos; frações de tempo e espera em ms | Dois workers ficaram ocupados por >97% da fase ACTIVE nas condições ofensivas | Aguardando não é profundidade exata da fila interna | Disputa computacional |
| [matriz_wait](figures/comparativas/matriz_wait.png) | Comparação temporal das quatro condições B2 | B2: work_submitted/started/completed | Reconstrução orientada a eventos; frações de tempo e espera em ms | Dois workers ficaram ocupados por >97% da fase ACTIVE nas condições ofensivas | Aguardando não é profundidade exata da fila interna | Disputa computacional |
| [matriz_cpuop](figures/comparativas/matriz_cpuop.png) | Comparação temporal das quatro condições B2 | B2: eventos de work | Pontos individuais por instante de submissão | Operações legítimas e ofensivas mostram custos e esperas distintos | Espera de worker não é espera HTTP total | Operações computacionais |
| [matriz_waitms](figures/comparativas/matriz_waitms.png) | Comparação temporal das quatro condições B2 | B2: work_submitted/started/completed | Reconstrução orientada a eventos; frações de tempo e espera em ms | Dois workers ficaram ocupados por >97% da fase ACTIVE nas condições ofensivas | Aguardando não é profundidade exata da fila interna | Disputa computacional |
| [matriz_duration](figures/comparativas/matriz_duration.png) | Comparação temporal das quatro condições B2 | B2: request_log.csv | Pontos individuais por início HTTP; 2xx e timeout separados | A duração legítima cresceu durante as condições ofensivas | Timeout é tempo até encerramento no cliente | Duração HTTP |
| [matriz_outcomes](figures/comparativas/matriz_outcomes.png) | Comparação temporal das quatro condições B2 | B2: request_log.csv | Eventos HTTP em janelas de 1 s pelo timestamp próprio | Inícios legítimos persistiram; respostas e timeouts diferiram | Taxas de início e encerramento têm critérios distintos | Atendimento temporal |
| [matriz_network](figures/comparativas/matriz_network.png) | Comparação temporal das quatro condições B2 | B2: traffic_capture.csv | Contagem de pacotes TCP em janelas de 1 s | A captura permite inspecionar variação temporal do volume | Pacotes não são requisições HTTP; classe não atribuída | Contexto de rede |
| [matriz_mem_escala_individual](figures/comparativas/matriz_mem_escala_individual.png) | Comparação temporal das quatro condições B2 | B2: victim_stats.raw_mem_usage | Conversão bytes/1048576; amostras reais e distribuições | Memória variou em todas as execuções, inclusive B2-L | Memória do contêiner, não atribuível a classe | Uso de memória |
| [matriz_duration_escala_individual](figures/comparativas/matriz_duration_escala_individual.png) | Comparação temporal das quatro condições B2 | B2: request_log.csv | Pontos individuais por início HTTP; 2xx e timeout separados | A duração legítima cresceu durante as condições ofensivas | Timeout é tempo até encerramento no cliente | Duração HTTP |
| [matriz_wait_escala_individual](figures/comparativas/matriz_wait_escala_individual.png) | Comparação temporal das quatro condições B2 | B2: work_submitted/started/completed | Reconstrução orientada a eventos; frações de tempo e espera em ms | Dois workers ficaram ocupados por >97% da fase ACTIVE nas condições ofensivas | Aguardando não é profundidade exata da fila interna | Disputa computacional |
| [temporal_completo](figures/flooding_64_vs_96/temporal_completo.png) | Comparação direta F64 versus F96 | B2-F e B2-F96: request_log, Docker, work | Indicadores ou séries por condição; coorte ACTIVE quando agregado | F96: 49,87 RPS ofensivos e 416 timeouts legítimos; F64: 54,07 RPS e 0 timeouts | Uma execução por concorrência | Comparação de concorrência |
| [temporal_compacto](figures/flooding_64_vs_96/temporal_compacto.png) | Comparação direta F64 versus F96 | B2-F e B2-F96: request_log, Docker, work | Indicadores ou séries por condição; coorte ACTIVE quando agregado | F96: 49,87 RPS ofensivos e 416 timeouts legítimos; F64: 54,07 RPS e 0 timeouts | Uma execução por concorrência | Comparação de concorrência |
| [desfechos_absoluto](figures/degradacao_legitima/desfechos_absoluto.png) | Quais tentativas legítimas tiveram resposta ou timeout? | B2: request_log; work quando indicado | Desfechos por coorte; duração 2xx e timeout separadas; ECDF/boxplot/fases | B2-A e B2-F96 tiveram mais timeouts; B2-F teve maior duração de respostas | Sucessos sobreviventes não representam todas as tentativas | Atendimento legítimo |
| [desfechos_percentual](figures/degradacao_legitima/desfechos_percentual.png) | Quais tentativas legítimas tiveram resposta ou timeout? | B2: request_log; work quando indicado | Desfechos por coorte; duração 2xx e timeout separadas; ECDF/boxplot/fases | B2-A e B2-F96 tiveram mais timeouts; B2-F teve maior duração de respostas | Sucessos sobreviventes não representam todas as tentativas | Atendimento legítimo |
| [distribuicao_cpu](figures/cpu/distribuicao_cpu.png) | Distribuição comparativa entre condições | B2: victim_stats e eventos de work | Amostras Docker reais; CPU/operação por evento; fases ou distribuições | CPU Docker ACTIVE foi maior nas condições com ataque que na B2-L | CPU Docker não é CPU por classe; sem inferência causal | Pressão computacional |
| [distribuicao_memoria](figures/memoria/distribuicao_memoria.png) | Distribuição comparativa entre condições | B2: victim_stats.raw_mem_usage | Conversão bytes/1048576; amostras reais e distribuições | Memória variou em todas as execuções, inclusive B2-L | Memória do contêiner, não atribuível a classe | Uso de memória |
| [cpu_operacao_legitima](figures/cpu/cpu_operacao_legitima.png) | Distribuição comparativa entre condições | B2: victim_stats e eventos de work | Amostras Docker reais; CPU/operação por evento; fases ou distribuições | CPU Docker ACTIVE foi maior nas condições com ataque que na B2-L | CPU Docker não é CPU por classe; sem inferência causal | Pressão computacional |
| [espera_legitima](figures/workers/espera_legitima.png) | Distribuição comparativa entre condições | B2: work_submitted/started/completed | Reconstrução orientada a eventos; frações de tempo e espera em ms | Dois workers ficaram ocupados por >97% da fase ACTIVE nas condições ofensivas | Aguardando não é profundidade exata da fila interna | Disputa computacional |
| [cpu_operacao_ofensiva](figures/cpu/cpu_operacao_ofensiva.png) | Distribuição comparativa entre condições | B2: victim_stats e eventos de work | Amostras Docker reais; CPU/operação por evento; fases ou distribuições | CPU Docker ACTIVE foi maior nas condições com ataque que na B2-L | CPU Docker não é CPU por classe; sem inferência causal | Pressão computacional |
| [espera_ofensiva](figures/workers/espera_ofensiva.png) | Distribuição comparativa entre condições | B2: work_submitted/started/completed | Reconstrução orientada a eventos; frações de tempo e espera em ms | Dois workers ficaram ocupados por >97% da fase ACTIVE nas condições ofensivas | Aguardando não é profundidade exata da fila interna | Disputa computacional |
| [duracao_sucessos](figures/degradacao_legitima/duracao_sucessos.png) | Distribuição comparativa entre condições | B2: request_log; work quando indicado | Desfechos por coorte; duração 2xx e timeout separadas; ECDF/boxplot/fases | B2-A e B2-F96 tiveram mais timeouts; B2-F teve maior duração de respostas | Sucessos sobreviventes não representam todas as tentativas | Atendimento legítimo |
| [tempo_ate_timeout](figures/degradacao_legitima/tempo_ate_timeout.png) | Distribuição comparativa entre condições | B2: request_log; work quando indicado | Desfechos por coorte; duração 2xx e timeout separadas; ECDF/boxplot/fases | B2-A e B2-F96 tiveram mais timeouts; B2-F teve maior duração de respostas | Sucessos sobreviventes não representam todas as tentativas | Atendimento legítimo |
| [taxas_legitimas](figures/degradacao_legitima/taxas_legitimas.png) | Taxa nominal, inícios e desfechos legítimos | B2: request_log; work quando indicado | Desfechos por coorte; duração 2xx e timeout separadas; ECDF/boxplot/fases | B2-A e B2-F96 tiveram mais timeouts; B2-F teve maior duração de respostas | Sucessos sobreviventes não representam todas as tentativas | Atendimento legítimo |
| [rps_por_fase](figures/degradacao_legitima/rps_por_fase.png) | Diferenças descritivas por fase | B2: request_log; work quando indicado | Desfechos por coorte; duração 2xx e timeout separadas; ECDF/boxplot/fases | B2-A e B2-F96 tiveram mais timeouts; B2-F teve maior duração de respostas | Sucessos sobreviventes não representam todas as tentativas | Atendimento legítimo |
| [timeouts_por_fase](figures/degradacao_legitima/timeouts_por_fase.png) | Diferenças descritivas por fase | B2: request_log; work quando indicado | Desfechos por coorte; duração 2xx e timeout separadas; ECDF/boxplot/fases | B2-A e B2-F96 tiveram mais timeouts; B2-F teve maior duração de respostas | Sucessos sobreviventes não representam todas as tentativas | Atendimento legítimo |
| [duracao_por_fase](figures/degradacao_legitima/duracao_por_fase.png) | Diferenças descritivas por fase | B2: request_log; work quando indicado | Desfechos por coorte; duração 2xx e timeout separadas; ECDF/boxplot/fases | B2-A e B2-F96 tiveram mais timeouts; B2-F teve maior duração de respostas | Sucessos sobreviventes não representam todas as tentativas | Atendimento legítimo |
| [cpu_por_fase](figures/cpu/cpu_por_fase.png) | Diferenças descritivas por fase | B2: victim_stats e eventos de work | Amostras Docker reais; CPU/operação por evento; fases ou distribuições | CPU Docker ACTIVE foi maior nas condições com ataque que na B2-L | CPU Docker não é CPU por classe; sem inferência causal | Pressão computacional |
| [memoria_por_fase](figures/memoria/memoria_por_fase.png) | Diferenças descritivas por fase | B2: victim_stats.raw_mem_usage | Conversão bytes/1048576; amostras reais e distribuições | Memória variou em todas as execuções, inclusive B2-L | Memória do contêiner, não atribuível a classe | Uso de memória |
| [ocupacao_e_acumulo](figures/workers/ocupacao_e_acumulo.png) | Workers ocupados e operações aguardando | B2: work_submitted/started/completed | Reconstrução orientada a eventos; frações de tempo e espera em ms | Dois workers ficaram ocupados por >97% da fase ACTIVE nas condições ofensivas | Aguardando não é profundidade exata da fila interna | Disputa computacional |
| [indicadores](figures/flooding_64_vs_96/indicadores.png) | Como F64 e F96 diferiram na fase ofensiva? | B2-F e B2-F96: request_log, Docker, work | Indicadores ou séries por condição; coorte ACTIVE quando agregado | F96: 49,87 RPS ofensivos e 416 timeouts legítimos; F64: 54,07 RPS e 0 timeouts | Uma execução por concorrência | Comparação de concorrência |
| [pressao_atendimento_B2-L](figures/cpu/pressao_atendimento_B2-L.png) | Coincidência temporal de CPU, workers, espera e atendimento | B2: victim_stats e eventos de work | Amostras Docker reais; CPU/operação por evento; fases ou distribuições | CPU Docker ACTIVE foi maior nas condições com ataque que na B2-L | CPU Docker não é CPU por classe; sem inferência causal | Pressão computacional |
| [rede_B2-L](figures/comparativas/rede_B2-L.png) | Volume de pacotes TCP | B2: traffic_capture.csv | Contagem de pacotes TCP em janelas de 1 s | A captura permite inspecionar variação temporal do volume | Pacotes não são requisições HTTP; classe não atribuída | Contexto de rede |
| [pressao_atendimento_B2-A](figures/cpu/pressao_atendimento_B2-A.png) | Coincidência temporal de CPU, workers, espera e atendimento | B2: victim_stats e eventos de work | Amostras Docker reais; CPU/operação por evento; fases ou distribuições | CPU Docker ACTIVE foi maior nas condições com ataque que na B2-L | CPU Docker não é CPU por classe; sem inferência causal | Pressão computacional |
| [rede_B2-A](figures/comparativas/rede_B2-A.png) | Volume de pacotes TCP | B2: traffic_capture.csv | Contagem de pacotes TCP em janelas de 1 s | A captura permite inspecionar variação temporal do volume | Pacotes não são requisições HTTP; classe não atribuída | Contexto de rede |
| [pressao_atendimento_B2-F](figures/cpu/pressao_atendimento_B2-F.png) | Coincidência temporal de CPU, workers, espera e atendimento | B2: victim_stats e eventos de work | Amostras Docker reais; CPU/operação por evento; fases ou distribuições | CPU Docker ACTIVE foi maior nas condições com ataque que na B2-L | CPU Docker não é CPU por classe; sem inferência causal | Pressão computacional |
| [rede_B2-F](figures/comparativas/rede_B2-F.png) | Volume de pacotes TCP | B2: traffic_capture.csv | Contagem de pacotes TCP em janelas de 1 s | A captura permite inspecionar variação temporal do volume | Pacotes não são requisições HTTP; classe não atribuída | Contexto de rede |
| [pressao_atendimento_B2-F96](figures/cpu/pressao_atendimento_B2-F96.png) | Coincidência temporal de CPU, workers, espera e atendimento | B2: victim_stats e eventos de work | Amostras Docker reais; CPU/operação por evento; fases ou distribuições | CPU Docker ACTIVE foi maior nas condições com ataque que na B2-L | CPU Docker não é CPU por classe; sem inferência causal | Pressão computacional |
| [rede_B2-F96](figures/comparativas/rede_B2-F96.png) | Volume de pacotes TCP | B2: traffic_capture.csv | Contagem de pacotes TCP em janelas de 1 s | A captura permite inspecionar variação temporal do volume | Pacotes não são requisições HTTP; classe não atribuída | Contexto de rede |

## Reprodução e validação

Da raiz do repositório:

```bash
python3 reports/b2_combined_characterization_20261112/scripts/generate.py
python3 reports/b2_combined_characterization_20261112/scripts/write_report.py
python3 reports/b2_combined_characterization_20261112/scripts/validate.py
```

Dependências: Python 3, pandas, NumPy, Matplotlib e Pillow (para validação dos PNG). O manifesto registra SHA-256 dos arquivos primários e scripts, parâmetros e saídas. `validation/checks.json` e `validation/result.json` documentam as verificações. Entradas originais são somente leitura.
