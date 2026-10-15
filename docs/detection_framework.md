# Etapa 11 — framework mínimo de detecção

Implementado em `analysis/detection/`, separado do extrator legado e das Etapas 0–10. Não contém detector estatístico, threshold científico, escolha de lookback, normalização, imputação, seleção de features ou implementação de métricas. Usa somente biblioteca padrão. Interface Python, sem CLI nesta etapa.

## Fluxo e módulos

```text
Stage 10 / seleção explícita
  inputs.load_series → BoundSeries (somente orquestração)
    .series → ObservedSeries (somente uma feature)
      fit_baseline → baseline/manifest.json
      score_run → scores/manifest.json + scores.csv
        calibrate → calibration/manifest.json
        decide → decisions/manifest.json + decisions.csv
          evaluation.evaluate → evaluation/manifest.json
```

`contracts.py` define callbacks/tipos. `inputs.py` valida/carrega observações. `pipeline.py` separa fitting, scoring, calibração e decisão. `artifacts.py` persiste artefatos e proveniência. `evaluation/` é o único módulo Stage 11 que abre labels. `detectors/` está vazio, reservado para etapas futuras. Não existe registro de plugins, fábrica de 15 métodos ou hierarquia de algoritmos.

## Entrada e identidade

Exemplo somente de carregamento, sem detector:

```python
from analysis.detection import load_series

source = load_series(
    'experiment_results/stage10-final/stage7-regressions/stage5/A',
    run_id='bd1303b0312e4b3bbf9436d92ae02b77',
    family='service', feature='request_starts',
    window_size_seconds='1', feature_schema_version=1,
    role='development',
)
source.verify()
```

Todos os seletores são obrigatórios. Roles possíveis: baseline, calibration, test, development. Nenhuma inferência por nomes de diretório ou posição na série. `development` é apropriado aos históricos; os três papéis científicos são designações explícitas para uma campanha futura, não certificação científica automática.

O leitor aceita exclusivamente schema Stage 10 v1 canônico, confere detector_columns, papel feature, cabeçalho, janela/grade regular, run ID, contagem, valores finitos/tipo integral quando declarado, nullability e vínculo com relatório Stage 9 elegível. Campos causais, labels, chaves, timestamps e features desconhecidas são recusados como entrada. Não lê config bruta, extrator legado ou dados de outras etapas.

A identidade inclui caminho do feature dataset, run ID, família/feature, Δ, versão, hash do manifest Stage 10, hash do manifest Stage 8 e hashes dos arquivos consumidos. Verifica SHA256/tamanho de schema, relatório e tabela selecionada. Snapshot antes/depois das fases detecta alterações nesses arquivos e no manifest. **Não abre nem calcula hash de labels no carregamento/scoring**: a verificação desses bytes cabe ao evaluator. Não reexecuta a validação científica Stage 9; preserva sua decisão e binding. Hashes não são assinatura contra adulteração coordenada.

## Contratos de fases e callbacks

- `fit_baseline(sources, fitter, spec, destination)`: apenas BoundSeries com role baseline, mesma feature/Δ/schema e IDs distintos. Callback `fit(tuple[ObservedSeries], config) → dict` recebe somente séries observáveis. Devolve artefato baseline com parâmetros JSON.
- `score_run(source, detector, spec, destination, baseline=None)`: confere baseline por identidade/configuração da implementação declarada, feature e hashes. Callback `start_run(parameters|None, config) → state`, depois `update(Observation, state) → ScoreValue`. Estado novo a cada run; atualização recebe apenas a observação corrente, permitindo métodos pontuais, lookback causal e estado sequencial. O framework não escolhe tamanho histórico. Detector que requer baseline deverá recusar parameters=None em seu contrato específico.
- `calibrate(score_runs, calibrator, spec, destination)`: aceita exclusivamente scores designados calibration; não aceita test/development/baseline. Callback `calibrate(tuple[CalibrationScores], config) → dict`. Recebe score e chaves, sem valores da feature ou caminhos. Não há calibrador real incluído.
- `decide(score_run, policy, spec, calibration, destination)`: exige artefato calibration compatível com feature, detector, modelo e policy. Callback `start_run(parameters, config) → state`, `decide(PolicyScore, state) → DecisionValue`. A calibração já está congelada; este passo não estima parâmetros do test set.
- `evaluation.evaluate(scores, decisions, dataset, evaluator, spec, plan, destination)`: valida alinhamento/referências, carrega ground truth e chama exclusivamente `evaluator.evaluate(EvaluationInput, EvaluationPlan) → dict`. Nenhum evaluator real incluído.

