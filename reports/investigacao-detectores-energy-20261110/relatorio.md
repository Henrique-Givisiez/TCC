# Investigação explicativa dos detectores estatísticos

Campanha `energy-powersaver-20261109`. Análise exclusivamente offline de 60 execuções TEST, em 20 blocos L2/A3/F96. Contexto temporal vinculado ao commit `084d4a5df108840a11bb9b449083f6c4ac22f8e9`. Nenhuma implementação, configuração, avaliação, calibração ou checkpoint científico foi alterado. Não foram executadas coletas ou commits.

## 1. Resumo executivo

Foram confirmadas as 16 combinações elegíveis: quatro detectores sobre pacotes ingress, bytes de payload TCP ingress, inícios HTTP e duração HTTP média. CPU é descritiva e está excluída da matriz congelada. A reconstrução determinística, usando os parâmetros originais, reproduziu 375.360 decisões, seus scores, as transições do CUSUM-freeze e as métricas por execução sem divergências; os 48 grupos agregados também conferem.

O CoV detectou A3 em 2/20 execuções para inícios, 3/20 para pacotes e 7/20 para bytes, contra 20/20 em F96. A explicação é a combinação de transição inicial mais forte em F96 e baixa variabilidade relativa nos patamares de ambos os ataques. Todos os alarmes ACTIVE dessas três features ocorreram nos primeiros cinco segundos. O CoV da duração detectou os dois ataques em 20/20, mas deixou de alarmar quando a duração se estabilizou perto do timeout, apesar da indisponibilidade.

EWMA preservou as mudanças sustentadas pela média exponencial de resíduos normalizados. Sua persistência POST depende da feature: há memória de estados muito elevados e, em F96, duração ainda ligeiramente elevada após o retorno operacional descritivo. A memória anterior ao marcador contribuiu decisivamente para parte dos alarmes tardios, mas não explica todos.

CUSUM-freeze funcionou conforme implementado: rejeitou cada atualização que ultrapassou h, preservou o estado anterior e continuou calculando novos candidatos. Todas as trajetórias ofensivas voltaram a emitir decisões negativas; não existe trava permanente. Não há evidência comparativa para declarar superioridade sobre outra variante.

Z-Score respondeu ao nível instantâneo: detectou todos os eventos, mas sua cobertura ACTIVE foi muito menor em inícios HTTP do A3 que em duração ou pacotes. Alarmes POST não equivalem automaticamente a indisponibilidade persistente; o ground truth oficial foi preservado.

## 2. Fontes e rastreabilidade

### 2.1 Inventário e seleção

A seleção é feita por `partition=TEST` no [plano congelado](../../experiments/protocols/energy-powersaver-20261109/plan.json), não pelo nome do cenário. São 20 execuções por cenário, sem exclusões. BASELINE (4), CAL_A (8) e CAL_B (8) entram apenas como origem dos parâmetros, limiares e elegibilidade persistidos; não são réplicas TEST nem foram recalibradas.

Fontes científicas, relativas a `experiment_results/scientific-energy-powersaver-20261109/`:

- `analysis/<feature>/baseline/manifest.json`: média, variância exata, sigma e suporte BASELINE.
- `analysis/<feature>/calibration/manifest.json`: limiares selecionados, referências e resultados CAL_A.
- `analysis/<feature>/verification/manifest.json`: confirmação CAL_B e elegibilidade por par.
- `analysis/<feature>/TEST/<id>/manifest.json`: scores, decisões, disponibilidade e, no CUSUM, transições completas.
- `analysis/<feature>/evaluation/<id>/manifest.json`: métricas oficiais e referência do ground truth.
- [resumo científico](../../experiment_results/scientific-energy-powersaver-20261109/analysis/summary/manifest.json): 16 pares, 48 grupos método×feature×cenário e resultados por execução.
- `collection/<id>/attempt-1/features/timeseries/{network,service,infrastructure}.csv`: cinco features disponíveis, incluindo CPU descritiva; os caminhos e hashes utilizados pelo detector vêm do próprio artefato TEST.
- Ground truth: `dataset/raw/attacks/attack_events.csv`, pelo caminho vinculado à avaliação, sem inferir ataque a partir da feature.

Contexto operacional: [relatório temporal](../investigacao-temporal-energy-20261110/relatorio.md) e [marcadores por execução](../investigacao-temporal-energy-20261110/recuperacao_execucao.csv). O HEAD conferido é o commit indicado pelo pesquisador. Esses marcadores não substituem os rótulos científicos.

### 2.2 Reconstrução e preservação

[analisar.py](analisar.py) lê diretamente as séries e parâmetros persistidos, inicializa as implementações originais em memória e percorre todas as observações desde o índice zero, inclusive WARMUP e a drenagem disponível. Não chama `fit`, `calibrate`, publicadores, coletores ou o pipeline de avaliação com escrita. A função pura de métricas direct é usada para conferir os resultados por execução; suas saídas ficam apenas na análise derivada. EWMA e candidato/posterior CUSUM recebem também conferência por recorrência independente.

Foram confrontados scores, decisões, razões de indisponibilidade, instante de disponibilidade e, no CUSUM, residual, estado anterior, candidato, aceitação e estado posterior. As 960 avaliações de método×feature×execução e os 48 grupos agregados foram conferidos. Resultado: **zero divergências**. As 375.360 linhas de decisão incluem WARMUP e drenagem; a avaliação científica usa somente [30,390), isto é, 360 janelas por execução antes das regras de fronteira. O total de comparações de campos é maior que o de decisões e está identificado separadamente em [verificacao.json](verificacao.json).

O código executado foi comparado com os hashes de runtime do plano congelado. [manifesto_entradas.json](manifesto_entradas.json) e [manifesto_complementar.json](manifesto_complementar.json) permitem conferir as 923 entradas distintas lidas, incluindo código e contexto operacional. A verificação final confirmou que seus bytes permaneceram inalterados. Os hashes finais dos artefatos derivados estão em [verificacao.json](verificacao.json).

Reprodução, a partir da raiz, sem escrita em resultados científicos:

