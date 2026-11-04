# Auditoria e instrumentação diagnóstica — 04/11/2026

## A. Estado inicial

- Branch: `refactor/project-organization`.
- HEAD inicial e final: `c918a772246690526eb9127716a3bce80b44301a`.
- Working tree inicialmente limpo, sem alterações locais a preservar. Nenhum commit novo foi criado; a intervenção permanece no working tree para revisão.
- Referência `ae052a829b0ddc1482f7b81b5880069525d083a2` presente e ancestral do HEAD. O único commit posterior modifica `docs/relatorio_2026_11_04_1.md`; não havia alteração posterior de código.
- Nenhum `AGENTS.md` encontrado na árvore inspecionada. O sandbox falhou na inicialização de loopback; comandos foram executados com a autorização de execução externa ao sandbox.
- Host Python 3.12.3; fontes reconstruídas em Python 3.12.10; vítima efetivamente em **Python 3.9.23**, conforme inspeção da imagem. Portanto, a descrição de Python 3.12 não se aplica a todos os componentes. Não foi feita migração da vítima.
- Host com 12 CPUs lógicas e aproximadamente 15,3 GiB de RAM, cerca de 9,4 GiB disponíveis na inspeção. Nenhum contêiner em execução inicialmente; redes experimentais preexistentes vazias.

Componentes auditados antes de editar: `normal_traffic`, `traffic_injectorV0`, `source_runner`, `source_manager`, `source_journal`, `request_logger`, `ground_truth`, `source_experiment`, `docker_manager`, `simple_server`, Dockerfiles, relógios, CPU, exportação, extração e testes existentes. A biblioteca padrão foi inspecionada somente de leitura, inclusive nas imagens efetivamente utilizadas; sua implementação privada não é dependência da instrumentação.

O plano mínimo adotado foi: observar o executor por `submit/Future/shutdown` públicos; reutilizar os instantes científicos; registrar a espera legítima já existente; obter tempos do worker retornando metadados pequenos; gravar JSONL assíncrono e limitado; analisar offline; validar duas cargas legítimas e comparar on/off sem ajustar taxas. Não foi necessária alteração de modelo, política de filas ou arquitetura do servidor.

## B. Diagnóstico do gerador

### Modelo estatístico identificado

**Confirmado pelo código:** `normal_http_request_worker`, em `simulator/normal_traffic.py:160`, cria `random.Random(worker_seed(seed,"normal",worker_index))`. A amostragem em `:195` usa `rng.expovariate(rps_per_worker)`. A taxa é por entidade/fonte, em oportunidades esperadas por segundo no modelo idealizado; o agregado nominal é `clientes × rate`. No modo contêiner, `source_manager.py:115` distribui o orçamento agregado de threads entre fontes e preserva o índice global do worker; `source_runner.py` inicia um produtor por fonte. Não existe adaptação sistemática de λ ao longo da execução legítima ou realimentação pela CPU.

As fontes possuem instâncias de RNG separadas, seeds derivadas por SHA256 de seed/componente/índice (`experiment_config.py:289`). Trata-se de independência operacional dos estados pseudoaleatórios, não demonstração matemática de independência de todas as chegadas realizadas. Seeds iguais reproduzem a sequência de sorteios, não o escalonamento do sistema.

**Propriedade teórica:** sorteios exponenciais de parâmetro λ têm média `1/λ`. Um processo com intervalos exponenciais independentes, primeira chegada também exponencial e sem custos adicionais teria contagens Poisson de média/variância `λT`; fontes independentes poderiam ser superpostas.

**Comportamento real confirmado:** o laço de `normal_traffic.py:173` submete primeiro, acompanha os Futures e filtra pendências, e somente depois sorteia/espera o próximo intervalo. A primeira submissão é imediata. O tempo de despacho não é compensado. Assim, intervalos entre submissões incorporam espera exponencial, bookkeeping, escalonamento e despacho. O custo da filtragem de pendências pode depender do número de tarefas ainda não concluídas. Os intervalos realizados não têm independência/i.i.d. garantida.

