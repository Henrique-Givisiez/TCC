# Etapa 9 — validação científica do dataset

O validador `experiments.validate_dataset` é offline e somente leitura. Recebe
um dataset exportado, confere integridade, consistência e requisitos mínimos de
uso científico. Não executa Docker, HTTP, captura, detectores ou correções.
Os produtores, datasets, schema de dados e contratos das Etapas 0–8 permanecem
inalterados. O único produto persistido é um relatório **fora** do dataset.

```bash
.venv/bin/python -B -m experiments.validate_dataset \
  experiment_results/stage8-final/stage7-validation/periodic \
  --output experiment_results/my-validation/validation_report.json
```

O destino deve ser novo; escrita dentro do dataset e overwrite são rejeitados.
O terminal mostra VALID / ELIGIBLE, VALID / NOT ELIGIBLE ou INVALID e os checks
que falharam. Exit code: 0 elegível, 1 inválido/inelegível, 2 erro de saída/uso.
A API `validate_dataset(directory)` retorna o mesmo relatório sem escrever arquivos.
Datasets devem estar encerrados e não podem ser alterados concorrentemente durante
a leitura. O validador não depende dos caminhos originais externos do manifest.

## Regras de decisão

* `structural_valid`: nenhuma falha ERROR da camada structural.
* `dataset_valid`: nenhuma falha ERROR estrutural ou semântica.
* `analysis_eligible`: dataset válido e todos os gates explícitos de elegibilidade
  satisfeitos. Warnings isolados não bloqueiam elegibilidade.

Os gates são INFO com `affects=["analysis_eligible"]`: sua falha indica ausência
de um pré-requisito de campanha, sem acusar corrupção. Checks ERROR têm
`affects=["dataset_valid"]`; warnings e informações sem efeito decisório têm
`affects=[]`. A dependência dataset_valid → analysis_eligible é explícita no
check DATASET_VALID_FOR_ANALYSIS.

Gates mínimos: status completed; producers_drained=true; ausência de erros
operacionais no run_status; requests/packets/métricas com pelo menos uma observação;
CSV de eventos e RTT interpretáveis (podem legitimamente estar vazios); tráfego
benigno/atacante quando configurado com quantidade e rate positivos; evento
esperado com início, fim efetivo e drain conhecidos e status completed.

Um cenário com rate/count zero não exige emissão daquela classe. Attack.enabled
planeja um evento mesmo sem emissão: não é automaticamente uma incoerência.
Não se exige CPU/RTT elevados, throughput reduzido, detector positivo, taxa
uniforme ou contagem igual a rate × duração. Taxa continua nominal **por atacante
durante atividade**, com intervalos exponenciais e capacidade eventualmente menor.

## Relatório e determinismo

`validation_schema_version=1` e `validator_rules_version=1`. Inclui run ID,
dataset schema version, SHA256 do manifest, hashes da implementação e dependências
diretas de regras, os três resultados, summary e checks. Não contém horário variável
de geração, RNG ou medições de desempenho do validador.

Cada check tem check_id estável, stage, severity, passed, affects, message e
evidence. A mesma regra pode aparecer por tabela/arquivo, identificado na evidência.
Falhas agregadas incluem contagem total e até dez exemplos, com linha, ID, path
ou valores conforme a regra. Para inspeção completa, consulte o arquivo original
referenciado no dataset. Summary conta ERROR/WARNING **que falharam**, INFO
registrados e os IDs dos gates que bloquearam elegibilidade.

O SHA do manifest associa o relatório à versão exata do pacote validado; os hashes
do index associam os arquivos. Isso detecta alteração acidental, não constitui
assinatura/autenticidade criptográfica contra um agente que reescreva manifest e
dados coerentemente. O mesmo dataset e versão do validador produzem o mesmo JSON.

## Contratos temporais preservados

`actual_start` é primeiro início atacante; `actual_end` certifica admissão fechada
e todas as admitidas já iniciadas; `drained_end` é última conclusão. São verificados
`actual_start <= actual_end` e `actual_start <= drained_end`, independentemente.
**Não se exige actual_end <= drained_end.** Fim da admissão deve preceder sua
certificação; os inícios ficam abaixo do actual_end efetivo quando conhecido.

