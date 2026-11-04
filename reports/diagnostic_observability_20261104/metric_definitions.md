# Dicionário da telemetria diagnóstica v1

Esta telemetria não integra `feature_schema.json`, as tabelas científicas ou a entrada dos detectores. A implementação está em `simulator/diagnostics.py`, `simulator/app/simple_server.py` e `experiments/summarize_diagnostics.py`.

## Convenções e confiabilidade

- Timestamps novos `at` e `*_at`: segundos de `time.monotonic()` no processo observador, sem converter para epoch. Metadados registram implementação, unidade, resolução declarada, PID e namespace de tempo. A resolução declarada de 1 ns não é garantia de precisão ou de custo de medição de 1 ns.
- Eventos HTTP da fonte reutilizam exatamente `elapsed_seconds`/`end_elapsed_seconds` científicos. `at = origem_monotônica + elapsed` é uma reconstrução desse mesmo instante, não uma segunda amostragem do início/fim.
- A origem do experimento e o horizonte planejado `[0,T)` vêm do status/configuração. A drenagem posterior é outro horizonte. Contagens por segundo usam `[i,i+1)`; o bin final parcial é explicitamente identificado quando T não é inteiro.
- Campos ausentes significam etapa não observada. Estatísticas sem amostras são `null`, nunca tempo zero. Contagens zero só representam ausência de eventos em registros considerados completos.
- Arquivos JSONL podem conter eventos emitidos fora da ordem de seus timestamps: `planned` é registrado retrospectivamente após a espera. Ordem física de escrita não substitui a ordem temporal; analisar por ID e pelos timestamps apropriados.
- IDs de diagnóstico são únicos no escopo `(run_id, source_id, attempt_id)`. `request_id` científico é ligado ao ID diagnóstico pelo evento HTTP da fonte. O cabeçalho **já existente** `X-Edos-Request-Id` permite ligar esse ID ao handler. Nenhum novo cabeçalho foi introduzido.
- A vítima registra `run_id=null`; o vínculo da execução é o diretório exclusivo, `diagnostics/metadata.json`, status e inventários. Sondagens de preparação não têm ID científico e são contadas separadamente. Não há associação por proximidade temporal.
- Durações de fonte são calculadas no próprio domínio da fonte. Durações de handler/worker só são agregadas quando o namespace do worker coincide com o do handler. A atribuição dos handlers à origem do host requer também a auditoria de relógios da vítima; o fluxo a executa antes da origem experimental. Não são calculadas latências de rede unidirecionais fonte→vítima.
- `events.summary.json` deve existir, ter `complete=true`, zero descartes/erros e contagem de linhas correspondente. Um arquivo faltante, JSON truncado, resumo ausente, divergência de contadores ou registros científicos é falha/inconclusão diagnóstica, não zero eventos. Erros impedem a aprovação do resumo offline. Os dados científicos não dependem da aprovação diagnóstica.
- A fila de escrita comporta 4096 registros por padrão, configuráveis por inteiro positivo. Produtores usam `put_nowait`. O writer usa buffer de arquivo de 64 KiB; não faz fsync por requisição. O resumo é escrito após drenagem e fechamento do arquivo. Fechamento abrupto pode deixar buffer ou resumo incompletos; não há promessa de persistência sob SIGKILL.

## Eventos da fonte

Todos carregam contexto de execução/fonte, tipo `kind` e `at`. A unidade dos instantes/intervalos é segundo.

