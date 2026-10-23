# Auditoria de duração HTTP e requisições iniciadas

Auditoria do checkout `7f5e47b4a1e852fca67072432a8a42f2f988eb47`, em 23/10/2026.
Escopo: investigação, testes determinísticos e documentação, priorizando sources
em containers → NGINX → vítimas. Não houve alteração de runtime, schemas,
geradores, detectores, thresholds ou resultados anteriores. Nenhuma campanha,
smoke novo, commit ou push foi executado nesta auditoria.

Foram conferidos README, documentos de proxy, container_sources, ground_truth,
dataset e feature_timeseries e os produtores/consumidores atuais. Não há AGENTS.md
na cadeia de diretórios deste checkout. Os contratos Stage14/15 e seus resultados
congelados não foram reprocessados. Um teste usa a fixture sintética Stage8/9/10
em diretório temporário, sem acessar datasets científicos reais.

## Uma tentativa, do agendamento à persistência

No fluxo containers, `source_manager.SourceManager.release` distribui as mesmas
âncoras epoch/monotônica do host. `validate_clocks` exige mesmo time namespace e
amostras monotônicas remotas dentro dos limites host antes de liberar tráfego.
`source_runner.main` usa `SharedClock`, cria JournalGroundTruth/RequestLogger,
configura o gerador com duration_observer e inicia um worker por source. O loop de
controle consulta o relógio aproximadamente a cada 10 ms, não no limite nominal
exato. O host não agenda cada envio nem mede diretamente seus instantes HTTP.

Sequência do ContinuousFlood e do tráfego normal:

1. O worker escolhe a URL e submete tarefas ao ThreadPoolExecutor. No contínuo há
   `GroundTruth.admit` **antes** de submit: pending aumenta e o journal registra
   admission sincronamente. Falha de submit por pool encerrado abandona admissão.
   Normal não tem esse protocolo de admissão de evento. O primeiro envio contínuo
   não espera um sorteio; os próximos intervalos são exponenciais, esperados após
   cada submissão. Não há log de timestamp individual de oportunidade/submit.
2. A tarefa pode esperar no executor: max_workers limita execução simultânea,
   não o tamanho da fila de submissões contínuas. Ainda não existe request_id,
   request_begin ou duração dessa tentativa. A fila não está na medição HTTP.
3. Ao executar `_send_one`/`_send_one_normal`, chama RequestLogger.begin. Antes do
   timestamp pode haver espera pelo lock do logger e do ground truth, também
   excluída da duração. GroundTruth.begin_request amostra epoch/elapsed monotônico,
   converte pending em in_flight no ataque, estabelece actual_start/last_start e
   calcula o contexto. Esse é o **início da tentativa no cliente**, não envio.
4. Ainda antes de retornar begin: fechamento eventualmente certificável do evento,
   journal de emission_closed quando aplicável, snapshot do evento do atacante,
   criação do request_id/linha pendente e gravação síncrona de request_begin.
   Journal abre, serializa, escreve e fecha o arquivo sob lock; não faz fsync.
   A linha request CSV completa **não** é escrita no begin. As escritas após o
   sample integram duration_ms. O journal de admissão contínua, anterior ao
   executor, fica fora. PeriodicBurst tem admissão atômica ao begin, descrita abaixo.
5. Só depois do retorno de begin o gerador amostra `start_time=time.monotonic()`.
   Valida a URL e chama `session.get` com timeout, allow_redirects=False e ID no
   header. Esse segundo início define a duração do injetor usada pelo avg_rtt_ms.
6. Requests prepara a requisição, consulta a conexão/pool, resolve nome/conecta
   quando necessário, transmite e espera headers/corpo. Uma Session por worker
   de agendamento é compartilhada por suas tarefas; não há um novo Session por
   tentativa. O adapter padrão pode reutilizar sockets; pool_maxsize=10,
   pool_block=False e retries=0 na receita Requests 2.32.3. Portanto esse limite
   não é um semáforo global de dez envios. Não se instrumenta cada reutilização.
   trust_env=False evita proxies de ambiente neste fluxo. O NGINX usa keepalive
   estático no upstream, conexão HTTP/1.1 e retries/buffering/cache desligados.