```bash
.venv/bin/python -B reports/investigacao-detectores-energy-20261110/analisar.py
.venv/bin/python -B reports/investigacao-detectores-energy-20261110/sintetizar.py
.venv/bin/python -B reports/investigacao-detectores-energy-20261110/verificar.py
```

Os scripts sobrescrevem somente seus derivados neste diretório. Não reproduzem calibração nem variantes contrafactuais. Não se exportaram novamente todas as trajetórias completas: elas já existem nos artefatos científicos. Foram preservados resumos por execução e testemunhos compactos de transição.

## 3. Contrato dos detectores

O contrato auditado antes da interpretação está em [contrato_detectores.md](contrato_detectores.md). As descrições abaixo correspondem ao código efetivo, não a fórmulas presumidas pelo nome do método.

### 3.1 Features e tempo

Todas as observações científicas são janelas não sobrepostas de 1 s, [i,i+1), com disponibilidade simulada no fechamento i+1. A latência reportada não mede tempo de execução do algoritmo nem disponibilidade real em produção. O estado começa em zero no início da execução e **não é reiniciado** em PRE, ACTIVE ou POST.

| Sigla usada nas tabelas | Feature | Semântica |
|---|---|---|
| P | `ingress_packet_count` | Contagem de registros de pacotes ingress; inclui payload zero e retransmissões observadas. Não é contagem de requisições. |
| B | `ingress_tcp_payload_length_sum_bytes` | Soma do campo `packet_length` do resumo TCP ingress; não é volume Ethernet nem bytes únicos de aplicação. |
| N | `request_starts` | Todos os inícios HTTP no cliente, legítimos e ofensivos, pelo segundo de início. |
| D | `mean_duration_ms` | Média de todas as terminações HTTP no segundo de **término**, incluindo timeouts, falhas e ambas as classes de tráfego. Não é média exclusiva de 2xx ou de tráfego legítimo. |
| CPU | `mean_cpu_percent` | Disponível como feature descritiva, com política estrita de atribuição e ausências; sem limiares ou avaliações científicas nesta campanha. |

Fonte: [extract_features.py](../../experiments/extract_features.py:222), [feature_schema.py](../../experiments/feature_schema.py:17). Não há logaritmo, valor absoluto ou imputação das séries científicas.

O [protocolo congelado](../../docs/scientific_protocol_direct_c135_o3_20261108.json:683) exclui CPU por insuficiência de disponibilidade temporal nos pilotos, agravada pela exigência de seis observações consecutivas do CoV. Isso não é resultado TEST de nenhum detector. O inventário [cpu_descritiva.csv](cpu_descritiva.csv) confirma que a feature atribuída tem muitas ausências: em ACTIVE, médias de 67,70 janelas disponíveis em A3 e 27,85 em F96, dentre 120. Ausência da feature atribuída não equivale a ausência de todos os snapshots brutos de CPU. Nos quatro sinais científicos, nenhuma decisão ficou indisponível dentro das janelas avaliadas de TEST.

### 3.2 Normalização e referências

Z-Score, EWMA e CUSUM compartilham a mesma referência por feature: quatro execuções BASELINE legítimas, janelas [30,390), 1.440 valores válidos. A média e a variância são calculadas com aritmética racional exata; sigma amostral usa ddof=1. Cada observação tem o mesmo peso. A referência fica congelada durante TEST.

| Feature | mu | sigma |
|---|---:|---:|
| P | 47,613889 pacotes/s | 11,968029 |
| B | 4.807,389583 bytes/s | 1.228,135744 |
| N | 15,865972 inícios/s | 4,051538 |
| D | 43,123104 ms | 4,842355 |

Os valores completos, parâmetros e limiares com precisão original estão em [parametros_congelados.csv](parametros_congelados.csv). O código usa Decimal com 50 dígitos e ROUND_HALF_EVEN nas operações finais; os valores arredondados deste relatório não são usados no replay.

### 3.3 Z-Score

`z_t=(x_t−mu)/sigma`, **assinado**, com alarme estrito `z_t>h`. Só a cauda superior é detectada; uma redução grande não gera alarme por módulo. Não existe atualização da referência ou estado acumulado. Valor ausente gera score indisponível. Baseline de sigma zero é rejeitada, sem epsilon. Fonte: [zscore.py](../../analysis/detection/detectors/zscore.py).

### 3.4 CoV

`CoV_t=s_t/m_t`, usando média aritmética e desvio amostral ddof=1 das **seis observações consecutivas incluindo a atual**. Não usa mu/sigma BASELINE. A decisão é `CoV_t>h`, não uma distância em relação ao CoV normal e não uma desigualdade inferior. Média exatamente zero torna o score indisponível; média positiva pequena não é regularizada por epsilon. Um valor ausente limpa o histórico, e seis observações válidas consecutivas são novamente necessárias. Fonte: [cov.py](../../analysis/detection/detectors/cov.py).

Consequência: uma feature alta e constante pode ser fortemente anômala em nível e produzir CoV próximo de zero. Uma transição de nível gera dispersão temporária enquanto valores dos dois patamares coexistem na janela de seis pontos. Isso deve ser verificado separadamente para cada feature.

### 3.5 EWMA

O score é `E_t=0,2 z_t+0,8 E_(t−1)`, com `E_0` inicializado em zero antes da primeira observação. Alpha é exatamente 0,2. A estatística decisória é essa média exponencial assinada, sem fator de variância dependente de t ou limite clássico presumido. Alarme `E_t>h`; alarmar não reseta nem congela E. Valor ausente gera decisão indisponível e reseta E para zero. Fontes: [ewma.py](../../analysis/detection/detectors/ewma.py), [_standardized.py](../../analysis/detection/detectors/_standardized.py).

O peso de um estado anterior decai por `0,8^k`: aproximadamente 3,52% após 15 atualizações válidas e 0,124% após 30. Isso é uma propriedade algébrica do alpha fixado, não comparação com outro alpha. Um estado de ordem 400 ainda pode contribuir materialmente durante a recuperação.

### 3.6 CUSUM-freeze

Com k=0,5 e estado inicial S=0:

```text
C_t = max(0, S_(t−1) + z_t − 0,5)
alarme_t = (C_t > h)
S_t = S_(t−1), se houver alarme
S_t = C_t, caso contrário
```

