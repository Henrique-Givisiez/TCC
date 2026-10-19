# Stage 15A — revisão de proveniência, sem execução TEST

Recomendação: **OPTION A**, condicionada à revisão humana e posterior implementação
explícita de uma ponte de proveniência. Stage 15A permanece parada. Esta revisão
não altera o preflight, não certifica todo o tooling incompleto e não autoriza sua execução.

Relatório machine-readable:
`experiment_results/stage15a-preflight-20261019/provenance_review.json`.
SHA256: `31b9fe33452b7b92af226569149c2e40938015ed2653ac0f2615d6a5ab572923`.
O diretório contém diffs históricos, genealogia por configuração, catálogo estático
de imports/chamadas e evidência sintética reproduzível.

## Genealogia histórica

Os 10 thresholds primários Z-score/CoV registram o HEAD
`6c5d9b6d26bc667bfb29e770bc39228d78982909` (Stage 14: calibração empírica e decisões
estritas). Os 10 EWMA/CUSUM registram
`63cba02cf1e11722a66df6f2643e78d88bfdc477` (Stage 14: extensão dos métodos
normalizados e posterior calibração). Cada hash histórico foi conferido com os
bytes no respectivo commit, não inferido apenas do nome do arquivo.

`63cba02` introduziu a única diferença de pipeline: capacidade `baseline_spec`.
`b0b025b3edbc6d981d6cff9929fa3b256ebaf00a` introduziu as três diferenças de
avaliação/horizonte, durante o contrato pré-TEST de seleção e preflight.
Esse último commit é a `authority_head` do evaluation protocol congelado.
Portanto essas mudanças precedem a coleta TEST; não são tuning pós-TEST.
O HEAD atual continua `ec086c25aaa81ac4da85f5f3c83875dce9b830c1`.

| Arquivo (`analysis/detection/`) | SHA256 histórico | SHA256 atual |
|---|---|---|
| `evaluation/__init__.py` | `d8dd1ac7bbf145691326898f8e29d37e42cc3340d54f0d23c449ac411cf2d59f` | `31ddb70da03505f8e506b3a6581d3b4a8186c684eea0998bff0a8c8d2594da98` |
| `evaluation/events.py` | `44836f114f560c7735ffd90f82bded4b1f5e45dcf05562abc8d90b12a0d55084` | `e6c0c18d00c577a7ff42f9bc57e8f07b9015aa3c04d66a9ae530ae27978b8dec` |
| `horizons.py` | `f4e04910ee68bbdaf8b1997dde6257f0a3332ab65be2127a65c3bf3e3e0099d1` | `3626399fa7b45f0dcb9b729f25ac54c5d9945eca0c9837e5d8ced06e4703a4cc` |
| `pipeline.py` (Z/CoV) | `651bbaa11c4e8696d86b0bbf3ad498f441f927fefbc6eaafd9685e8531ab80e6` | `22cb26f9a5e9da26ea9a2373faba6accb3b935b860c2e983316a9ca7e1e5db48` |

Os thresholds EWMA/CUSUM já registram o hash atual de pipeline. Os três outros
arquivos divergem nos snapshots amplos das 20 configurações.

## Dataflow real

No framework: `inputs.load_series → pipeline.score_run → detector.start_run`
(uma vez por run) `→ detector.update` (em ordem causal) `→ PolicyScore →
pipeline.decide → StrictUpperTail.start_run/decide`.
O leitor genérico continua bloqueando TEST; não se deve mudar role para development
para contornar esse guard.

O draft preservado propõe um leitor TEST específico, condicionado ao freeze e
inventário: `read_observations → combination → score_decide → start_run/update →
PolicyScore → StrictUpperTail`. Ele não chama `pipeline.score_run/decide`.
`pipeline` é importado indiretamente por `analysis.detection.__init__`, o que é
separado de chamar suas funções. Uma sonda somente de import registrou 29 módulos
locais e nenhum módulo de evaluation. O catálogo de imports/chamadas por linha
está em `static_dataflow_evidence.json`; a sonda está em `import_only_evidence.json`.

| Método | Funções matemáticas | Parâmetros efetivos |
|---|---|---|
| Z-score | `ZScore.start_run/update`; `_moments.read_fraction/decimal_ratio/standard_deviation/finite_fraction` | mean_exact, sigma, variance_exact e convenções BASELINE verificadas; signed |
| CoV | `CoV.start_run/update`; `_moments.sample_moments/standard_deviation/decimal_ratio` | L=6, ddof=1, janela incluindo atual, null reseta, média zero unavailable |
| EWMA | `StandardizedUpperTail.start_run/residual`; `ZScore.start_run/update`; `EWMA.update` | BASELINE congelado, lambda=0.2, estado inicial/reset=0 |
| CUSUM | `StandardizedUpperTail.start_run/residual`; `ZScore.start_run/update`; `CUSUM.update` | BASELINE congelado, k=0.5, estado inicial/reset=0 |