**Classificação:** geração baseada em **esperas relativas exponenciais com despacho inicial imediato e execução HTTP assíncrona limitada**. Aproxima um modelo Poisson somente quando os custos e as limitações operacionais forem desprezíveis, em horizontes adequados. Não é correto afirmar Poisson homogêneo exato somente por `expovariate`. As referências a “Poisson” nos comentários/logs antigos são uma idealização, não uma propriedade comprovada da execução.

### Modelo operacional e filas

`normal_traffic.configure` (`:44`) cria `ThreadPoolExecutor(max_workers=...)`. O produtor não espera a resposta anterior para submeter. O executor tem fila de trabalho sem limite de admissão explícito no código atual; limpar a lista local de Futures concluídos não limita sua fila. No modo contêiner, quatro threads agregadas viram duas por fonte nesta validação.

Uma tarefa somente produz início científico dentro de `_send_one_normal` (`normal_traffic.py:70`), por `RequestLogger.begin` (`request_logger.py:35`). Esse início ocorre no cliente após a tarefa obter execução e antes da chamada Requests; não é submissão nem chegada à vítima. Se as threads estiverem ocupadas, a oferta pode continuar e o início HTTP pode atrasar. Isso é oferta em malha aberta com execução limitada, não modelo fechado que espera cada resposta. Dependências operacionais e filas tornam a realização distinta da oferta ideal.

Requests usa timeout escalar configurado para conexão/leitura, não um deadline total de toda a operação. Uma resposta lenta pode ocupar uma thread por mais tempo; o código não introduz cancelamento automático do trabalho remoto. A sessão Requests é compartilhada entre as tarefas de um produtor; nenhuma alteração desse mecanismo foi feita. Contenção/efeitos adicionais da sessão são hipótese não isolada nesta intervenção.

O fim científico é amostrado antes dos contadores e da persistência de conclusão (`normal_traffic.py:99` e `RequestLogger.finish:64`). O `duration_ms` científico inclui o intervalo integral entre os instantes do logger, inclusive o caminho após begin e antes da chamada HTTP; a duração do observador operacional de latência é capturada em outro ponto e **não substitui** essa feature.

`stop_http_traffic` sinaliza parada sem cancelar tarefas já submetidas. `drain` (`normal_traffic.py:121`) usa o orçamento existente de 30 s e `shutdown(wait=False)`, acompanhando Futures. Fontes incompletas são tratadas pela política existente de encerramento (`source_runner.py:105` em diante); não foi adicionada política de descarte ou cancelamento. O controlador da fonte consulta o tempo/parada em passos de aproximadamente 10 ms, de modo que inícios de cauda muito próximos de T podem existir.

### Origem ofensiva: auditoria somente de leitura

`traffic_injectorV0.http_request_worker:147` tem mecanismo contínuo de primeira submissão imediata e esperas exponenciais relativas, com admissão de evento antes da submissão. O perfil periódico (`:269`) é diferente: sorteia a primeira oportunidade dentro de cada janela, usa limites temporais e reserva de slot antes da submissão (`:253`); oportunidades podem não ser submetidas quando não há slot. Esses mecanismos foram apenas auditados. Nenhuma linha do módulo ofensivo ou de seus padrões foi alterada, e nenhum tráfego ofensivo foi executado.

### Limitações anteriores e conclusões medidas

Antes havia início/fim HTTP nos journals, mas não prazos legítimos relativos, chamada de submit e entrada da tarefa. Agora esses pontos podem ser distinguidos. Continua inexistindo uma agenda independente cumulativa que permita perguntar “quantas chegadas ideais teriam ocorrido sem nenhum custo de despacho”; não foi fabricada tal agenda.

As diferenças entre taxa nominal e contagem por segundo, isoladamente, não diagnosticam saturação. As validações abaixo mostram atrasos transitórios de executor observados, sem tarefas não resolvidas após drenagem. Não demonstram saturação permanente do gerador ou da vítima.

## C. Diagnóstico da vítima

`simulator/app/simple_server.py:130` inicia `ThreadingHTTPServer` e `ProcessPoolExecutor`. O número de processos vem de `INSTANCE_MAX_CONCURRENT_REQUESTS`, configurado por `server.process_pool_workers` via Docker; foram dois processos. Os custos fixos permanecem `/light=10000`, `/medium=100000`, `/expensive=1000000` iterações do mesmo kernel (`:38`). Essas quantidades não são promessa de tempo de CPU fixo.

