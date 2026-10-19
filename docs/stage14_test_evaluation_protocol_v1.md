# Stage 14 — protocolo de avaliação pré-TEST v1

O contrato machine-readable está em
[`stage14_test_evaluation_protocol_v1.json`](../experiments/protocols/stage14_test_evaluation_protocol_v1.json),
status **FROZEN**. Esta etapa não libera execução TEST.

## Pergunta e desenho experimental

Comparar separadamente controle de falsos positivos, detecção Continuous,
detecção Periodic, métricas window-level/event-level, delay, persistência
pós-evento e estabilidade entre seeds. Não existe ranking ponderado, score
composto ou escolha de melhor detector por uma única métrica.

São 16 seeds TEST, cada uma com a tripla pareada B/C/P: controle benigno,
Continuous e Periodic. A unidade experimental é **run/seed**, não janela.
O pareamento permanece disponível para comparações futuras; nenhum teste de
hipótese é implementado nesta etapa.

## Configurações e horizontes

São 20 configurações primárias: cinco features independentes para cada método
Z-score, CoV L=6, EWMA lambda=0.2 e CUSUM k=0.5; alpha=0.01 em todas.
Modelos e thresholds vêm exclusivamente do four-method calibration freeze.
Alpha=0.005/0.02 e CoV L=3/12 continuam sensitivity, sem substituir a análise
primária após observar TEST.

Observação/scoring permanece `[0,144)`. O estado causal e as decisões são
construídos desde t=0, sem reset em t=48. Somente depois são selecionadas janelas
inteiramente contidas em `[48,144)` para avaliação primária. `[0,48)` serve apenas
para diagnóstico de startup, warmup, estados iniciais e alarmes. O protocolo v2,
duração e tempos nominais PRE/ATTACK/POST permanecem inalterados.

## Métricas window-level

No cenário B, registrar por run/configuração candidatos, decisões válidas,
unavailable, FP, TN, alarmes positivos e FPR=FP/(FP+TN). Um alarme positivo é uma
janela positiva, sem agrupar episódios silenciosamente.

Em C/P, usar o overlap efetivo contínuo: exatamente 0 é benigno, exatamente 1 é
ataque e fração estritamente entre ambos é boundary. Boundary fica fora da matriz
binária primária, sem arredondamento. Decisões unavailable permanecem excluídas
dos denominadores e contadas separadamente, incluindo seu grupo de ground truth.

Registrar TP/FP/TN/FN, Precision=TP/(TP+FP), Recall=TP/(TP+FN),
F1=2TP/(2TP+FP+FN) e FPR=FP/(FP+TN). Denominador zero produz null/undefined.
Overlap contínuo é preservado para complemento, sem nova métrica complexa.

Resumos entre seeds usam média, mediana, desvio padrão amostral (ddof=1), mínimo
e máximo dos valores definidos por run, com suporte definido/undefined explícito.
Desvio padrão com menos de dois valores definidos é null. Pooled metrics são
apenas complementares, identificadas como pooled; janelas não são réplicas
inferenciais independentes.

## Eventos e pós-evento

Evento detectado exige decisão positiva selecionada cuja janela observacional
tenha interseção positiva com `[actual_start,actual_end)`. Detection time é a menor
disponibilidade entre decisões positivas elegíveis; delay é esse tempo menos
actual_start. Não há exigência de disponibilidade antes de actual_end, nem uso de
drained_end como endpoint atacante. Evento não detectado tem delay null.

Reportar eventos totais/detectados, event detection rate e delays, preservando
seed. Resumos de delay usam somente eventos detectados; misses continuam no
denominador da taxa de detecção. O evento não é recortado para `[48,84)`.
Periodic continua sendo um evento global incluindo os silêncios; bursts não se
tornam eventos primários independentes. attack_request_starts é diagnóstico.

O complemento pós-evento seleciona janelas inteiramente contidas em
`[max(actual_end,48),144)`, registra suporte válido/unavailable, positivos e
alarm rate=positivos/válidos. Não mistura persistência com detection delay nem
altera threshold ou reset policy.

## Autoridade e isolamento

O manifesto fixa a autoridade de aprovação `b0b025b...` e seus environment/binding.
O commit que versiona o próprio manifesto é ligado externamente por finalization:
novo HEAD, novo environment/binding e SHA do manifesto em sidecar administrativo.
Assim não existe referência circular HEAD↔manifesto nem reescrita do contrato.

Não há fitting, calibration, seleção de threshold/feature/método ou ajuste de
lambda/k/L com TEST. TEST não influencia parâmetros. Preflights apenas verificam
metadados; execução, observações, labels, scoring, decisions e métricas TEST
continuam bloqueados. O manifesto não implementa runner de campanha ou release.

## Limitações

As janelas são temporalmente dependentes; unavailable reduz suporte e nunca vira
zero. FPR de calibração não garante FPR por seed TEST. Availability no fechamento
da janela é causal/simulado, sem medir latência computacional. Tempos efetivos e
boundary windows precisam permanecer explícitos. Este contrato define as métricas;
não acrescenta callbacks científicos de métricas nem testes de hipótese.
