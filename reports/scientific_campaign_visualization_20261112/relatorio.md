# Visualização da campanha científica definitiva

## Inventário e escopo

Campanha: `experiment_results/scientific-energy-powersaver-20261109`. Plano congelado: `experiments/protocols/energy-powersaver-20261109/plan.json`. Foram localizadas e auditadas **80 execuções concluídas**: 4 BASELINE, 8 CAL_A, 8 CAL_B e 60 TEST. TEST contém 20 blocos de três cenários (L2, A3, F96); o pareamento é o campo `block` do plano, com seeds e ordem registrados. Não se parearam execuções por ordem de arquivo.

| Etapa | L2 | A3 | F96 | Total |
|---|---:|---:|---:|---:|
| BASELINE | 4 | 0 | 0 | 4 |
| CAL_A | 8 | 0 | 0 | 8 |
| CAL_B | 8 | 0 | 0 | 8 |
| TEST | 20 | 20 | 20 | 60 |

Duração efetiva configurada: 390 s. WARMUP [0,30), PRE [30,150), ataque [150,270) e POST [270,390). L2 não contém ataque. A3 usa duas fontes ofensivas a 4 RPS cada em `/expensive`; F96 usa duas a 32 RPS cada em `/medium`, com concorrência ofensiva 96. O tráfego legítimo usa duas fontes a 8 RPS cada em `/medium`. A coleta é direta e a vítima possui dois workers.

## Sinais e implementação real dos detectores

As cinco séries extraídas são pacotes TCP de entrada, soma do payload TCP de entrada, inícios HTTP, duração média HTTP e CPU média do contêiner em janelas de 1 s. **Somente os quatro primeiros sinais integram a matriz oficial de detectores.** A CPU é descritiva no protocolo congelado; não foram inventadas decisões detector × CPU. O campo de bytes é soma de payload TCP de entrada, não bytes totais no fio.

- **Z-Score:** valor padronizado assinado `(x−μ)/σ` contra BASELINE independente, com `ddof=1`; valor ausente torna o score indisponível. Alarme quando score supera o limiar CAL_A.
- **CoV:** desvio padrão amostral dividido pela média aritmética de seis observações consecutivas, incluindo a atual; ausência reinicia a janela. Média zero ou aquecimento tornam o score indisponível. Alarme quando CoV supera seu limiar.
- **EWMA:** média exponencial dos resíduos padronizados pelo BASELINE congelado, λ=0,2, estado inicial zero; ausência reinicia o estado. Alarme de cauda superior acima do limiar.
- **CUSUM-freeze:** candidato `max(0, estado anterior + z − 0,5)`. Se candidato > h, emite alarme e **preserva o estado anterior**; não acumula o candidato rejeitado. Em empate com h, aceita a atualização e não alarma. Ausência reinicia a zero. As figuras separam candidato, estado posterior, limiar e decisão.

As decisões são por janela. Um trecho com várias janelas em alarme não significa vários eventos ofensivos independentes. As figuras usam os scores e alarmes dos manifests TEST oficiais; não executam detectores novamente.

## Calibração e avaliação

BASELINE ajustou as referências; CAL_A selecionou os limiares; CAL_B verificou os pares método × sinal; TEST avaliou configurações congeladas. Os 16 pares nos quatro sinais elegíveis constam da liberação científica. Figuras de calibração usam somente BASELINE/CAL_A/CAL_B. As métricas TEST são importadas dos manifests oficiais, incluindo detecção por evento, FPR PRE, positividade POST, cobertura e latência observada. A disponibilidade operacional ACTIVE corresponde à fração oficial de respostas 2xx dentro do prazo da fase (`timely_2xx / starts`), calculada dos journals reconciliados; difere da fração de respostas 2xx eventualmente concluídas no log HTTP. Latência é mostrada apenas para eventos detectados, sempre acompanhada da taxa de detecção. FPR total pode ser indefinido nas execuções ofensivas; PRE e POST são apresentados com nomes próprios, sem reclassificação retrospectiva.

## Rastreabilidade temporal e infraestrutura

