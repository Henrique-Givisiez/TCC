# Investigação da recuperação pós-ataque e da CPU — B1 + B2

## 1. Objetivos e fontes

Investigar a duração HTTP residual de A3 e F96 após 270 s, o atendimento legítimo e a cobertura da característica temporal de CPU. A campanha TEST contém 60 execuções de 390 s, com L2, A3 e F96 em 20 blocos pareados. As fontes são `reports/scientific_campaign_visualization_20261112/processed/{signals,seconds_*,work_*,http_*,docker_*}.csv`, `inventario_execucoes.csv`, os `cpu_quality.json` de cada execução e o código `reports/scientific_campaign_visualization_20261112/scripts/audit.py`. Os hashes SHA-256 das entradas lidas estão em `processed/input_hashes.json`.

As séries `signals.csv` vêm dos CSVs de características da campanha. `seconds_*` integra a fila no tempo, `work_*` conserva submissão, início e fim de cada operação interna, `http_*` conserva início, fim, duração e classificação de cada tentativa HTTP, e `docker_*` conserva os snapshots da CPU da vítima. O script de auditoria anterior verificou a correspondência uma operação por requisição registrada para estas execuções; **as categorias não são intercambiáveis**: a operação é submetida, pode aguardar worker, executa e termina; a tentativa HTTP tem eventos próprios de início e conclusão.

## 2. Metodologia

POST foi subdividido em POST-1 [270,300), POST-2 [300,330), POST-3 [330,360) e POST-4 [360,390). A unidade de cada resumo e contraste é a execução. Cada estimativa por cenário é a média das 20 estimativas por execução; o desvio padrão amostral usa `ddof=1`. `post_por_execucao.csv` registra valores, quantidades de janelas válidas e cobertura por métrica. `post_resumo.csv` registra média, desvio padrão, `n_valid` e cobertura média. Para snapshots, o campo chamado `cpu_snapshot_coverage` é **snapshots válidos por 30 s**, uma frequência relativa que pode superar 1; não é fração de janelas cobertas. Para contagens e fila, a cobertura é integral. L2 não possui tráfego ofensivo; suas contagens ofensivas são zero estrutural.

Pacotes e bytes são somas das 30 janelas; a implementação de extração usa `packet_length` da captura como tamanho do payload TCP registrado. Inícios HTTP são somas por instante de início. `mean_duration_ms` é a **média das 30 médias de janelas com conclusões**, incluindo tentativas malsucedidas; cada média de janela usa a duração das tentativas concluídas nela. Não é uma média direta por requisição. `waiting_mean` é a média temporal integrada da fila. A fração com dois workers é integrada exatamente dos intervalos de execução de `work_*`. `waiting_max_exact` é o máximo nos eventos e no limite esquerdo. CPU da característica é média simples das janelas válidas; CPU dos snapshots é média simples dos snapshots válidos recebidos no intervalo.

`http_por_execucao.csv` define mediana, p95, 2xx, timeout e outros erros pela **coorte de início** em cada intervalo. A coluna `completed` conta, separadamente, conclusões no intervalo e pode incluir requisições iniciadas antes. `active_started_post_completed` cruza início em ACTIVE e conclusão no intervalo POST. Os registros desta campanha têm fim observado; a metodologia não classifica uma requisição sem conclusão observada como timeout.

Contrastes `A3 − L2`, `F96 − L2` e `A3 − F96` foram calculados dentro de cada um dos 20 blocos. O IC bilateral de 95% é média ± `t(0,975; n−1) × s/√n`, com `n` pares válidos. Trata-se de IC t pareado descritivo; não há ajuste por múltiplas comparações. Janelas não entram como unidades independentes.

Critério de recuperação da fila, definido antes de examinar POST: o percentil 95 dos 120 valores de `waiting_mean` de PRE, com piso de 1 operação, é o limiar individual. Recuperação é o primeiro segundo de POST que inicia dez segundos consecutivos com `waiting_mean` abaixo ou igual ao limiar. Ausência até 390 s seria censura à direita; não houve casos censurados por esse critério. Ele mede aproximação ao nível de PRE, não ausência absoluta de espera nem recuperação da latência.

## 3. Recuperação pós-ataque

As médias abaixo são entre execuções. Os detalhes de **todos** os indicadores, incluindo pacotes, bytes, inícios e conclusões por classe e máximos da fila, estão em `post_resumo.csv` e `post_por_execucao.csv`.