Primeiro/último início e última conclusão são comparados exatamente no domínio
monotônico compartilhado: esses valores são cópias/min/max dos mesmos floats
persistidos, não medidas independentes. A duração é o cálculo original
`(end_elapsed-start_elapsed)*1000`. Não há epsilon ou tolerância inventada.

ContinuousFlood conserva fila: começo depois do fim planejado/stop_requested é
permitido para tarefa já admitida, desde que anterior ao actual_end. Não se tenta
deduzir a hora de admissão a partir da request. PeriodicBurst exige início dentro
da janela global e do burst início-a-início. Conclusões no silêncio ou após janela
global são permitidas. Journals disponíveis verificam admissão e início no mesmo
sample/event, sem backlog; sua ausência gera warning e limita essa certificação.

`attack_active` segue o evento global, incluindo silêncio entre bursts. Labels
incertos permanecem null conforme o contrato; não são substituídos por zero.
Benignas durante ataque são aceitas. Packet labels são conferidos contra o próprio
elapsed registrado, sem afirmar igualdade com um instante de request.

## Integridade e identidade

Manifest/schema canônicos são interpretados com versão conhecida; o schema
persistido não pode desativar verificações alterando campos/tipos. Descrições
textuais podem diferir sem constituir incompatibilidade. JSON com chaves duplicadas
ou números não finitos é rejeitado. CSV exige header conhecido, células corretas,
tipos/domínios e nullability. O caso documentado de active_containers_names vazio
é aceito, sem preenchimento dos dados.

Paths absolutos, traversal e symlinks são rejeitados antes da leitura de arquivos
indexados. Todos os arquivos presentes no index têm hash/tamanho conferidos,
inclusive evidências. Falta de evidence opcional é warning; falta de arquivo
canônico indexado é ERROR. Incomplete pode omitir explicitamente CSVs essenciais
no index, como permite a Etapa 8: warning, dataset potencialmente válido, mas
inelegível. Arquivo presente e malformado continua sendo uma falha de integridade.

IDs são contextualizados pelo run. Source IDs, IPs, containers e o par
(source_type,worker_index) são únicos dentro do inventário. Request/source usa
(generator,worker_id); no host, worker é validado contra quantidade configurada.
Event/attack IDs e request IDs são únicos. Quantidades do inventário devem coincidir
com configuração em completed; divergência em incomplete pode refletir setup
parcial, sendo warning. Source sem run_id pode existir num setup incomplete sem
observações; não é usada como fonte identificada de tráfego iniciado.

Operação/path e destino lógico são conferidos. Paths legados continuam válidos
quando configurados; não se impõe apenas /light,/medium,/expensive aos runs antigos.
Outcome/status HTTP/erro são conferidos sem remover failures. RTT é o subconjunto
response de requests, no instante de conclusão e com a mesma duração HTTP;
**não TCP RTT**. Journals locais não são autoridades para labels globais reconciliados.

## Cobertura e limitações

São registrados primeiro/último elapsed, span e número de observações de
traffic/service/infrastructure. Isso **não comprova cobertura contínua**. Não há
95%, limite de gap ou margem de clock arbitrários. Falta de observações de fases
antes/durante/depois, quando justificadas pela configuração, gera warning.
Em ataque isolado, silêncio antes/depois não exige requests/packets; métricas
ainda podem registrar essas fases. Um tick não precisa ocorrer exatamente no fim.

Capture epoch pode retroceder por ajuste/reordenação: warning. A fórmula local
elapsed=packet_epoch-anchor_epoch é verificável exatamente, sem comparar clocks
independentes. Request epoch retrógrado também é warning; sua ordem monotônica
continua obrigatória. Source IP ausente é warning; pacote incompatível com o
segmento source_proxy declarado é contradição ERROR. Portas/IPs/comprimentos devem
ser plausíveis, sem tratar packet_length como frame Ethernet completo.

Métricas têm tipos finitos, valores não negativos e elapsed ordenado; nomes de
vítimas presentes devem pertencer ao backend inventory. Nomes esperados nunca
observados são warning, não exigência de ausência de cache/startup gaps.
Não se exige CPU > 0, CPU <= 100 ou qualquer degradação. Um PCAP clássico com
somente header de 24 bytes gera warning; não é confrontado pacote a pacote com
CSV, pois os processos de captura são distintos.