`Component(name, version, config, missing)` identifica componentes. `missing` deve ser `reject` ou `preserve`; default conservador reject. Config e parâmetros enviados a callbacks são cópias JSON, não dicionários compartilhados dos manifests. Parâmetros precisam ser dados JSON; Decimal é persistido como string exata, que o método deverá interpretar ao carregar. Não há pickles ou desserialização executável.

`open_artifact(reference, kind)` reabre baseline/calibração conferindo hash/outputs. `load_scores(reference)` e `load_decisions(reference)` permitem retomar fases em outro processo. Os registros em memória são confrontados com os CSVs antes do consumo, impedindo divergência silenciosa por troca de registros.

## Separação e leakage

Tipos imutáveis de observação contêm somente run ID, chaves temporais e um valor. Fitter não recebe envelope BoundSeries, manifest, dataset path ou labels. Detector recebe observações individualmente; não tem acesso à série futura na interface de update. Calibração/decisão recebem PolicyScore, que nem sequer contém o valor original. Somente EvaluationInput contém WindowTruth.

O framework impede reutilizar o mesmo run ID do baseline como calibration/test e o mesmo run ID de calibration como test, inclusive por aliases. Replicações de Δ do mesmo run não viram amostras independentes. Calibração exige mesmos detector/modelo/feature para todos os seus scores. Um teste confirma via bloqueio de `Path.open` que todas as fases anteriores ao evaluator completam sem ler labels.csv; outro confirma que adulteração de labels só afeta avaliação.

Isso evita leakage acidental na API; **não é sandbox de código Python hostil**. Um componente arbitrário pode abrir arquivos por conta própria. Implementações devem ser revisadas e não receber caminhos/labels via config ou closures. Não há certificação automática da normalidade das séries designadas baseline: fazê-la consultando labels violaria a separação. Comparabilidade do cenário e independência de seeds são responsabilidade do protocolo/split futuro, pois não estão integralmente representadas na série observável Stage 10. Separação por ID é necessária, mas não suficiente para independência científica.

## Missing e warm-up

Família de rede sem direção suportada ou série inteiramente null → `ContractError` com feature_unavailable, sem publicar scores. Série parcialmente null com missing=reject → recusa antes do callback; com preserve → recebe `Observation.value=None` na posição temporal original. Nada vira zero e nenhuma janela é compactada.

Em preserve, o componente deve declarar/documentar o tratamento de seu estado em gaps. O framework não inventa reset, preenchimento, avanço de filtro ou histórico. Nesta versão um valor ausente exige score ausente; previsão de estado pode continuar internamente, mas não vira score observado. Uma extensão futura que produza score preditivo em ausência terá de declarar essa semântica separadamente.

`ScoreValue(None, 'warmup')` ou `ScoreValue(None, 'missing_observation')` são válidos. Score presente deve ser finito e não carregar razão de indisponibilidade. Score ausente exige razão. Decisão de score ausente é automaticamente indisponível com razão preservada, não normal/false. Policy pode também se abster explicitamente. Não se escolheu lookback, suporte mínimo estatístico ou critério próximo de zero.

## Formatos e auditabilidade

Cada fase escreve em diretório novo, sem sobrescrever/nestear inputs ou artefatos dependentes. Inputs não são copiados. CSVs são completos antes da publicação; falha de callback/validação não publica resultado. Destino é reservado por mkdir exclusivo; não há locking de inputs nem promessa de transação entre processos concorrentes. Inputs devem estar encerrados/quiescentes, como na Etapa 10.

Todos os manifests têm schema_version=1 e kind, metadados da fase, parâmetros quando aplicável, proveniência e lista de outputs com SHA256/tamanho. Não têm self-hash circular: consumidor guarda hash do manifest referenciado. Referências incluem caminho e SHA256 do manifest. Verificações percorrem referências de modelo/calibração e fontes consumidas; mudança posterior nessas dependências invalida o consumo, sem tocar nos inputs.

**Baseline manifest:** component (nome/versão/config/missing), feature (família/nome/Δ/schema), sources (runs, roles e referências/hash dos datasets), parameters, provenance. Não contém ground truth nem raw CSV. Não concatena runs numa sequência temporal única: fitter recebe tuple de séries separadas.

**Score CSV:** run_id, window_index, window_start_seconds, window_end_seconds, score, score_available, unavailable_reason, available_at_seconds. Ausente é célula vazia. Manifest identifica feature, detector/config, fonte/role, baseline opcional, parâmetros treinados, fontes do baseline, semântica de disponibilidade e hashes de saída.

