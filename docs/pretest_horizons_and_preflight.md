# Contratos pré-TEST: seleção de avaliação e preflight

Esta alteração não libera TEST. Os guards de leitura, scoring e avaliação de
dados TEST permanecem LOCKED. Nenhum detector, parâmetro, threshold, modelo,
protocolo v2, matriz ou série Stage 8/9/10 é alterado.

## Série completa e seleção posterior

O horizonte TEST original `[0,144)` permanece no protocolo v2 como horizonte de
observação/scoring. O detector processa a série completa, em ordem causal, e as
decisões são produzidas antes de selecionar as janelas de avaliação. Não há reset
em t=48: EWMA/CUSUM carregam seu estado e CoV preserva o histórico.

`EvaluationSelection('primary')` seleciona somente janelas integralmente contidas
em `[48,144)`. `EvaluationSelection('startup_diagnostic')` seleciona `[0,48)`.
Ambas preservam os objetos, timestamps, scores e unavailable originais.

`EvaluationPlan` recebe essa seleção explícita. A mesma abstração seleciona as
janelas para o callback window-level e as decisões elegíveis para avaliação de
eventos. Para TEST, ausência de seleção explícita é erro; não há fallback
silencioso para o horizonte inteiro. BASELINE/CALIBRATION mantêm seus horizontes
históricos. Fixtures DEVELOPMENT sem campanha permitem testar essa seleção sem
acessar TEST real.

Eventos continuam usando `actual_start/actual_end` persistidos. A seleção não
recorta nem redefine eventos para `[48,84)`, não usa `drained_end` como endpoint e
não modifica a política de overlap/availability. Uma janela positiva selecionada
que sobrepõe o evento pode produzir detecção válida depois de `actual_end`.
Periodic continua sendo um evento global, incluindo silêncio. Boundary windows
continuam separadas pelas frações exatas de overlap.

## Preflight separado de execução

`preflight_entry(binding, hash, partition='test', run=...)` valida somente
metadados: bundle/protocolo/matriz/seeds, configuração planejada, ambiente/HEAD,
cleanliness segundo o binding, identidade e colisão do destino. Não abre resultados
TEST, não cria diretório científico, não inicializa backend, captura ou tráfego.

O registro TEST identifica `capability='preflight_only'`,
`execution_authorized=false`, `test_execution='LOCKED'` e `pipeline=[]`.

O CLI permite `--preflight` (ou o dry-run padrão), mutuamente exclusivo de
`--execute`. Artefatos administrativos opcionais `--audit-output` de TEST devem
ficar fora do root científico aceito.

`execute_entry(..., partition='test', execute=True)` continua fatal antes de
locks, preparação de metadata, criação de outputs ou invocação do backend.
`prepare_entry` permanece a preparação científica legada e também rejeita TEST;
preflight explícito não é preparação para executar. Não há flag de release TEST.
O dry-run legado `execute_entry(..., execute=False)` delega apenas ao preflight.

Os testes usam exclusivamente fixtures temporárias e ambiente mockado. Nenhum
preflight real das 48 entradas TEST é realizado nesta etapa.

## Escopo restante

Esta alteração fornece contratos, não o manifesto final de evaluation protocol
nem métricas científicas novas. A materialização do protocolo e os 48 dry-runs
reais dependem de revisão humana posterior. Execução, leitura de observações,
scoring e avaliação TEST continuam sem capacidade de release.
