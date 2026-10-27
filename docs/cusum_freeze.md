# CUSUM com congelamento — implementação sintética/DEVELOPMENT v1

Identidade: **`cusum-freeze`, versão `1`**, distinta de `cusum`, versão `1`.
Implementa a política da [proposta de27/10](new_campaign_protocol_proposal_20261027.md),
sem alterar `cusum.py`, `_standardized.py`, contratos antigos, pipeline genérico,
calibrador, avaliador histórico ou artefatos congelados.

## Regra e contrato

Código: [detectors/cusum_freeze.py](../analysis/detection/detectors/cusum_freeze.py).
Normalização usa exclusivamente momentos benignos fixos validados por
`ZScore.start_run`; não há fitting. Mantém `k=0.5` exato da referência anterior,
direção superior, estado inicial zero, Decimal50/ROUND_HALF_EVEN em contexto
privado. `h` é explícito, finito, não negativo e fixo. Aceita texto decimal,
Decimal ou inteiro; rejeita bool/float para evitar limiar implicitamente diferente.
A identidade persiste h em representação decimal canônica.

Para cada valor válido: `z=(x−mu_B)/sigma_B`;
`candidato=max(0,S_anterior+z−0.5)`. Score publicado é o candidato.
Decisão é `candidato>h`; igualdade é aceita sem alarme. Se aceita, armazenar o
candidato; se rejeitada, preservar S anterior. A próxima observação usa esse S.
O estado armazenado fica em `[0,h]`, mas o score pode superar h.

`CUSUMFreeze(h=...).start_run(parameters)` cria estado imutável;
`step(observation,state)` retorna `FreezeTransition`, com:

- observação escalar, estado anterior, residual e candidato;
- `update_accepted`, estado posterior e próximo estado;
- `PolicyScore` com candidato e `DecisionRecord` sobre **esse mesmo score**.

`step` só recebe o `Observation` real do contrato: run, índice, limites de janela
e valor. Não aceita labels, classes de tráfego, paths ou horários de ataque.
Horários de janela são necessários para contiguidade/disponibilidade; não são
horários de eventos. Novo processamento inicia em índice0 e tempo0; depois exige
mesmo run, próximo índice e fronteira contígua. Descarte não interrompe o avanço
dos metadados. Estados/resultado são imutáveis; o caller deve usar `next_state`.

Missing: candidato/score/decisão indisponíveis,
`update_accepted=null` (não representa rejeição de candidato), motivo
`missing_observation_reset`, reset numérico a zero e metadados avançados.
Disponibilidade simulada no fechamento da janela, sem medir latência de cálculo.
Não há cooldown, reset por alarme, confirmação, lower-tail ou adaptação do baseline.

## Integração e vínculo de h

[cusum_freeze_run.py](../analysis/detection/cusum_freeze_run.py) oferece:

```python
from analysis.detection.cusum_freeze_run import process_series, transition_rows

# observed_series: ObservedSeries sintética; parâmetros manuais benignos fixos.
# h=2 é apenas exemplo de teste, não limiar cientificamente calibrado.
run = process_series(observed_series, h='2', baseline_parameters=parameters)
diagnostics = transition_rows(run)
scores = run.scores
decisions = run.decisions
```

`FreezeRun` tem snapshots JSON canônicos de configuração e normalização, série
observável e transições imutáveis. `validate_run` reprocessa a série com os mesmos
momentos e h e confere todas as transições/decisões; substituir apenas decisão ou
h sem trajetória correspondente é recusado. **Alterar h exige reprocessar.**
Não há parâmetro de limiar na avaliação nem uma etapa independente de decisão.
`FreezeRun` não é `ScoreRun`; o `decide` genérico não o aceita. Converter manualmente
seus números em outro tipo não é uma API suportada e perderia a identidade acoplada.

`process_development_run(source, baseline=..., h=..., destination=...)` aceita
somente `BoundSeries` DEVELOPMENT sem vínculo à campanha científica. Verifica
hashes, feature/representação/janela, identidade Z-score do baseline e separação
dos runs de normalização/alvo. As cinco features permitidas são as mesmas de
EWMA/CUSUM anteriores. CALIBRATION, TEST e referências de campanha são recusadas
antes de leitura de modelo/dados; não existe nova autorização científica.