| Evento/campo | Definição e ponto observado | Inclusão e ausências | Limitação |
|---|---|---|---|
| `planned` | Sorteio existente do gerador legítimo: `planned_at = wait_started_at + sampled_interval` | Registrado após a espera real retornar, inclusive se interrompida; inclui a última oportunidade posterior a T | É prazo relativo à espera real, não agenda cumulativa independente; uma interrupção abrupta durante a espera pode impedir seu registro |
| `sampled_interval` | Valor realmente retornado por `rng.expovariate(rate)` | Todos os sorteios observados, inclusive último intervalo censurado | O tamanho da amostra depende do término; não é prova de independência do processo realizado |
| `submitted` / `at` | Instante imediatamente antes da chamada pública `Executor.submit` | Toda chamada, inclusive a que depois recebe `rejected` | Não é timestamp interno de enfileiramento nem instante de aceitação; inclui custo do próprio registro antes da chamada |
| `submitted.planned_at` | Prazo relativo associado à próxima chamada | `null` no primeiro despacho imediato ou quando o planejamento não foi observado | O primeiro envio não possui um prazo independente a reconstruir; não se inventa esse valor |
| `task_started` | Entrada na função wrapper executada por uma thread do executor | Só tarefas que efetivamente entram no wrapper | Antecede `RequestLogger.begin`; não é início HTTP nem chegada à vítima |
| `http_started` | Mesmo início científico de `RequestLogger.begin` | Cada tentativa admitida pelo logger, uma vez | Ocorre antes da persistência do journal e da chamada Requests; não é aceitação TCP ou recebimento no servidor |
| `http_finished` | Mesmo fim científico observado pelo cliente e entregue ao logger | Tentativas com conclusão/falha observada, com `outcome`, status e tipo de erro quando disponíveis | `requests.get` normal inclui recepção do corpo; não é tempo de CPU |
| `task_finished` | Saída da função enviada ao executor, inclusive por exceção | Contém `error_type` quando a função propagou exceção | Pode ocorrer após o fim HTTP devido a contadores/persistência; falha HTTP tratada não implica exceção da tarefa |
| `cancelled` | Callback público de Future que confirma `Future.cancelled()` | Somente cancelamento realmente observado | O diagnóstico não cancela tarefas; ausência de evento não prova que uma tarefa nunca ficará pendente |
| `rejected` | `Executor.submit` lançou exceção | A chamada foi observada, mas não há Future aceito | Separar de cancelamento e de falha HTTP |
| `source_closed` | Snapshot dos contadores após a política existente de drenagem | Registra também `drained` e `logger_complete` | Drenagem falsa ou evento ausente impede afirmar fechamento completo |
| `target_url` / endpoint | URL já escolhida pelo gerador, disponível em submissão e eventos HTTP | Prazo futuro ainda não tem URL resolvida; endpoint/configuração continuam conhecidos | Não antecipa a resolução do destino para fabricar planejamento |

O módulo ofensivo não foi editado. O adaptador genérico pode observar suas chamadas públicas de executor e os eventos comuns do logger, mas o planejamento ofensivo não recebeu hooks. Nessa origem, prazos ausentes permanecem desconhecidos. Essa capacidade não foi validada com tráfego ofensivo nesta intervenção.

## Métricas derivadas da fonte

Período padrão: ciclo completo da fonte até `source_closed`, salvo os campos explicitamente restritos a `[0,T)`. Contagens usam unidade evento/tentativa; taxas usam eventos/s; atrasos usam segundos no JSON.

