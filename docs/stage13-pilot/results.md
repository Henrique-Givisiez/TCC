# Resultados do piloto experimental — Etapa 13

**Piloto de desenvolvimento, não avaliação científica definitiva. Sem thresholds, decisões, ranking ou eficácia.**

## Execução e desenho

Plano prévio em [design.md](design.md). Operação /medium para todos os clientes, quatro sources benignas ×2 RPS, um atacante ×8 RPS durante atividade. Containers → NGINX → uma vítima, dois workers, autoscaling desligado, timeout 2 s e Δ=1 s. PRE=24 s, evento planejado=36 s, POST=24 s; total 84 s. Periódico: burst 2 s/período 6 s, duty 1/3, seis ciclos. CoV L=3/6/12 somente de desenvolvimento.

Concluídos 15 runs, 15 elegíveis, 0 falhas/inelegíveis. Seeds 101,211,307,401,503, cada uma pareada B/C/P; ordem predeclarada e parcialmente contrabalançada. Nenhuma micrograde/intensidade adicional foi necessária após a primeira tríade.

Todos os cenários passaram exportação Stage 8, validação Stage 9 e extração Stage 10. Config canônica só varia nos fatores previstos; IDs das imagens são iguais dentro e entre seeds e foram confrontados com backends/sources reais. Proveniência e hashes estão preservados. Isso prova comparabilidade nominal, não identidade de carga de host, timing ou chegadas realizadas.

| Seed | Cenário | Run ID | Status/elegível | Requests benignas/ataque | Falhas | Lifecycle (s) | Última observação (s) |
|---|---|---|---|---|---|---|---|
| 101 | B | `8636cd42ccf84dcda66b050cc8d99824` | completed/sim | 686/0 | 0 | 97.36 | 84.04 |
| 101 | C | `bc12d7b48a8c4ffd83407ec2671ae156` | completed/sim | 685/293 | 0 | 98.38 | 84.01 |
| 101 | P | `a807f19b0dee4b2eb0cc88a17b1b873e` | completed/sim | 685/102 | 0 | 98.33 | 84.01 |
| 211 | B | `91a1f8050d30412299fc7be53cc0d05d` | completed/sim | 643/0 | 0 | 97.08 | 84.01 |
| 211 | C | `31d60ad4934e4a71b38276155361339d` | completed/sim | 642/278 | 0 | 98.33 | 84.01 |
| 211 | P | `dd9856abc2a9411ca322c732552501c4` | completed/sim | 642/97 | 0 | 99.5 | 84.01 |
| 307 | B | `bdbce59a4ba848c2a3988d8058a0ec31` | completed/sim | 704/0 | 0 | 97.02 | 84.01 |
| 307 | C | `82a690f332e14f3bb6ed66348fac386a` | completed/sim | 704/263 | 0 | 98.58 | 84.06 |
| 307 | P | `13edfe9395bb4c3c9c6c965e89be2928` | completed/sim | 704/91 | 0 | 98.41 | 84.01 |
| 401 | B | `30e8ee84abf84f4faa554f8cacdf9e72` | completed/sim | 729/0 | 0 | 97.2 | 84.05 |
| 401 | C | `4a973970b9b64c3ba0a24a469b22bd31` | completed/sim | 728/348 | 0 | 98.5 | 84.01 |
| 401 | P | `6aeb69a3fb084b7aa1bd8f6b16d30d0c` | completed/sim | 728/127 | 0 | 99.58 | 84.01 |
| 503 | B | `983ff9fa88344b5499a5ffcc6dc6b610` | completed/sim | 684/0 | 0 | 97.06 | 84 |
| 503 | C | `9755e84b40034f2c900a670271f16159` | completed/sim | 684/281 | 0 | 98.5 | 84.01 |
| 503 | P | `a99962874b6b4963b2128d9d68ff50bb` | completed/sim | 684/91 | 0 | 98.48 | 84.01 |

## Variabilidade entre seeds

