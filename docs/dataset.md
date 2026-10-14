# Etapa 8 — dataset experimental observado

Esta etapa acrescenta uma camada offline sobre os resultados existentes. Não muda
produtores, geração, taxa, fila, HTTP, captura, vítima, proxy ou ground truth.
O exportador copia todos os arquivos regulares do diretório de um run, sem alterar
bytes, campos, rótulos, unidades, timestamps ou caminhos nos documentos originais.
Não calcula séries temporais, features ou validade científica.

## Diagnóstico e inventário

| Artefato | Produtor e momento | Unidade/papel | Relógio | Correlação/uso |
|---|---|---|---|---|
| attack_events.csv | GroundTruth; snapshots de ciclo de vida e reconciliação final global | Evento global; ground truth científico | Âncoras epoch/monotônico e segundos desde início | run_id, attack_id, event_id |
| request_log.csv | RequestLogger begin/finish; agregação dos sources ao encerrar | Tentativa HTTP, inclusive falhas/incompletas; serviço científico | Epoch e elapsed monotônico no início e conclusão; duração ms | run_id, request_id, event_id, generator/worker_id |
| rtt_log.csv | RequestLogger.save_rtt; agregado ao final | Subconjunto outcome=response; duração HTTP do cliente | Timestamp/elapsed da **conclusão**; rtt em ms | run_id, request_id; redundância intencional com duration_ms |
| traffic_capture.csv | TcpdumpSniffer; parser em tempo real e reconciliação final | Linha IPv4 TCP reconhecida; tráfego observado | Epoch do tcpdump; elapsed = epoch menos âncora epoch | run_id, IP/porta; sem request_id |
| traffic_capture.pcap | Segundo processo tcpdump, quando disponível | Pacote capturado; tráfego bruto | Timestamp de captura | Segmento/interface/BPF; sem chave direta ao CSV |
| simulation_metrics.csv | Tick do orchestrator; StatsCollector/host_stats | Observação existente de infraestrutura, já média/cache | Epoch e elapsed no tick, não instante original do Docker | run_id, conjunto de nomes das vítimas |
| run_status.json | Orchestrator no setup/encerramento | Estado final e motivos; metadata canônica | Âncoras quando início ocorreu | run_id, experiment_id, evidências da topologia |
| effective_config.json | Setup do proxy ou runner | Configuração efetiva/seed; metadata canônica | Sem relógio próprio | id; parâmetros de tráfego, operações, padrão e infraestrutura |
| source_inventory.json | SourceManager, setup e finalização | Source e atributos daquele run; identidade científica | Sem timeline própria | run_id, source_id, worker_index, IP/container |
| source_plan/manifests/image_identity | SourceManager no setup | Quotas, configurações, imagem/receita; metadata/evidência | Sem relógio ou timestamps de diagnóstico | source_id/worker_index; digests e image_id |
| journal.jsonl | SourceJournal durante atividade | Mensagem sequencial: admissão, começo/fim, snapshot, diagnóstico | Dependente do kind; payload preservado | source_id, run_id, sequence, request_id/event_id |
| local_events/requests/rtt/summary | Cada source; atualizações/encerramento | Cópias locais/evidência, não autoridade global | Relógios locais homologados pelo clock audit | IDs; rótulos locais podem diferir dos reconciliados |
| control/ready/final_status/clock_validation | Controle de sources; setup/final | Operação e auditoria de relógios | Epoch, monotônico e nanosegundos, conforme campo | Source/run, amostras host antes/depois e container |
| proxy identity/backend_inventory/config/capture_metadata | HttpProxy/orchestrator no setup/final | Topologia, imagens, BPF e configuração; metadata | Campos de diagnóstico, quando presentes | run_id, IDs/nome/hostname/IP dos backends |
| NGINX access log | NGINX ao concluir request | Evidência operacional de roteamento, incluindo probes | $msec epoch na escrita; durações em segundos | request_id quando presente, upstream IP:port |
| routing_evidence.jsonl | Cliente ao observar resposta | Corpo/status para auditar backend; evidência de serviço | Não acrescenta timestamp próprio | run_id/request_id, hostname do corpo |
| summary logs | Loggers dos geradores; plano e encerramento de workers | Mistura de plano e resultado, diagnóstico | Lifetime do worker; não tempo desde início | Sem worker_id global/record_type explícito |
| validation/summaries/audits/stderr/outros | Runners, capturas auxiliares e checks | Operacional/debug; preservado integralmente | Variável ou ausente | Associação pelo diretório, campos disponíveis |