O instante de cada score/alarme é o fechamento da janela (`window_end_seconds`), conforme o manifesto oficial. A disponibilidade é simulada pelo fechamento da janela ou disponibilidade explicitamente registrada, não tempo medido de processamento do detector. Requisições são atribuídas à coorte pelo início HTTP; respostas e timeouts por seu encerramento nas séries temporais. A CPU Docker usa snapshots em `victim_stats.jsonl`, preservando `received_seconds` e valores ausentes; memória usa `simulation_metrics.csv.mem_usage` em MiB, com a vítima como único contêiner ativo nas amostras aceitas. A memória é a medida agregada dos contêineres ativos, que neste conjunto equivale ao contêiner da vítima; não é RAM do host. Operações aguardando e ocupação foram reconstruídas dos eventos de submissão, início e conclusão, integradas em médias por segundo. Operações aguardando não equivalem à fila interna exata.

## Cobertura das visualizações

| Categoria | Estado | Evidência e limite |
|---|---|---|
| Infraestrutura e atendimento HTTP | Completa no escopo dos registros | Painéis por execução, fases, recursos, requisições e disponibilidade; workers e espera são reconstruídos. |
| Cinco sinais monitorados | Completa | Cinco séries descritivas; CPU não possui decisões oficiais. |
| Detectores, estatísticas, limiares e alarmes | Parcial por execução | Quatro sinais elegíveis e quatro detectores; os 60 testes têm raster, enquanto trajetórias detalhadas usam três execuções ilustrativas. `--all-traces` amplia para as 960 combinações. |
| Desempenho, calibração e pareamento | Completa no escopo oficial | Detecção, FPR, latência, disponibilidade, BASELINE/CAL_A/CAL_B e 20 blocos. |
| Infraestrutura versus alarmes | Parcial por execução | Painéis detalhados das execuções ilustrativas e rasters por teste; coincidências são descritivas. |
| Detecção sobre CPU | Indisponível no protocolo | Sem resultados oficiais detector × CPU; nenhuma decisão foi criada. |

## Figuras produzidas

| Grupo | Figuras PNG/PDF |
|---|---:|
| alarmes | 66 |
| calibracao | 13 |
| comparacoes | 26 |
| desempenho | 27 |
| detectores | 156 |
| infraestrutura | 72 |
| infraestrutura_vs_alarmes | 24 |
| pareamento | 22 |
| sinais | 73 |

**Total: 479 figuras**, cada uma em PNG a 300 dpi e PDF vetorial. O catálogo completo está em [`catalogo_figuras.csv`](catalogo_figuras.csv).

### Execuções ilustrativas selecionadas objetivamente

Para explicar trajetórias sem escolher uma execução favorável, a visualização detalhada usa a execução cuja CPU média ACTIVE está mais próxima da mediana do respectivo cenário; empate pelo ID. As 60 execuções permanecem nos painéis de infraestrutura, sinais e raster de alarmes. O comando `plots.py --all-traces` permite gerar C1/C2 para todas as 960 combinações TEST.

| Cenário | Execução | Bloco | CPU média ACTIVE (%) | Mediana do cenário (%) |
|---|---|---:|---:|---:|
| L2 | ps_direct80_039_L2 | 7 | 51.19 | 51.13 |
| A3 | ps_direct80_037_A3 | 6 | 212.11 | 212.16 |
| F96 | ps_direct80_027_F96 | 3 | 235.95 | 236.02 |

## Resultados observados em TEST

### Infraestrutura e atendimento legítimo

| Cenário | CPU média ACTIVE, mediana das execuções (%) | Memória média ACTIVE, mediana (MiB) | Fração com 2 workers, mediana | Timeout legítimo ACTIVE, mediana por execução |
|---|---:|---:|---:|---:|
| L2 | 51.13 | 44.09 | 8.4% | 0 |
| A3 | 212.16 | 64.59 | 99.5% | 1742 |
| F96 | 236.02 | 69.55 | 98.0% | 1228 |