Na biblioteca padrão das imagens, `ThreadingHTTPServer.daemon_threads=True`. Uma conexão aceita gera uma thread; keep-alive permite vários atendimentos sequenciais na mesma thread. Não há limite de threads/conexões ativas definido pela aplicação. O backlog configurado pelo servidor é cinco; isso não significa no máximo cinco conexões ou handlers ativos e seu efeito depende do kernel.

O handler chama o pool de processos e bloqueia em `.result()` (`simple_server.py:106`). A implementação padrão tem fila de chamadas entre processos limitada a workers+1 (três aqui), mas o controle de tarefas pendentes no processo pai não impõe esse limite de admissão a `submit`. Não se conclui que todo o backlog do aplicativo esteja limitado a três trabalhos. Não foi usada profundidade privada da fila para medir congestionamento.

O caminho anterior não definia timeout de handler ou de `.result()`, nem cancelava trabalho ao expirar o timeout do cliente. Exceções de worker/pool, parsing ou escrita seguem o tratamento padrão do servidor e podem encerrar a conexão. A instrumentação registra o tipo observado e **relança a mesma exceção**, sem fabricar resposta 500 ou transformar falha em sucesso.

Antes existiam logs padrão HTTP no stderr e `elapsed` no corpo, medido ao redor do pool/sleep. Não era possível separar espera até o worker de sua execução. Agora há tempos de handler/submissão/worker/retorno/escrita, concorrência e CPU de processo durante o kernel. A CPU científica continua sendo exclusivamente Docker Stats.

O ponto “recebido” disponível é entrada em `do_GET` (`:78`), após parsing da linha/cabeçalhos; não mede conexão aceita, primeiro byte ou corpo completo arbitrário. Fim do handler (`:95`) não é confirmação de que o cliente recebeu tudo. O envio do status e a finalização da escrita são pontos distintos: um erro posterior pode coexistir com status 200 registrado. Essas distinções estão no [dicionário de métricas](metric_definitions.md).

## D. Instrumentação implementada

### Arquivos

| Arquivo | Alteração e motivo |
|---|---|
| `simulator/diagnostics.py` | Writer assíncrono com fila limitada, contadores de perda e adaptador das interfaces públicas do executor. |
| `simulator/normal_traffic.py` | Quatro linhas observam início/intervalo da espera real e registram o prazo relativo após seu retorno; sorteio e espera anteriores preservados. |
| `simulator/request_logger.py` | Hooks opcionais que reutilizam os instantes e IDs científicos, sem modificar campos ou schemas. |
| `simulator/source_runner.py` | Habilita adaptador/writer por manifesto e registra fechamento depois da drenagem existente. |
| `simulator/source_manager.py` | Propaga diagnóstico somente quando habilitado. |
| `simulator/app/simple_server.py` | Caminho opcional de observação do handler e wrapper computacional com retorno de tempos; kernel e custos intactos. |
| `simulator/experiment_config.py` | Grupo opcional `diagnostics`, validação e omissão do padrão no JSON histórico. |
| `simulator/docker_manager.py` | Volume e variáveis opcionais de diagnóstico para uma vítima fixa. |
| `simulator/source_experiment.py` | Diretório, metadados/hashes, auditoria de relógio da vítima e solicitação de flush antes de remover o contêiner. |
| `Dockerfile`, `docker/Dockerfile.sources` | Empacotam o módulo diagnóstico, sem novas dependências. |
| `experiments/diagnostic_run.py` | Entrypoint de validação exclusivamente legítima com tags de imagem separadas. |
| `experiments/summarize_diagnostics.py` | Resumos offline, contadores, atrasos, horizontes, estatística descritiva e reconciliação com registros científicos. |
| `experiments/configs/diagnostic_validation/` | Oito configurações diretas e uma regressão curta proxy, sem campanhas. |
| `tests/test_diagnostics.py` | 20 testes de instrumentação e resumo, incluindo perdas, cancelamentos, timestamps, fechamento incompleto, relógios e concorrência. |
| `reports/diagnostic_observability_20261104/` | Relatório, dicionário, comandos, resultados compactos, exemplos e hashes. |

### Habilitação, registros e armazenamento

```json
"diagnostics": {"enabled": true, "queue_capacity": 4096}
```

