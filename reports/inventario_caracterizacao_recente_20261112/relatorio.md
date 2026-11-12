# Inventário da caracterização exploratória recente

Data do inventário: 12/11/2026. Escopo: arquivos locais; nenhuma coleta ou análise estatística nova. **Confirmada** significa configuração ou evento em artefato primário; **documentada**, afirmação em relatório ou plano; **inferida**, encadeamento indireto; **não determinada**, falta de prova. A matriz linha a linha está em [matriz.csv](matriz.csv). Caminhos são relativos à raiz do repositório.

## Resumo executivo

A rodada recente começou com a adaptação da topologia direta e a instrumentação em **04/11** (commits `ae052a8`, `f1701cf`), passou pela exploração de capacidade em 04–05/11, pela caracterização A2/A1 em 06/11, pelos pilotos ofensivos isolados e combinados em 07–08/11 e chegou ao primeiro contrato direto de 80 execuções em **08/11** (`bab3729`, `docs/scientific_protocol_direct_20261108.json`). O contrato C1.3.5/O3 e o plano ambiental com dois pilotos em 09/11 são marcos posteriores de congelamento (`docs/scientific_protocol_direct_c135_o3_20261108.json`, `reports/energy-powersaver-20261109/report.md:3-20`). Assim, a fronteira não é simplesmente uma data: os pilotos de 09/11 validam a configuração já escolhida para o ambiente final; os 80 resultados definitivos não entram neste inventário.

Quatro grupos: somente legítimo; assimetria isolada; flooding isolado; tráfego combinado. A matriz consolidada contém **42 linhas: 39 execuções concluídas e 3 configurações somente planejadas**. Variaram fonte, RPS/fonte, agregado, endpoint, presença de legítimos, diagnóstico ON/OFF e concorrência ofensiva. A1 longa efetivamente testou 16 e 32 RPS agregados, não 8/64; 8/64/96/128 pertencem à exploração curta de capacidade (`reports/capacity_exploration_20261104/selected_matrix.md:1-13`; `experiment_results/legitimate-characterization-a1-20261106T202205Z/report.md:1-35`). Selecionaram-se L2 (2×8), A3 (2×4) e, no protocolo, F96 (2×32, concorrência 96). A escolha de F96 contradiz a recomendação explícita do relatório B2-F96 de conservar 64; a motivação dessa reversão não está estabelecida pelos registros examinados.

## Linha do tempo e delimitação

| Data | Evidência e decisão | Estatuto |
|---|---|---|
| 04/11 | Topologia direta, captura `source_victim` e cinco features preservadas (`docs/relatorio_2026_11_04_1.md:10-155`, `ae052a8`). Instrumentação de gerador/vítima (`docs/relatorio_2026_11_04_2.md`, `f1701cf`). | Documentada no código e relatórios |
| 04–05/11 | Capacidade: cinco pilotos P1–P5 e 11 das 14 células principais planejadas. `reports/capacity_exploration_20261104/runs.csv` registra os 16 ensaios concluídos. C3_ON_r2, C3_OFF_r2 e C5_ON_r2 não foram feitos após C5 acionar o limite de progressão por espera p95 do worker >100 ms (`campaign_report.md:5-9`). | Confirmada para execuções; plano em `selected_matrix.md` |
| 06/11 | A2 compara `/medium` e `/expensive`, duas repetições por endpoint; A1 testa L2,L6,L3,L7 nessa ordem. `2423427`, `8182681`; relatórios nos diretórios de resultados. | Confirmada |
| 07/11 | Proteção das composições (`ab8961c`), piloto integrado de assimetria A1 isolado (run `d5541220539243f0872a09dcf977bc39`), B1.2 A2–A4 e F1–F5. | Confirmada; `reports/b12-isolated-20261107T200251Z/report.md:1-23` |
| 07–08/11 | B2-L, B2-A, B2-F e B2-F96, uma execução cada, sucessivas. Relatórios e `raw/effective_config.json` respectivos. | Confirmada |
| 08/11 | Contrato direto já nomeia L2/A3/F96 e concorrência 96 (`docs/scientific_protocol_direct_20261108.json:282-330,465-488`); revisão C1.3.5/O3 (`25bd463`, `a2e9f44`). | Confirmada para contrato; razão da reversão F2→F96 não determinada |
| 09/11 | Um piloto A3 e um F96 sob `power-saver`; plano de 80 slots congelado depois dos pilotos (`reports/energy-powersaver-20261109/report.md:1-20,52-65,120-133`). | Confirmada; validação de transição, não varredura |