7. Com stream=False padrão, Session.send consome `r.content` antes de retornar.
   Assim, em retorno normal, o corpo completo já foi lido (incluindo eventual
   decodificação de transporte); não é só tempo até headers/primeiro byte. Não
   se usa Response.elapsed, ping, ACK ou TCP_INFO. A posterior response.text para
   routing evidence faz conversão de texto depois do limite final.
8. No finally, **antes** de finish, counters e persistência, captura
   `end_sample=clock.sample()`. Em seguida outra leitura monotônica encerra a
   duração do injetor. Logo há uma pequena diferença de limites também no fim:
   o injetor inclui o custo do sample final e qualquer preempção entre leituras.
9. RequestLogger.finish usa o end_sample já capturado: calcula duration_ms,
   classifica outcome, grava request_finish no journal e a linha no CSV local,
   atualiza RTT em memória para outcome=response, notifica GroundTruth.finish_request
   (que persiste eventos), e grava routing evidence. O gerador só depois atualiza
   counters e emite latency_sample. Nada disso entra no tempo já encerrado, mas
   pode atrasar a publicação da amostra e ocupar a tarefa/executor por mais tempo.
10. No encerramento, source_aggregate.aggregate reconstrói request_log global a
    partir de request_begin/finish dos journals e rtt_log a partir de response;
    ordena, reconcilia o contexto temporal global e preserva tempos/durações.
    Ausência de finish gera incomplete com término/duração ausentes. Cópias locais
    são evidência; os CSVs globais reconciliados são a autoridade do run.

O timeout escalar Requests configura limites de conexão/leitura, não um deadline
absoluto que inclua executor, logs e todo o corpo. Uma transferência com progresso
pode durar mais do que esse número. Não existe medição separada de DNS, fila de
socket, transmissão, chegada ao proxy ou chegada à vítima. A fila de processos
na vítima (`do_GET`: `_pool.submit(...).result()`) e o serviço/espera depois da
chamada HTTP integram a observação do cliente, sem serem isolados.