O score publicado é o **candidato C**, que pode exceder h; o estado armazenado S permanece em [0,h]. O congelamento é a rejeição daquela atualização: não existe flag de trava permanente nem interrupção das observações. Cada janela seguinte calcula outro candidato com o estado preservado; pode emitir novo alarme ou aceitar a atualização e emitir decisão negativa. Empate com h é aceito sem alarme. Ausência gera score/decisão indisponíveis e estado zero. Fonte: [cusum_freeze.py](../../analysis/detection/detectors/cusum_freeze.py).

O mesmo h pertence à transição e à decisão. Não é válido trocar h apenas limiarizando scores de uma trajetória anterior. A reconstrução usou exatamente o h congelado de cada feature.

### 3.7 Limiares e elegibilidade

Z/CoV/EWMA usam o quantil empírico superior de CAL_A, alvo nominal de 1%, índice `ceil((N−1)×0,99)`, comparação estrita > e empate negativo. CUSUM-freeze usa o menor h elegível da grade persistida vinculada ao CUSUM-reference. Esta investigação lê a seleção; não a refaz. CAL_A exige cobertura ≥95%, FPR médio ≤1% e máximo por execução ≤5%; CAL_B confirma com média ≤2% e máximo ≤5%, sem nova seleção. Fontes: [engine.py](../../analysis/detection/scientific/engine.py), [empirical.py](../../analysis/detection/empirical.py).

As diferenças de h refletem as distribuições de cada estatística sob tráfego legítimo. Não se podem comparar diretamente magnitudes de CoV, EWMA e CUSUM como se tivessem a mesma unidade ou distribuição.

## 4. Conferência dos resultados científicos

### 4.1 Definições e denominadores

A métrica oficial de detecção de evento exige pelo menos uma decisão positiva de janela com sobreposição ao evento, disponível entre `actual_start_seconds` e `actual_end_seconds`. Latência = primeira disponibilidade elegível menos início efetivo, **condicional aos eventos detectados**. Janelas parcialmente ofensivas podem permitir detecção de evento, mas não entram no recall de janelas integralmente ofensivas.

O FPR primário é obtido nas 20 L2, em [30,390): positivas/disponíveis por execução, depois média. Aqui cada L2 tem 360 decisões disponíveis, total 7.200 por par. PRE dos ataques tem `pre_fpr` separado. O protocolo direct relata POST separadamente: não o incorpora ao FPR primário L2. POST oficial exige início de janela ≥270 e ≥`actual_end_seconds`. Portanto o denominador costuma ser 119 janelas em A3 e 118 em F96, não 120. A classificação de fronteira é preservada exatamente. Fonte: [direct_metrics.py](../../analysis/detection/scientific/direct_metrics.py).

### 4.2 As 16 combinações

Z = Z-Score; C = CoV; E = EWMA; F = CUSUM-freeze. Latências são médias em segundos, condicionais à detecção; as duas contagens de POST são médias de janelas positivas por execução, na definição oficial. As casas arredondadas de h são apenas de apresentação.

| Feature | Método | h | Detecção A3 | Detecção F96 | FPR L2 | Latência A3 / F96 | Positivas POST A3 / F96 |
|---|---|---:|---:|---:|---:|---:|---:|
| P | Z | 2,455384 | 20/20 | 20/20 | 0,8333% | 2,843 / 0,992 | 22,20 / 6,35 |
| P | C | 0,432214 | 3/20 | 20/20 | 1,1528% | 1,661 / 0,992 | 4,15 / 7,85 |
| P | E | 0,792698 | 20/20 | 20/20 | 0,9444% | 2,943 / 0,992 | 46,65 / 19,15 |
| P | F | 3,844449 | 20/20 | 20/20 | 0,4583% | 2,793 / 0,992 | 35,70 / 6,70 |
| B | Z | 2,500221 | 20/20 | 20/20 | 0,6944% | 1,593 / 0,992 | 0,75 / 0,85 |
| B | C | 0,443323 | 7/20 | 20/20 | 1,1667% | 1,422 / 0,992 | 1,65 / 4,15 |
| B | E | 0,785326 | 20/20 | 20/20 | 0,9167% | 2,043 / 0,992 | 6,00 / 12,85 |
| B | F | 3,833219 | 20/20 | 20/20 | 0,4583% | 2,043 / 0,992 | 0,80 / 0,70 |
| N | Z | 2,501279 | 20/20 | 20/20 | 0,6806% | 3,143 / 0,992 | 0,75 / 0,85 |
| N | C | 0,443323 | 2/20 | 20/20 | 1,2083% | 0,993 / 0,992 | 1,05 / 4,20 |
| N | E | 0,785658 | 20/20 | 20/20 | 0,9167% | 2,943 / 0,992 | 4,55 / 11,95 |
| N | F | 3,835899 | 20/20 | 20/20 | 0,4861% | 2,793 / 0,992 | 0,75 / 0,80 |
| D | Z | 2,343848 | 20/20 | 20/20 | 1,2917% | 0,993 / 0,992 | 38,25 / 14,70 |
| D | C | 0,182833 | 20/20 | 20/20 | 1,7639% | 0,993 / 0,992 | 7,30 / 9,55 |
| D | E | 0,787408 | 20/20 | 20/20 | 1,5139% | 0,993 / 0,992 | 66,90 / 62,65 |
| D | F | 3,566411 | 20/20 | 20/20 | 0,9722% | 0,993 / 0,992 | 38,70 / 23,35 |

Fonte completa: [tabela_combinacoes.csv](tabela_combinacoes.csv), com parâmetros, h exato, denominadores de latência, frações POST e recall; métricas individuais em [alarmes_por_execucao.csv](alarmes_por_execucao.csv). Todas as contagens, médias de métricas, latências e durações POST correspondem às avaliações e ao resumo persistidos. Não se recalcularam intervalos de confiança por bootstrap; os existentes continuam nos artefatos científicos.