Rodadas anteriores, em especial `development-d1-20261027`, `development-d3-*`, `scientific-reduced-20261029` e `stage14*`, têm código, topologia ou objetivo diferentes e **não alimentam as tabelas**. O A1 isolado de 07/11 é exceção expressa: B1.2 o reutilizou como `A1-reference`, sem repetir a coleta (`reports/b12-isolated-20261107T200251Z/report.md:5-13,150-165`). Os diretórios genéricos antigos `normal_baseline`, `clients_rps_grid` etc. não foram promovidos à rodada recente por semelhança de nome.

## Matriz completa de configurações

`L` = legítimo; `O` = ofensivo. RPS abaixo é **nominal**, por fonte × agregado. Concorrência é orçamento agregado do grupo indicado, repartido igualmente entre as fontes. Em B1.2/B2: dois workers, topologia direta, timeout HTTP 2 s, diagnósticos/captura ON, 150 s, ataque [30,60), observações PRE [0,30), ACTIVE [30,60), POST [60,150). A1: dois workers, 150 s, recorte principal [30,150). Capacidade: dois workers, `/medium`, 12 s nos pilotos e 20 s nas células C; não corresponde ao protocolo ofensivo.

### Grupo 1 — somente legítimo

| ID e pasta sob `experiment_results/` | L fontes × RPS = total | Endpoint; concorrência L | Duração; modo | Execução/situação |
|---|---:|---|---|---|
| `capacity-exploration-20261104/P1_8rps` | 2×4=8 | `/medium`; 64 | 12 s; diagnóstico ON | Executado, piloto curto |
| `.../P2_32rps` | 2×16=32 | `/medium`; 64 | 12 s; ON | Executado |
| `.../P3_64rps` | 2×32=64 | `/medium`; 64 | 12 s; ON | Executado |
| `.../P4_96rps` | 2×48=96 | `/medium`; 64 | 12 s; ON | Executado |
| `.../P5_128rps` | 2×64=128 | `/medium`; 64 | 12 s; ON | Executado |
| `.../C1_ON_r1,r2` | 2×4=8 | `/medium`; 64 | 20 s; ON | 2 executados |
| `.../C2_ON_r1,r2; C2_OFF_r1,r2` | 2×32=64 | `/medium`; 64 | 20 s; diagnóstico ON/OFF | 4 executados |
| `.../C3_ON_r1; C3_OFF_r1` | 2×64=128 | `/medium`; 64 | 20 s; ON/OFF | 2 executados; r2 de ambos planejados, sem execução localizada |
| `.../C4_ON_r1,r2` | 4×16=64 | `/medium`; 64 | 20 s; ON | 2 executados |
| `.../C5_ON_r1` | 4×32=128 | `/medium`; 64 | 20 s; ON | 1 executado; r2 planejado, sem execução localizada |
| `endpoint-characterization-a2-20261106T200836Z/M_A,M_B` | 2×1=2 | `/medium`; 4 | 60 s | 2 executados; controle de endpoint |
| `.../E_A,E_B` | 2×1=2 | `/expensive`; 4 | 60 s | 2 executados; custo de endpoint, não tráfego normal final |
| `legitimate-characterization-a1-20261106T202205Z/L2,L6` | 2×8=16; 4×4=16 | `/medium`; 64 | 150 s | Executados; L2 preferido |
| `.../L3,L7` | 2×16=32; 4×8=32 | `/medium`; 64 | 150 s | Executados; não escolhidos |
| `b2-l-20261107T232559Z` | 2×8=16 | `/medium`; 64 | 150 s | Executado; referência combinada |