Dependências numéricas: módulos dos detectores, `_standardized.py` quando aplicável,
`_moments.py`, `inputs.number`, tipos em `contracts.py`, Decimal/Fraction.
Decisões: `empirical.StrictUpperTail`, `checked_score`, config alpha=0.01 e threshold
persistido. `quantile_index` é usado na validação do suporte persistido, sem estimar
novo threshold. A comparação é estritamente `>`; empate negativo; null unavailable.

`inputs.py`, `feature_schema.py`, `artifacts.py` e a orquestração também importam:
seleção de feature/janelas, parsing exato, identidade do modelo, disponibilidade e
serialização podem afetar o resultado se forem modificados. Não basta verificar
somente os arquivos de fórmulas. O relatório JSON lista essas dependências por método.
Os callbacks recebem somente Observation ou PolicyScore; cenário fica na metadata.
Nenhuma tabela GT/labels é necessária para esse caminho.

## Análise semântica

`evaluation/__init__.py`: acrescenta `EvaluationSelection` ao plano e substitui a
seleção implícita por seleção explícita dos scores, decisions e labels já existentes.
Encaminha a seleção ao evaluator de eventos. Nenhuma chamada ao scorer/policy.

`evaluation/events.py`: recebe seleção explícita e filtra decisões elegíveis antes
da atribuição a eventos/GT. É downstream das decisões e não altera sua geração.

`horizons.py`: preserva a seleção whole-window histórica, fatorada em `_contained`,
e acrescenta regiões de avaliação. Não lê observações para o scorer nem atualiza
estado. O módulo também é dependência real da seleção de CALIBRATION, chamada por
`pipeline.calibrate` **depois** do scoring; essa semântica permaneceu igual.
Não deve ser classificado como um arquivo inteiramente irrelevante à calibração.
A divergência específica é de avaliação, não de score/decision.

A implementação atual aplica o contrato pré-TEST de avaliação primária `[48,144)`
sem substituir o horizonte observação/scoring `[0,144)`. É necessária para exigir
esse recorte no evaluator genérico futuro; não é necessária para calcular os scores
15A e não impõe reset em t=48. Tanto o pipeline histórico quanto o atual iteram toda
a série fornecida, sem chamar horizons em `score_run` ou `decide`.

`pipeline.py`: o diff completo contém apenas a nova verificação opcional de
`detector.baseline_spec`. Para Z/CoV, atributo ausente → `expected_model=component(spec)`,
igual à verificação histórica. Para CoV sem baseline, a avaliação adicional de
`component(spec)` é pura e já ocorria em `missing_check`. EWMA/CUSUM declaram o
modelo normalizador Z-score; essa capacidade já existe no HEAD de sua calibração.

Não mudaram fórmula, ddof, warmup, null, reset, tail, available_at, comparação do
threshold ou seleção temporal do scorer. AST do laço de update é idêntica; todas
as demais funções de pipeline, incluindo `decide` e `calibrate`, têm AST idêntica.

## Reprodução sem TEST

Foram executadas 160 comparações sintéticas: 20 configurações × 8 sequências ×
144 janelas, total de 23.040 janelas comparadas por par histórico/atual. Sequências:
variável positiva, zeros, null/reset/warmup, signed, offset grande com variação
pequena, nulls próximos à fronteira 48, estado contínuo e todos null.

Os parâmetros numéricos foram lidos dos manifests BASELINE/thresholds congelados,
sem fit/calibrate. Envelopes sintéticos temporários foram criados somente para
exercitar as APIs, sem serem apresentados como nova autoridade científica.
Nenhuma tabela observacional BASELINE/CALIBRATION/TEST foi lida. Um guard de IO
rejeitou paths de observações científicas e GT; um guard de chamadas rejeitou
fit/calibrate/evaluation. Os módulos do evaluator nem foram importados nesse teste.