Os nomes/headers originais completos, tipos, unidades, significado, produtor,
nullability e domínios das sete tabelas CSV estão em `schema.json`, incluído em
**cada dataset**, produzido por `experiments/dataset_schema.py`. Os contratos JSON/
JSONL e os relógios também estão documentados nesse arquivo. O schema descreve os
formatos existentes; não introduz outro schema nas tabelas antigas.

## Correlações, relógios e lacunas

Todas as identidades são contextualizadas pelo run. `source_id` não é substituído
por IP, e pode reaparecer em outro run. A associação request/source no modo
containers é `(generator, worker_id)` ↔ `(source_type, worker_index)` do inventário;
o journal registra source_id diretamente. Request/event usa event_id, e
active_event_ids indica contexto temporal, não causalidade. Requests benignas
durante ataque continuam benignas.

Request → proxy → vítima é direto quando request_id aparece no access log e na
routing evidence; upstream/hostname associam ao backend inventory. Probes podem
não ter esse ID. Packet → source é contextual pelo IP **daquele run**, sem
reclassificar traffic_class=unknown. Packet → request não tem chave direta:
tupla/tempo permite apenas inferência. Métricas identificam o conjunto monitorado,
não constituem histórico individual de cada amostra Docker.

O ground truth continua tendo um evento global, incluindo silêncio entre bursts.
actual_start é a primeira tentativa iniciada; actual_end certifica admissão fechada
e nenhuma admitida ainda aguardando início; drained_end é a última conclusão.
drained_end pode ser menor que actual_end. Ausência de valor permanece ausência;
attack_active vazio não vira zero. Nenhuma coluna burst_active é criada.

Para alinhamento, use as âncoras de run_status/eventos e a clock_validation original.
Epoch e monotônico não são amostrados atomicamente. Captura usa relógio epoch;
requisições/eventos usam elapsed monotônico. Ajustes no relógio de parede podem
prejudicar alinhamento; a calibração inicial não monitora drift continuamente.
NGINX registra conclusão/log, não o começo observado pelo cliente. Local summaries
medem lifetime e misturam linhas de plano e resultados, sem identificador global
de worker. Não são automaticamente tabelas de taxa instantânea.

`rtt_log.rtt` é duração HTTP observada, **não TCP RTT**. `avg_rtt_ms` já existente
usa outro intervalo de instrumentação e pode diferir de duration_ms.
`mem_usage` é MiB; `packet_length` é comprimento da descrição TCP (`tcp N`/`length N`),
**não tamanho integral do frame na rede**. elapsed_time_s em metrics é redundância
arredondada preservada. O CSV principal e o PCAP principal vêm de processos tcpdump
distintos, portanto não se promete equivalência pacote a pacote. As receitas
copiadas no setup não provam que imagens em cache foram construídas daquela árvore.

## Exportação e estrutura

```bash
.venv/bin/python -B -m experiments.export_dataset RUN_DIRECTORY DATASET_DIRECTORY
```

Execute sobre um run encerrado, sem produtores escrevendo. O destino deve ser
novo, separado da origem; não há overwrite. Symlinks são rejeitados. O exportador
aceita nomes canônicos e os aliases fixos da Etapa 3 (`*_run`), rejeitando presença
ambígua dos dois. Não tenta adivinhar configurações/IDs de grids históricos.

```text
dataset/
  dataset_manifest.json
  schema.json
  metadata/
    effective_config.json
    run_status.json
    source_inventory.json                 # quando disponível
    run_provenance.json                   # quando registrado antes da execução
    export_provenance.json
    topology/{proxy,sources}/
  raw/
    traffic/{traffic_capture.csv,traffic_capture.pcap}
    service/{request_log.csv,rtt_log.csv,routing_evidence.jsonl}
    infrastructure/simulation_metrics.csv
    attacks/attack_events.csv
  evidence/
    proxy/                               # access logs, readiness etc.
    sources/                             # journals, locais, audits, receitas
    other/                               # summaries e todos os demais arquivos
```

Arquivos opcionais não são inventados. Não há diretório processed nem features
nesta etapa. Futuras saídas processadas devem permanecer separadas dos originais.