Os registros primários das células de capacidade estão em `raw/effective_config.json` e `raw/run_status.json`; o índice `reports/capacity_exploration_20261104/runs.csv` contém os 16 IDs e estados. Para A1/A2, consultar os mesmos arquivos por subpasta, além de `runs.json` e relatórios de campanha. O relatório de capacidade registra que C5 terminou normalmente, mas excedeu o limite de progressão predefinido de espera p95 do worker (433 ms ante 100 ms), interrompendo as três repetições restantes de 128 RPS (`reports/capacity_exploration_20261104/campaign_report.md:5-9,73-81`). As células faltantes não devem ser convertidas em execuções. Não foi localizado um plano primário A1 que estabeleça outras células além das quatro executadas.

### Grupos 2 e 3 — ofensivo isolado

| ID (`experiment_results/`) | Mecanismo; O fontes × RPS = total | Endpoint; concorrência O | Estado e evidência |
|---|---|---|---|
| `b11-integrated-asymmetry-20261107-r1` / A1-reference | assimetria; 2×1=2 | `/expensive`; 64 | Executado como piloto de integração, reutilizado em B1.2 |
| `b12-isolated-20261107T200251Z/A2,A3,A4` | assimetria; 2×2=4; 2×4=8; 2×8=16 | `/expensive`; 64 | Três executados; A3 levou à composição B2-A |
| `b12-isolated-20261107T200251Z/F1,F2,F3,F4,F5` | flooding; 2×16=32; 2×32=64; 2×64=128; 2×96=192; 2×128=256 | `/medium`; 64 | Cinco executados; F2 levou à composição B2-F |

Todos esses ensaios foram isolados, 0 fontes legítimas. O RPS ofensivo iniciado em [30,60), registrado no relatório B1.2, foi A1 2,067; A2 3,833; A3 7,933; A4 16,033; F1 30,700; F2 60,233; F3 66,833; F4 65,000; F5 63,100. F3–F5 acumularam tarefas no cliente e expirações pré-HTTP 1438, 2743 e 3725; a causa única da limitação não foi isolada (`reports/b12-isolated-20261107T200251Z/report.md:24-45,99-125`). A4 teve residual computacional longo, até 92,538 s. Apenas uma realização por intensidade.

### Grupo 4 — composições simultâneas

| ID (`experiment_results/`) | L fontes × RPS | O fontes × RPS | Endpoints L/O; concorrência L/O | Duração, ataque | Estado |
|---|---|---|---|---|---|
| `b2-a-20261107T234426Z` | 2×8=16 | 2×4=8 | `/medium`/`/expensive`; 64/64 | 150 s; [30,60) | Executado, candidato A3 |
| `b2-f-20261108T000313Z` | 2×8=16 | 2×32=64 | `/medium`/`/medium`; 64/64 | 150 s; [30,60) | Executado, candidato F2 |
| `b2-f96-20261108T002312Z` | 2×8=16 | 2×32=64 | `/medium`/`/medium`; 64/96 | 150 s; [30,60) | Executado, concorrência adicional |
| `pilots-energy-powersaver-20261109/A3` | 2×8=16 | 2×4=8 | `/medium`/`/expensive`; 64/64 | 150 s; [30,60) | Piloto ambiental posterior |
| `pilots-energy-powersaver-20261109/F96` | 2×8=16 | 2×32=64 | `/medium`/`/medium`; 64/96 | 150 s; [30,60) | Piloto ambiental posterior |

Há somente **uma intensidade** de cada mecanismo no B2 combinado; F96 altera orçamento, não RPS. Os pilotos de 09/11 repetem as duas configurações finais sob outro perfil de energia e outra semente; não são uma varredura. B2-A/B2-F/B2-F96 têm configuração primária em `raw/effective_config.json`, status em `raw/run_status.json`, proveniência e dataset/manifesto; relatórios em `reports/b2-*/report.md`. A classificação legítimo/ofensivo usa `source_inventory.json`, `traffic_class` e IDs correlacionados: em F96 ambos usam `/medium`, logo endpoint não separa as classes (`reports/b2-f96-20261108T002312Z/report.md`, seção Atendimento legítimo).

