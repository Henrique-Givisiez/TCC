# Stage 14D.1 — TEST collection freeze

A coleção TEST está FROZEN, pronta para Stage 15, que não foi iniciada.
A unidade experimental continua run/seed; janelas não são réplicas independentes.

## Collection authority

- Collection HEAD: `f27a5ae6117667f980f6de0217222d25da0e6e42`.
- Environment SHA256: `a6859c8b2db988560dfdb2717cbfa3a582b38a06fa5b23ab439dcf42e7ce5ed7`.
- Binding SHA256: `45eeed559cf863873ff6d0e70bf01571a4591789c1cf863279a8e530fe2fa46b`.
- Release: `experiment_results/stage14d-release-20261019/test_campaign_release_v1.json`.
- Release SHA256: `ae4aa451b7088696071fc12ff17557e72c2df0eaa0427d5c8600173d0cc4400e`.
- Campaign identity: `56c72f0445a08bb909d5abde24078fab448d2b47691decbf99df1d7cdd582ad3`.

## Campaign completion and data integrity

48/48 COMPLETED_VALID; exatamente 16 B, 16 C, 16 P e 16 seeds pareadas.
PENDING/RUNNING/FAILED/INCOMPLETE/INVALID = 0. Stop solicitado = false.
48 entry_start, 48 autorizações, 48 validações técnicas; exatamente 48 transições
PENDING→RUNNING e 48 RUNNING→COMPLETED_VALID. Attempts = 1 para cada entrada.
Retries automáticos, tentativas extras, substituições e evidências de overwrite = 0.
Cada inventário de arquivos coincide integralmente com o recibo histórico.

Lock livre, nenhum container ativo e nenhum runner/simulador/tcpdump científico
ativo na consulta do host. Nenhum processo foi encerrado pelo auditor.

Stage 8/9/10 íntegros em 48/48; dataset_valid e analysis_eligible = true em 48/48.
Schemas, origem raw→Stage8, recibos, hashes exaustivos, configuração/matrix,
proveniência de código e identidade de execução conferem. Stage10 mantém Δ=1s,
horizonte contratual (incluindo cauda observada), todas as janelas e separação
features/labels. Schema de null/zero e ausência de imputação preservado.
Configurações são exatamente as da matrix: nominal 144s, PRE=48s,
ATTACK=36s para C/P, POST=60s, B benign-only, C continuous, P periodic_burst.
Workload, fontes, rates, infraestrutura e autoscaling conferem com a matrix.
GT foi lido exclusivamente para schema/identidade/event count/tempos contratuais:
B sem eventos, C/P com um evento global, incluindo silêncio periódico.
Nenhum cruzamento entre GT e decisões foi executado.

Warnings existentes preservados: entrada 29/C tem dois warnings efetivos Stage9,
REQUEST_FAILURES_OBSERVED e EXPECTED_PHASE_OBSERVATIONS (packets), sem blockers.
Os 48 Stage10 registram INFRASTRUCTURE_RECORDS_WITHOUT_SUPPORT; a entrada 29
preserva também os dois STAGE9_WARNING. Inventário contém os diagnósticos completos.
Nenhum warning foi convertido em exclusão.

## Inventory and freeze

- Inventory: `experiment_results/stage14d-test-campaign-20261019/test_collection_inventory.json`.
- Entries: 48, na ordem congelada da matrix.
- Inventory SHA256: `10ab05b24e9896d41e944192909f79b366e8cbbe7e08eb24f695b5d2ad1c2b47`.
- Freeze: `experiment_results/stage14d-test-campaign-20261019/test_collection_freeze_manifest.json`.
- Freeze SHA256: `8d784758ff7b751f68dc595d434a65bae1d764d5a21312b0e3d96a5f6613327d`.
- Status: FROZEN.

Freeze referencia inventory, matrix, seed plan, protocol v2, evaluation protocol,
four-method freeze, release, binding, environment e HEAD históricos, além dos
hashes do checkpoint, operations e console. Todos conferiram com a release.
A genealogia administrativa posterior referencia esses bytes sem reescrever a
autoridade científica. Seu registro fica separado em `administrative_finalization.json`
no diretório da campanha para evitar circularidade com o commit.
Não se emite nova autorização de execução nem se executam preflights científicos.

## Scientific isolation

Z-score TEST evaluated = NO; CoV TEST evaluated = NO;
EWMA TEST evaluated = NO; CUSUM TEST evaluated = NO.
Precision calculated = NO; Recall calculated = NO; F1 calculated = NO;
FPR TEST calculated = NO; detection delay calculated = NO.
Post-TEST tuning = NO; threshold changes = NO; detector changes = NO;
feature selection changes = NO; matrix changes = NO; seed changes = NO;
evaluation protocol changes = NO; automatic retries = NO.
Scientific detector evaluation performed = NO.

Essas conclusões são limitadas aos registros disponíveis: hashes históricos
intactos, Git clean durante as execuções, recibos exaustivos sem artefatos de
avaliação e log com exatamente uma execução por entrada. Não constituem prova
sobre atividades externas sem registro. Nenhum dado científico foi modificado.

## Administrative validation and Git

`python -B -m unittest tests.test_stage14_test_collection`: 3 testes passaram.
Incluem rejeição de duplicatas/ausências/seeds extras/tentativas extras e auditoria
real dos 48 runs, comparando os dois artefatos materializados byte a byte.
Auditor só importa contratos e validação técnica; não invoca execução, extração,
scoring, decision policy ou evaluator.

Um único commit local: `stage14: freeze completed test collection`.
O commit administrativo não é o HEAD que produziu os dados. Hash do commit e
HEAD administrativo final são registrados na genealogia pós-commit separada.
Push = NO. Stage 15 = não iniciada. Parar para revisão humana.