Padrão: desabilitado. Habilitação exige fontes em contêineres, uma vítima inicial fixa e autoscaler desabilitado. Funciona em `direct` e `proxy`. Configurações históricas mantêm seu JSON padrão, sem novo grupo quando o diagnóstico está no padrão desabilitado. Os testes confirmam a compatibilidade.

É necessário **reconstruir as imagens** que contêm a aplicação e as fontes; o código existente pode reutilizar uma tag local antiga. Nesta validação foram usadas tags isoladas `edos_target_app:diagnostics-20261104` (ID `3f0a418c93db…`) e `edos_sources:diagnostics-20261104` (ID `b8e3996d9b73…`), preservando as tags históricas. O build reinstalou apenas os requisitos já fixados do Dockerfile das fontes; não foram acrescentadas dependências.

Estrutura por execução:

```text
raw/diagnostics/metadata.json
raw/diagnostics/victim_clock_validation.json
raw/diagnostics/victim/events.jsonl
raw/diagnostics/victim/events.summary.json
raw/source_artifacts/<source_id>/output/diagnostics/events.jsonl
raw/source_artifacts/<source_id>/output/diagnostics/events.summary.json
```

Os arquivos são exportados como evidências pelo exportador existente: diagnósticos da vítima em `evidence/other/diagnostics/`, fontes em `evidence/sources/.../diagnostics/`. Nenhuma tabela científica recebeu colunas novas. Resumos são gerados fora do dataset, não alimentam detectores e não substituem as cinco features.

Eventos da fonte: prazo relativo, chamada de submissão, entrada/saída de tarefa, início/fim HTTP, rejeição, cancelamento e fechamento. Registros da vítima: entrada/fim de handler, etapas computacionais, status/erro e concorrência. Os nomes, unidades, inclusão, ausências, horizontes e limitações de **cada métrica** estão em [metric_definitions.md](metric_definitions.md).

### Custos, relógios e correlação

O novo caminho crítico faz amostragens de relógio, locks curtos, contadores e enfileiramento não bloqueante; não abre arquivos para cada novo evento. A fila tem capacidade explícita; saturação descarta diagnóstico e incrementa `dropped`, sem cancelar HTTP. Não há tabela ilimitada de tentativas em memória no observador; cada tarefa existente recebe um pequeno contexto e as análises por ID são offline. O armazenamento em disco cresce com a duração/tráfego, sem retenção ilimitada em RAM.

O worker não escreve arquivos: devolve um pequeno dicionário pelo mecanismo existente de resultado do pool. Isso acrescenta custo de IPC e relógios, mensurado apenas de forma limitada na comparação abaixo. O mecanismo de execução e o número de processos não mudam. O kernel `_burn_cpu` é o mesmo.

Nenhum cabeçalho foi acrescentado. O ID de requisição já transmitido serve à correlação explícita. `run_id` da vítima fica nulo, vinculado pelo diretório e metadados; sondagens ficam separadas. Não há correspondência arbitrária por timestamp.

Fontes e vítima usam CLOCK_MONOTONIC. As fontes mantêm a auditoria existente de namespaces, offsets nulos, kernel, implementação e brackets do host; a vítima recebe a mesma auditoria antes da origem experimental. Workers devolvem seu namespace/relógio. As durações worker↔handler exigem correspondência de namespace. Os namespaces dos contêineres não precisam ter o mesmo identificador do host quando há prova explícita de offsets nulos e relógio nativo comparável.

`ExperimentClock` (`ground_truth.py:20`) mantém epoch e monotônico como amostras distintas. Captura TCP continua usando epoch e a subtração documentada da origem epoch; não se igualam timestamps de instrumentos diferentes. Não foi implementada medição precisa de latência fonte→vítima ou de primeiro byte de rede.

## E. Validação

### Testes automatizados

Rodadas de regressão executadas: 88/88, 100/100, 263/263, 265/265, 268/268 e **271/271 aprovados** na rodada final. Não houve falha de asserção, erro ou teste ignorado nessas rodadas. As saídas reais estão anexadas.

Comando final:

```sh
.venv/bin/python -B -m unittest tests.test_diagnostics tests.test_direct_topology tests.test_topology_integrity tests.test_experiment_config tests.test_feature_extraction tests.test_dataset_validation tests.test_source_containers tests.test_capture_lifecycle tests.test_dataset_export tests.test_http_proxy tests.test_proxy_monitor tests.test_single_victim tests.test_cpu_accounting_audit tests.test_http_timing_audit tests.test_application_operations -q
```

Cobertura: timestamps científicos preservados; identidade e ordem de etapas; falhas relançadas e registradas; cancelamento real de Future pendente; rejeição de submit; IDs únicos; coerência de contadores; duas tarefas/handlers concorrentes; escrita indisponível; fila diagnóstica saturada; sorteio exponencial e despacho imediato iguais com observação on/off; ambos os modos; ausência de prazo fabricado; oportunidade posterior a T; divergências de contador, perda diagnóstica e timestamp científico detectadas; contratos de captura, exportação, CPU, falhas HTTP e nulos.

Teste D3 executado **separadamente**, com um erro/reprovação esperado e não ocultado:

```sh
.venv/bin/python -B -m unittest tests.test_development_d3.D3Tests.test_real_authority_configs_and_exclusive_seed_reservations -q
```

Resultado: `ValueError: Bound source changed: Dockerfile`, saída 1. O teste não está contado entre os 271 aprovados. A autoridade antiga permanece inválida; nenhum hash foi atualizado. Seu reaproveitamento já não era autorizado após a topologia direta.

Uma inspeção administrativa de runtime coincidiu com o encerramento de um contêiner e retornou HTTP 409; não foi usada como evidência de limites. A lacuna foi delimitada: foram inspecionadas as duas imagens em contêineres temporários sem rede, e os `HostConfig` efetivos foram gravados na regressão proxy. Não houve falha de coleta científica associada. O snapshot tardio vazio não é prova dos recursos das oito execuções diretas.

### Configuração e reprodução

Todas as execuções diretas: 16 s, duas fontes, `/medium`, quatro threads de envio agregadas (duas/fonte), dois processos computacionais, timeout Requests de 2 s, monitoramento em ticks de 1 s com polling solicitado de 0,25 s, captura habilitada, sem atacantes/autoscaling. A intensidade moderada foi escolhida para observação, não para saturação agressiva. Seeds pareadas: `2310041` e `2310042`.

Não foram impostas novas quotas Docker. A configuração e a inspeção das imagens/HostConfig proxy mostram `Memory=0`, `NanoCpus=0`, `CpuQuota=0`, cpuset vazio e ausência de PidsLimit explícito. Isso significa ausência de quotas explícitas nesses campos, não recursos infinitos ou caracterização de todos os limites ancestrais do host. Orçamentos de concorrência, timeout e drenagem existentes foram preservados.

Comandos de construção, execução, análise e verificação estão em [commands.txt](commands.txt). Exemplo:

```sh
docker build -t edos_target_app:diagnostics-20261104 .
docker build -f docker/Dockerfile.sources -t edos_sources:diagnostics-20261104 .
.venv/bin/python -B -m experiments.diagnostic_run --config experiments/configs/diagnostic_validation/low_enabled_r1.json --output experiment_results/diagnostic-observability-20261104/low_enabled_r1/raw --dataset-output experiment_results/diagnostic-observability-20261104/low_enabled_r1/dataset --victim-image edos_target_app:diagnostics-20261104 --source-image edos_sources:diagnostics-20261104
.venv/bin/python -B -m experiments.summarize_diagnostics experiment_results/diagnostic-observability-20261104/low_enabled_r1/raw --output <novo-resumo.json>
```

Os diretórios brutos/datasets recusam sobrescrita. Resumos finais conferidos: `<execução>/diagnostic_summary_final.json`; validação científica: `<execução>/verification/verification.json`. Base completa: `experiment_results/diagnostic-observability-20261104/`. As oito comparações diretas usaram as mesmas duas imagens. O metadado adicional de limites foi acrescentado ao host depois, na regressão proxy; os hashes individuais preservam essa distinção, sem reescrever os registros anteriores.

### Resultados observados

Taxa efetiva abaixo = inícios científicos em `[0,16)` divididos por 16; total inclui a drenagem. Duração média usa todas as conclusões observadas, sem confundi-la com CPU. Cada par mantém seed e configuração, variando o diagnóstico.

