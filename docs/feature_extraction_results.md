# Resultados da Etapa 10

Foram extraídos os 17 datasets históricos elegíveis da Etapa 9 e o run prospectivo da Etapa 8. Os dois incomplete reais foram recusados. Nenhuma etapa anterior/dataset/relatório foi alterado; nenhum commit foi criado.

Os 33 testes novos passaram; a suíte completa passou com 182 testes. Duas extrações de cada run geraram os mesmos bytes em TODOS os arquivos. Hashes/mtimes de 1396 inputs e relatórios permaneceram iguais. Contagens de inícios, conclusões, falhas e starts atacantes foram conservadas; nos 11 runs com direção suportada, todos os records de packets e suas somas de packet_length foram conservados.

Saídas: `experiment_results/stage10-final/`; auditoria em `summary.json`. O CLI também foi executado em PeriodicBurst com Δ=0.5 s.

| Run | Janelas de 1 s | Network disponível | Ticks sem suporte | Janelas infra null |
|---|---:|---|---:|---:|
| stage7-regressions/stage3/A | 31 | não | 3 | 4 |
| stage7-regressions/stage3/B | 30 | não | 3 | 3 |
| stage7-regressions/stage3/C | 31 | não | 3 | 4 |
| stage7-regressions/stage4/A | 31 | não | 2 | 3 |
| stage7-regressions/stage4/B | 30 | não | 2 | 2 |
| stage7-regressions/stage4/C | 31 | não | 2 | 3 |
| stage7-regressions/stage4/technical | 11 | não | 2 | 3 |
| stage7-regressions/stage5/A | 31 | sim | 2 | 3 |
| stage7-regressions/stage5/B | 30 | sim | 2 | 2 |
| stage7-regressions/stage5/C | 31 | sim | 2 | 3 |
| stage7-regressions/stage6/expensive | 9 | sim | 2 | 3 |
| stage7-regressions/stage6/light | 9 | sim | 2 | 3 |
| stage7-regressions/stage6/medium | 9 | sim | 2 | 3 |
| stage7-validation/capacity | 16 | sim | 2 | 3 |
| stage7-validation/continuous | 16 | sim | 2 | 3 |
| stage7-validation/multiple | 16 | sim | 2 | 3 |
| stage7-validation/periodic | 16 | sim | 2 | 3 |
| fresh-periodic | 16 | sim | 2 | 3 |

## Warnings e interpretações

NETWORK_DIRECTION_UNAVAILABLE nos sete runs históricos no host: faltam o inventário/segmento source_proxy usados pela feature set aprovada. Network fica null, nunca zero. Não é erro do dataset Stage 9, nem tentativa de aplicar semântica de containers ao host. Service/infrastructure são preservados.

INFRASTRUCTURE_RECORDS_WITHOUT_SUPPORT em todos os runs: dois ticks sem suporte em geral e três na Etapa 3. Ticks não são usados nas médias; ficam auditáveis no manifest com seus valores originais. Há null adicional na cauda onde não existem samples.

STAGE9_WARNING preserva proveniência histórica desconhecida nos 17 runs arquivados e working tree dirty no run prospectivo. A proveniência do extrator tem scope separado e não preenche a proveniência de execução antiga.

A grade pode estender-se além do planejado, e o último intervalo contém padding não observado. Não se declara cobertura perfeita, ausência física de atividade ou redução da taxa. Nenhum packet/request de cauda foi descartado. Os dois incomplete não produziram feature datasets.

## Evidência PeriodicBurst e cauda

| Janela | Starts atacantes (labels) | Overlap global | Request starts | Request completions |
|---|---:|---:|---:|---:|
| [2,3) | 9 | 0.9083243369996126 s | 17 | 17 |
| [3,4) | 0 | 1 s | 9 | 9 |
| [6,7) | 0 | 1 s | 3 | 4 |
| [12,13) | 0 | 1 s | 7 | 8 |
| [13,14) | 0 | 0.507451790999767 s | 8 | 8 |
| [15,16) | 0 | 0 s | 0 | 0 |

Os silêncios [6,7) e [12,13) têm zero starts atacantes, mas incluem conclusões atacantes e overlap global de 1 s. [15,16) contém 15 records de packets de cauda; service não possui novas requests e infrastructure é null. O trecho após a última observação 15.005907535552979 até 16 não é cobertura comprovada.

Na Etapa 6 expensive, uma request benigna inicia em 8.008284544000162 e conclui em 8.183485651999945, além dos 8 s planejados. Ambos os marcos aparecem em [8,9), independentemente do evento atacante encerrado antes.

Limitações permanecem: clocks distintos, captura potencialmente parcial, médias/cache prévios, network não aplicável aos hosts legados, ausência de ligação packet/request e possível correlação de missingness/cauda com desenho experimental. Stage 11 deve usar apenas detector_columns, jamais labels/chaves/manifest.

Arquitetura, schema e políticas em [feature_timeseries.md](feature_timeseries.md).