As médias rápidas do CoV em A3 são condicionais a somente 2, 3 ou 7 detecções, com misses censurados no fim do evento. O resumo oficial não fornece intervalo de latência nesses casos por suporte inferior a oito. Não se deve apresentar essas médias como evidência de maior rapidez global. O alvo de 1% CAL_A tampouco garante FPR TEST exatamente ≤1%; os valores TEST foram preservados, sem retuning.

## 5. Investigação do CoV

### 5.1 Três sinais de intensidade: mudança de nível e variabilidade relativa

A hipótese central é sustentada **para P, B e N**, com uma ressalva: F96 também apresenta CoV baixo no patamar sustentado; sua detecção de 20/20 vem da transição inicial, não de uma variabilidade relativa elevada durante todo o ataque.

| Feature | CoV PRE A3 | CoV ACTIVE A3 | CoV ACTIVE F96 | h | Eventos A3 / F96 |
|---|---:|---:|---:|---:|---:|
| P | 0,2357 | 0,1316 | 0,0558 | 0,4322 | 3/20 / 20/20 |
| B | 0,2401 | 0,1973 | 0,0693 | 0,4433 | 7/20 / 20/20 |
| N | 0,2396 | 0,1946 | 0,0758 | 0,4433 | 2/20 / 20/20 |

Os CoV da tabela são médias entre execuções das medianas temporais por execução, não medianas de segundos empilhados. Fonte: [analise_cov.csv](analise_cov.csv), [variabilidade_cov.csv](variabilidade_cov.csv).

No A3, N teve média local de aproximadamente 15,92 em PRE e 23,63 em ACTIVE, enquanto o desvio local passou de 3,87 para 4,69: a média cresceu proporcionalmente mais, reduzindo s/m. P passou de média local 47,80 para 108,29, com desvio 11,46 para 14,80. B passou de 4.824,48 para 7.792,80, com desvio 1.176,45 para 1.564,48. Há aumento de intensidade sem aumento proporcional suficiente da dispersão, na maioria das janelas. Não é ausência de mudança da feature.

As diferenças entre 2, 3 e 7 detecções dependem do sinal observado, da magnitude da transição e do limiar específico. B não é múltiplo fixo de N; P inclui registros TCP sem payload, portanto os três sinais não são substitutos. Os dados sustentam as diferenças de scores e cruzamentos, mas esta análise não decompõe causalmente o excedente de pacotes entre ACKs, retransmissões e outros tipos.

Em F96, as máximas de CoV ACTIVE por execução têm médias de aproximadamente 1,007 (P), 1,118 (B) e 0,991 (N), bem acima dos respectivos h. Mas as medianas ACTIVE caem abaixo até das medianas legítimas. A transição mistura os poucos pontos anteriores ao ataque com valores muito maiores, e cruza o limiar antes que a janela de seis observações se adapte completamente ao novo patamar.

### 5.2 Alarmes concentrados na transição

Em todas as 20 F96, o primeiro alarme de P/B/N fica disponível em +1 s relativo ao início programado; o último desses alarmes ACTIVE fica entre +4 e +5 s. Em A3, as poucas execuções detectadas alarmam entre +1 e +4 s, dependendo da feature. Não há alarmes dessas três features após os primeiros 10 s de ACTIVE, em nenhuma repetição. Na realidade, o último é +4 s em A3 e +5 s em F96. Fonte: [cov_tempos_alarmes.csv](cov_tempos_alarmes.csv).

Assim, 20/20 eventos F96 detectados coexistem com recall oficial de aproximadamente 2,58% das janelas ofensivas completas para esses pares. A detecção binária de evento não indica acompanhamento da saturação sustentada.

### 5.3 A duração não repete o resultado de baixa detecção

O CoV D detecta 20/20 A3 e 20/20 F96, pois a transição de dezenas para centenas/milhares de milissegundos gera dispersão relativa suficiente. Há em média 13,10 decisões positivas nos 120 segundos programados de A3 e 12,45 em F96, com intervalos entre execuções de 7–22 e 9–15. Todas ocorrem antes de completar 30 s de ACTIVE.

Nos últimos 30 s de ACTIVE, a duração termina próxima de 2.004,70 ms em A3 e 2.005,26 ms em F96, enquanto o desvio **local de seis observações** médio é somente 0,17 e 0,24 ms. CoV fica da ordem de 0,0001, contra h=0,1828. A estabilização perto do timeout reduz o score justamente quando a disponibilidade legítima está em zero. Essa duração é observada no cliente e não significa término computacional na vítima. Fontes: [analise_cov.csv](analise_cov.csv), [features_por_periodo.csv](features_por_periodo.csv), contexto temporal anterior.

Portanto, a hipótese de mudança de nível sem variabilidade proporcional explica o silêncio sustentado também em D, mas **não** explica baixa detecção de evento em D: esse par detectou todos os eventos na transição. Não se generaliza a falha binária de P/B/N para todas as features.

## 6. Investigação do EWMA

### 6.1 Início e saturação sustentada

No A3, os resíduos médios ACTIVE são aproximadamente 1,96 para N, 2,49 para B, 5,19 para P e 382 para D. A EWMA acumula a mudança de nível sem atualizar a referência normal. Os h EWMA ficam próximos de 0,79 porque sua distribuição legítima é mais concentrada que a de z instantâneo. Como referências de nível para um patamar constante, mu+sigma×h equivale aproximadamente a 19,05 inícios/s, 5.771,88 bytes/s, 57,10 pacotes/s e 46,94 ms; esses não são limiares instantâneos de x.

Em A3, o recall oficial EWMA é 98,95% para N, 99,58% para B, 99,08% para P e 100% para D, contra 27,90%, 48,32%, 92,73% e 100% no Z-Score. A média exponencial torna persistente a evidência de um nível moderadamente elevado, mesmo quando muitas observações individuais não alcançam o h do Z. Em F96, todos os pares EWMA têm 100% de recall oficial. Fonte: [tabela_combinacoes.csv](tabela_combinacoes.csv), [analise_zscore.csv](analise_zscore.csv).

### 6.2 Retorno e diferenças entre features

O primeiro segundo de decisão negativa em POST, medido pela disponibilidade após 270 s, ocorre em média nos seguintes tempos:

| Feature | A3: média; mínimo–máximo | F96: média; mínimo–máximo |
|---|---|---|
| N | 4,40; 1–8 s | 13,15; 10–18 s |
| B | 5,60; 3–8 s | 14,10; 11–18 s |
| P | 47,40; 37–57 s | 20,65; 15–26 s |
| D | 67,75; 53–83 s | 43,45; 35–56 s |

Fonte: [analise_ewma.csv](analise_ewma.csv). Primeiro negativo não é retorno permanente: novos alarmes podem surgir depois. Em D/F96, o último positivo ocorre em média +114,10 s, e em algumas execuções chega ao fechamento final +120 s. Não se deve converter o último alarme isolado em duração contínua de indisponibilidade.

N e B voltam a níveis legítimos rapidamente após cessarem os inícios ofensivos, apesar do backlog computacional que continua na vítima. P e D podem permanecer alterados durante a drenagem; isso é observado nas próprias séries, sem supor que todas as features representem a mesma carga. A memória de EWMA prolonga a resposta depois de a observação baixar.

### 6.3 Memória versus novas observações após retorno operacional

Foi definido um marcador conservador por execução: máximo entre confirmação do retorno de pendências ao patamar PRE, confirmação de disponibilidade, primeira fila aguardando vazia, último término computacional ofensivo e último término de falha legítima. As confirmações descritivas exigem três blocos de 5 s e já vêm da investigação temporal. O marcador ocorre em média +55 s em A3 (40–65) e +26,5 s em F96 (25–35), após 270 s. Não é mudança do ground truth nem prova de equivalência estatística da feature com BASELINE.

A partir do marcador, decompôs-se o estado observado em `E_t=0,8^k E_m + soma ponderada dos z realmente observados depois de m`, com resets preservados. É uma identidade do próprio estado, não uma simulação de outro detector ou novo estado inicial. Contou-se quando a contribuição posterior, sozinha na decomposição, não excedia h, mas o score completo excedia: nesses casos, a memória anterior ao marcador era necessária ao cruzamento.

| Duração EWMA após o marcador | A3 | F96 |
|---|---:|---:|
| Execuções com decisões positivas | 20/20 | 20/20 |
| Positivas por execução, média | 12,90 | 38,10 |
| Mediana; Q1–Q3; mínimo–máximo | 12; 9–15,25; 7–22 | 38; 31,5–44,25; 20–61 |
| Cruzamentos em que a memória anterior ao marcador foi necessária, média | 11,00 | 11,60 |
| Estado EWMA no marcador, média | 8,60 | 8,77 |

Fontes: [analise_ewma.csv](analise_ewma.csv), [variabilidade_mecanismos.csv](variabilidade_mecanismos.csv). As 20 execuções de cada ataque tiveram pelo menos sete cruzamentos desse tipo. Não se atribui todo alarme restante à ausência de memória: as observações posteriores também têm sua própria memória exponencial, e as contribuições podem atuar conjuntamente.

Em F96, a duração média por janela depois do marcador ainda é 46,10 ms, contra 43,55 em A3 e mu BASELINE=43,12 ms. Nos últimos 30 s, F96 fica em média em 45,83 ms; L2 em 42,80 ms e A3 em 43,14 ms. O resíduo médio posterior é 0,615 em F96 contra 0,088 em A3. Logo, uma feature discretamente elevada e seus episódios de maior duração também sustentam alarmes, mesmo com 100% de sucesso legítimo final. Fontes: [features_apos_retorno.csv](features_apos_retorno.csv), [features_por_periodo.csv](features_por_periodo.csv).

**Resposta à questão central:** POST inicial combina degradação residual e memória; após o marcador, D mantém memória demonstrável e, sobretudo em F96, contribuição de novas observações elevadas. Não é correto chamar toda persistência de memória pura, nem toda decisão positiva de indisponibilidade remanescente.

## 7. Investigação do CUSUM-freeze

### 7.1 O congelamento funcionou

Todos os estados rejeitados preservaram exatamente o valor anterior; todos os candidatos e posteriores reconstruídos coincidiram com os persistidos. O estado armazenado nunca excedeu h, enquanto candidatos de D chegaram à ordem de 405. Não houve inconsistência entre candidato, decisão e estado. Fontes: [verificacao.json](verificacao.json), [analise_cusum_freeze.csv](analise_cusum_freeze.csv), [cusum_retomadas.csv](cusum_retomadas.csv).

No F96, as 120 janelas programadas ACTIVE foram rejeitadas/positivas em todas as 20 execuções para cada feature. Em D/A3 ocorre o mesmo. No A3, as médias de rejeições são 116,40 em P, 103,30 em B e 90,85 em N, com aceitações entre alarmes quando o candidato cai abaixo de h. Isso explica por que a detecção de evento de 20/20 não implica decisões continuamente positivas em todos os sinais.

### 7.2 Evidência concreta da preservação e retomada

Os exemplos abaixo são das primeiras execuções ofensivas TEST de cada cenário, depois de caracterizadas todas as distribuições. São segundos da execução, não tempos relativos ao ataque. Valores arredondados somente para leitura; D tem h=3,566411.

| Execução / janela | z | Estado anterior | Candidato | Estado posterior | Decisão |
|---|---:|---:|---:|---:|---|
| `ps_direct80_023_A3`, [150,151) | 40,5550 | 0 | 40,0550 | 0 | positiva |
| mesma, [269,270) | 405,0780 | 0 | 404,5780 | 0 | positiva |
| mesma, [306,307) | 1,4591 | 0 | 0,9591 | 0,9591 | negativa |
| `ps_direct80_022_F96`, [150,151) | 17,8019 | 0 | 17,3019 | 0 | positiva |
| mesma, [269,270) | 405,2080 | 0 | 404,7080 | 0 | positiva |
| mesma, [277,278) | −1,1276 | 0 | 0 | 0 | negativa |

Fonte: [testemunhos_transicoes.csv](testemunhos_transicoes.csv). O acumulador armazenado nesses exemplos não cresce para centenas: é o **candidato publicado** que assume esse valor. A emissão repetida de alarmes decorre dos novos resíduos elevados, mesmo com o estado anterior preservado em zero.