A unidade desta tabela é a **média de cada run durante [24,60)**, com cinco runs por célula. Não são centenas de janelas independentes. As médias de duração são médias de médias Stage 10, sem ponderação por número de requests. CV descritivo = desvio das cinco médias dividido pela média delas; não é o detector CoV. Quantis usam interpolação linear em (n−1)q. Nulls excluídos apenas do cálculo descritivo, com suporte explícito nos CSVs, sem alterar dados.

| Feature | Cenário | Média entre runs | SD entre runs | Mediana | Min–max | CV descritivo |
|---|---|---|---|---|---|---|
| ingress_packet_count | B | 19.06 | 0.5183 | 19.06 | 18.44–19.83 | 0.02719 |
| ingress_tcp_payload_length_sum_bytes | B | 1581 | 57.57 | 1584 | 1519–1655 | 0.03641 |
| request_starts | B | 8.067 | 0.2937 | 8.083 | 7.75–8.444 | 0.03641 |
| mean_duration_ms | B | 34.34 | 1.09 | 34.79 | 32.8–35.3 | 0.03173 |
| mean_cpu_percent | B | 18.37 | 0.598 | 18.19 | 17.78–19.18 | 0.03256 |
| ingress_packet_count | C | 41.42 | 2.869 | 40.97 | 37.92–45.75 | 0.06926 |
| ingress_tcp_payload_length_sum_bytes | C | 3174 | 189.3 | 3131 | 2951–3474 | 0.05965 |
| request_starts | C | 16.19 | 0.9661 | 15.97 | 15.06–17.72 | 0.05965 |
| mean_duration_ms | C | 38.92 | 0.4462 | 39.07 | 38.19–39.39 | 0.01146 |
| mean_cpu_percent | C | 34.01 | 1.9 | 34.39 | 31.32–36.07 | 0.05586 |
| ingress_packet_count | P | 27.01 | 1.384 | 27.14 | 25.11–28.94 | 0.05123 |
| ingress_tcp_payload_length_sum_bytes | P | 2139 | 98.26 | 2145 | 2014–2281 | 0.04594 |
| request_starts | P | 10.91 | 0.5013 | 10.94 | 10.28–11.64 | 0.04594 |
| mean_duration_ms | P | 35.83 | 0.9637 | 35.84 | 34.25–36.7 | 0.0269 |
| mean_cpu_percent | P | 24.36 | 1.161 | 24.67 | 22.57–25.66 | 0.04766 |

Detalhes de todas as fases, nulls, quantis e blocos PRE/POST em `analysis/features_by_run_phase.csv`, `features_by_run_block.csv` e `between_seeds.csv`. Comparações por blocos são descritivas, sem teste de significância ou descarte de startup.

## Baselines e Z-score

25 modelos de baseline único (cinco features × cinco benignos) documentam variação de μ/σ. Scoring cross-fit usa baseline B de OUTRA seed por rotação predefinida: 101←503,211←101,307←211,401←307,503←401. É retrospectivo e exploratório, não valida treinamento cronologicamente anterior ao teste. Nenhum atacado ou próprio run serve ao seu fitting. Outro ramo ajusta cinco modelos usando apenas B101+B211 e pontua 307/401/503; todos permanecem piloto, mas essa ramificação ilustra seeds disjuntas.

Fitting preserva todas as observações válidas da série completa, inclusive cauda; isso é o contrato existente e não foi silenciosamente substituído por um baseline recortado. A influência da cauda e do startup é uma limitação metodológica a resolver antes da campanha. μ/sigma abaixo são dos artefatos realmente usados, com ddof=1, parâmetros exatos auditáveis e nulls contados.

| Feature | Parâmetro | Média entre seeds | SD | Min–max | CV descritivo |
|---|---|---|---|---|---|
| ingress_packet_count | mu | 19.53 | 1.29 | 17.64–20.85 | 0.06605 |
| ingress_packet_count | sigma | 7.949 | 0.4976 | 7.279–8.466 | 0.06259 |
| ingress_tcp_payload_length_sum_bytes | mu | 1589 | 72.69 | 1483–1681 | 0.04574 |
| ingress_tcp_payload_length_sum_bytes | sigma | 611.1 | 35.23 | 554.3–650.6 | 0.05765 |
| request_starts | mu | 8.108 | 0.3709 | 7.565–8.576 | 0.04574 |
| request_starts | sigma | 3.13 | 0.157 | 2.886–3.319 | 0.05017 |
| mean_duration_ms | mu | 34.04 | 1.521 | 31.57–35.76 | 0.0447 |
| mean_duration_ms | sigma | 6.232 | 0.6112 | 5.462–6.828 | 0.09808 |
| mean_cpu_percent | mu | 18.51 | 0.9485 | 16.97–19.3 | 0.05123 |
| mean_cpu_percent | sigma | 6.652 | 0.7261 | 5.873–7.501 | 0.1092 |