Em todos os pares: registros score/decision iguais e CSVs byte a byte iguais.
Foram verificados também 20 empates negativos e 20 unavailable preservados.
As dependências compartilhadas com os módulos históricos têm bytes idênticos aos
respectivos commits; portanto não houve substituição matemática oculta ao carregar
os pipelines históricos em memória. Artefatos temporários foram removidos.
Manifestos completos de uma execução histórica real teriam HEAD/proveniência
históricos; a igualdade demonstrada aqui é dos payloads e contratos, sem reescrever
sua autoria. O digest canônico da evidência sintética é
`99a2ce3015ae04ad69a6fb336dd454f8ff6c345ac1e3fb63c57d9d8e15295d13`.

Checks separados confirmaram continuidade causal de CoV/EWMA/CUSUM em 48:
processar desde zero difere de reiniciar em 48 e coincide com o prefixo causal.
A seleção histórica/current de horizons produziu registros e metadata iguais
para os três intervalos do protocolo, usando apenas objetos sintéticos. A seleção
primária atual preservou identidade dos objetos e índices 48…143, sem evaluator.

## Proveniência do threshold

`pipeline.calibrate` publica o threshold com `provenance(calibrator)`.
`artifacts.provenance` faz `base.rglob('*.py')` sobre todo `analysis/detection`.
Isso registra um snapshot do framework, não um trace das dependências executadas.
`evaluation/events.py` aparece porque o arquivo existe nesse diretório; não porque
o calibrador consumiu eventos. A origem específica do componente é registrada à parte.
Esse registro histórico é verdadeiro e deve continuar imutável.

| Arquivo | Mudança | Usado no score? | Usado na decision? | Mudança só evaluation? | Altera resultado 15A? | Classificação |
|---|---|---|---|---|---|---|
| evaluation/__init__.py | seleção explícita posterior | Não | Não | Sim | Não | EVALUATION_ONLY |
| evaluation/events.py | seleção das decisões elegíveis | Não | Não | Sim | Não | EVALUATION_ONLY |
| horizons.py | regiões explícitas; calibração equivalente | Não | Não | Sim; módulo também serve calibração | Não | EVALUATION_ONLY |
| pipeline.py | API de identidade do normalizador | Sim no framework; draft não chama | Sim no framework; função inalterada | Não | Não | SCIENTIFIC_EQUIVALENT |

A inclusão dos arquivos não chamados no snapshot é PROVENANCE_ONLY como motivo
do bloqueio amplo; as mudanças reais de avaliação merecem EVALUATION_ONLY, em vez
de serem apagadas da história.

## Recomendação e limites

OPTION A: preservar historical provenance e acrescentar current execution provenance
com uma ponte separada, content-addressed, que referencie esta revisão, diffs e
verificação das dependências científicas. Registrar explicitamente exceções de
avaliação e equivalência de pipeline. Manter estritos os hashes de coleção/modelos/
thresholds, componentes, features, alpha e dependências efetivas. Nunca substituir
hashes históricos nem simplesmente ignorar toda divergência de framework.

Não foi identificado risco de alteração numérica causado por essas quatro
divergências. Testes finitos não provam equivalência universal isoladamente; o diff
completo, identidade de bytes e preservação do ramo Z/CoV sustentam a conclusão.
O leitor e a orquestração 15A novos ainda precisam de testes próprios e revisão;
esta auditoria não é uma aprovação geral desse draft. Não há razão identificada
para recalibrar ou regenerar TEST. Nenhuma resolução foi implementada.

## Respostas obrigatórias

1. Algum TEST scored? NÃO.
2. Alguma decision TEST produzida? NÃO.
3. Algum GT TEST consumido? NÃO.
4. Alguma métrica de eficácia calculada? NÃO.
5. Thresholds congelados mudaram? NÃO.
6. Implementações matemáticas dos quatro detectores mudaram? NÃO.
7. evaluation/__init__.py participa de score/decision? NÃO.
8. evaluation/events.py participa de score/decision? NÃO.
9. horizons participa? Somente seleção posterior; também seleção histórica de calibração, equivalente.
10. Pipeline mudou? API opcional baseline_spec para validar o normalizador EWMA/CUSUM.
11. Altera Z-score numericamente? NÃO.
12. Altera CoV numericamente? NÃO.
13. Histórico/atual equivalentes nos testes não-TEST? SIM.
14. Snapshot histórico mais amplo que dependências científicas? SIM.
15. Risco científico real nessas divergências? Nenhum identificado; draft futuro ainda precisa validação.
16. Recomendação? OPTION A, sem implementar agora.
17. Recalibrar? NÃO.
18. Regenerar TEST? NÃO.
19. Algum arquivo histórico alterado? NÃO.
20. Stage 15A continua parada? SIM.

STOP original e tooling untracked preservados. Nenhum commit ou push.
Stage 15B não iniciada. Parar para revisão humana.