Todas as **160 trajetórias ofensivas método×feature×execução** voltaram a emitir decisão negativa e aceitaram atualizações após o primeiro cruzamento ACTIVE. Não existe trava permanente. Em D, o primeiro negativo após esse cruzamento ocorre em média em 309,20 s em A3 e 280,55 s em F96. Nas features N/B de F96 ele ocorre em 271 s em todas as execuções, embora o processamento ofensivo ainda não tenha terminado. Fonte: [analise_cusum_freeze.csv](analise_cusum_freeze.csv), [cusum_retomadas.csv](cusum_retomadas.csv).

### 7.3 Persistência e alcance da variante

O estado preservado pode aumentar a sensibilidade do candidato seguinte: a condição equivale a `z_t > 0,5+h−S_(t−1)`. Portanto, novas observações e estado anterior atuam juntos. Quando z diminui, uma atualização aceita permite reduzir S, possivelmente a zero. Em D/F96, alarmes tardios continuam mesmo após a recuperação operacional descritiva, junto à duração ainda deslocada; isso não exige um estado permanentemente congelado.

Há em média 13,35 janelas positivas D/F96 depois do marcador conservador, contra 1,30 em A3. Nos últimos 30 s, são 4,20 em F96 e 0,40 em A3. As novas decisões precisam sempre de um candidato acima de h; não são republicação automática do primeiro alarme. Fontes: [alarmes_post_recuperacao.csv](alarmes_post_recuperacao.csv), [features_apos_retorno.csv](features_apos_retorno.csv).

**O que foi demonstrado:** a variante impede que uma atualização que excede h aumente o estado armazenado, e continua emitindo decisões conforme a regra do projeto. **O que não foi demonstrado:** redução de falsos alarmes, latência ou persistência relativamente ao CUSUM clássico/outra variante. Não foi construída comparação contrafactual. A existência de um limite de estado e o FPR observado não bastam para atribuir ganho comparativo ao congelamento.

## 8. Investigação do Z-Score

O Z-Score é sensível a mudança de nível na direção superior; a referência não se adapta à saturação. Os limiares correspondem aproximadamente aos seguintes níveis instantâneos:

| Feature | Nível de fronteira mu+sigma×h | Recall oficial A3 | Recall oficial F96 |
|---|---:|---:|---:|
| P | 77 pacotes/s | 92,73% | 100% |
| B | 7.878 bytes/s | 48,32% | 99,21% |
| N | 26 inícios/s | 27,90% | 99,21% |
| D | 54,47 ms | 100% | 100% |

Fontes: [analise_zscore.csv](analise_zscore.csv), [tabela_combinacoes.csv](tabela_combinacoes.csv). A decisão é estrita; a fronteira arredondada não deve substituir a comparação Decimal original. Empates com o score h são negativos.

Em A3, N tem resíduo médio 1,96, abaixo de h=2,50: oscilações geram alguns cruzamentos, suficientes para detectar todos os eventos, mas deixam a maioria das janelas negativa. B fica em média perto de h, com cobertura intermediária. P e D têm resíduos médios muito acima dos respectivos limiares, sustentando muito mais decisões positivas. Em F96, a intensidade entregue ainda mantém os níveis muito acima da referência nos quatro sinais. Fonte: [analise_zscore.csv](analise_zscore.csv).

A ausência de memória torna o Z capaz de retornar assim que a observação baixa, mas não garante ausência de novos alarmes por flutuações posteriores. POST oficial tem em média apenas 0,75 positiva N/A3 e 0,85 N/F96, enquanto D tem 38,25 e 14,70. D permanece elevada durante a drenagem; seu sinal não é equivalente aos inícios ofensivos. Depois do marcador conservador, D ainda tem 0,85 e 5,75 positivas, coerentes com episódios de duração acima de 54,47 ms, não com um estado acumulado. Fontes: [alarmes_post_recuperacao.csv](alarmes_post_recuperacao.csv), [analise_zscore.csv](analise_zscore.csv).

Os quatro pares Z detectaram 20/20 em ambos os ataques, mas isso não estabelece superioridade sobre os demais: FPR, cobertura sustentada, direção da anomalia e latência condicional também importam. As diferenças aqui explicam o resultado observado sem testar novas variantes ou limiares.

## 9. Alarmes em POST

### 9.1 Classificação contextual sem novo ground truth

Cada execução ofensiva foi vinculada aos seis tipos de marcador solicitados: fim programado de emissão, última conclusão ofensiva, primeira fila aguardando vazia, retorno das pendências e disponibilidade (início/confirmado), última requisição POST com falha (início/término). Eles são repetidos como colunas em [alarmes_post_recuperacao.csv](alarmes_post_recuperacao.csv), junto ao marcador conservador definido na seção 6.

O marcador conservador é mais tardio que o primeiro sucesso ou primeiro esvaziamento, pois inclui a confirmação descritiva de 15 s. “Antes do retorno” inclui momentos de degradação e momentos de observação da recuperação; não significa que cada segundo desse segmento tenha indisponibilidade. “Depois do retorno” não garante que a feature seja igual à BASELINE. As 40 execuções possuem marcadores suficientes; não houve categoria sem evidência. A regra reserva janela que atravessa o marcador como fronteira; nesta amostra os marcadores conservadores ficaram na grade e essa categoria teve zero janelas.

As contagens são calculadas dentro do POST **oficial** para manter correspondência com o protocolo; o contexto operacional usa marcadores baseados no fim programado de emissão de 270 s. Isso é explícito e não transfere decisões entre os rótulos oficiais.

### 9.2 Quantificação por segmento

Exemplo transversal para D, média entre as 20 execuções de cada cenário:

| Método | Cenário | Positivas antes do marcador | Positivas depois do marcador | Proporção positiva depois, média por execução | Positivas nos últimos 30 s |
|---|---|---:|---:|---:|---:|
| Z-Score | A3 | 37,40 | 0,85 | 1,34% | 0,35 |
| Z-Score | F96 | 8,95 | 5,75 | 6,16% | 2,15 |
| CoV | A3 | 6,00 | 1,30 | 1,95% | 0,30 |
| CoV | F96 | 6,65 | 2,90 | 3,08% | 1,15 |
| EWMA | A3 | 54,00 | 12,90 | 20,08% | 0,60 |
| EWMA | F96 | 24,55 | 38,10 | 40,78% | 9,00 |
| CUSUM-freeze | A3 | 37,40 | 1,30 | 2,04% | 0,40 |
| CUSUM-freeze | F96 | 10,00 | 13,35 | 14,29% | 4,20 |

