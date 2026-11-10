# Contrato de análise definido antes dos cálculos

Análise offline de todas as entradas TEST do plano energy-powersaver-20261109 (20 por cenário). Não incluir calibrações ou warmup. Tempo relativo = CLOCK_MONOTONIC − diagnostics/metadata.json:origin_monotonic − 150 s. WARMUP [0,30), PRE [30,150), ACTIVE [150,270), POST [270,390), em segundos da execução. Intervalos semiabertos. L2 usa as mesmas fronteiras nominais.

| Variável | Origem | Unidade, relógio e resolução | Denominador / inclusão |
|---|---|---|---|
| Planejamento legítimo | source_artifacts/*/output/diagnostics/events.jsonl, planned_at | eventos; monotônico, resolução declarada pelo relógio | contagem por segundo planejado |
| Planejamento ofensivo | configuração e journal de admissão | RPS nominal; não existe evento independente planned ofensivo | nominal × 120 é referência configurada, nunca contagem observada |
| Admissão ofensiva | journal.jsonl, admission.elapsed_seconds | eventos; relógio compartilhado relativo | contagem por segundo de admissão |
| Tentativa submetida / tarefa iniciada | eventos submitted/task_started da fonte | eventos; monotônico | contagem pelo próprio timestamp |
| HTTP iniciado | request_log.csv:elapsed_seconds e eventos http_started da fonte | requisições; monotônico relativo | contagem por início; inclui todos os resultados finais |
| HTTP recebido | vítima: handler_started com identidade declarada | requisições; monotônico | contagem por recepção; não equivale ao início no cliente |
| Trabalho submetido/iniciado/concluído | vítima: work_submitted.at, work_started.at, work_completed.work_finished_at | operações; monotônico | contagens de eventos na janela; coortes de espera/custo pela submissão |
| Pendências / aguardando / workers | intervalos [submit,finish), [submit,start), [start,finish) | operações ou slots; integração exata no tempo | área / duração da janela; snapshot e pico também exportados |
| Espera submit→worker | work_started.at − work_submitted.at | ms | operações submetidas na janela, mesmo concluindo depois |
| Custo CPU por operação | work_completed.work_cpu_seconds | ms de CPU do worker | operações submetidas na janela |
| 2xx / timeout / duração | request_log.csv, status, error_type, duration_ms | requisições / ms | coorte por início HTTP, término posterior preservado; sucesso = 2xx / inícios; timeout não é resposta |
| Expiração anterior ao HTTP | journal task_resolution:expired_before_http | tentativas | coorte de submissão da fonte; série adicional pelo instante de resolução quando disponível |
| CPU vítima | victim_stats.jsonl:state=valid,cpu_percent | % Docker, 100% = um núcleo lógico | amostras nativas próximas de 1 s, atribuídas ao segundo de received_seconds; sem interpolar; intervalo de medição atravessa fronteiras |
| Recuperação operacional registrada | receipt/manifest.json, operational service evidence | booleano e janelas de 30 s | reproduzir o registro, sem substituir seu critério |

Validar certificados comparable das fontes e vítima; comprovação por namespace/offsets nativos e amostras entre host_before/host_after, não presumir sincronismo UTC. Conservar evidências e hashes. Resolução nominal de CLOCK_MONOTONIC não equivale à exatidão física: bins de 1 s são agregação descritiva, não prova de ordenação causal submilissegundo entre processos.

Séries de 1 s: contar eventos na janela e integrar intervalos sem arredondar timestamps. Resultados HTTP atribuídos à coorte de início; exportar também terminais pelo instante de término. Valores sem observação ficam ausentes, nunca sucesso zero. Agregar primeiro cada execução e depois calcular média, mediana, desvio-padrão amostral, quartis, mínimo e máximo entre execuções; segundos não são réplicas independentes. Figuras: média e IQR, sem suavização; disponibilidade exibida em coortes não sobrepostas de 5 s para leitura, mantendo CSV de 1 s.

Recuperação descritiva (não altera critério experimental): primeiro bloco de 5 s do POST com pendência média ≤ percentil 95 das médias de 1 s do PRE, mantido por 3 blocos (15 s); também primeiro instante de fila aguardando vazia. Disponibilidade: primeira sequência de três coortes de 5 s com sucesso ≥99%, e adicionalmente início do sufixo POST sem qualquer falha entre inícios HTTP. Esses limites são definições exploratórias explícitas, não testes de detectores nem equivalência estatística com PRE. Tempos de confirmação incluem os 15 s, tempos de início são reportados separadamente. Censurar se não observado até 390 s.

H3 será examinada por identidade: término computacional posterior ao timeout cliente da mesma request_id, e interseção temporal positiva do processamento do worker com o período posterior ao timeout. Não inferir a partir apenas de contagens agregadas.
