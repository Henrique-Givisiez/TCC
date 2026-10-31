# Primeira seleção de resultados — clock r2

Preparação offline em 31/10/2026 para o TCC. Quatro figuras principais em PDF vetorial e PNG a 300 dpi; tabelas preservam os números dos artefatos existentes. Nenhum experimento, calibração, detector, score, decisão, limiar ou IC foi executado ou produzido novamente. Não foram alterados os artefatos de origem.

## Figuras e legendas sugeridas

| Figura | PDF para o TCC | Prévia PNG | Conteúdo |
|---|---|---|---|
| A | [Detecção](figures/A_detection.pdf) | [PNG](figures/A_detection.png) | Quatro métodos × cinco features, M16/E16, IC95%, detectados/avaliados e misses. |
| B | [Falsos alarmes](figures/B_false_alarms.pdf) | [PNG](figures/B_false_alarms.png) | FPR por janela de request_starts, três cenários, IC95%. |
| C | [Impacto pareado](figures/C_paired_service.pdf) | [PNG](figures/C_paired_service.png) | Doze pares por bloco: CPU da vítima, duração e timeouts legítimos em ACTIVE. |
| D | [Evolução temporal](figures/D_time_evolution.pdf) | [PNG](figures/D_time_evolution.png) | Trio B01: carga realizada, duração HTTP, CPU, pendências e quatro métodos. |

**A — legenda sugerida.** Detecção por evento nos 12 blocos TEST para M16 e E16. Pontos e barras representam estimativas e IC95% congelados, respectivamente; os rótulos informam eventos detectados/avaliados e misses. Cada evento é detectado quando existe alarme com sobreposição observacional e disponibilidade entre o início e o fim reais da emissão. C16 não possui eventos ofensivos e não recebe detecção zero. ICs são pontuais e condicionais ao treinamento congelado; não se estabelece ranking global.

**B — legenda sugerida.** FPR por janela benigna de request_starts, expressa como média dos 12 blocos, com IC95% congelado. O denominador benigno em M16/E16 inclui POST e possíveis efeitos residuais da emissão. FPR por janela difere da proporção de execuções com ao menos um falso alarme, apresentada na tabela complementar. Janelas mistas são excluídas das métricas por janela.

**C — legenda sugerida.** Valores individuais em ACTIVE para M16 e E16, ligados dentro de cada bloco. Duração e timeouts usam requisições legítimas; CPU corresponde à vítima inteira, sob ambas as cargas. As exposições realizadas diferem, com E16 sujeito à política de proteção: a comparação descreve essa política operacional e não uma condição de dose igual. Cada linha representa um bloco; deslocamentos horizontais mínimos separam pontos coincidentes. Contrastes e IC95% congelados estão na tabela complementar. Percentis individuais não foram promediados.

**D — legenda sugerida.** Evolução ilustrativa do bloco completo de menor identificador, B01, selecionado sem usar valores de métricas ou aparência das curvas. Taxas de início e durações por conclusão são agregadas em bins de 5 s; CPU usa ticks registrados; pendências são amostradas a cada segundo. Séries legítimas e de ambas as classes são identificadas separadamente. Alarmes existentes de request_starts são posicionados na disponibilidade atribuída ao fechamento da janela de 1 s. A faixa indica emissão real; linhas tracejada, contínua e pontilhada magenta marcam início, fim e comando de parada. O comando e o fim E16 diferem por apenas 8,8 ms e ficam praticamente sobrepostos nesta escala; os valores exatos estão na tabela de fronteiras. C16 não tem emissão ofensiva. O exemplo não substitui os resultados das 12 repetições.

Para diagramação, A e D devem ocupar uma página, preferencialmente em orientação paisagem para D; B e C admitem largura de página. Usar o PDF para preservar fontes e traços vetoriais.

## Tabelas prontas e auxiliares