Proveniência explicitamente desconhecida em run antigo é warning. Proveniência
registrada exige binding/scope, SHA/dirty quando Git disponível e fingerprint
internamente consistente. Dirty/Git indisponível gera warning. Hashes não
reconstroem conteúdo histórico e SHA do host não atesta imagem Docker em cache.
Alinhamento contínuo de relógios, completude de captura e vínculo packet/request
não podem ser certificados pelos dados disponíveis. A calibração original fica
preservada como evidência; não se inventa um relógio novo.

## Testes e resultados

```bash
.venv/bin/python -B -m unittest tests.test_dataset_validation -v
.venv/bin/python -B -m unittest discover -s tests -q
```

Testes usam fixtures exportadas temporárias. Corrupções semânticas atualizam
hash/tamanho **apenas nas cópias de teste**, para comprovar detecção além do checksum.
Testes de checksum mantêm o index original. Datasets reais nunca são corrompidos.
Casos positivos aceitam pouco tráfego estocástico, benignas durante ataque, erros
HTTP/transporte, drain anterior ao end, fila contínua e conclusões no silêncio.

Resultados e tabela dos 19 runs em [scientific_validation_results.md](scientific_validation_results.md).
Etapa 10 deve consumir apenas analysis_eligible=true, conferir associação do
relatório ao manifest e manter warnings/proveniência junto às análises. Construção
de séries/features permanece fora desta etapa.

## Catálogo de checks

As severidades abaixo são declaradas para a regra; um ERROR com passed=true não
é um erro encontrado. Regras condicionais de presença/contagem usam WARNING em
incomplete, como indicado. INFO de elegibilidade tem efeito apenas naquele gate.