| Intervalo | Cenário | Duração de conclusão (ms) | Fila média (operações) | Dois workers (fração) | Inícios HTTP |
|---|---:|---:|---:|---:|---:|
| POST-1 | L2 | 43,01 | 0,04 | 0,09 | 479,95 |
| POST-1 | A3 | 1.985,87 | 491,55 | 0,99 | 480,30 |
| POST-1 | F96 | 616,73 | 67,78 | 0,37 | 480,25 |
| POST-2 | L2 | 42,65 | 0,04 | 0,08 | 469,75 |
| POST-2 | A3 | 552,16 | 77,41 | 0,32 | 469,85 |
| POST-2 | F96 | 45,84 | 0,04 | 0,10 | 469,85 |
| POST-3 | L2 | 43,30 | 0,04 | 0,09 | 488,70 |
| POST-3 | A3 | 43,95 | 0,04 | 0,09 | 488,75 |
| POST-3 | F96 | 46,48 | 0,04 | 0,10 | 489,05 |
| POST-4 | L2 | 42,80 | 0,04 | 0,09 | 466,75 |
| POST-4 | A3 | 43,14 | 0,04 | 0,09 | 467,00 |
| POST-4 | F96 | 45,83 | 0,04 | 0,10 | 467,50 |

Os inícios voltam ao mesmo patamar nominal nos três cenários, enquanto as conclusões ainda refletem trabalho acumulado. A3 conserva fila e ocupação altas em POST-1 e parte de POST-2. F96 esvazia a fila no início de POST-1. As durações de POST-3 e POST-4 ficam próximas das de L2; pequenas diferenças persistem, mas não sustentam uma narrativa de grande degradação residual até 390 s.

## 4. Contrastes pareados

| Intervalo | Indicador | A3 − F96 (IC 95%) | A3 − L2 (IC 95%) | F96 − L2 (IC 95%) |
|---|---|---:|---:|---:|
| POST-1 | Duração HTTP (ms) | 1.369,14 [1.292,17; 1.446,10] | 1.942,86 [1.905,03; 1.980,69] | 573,72 [503,81; 643,63] |
| POST-1 | Fila média | 423,77 [380,64; 466,91] | 491,51 [446,60; 536,42] | 67,74 [49,38; 86,10] |
| POST-1 | Dois workers | 0,62 [0,58; 0,66] | 0,90 [0,88; 0,92] | 0,28 [0,25; 0,31] |
| POST-1 | CPU snapshots (%) | 97,16 [90,67; 103,65] | 158,46 [155,61; 161,31] | 61,30 [55,41; 67,18] |
| POST-2 | Duração HTTP (ms) | 506,32 [343,84; 668,79] | 509,51 [347,05; 671,97] | 3,19 [2,75; 3,62] |
| POST-2 | Fila média | 77,37 [42,91; 111,84] | 77,38 [42,91; 111,84] | 0,00 [0,00; 0,01] |
| POST-2 | Dois workers | 0,23 [0,15; 0,30] | 0,24 [0,16; 0,31] | 0,01 [0,01; 0,01] |
| POST-2 | CPU snapshots (%) | 44,34 [30,68; 58,00] | 49,03 [35,35; 62,71] | 4,69 [4,02; 5,37] |

Todos esses contrastes têm 20 pares válidos. As 156 linhas de `contrastes_pareados.csv` incluem os quatro intervalos e os 13 indicadores, com média, desvio padrão, `n` e IC; `contrastes_por_bloco.csv` contém cada diferença. Em POST-3 e POST-4, a diferença A3 − F96 na duração é aproximadamente −2,5 a −2,7 ms, de magnitude pequena frente às diferenças iniciais.

## 5. Acúmulo de operações

No instante 270 s, A3 tinha em média 185,5 operações ofensivas e 361,9 legítimas aguardando; 1,75 ofensivas e 0,25 legítimas em execução. F96 tinha 304,6 ofensivas e 100,85 legítimas aguardando; 1,35 ofensivas e 0,65 legítimas em execução. Portanto, a fila ofensiva inicial do F96 era maior, mas a fila **legítima** do A3 era muito maior. Em 300 s, a fila do A3 ainda tinha 9,2 ofensivas e 348,95 legítimas; F96 tinha zero ofensivas e 0,05 legítimas em média. Em 330 s, ambas as filas estão próximas de zero. Valores por execução e classe constam em `filas_instantes_por_execucao.csv`.

