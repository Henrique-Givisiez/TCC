# Instrumentação do proxy — entrega para revisão

Diagnóstico do checkout: não há AGENTS.md no repositório ou diretório pai.
Foram consultados README, http_proxy, container_sources, dataset, feature_timeseries,
os contratos de arquivamento/exportação, e os documentos de freeze Stage14/15.
`simulator/http_proxy.py` gera upstream estático, valida com nginx -t, inicia a
imagem por digest e confirma readiness HTTP das vítimas com phase=setup antes do
relógio. `verify` inspeciona ID e running durante o experimento e após drenagem;
`close` para, preserva logs montados e remove quando drenado. O caminho host está
em main_orchestrator; o caminho containers em source_experiment. docker_manager
cria vítimas sem publicação no modo proxy. StatsCollector continua exclusivamente
com vítimas, incluindo sua semântica histórica de média/cache. Nenhum dado novo
entra em simulation_metrics, RTT, request_starts, ground truth, features ou detectores.

Os freezes históricos Stage14/15, seus hashes, modelos, thresholds e resultados
não foram reescritos. Esta árvore instrumentada é uma versão diferente: não deve
ser apresentada como o runtime das campanhas congeladas. Os smokes são técnicos,
fora dessas campanhas. Sem autoscaling, reload ou mudança de upstream; políticas
HTTP, pools, retries, buffering e timeouts do serviço foram preservados.

## Coleta e schema v1

Novo `simulator/proxy_monitor.py`: thread independente, cliente Docker próprio,
intervalo técnico `config.PROXY_POLL_INTERVAL_SECONDS=1.0`, timeout de transporte
Docker `PROXY_COLLECTION_TIMEOUT_SECONDS=2.0`. wget tem timeout de 1 s. Encerramento
aguarda no máximo 2*timeout+2 s; thread remanescente é registrada explicitamente.
Uma chamada pode continuar no daemon após timeout do cliente. O coletor é daemon;
nenhum mecanismo promete recuperar uma chamada travada no daemon ou sobreviver a
SIGKILL com buffer ainda não escrito. Cada linha completa é descarregada imediatamente;
finalização incompleta mantém as linhas já escritas. Não há cache de observações.

Arquivos novos sob proxy_artifacts:

- `nginx_build.txt`: saída real de nginx -V; setup exige --with-http_stub_status_module.
- `monitor_samples.jsonl`: uma linha JSON por tentativa de ciclo, schema_version=1.
- `monitor_summary.json`: run_id, container_id, monitoring_queries_attempted,
  thread_alive e, quando aplicável, fatal_error; source_errors contém contagem
  por fonte na versão final (os dois smokes precederam essa adição ao resumo).
- `monitor_networks.json`: run_id, container_id e snapshot Docker das redes,
  preservando IP/MAC/NetworkID/EndpointID. `monitor_interfaces.txt` guarda ip -o addr
  para associar nomes eth* a IP/MAC das redes; não presuma ordem fixa das interfaces.

Cada linha tem run_id, container_id, timestamp (epoch UTC em segundos),
elapsed_seconds (monotônico relativo à mesma âncora ExperimentClock do run),
scheduled_elapsed_seconds, delay_seconds, monitoring_query_sequence e
collection_duration_seconds. Os objetos `status` e `docker` têm timestamp e
elapsed_seconds próprios, no começo da aquisição, duration_seconds, success,
error e data. As duas fontes são sequenciais, não uma fotografia atômica.
Clock epoch e monotônico não são amostrados atomicamente; drift não é corrigido.
Atrasos aparecem em delay/duração; saltos de scheduled mostram slots pulados,
sem fabricar linhas de observação nesses slots. A coleta começa após bind_run e
continua durante a drenagem, antes de parar o proxy.

Ausência = JSON null, nunca zero. Erro de fonte = success=false, erro textual e
data=null. Falha fatal do worker vai ao resumo. Monitoramento indisponível não é
uma conclusão de identidade/parada do proxy e não substitui verify; este continua
invalidando a integridade do run quando necessário. O par ID/run é persistido
em cada linha. As chamadas usam exclusivamente o ID esperado, nunca nome mutável.

`status.data` contém inteiros:

| Campo | Semântica |
|---|---|
| active_connections | Conexões cliente abertas, incluindo waiting |
| accepted_connections_total | Conexões cliente aceitas desde início do NGINX |
| handled_connections_total | Conexões tratadas; pode divergir de accepted sob limites de recursos |
| requests_total | Requisições cliente processadas acumuladas |
| reading_connections | Conexões lendo cabeçalhos |
| writing_connections | Conexões escrevendo resposta |
| waiting_connections | Conexões keep-alive ociosas; **não tamanho de fila** |