| Check ID | Camada | Severidade | Regra |
|---|---|---|---|
| `ATTACK_ID_UNIQUE` | semantic | ERROR | Attack IDs are unique for the current one-event contract |
| `ATTACK_START_WINDOW_VALID` | semantic | ERROR | Periodic starts require active burst/global window; continuous queued starts may extend through effective actual_end |
| `CANONICAL_ARTIFACT_PRESENT` | structural | ERROR / WARNING | Presença segura de JSON canônico; WARNING se opcional/ausente em incomplete. |
| `CANONICAL_REFERENCE_VALID` | structural | ERROR | Canonical references must be indexed paths of the supported layout |
| `CAPTURE_SEGMENT_CONSISTENT` | semantic | ERROR | Declared source_proxy capture contains source/proxy TCP observations |
| `CAPTURE_TEMPORAL_COVERAGE` | quality | WARNING | Observed span only; first/last observations do not prove uninterrupted coverage and no percentage threshold is used |
| `CONFIGURATION_VALID` | semantic | ERROR | Effective configuration satisfies the existing configuration contract |
| `COVERAGE_LIMITATIONS` | quality | INFO | No direct packet/request join, continuous clock drift proof, capture completeness guarantee, CPU/RTT degradation expectation or exact stochastic request count |
| `CSV_FIELD_VALID` | structural | ERROR | Scientific types, nullability and domains are respected |
| `CSV_PARSEABLE` | structural | ERROR | CSV header and record widths are recognized |
| `DATASET_PATH_SAFE` | structural | ERROR | Indexed paths must stay inside dataset and not traverse symlinks |
| `DATASET_VALID_FOR_ANALYSIS` | quality | INFO | Analysis eligibility requires a valid dataset independently of run status |
| `EVENT_CONFIGURATION_CONSISTENT` | semantic | ERROR | Profile, planned global interval, experiment and anchors agree |
| `EVENT_CONFIG_PRESENCE` | semantic | ERROR / WARNING | Enabled attack plans one global event even when rate or source count is zero |
| `EVENT_ID_UNIQUE` | semantic | ERROR | Event IDs are unique |
| `EVENT_REFERENCE_OBSERVABLE` | quality | WARNING | Ausência de eventos impede verificar referências/contexto. |
| `EVENT_REFERENCE_VALID` | semantic | ERROR | Attack requests identify an existing event and its attack_id |
| `EVENT_REQUEST_MILESTONES_MATCH` | semantic | ERROR | Recorded event first/last starts and last completion match the observed requests exactly in their shared monotonic domain |
| `EVENT_TEMPORAL_ORDER` | semantic | ERROR | Start precedes end and drain independently; no end <= drain requirement |
| `EXECUTION_CODE_RECORDED` | quality | WARNING | Git unavailable limits reproducibility, without inventing SHA |
| `EXECUTION_PROVENANCE_AVAILABLE` | quality | WARNING | Legacy execution provenance is explicitly unknown; export provenance must not replace it |
| `EXECUTION_PROVENANCE_CONSISTENT` | semantic | ERROR | Execution binding, Git fields and fingerprint are internally coherent; historical file contents are not reconstructed |
| `EXECUTION_WORKTREE_CLEAN` | quality | WARNING | Dirty or unavailable working tree cannot be reconstructed from hashes alone |
| `EXPECTED_EVENT_EXECUTED` | quality | INFO | Expected event has an observed beginning, effective end and drain |
| `EXPECTED_PHASE_OBSERVATIONS` | quality | WARNING | Missing phase observations limit interpretation, but may follow stochastic generation or incomplete execution |
| `EXPECTED_TRAFFIC_OBSERVED` | quality | INFO | Expected causal traffic exists; no rate × duration request count is required |
| `EXPECTED_VICTIM_METRICS_OBSERVED` | quality | WARNING | Missing named victims limit infrastructure attribution; startup cache gaps are not invalidity |
| `EXPERIMENT_ID_CONSISTENT` | semantic | ERROR | Configuration and status identify the same experiment |
| `EXPORT_PROVENANCE_SCOPE_VALID` | semantic | ERROR | Export provenance describes export time, not execution time |
| `FILE_HASH_MATCH` | structural | ERROR | Present indexed files must match their SHA256 |
| `FILE_INDEX_FIELDS_VALID` | structural | ERROR | Every indexed file needs a SHA256 and nonnegative byte size |
| `FILE_INDEX_UNIQUE` | structural | ERROR | Exported file paths must be unique |
| `FILE_SIZE_MATCH` | structural | ERROR | Present indexed files must match their byte sizes |
| `GLOBAL_ATTACK_CONTEXT_CONSISTENT` | semantic | ERROR | Labels follow the global event, including silence; packet labels are checked in their recorded elapsed domain, not matched to request clocks |
| `HTTP_DURATION_REFERENCE_VALID` | semantic | ERROR | RTT table is exactly the response subset at client completion; it is not TCP RTT |
| `INDEXED_FILE_PRESENT` | structural | ERROR | Indexed canonical/scientific files must exist |
| `JSON_PARSEABLE` | structural | ERROR | JSON artifact is parseable |
| `MANIFEST_FIELDS_VALID` | structural | ERROR | Manifest must identify a run, status and file index |
| `MANIFEST_SCHEMA_SUPPORTED` | structural | ERROR | Only dataset schema version 1 is supported |
| `METRICS_TEMPORAL_COVERAGE` | quality | WARNING | Observed span only; first/last observations do not prove uninterrupted coverage and no percentage threshold is used |
| `METRIC_CONTAINER_REFERENCE_VALID` | semantic | ERROR | Named monitored victims must exist in backend inventory |
| `METRIC_MONOTONIC_ORDER` | semantic | ERROR | Monitoring elapsed samples are nondecreasing |
| `METRIC_VALUES_PLAUSIBLE` | semantic | ERROR | Counts, resource observations and durations are nonnegative; no CPU ceiling or degradation requirement |
| `OPTIONAL_EVIDENCE_PRESENT` | structural | WARNING | Missing optional evidence limits auditability |
| `PACKET_EPOCH_ALIGNMENT` | semantic | ERROR | Capture elapsed uses its exact documented epoch subtraction, not request monotonic timestamps |
| `PACKET_EPOCH_ORDER` | quality | WARNING | Backward capture epoch observations may indicate reordering or clock adjustment |
| `PACKET_FIELDS_PLAUSIBLE` | semantic | ERROR | TCP payload lengths and ports are nonnegative/in range |
| `PACKET_IP_VALID` | semantic | ERROR | Packet CSV IPv4 addresses are parseable run attributes |
| `PERIODIC_ADMISSION_NO_BACKLOG` | semantic | ERROR | When journals are available, periodic admission and beginning share the same observed sample and remain inside allowed windows |
| `PROVENANCE_DECLARATION_VALID` | semantic | ERROR | Unknown execution provenance must not contradict an indexed execution record |
| `RANDOM_SEED_RECORDED` | quality | WARNING | Missing resolved seed limits reproduction without corrupting observations |
| `RAW_CAPTURE_NONEMPTY` | quality | WARNING | A classic PCAP with only its 24-byte global header has no observations; this does not assert equality with CSV capture |
| `REQUEST_CAUSAL_CLASS_VALID` | semantic | ERROR | Generator determines causal class, independently of attack_active |
| `REQUEST_FAILURES_OBSERVED` | quality | WARNING | Request failures are preserved observations, not automatic dataset corruption |
| `REQUEST_ID_UNIQUE` | semantic | ERROR | Request IDs are unique within run |
| `REQUEST_OPERATION_VALID` | semantic | ERROR | Observed operation and logical service destination agree with configuration |
| `REQUEST_OUTCOME_VALID` | semantic | ERROR | HTTP/transport outcomes and nullable fields agree |
| `REQUEST_TEMPORAL_ORDER` | semantic | ERROR | Elapsed order and duration arithmetic must agree; epoch drift is not assumed absent |
| `REQUEST_WALL_CLOCK_ORDER` | quality | WARNING | Backward epoch timestamps may indicate clock adjustment; monotonic duration remains authoritative |
| `RUN_COMPLETED` | quality | INFO | Technical incomplete runs are not eligible even when their dataset is intact |
| `RUN_DRAIN_CERTIFIED` | quality | INFO | Eligibility requires the existing producers_drained certification |
| `RUN_ID_CONSISTENT` | semantic | ERROR | Scientific observations belong to the manifest run |
| `RUN_STATUS_CONSISTENT` | semantic | ERROR | Manifest and canonical run status must agree |
| `RUN_STATUS_FIELDS_VALID` | semantic | ERROR | Run errors, drain certification and available clock anchors have documented types |
| `RUN_WITHOUT_OPERATIONAL_FAILURE` | quality | INFO | Operational failures block eligibility; observed request failures alone do not |
| `SCIENTIFIC_ARTIFACT_PRESENT` | structural | ERROR / WARNING | Scientific CSV must be indexed and present, or explicitly absent in an incomplete run |
| `SCIENTIFIC_OBSERVATIONS_USABLE` | quality | INFO | Requests, capture and metrics need observations; event/RTT tables may legitimately be empty |
| `SERVICE_TEMPORAL_COVERAGE` | quality | WARNING | Observed span only; first/last observations do not prove uninterrupted coverage and no percentage threshold is used |
| `SOURCE_COUNT_CONFIG_CONSISTENT` | semantic | ERROR / WARNING | Configured source counts match inventory |
| `SOURCE_FIELDS_VALID` | semantic | ERROR | Source identity, class, worker index and run IP are explicit |
| `SOURCE_IDENTITY_UNIQUE` | semantic | ERROR | Scientific IDs and source topology associations are unique within run |
| `SOURCE_INVENTORY_REFERENCE_VALID` | structural | ERROR / WARNING | Container source inventory must be a canonical indexed reference |
| `SOURCE_IP_OBSERVED` | quality | WARNING | Missing inventoried IPs are a coverage warning, not absence of source identity |
| `SOURCE_JOURNAL_AVAILABLE` | quality | WARNING | Missing journals limit admission/backlog evidence; primary observations remain authoritative |
| `SOURCE_JOURNAL_IDENTITY_VALID` | semantic | ERROR | Parseable source journals preserve identity and sequence |
| `SOURCE_JOURNAL_PARSEABLE` | quality | WARNING | Malformed optional journals limit auditability |
| `SOURCE_JOURNAL_REQUEST_PRESENT` | semantic | ERROR / WARNING | Journal requests are present in the primary table; incomplete aggregation may lack observations |
| `SOURCE_JOURNAL_REQUEST_REFERENCE` | semantic | ERROR | Observed journal requests agree with root requests except locally reconciled temporal labels |
| `SOURCE_REFERENCE_SCOPE` | semantic | INFO | Host generators have no container-source inventory; worker indices are checked against configuration |
| `SOURCE_REFERENCE_VALID` | semantic | ERROR | Requests reference configured and, when available, inventoried workers |
| `SOURCE_RUN_ID_CONSISTENT` | semantic | ERROR | Sources belong to this run; incomplete setup without observations may remain unbound |
| `TABLE_SCHEMA_SUPPORTED` | structural | ERROR | Scientific field definitions must match version 1; prose may differ |