Na B2-A, P2 teve 514 inícios legítimos, 43 respostas e 471 timeouts, com RPS ofensivo iniciado de 7,933; o pico agregado de operações pendentes foi 361, incluindo o pós-ataque (`reports/b2-a-20261107T234426Z/report.md:22-37,90-105`). Na B2-F, P2 preservou 514/514 respostas legítimas, mas a duração média chegou a 1102,37 ms; o ataque iniciou 54,067 RPS e acumulou 191 expirações antes do HTTP (`reports/b2-f-20261108T000313Z/report.md`, seção Conclusão). Na B2-F96, P2 teve 98/514 respostas legítimas e 416 timeouts, com 49,867 RPS ofensivos iniciados e 308 expirações (`reports/b2-f96-20261108T002312Z/report.md`, seção Comparação direta). Esses números descrevem realizações individuais; não são efeitos médios populacionais.

## Inventário dos dados e instrumentação

| Medida / campo real | Origem | Unidade e granularidade | Disponibilidade e limites |
|---|---|---|---|
| CPU vítima: `cpu_percent`, `average_cpu_percent` | `raw/victim_stats.jsonl`; `raw/simulation_metrics.csv` | % Docker, amostras brutas ~3 s e ticks efetivos ~5–10 s nos B1/B2 | Direta onde há coleta; 100% ≈ um núcleo lógico. Série esparsa, embora polling configurado em 1 s. Não é CPU de processo/worker/host. |
| CPU host: `host_cpu_percent` | `raw/simulation_metrics.csv`; monitor de capacidade | % do host, por tick | Direta onde presente; campo distinto da CPU Docker. |
| CPU por operação: `work_cpu_seconds`, `work_process_cpu_ms` | `raw/diagnostics/victim/events.jsonl` e análises de capacidade | s ou ms, por operação | Direta nos ciclos completos; worker/processo, não CPU agregada do contêiner. |
| Memória vítima: `raw_mem_usage`, `mem_app_mb`, `mem_usage` | `raw/victim_stats.jsonl`; `raw/simulation_metrics.csv` | bytes/MiB, por amostra | Direta, memória de contêiner; host RAM apenas em preflight/política. Não há série de memória do processo Python independente confirmada. |
| Ocupação de workers e trabalho pendente | eventos `work_submitted`, `work_started`, `work_completed` (ou falha quando houver) em `raw/diagnostics/victim/events.jsonl` | contagens deriváveis por evento; até 2 workers | Derivável após reconciliar IDs/relógios. `pending=waiting+running`; não é profundidade privada exata da fila do executor. |
| Espera por worker; duração computacional | diferenças entre `at` de `work_submitted`/`work_started`, e `work_finished_at−work_started_at` de `work_completed` | segundos deriváveis por operação | Deriváveis somente em ciclo completo; espera inclui IPC e escalonamento. CPU/op tem campo próprio. |
| Handler HTTP ativo/aguardando | `handler_started`, `handler_finished` e submissão computacional na vítima | contagem ou intervalo derivável | Não há contador direto e contínuo da fila do servidor HTTP localizado. Intervalos entre handler e submissão são deriváveis, mas não equivalem ao tempo de fila HTTP pré-handler. |
| Planejamento, admissão e despacho ofensivos | `submitted`, `task_started`, `task_finished` em `raw/source_artifacts/attack_*/output/diagnostics/events.jsonl`; admissão/expiração em `journal.jsonl` | monotônico, por tentativa | Diretos em B1/B2; no B2-F96 ofensivo não há evento `planned` e `planned_at` em `submitted` é nulo. Diferença submetidas−iniciadas aproxima backlog, sem acesso à fila privada. |
| Início/conclusão HTTP, status, outcome, erro | `raw/request_log.csv`: `timestamp`, `elapsed_seconds`, `end_timestamp`, `end_elapsed_seconds`, `duration_ms`, `http_status`, `outcome`, `error_type`, `traffic_class` | s/ms, por tentativa | Diretos; separa coortes quando identidade válida. `rtt_log.csv` mantém RTT separado. Encerramento conhecido inclui timeout e não significa resposta recebida. |
| Taxa nominal/efetiva; concorrência | `raw/effective_config.json` (`rate`, `max_concurrent_sends`); inícios de `request_log.csv`; eventos de tarefa/HTTP | RPS configurado; RPS derivado por intervalo; posições configuradas e ocupação derivável | Disponível. RPS iniciado = inícios na janela/duração; nominal×duração não é contagem de planos registrada. |
| Pacotes TCP, comprimento e payload | `raw/traffic_capture.csv` (`packet_length`), `raw/source_artifacts/traffic_capture.pcap`, dataset de captura; extrator de features | pacote/byte; linha por pacote; agregação em janelas de 1 s | CSV/PCAP presentes nos runs certificados. Payload TCP e pacotes ingressantes são derivados da captura; sem deduplicação de retransmissões. Não se processou PCAP neste inventário. |
| Cinco features científicas | dataset exportado (`features`), código de extração | pacotes, bytes payload, inícios, duração média HTTP, CPU Docker; janelas [t,t+1) | Disponíveis nos runs exportados. Duração é nula sem conclusões; CPU não é imputada quando não há observação (`docs/relatorio_2026_11_04_1.md:107-130`). |