- [Contrastes C em Markdown](tables/C_contrasts.md) e [LaTeX](tables/C_contrasts.tex): três diferenças E16−M16 com ICs oficiais; CPU e timeouts em pontos percentuais, duração em ms.
- [FPR versus execuções com falso alarme](tables/B_fpr_vs_runs.md): explicita os dois denominadores. Ambos os ICs são transcritos; não recalculados.
- [Detecção nas cinco features](tables/event_detection.csv): inclui C16 com campos de evento vazios, sem zero artificial.
- [FPR, recall, atraso, POST e algum FP](tables/window_delay_post_metrics.csv): estimativas, limites e suporte publicados. Atraso está em segundos e apenas entre detectados; ausência de IC permanece vazia.
- [Avaliações por execução](tables/evaluation_by_run.csv): transcrição das 180 avaliações × quatro métodos, incluindo TP/FP/TN/FN, fronteiras, denominadores, POST, misses implícitos no indicador de evento e disponibilidade.
- [Operacionais por execução](tables/operational_by_run.csv), [resumos por cenário](tables/operational_summaries_frozen.csv) e [todos os contrastes operacionais existentes](tables/operational_contrasts_frozen.csv): valores congelados para as fases e indicadores de exposição/parada/recuperação. Campos de frações nesses CSVs permanecem entre 0 e 1.
- [Inventário do proxy por execução](tables/proxy_inventory_by_run.csv): presença de arquivos, leituras válidas/falhas, campos suportados, intervalos, lacunas e correspondência de IDs; são contagens descritivas novas dos registros existentes, não métricas inferenciais.
- D: [agregações visuais de 5 s](tables/D_visual_aggregates_5s.csv), [alarmes existentes](tables/D_existing_alarms.csv), [fronteiras](tables/D_event_boundaries.csv), `D_pending_<cenário>.csv` e `D_victim_ticks_<cenário>.csv`. Os ticks são cópias tabulares dos registros vinculados; não uma nova extração de features.

As tabelas Markdown arredondam para três casas decimais. Os CSVs retêm os números lidos, sem arredondamento de apresentação. Nenhuma estimativa ou limite é obtido das médias dos extremos de ICs. Zero permanece zero observado; nulos ficam vazios. O campo `ci_method` fica vazio quando o objeto original não o publica, como no resumo de atraso, sem inventar metadados.

## Fontes e definições

Autoridades: `experiments/protocols/scientific_reduced_clock_r2_20261029/plan.json` e `experiment_results/scientific-reduced-clock-r2-20261029/checkpoints/TEST/manifest.json`. O checkpoint aponta para o summary de SHA256 `913c5fb44588df0ea228866ac8333576b6b8a0270daceb2e700a3eb6fab35400`. Foram seguidas as referências reais `artifacts.summary`, `summary.evaluations`, `evaluation.run`, `checkpoint.receipts` e `receipt.dataset`, com os hashes dos arquivos utilizados. O inventário nominal não foi usado para adivinhar tentativas ou caminhos.

Os documentos de contexto são [relatório](../scientific_reduced_clock_r2_20261030/report.md), [síntese](../scientific_reduced_clock_r2_20261030/summary.md) e [nota metodológica](../scientific_reduced_clock_r2_20261030/methodology_note.md). A cadeia histórica não foi reauditada: a conferência ficou nos vínculos usados por esta apresentação. Os 180 manifests de avaliação foram lidos; as três séries de alarmes de D vieram de seus runs referenciados. [provenance.json](provenance.json) e [sources.csv](tables/sources.csv) registram a seleção, versões, caminhos e hashes.

**Detecção e POST.** `analysis/detection/scientific/evaluation.py::metrics, aggregate` define o horizonte por janela `[30,390)`, janelas puras e disponibilidade até 390 s; POST exige início da janela maior ou igual ao fim real. POST é subconjunto benigno. Nas cinco features: C16 tem 4.320 benignas; M16 tem 1.428 ofensivas, 2.868 benignas (1.428 POST) e 24 mistas; E16 tem 970 ofensivas, 3.326 benignas (1.886 POST) e 24 mistas. As contagens somadas são documentais; as estimativas são médias por bloco. Detecção usa 12 eventos, não essas contagens de janelas. Atraso usa primeira disponibilidade elegível menos início real; misses ficam fora da média condicional e mantêm contagem própria. Disponibilidade atribuída não mede tempo computacional.

**População de C.** `evaluation.py::impact` usa ACTIVE **[150,e)**, com `e` igual ao fim real da emissão; para C16 usa [150,270). Essa fase operacional começa em 150 s nominal, enquanto a exposição ofensiva é **[s,e)**, com início real `s`; a pequena diferença é preservada. `ACTIVE/mean_all_ms` usa toda a duração dos legítimos iniciados nessa fase que tenham conclusão registrada, incluindo falhas e conclusões após a fase. `ACTIVE/timeout_fraction` divide os concluídos dessa coorte cujo `error_type` contém `Timeout` pelo número de concluídos da coorte. Não equivale à métrica de falha/atraso de 3 s de `development_d3_minimal.measure`. CPU é a média aritmética dos ticks suportados da vítima registrados em ACTIVE; não pode ser atribuída exclusivamente ao tráfego legítimo. Sua escala Docker admite mais de 100%.

A exposição média congelada M16 é 119,998 s [119,996; 120,000]; E16, 82,410 s [68,698; 95,815]. Houve 10/12 paradas precoces E16 por `service_compromise` e nenhuma em M16. O contraste não isola efeito causal da intensidade. Recuperação confirmada é uma regra operacional composta das últimas duas janelas POST qualificadas, com limite de crescimento de pendentes; não é ausência de qualquer efeito residual nem retorno dos alarmes a zero. As regras estão em `evaluation.py::impact` e `experiments/development_d3_minimal.py::assess_window`.