Fonte: [alarmes_post_recuperacao.csv](alarmes_post_recuperacao.csv); distribuição completa em [variabilidade_post.csv](variabilidade_post.csv). O denominador depois do marcador tem média de 65 janelas por execução A3 e 93,5 por execução F96. As proporções são primeiro calculadas por execução, não pela divisão das duas médias da tabela. Para P/B/N, as médias de positivas posteriores ficam entre 0,20 e 1,40 por execução, dependendo do detector/cenário.

POST pode conter simultaneamente: decisão fora do evento oficial, degradação residual, memória estatística e anomalia de feature sem indisponibilidade. No protocolo direct, “positivo POST” é a denominação primária desse resultado; chamá-lo de falso positivo relativamente ao intervalo do ataque não o transforma em evidência de serviço normal naquele momento. Tampouco altera o FPR primário definido em L2.

O contexto temporal encontrou duas recuperações operacionais não confirmadas (`ps_direct80_043_A3`, `ps_direct80_075_F96`) por crescimento de três pendências HTTP na última janela, apesar de sucesso final integral. Esta análise mantém esse fato e não usa o booleano operacional para substituir os marcadores descritivos ou os rótulos dos detectores.

## 10. Variabilidade entre execuções

As tabelas de mecanismo têm uma linha por execução e feature; os resumos incluem média, mediana, DP amostral, quartis, mínimo e máximo. Não se tratam segundos consecutivos como réplicas independentes. Nenhuma observação foi excluída.

No CoV, as exceções A3 detectadas foram:

- N: `ps_direct80_033_A3` e `ps_direct80_048_A3`.
- P: `ps_direct80_033_A3`, `ps_direct80_041_A3` e `ps_direct80_048_A3`.
- B: `ps_direct80_023_A3`, `ps_direct80_030_A3`, `ps_direct80_033_A3`, `ps_direct80_041_A3`, `ps_direct80_045_A3`, `ps_direct80_048_A3` e `ps_direct80_053_A3`.

Todos esses alarmes são iniciais. A lista integral de misses por par está em [execucoes_divergentes.csv](execucoes_divergentes.csv), e os tempos em [cov_tempos_alarmes.csv](cov_tempos_alarmes.csv). Não se atribui uma anomalia técnica às execuções não detectadas; elas demonstram a interação entre sinal e estatística.

No EWMA D, as positivas após o marcador têm média/mediana 12,9/12 em A3, IQR 9–15,25 e intervalo 7–22; em F96, 38,1/38, IQR 31,5–44,25 e intervalo 20–61. O maior valor F96 é `ps_direct80_058_F96` (61), seguido de `ps_direct80_022_F96` (54) e `ps_direct80_032_F96` (53). Esses valores não foram excluídos e o máximo 61 não ultrapassa a cerca superior de 1,5×IQR dessa distribuição.

Aplicando a regra descritiva de 1,5×IQR às positivas EWMA tardias de P/B/N, aparecem `ps_direct80_055_A3`, `ps_direct80_072_A3`, `ps_direct80_056_F96` e, em P, `ps_direct80_074_F96`. São entre cinco e oito janelas tardias em sinais cuja mediana é zero ou 0,5, não evidência automática de falha experimental. Fonte: [execucoes_divergentes.csv](execucoes_divergentes.csv), com critério e variável explícitos.

Para CUSUM D, as positivas POST programadas variam de 25–50 em A3 e 11–37 em F96; depois do marcador, de 0–5 em A3 e 3–25 em F96. Todos os 20 F96 ainda tiveram algum alarme tardio D, mas todas as trajetórias retomaram decisões negativas. A variabilidade confirma episódios intercalados, não um latch universal. Fontes: [analise_cusum_freeze.csv](analise_cusum_freeze.csv), [variabilidade_mecanismos.csv](variabilidade_mecanismos.csv).

## 11. Hipóteses e evidências

| Hipótese | Classificação | Evidência e delimitação |
|---|---|---|
| Baixa detecção CoV A3 em P/B/N decorre de mudança de nível sem aumento proporcional suficiente da variabilidade | **Sustentada** | Medianas CoV ACTIVE menores que PRE e h; somente 3/7/2 eventos detectados; cruzamentos apenas iniciais. [analise_cov.csv](analise_cov.csv), [cov_tempos_alarmes.csv](cov_tempos_alarmes.csv). Não se estende à detecção de evento D, que é 20/20. |
| CoV acompanha a sobrecarga sustentada em F96 porque detecta 20/20 eventos | **Não sustentada** | Alarmes P/B/N terminam até +5 s; D até +29 s; nenhum positivo CoV após os primeiros 30 s, embora a saturação persista. |
| Persistência EWMA POST é somente memória do ataque | **Parcialmente sustentada** | Memória anterior ao marcador é necessária em parte dos cruzamentos; F96 também mantém duração e novas contribuições elevadas. [analise_ewma.csv](analise_ewma.csv), [features_apos_retorno.csv](features_apos_retorno.csv). |
| CUSUM-freeze preserva o estado rejeitado e continua decidindo conforme a variante | **Sustentada** | Replay exato, estados em [0,h], candidatos acima de h e retomada negativa em 160/160 trajetórias ofensivas. [cusum_retomadas.csv](cusum_retomadas.csv), [verificacao.json](verificacao.json). |
| Congelamento cria alarme permanente após o primeiro cruzamento | **Não sustentada** | Todas as trajetórias ofensivas emitiram decisões negativas e aceitaram atualizações posteriores. |
| Congelamento melhorou desempenho comparado ao CUSUM clássico | **Inconclusiva** | Não existe comparação apropriada executada nesta investigação; não se criou contrafactual. Limitar S é propriedade demonstrada, ganho de desempenho relativo não. |
| Diferenças Z/EWMA no A3 são compatíveis com nível moderado abaixo do h instantâneo e acima da faixa EWMA | **Sustentada** | N: resíduo médio 1,96; hZ=2,50 e hE=0,786, com recall 27,90% versus 98,95%. [tabela_combinacoes.csv](tabela_combinacoes.csv), [analise_zscore.csv](analise_zscore.csv). |
| Toda decisão positiva depois do retorno operacional indica indisponibilidade persistente | **Não sustentada** | Há memória e anomalia de duração com sucesso HTTP final integral, sobretudo D/F96. [alarmes_post_recuperacao.csv](alarmes_post_recuperacao.csv), relatório temporal. |