| Família de ensaios | HTTP e configuração | Diagnóstico de fonte/vítima | CPU/memória e captura | Ressalva de cobertura |
|---|---|---|---|---|
| Capacidade P/C | Diretos | ON: diretos; OFF: intencionalmente ausentes ou reduzidos | Coleta/captura no índice e runs | ON/OFF não têm a mesma observabilidade; consultar `runs.csv` por célula. |
| A2 e A1 | Diretos | Diretos | Diretos | A1 CPU efetiva mais esparsa com quatro fontes; A2 mede endpoint em 2 RPS. |
| B1.1/B1.2 isolados | Diretos | Diretos, journals ofensivos | Diretos | A1-reference foi coletado para validação de integração; B1.2 o reutilizou. |
| B2-L/A/F/F96 | Diretos | Diretos, por fonte; ofensivo com admissão | Diretos | Admissão legítima independente indisponível; B2-L sem fonte ofensiva. |
| Pilotos 09/11 | Diretos | Diretos | Diretos, mais selos ambientais | Condição de energia posterior; não comparar como réplica estrita de B2. |

Aqui, “direto” indica campo/evento preservado, não cobertura contínua nem medição de todos os estados internos. As tabelas detalhadas por período e os manifestos de cada família estão nos diretórios de relatório citados acima.

No diagnóstico B2-F96 conferido diretamente, a fonte legítima registra `planned` com `planned_at` e `wait_started_at`, depois `submitted`, `task_started`, `http_started`, `http_finished`, `task_finished`; a ofensiva registra os cinco últimos eventos, sem `planned` independente. O journal ofensivo preserva admissão e resolução. `http_started` marca o início lógico no cliente, mas não um timestamp separado do envio de bytes ao socket; `http_finished` marca encerramento local e seus campos `http_status`/`outcome` distinguem resposta de timeout. Não há eventos independentes de recebimento de resposta no socket e de conclusão da operação HTTP além de `http_finished`. Na vítima, `handler_started` e `handler_finished` delimitam o handler; `work_submitted`, `work_started` e `work_completed` delimitam a computação. Essa cadeia não mede diretamente o instante em que a requisição chega à fila pré-handler do servidor. Campos e eventos foram verificados em `experiment_results/b2-f96-20261108T002312Z/raw/source_artifacts/{normal_1,attack_1}/output/diagnostics/events.jsonl` e `raw/diagnostics/victim/events.jsonl`.

**Três esperas diferentes.** (A) No gerador ofensivo há produtor, admissão, tarefas submetidas ao executor e limite de concorrência; o atraso até `task_started` e a expiração pré-HTTP são observáveis, mas a profundidade real da fila interna não é. O gerador legítimo usa esperas exponenciais relativas e não possui medida independente de admissão equivalente à ofensiva. (B) No servidor, `handler_started` marca entrada observada; ausência de timestamp na porta antes do handler impede medir diretamente espera de requisição na fila HTTP. `request_log.csv` mede duração fim a fim no cliente, não a fila HTTP. (C) Na computação há submissão e início de worker distintos; a espera é derivável, com IPC/escalonamento incluídos. O limite é o pool de dois processos. Os eventos de rede, cliente, handler e worker pertencem a relógios diferentes; cruzamentos dependem dos certificados de clock (`raw/diagnostics/victim_clock_validation.json`, `raw/source_artifacts/clock_validation.json`).