Há operações ofensivas iniciadas em ACTIVE ainda executando em 270 s: média de 1,75 no A3 e 1,35 no F96. Também há operações legítimas atravessando a fronteira, em espera e em execução. A média do tempo até recuperação da fila pelo critério definido é 38,2 s após 270 s no A3 (DP 5,9; faixa 25–48 s) e 9,5 s no F96 (DP 2,4; faixa 7–17 s). Todas as 20 execuções por cenário atingiram o critério. A fila não equivale a requisições HTTP concluídas; cruzamentos de início e fim são contados separadamente.

## 6. Atendimento legítimo

| Cenário | Intervalo | Inícios legítimos | Conclusões legítimas | Mediana da coorte (ms) | p95 da coorte (ms) | 2xx da coorte | Timeouts da coorte |
|---|---|---:|---:|---:|---:|---:|---:|
| L2 | POST-1 | 479,95 | 480,60 | 35,31 | 76,53 | 100% | 0 |
| A3 | POST-1 | 480,30 | 479,00 | 2.004,71 | 2.005,91 | 2% | 470,20 |
| F96 | POST-1 | 480,25 | 511,55 | 93,90 | 2.005,45 | 79% | 99,45 |
| A3 | POST-2 | 469,85 | 502,15 | 150,05 | 1.592,09 | 81% | 91,25 |
| F96 | POST-2 | 469,85 | 469,80 | 39,43 | 81,15 | 100% | 0 |
| A3 | POST-3 | 488,75 | 489,05 | 36,23 | 77,86 | 100% | 0 |

Cada número é a média das estatísticas de 20 execuções, com detalhes e DP auditáveis em `http_por_execucao.csv` (o CSV de resumo por execução permite calculá-los). Inícios e mediana/p95/2xx/timeouts são da coorte de início; conclusões são por instante de fim e podem conter outras coortes. Em POST-1, por execução, cerca de 31,75 tentativas legítimas iniciadas em ACTIVE terminam no A3 e 31,80 no F96; também terminam 15,95 ofensivas no A3 e 95,95 no F96. No POST-2 não há conclusões de coortes iniciadas em ACTIVE. A degradação residual do A3 **atinge diretamente os clientes legítimos**, inclusive com timeouts; não é um artefato produzido apenas pela mistura de tráfego ofensivo no agregado.

## 7. Auditoria da CPU

`simulator/stats_collector.py` agenda snapshots da vítima a cada 1 s; `simulator/cpu_observations.py` calcula `Δtotal_usage / Δsystem_cpu_usage × online_cpus × 100` a partir de contadores Docker e exige leitura de referência. Pode superar 100% em um processo que usa mais de um núcleo. `experiments/cpu_features.py` associa **um delta inteiro** a uma janela de 1 s se ambos os brackets de aquisição estiverem a até 0,05 s das fronteiras nominais, o snapshot chegar até o fechamento da janela e houver um único candidato. Não há interpolação ou preenchimento com zero. `cpu_quality.json` registra rejeições; o primeiro snapshot não tem delta válido.

| Cenário | Fase | Cobertura média da série | Snapshots válidos por execução (média) | CPU série (%) | CPU snapshots (%) |
|---|---|---:|---:|---:|---:|
| L2 | PRE | 90% | 119,70 | 52,55 | 52,44 |
| A3 | PRE | 91% | 119,75 | 52,88 | 52,93 |
| F96 | PRE | 91% | 119,85 | 53,01 | 53,05 |
| L2 | ACTIVE | 76% | 120,05 | 50,80 | 51,23 |
| A3 | ACTIVE | 56% | 119,85 | 212,21 | 212,03 |
| F96 | ACTIVE | 23% | 119,20 | 233,15 | 235,66 |
| L2 | POST | 70% | 120,05 | 51,88 | 51,98 |
| A3 | POST | 54% | 120,00 | 93,75 | 104,19 |
| F96 | POST | 16% | 120,25 | 60,86 | 70,72 |