Status ouve exclusivamente 127.0.0.1:8081 **dentro** do container, sem porta publicada,
com location exata stub_status e demais paths 404. O coletor usa Docker exec wget;
fontes e vítimas não acessam esse loopback. A sessão de monitoramento requer acesso
ao Docker, como a coleta de recursos. Seu header X-Edos-Phase=monitoring aparece
no access log; cada tentativa é contada separadamente, mesmo em erro, sem alegar
que todas foram processadas. Essas consultas participam dos contadores globais
NGINX e de active/writing. Porta separada não elimina essa interferência. Não há
subtração ou correção automática. Setup e capture_audit mantêm suas fases anteriores.

`docker.data`: cpu_percent usa delta de cpu_usage.total_usage dividido por delta
system_cpu_usage vezes online_cpus vezes 100; 100% corresponde a um núcleo e pode
superar 100%. Primeira leitura é null; reset, sistema sem avanço e suporte ausente
são null com delta_state. CPU zero com delta válido permanece zero.
memory_usage_bytes é **memory_stats.usage bruto** do cgroup em bytes, incluindo
cache contabilizado pelo Docker; não é RSS nem memória sem cache. Não modifica a
convenção mem_app_mb das vítimas. docker_read preserva timestamp do daemon; leitura
repetida é recusada como stale. `interfaces` indexa cada interface Docker e guarda
rx_bytes/tx_bytes acumulados e rx_bytes_per_second/tx_bytes_per_second.
Taxas usam intervalo monotônico realmente observado entre começos das aquisições
Docker bem-sucedidas (observed_interval_seconds), não a cadência nominal; esse
intervalo aproxima o intervalo de captura do daemon, com incerteza da chamada.
Primeira leitura, interface nova, contador ausente, reset ou intervalo inválido
têm taxas null e delta_state explícito. Após falha, próximo delta pode abranger a
lacuna: não implica cobertura amostral nesse trecho. Não há taxa derivada do status.
Interfaces/redes permanecem separadas: somar frontend e backend **não mede volume
único de clientes**. Exec/wget também consome recursos e tráfego loopback pode não
estar incluído nos contadores das interfaces reportadas pelo Docker.

Access logs existentes preservam status HTTP, upstream/status, request_time,
upstream_response_time e connect_time para análise posterior. Timestamp NGINX é
de conclusão. request_time menos upstream_response_time não se chama “latência
pura do proxy”: transporte, espera, buffering e intervalos diferentes impedem isso.

## Arquivamento, exportação e execução

`experiments.result_archive.move_result` já move a árvore proxy_artifacts inteira
após validar seu run_id, junto das métricas. `experiments.export_dataset` já copia
recursivamente novos arquivos para evidence/proxy, preservando bytes e hashes.
Não foi necessário alterar schemas científicos congelados ou esses dois módulos.

Comandos exatos executados, sequencialmente, a partir da raiz (saídas existentes
não podem ser reutilizadas; escolha nomes novos para outra execução):

```bash
.venv/bin/python -B -m experiments.dataset_run --config experiments/configs/proxy_observability/benign.json --output experiment_results/proxy-observability-20261023/benign-v2 --dataset-output experiment_results/proxy-observability-20261023/benign-v2-dataset
.venv/bin/python -B -m experiments.dataset_run --config experiments/configs/proxy_observability/continuous.json --output experiment_results/proxy-observability-20261023/continuous-v2 --dataset-output experiment_results/proxy-observability-20261023/continuous-v2-dataset
.venv/bin/python -B -m experiments.plot_proxy_monitor experiment_results/proxy-observability-20261023/benign-v2 experiment_results/proxy-observability-20261023/benign.png
.venv/bin/python -B -m experiments.plot_proxy_monitor experiment_results/proxy-observability-20261023/continuous-v2 experiment_results/proxy-observability-20261023/continuous.png
.venv/bin/python -B -m unittest tests.test_proxy_monitor tests.test_http_proxy tests.test_source_containers tests.test_dataset_export tests.test_feature_extraction -q
```

Os perfis usam duração 8 s e janela nominal contínua [2,5), preservando geradores,
taxas, endpoints e demais defaults de container_sources; benign desliga o ataque.
Docker nativo e imagens estavam disponíveis. O sandbox bloqueou o socket;
a execução autorizada fora do sandbox funcionou. A primeira tentativa benign
colidiu com diretório existente e foi recusada, sem sobrescrita; benign-v2 foi novo.