## Mapa de comparabilidade

| Conjunto | Classe | Fundamento e restrição |
|---|---|---|
| C2 ON/OFF r1 e r2; C3 ON/OFF r1 | Comparável com ressalvas | Configurações pareadas no plano, mas ordem/semente e presença do diagnóstico interferem; C3 não tem r2 local. |
| C2 vs C4 e C3 vs C5 da capacidade | Comparável com ressalvas | Mesmo agregado/endpoint/workers, duas vs quatro fontes; C3/C5 têm repetições incompletas e a trajetória muda com fontes. |
| A1 L2 vs L6; L3 vs L7; L2 vs L3; L6 vs L7 | Comparável com ressalvas | Mesmo checkout/imagens/duração/endpoint/workers; uma realização por célula, sementes iguais não igualam trajetórias; CPU com cobertura desigual. |
| A2 M_A/M_B vs E_A/E_B | Comparável com ressalvas | Varia endpoint sob baixa taxa e mesmo plano; não simula coortes ofensivas nem L2. |
| B1.2 A2–A4 entre si; F1–F5 entre si | Comparável com ressalvas | Mesma composição isolada, duração, pool e concorrência; RPS varia, mas o RPS entregue em F3–F5 não acompanha nominal. A1-reference teve propósito anterior. |
| B2-L vs B2-A/B2-F/B2-F96 | Comparável com ressalvas | L2/configuração base e instrumentação comuns; presença/mecanismo ofensivo muda, imagens B2 certificadas. Execuções sequenciais e únicas. |
| B2-F vs B2-F96 | Comparável com ressalvas | Configuração efetiva difere só em ID e concorrência ofensiva 64→96 (`reports/b2-f96-20261108T002312Z/report.md:3-12`), mas custo/op pré-ataque e host variaram; efeito causal isolado não comprovado. |
| B2-A vs B2-F | Não diretamente comparável como variação só de intensidade | Mecanismo, endpoint, custo/op e RPS mudam juntos. Serve para descrever dois ataques, não uma curva dose resposta comum. |
| Capacidade curta vs A1 longa; B1.2 isolado vs B2 combinado; B2 vs pilotos 09/11 | Não diretamente comparável | Duração, composição, estágio de código/instrumentação ou perfil energético diferem. Comparações descritivas exigem explicitar todos esses fatores. |
| Rodadas de outubro vs esta caracterização | Não diretamente comparável | Protocolo, topologia e autoridade histórica distintos. |

Os diagnósticos de CPU de 08/11 (`experiment_results/c1-2-cpu3-20261108`, `docs/scientific_protocol_direct_c135_20261108.json`) são validação de observabilidade, não nova varredura L/A/F; não foram usados para completar células ausentes. O congelamento científico de 08/11 traz ainda modificações de coleta/captura e contrato, portanto séries B2 não são automaticamente réplicas de TEST.

## Seleção dos cenários definitivos

**L2.** A1 efetivamente comparou L2/L6 em 16 RPS e L3/L7 em 32 RPS. O relatório A1 chama L2 de *candidata preferencial*, com 15,933 RPS iniciados no período principal, 100% de sucesso, média HTTP 45,379 ms e menor carga que as opções de 32; L6 permaneceu alternativa plausível (`experiment_results/legitimate-characterization-a1-20261106T202205Z/report.md:1-35,175-196`). B2-L repetiu a configuração e validou seu uso como referência (`reports/b2-l-20261107T232559Z/report.md:1-25`). O contrato de 08/11 a adotou. Isso é seleção operacional documentada, não equivalência estatística demonstrada.