| Nome | Definição | Ausência/limitação |
|---|---|---|
| `nominal_rps` | Configuração por fonte legítima; agregado nominal = fontes × taxa | Não é quantidade determinística por segundo nem medição de chegada |
| `counts` | Contagens diretas de cada `kind` no JSONL | Exigem writer completo; são conferidas contra o snapshot final |
| `counters.submitted/task_started/task_finished/cancelled/rejected` | Contadores próprios incrementados nos respectivos pontos observados | Não consultam `_work_queue`, `_pending_work_items` ou profundidade privada de executor |
| Submissões aceitas após fechamento | `submitted - rejected` | Derivada; não fornece instante exato da aceitação |
| `planned_within_plan` | Prazos amostrados com `0 <= planned_at-origem < T` | Exclui primeiros despachos sem prazo independente |
| `planned_after_plan` | Prazos amostrados em ou após T | Inclui futuras oportunidades normalmente não submetidas e eventuais submissões de cauda; não representa perda |
| `planned_not_submitted_in_plan` | IDs com prazo em `[0,T)` e sem evento de submissão até fechamento | Oportunidade não realizada observada, não necessariamente defeito ou perda de requisição; interpretar encerramento e completude |
| `submitted_not_started` | IDs de chamada a submit sem evento `http_started` | Pode incluir rejeição, cancelamento ou falha anterior ao HTTP; não é automaticamente perda operacional |
| `unresolved_tasks` | Submissão sem `task_started`, `cancelled` ou `rejected` até fechamento | Ausência de resolução observada; depende de logs completos e drenagem |
| `task_failures` | `task_finished` com exceção propagada | Diferente de respostas HTTP >=400 e timeouts tratados pelo gerador |
| Falhas HTTP | Eventos científicos/diagnósticos com `http_error`, `transport_error` ou `client_error` | Tentativas incompletas permanecem separadas; não ganham duração |
| `plan_to_submit` | `submitted.at - planned.planned_at`, por ID | Só pares disponíveis no mesmo domínio; primeiro despacho não tem essa duração |
| `submit_to_task` | `task_started.at - submitted.at` | Inclui despacho, registro e espera; não mede isoladamente fila interna |
| `submit_to_http` | `http_started.at - submitted.at` | Inclui espera de executor e caminho até o início científico; não integra a duração HTTP científica |
| `plan_to_http` | `http_started.at - planned.planned_at` | Só IDs com prazo observado; inclui atrasos operacionais e instrumentação |
| `http_peak/http_active_at_end` | Máximo e saldo do sweep de inícios/fins HTTP científicos observados | Concorrência no cliente; não representa número de conexões nem de handlers na vítima |
| `submitted_not_task_started_peak` | Máximo dos snapshots `submitted - task_started - cancelled - rejected` | Diferença observada, incluindo chamadas ainda em despacho; **não é profundidade exata de fila** |
| `first_dispatch_unplanned` | Submissões sem prazo independente associado | Nas execuções legítimas foi uma por fonte; em origem não instrumentada para planejamento pode significar planejamento indisponível |
| `counts_per_second` | Vetores separados de prazos, submissões e inícios HTTP em `[i,i+1)` dentro de `[0,T)` | Prazos excluem primeiro despacho; migração entre bins não é descarte |

## Eventos e métricas da vítima

`handler_started` e `handler_finished` são observações de `do_GET`. O início ocorre após o parser da linha/cabeçalhos HTTP; não mede aceitação TCP, primeiro byte ou recebimento de corpo arbitrário. O fim ocorre após `wfile.write` retornar ou após exceção; não confirma recepção integral pelo cliente. Keep-alive permite vários handlers sucessivos na mesma thread/conexão. Contadores excluem conexões ociosas.