Ambos completed, sem erros de status/Docker: benign-v2 tem 9 amostras, CPU
2,2308–3,0893%, memória bruta 7.692.288–10.846.208 bytes e conexões ativas 1–11;
continuous-v2 tem 10 amostras, CPU 2,6910–4,2163%, memória 5.488.640–7.831.552 bytes
e conexões 1–21. Incluem cauda de drenagem, e CPU inicial null é excluída desses
extremos. Gráficos PNG estão no diretório pai dos runs; faixa vermelha usa eventos
actual_start/actual_end, não a janela nominal. São observações reais, não mocks.

Testes focam parser, múltiplos núcleos, memória, redes/deltas, primeira leitura,
reset, tempo inválido, fonte indisponível/timeout, stale, alinhamento e ID,
thread/flush/encerramento, exportação byte a byte e arquivamento. Regressões
existentes verificam isolamento das vítimas e contratos de features.

Como evoluímos o monitoramento do proxy? Passamos de identidade, logs e
integridade operacional a séries independentes de conexões e recursos, associadas
ao relógio/run, com falhas e interferência do monitor explícitas. O consumo acima
é observado; sinais de saturação exigem analisar conjuntamente limites, divergência
accepted/handled, erros, tempos e comportamento de serviço. Waiting isolado não
prova saturação. Overhead **causal** requer comparação experimental controlada,
com carga, ambiente, repetição e instrumentação equivalentes. Estes smokes não
estimam esse overhead e não justificam alterar thresholds ou conclusões congeladas.

## Revisão do fechamento — 23/10/2026

A revisão manteve o mecanismo de coleta e corrigiu somente a apresentação gráfica.
`observation_series` usa explicitamente success e os elapsed_seconds de cada fonte;
null permanece indisponível na figura (NaN apenas na representação Matplotlib).
Todas as séries agora usam pontos sem linhas: não há interpolação através de
falhas, slots pulados ou intervalos sem suporte. Os PNGs anteriores foram mantidos;
figuras revisadas estão em `experiment_results/proxy-observability-review-20261023/`.

### Ordem, cgroup e intervalos

No código, `sample` itera status → docker. Status faz containers.get, exec_run wget,
verifica exit_code e faz parsing; somente depois chama api.stats(one_shot=True).
Em sucesso normal, o wget terminou antes da chamada de stats. Nos smokes anteriores,
o início Docker ocorreu 32,83–46,32 ms (benigno) e 37,00–61,00 ms (contínuo) após
o início status. O timestamp docker_read do daemon caiu dentro da chamada Docker
em todas as leituras anteriores: 0,519–1,425 ms após o início no benigno e
0,583–1,025 ms no contínuo. Isso não estabelece sincronização atômica.
Se exec_run falhar por timeout, sua execução remota pode continuar: a ausência
de sobreposição de processos não é garantida nesse caso. As chamadas Python
continuam sequenciais, inclusive no caminho de exceção.

CPU do container inclui NGINX master/workers **e os processos executados nesse
container**, inclusive o wget de cada consulta. Execuções pontuais `nginx -V` e
`ip -o addr` também pertencem ao cgroup enquanto existem. Docker daemon, cliente
Python, runtime/shim externos ao cgroup e geradores/vítimas têm seus próprios
recursos; seu custo não está todo incluído na CPU do proxy. O atendimento NGINX
ao status e o wget entram nos contadores acumulados de CPU. O wget normalmente
já terminou quando se lê memória: sua memória transitória pode ser perdida pela
amostragem, embora cache e efeitos remanescentes possam persistir. Portanto a
leitura de memória posterior não mede pico do wget nem isola memória do NGINX.
Execução sequencial não remove a interferência do monitoramento.

CPU_i é uma razão de **deltas entre dois snapshots Docker bem-sucedidos**, não
CPU instantânea. Os limites físicos são os docker_read anterior e atual; no
relógio do experimento, sua aproximação registrada é
`[docker.elapsed_seconds_i - observed_interval_seconds_i, docker.elapsed_seconds_i]`.
A figura coloca apenas um ponto no limite direito aproximado, identificado no
rótulo como fim do intervalo; não desloca o valor para o início nem para o meio,
e não o atribui ao timestamp do ciclo ou à fonte status. Memória e conexões usam
os respectivos instantes de início de aquisição, sem alegar simultaneidade.
Após falha Docker, o próximo delta válido pode cobrir uma lacuna entre snapshots;
esse valor não implica observações intermediárias e nenhum segmento é desenhado
atravessando a falha. A incerteza dos limites inclui a duração das chamadas Docker.

### Conferência dos logs reais