| Condição | Diagnóstico | Seed | Inícios no plano/total | Inícios/s no plano | Duração HTTP média (ms) | CPU média dos ticks suportados (% Docker) |
|---|---|---:|---:|---:|---:|---:|
| Baixa, nominal 2 RPS | OFF | 2310041 | 34/34 | 2,1250 | 16,988 | 4,033 |
| Baixa, nominal 2 RPS | ON | 2310041 | 34/34 | 2,1250 | 16,028 | 3,881 |
| Baixa, nominal 2 RPS | OFF | 2310042 | 42/42 | 2,6250 | 16,818 | 2,787 |
| Baixa, nominal 2 RPS | ON | 2310042 | 42/42 | 2,6250 | 16,780 | 3,057 |
| Moderada, nominal 24 RPS | OFF | 2310041 | 381/381 | 23,8125 | 29,971 | 35,476 |
| Moderada, nominal 24 RPS | ON | 2310041 | 380/381 | 23,7500 | 30,235 | 35,947 |
| Moderada, nominal 24 RPS | OFF | 2310042 | 428/429 | 26,7500 | 30,942 | 36,556 |
| Moderada, nominal 24 RPS | ON | 2310042 | 427/428 | 26,6875 | 31,078 | 37,163 |

Todas as tentativas acima concluíram com HTTP 200, sem falhas. A quantidade configurada não foi usada como igualdade determinística de aprovação. As taxas observadas distintas entre seeds não foram corrigidas.

| Execução ON | Prazos em `[0,T)` | Taxa de prazos/s | Primeiros despachos sem prazo independente | Prazos >= T | Handlers científicos correlacionados | Pico de handlers |
|---|---:|---:|---:|---:|---:|---:|
| Baixa r1 | 32 | 2,0000 | 2 | 2 | 34 | 2 |
| Baixa r2 | 40 | 2,5000 | 2 | 2 | 42 | 2 |
| Moderada r1 | 378 | 23,6250 | 2 | 3 | 381 | 3 |
| Moderada r2 | 425 | 26,5625 | 2 | 3 | 428 | 4 |

Não houve prazo dentro do plano sem submissão observada, rejeição, cancelamento ou tarefa não resolvida após drenagem. Nos ensaios moderados ON, um dos três prazos >= T foi efetivamente submetido/iniciado na cauda; os dois restantes são próximas oportunidades normalmente interrompidas pelo fim. Os inícios de cauda foram `16,003047431 s` e `16,001510493 s`, preservados e separados. Não são apresentados como perdas nem escondidos no denominador da taxa do plano.

As dez sondagens de preparação de cada execução foram registradas pela vítima e excluídas da contagem científica por falta de ID da tentativa científica. Os registros ON tiveram zero descartes, zero erros de escrita, contadores reconciliados e pares início/fim completos. Nas execuções OFF não foram criados diretórios diagnósticos nem hooks habilitados; observações não disponíveis permanecem nulas nos resumos.

### Atrasos e concorrência

| Execução ON | Média submissão→início HTTP (ms, agregada) | Máximo observado entre fontes (ms) | Média submissão→worker (ms) | Máximo submissão→worker (ms) | Pico da diferença submetidas−tarefas iniciadas |
|---|---:|---:|---:|---:|---:|
| Baixa r1 | 0,223 | 0,386 | 0,474 | 0,654 | 1 |
| Baixa r2 | 0,225 | 0,451 | 0,483 | 0,736 | 1 |
| Moderada r1 | 1,844 | 82,278 | 0,579 | 8,916 | 3 |
| Moderada r2 | 1,582 | 79,136 | 0,586 | 11,332 | 3 |

A diferença pendente é um contador derivado de observações públicas, **não** profundidade exata de fila. O atraso até worker inclui IPC, serialização e escalonamento, não somente espera em fila. Os valores demonstram atrasos operacionais transitórios do lado gerador e algumas esperas do lado vítima; não bastam para declarar saturação.

Exemplo correlacionado (`moderate_enabled_r1`, `normal_2`, ID diagnóstico 77, `request_normal_2_000000077`): prazo `6,141924065 s`; chamada submit `6,142040697 s`; entrada de tarefa `6,224309029 s`; início HTTP `6,224318389 s`. A espera submissão→HTTP foi 82,278 ms, enquanto a duração HTTP foi 53,685 ms, o handler 11,829 ms e submissão→worker 0,475 ms. São intervalos distintos, sem atribuir a duração HTTP à CPU.