## CoV: sensibilidade temporal, sem escolha de L

Cada score usa L observações consecutivas, incluindo a atual. Null reinicia histórico; o warm-up é consequência metodológica, não negativo/zero. As médias abaixo são resumos dos cinco runs e não um ranking. O próprio objeto medido muda com L: misturar fases no histórico pode elevar ou sustentar o CoV, em vez de simplesmente suavizar. Não há método acumulativo adicional neste piloto.

| Feature | Cenário | L dev | Média dos scores médios por run | Janelas sem score no evento |
|---|---|---|---|---|
| request_starts | B | 3 | 0.356 | 0 |
| request_starts | B | 6 | 0.3846 | 0 |
| request_starts | B | 12 | 0.3924 | 0 |
| request_starts | C | 3 | 0.2389 | 0 |
| request_starts | C | 6 | 0.269 | 0 |
| request_starts | C | 12 | 0.3073 | 0 |
| request_starts | P | 3 | 0.4209 | 0 |
| request_starts | P | 6 | 0.5031 | 0 |
| request_starts | P | 12 | 0.4987 | 0 |
| mean_cpu_percent | B | 3 | 0.2569 | 0 |
| mean_cpu_percent | B | 6 | 0.3286 | 0 |
| mean_cpu_percent | B | 12 | 0.3625 | 0 |
| mean_cpu_percent | C | 3 | 0.1733 | 0 |
| mean_cpu_percent | C | 6 | 0.2186 | 0 |
| mean_cpu_percent | C | 12 | 0.2633 | 0 |
| mean_cpu_percent | P | 3 | 0.3364 | 0 |
| mean_cpu_percent | P | 6 | 0.4304 | 0 |
| mean_cpu_percent | P | 12 | 0.4583 | 0 |

## Inspeção temporal

Seed diagnóstica 307 foi escolhida por posição central na lista prévia, não por resultado. `analysis/diagnostic_seed307.csv` mostra todas as cinco features, Z-score/CoV, PRE→evento→POST, fase programada de burst/silêncio, overlap e attack_request_starts. Abertura de labels é bloqueada durante TODO fitting/scoring; esses campos são acrescentados só depois, pelo adaptador diagnóstico/evaluator. Não redefinimos attack_active nem criamos burst_active.

O calendário programado é auxiliar e não prova emissão. Os seis bursts por seed tiveram as seguintes contagens realizadas; o evento global inclui os silêncios e seus efeitos/conclusões.

| Seed | Starts por burst P | Total atacante P | Total atacante C |
|---|---|---|---|
| 101 | 20,13,18,19,19,13 | 102 | 293 |
| 211 | 18,11,17,16,16,19 | 97 | 278 |
| 307 | 17,22,21,13,7,11 | 91 | 263 |
| 401 | 24,15,20,23,16,29 | 127 | 348 |
| 503 | 16,13,18,12,15,17 | 91 | 281 |