Publica em diretório novo um artefato de kind `cusum-freeze-run` com componente,
h, fontes, baseline e hashes, proveniência e transições completas. Não usa o
kind `scores` ou `decisions` para simular compatibilidade inexistente.
`load_development_run` verifica artefato/fontes/baseline e reprocessa observações
originais para conferir a trajetória persistida; não aceita h alternativo.
Não há calibração/threshold artifact fabricado nem uso automático de freezes.

[evaluation/cusum_freeze.py](../analysis/detection/evaluation/cusum_freeze.py)
contém `evaluate_synthetic(run, labels, evaluator, plan)`: confere trajetória e
alinhamento dos labels, e passa ao callback existente `EvaluationInput`, contendo
as decisões já produzidas. O callback recebe candidato/decisão, sem S armazenado
ou h para refazer a comparação. Labels só entram nessa camada. A semântica de
métricas fica no evaluator/plano explícitos; não se introduz uma nova regra
histórica de eventos ou prazo de detecção. A publicação científica de avaliação
e a integração com release da nova campanha continuam pendentes.

## Sequência numérica reproduzida nos testes

Baseline sintético manual: mu=10, sigma amostral=2; `k=.5`, **h=2 sintético**.
Não há ajuste/calibração nesses valores.

| Índice | x | z | S anterior | Candidato | Score | Alarme | Atualização aceita | S posterior |
|---|---:|---:|---:|---:|---:|---|---|---:|
|0|12|1|0|0.5|0.5|não|sim|0.5|
|1|14|2|0.5|2|2|não|sim|2|
|2|14|2|2|3.5|3.5|sim|não|2|
|3|14|2|2|3.5|3.5|sim|não|2|
|4|10|0|2|1.5|1.5|não|sim|1.5|
|5|8|−1|1.5|0|0|não|sim|0|
|6|null|null|0|null|null|null|null|0|
|7|12|1|0|0.5|0.5|não|sim|0.5|

Igualdade em2 é aceita; alarmes consecutivos em3.5 preservam2. A observação
seguinte retoma em1.5 e depois decai a zero. Missing não gera decisão negativa.
Há também teste separado de missing com S anterior1.5 para demonstrar o reset.
Em h=0, todo candidato positivo alarma e preserva0; candidato zero é aceito.

Integração obrigatória: com x=18, z=4 e h=1 sintético, candidato/score=3.5,
S anterior/posterior=0 e decisão=true. Somente depois do processamento, a camada
de avaliação recebe um `WindowTruth` sintético de overlap1 alinhado à janela.
O evaluator conta **TP=1** usando `DecisionRecord.decision`, sem recalcular
`S>h` (que daria falso). Não é reavaliação do TEST congelado.

## Validação, preservação e limitações

[tests/test_cusum_freeze.py](../tests/test_cusum_freeze.py): 12 testes de sequência,
igualdade, alarmes consecutivos, retomada, decaimento, missing/reset, h=0,
limiares inválidos, contiguidade e avanço após rejeição/missing, causalidade por
prefixo, contexto Decimal, ausência de refit/GT, imutabilidade e adulteração,
roundtrip do artefato, guards DEVELOPMENT, normalização incompatível e TP na
avaliação. Testes de regressão exercitam a implementação anterior sem mudança.

```bash
python3 -B -m unittest tests.test_cusum_freeze tests.test_ewma_cusum \
  tests.test_statistical_scores tests.test_empirical_policy -q
```

Resultado desta entrega: **95 testes, OK**. Somente fixtures sintéticas, arquivos
temporários e contratos foram usados; sem Docker, nova calibração ou scoring/
avaliação do TEST científico. O CUSUM anterior mantém a sequência
`.5,2,3.5,5,4.5` para x=`12,14,14,14,10`, conservando sua acumulação V1.

Arquivos históricos de implementação/contrato e artefatos congelados não foram
editados. A proveniência atual inclui os novos arquivos: isso não transforma
este checkout no ambiente histórico congelado. Reprodução oficial antiga deve
continuar usando sua autoridade/checkout e verificações de hashes; nenhum guard
foi relaxado ou manifesto reescrito para aceitar a árvore nova.

Congelamento não garante baixa persistência: um S preservado perto de h ainda
pode gerar muitos alarmes. A variante pode responder de forma diferente no benigno
e depois do evento; não há alegação de superioridade, FPR nominal ou eficácia.
O processamento/validação offline materializa a série e reprocessa para conferir
integridade; não é benchmark nem serviço de streaming em produção.

A [calibração benigna e integração científica](cusum_freeze_calibration_pending.md)
permanecem pendências separadas. Nenhum limiar deste documento é recomendado
para a campanha.