Outro exemplo migra de prazo em `10,960341562 s` para início HTTP em `11,024401709 s`. A feature continua contando a tentativa na janela **11**, conforme seu início efetivo, não na janela do prazo. Exemplos completos em `examples.json`.

### Caracterização estatística descritiva

| Execução ON | Sorteios observados | Média do intervalo sorteado (s) | Referência 1/λ (s/fonte) | Média dos inícios por janela | Variância amostral | Variância/média |
|---|---:|---:|---:|---:|---:|---:|
| Baixa r1 | 34 | 0,982117 | 1,000000 | 2,1250 | 1,4500 | 0,6824 |
| Baixa r2 | 42 | 0,771584 | 1,000000 | 2,6250 | 1,9833 | 0,7556 |
| Moderada r1 | 381 | 0,083509 | 0,083333 | 23,7500 | 23,4000 | 0,9853 |
| Moderada r2 | 428 | 0,074429 | 0,083333 | 26,6875 | 12,3625 | 0,4632 |

Os intervalos e vetores completos de contagem estão nos resumos, permitindo distribuição empírica/CDF. Incluem o último intervalo sorteado, mesmo interrompido; a análise de execução/início separa horizontes. Há só 16 janelas por repetição, primeiro envio imediato por fonte e custos de despacho. Nenhuma razão variância/média foi usada para aprovar/reprovar um modelo ou diagnosticar saturação. Não se calculou p-valor ou ajuste que aparentasse caracterização geral a partir dessas amostras.

### Sobrecarga limitada e modo proxy

Nos pares moderados, a média HTTP ON−OFF foi aproximadamente +0,264 ms e +0,136 ms; CPU média +0,471 e +0,607 pontos percentuais. Nos pares baixos, −0,960 ms/−0,151 pp e −0,037 ms/+0,270 pp. Houve uma tentativa a menos dentro do plano nos pares moderados ON, com diferenças de cauda explicitadas. Não houve falha nos pares.

Essas observações são descritivas, com duas repetições e sem randomização ampla ou controle de todas as atividades do host. Não provam equivalência nem estabelecem regressão de desempenho; a sobrecarga não é nula por definição. Concorrência de handler não está disponível no OFF e não foi estimada artificialmente.

Regressão proxy: 8 s, mesma seed r1, duas fontes a 1 RPS, `/medium`, diagnóstico ON. Foram 15 tentativas/conclusões HTTP 200, 15 handlers correlacionados, pico de dois handlers, sem perda diagnóstica. O cabeçalho existente atravessou NGINX e o segmento histórico `source_proxy` foi reconciliado. A topologia direta usa `source_victim`. Todas as nove execuções passaram na verificação independente das cinco features.

## F. Preservação científica e integridade

Confirmado no código, nos testes e nas nove verificações integradas:

1. Sorteio e espera exponenciais existentes mantidos; nenhum compensador de taxa ou quantidade determinística por segundo foi introduzido. O teste on/off compara o mesmo sorteio com seed controlada, sem presumir determinismo de agendamento.
2. `request_starts` continua usando início científico efetivo no cliente. Hooks reutilizam esse instante; planejamentos não entram na feature.
3. `mean_duration_ms` continua incluindo todas as tentativas concluídas, inclusive falhas com duração, pela janela de conclusão e com duração integral. Tentativas incompletas não recebem fim/duração artificial; janelas sem conclusão permanecem nulas.
4. CPU científica mantém a mesma fórmula/normalização Docker e os ticks suportados do coletor, inclusive fallback histórico; CPU do worker é somente diagnóstico separado. Não se alteraram `StatsCollector` ou extrator.
5. Janelas de um segundo, origem, horizonte de cauda, pontos/filtros de captura, inclusão de pacotes sem payload/retransmissões e soma de payload continuam os mesmos.
6. PCAP independente = CSV = features de rede em todas as nove execuções; zero perdas pelo kernel em todas as capturas CSV/PCAP. HTTP e CPU foram reconciliados com os registros originais pelo verificador existente.
7. Nenhum cabeçalho novo: observou-se 196 bytes TCP de ingresso por tentativa nestes ensaios, ON e OFF, em ambas as topologias. É constatação destas capturas, não definição geral de payload único HTTP ou garantia de ausência futura de retransmissões. Contagens de pacotes podem variar com o timing.
8. Schemas científicos e exportador mantidos byte a byte; os diagnósticos são evidências adicionais já aceitas pelo exportador, sem novas colunas científicas ou entradas para os detectores.
9. Z-Score, CoV, EWMA, CUSUM, limiares, critérios/protocolos e módulos ofensivos não foram modificados. Comparações de hash com o HEAD estão anexadas em `preservation.json`.
10. Nenhum dataset histórico foi sobrescrito. Todos os resultados novos usam uma raiz exclusiva, e o exportador/runner mantém recusa de sobrescrita. Não se executaram calibração, teste científico, ataques ou campanhas de avaliação de detectores.