**A3.** B1.2 testou 2/4/8/16 RPS agregados isolados (A1–A4), encontrando em A3 7,933 RPS iniciado, 38 timeouts ofensivos, espera média por worker 1309 ms e acúmulo; A4 teve efeito mais severo e residual prolongado (`reports/b12-isolated-20261107T200251Z/report.md:24-92`). B2-A testou apenas A3 + L2. O contrato o adotou; o piloto `power-saver` confirmou estresse e fila, mas foi uma nova condição de ambiente. Não se atribui o motivo exato de escolha entre A2/A3/A4 além do que os relatórios registram.

**F96.** B1.2 testou 32/64/128/192/256 RPS isolados; F2=64 foi o patamar que ainda entregou cerca de 60,233 RPS isolados, enquanto F3–F5 ficaram em ~63–67 com numerosas expirações. B2-F combinou L2+F2 com concorrência 64: 54,067 RPS ofensivos iniciados e 191 expirações. B2-F96 manteve RPS e elevou só a concorrência a 96: 49,867 RPS, 308 expirações e maior degradação legítima. O próprio relatório B2-F96 **recomendou manter F2/64** por não melhorar a entrega (`reports/b2-f96-20261108T002312Z/report.md`, seções Comparação direta e Conclusão). Porém o contrato direto de 08/11 fixa F96 e aponta para a configuração B2-F96 (`docs/scientific_protocol_direct_20261108.json:318-330,465-488,551-553`); o piloto de 09/11 conserva 96 e observou 55,5 RPS e 214 expirações (`reports/energy-powersaver-20261109/report.md:180-213`). **Divergência aberta:** nenhum documento examinado explica por que a recomendação de 64 foi revertida. A evidência primária comprova o que se executou; o protocolo comprova o que se adotou; não comprova a motivação.

## Lacunas, incertezas e implicações para a metodologia

1. Determinar a deliberação que substituiu a recomendação F2/64 por F96/96. Não apresentar maior dano observado como justificativa documentada sem ata ou registro contemporâneo.
2. Confirmar se existiu uma matriz A1 mais ampla formalmente planejada. Os registros primários inspecionados só confirmam L2/L6/L3/L7; não se devem acrescentar IDs hipotéticos à matriz.
3. Registrar na metodologia o gate predefinido de 100 ms da exploração de capacidade e a interrupção após C5: 11 células principais mais 5 pilotos, ante 14 células principais previstas (`reports/capacity_exploration_20261104/campaign_report.md:5-9`).
4. Especificar versões de código e imagens por etapa, sobretudo transições 04/11→06/11→07/11→08/11; IDs de imagem estão em `source_artifacts/image_identity.json` e proveniência de cada run. Não tratar repetições entre etapas como pares controlados.
5. Declarar topologia direta, uma vítima, dois workers, `/medium`/`/expensive`, semente, timeout 2 s, taxas por fonte/agregadas, concorrência por classe e períodos semiabertos. Distinguir a caracterização 150 s da coleta científica 390 s, com ataque de 120 s.
6. Definir taxa efetiva por **início HTTP**, coortes por início, encerramentos posteriores, timeout vs resposta, expiração pré-HTTP e descarte de gerador. Descrever a geração por esperas exponenciais relativas, sem afirmar Poisson homogêneo exato.
7. Descrever separadamente atrasos do gerador, handler HTTP e espera por worker. Declarar que não há medida direta confirmada do tempo na fila de admissão do servidor e que pending reconstruído não é profundidade interna do executor.
8. Informar origem/unidade/cadência efetiva da CPU Docker e memória; distinguir CPU do host, do contêiner e por operação. Os ticks de 5–10 s não justificam apresentar CPU contínua a 1 Hz. A distinção é importante para o método e para limitações de comparabilidade.
9. Descrever identificação das classes por fonte/ID, inclusive quando legítimos e ofensivos usam o mesmo endpoint; mencionar operações `unknown` de auditoria separadas.
10. Relatar certificação, relógios, PCAP/CSV, hashes e limpeza como condições técnicas, sem convertê-las em evidência de equivalência causal ou inferência estatística. A rodada tem poucas repetições e condições de energia distintas.

Este inventário preserva os dados originais e não usa a campanha definitiva para inferir resultados exploratórios.