Fontes primárias da dependência fixada: [Session.send e leitura do corpo](https://raw.githubusercontent.com/psf/requests/v2.32.3/src/requests/sessions.py),
[HTTPAdapter: pool, retries e timeout](https://raw.githubusercontent.com/psf/requests/v2.32.3/src/requests/adapters.py).
O ambiente host de testes tem Requests 2.34.2/urllib3 2.8.0; a receita sources fixa
2.32.3/2.3.0. Os testes verificam o checkout com a biblioteca host instalada e
adapter de transporte controlado; não certificam o binário de uma imagem cached.

## Definições atuais: relógio e limites

Notação: B=sample de begin; H=monotonic após begin; E=sample no finally;
F=monotonic logo após E. Elapsed = monotonic menos âncora do experimento.
Epoch é time.time em segundos, para alinhamento, sem ser usado na subtração de
duração Python. Epoch/monotônico não são amostrados atomicamente; drift não é
monitorado continuamente. Os limites não são instantes de transmissão na rede.

| Medida | Relógio / unidade | Limites e inclusão/exclusão |
|---|---|---|
| request_log.duration_ms | 1000 × (E.elapsed − B.elapsed), ms | Inclui instrumentação síncrona após B, validação/Requests, conexão quando necessária, espera no proxy/vítima e corpo; exclui espera no executor/locks anteriores a B, agendamento e persistência final após E. |
| rtt_log.rtt atual | Igual ao duration_ms selecionado, ms | Não é uma segunda cronometragem; herda os mesmos limites. timestamp/elapsed são E. |
| simulation_metrics.avg_rtt_ms | Média de 1000 × (F − H) dos injetores; ms, gravada com 2 casas | Exclui begin; inclui validação/Requests/corpo e sample final. Exclui persistência de finish. Epoch/elapsed na linha são do tick host, não dos HTTPs. |
| feature mean_duration_ms | Média aritmética dos duration_ms persistidos, ms | Herda o intervalo B→E de cada tentativa, sem retirar logs ou estimar TCP RTT; não lê avg_rtt_ms nem rtt_log como fonte da média. |
| NGINX request_time | Segundos com resolução de ms; relógio de parede cached NGINX | Primeiro byte lido do cliente → escrita do access log após enviar os últimos bytes. Exclui logs/execução Python anteriores à chegada e aquisição da conexão anterior a esse começo. Não prova entrega à aplicação cliente. |
| NGINX upstream_time (=upstream_response_time) | Segundos com resolução de ms; timer interno ngx_current_msec | Intervalo do upstream desde início da tentativa/conexão até finalização da resposta upstream. Inclui conexão quando criada, espera/processamento/recepção; não é somente CPU/serviço da vítima. |
| NGINX connect_time (=upstream_connect_time) | Segundos com resolução de ms; mesmo timer upstream | Estabelecimento upstream, não conexão cliente→proxy; pode ser zero com reutilização ou arredondamento. |

`$msec` na coluna timestamp do access log é epoch no instante da escrita.
`request_time` em NGINX 1.28.0 usa ngx_timeofday menos start_sec/start_msec,
truncado em zero se necessário. Upstream usa diferenças de ngx_current_msec,
monotônico quando compilado com NGX_HAVE_CLOCK_MONOTONIC, com fallback de parede;
não é o ExperimentClock e não se inferiu a macro de build apenas do access log.
A inspeção do código upstream é da release 1.28.0, correspondente à tag do projeto.

Referências: [log module: request_time e msec](https://nginx.org/en/docs/http/ngx_http_log_module.html),
[variáveis upstream](https://nginx.org/en/docs/http/ngx_http_upstream_module.html),
[cálculo de request_time](https://raw.githubusercontent.com/nginx/nginx/release-1.28.0/src/http/ngx_http_variables.c),
[limites dos timers upstream](https://raw.githubusercontent.com/nginx/nginx/release-1.28.0/src/http/ngx_http_upstream.c),
[relógio cached/monotônico](https://raw.githubusercontent.com/nginx/nginx/release-1.28.0/src/core/ngx_times.c).

Não se deve subtrair request_time−upstream_time e chamar o resultado de latência
pura do proxy: limites, sobreposição de transporte, precisão e relógios diferem.
O corpo da vítima contém outro elapsed, perf_counter em torno de seu trabalho;
também não é nenhum dos tempos acima nem um timestamp de recebimento da vítima.

## População, falhas e janelas

| Medida | População e falhas | Atribuição temporal / ausência |
|---|---|---|
| request_log | Uma linha por tentativa observada, normal/attack; response (<400), http_error (≥400), transport_error (RequestException) e client_error (outra exceção); incomplete quando sem finish. | Início B e fim E guardados separadamente; CSV não agrega janelas. Incomplete tem fim/duração vazios. Contexto attack_active é o do início, reconciliado globalmente, não o da conclusão. |
| rtt_log | Somente outcome=response; inclui 3xx não seguido, não somente HTTP 200/2xx. Exclui http_error, transport_error, client_error e incomplete. | Timestamp e elapsed de conclusão E. Não há janelas nativas nem zero substituindo a falta de linha. Fluxo sem RequestLogger, histórico: save_rtt_log tem fallback de duas colunas, que não deve ser confundido com este contrato atual. |
| avg_rtt_ms, containers | latency_sample dos geradores: error is None, inclusive HTTP ≥400; exclui exceções. Seleciona classe attack durante janela **nominal** configurada e normal fora dela. Não é média conjunta de todas as tentativas. | Cada tick consome todas as novas mensagens visíveis, marca ambas as classes como consumed e calcula média só da classe selecionada; as demais não voltam em ticks posteriores. Não usa elapsed da conclusão para binning. Vazio vira 0, não ausência explícita. Não há tick extra da cauda depois do drain. |
| mean_duration_ms | Todas as tentativas com fim e duração, incluindo HTTP/transport/client errors; exclui incompletas da média. | Janela decimal [kΔ,(k+1)Δ) pelo **fim E**. Cada tentativa tem peso igual; zero observado é válido; média sem conclusões é null/célula vazia. Horizonte inclui cauda observada além do plano. |
| Access log NGINX | Requests efetivamente observados no NGINX, com status de sucesso/erro/aborto e probes setup/capture_audit/monitoring. IDs correlacionam tentativas quando presentes; falha no cliente pode não ter access. | Escrita/conclusão NGINX, sem janelamento científico automático. Upstream não usado/indisponível pode produzir string vazia/“-”, não zero; variáveis upstream podem listar múltiplos tempos em geral, embora retries estejam off aqui. |

No fluxo host, get_average_rtt_ms/get_average_rtt_attack_ms drenam buffers em
memória; seleção usa attack_has_started operacional, amostrada antes das ações do
tick, não exatamente a seleção nominal dos containers. O buffer benigno é drenado
a cada tick; o atacante só quando selecionado. Não há equivalência exata entre
essas agregações de tick, nem entre elas e as janelas regulares das features.

Há também atraso entre E e publicação de latency_sample: finish persiste dados
antes do observer. Assim uma conclusão pode chegar a um tick posterior; o tick
seleciona a classe segundo o relógio então observado, não segundo E. A classe não
selecionada é descartada desse resumo. Não é defeito do cálculo da média dos
valores selecionados, mas é limitação material para usá-lo como série de latência
global ou por janelas de conclusão. O journal não registra o instante de ingestão
de cada mensagem pelo host: não se pode reconstruir exatamente esses buckets
posteriormente apenas pelos elapsed dos payloads.

Em erro lendo o corpo, session.get pode levantar RequestException antes da
atribuição de response: a linha fica sem http_status mesmo que headers tenham
chegado e o NGINX tenha registrado 200. O término mede tempo até a exceção, não
até corpo completo. Não há raise_for_status: HTTP 503 retorna normalmente,
incrementa counter ok e entra no avg_rtt_ms; RequestLogger o classifica http_error
e não o inclui no rtt_log. Erro em logging pode fazer a tarefa falhar e o run ficar
incompleto; os testes não alegam que escrita em disco nunca falha ou é durável a
SIGKILL. Falhas de instrumentação não são tempo HTTP válido adicional inventado.

## Onde request_starts é contado

A contagem é **offline**, em `experiments.extract_features.extract_features`,
linha 226 do checkout: para cada linha de request_log, incrementa request_starts
na janela index(elapsed_seconds). Não é contagem em NGINX ou na vítima.
A janela de fim recebe request_completions e a duração da média. Em labels.csv,
attack_request_starts conta o subconjunto traffic_class=attack pela mesma janela
de começo; esse campo causal não entra nas features do detector.

| Evento | Evidência atual | Equivale a request_starts? |
|---|---|---|
| Oportunidade/agendamento/submit | Ritmo no worker; não há timestamp científico individual de submit | Não: tarefa pode ficar enfileirada ou não ser admitida. |
| Admissão contínua | Journal admission antes de submit; inclui abandonos se submit falha | Não: ainda pode faltar início. |
| Início da tentativa no cliente | GroundTruth.begin_request → RequestLogger.begin → request_begin/request_log.elapsed_seconds | Sim: é a definição usada no binning, inclusive falhas/incomplete com início conhecido. |
| Transmissão do primeiro byte | Não há timestamp de envio HTTP instrumentado; pacote capturado não tem request_id | Não. |
| Recebimento no proxy | Access log documenta processamento; timestamp é de conclusão; request_time permite apenas estimativa do começo NGINX | Não; estimativa não vira timestamp exato de begin/transmissão. |
| Recebimento na vítima | Não existe timestamp de recebimento em schema científico; upstream/hostname evidenciam caminho | Não; o elapsed no corpo mede trabalho, não chegada. |

## Depois do término nominal do ataque

ContinuousFlood não revalida o deadline ao executar a tarefa. O source_runner
solicita stop ao observar o fim nominal; stop_http_flood fecha novas admissões
sob o lock de evento, desliga worker/stop_event e faz joins curtos. Uma admissão
que venceu a corrida com stop permanece válida, mesmo antes do submit terminar.
Tarefas já admitidas/submetidas não são canceladas: podem começar **depois** do
fim nominal e de stop_requested. A espera na fila não entra na duração; o início
tardio entra normalmente em request_log e request_starts na sua janela real.

O fim efetivo actual_end só pode ser certificado com accepting=false, pending=0
e relógio estritamente posterior ao último início. Até isso ocorrer o evento
permanece aberto. Fechamento pode ocorrer no begin do último pendente, em stop
posterior ou ao finalizar um HTTP; não é o instante do último pacote nem o fim
de toda comunicação. Pode haver escrita síncrona e até transmissão iniciada após
actual_end por uma tentativa cujo **begin** já ocorreu antes dele.

in_flight inclui tentativas iniciadas que ainda não notificaram finish, não
apenas sockets ativos: instrumentação e persistência também influenciam o ciclo
de vida. O timestamp drained_end usa o maior E capturado nas conclusões, não o
instante da escrita final ou da saída do processo. Pode ser menor que actual_end
se uma confirmação de fechamento só acontece mais tarde. A publicação da
certificação source_closed vem após drain e persistência.

`drain(timeout=30)` aguarda produtores e futures; shutdown(wait=False) não cancela
a fila. Em falha, logger.finalize preserva pendentes como incomplete, sem fim
fictício; source termina com erro. SourceManager.stop dá até 35 s antes de matar
sources restantes e preserva status. `source_aggregate.reconcile` usa menor start,
maior last_start e maior fechamento certificado de todos os atacantes; drained
exige source_closed, drained e logger_complete de cada source. No caminho completo,
o máximo dos fins de conclusão compõe drained_end global. Ground truth não usa
janela nominal para reclassificar uma tarefa contínua já admitida como benigna.

PeriodicBurst tem contrato distinto: reserva slot antes de submit e revalida
stop_event/deadline/padrão no begin, com admissão atômica nesse mesmo sample.
Oportunidade expirada não vira tentativa nem request_start; não há backlog
admitido transportado para outro burst. Nenhuma política foi mudada nesta auditoria.

## Evidências verificadas e testes

Novo arquivo: `tests/test_http_timing_audit.py`. Usa relógio virtual, Events para
ordenar executor real de um worker e Session Requests real com BaseAdapter/Body
controlados; não usa sleep para produzir duração, rede externa, Docker ou vítima.
Events/futures têm timeout real de 5 s apenas para impedir travamento do teste.

| Evidência determinística | Resultado |
|---|---|
| Begin em 2 s; journal anterior ao envio demora 750 ms; headers 125 ms + corpo 375 ms; persistência final 1250 ms | duration_ms/rtt=1250 ms, duração do injetor=500 ms; fim E=3,25 s; publicação só em 4,5 s. Corpo foi consumido antes de E. |
| Tarefa submetida em 1 s, executor ocupado até 6 s, HTTP 500 ms | Nenhum begin/ID antes de 6 s; duration_ms=500 ms, não 5500 ms. |
| HTTP 503 e ConnectionError após 125 ms, com delay de begin | Ambos em request_log (1250/875 ms), nenhum no rtt_log; somente 503 publica latency_sample de 500 ms. Verificado em normal e ataque. |
| Admissão contínua 9 s; stop_http_flood em 10 s; executor libera em 12 s | Begin=12 s aceito; fechamento certificado 12,25 s; conclusão/drained_end=14 s; duração=2000 ms e origem attack preservada. |
| Finish ausente e finalize | incomplete, fim/duração ausentes; finish tardio não inventa uma nova conclusão. |
| Agregação por journals | Mantém tempos/durações e apenas response no RTT global. |
| Fixture de features com HTTP/transport errors concluindo exatamente em 3 s | 4 starts em [2,3), 0 em [3,4); 3 conclusões e média (1000+200+250)/3 ms em [3,4). |

Foram executados **7 testes novos**, todos OK, e **76 regressões** de ground truth,
attack patterns, sources, features e proxy, todas OK. Incluem incompletas, bordas
decimais, fins após o plano e falhas das diferentes populações. Mensagem de run
incomplete na saída da regressão pertence a uma fixture de falha, não a experimento
real nesta etapa. Logs integrais em:
`experiment_results/http-timing-audit-20261023/{focused-tests,regression-tests}.log`.

Comandos exatos:

```bash
.venv/bin/python -B -m unittest tests.test_http_timing_audit -v
.venv/bin/python -B -m unittest tests.test_ground_truth tests.test_attack_patterns tests.test_source_containers tests.test_feature_extraction tests.test_http_proxy -v
.venv/bin/python -B experiment_results/http-timing-audit-20261023/inspect_existing.py
```

Também foram lidos os smokes **já existentes**, sem reexecutá-los. JSON completo e
script de leitura em `experiment_results/http-timing-audit-20261023/`:

- benign-v2: 277 requests response, 277 RTTs, igualdade de duração por request_id;
  todos correlacionados a um único access NGINX.
- continuous-v2: 385 response/385 RTTs, mesma igualdade e correlação. Fim nominal
  5 s, stop_requested=5,005357131, actual_end=5,006827085 e drained_end=5,032605109.
  Zero starts após o fim nominal naquele smoke leve; uma conclusão após actual_end.
  A ausência de backlog nesse run não contradiz o teste de fila saturada.
- Associação de latency_sample por source+end_elapsed foi unívoca nas 277/385
  tentativas. A diferença entre duration_ms e duração do injetor teve mediana
  0,135105/0,139227 ms e máximo 0,667445/9,780213 ms. É diferença entre limites de
  medição, sujeita a escalonamento; não é estimativa causal isolada de overhead.
- Os hashes host de oito módulos do runtime na proveniência dos smokes coincidem
  com o checkout auditado. Isso não certifica o conteúdo do código já embutido
  na imagem sources cached. Seus binários não foram reinspecionados nesta etapa.
  Foram rechecados 91/135 hashes de arquivos dos runs; todos permaneceram iguais.

## Comportamento correto, limitações e recomendações

Não foi demonstrado defeito aritmético ou violação dos contratos atuais de
request_log/rtt_log/features/ground truth. Há diferenças intencionais e limitações
que se tornam erros de interpretação se as medidas forem apresentadas como
equivalentes, TCP RTT, contagem de envios ou média de todos os HTTPs por segundo.

| Medida | Avaliação atual | Recomendação e impacto de eventual correção |
|---|---|---|
| duration_ms | Correto para B→E; inclui begin, exclui executor/persistência final. Limitação se o objetivo for somente chamada HTTP ou latência desde agendamento. | **Manter.** Mover B silenciosamente quebraria a fórmula do schema, igualdade histórica com RTT, features e comparabilidade. Se houver futura necessidade, definir medida adicional/versionada com limites explícitos e evidência de fila, sem substituir esta. |
| rtt_log | Correto como projeção response de duration_ms; nome RTT é histórico e insuficiente para definir TCP RTT. Seleção exclui erros HTTP. | **Manter valores/schema**, apresentar como duração HTTP do cliente para outcome=response. Trocar população para todos os retornos mudaria distribuição e denominadores; exigir nova definição/versionamento, não reescrever runs. |
| avg_rtt_ms | Média correta dos samples selecionados, mas com população distinta, bucket por chegada, descarte da classe não selecionada, zero ambíguo e cauda ausente. Não serve como substituto da feature de duração. | **Preservar o campo legado; recomendar revisão prospectiva** se a pergunta exigir média por classe/janela de conclusão com suporte explícito. Seria outra medida: nomes/artefatos versionados, null separado de zero, contagens/erros e janela explicitados. Mudaria valores e distribuição; não reaproveitar thresholds/avaliações congeladas nem comparar sem estratificar versão. Nada implementado agora. |
| mean_duration_ms | Correto para todas as conclusões por janela de E, incluindo tempo até falha. Não é média de só sucessos, nem duração média das tentativas iniciadas na mesma janela. | **Manter.** Alterar para sucessos ou janela de começo quebra schema/feature contract e comparabilidade dos detectores; eventual alternativa deve ter nome/versão novos e avaliação própria. |
| request_starts | Correto para tentativas que alcançaram begin, incluindo falhas/incompletas; não mede submit/envios/chegadas. | **Manter.** Renomear conceitualmente para taxa transmitida sem nova instrumentação seria defeito. Contagem de outro evento exigiria nova métrica e não poderia ser reconstruída exatamente dos starts históricos. |
| Tempos NGINX | Corretos como evidência operacional do proxy, resolução ms e população própria; clock/boundaries distintos. | **Manter separados.** Não substituir duração cliente, imputar upstream ausente como zero ou usar diferença de timers como CPU/latência pura do proxy. Nova análise exige filtragem explícita de fases/IDs e compatibilidade temporal. |
| Emissão/drenagem contínua | Inícios tardios já admitidos e conclusões em voo são comportamento correto do contrato existente, não um defeito de RTT. | **Manter.** Cancelar backlog ou impor deadline ao start mudaria o ataque e a distribuição de carga/labels; não é correção de medição e está fora desta etapa. |

O defeito seria **de definição/apresentação** ao afirmar que os nomes históricos
RTT ou avg_rtt_ms têm a mesma população e limites, ou que request_starts conta
tráfego recebido. A limitação de agregação do avg_rtt_ms justifica uma futura
proposta explícita; não autoriza alterar contratos congelados. Nenhuma correção
de medição foi implementada antes de avaliar compatibilidade/comparabilidade.

## Referências no checkout

| Arquivo / função (linha inicial) | Papel |
|---|---|
| simulator/source_runner.py:21 — main | Clock compartilhado, configuração de logger/observer, controle nominal, stop e drain. |
| simulator/source_manager.py:21 / :116 / :156 | validate_clocks, release e stop global dos sources. |
| simulator/normal_traffic.py:141 / :70 / :121 / :247 | Agendamento, tarefa de envio, drain, buffer de média host. |
| simulator/traffic_injectorV0.py:147 / :75 / :421 | Agendamento contínuo, tarefa de envio, stop_http_flood. |
| simulator/traffic_injectorV0.py:237 / :253 / :269 | Revalidação/reserva de slot/agendamento PeriodicBurst. |
| simulator/request_logger.py:34 / :61 / :90 / :100 | begin, finish, finalize e save_rtt. |
| simulator/ground_truth.py:77 / :96 / :123 / :131 / :140 | admit, begin_request, finish_request, stop e _close_emission. |
| simulator/source_journal.py:19 / :38 / :53 | Escrita síncrona do journal e hooks de admissão/begin. |
| simulator/source_aggregate.py:26 / :79 | Reconciliação global e reconstrução de request/RTT. |
| simulator/source_experiment.py:99 | Consumo de latency_sample, seleção de classe e escrita da média no tick. |
| simulator/main_orchestrator.py:83 / :454 | Escrita de métricas e seleção/buffers no fluxo host. |
| experiments/extract_features.py:203 / :225 / :250 | Índice de janela, contagem de starts/conclusões e média de duração. |
| experiments/dataset_schema.py:35 / :51 / :63 | Contratos atuais duration_ms, RTT e avg_rtt_ms, preservados. |
| simulator/http_proxy.py:22 | log_format e políticas NGINX. |
| simulator/app/simple_server.py:56 | Recebimento HTTP/workload, fila de processos e resposta. |
| docker/Dockerfile.sources / docker/requirements.sources.txt | Lista de código embutido e versões fixadas da receita. |

## Respostas para o orientador

**Como o RTT é medido?** O nome histórico representa duração HTTP no cliente,
medida por relógio monotônico até o retorno com corpo completo ou até a falha.
No rtt_log entram apenas outcome=response e o valor é duration_ms, incluindo a
instrumentação inicial. Não é TCP RTT; avg_rtt_ms usa outro início e população.

**Onde as requisições iniciadas são contadas?** Na extração offline de features,
uma por linha de request_log, pela janela de elapsed_seconds do begin na tarefa
de envio. Esse começo ocorre depois da fila do executor e antes dos logs síncronos
e da chamada HTTP; não comprova transmissão ou recebimento no proxy/vítima.