| Campo/métrica | Definição, relógio e unidade | Inclusão/ausências e limitações |
|---|---|---|
| `handler_started_at` | Entrada no wrapper de `do_GET`, monotônico, s | GETs que chegaram a esse handler; não observa falhas anteriores no parser |
| `work_submitted_at` | Antes da chamada pública ao pool de processos, monotônico do handler, s | Ausente se o processamento falhar antes desse ponto; não é inserção interna na fila |
| `work_started_at` | Início do wrapper no processo worker, monotônico do worker, s | Devolvido somente quando o trabalho retorna; dados parciais podem faltar em falha/morte do worker |
| `work_finished_at` | Após o kernel computacional retornar, monotônico do worker, s | Não é término do handler nem envio da resposta |
| `work_result_observed_at` | Retorno de `.result()` no handler, monotônico, s | Inclui transporte do resultado e escalonamento do handler |
| `handler_finished_at` | Final do bloco de atendimento após escrita/erro, monotônico, s | Não é ACK TCP ou confirmação de recepção no cliente |
| `work_cpu_seconds` | Diferença de `time.process_time()` no worker em torno do kernel, s de CPU do processo | Diagnóstico opcional; não substitui a CPU Docker. Exclui espera anterior, não mede CPU do handler e não é duração em relógio |
| `active_handlers_at_start/finish` | Contador próprio sob lock na entrada/saída de `do_GET`, handlers | Snapshot direto de handlers ativos; não inclui threads esperando próxima requisição keep-alive |
| `http_status/error_type` | Status entregue a `send_response` e exceção observada no handler | Status 200 pode coexistir com erro posterior de escrita; não prova sucesso no cliente |
| `handler_to_submit` | Submissão − início do handler, s | Mesmo relógio do handler; inclui parsing do endpoint e custo diagnóstico inicial |
| `work_wait` | Início no worker − chamada submit no handler, s | Inclui despacho, serialização, IPC, fila, escalonamento e inicialização; não é fila pura |
| `work_wall` | Fim − início no worker, s em relógio | Inclui preempção; não equivale a CPU individual |
| `work_result_transport` | Observação do resultado − fim no worker, s | Inclui IPC e retomada do handler; requer comparabilidade dos relógios |
| `post_work_handler` | Fim do handler − fim no worker, s | Inclui transporte do resultado, eventual sleep legado, preparo e escrita; não inclui confirmação pelo cliente |
| `handler_wall` | Fim − início do handler, s | Diferente da duração HTTP do cliente |
| `handler_starts/finishes/errors` | Contagens de eventos ligados a IDs científicos desta execução | Sondagens sem ID científico são separadas em `unattributed_setup_handlers` |
| `matched_request_ids` | IDs com handler finalizado e correspondência explícita ao registro científico | Ausências não são pareadas por similaridade temporal |
| `client_attempts_without_completed_handler` | IDs científicos sem finalização observada na vítima | Pode refletir erro de conexão, parser, timeout, handler pendente ou perda de diagnóstico; não classificar sem contexto |
| `peak_handlers` | Maior snapshot de handlers ativos nas entradas científicas | Snapshot inclui todos os handlers ativos naquele instante; sondagens de preparação já haviam terminado nas validações |
| `incomplete_handlers_observed` | Inícios científicos − finais científicos observados | Não inventa término; verificar perdas de writer e exceções |

## Estatística descritiva e comparação

`stats` devolve n, média aritmética, mínimo, máximo, mediana e p95 empírico pelo posto `ceil(.95*n)`. Amostra vazia produz estatísticas nulas. `count_windows` produz média e variância amostral (denominador n−1) das contagens e razão variância/média quando definida. Não há teste rígido de aderência.

A referência exponencial é média `1/λ` por fonte, para os **sorteios**. Contagens de Poisson com média/variância `λT` só servem à idealização homogênea sem custos de despacho, primeiro envio forçado ou limitações operacionais. O processo auditado possui essas diferenças. Em idealização com primeiro envio imediato por C fontes e custos nulos, o total inclui C despachos iniciais além dos eventos exponenciais; nem esse limite ideal deve ser tratado como lei exata do experimento real.

Não agrupar fases com taxas distintas como se fossem estacionárias. Nas validações a taxa legítima é fixa por fonte. Há somente 16 bins por repetição direta; a razão variância/média observada não confirma nem refuta isoladamente Poisson ou saturação. As listas completas de intervalos amostrados e de contagens ficam nos resumos, permitindo reconstruir distribuição empírica/CDF sem impor distribuição ajustada.

Comparações habilitado/desabilitado usam a mesma configuração e seed em cada par, mantendo o horizonte `[0,T)` para a taxa de início. Totais com drenagem ficam em coluna distinta. Seeds iguais reproduzem os sorteios, não o agendamento ou todas as medições. A comparação é descritiva; duas repetições curtas não estabelecem equivalência, ausência de sobrecarga ou regressão de desempenho.