| Método | L dev | Janela | Fase programada | Feature | Score | Overlap pós-hoc | Starts atacantes pós-hoc |
|---|---|---|---|---|---|---|---|
| zscore_crossfit |  | [23,24) | not_applicable | 12 | 1.392 | 0 | 0 |
| zscore_crossfit |  | [24,25) | burst | 17 | 2.961 | 0.9722 | 8 |
| zscore_crossfit |  | [25,26) | burst | 15 | 2.333 | 1 | 9 |
| zscore_crossfit |  | [26,27) | silence | 9 | 0.4504 | 1 | 0 |
| zscore_crossfit |  | [29,30) | silence | 10 | 0.7643 | 1 | 0 |
| zscore_crossfit |  | [30,31) | burst | 20 | 3.903 | 1 | 13 |
| zscore_crossfit |  | [31,32) | burst | 17 | 2.961 | 1 | 9 |
| zscore_crossfit |  | [32,33) | silence | 7 | -0.1772 | 1 | 0 |
| zscore_crossfit |  | [59,60) | silence | 10 | 0.7643 | 1 | 0 |
| zscore_crossfit |  | [60,61) | not_applicable | 5 | -0.8049 | 0.002043 | 0 |
| zscore_crossfit |  | [65,66) | not_applicable | 6 | -0.491 | 0 | 0 |
| zscore_crossfit |  | [72,73) | not_applicable | 8 | 0.1366 | 0 | 0 |
| zscore_crossfit |  | [83,84) | not_applicable | 8 | 0.1366 | 0 | 0 |
| cov | 6 | [23,24) | not_applicable | 12 | 0.3697 | 0 | 0 |
| cov | 6 | [24,25) | burst | 17 | 0.3827 | 0.9722 | 8 |
| cov | 6 | [25,26) | burst | 15 | 0.2648 | 1 | 9 |
| cov | 6 | [26,27) | silence | 9 | 0.2996 | 1 | 0 |
| cov | 6 | [29,30) | silence | 10 | 0.3147 | 1 | 0 |
| cov | 6 | [30,31) | burst | 20 | 0.3837 | 1 | 13 |
| cov | 6 | [31,32) | burst | 17 | 0.3994 | 1 | 9 |
| cov | 6 | [32,33) | silence | 7 | 0.4378 | 1 | 0 |
| cov | 6 | [59,60) | silence | 10 | 0.6646 | 1 | 0 |
| cov | 6 | [60,61) | not_applicable | 5 | 0.7294 | 0.002043 | 0 |
| cov | 6 | [65,66) | not_applicable | 6 | 0.4676 | 0 | 0 |
| cov | 6 | [72,73) | not_applicable | 8 | 0.294 | 0 | 0 |
| cov | 6 | [83,84) | not_applicable | 8 | 0.4041 | 0 | 0 |

## Custo medido

| Medida | Resultado |
|---|---|
| Tempo nominal total | 1260 s (21.00 min) |
| Lifecycle somado | 1472.29 s |
| Wall somado execução + Stage 8–10 | 1475.45 s |
| Intervalo primeiro início→último fim (inclui pausas) | 1563.56 s |
| Armazenamento raw | 54.71 MiB |
| Armazenamento datasets | 55.90 MiB |
| Armazenamento features | 1.20 MiB |
| Armazenamento validation | 0.51 MiB |
| Análise de scores/estatísticas | 5.33 s wall, 4.63 s CPU do processo |
| Pico RSS da análise | 41.14 MiB |
| Armazenamento piloto antes do relatório/auditoria | 118.56 MiB |
| Armazenamento análise antes do summary | 5.85 MiB |

Média observada ≈98.36 s e 7.49 MiB por run para raw+dataset+features+validation. Uma extrapolação linear de R runs semelhantes custa ≈R×esses valores, antes de pausas, falhas, armazenamento de scores e mudanças de duração. Matriz científica normal-only training/calibration mais tríades de teste tem R=n_B+n_C+3n_T, não necessariamente todas as combinações em todas as fases. Raw e Stage 8 duplicam parte da evidência por contrato; nenhum foi apagado.

## Repetições: sensibilidade de planejamento, não N final

As curvas 1→5 seeds estão em incremental_convergence.csv; a ordem é fixa e um aparente platô não prova convergência. A tabela abaixo usa médias benignas por run no período planejado, calcula SD entre runs e ilustra n≈(1,96·s/(r·média))² para semi-amplitudes relativas r. É uma aproximação normal otimista de planejamento, não IC garantido, recomendação final ou correção da incerteza da variância estimada com cinco seeds. A quantidade mínima algébrica exibida é duas; isso não significa que duas sejam cientificamente suficientes. Quantis t/planejamento conservador, blocos de host e um piloto normal maior podem aumentar o necessário.