Essas são descrições por execução. Diferenças entre A3 e F96 incluem mecanismo, endpoint e intensidade, além da interação com o tráfego legítimo. Diferenças no nível inicial de memória não são atribuídas ao ataque.

### Detectores

| Cenário | Detector | Eventos detectados / 80 combinações (4 sinais × 20 blocos) |
|---|---|---:|
| A3 | zscore | 80/80 |
| A3 | cov | 32/80 |
| A3 | ewma | 80/80 |
| A3 | cusum-freeze | 80/80 |
| F96 | zscore | 80/80 |
| F96 | cov | 80/80 |
| F96 | ewma | 80/80 |
| F96 | cusum-freeze | 80/80 |

A contagem acima resume pares sinal × execução; **não** é número de eventos ofensivos independentes. Para cada par método × sinal, há 20 eventos em 20 blocos. Consulte os heatmaps para os denominadores corretos por par. Em assimetria, o CoV apresentou detecção menos frequente em alguns sinais; os demais métodos detectaram os eventos das combinações elegíveis observadas. Em Flooding, todas as combinações elegíveis registraram detecção. A positividade em PRE e POST e as latências variam, portanto a detecção isolada não define superioridade.

## Fatos, interpretações e limites

**Fatos observados:** as séries TEST possuem lacunas de CPU quando não houve valor válido na janela; os manifests TEST preservam decisões indisponíveis. Os 20 blocos foram processados, e as métricas oficiais de avaliação foram mantidas sem recalibração. Os rasters mostram alarmes antes e após a emissão ofensiva, cuja interpretação segue as definições de PRE e POST do pipeline.

**Interpretação exploratória:** comparar sinal, score, limiar e decisão ajuda a examinar como cada método responde ao mesmo episódio. As figuras de infraestrutura permitem verificar coincidência temporal entre pressão computacional, duração HTTP e alarmes. Coincidência não comprova causalidade.

**Limitações:** somente quatro sinais foram elegíveis a detectores; CPU ficou descritiva. A memória tem cadência de aproximadamente 5 s, enquanto CPU e features possuem relógios/cadências próprios. A duração média por janela pode ser ausente, e não é uma amostra individual de latência. As janelas não são unidades experimentais independentes. O tempo de processamento do detector não foi medido. A captura de rede não atribui pacotes a classes com a mesma segurança que o log HTTP. Os PDFs com muitos pontos permanecem vetoriais e podem ser grandes.

## Figuras potencialmente úteis para o TCC

Esta é uma sugestão preliminar sem excluir nenhuma figura: painel de cinco sinais da execução ilustrativa, trajetória de sinal–estatística–alarme para cada método, matriz de detecção por evento A3/F96, raster de alarmes de uma execução e painel infraestrutura versus alarmes. A escolha final requer inspeção científica dos pares de FPR, detecção e latência, inclusive casos sem detecção.

## Reprodução

Da raiz do repositório:

```bash
python3 reports/scientific_campaign_visualization_20261112/scripts/audit.py
python3 reports/scientific_campaign_visualization_20261112/scripts/plots.py
python3 reports/scientific_campaign_visualization_20261112/scripts/report.py
python3 reports/scientific_campaign_visualization_20261112/scripts/validate.py
```

Para adicionar as 960 trajetórias C1/C2 individuais de TEST, executar `plots.py --all-traces` e depois `report.py` e `validate.py`. Essa opção aumenta substancialmente o tempo e o volume de arquivos. Dependências: Python 3, NumPy, pandas, Matplotlib e Pillow. Nenhum artefato original é escrito.

## Precisão dos limiares

Os manifests oficiais preservam dezenas de casas decimais. Em uma janela CUSUM-freeze, score e limiar distintos aparecem iguais após conversão para `float` no CSV de visualização; a validação compara esse empate aparente com os decimais originais. A decisão oficial foi preservada.

## Estado da validação

Verificações automatizadas: **20/20 aprovadas**; resultado geral: **aprovado**. Detalhes em [`validation/result.json`](validation/result.json). A inspeção visual por amostragem é descrita separadamente nos registros de validação.