Auditoria reproduzível: `experiment_results/proxy-observability-review-20261023/audit.py`;
resultado integral em `audit.json`. Foram comparados resumo, JSONL e access log,
incluindo fases de setup/capture_audit separadas de monitoring. Cada tentativa
teve exatamente um access de monitoring temporalmente compatível (tolerância de
2 ms para timestamp NGINX em milissegundos). Todos esses accesses são HTTP 200,
sem upstream; não passaram às vítimas. Não existe query ID único no access log:
a associação individual é temporal, apoiada por contagens iguais e ausência de
concorrência de consultas, e não uma nova chave de correlação garantida.

| Run | Tentativas / accesses monitoring 200 | Duração ciclo mín–máx (ms) | Atraso máximo (ms) | Slots pulados |
|---|---:|---:|---:|---:|
| benign-v2 anterior | 9 / 9 | 34,577–52,297 | 0,125 | 0 |
| continuous-v2 anterior | 10 / 10 | 38,815–70,695 | 0,175 | 0 |
| final-benign novo | 10 / 10 | 33,594–77,539 | 0,316 | 0 |

Não há tentativas com erro registrado ou sem access compatível nesses runs.
Isso é evidência de consultas atendidas nesses smokes; em geral, o contador
monitoring_queries_attempted avança **antes** de containers.get/exec e pode incluir
falha antes do envio. Erro de transporte/parsing também pode ocorrer após NGINX
atender. source_errors.status não mede exclusivamente consultas não atendidas.
Ausência de access isoladamente não distinguiria não chegada de perda de log.
Não foram injetadas falhas na integração real; falhas são cobertas pelos testes.

Não foram encontrados resets dos contadores NGINX, CPU ou interfaces, nem stale
ou fontes indisponíveis. Cada run tem CPU null na primeira leitura e duas
interfaces com taxas null nessa leitura. As demais leituras têm delta_state=valid;
memória nunca esteve ausente. Intervalos observados de CPU: 0,994684–1,008464 s
no benigno anterior, 0,991487–1,015906 s no contínuo e 0,987415–1,011927 s no novo.
Os valores de status são gauges/contadores observados; não se deduziu fila,
saturação ou overhead causal a partir dessas contagens.

### Versão final, teste e smoke adicional

Um único smoke benigno adicional, 8 s, sem campanhas ou alteração de configuração
experimental além do perfil técnico já existente. Run novo:
`04d1d3dd38954e39a423cfb3e316868c`, status completed; resumo real contém
`source_errors={"status":0,"docker":0}`, 10 tentativas e thread_alive=false.
O resumo exportado foi preservado byte a byte. Os resumos anteriores continuam
sem o campo: não foram atualizados retroativamente.

```bash
MPLCONFIGDIR=/tmp/proxy-review-mpl .venv/bin/python -B -m unittest tests.test_proxy_monitor tests.test_http_proxy tests.test_source_containers tests.test_dataset_export tests.test_feature_extraction -q
.venv/bin/python -B -m experiments.dataset_run --config experiments/configs/proxy_observability/benign.json --output experiment_results/proxy-observability-review-20261023/final-benign --dataset-output experiment_results/proxy-observability-review-20261023/final-benign-dataset
.venv/bin/python -B experiment_results/proxy-observability-review-20261023/audit.py
MPLCONFIGDIR=/tmp/proxy-review-mpl .venv/bin/python -B -m experiments.plot_proxy_monitor experiment_results/proxy-observability-20261023/benign-v2 experiment_results/proxy-observability-review-20261023/benign-reviewed.png
MPLCONFIGDIR=/tmp/proxy-review-mpl .venv/bin/python -B -m experiments.plot_proxy_monitor experiment_results/proxy-observability-20261023/continuous-v2 experiment_results/proxy-observability-review-20261023/continuous-reviewed.png
MPLCONFIGDIR=/tmp/proxy-review-mpl .venv/bin/python -B -m experiments.plot_proxy_monitor experiment_results/proxy-observability-review-20261023/final-benign experiment_results/proxy-observability-review-20261023/final-benign.png
```

Saída integral em tests.log: **128 testes, OK**, sem falhas. O aviso de run
incomplete emitido pela suíte pertence à fixture de finalização com falha, não ao
smoke real. Novos testes verificam ordem exec/stats, source_errors com sucesso e
falha, timestamps próprios, preservação de null e uso exclusivo de pontos na
figura. Diff completo contra HEAD, incluindo arquivos novos, em complete.diff.
Nenhum commit ou push foi feito. Não houve mudança de RTT, ataques, detectores,
políticas do proxy, coletor ou resultados anteriores nesta revisão.