| Feature | n ilustrativo: r=10% | r=5% | r=2% |
|---|---|---|---|
| ingress_packet_count | 2 | 7 | 42 |
| ingress_tcp_payload_length_sum_bytes | 2 | 4 | 20 |
| request_starts | 2 | 4 | 20 |
| mean_duration_ms | 2 | 4 | 20 |
| mean_cpu_percent | 2 | 5 | 26 |

Para fechar N é preciso escolher precisão e endpoint principal. Esses cálculos dimensionam médias, não recall de eventos, delay ou falsos alarmes raros. Estes últimos precisam eventos/exposição próprios e só poderão ser planejados após protocolo de decisão. Não se deve tratar as janelas correlacionadas ou os três cenários pareados como novas seeds. Não foi usado bootstrap/IC forte com esta amostra pequena.

## Separação e calibração a estudar

A: runs distintos é obrigatório, mas reutilizar seed em baseline/calibration/test pode repetir o mesmo fluxo e subestimar generalização; reexecuções da mesma seed são úteis para variabilidade do sistema, não substituem seeds novas. B: preferir conjuntos de seeds disjuntos por papel, **também com runs fisicamente independentes**. A partição 101/211→307→401/503 é ilustrativa e já foi inspecionada; não será reaproveitada como teste cego. Campanha definitiva usará dados novos, baseline/calibration normais, testes B/C/P pareados dentro de cada seed de teste e ambiente compatível. A comparação de padrões deverá explicitar o efeito de duty cycle/carga média e das políticas de admissão já existentes.

Quantis de scores benignos de calibração são viáveis como alternativa empírica, com orientação/cauda explícita e diagnóstico de dependência; média+kσ permite uma família simples, mas k não foi escolhido e caudas não são necessariamente gaussianas. Limite teórico de Z-score requer hipóteses e parâmetros estimados não geram automaticamente N(0,1); não há justificativa automática para |z|>3. CoV não tem limite universal independente de L, taxa e distribuição. Controle de FPR máximo deve ser estimado/confirmado em calibração normal independente, com intervalo e exposição suficientes; FPR/janela não equivale a episódios por hora. Uma única seed de calibração de 84 s dá cauda pobre, agravada por scores CoV sobrepostos. Os quantis em benign_calibration_score_distributions.csv são apenas descrições, não thresholds ou decisões.

## Limitações e próximos passos

Leitura substantiva e decisões pendentes em [interpretation.md](interpretation.md). Nenhuma eficácia é inferida destas tabelas. Todas as cinco candidatas continuam justificadas por observabilidade; qualquer redução deve ser por custo/suporte/redundância e hipótese, não maximização em labels do piloto.

Event-level: Stage 8 tem actual_start/actual_end e IDs em attack_events.csv, auditados em event_timing_and_counts.json. Stage 10 v1 só tem overlap da união e starts auxiliares; não preserva identidade/intervalos individuais para ligar cada decisão a um evento. Logo falta **o vínculo verificável do evaluator com intervalos efetivos**, não necessariamente dado bruto inexistente. Não calculamos detection delay e não alteramos Stage 10.

Foram adicionados pilot_stage13/{__init__,run,batch,analyze,truth,audit,report}.py, tests/test_stage13_pilot.py, docs/stage13-pilot/* e experiment_results/stage13-pilot/*. Nenhum arquivo preexistente de Etapas 0–12 foi alterado. O snapshot verificou 3923 arquivos por SHA/mtime e 1520 entradas dos manifests novos. Uma correção técnica no helper de comparação do runner (to_json em vez de API inexistente to_dict), sem alteração de config/simulação, tem versões arquivadas e revisão registrada no plano. Nenhum run foi descartado/regerado para esconder falha. Após a coleta, foi adicionado apenas um guard de reexecução antes de qualquer escrita; o runner usado na coleta e o plano original foram preservados por hash. O código atual não retoma/estende um plano cuja identidade de runner mudou. Reproduzir em diretório de campanha novo exige novo plano, sem sobrescrever este piloto.

A suíte final passou com 254 testes, incluindo cinco novos testes de desenho, quantis, regiões e proteção contra reexecução com overwrite. Não houve commit.