Todos os validadores de dataset registram `EXECUTION_WORKTREE_CLEAN` como aviso, pois as alterações não estão commitadas. O aviso não foi suprimido; os relatórios mantêm HEAD, proveniência, configuração, IDs de imagem e hashes. Todos os outros checks aplicáveis passaram. A autoridade D3 continua reprovada no teste separado.

A limpeza final confirmou nenhum contêiner das validações e nenhum tcpdump em execução, redes preexistentes vazias e preservadas. As imagens novas usam tags próprias; contêineres alheios já parados foram preservados. Evidência em `cleanup.json`.

## G. Limitações e pendências

| Relevância | Limitação/pendência | Tratamento nesta intervenção |
|---|---|---|
| Alta para futura campanha | Nova revisão de código não tem autoridade D3 anterior | Gate/hashes mantidos; revisar/versionar protocolo futuro separadamente, sem campanha automática |
| Alta para interpretação | Prazo relativo não é agenda ideal independente; primeiro envio não possui prazo independente | `planned_at=null` quando ausente; métricas distinguem primeira submissão, plano e cauda |
| Alta em falhas abruptas | SIGKILL, travamento de disco ou morte de worker podem deixar eventos incompletos | Resumos, perdas e reconciliações explícitos; trabalho sem resultado pode não devolver tempos do worker; não fabricar etapas |
| Média para implantação | Tags Docker antigas podem não conter diagnóstico | Reconstrução obrigatória e tags/IDs separados; resumo ausente não permite aprovação diagnóstica |
| Média para observação futura | Planejamento ofensivo não instrumentado; tráfego ofensivo não validado | Módulo ofensivo intacto; somente observação genérica de executor/logger está disponível, sem afirmar cobertura de cada perfil |
| Média para generalização | Duas seeds, execuções de 16 s e apenas `/medium` na carga real | Não concluir Poisson, saturação ou equivalência de desempenho; testes preservam os três budgets/endpoints |
| Média para relógios | Auditoria é finita; epoch e monotônico não são amostrados atomicamente | Sem latência unidirecional de rede; durações locais e origem conforme contrato; sem promessa de deriva nula universal |
| Média para arquitetura | Oferta contínua tem fila de executor sem admissão limitada; handlers também não têm cap explícito | Documentado; nenhum limitador, cancelamento ou mudança comportamental foi implementado |
| Média para ambiente | Vítima continua Python 3.9.23; não houve migração para 3.12 | Divergência explicitada, não corrigida silenciosamente |
| Baixa neste escopo | Sem timestamps de aceitação TCP, primeiro byte ou recebimento completo de corpo arbitrário | Ponto de observação do handler definido com precisão; não propor observabilidade adicional sem necessidade |
| Baixa neste escopo | Não há HostConfig salvo individualmente de cada comparação direta | Código/opções e imagens preservados; inspeção de imagens e HostConfig proxy confirmam ausência de quotas explícitas; snapshot tardio não usado |

Os seis critérios de conclusão foram atendidos no escopo: modelo real descrito; prazos/submissões/inícios delimitados; atendimento e processamento observáveis; registros reconciliados com perdas explícitas; contratos científicos preservados; infraestrutura mais observável sem depender da escolha futura de ataque. A evidência sustenta essa preparação, sem afirmar ausência absoluta de saturação, aderência estatística perfeita ou equivalência de desempenho.