**Calibration manifest:** component da policy/calibrator, detector/feature/modelo correspondentes, sources de calibração, referências aos score artifacts, parameters e provenance. Threshold futuro poderá estar em parameters, mas nenhum é criado pelo framework.

**Decision CSV:** chaves/score/disponibilidade do score, decision (true/false/vazio), decision_unavailable_reason, decision_available_at_seconds e policy_reference (hash do manifest calibration). Manifest separa referências de scores, baseline e calibration e persiste parâmetros de decisão e proveniência.

**Proveniência:** hashes efetivos de todos os módulos Stage 11, classe/arquivo SHA256 da implementação fornecida, Git HEAD quando disponível, Python e plataforma. A implementação precisa ter source file inspecionável; classes dinâmicas sem fonte são recusadas. Hash de arquivo efetivo inclui alterações não commitadas, sem afirmar que o HEAD representa sozinho o código executado. Dependências externas específicas de futuros detectores deverão ampliar sua proveniência quando introduzidas. Não se consulta Docker nem se captura timestamp variável. Mesmos componentes, ambiente, paths/referências e inputs produzem os mesmos bytes; uma mudança de referência/código é registrada.

## Disponibilidade temporal e avaliação pendente

Para cada score, o instante padrão é **fechamento da janela**, simulado offline. Não é medição de latência computacional. Um método pode declarar disponibilidade posterior, que será registrada; nunca anterior ao fim da evidência. Decisão também não pode preceder o score, e tempos de disponibilidade não podem regredir. Não existe persistência/hysteresis automática. Uma confirmação posterior pode atrasar DecisionValue, mas exige implementação/política futura explícita, sem inferência a partir de labels.

EvaluationPlan exige `overlap_policy`, configuração explícita e `availability_policy`, sem defaults científicos. O framework não escolhe any-overlap, maioria, exclusão de boundaries ou ponderação. `WindowResult` prepara TP/FP/TN/FN/Precision/Recall/F1/FPR, aceitando None para medidas indefinidas; nenhuma fórmula é executada nesta etapa. Evaluator recebe overlap_seconds/fraction originais, sem binarizar. Auxiliar attack_request_starts não é feature e não é necessário à interface principal.

`EventTruth`/`EventResult` preparam ID, actual_start/end, detectado, primeira disponibilidade, delay e censura dos misses. **Event-level não está operacional:** labels Stage 10 v1 contêm overlap da união, sem todos os IDs/limites/eventos sobrepostos. EvaluationInput.events=None explicita isso; nenhum evento é inferido por bins e nenhum delay é calculado. A ligação futura a ground truth efetivo verificável deverá existir exclusivamente no evaluator. Essa limitação foi mantida sem alterar Etapas 0–10 ou escolher política científica.

O plugin evaluator deve declarar métricas suportadas, denominadores/cobertura e interpretações do plano; o core não valida a correção científica de fórmulas fornecidas pelo usuário. O único evaluator incluído está nos testes e retorna contagens de linhas, não métricas.

## Testes e validação

```bash
.venv/bin/python -B -m unittest tests.test_detection_framework -v
.venv/bin/python -B -m unittest discover -s tests -q
```

Os únicos fitters/detectores/calibradores/policies/evaluators fake estão em `tests/test_detection_framework.py`. Demonstram estado, warm-up, parâmetro persistido e decisão sintética, sem implementar qualquer método planejado.

Cobertura: seleção obrigatória e campos proibidos; indisponibilidade; nullability; warm-up/reset por run; não leitura de labels; limites temporais; fases/roles/aliases; baseline/policy incompatíveis; corrupção e alteração pós-leitura; snapshot durante callback; reabertura de artefatos; divergência entre memória/CSV; determinismo; saída nova e separada; preservação de hashes/mtime dos inputs; plano obrigatório no evaluator. Verificação histórica descrita em [detection_framework_results.md](detection_framework_results.md).

## Decisões da campanha e próximos passos

Runs atuais são desenvolvimento/validação funcional. A campanha científica principal será nova e controlada, com baseline/calibration/test independentes. Quantidade de seeds depende de piloto; não foi definida. Novos ContinuousFlood/PeriodicBurst deverão diferir somente nos fatores deliberadamente estudados, evitando o confundimento atual de operação/capacidade.

Shannon permanece pendente: agregações atuais não preservam necessariamente a distribuição categórica necessária. Definir representação e hipótese separadamente, antes da implementação. Etapa 12 poderá adicionar Z-score e CoV aos contratos existentes; nenhum método foi implementado aqui. Permanecem pendentes políticas científicas de overlap, horizonte/cobertura, gaps por método, baseline degenerado, calibração, thresholds, lookbacks, eventos e incerteza.