## 12. Limitações

**Protocolo:** a direção é superior; reduções de variabilidade relativa ou quedas de nível não são o alvo dessas decisões. A avaliação binária de evento admite detecção por uma única janela, diferente de acompanhamento sustentado. Latências são condicionais aos detectados e simuladas no fechamento da janela, sem medir custo computacional do algoritmo. A calibração legítima independente não garante invariância do FPR TEST. Não há comparação de doses iguais ou generalização de superioridade entre detectores.

**Features e instrumentação:** D é calculada por término e mistura classes/resultados; não pode ser interpretada como latência 2xx legítima. P e B são observáveis TCP, não operações computacionais ou requisições. A CPU atribuída tem cobertura insuficiente para integrá-la retrospectivamente à matriz; nenhuma combinação CPU foi inventada. A instrumentação operacional e a série da feature têm denominadores diferentes.

**Análise derivada:** o replay determinístico foi validado contra os resultados científicos, mas os cruzamentos com retorno operacional e a decomposição EWMA são explicações adicionais, não novos resultados certificados do protocolo. O marcador conservador é definido retrospectivamente e depende das confirmações exploratórias do estudo temporal; não prova equivalência de todas as distribuições a PRE. Não foram recalculados intervalos bootstrap, comparações de significância ou decisões com outro alpha/h. Ausência de indisponibilidade observada não exclui alterações menores de latência ou transporte.

Não se decompôs causalmente o deslocamento tardio de D/F96 em componentes de escalonamento, temperatura, rede ou processamento. O que os dados permitem afirmar é que a feature e sua estatística continuam alteradas em parte das janelas, mesmo após recuperação da disponibilidade. A presença de alarmes tardios não basta para identificar a causa física desse deslocamento.

## 13. Conclusões científicas

1. **As diferenças observadas são consistentes com as implementações congeladas.** Todas as 375.360 linhas de decisão e as métricas por execução foram reproduzidas sem divergências; os 48 grupos agregados conferem. Evidência: [verificacao.json](verificacao.json).
2. **O CoV responde principalmente à transição nestes ataques, e não ao nível sustentado da sobrecarga.** P/B/N detectam F96 em 20/20, mas deixam de alarmar até +5 s; em A3 detectam apenas 3/7/2 eventos. D detecta ambos em 20/20, mas fica silenciosa quando timeouts estabilizam a duração. Evidência: [cov_tempos_alarmes.csv](cov_tempos_alarmes.csv), [analise_cov.csv](analise_cov.csv).
3. **A sensibilidade sustentada depende da relação entre nível, referência e estatística.** N/A3 mantém z médio 1,96, abaixo do hZ=2,50; Z detecta todos os eventos, mas cobre 27,90% das janelas, enquanto EWMA cobre 98,95%. Evidência: [analise_zscore.csv](analise_zscore.csv), [tabela_combinacoes.csv](tabela_combinacoes.csv).
4. **A persistência EWMA após o retorno operacional combina memória e comportamento posterior da feature.** D tem positivas tardias nas 40 execuções; memória anterior ao marcador é necessária em média em 11,0/11,6 cruzamentos A3/F96, e F96 mantém maior duração posterior. Evidência: [analise_ewma.csv](analise_ewma.csv), [features_apos_retorno.csv](features_apos_retorno.csv).
5. **O CUSUM-freeze limita o estado armazenado sem tornar o alarme permanente.** Cada atualização rejeitada preserva S, candidatos continuam sendo avaliados e todas as 160 trajetórias ofensivas retomam negativos. Não há base para declarar ganho sobre CUSUM clássico. Evidência: [cusum_retomadas.csv](cusum_retomadas.csv), [analise_cusum_freeze.csv](analise_cusum_freeze.csv).
6. **Alarmes POST têm significados operacionais distintos.** N/B podem voltar a níveis legítimos antes de terminar a drenagem computacional; D e P podem acompanhar resíduo, e D/F96 mantém alguns alarmes após retorno da disponibilidade. Esses fenômenos não alteram o ground truth oficial ou o FPR L2. Evidência: [alarmes_post_recuperacao.csv](alarmes_post_recuperacao.csv), estudo temporal anterior.
7. **Taxa de detecção de evento isolada esconde diferenças importantes.** Há pares com 20/20 e recall de aproximadamente 2,58% em F96, além de diferenças de FPR e persistência. A interpretação exige distinguir evento detectado, janelas cobertas, latência condicional e alarmes posteriores. Evidência: [tabela_combinacoes.csv](tabela_combinacoes.csv), [alarmes_por_execucao.csv](alarmes_por_execucao.csv).

## 14. Pendências

- A redação do TCC deve escolher uma apresentação consistente para POST: manter a métrica oficial e, se utilizar o corte operacional derivado, identificá-lo como contextual. Não há necessidade de recalcular rótulos ou alterar resultados.
- O termo “freeze” deve ser descrito como rejeição de atualização com preservação do estado anterior; se textos anteriores o tratam como latch permanente, precisam de correção conceitual na redação, sem mudança de código.
- A causa física do pequeno deslocamento tardio de D/F96 não foi isolada. Isso limita atribuições causais específicas, mas não impede explicar as decisões a partir das observações e estados reconstruídos.
- Uma afirmação de benefício relativo ao CUSUM clássico exigiria evidência comparativa apropriada, ausente nesta atividade. Não deve constar como conclusão; nenhum contrafactual foi produzido.

Não foram encontradas inconsistências nas decisões, estados ou agregados científicos examinados. Novas atividades dependem de autorização independente.