**Persistência de alarmes.** No caminho científico clock r2, a saída existente é `post_positive`, `post_available`, `post_windows`, `post_fpr=post_positive/post_available` e `post_positive_per_total=post_positive/post_windows`, por execução; `aggregate` consolida `post_fpr` com IC. É fração de janelas positivas em POST, não duração de sequência contínua, tempo até último alarme ou tempo até cessação estável. Não foi localizada métrica temporal adicional de persistência nos manifests vinculados ou no avaliador científico. A recuperação operacional é outra definição. O script histórico `experiments/audit_cusum_persistence.py` se vincula a manifests de estágios anteriores; seu nome não comprova uma métrica temporal clock r2. Não foi executado ou incorporado.

## Transformações exclusivas da figura D

Seleção fixa: menor número de bloco TEST contendo os três cenários → B01. Não houve busca por menor atraso, maior impacto ou aparência conveniente. Os 12 pares de C são mantidos independentemente dessa seleção.

- `raw/service/request_log.csv`: inícios por classe em `[a,a+5)`, divididos por 5 s. Não se usa RPS nominal dos summaries dos geradores. Ausência de inícios em C16/ofensivo é zero verificado pela ausência da classe, não um arquivo ausente convertido em zero.
- Duração: média aritmética das conclusões em `[a,a+5)`, separando legítimos e ambas as classes, com a duração inteira atribuída pela conclusão. Bins sem conclusões ficam ausentes. Essa agregação **difere da coorte por início de C** e da feature oficial de 1 s; serve só à visualização. Não usa médias de percentis nem o campo operacional misto `avg_rtt_ms`.
- CPU: ticks nativos de `raw/infrastructure/simulation_metrics.csv`, usando `elapsed_seconds`, com `active_containers_names` como suporte; sem suporte fica ausente. Coletor/cache e deltas Docker impedem interpretá-los como CPU instantânea ou integral exata daquele segundo.
- Pendências: contagem de tentativas com `start < t` e (`end` ausente ou `end >= t`), conforme `development_d3_minimal.pending`, para t inteiro em [30,390]. São pendências **no cliente**, não fila interna do proxy/servidor. Sem suavização ou preenchimento. Os runs são concluídos e reconciliados; a observação alcança esse horizonte.
- Alarmes: apenas decisões booleanas já persistidas em `run.methods`, nas datas `available_at_seconds`; não se aplica novamente um limiar. Marcas verticais são alarmes positivos; ausência de marca só significa negativo onde a decisão existe. Decisões indisponíveis seriam marcadas com × cinza; não há indisponibilidade dentro do horizonte ilustrado. As linhas ligando pontos de taxas/duração/CPU são recurso visual, não interpolação de dados gravada ou inferência.
- Eventos: `raw/attacks/attack_events.csv`; comando: `receipt.operational.scalars.stop_command_seconds`. Em B01: M16 [150,008323; 270,008933) s; E16 [150,003305; 240,568891) s; comando E16 em 240,560076 s. Drenagem não substitui fechamento da emissão.

## Reprodução e verificações

Na raiz do repositório, executar apenas o script de apresentação:

```bash
.venv/bin/python -B reports/scientific_reduced_clock_r2_figures_20261031/generate.py \
  --repo /home/henrique-givisiez/Documents/Faculdade/TCC/TCC \
  --plan experiments/protocols/scientific_reduced_clock_r2_20261029/plan.json \
  --checkpoint experiment_results/scientific-reduced-clock-r2-20261029/checkpoints/TEST/manifest.json \
  --output reports/scientific_reduced_clock_r2_figures_20261031
```

Dependências locais: Python, NumPy e Matplotlib; versões usadas constam em provenance.json. O script não importa módulos do runtime científico, não acessa rede/Docker e só grava no diretório de apresentação. Aceita saída diferente e remapeia referências congeladas para `--repo` ao mover o checkout. PDFs incorporam fontes TrueType; PNGs são exportados a 300 dpi. O script regenera figuras, tabelas e proveniência; este índice e o inventário textual são documentação de acompanhamento.

Foram conferidos os vínculos de entrada usados, 36 recibos/datasets, 180 avaliações, 12 pares completos e a identidade de cada amostra de proxy. Estimativas e ICs vêm diretamente do summary. As quatro figuras foram inspecionadas visualmente: títulos, eixos, ICs, legendas e limites sem sobreposição ou cortes. Não se encontrou divergência entre as fontes oficiais utilizadas; as lacunas de proxy são registradas no [inventário](inventory.md). [Pendências](pending.md) distinguem limites documentais de resultados já disponíveis.