Em ACTIVE/POST, o F96 teve respectivamente 845/1.284 rejeições por alinhamento insuficiente e 998/743 por chegada após o fechamento, somadas nas 20 execuções. A3 teve 114/262 por alinhamento e 932/841 por atraso. Os snapshots continuam próximos de um por segundo: a queda de cobertura da característica decorre principalmente da **regra conservadora de atribuição temporal**, combinada com mudança na cadência efetiva e no tempo de aquisição/recebimento sob os cenários, não da ausência maciça de snapshots. A associação entre carga e rejeições é observável; a causa física das mudanças de temporização não foi isolada experimentalmente.

A seleção altera médias: no POST completo, a média por execução da série é 93,75% no A3 e 60,86% no F96, contra 104,19% e 70,72% nos snapshots. As diferenças médias série menos snapshots são −10,45 e −9,86 pontos percentuais. Isso constitui evidência de **viés de seleção temporal** nas janelas aceitas em POST; não estabelece um viés universal da instrumentação. A representação dos snapshots tem melhor cobertura, mas é média por snapshot, não integral temporal exata. Ambas são percentuais Docker multicore.

**Recomendação para a seção 5.3:** ao discutir as características temporais e a disponibilidade para detectores, usar `mean_cpu_percent` com cobertura explícita, nunca imputada; não tratar CPU como sinal científico elegível dos detectores definitivos. Para impacto na infraestrutura, usar os snapshots originais `docker_*` e declarar a média por snapshot. A figura B2 visualiza por que essas duas fontes não devem ser confundidas.

## 8. Interpretação científica e limites

**Observações demonstradas.** O A3 apresenta maior duração de conclusão, fila, ocupação de dois workers, CPU e timeouts legítimos em POST-1 e POST-2. Ambos os cenários retornam a números semelhantes de novas requisições. A fila do F96 volta ao patamar de PRE antes da do A3 pelo critério operacional. A3 e F96 têm padrões distintos de recuperação, com convergência aproximada em POST-3. A cobertura da CPU temporal varia por cenário e fase apesar de snapshots frequentes.

**Interpretação sustentada.** A permanência de operações aguardando, sobretudo legítimas, e a saturação dos workers acompanham a degradação de duração no A3. O perfil de trabalho computacional do A3 é compatível com menor vazão de esvaziamento da fila; a recuperação do atendimento legítimo acompanha a queda da fila. O F96 acumula mais operações ofensivas no limite 270 s, mas as libera muito mais cedo. A série agregada de duração inclui timeouts, por isso deve ser lida junto das coortes legítimas.

**Hipóteses não verificadas.** A contribuição causal isolada do custo de CPU de cada operação para a diferença A3–F96, o papel exato da política de escalonamento, e o mecanismo físico de atraso dos snapshots não foram identificados por intervenção ou rastreamento de baixa camada. A correlação temporal, por si, não prova causalidade.

**Limitações.** O horizonte acaba em 390 s; o critério de recuperação depende de uma janela de dez segundos e de um limiar de PRE. O IC t com 20 blocos descreve incerteza entre execuções pareadas e não corrige múltiplos desfechos. Médias de janela, médias por tentativa e médias por snapshot usam pesos distintos. O p95 é calculado por execução e depois resumido, sem juntar requisições de execuções diferentes. Não houve comparação causal controlada entre mecanismos além dos cenários pareados do protocolo. A investigação é suplementar e não altera resultados oficiais.

## 9. Figuras e rastreabilidade

- `figures/b1_a_recuperacao.{png,pdf}`: médias por execução em blocos de 5 s da duração de conclusão (`signals.csv`), da espera integrada (`seconds_*`) e da ocupação exata (`work_*`); bandas ±1,96 erro padrão entre 20 execuções, calculadas de `tracos_5s_por_execucao.csv`.
- `figures/b1_b_legitimo.{png,pdf}`: mediana por execução das coortes legítimas iniciadas em cada bloco de 5 s (`http_*`), com a mesma banda; fonte `tracos_5s_por_execucao.csv`.
- `figures/b2_cpu_cobertura.{png,pdf}`: cobertura da série temporal (`signals.csv`) e frequência relativa de snapshots válidos (`docker_*`), de `cpu_cobertura_por_execucao_fase.csv`.

Todas indicam o fim do ataque em 270 s; na B2, a marca é a fronteira ACTIVE/POST. Os CSVs e scripts desta pasta permitem reproduzir as figuras e verificar as fontes.