O manifest usa schema_version=1, run_id, status e referências à configuração,
status, inventário, schema e proveniências. Cada arquivo tem path relativo,
origin_path original, grupo/papel, tamanho e SHA256; tabelas conhecidas têm schema_ref.
origin_path também resolve referências absolutas antigas sem reescrever JSONs:
procure o caminho original na lista e abra seu path relativo exportado.
O manifest não contém hash de si próprio nem duplica configuração/eventos.

São exigidos configuração/status para identificar qualquer run. Em completed,
os cinco CSVs científicos são obrigatórios; inventário também no modo containers.
Ausência produz erro claro, sem publicar dataset parcial. Em incomplete, esses
arquivos podem faltar, com missing_artifacts/structural_status=partial explícitos.
Headers desconhecidos em incomplete são preservados com warnings. Headers
desconhecidos em completed ou IDs de runs diferentes são rejeitados. Isso é
checagem básica de empacotamento, **não validação científica da Etapa 9**.
Incomplete com todos os arquivos pode ser estruturalmente complete; o status real
continua incomplete. Erros, extremos, falhas, silêncio e tráfego benigno são mantidos.

## Proveniência prospectiva

```bash
.venv/bin/python -B -m experiments.dataset_run \
  --config experiments/configs/periodic_burst.json \
  --output experiment_results/my-run \
  --dataset-output experiment_results/my-dataset
```

Este entrypoint opcional redireciona os caminhos de resultados e invoca o mesmo
orchestrator sem mudar a simulação. Resolve/preserva seed e salva configuração;
registra antes da invocação commit SHA, dirty, lista de caminhos/status Git, hashes
do código/receitas/dependências, Python/OS/kernel e versões Docker cliente/servidor.
Não grava diff ou conteúdo da árvore, e não força commit. No final, associa a
proveniência ao run_id do status, sem substituir o snapshot inicial. Falha anterior
à criação do status não é convertida em um run fictício.

Runs antigos ficam execution_provenance.status=not_recorded: o SHA atual não prova
o SHA da execução passada. export_provenance tem scope=export e descreve somente
exportação. Ausência de Git/Docker é explícita. Hashes identificam código dirty,
mas não permitem reconstruí-lo; preserve externamente código/imagens para reprodução
integral. Digests das imagens e a identidade do host são evidências distintas.

## Auditabilidade a partir somente do dataset

| Pergunta | Onde responder |
|---|---|
| Configuração/seed/duração/quantidades/operação/padrão/taxa/burst? | metadata/effective_config.json; taxa nominal **por atacante durante atividade**, intervalos exponenciais |
| Commit/dirty/ambiente? | execution_provenance → metadata/run_provenance.json; desconhecido se não registrado |
| IPs/container/source/class daquele run? | metadata/source_inventory.json |
| Workers, quotas, endpoint lógico, seed do source? | metadata/topology/sources/source_plan.json e evidence/sources/*/manifest.json |
| Imagem/configuração do proxy e vítimas? | metadata/topology/proxy e configuração canônica |
| Início efetivo/fim da admissão/drain? | raw/attacks/attack_events.csv; actual_start/actual_end/drained_end_seconds |
| Packets/requests/métricas? | raw/traffic, raw/service, raw/infrastructure; PCAP quando presente |
| Completed/incomplete e motivos? | metadata/run_status.json; manifest aponta status, nunca filtra runs |
| Caminhos antigos e todos os diagnósticos? | manifest.files e evidence/ |

## Testes e regressão

```bash
.venv/bin/python -B -m unittest tests.test_dataset_export -v
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B -m experiments.validate_dataset_export \
  --runs experiment_results/stage7-validation \
  --runs experiment_results/stage7-regressions \
  --output experiment_results/stage8-final
```

A regressão exercita exportação sobre runs reais arquivados das Etapas 3–7 e
confere hashes do dataset e originais; export_validation.json contém respostas
de auditoria extraídas do dataset. Não reexecuta os antigos ensaios físicos nem
implementa um validador formal de qualidade. A suíte existente continua cobrindo
os produtores. O ensaio prospectivo real verifica o novo entrypoint e proveniência.

Pendências da Etapa 9: critérios formais de validade/integridade temporal,
checagem de completude/consistência científica, tratamento explícito de limitações
de captura/clock/metadata. Nenhuma política de exclusão ou correção é aplicada aqui.

Os resultados observados estão em [dataset_validation.md](dataset_validation.md).
