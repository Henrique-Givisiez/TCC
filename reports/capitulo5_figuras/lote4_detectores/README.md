# Capítulo 5 — lote 4: detectores e contrastes de recall

Este lote **organiza resultados científicos oficiais** da campanha
`energy-powersaver-20261109`. Os detectores, limiares e intervalos de confiança
não foram recalculados. A avaliação usa exclusivamente 60 execuções TEST:
20 blocos completos, com L2, A3 e F96 em cada bloco.

| Entrega | Arquivo |
|---|---|
| T5.3-A, tabela principal | `tables/t53a_desempenho_detectores.tex` e `.csv` |
| Métricas complementares oficiais | `tables/metricas_complementares.csv` |
| F5.3-B, contrastes de recall | `figures/f53b_contrastes_recall.pdf` e `.png` |
| Observações por execução e bloco | `processed/metricas_por_execucao.csv` |
| Contrastes e IC oficiais | `processed/contrastes_pareados.csv` |
| Proveniência | `processed/manifest.json` |

O LaTeX requer `\usepackage{booktabs}`. A tabela principal contém as 16
combinações na ordem fixa: Z-Score, CoV, EWMA, CUSUM-freeze; dentro de cada
detector, inícios HTTP, pacotes TCP, bytes de payload TCP e duração média HTTP.
CPU não integra a matriz de detecção. A tabela principal contém FPR legítima,
detecção por evento e recall por janela. Latência condicional, alarmes em POST,
IC e métodos de IC estão no CSV complementar, evitando uma tabela larga.

## Origem e integridade

- Fonte principal: `experiment_results/scientific-energy-powersaver-20261109/analysis/summary/manifest.json`,
  campos `results`, `scenario_contrasts`, `eligibility`, `ci`, `evaluations` e
  `authority`. O manifesto vincula seu plano, protocolo e os 240 manifests de
  avaliação por hash. O script confere esses hashes, a campanha e os 60 IDs
  TEST do plano `experiments/protocols/energy-powersaver-20261109/plan.json`.
- Os resultados `results/<característica>/<cenário>/<detector>` contêm
  `per_run`, `detection`, `means`, `delay`, `denominators` e cobertura. Cada
  registro `per_run` possui `entry`, `block` e `metrics`. Os 960 registros
  detector × característica × execução foram organizados em
  `processed/metricas_por_execucao.csv`.
- Os contrastes oficiais estão em
  `scenario_contrasts/<característica>/<detector>/A3-F96:recall`.
  `processed/contrastes_pareados.csv` apenas transcreve estimativa, IC,
  método e número de pares, com conversão de fração para pontos percentuais.
  A média das 20 diferenças por bloco foi conferida contra a estimativa
  oficial; **os IC não foram recalculados**.
- `analysis/<característica>/calibration/manifest.json:thresholds` registra
  os limiares selecionados com fontes exclusivamente CAL_A; `verification`
  registra a aprovação dos 16 pares com fontes CAL_B. TEST não entra nessas
  fontes. O resumo oficial marca as 16 combinações como elegíveis, sem
  atribuir a isso significado de bom desempenho.

## Definições operacionais preservadas

As definições vêm de `analysis/detection/scientific/direct_metrics.py:metrics`,
`direct_summary.py:summarize` e `statistics.py`.

- **Detecção por evento:** variável booleana por execução ofensiva, positiva
  quando há decisão positiva válida, com disponibilidade dentro do evento
  ofensivo real. A tabela mostra execuções detectadas entre 20; não é recall
  por janela.
- **Recall por janela:** `tp/(tp+fn)` em cada execução, entre janelas
  inteiramente contidas no evento ofensivo real. Janelas de fronteira são
  excluídas. A tabela usa a **média dos 20 valores por execução**, conforme
  `results:means:recall:estimate`; não agrupa janelas de diferentes execuções.
  Em A3 há 119 janelas válidas por execução; em F96, 119–120.
- **FPR:** apenas a referência L2, `control.positive/control.available`
  nas 360 janelas de `[30,390)` em cada execução, seguida de média entre as
  20 execuções. Essa FPR **não** é a FPR PRE das execuções ofensivas.
- **Latência:** primeiro alarme válido disponível menos o início real do
  evento, em segundos. O resumo é **condicional às execuções detectadas**;
  para não detectadas, `delay_s` é ausente e `censor_at_seconds` registra o
  fim do evento. O pipeline só fornece IC de latência quando há ao menos
  oito detecções. Não foram imputadas latências zero.
- **Alarmes em POST:** `post.positive/post.available` por execução,
  agregados oficialmente entre execuções. POST considera janelas posteriores
  ao fim real do evento; em A3 são 119 janelas válidas e em F96, 118–119.
  Alarmes em POST não são rotulados como falsos positivos.
- **Observações ausentes:** o cálculo oficial só considera decisões válidas
  disponíveis. Neste conjunto, a cobertura registrada das decisões é 100%
  nas 48 combinações cenário × detector × característica; a variação do
  número de janelas ofensivas e POST decorre das fronteiras do evento, não
  de imputação de duração HTTP ausente.

## Contraste e incerteza

A F5.3-B mostra `recall(A3) − recall(F96)` em **pontos percentuais**. Cada
diferença é formada dentro de um bloco; a média e o IC oficiais preservam
o par. O protocolo usa IC de 95% e 10.000 reamostragens da unidade bloco.
Treze contrastes usam `BCa_block_mean`. Três contrastes degenerados, com
diferença observada zero em duração HTTP, usam o fallback limitado
`Hoeffding_degenerate`; são marcados por losango vazado. Um IC que cruza zero
não demonstra equivalência. Esses IC são pontuais para cada combinação, sem
inferência de superioridade global nem correção de multiplicidade.

## Leitura científica e limites

O CoV detectou somente 2/20, 3/20 e 7/20 execuções A3 nos sinais de
inícios HTTP, pacotes e payload, respectivamente; em F96, detectou 20/20
nesses sinais, mas com recall por janela de aproximadamente 2,6%. Z-Score,
EWMA e CUSUM-freeze tiveram detecção por evento em 20/20 em todos os seus
pares avaliados, mas o recall variou bastante. Na duração média HTTP, Z-Score,
EWMA e CUSUM-freeze apresentaram recall de 100% em ambos os cenários; isso
gera contrastes degenerados e IC conservadores. A latência de uma combinação
com poucas detecções não deve ser interpretada isoladamente.

Os contrastes comparam **configurações ofensivas selecionadas**, que diferem
em taxa, endpoint, custo computacional e concorrência. Não isolam uma causa
única nem estabelecem superioridade intrínseca de um detector ou mecanismo.
O parecer `VALID_WITH_RESTRICTIONS` foi informado na especificação da tarefa;
este lote confirmou diretamente a elegibilidade dos 16 pares e o vínculo
com os resultados TEST do resumo oficial.

## Reprodução

Na raiz do repositório:

```bash
.venv/bin/python -B reports/capitulo5_figuras/lote4_detectores/scripts/generate.py
```

O script confere inventário, partições, hashes dos 240 manifests de
avaliação, calibração CAL_A, verificação CAL_B, blocos, denominadores,
contagens de detecção e estimativas pontuais oficiais. Não lê os dados brutos,
não executa os detectores e não altera artefatos da campanha. A figura foi
inspecionada visualmente. O LaTeX foi conferido textualmente; não há
compilador LaTeX disponível neste ambiente.
