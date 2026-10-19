# Stage 15A — Frozen TEST scores and decisions

Stage 15A FROZEN — ready for Stage 15B. Stage 15B não foi iniciada.
Somente scores/decisions primários e contagens administrativas foram produzidos.
Não houve avaliação de eficácia nem cruzamento com ground truth.

## Autoridade e ponte

- Collection authority HEAD: `f27a5ae6117667f980f6de0217222d25da0e6e42`.
- Processing HEAD/base: `ec086c25aaa81ac4da85f5f3c83875dce9b830c1`, acrescido dos arquivos de execução novos cujos hashes exatos estão no manifesto.
- O commit administrativo posterior incorpora esses mesmos bytes e outputs; sua genealogia é registrada separadamente em `administrative_finalization.json`, sem circularidade ou reatribuição da coleta.
- TEST inventory SHA256: `10ab05b24e9896d41e944192909f79b366e8cbbe7e08eb24f695b5d2ad1c2b47`.
- TEST collection freeze SHA256: `8d784758ff7b751f68dc595d434a65bae1d764d5a21312b0e3d96a5f6613327d`.
- Four-method calibration freeze SHA256: `898e79394ac48a86a734100d324d0b6b966412166a0eac105dbdeccb2bd236f5`.
- Evaluation protocol SHA256: `c2e1ab6314ab67c984b6b0e8f505982d72ea4de2f463e8607488e73c2764ef20`.
- Provenance review SHA256: `31b9fe33452b7b92af226569149c2e40938015ed2653ac0f2615d6a5ab572923`.
- Provenance bridge: `experiment_results/stage15a-preflight-20261019/provenance_bridge.json`.
- Bridge SHA256: `9c361e6b873dc39eb7d1d51de4c2b3476260aa25f4959ea126e0e07dd115c7a7`.

A ponte registra a aprovação humana OPTION A, STOP original, revisão e evidência
sintética, os quatro pares de hashes históricos/atuais e suas classificações.
Historical provenance != current repository provenance; scientific score/decision
behavior foi verificado equivalente para essas divergências específicas.
Manifests históricos permanecem intactos.

O preflight aceita somente esses pares exatos. Todas as demais identidades e o
conjunto completo de arquivos do framework permanecem verificados; arquivo novo,
ausente ou modificado fora da revisão causa STOP. O manifesto e cada combinação
referenciam a revisão e a ponte. O guard genérico de TEST não foi modificado.

## Processamento

48 runs × 4 métodos × 5 features = 960 combinações, sem ausências/duplicatas.
Z-score signed; CoV L=6/ddof=1; EWMA lambda=0.2; CUSUM k=0.5.
Alpha=0.01; comparação estrita `score > threshold`; empate negativo.
Parâmetros BASELINE e thresholds CALIBRATION exclusivamente dos freezes existentes.
Nenhum método/feature/seed/matrix/parâmetro/threshold foi modificado.

Cada série processa as janelas 0…143, horizonte [0,144), começando em t=0 e
preservando estado através de t=48. Cauda Stage10 permanece intacta na origem.
Null/unavailable e zero são distintos; não há imputação, cooldown, hysteresis,
reset por alarme ou adaptação. [48,144) não é usado para recortar a entrada.

Os callbacks recebem somente Observation e PolicyScore. Scenario é metadata
administrativa externa; GT/labels/eventos não entram nos callbacks. Os arquivos
GT/labels foram somente incluídos na verificação de hashes da coleção, sem parsing
ou uso científico. O leitor escalar abre exclusivamente a tabela observável.
Um guard de execução rejeita chamadas a fit/calibrate/evaluator na aplicação.

A entrada 29/C foi processada normalmente e mantém seus diagnósticos Stage9:
REQUEST_FAILURES_OBSERVED e EXPECTED_PHASE_OBSERVATIONS. Nenhuma elegibilidade mudou.
Todos os warnings/diagnósticos existentes são preservados em lineage.

## Outputs e reprodução

Diretório: `experiment_results/stage15a-test-scoring-20261019/`.
São 960 arquivos `runs/<entry>/<method>/<feature>.json`, mais o manifesto:
`stage15a_scoring_manifest.json` — 961 artefatos de scoring/freeze.
A genealogia administrativa posterior é um sidecar adicional, fora desse conjunto.

Manifest SHA256: `089a25681dd13810a94a92def805aa9a7e314955ebdcca671d625d959ae3a9d5`.
O manifesto contém SHA256/tamanho de cada output e hash do conjunto ordenado,
configurações, thresholds, source hashes e autoridade. Não inclui seu próprio hash.
Cada série registra run/seed/scenario metadata, feature/config, threshold/alpha,
observação, janela, disponibilidade, score, decisão e motivo unavailable.

Contagens administrativas agregadas, sem interpretação científica:

| Campo | Contagem |
|---|---:|
| observations | 138240 |
| valid scores | 136354 |
| unavailable scores | 1886 |
| positive decisions | 16487 |
| negative decisions | 119867 |

Cada combinação foi repetida em memória antes de publicação. Uma passagem separada
`python -B -m experiments.stage15a_test_scoring --verify` recompõe todos os outputs
e o manifesto e exige igualdade byte a byte, sem sobrescrever arquivos.

## Testes

104 testes específicos/regressões passaram antes do primeiro score TEST:
`test_stage15a_test_scoring`, `test_statistical_scores`, `test_ewma_cusum`,
`test_empirical_policy`, `test_pretest_evaluation_protocol`.
Após a publicação, 14 testes Stage15A passaram, incluindo a auditoria independente
dos 960 arquivos. São 105 testes distintos, com os 13 específicos iniciais
repetidos para incluir o novo teste dos outputs publicados.

Cobertura: ponte hash-bound, pares novos rejeitados, autoridades inválidas,
48×20, identidade de threshold/configuração, alpha/L/lambda/k, strict >, sinal,
null/reset/warmup, causalidade em 48, determinismo, contratos sem labels,
leitor escalar, guard de evaluator e integridade/lineage de todos os outputs.
A suíte completa inclui execução de evaluator e não foi rodada neste escopo.
Logs e preflight anterior ao primeiro score estão no diretório administrativo.

## Isolamento científico

TEST fitting = NO; TEST calibration = NO; TEST-derived threshold = NO.
Post-TEST tuning = NO; detector/threshold/feature/alpha/matrix/seed changes = NO.
GT consumed by scorer = NO; GT consumed by decision policy = NO.
Scientific evaluator executed = NO.
TP/FP/TN/FN, Precision, Recall, F1, FPR TEST, TPR, specificity, accuracy,
detection delay, event detection rate e post-event alarm rate = NOT CALCULATED.
Rankings, comparações de eficácia e significância estatística = não produzidos.

Um único commit local: `stage15: freeze primary test scores and decisions`.
Commit/HEAD final e Git clean são registrados no sidecar pós-commit.
Push = NO. Parar para revisão humana; não iniciar Stage 15B.
