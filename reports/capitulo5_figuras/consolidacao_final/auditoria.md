# Auditoria das visualizações do Capítulo 5

## A. Resumo executivo

Foram selecionadas **11 figuras e 2 tabelas** dos cinco lotes: 6 itens com
aprovação explícita da coordenação, 5 implementados e rastreados que ainda
pedem conferência editorial da versão final, e 2 mapas binários F5.3-C cuja
diagramação final está pendente. Não foi encontrado impedimento científico P0.
As **26 cópias** (PDF/PNG ou TeX/CSV) são idênticas byte a byte aos arquivos de
origem; `manifesto_copias.csv` contém seus SHA256. Nenhum resultado oficial foi
recalculado nesta consolidação.

As figuras exploratórias A2, B1 e B2 permanecem identificadas como pilotos;
as figuras definitivas usam `energy-powersaver-20261109`, partição TEST, com
60 execuções em 20 blocos completos. Não há fonte da campanha
`scientific-c135-readiness-fix-20261108` entre as versões selecionadas.

## B. Auditoria científica e de proveniência

| Itens | Fontes, campos e filtros confirmados nos scripts | Unidade e agregação | Ressalva |
|---|---|---|---|
| F5.1-B | `reports/a2_endpoint_characterization_20261112/processed/summary.csv`: `cpu_worker_mean_ms`; M_A/M_B e E_A/E_B; `[0,60)` | Média por operação dentro da execução; duas médias de execução por endpoint | Descritiva, sem IC. CPU do worker, não CPU Docker. |
| F5.1-D | `reports/b1_attack_characterization_20261112/processed/summary.csv`: `http_started`, `submitted`, `abandoned_admission`; F1–F5, `[30,60)` | Uma execução por intensidade; `http_started/30` | Expiração anterior ao início HTTP não é timeout do cliente. |
| F5.1-E | `reports/b2_combined_characterization_20261112/processed/phase_summary.csv`: `success_median_ms`, `http_2xx_start_cohort`, `timeout_start_cohort`, `started`; B2-L/A/F/F96, ACTIVE `[30,60)` | Mediana de 2xx e proporções de tentativas por condição | Duração só das respostas 2xx; uma execução por condição. |
| F5.2-A | `reports/investigacao-temporal-energy-20261110/series_1s.csv`: `benign_duration_2xx_ms`, inícios e timeouts legítimos; TEST `[30,390)` | Média 2xx por execução/segundo, depois mediana entre 20; timeouts por execução/5 s, depois mediana | Durações ausentes ficam ausentes; cobertura ACTIVE: A3 242/2400 e F96 909/2400 pares execução–segundo. |
| F5.2-C | `reports/scientific_campaign_visualization_20261112/processed/http_phases.csv`: `started`, `http_2xx_cohort`, `timeout_cohort`, `other_cohort`; classe legítima, ACTIVE | Proporções por execução, 20 pontos por cenário ligados por bloco; mediana descritiva | Sucesso eventual por coorte de início. O indicador operacional oficial usa denominador distinto em 22 execuções. |
| F5.2-D | Auditoria `processed/docker_<id>.csv` (`t`,`cpu`,`state`) e `memory_<id>.csv` (`t`,`mem`); TEST `[30,390)` | CPU: média de 4–6 snapshots válidos por janela de 5 s e execução; memória: um valor por 5 s; mediana entre execuções | CPU é do contêiner da vítima, 100% ≈ um processador lógico. Não equivale ao resumo oficial de CPU agregado em 5 s. |
| F5.2-E | `series_1s.csv`: `waiting`, `running`, `pending`, `pending_end`; TEST `[30,390)` | `waiting` = média temporal dentro de 1 s por execução; mediana de 20 execuções | `pending = waiting + running`; figura mostra só `waiting` da vítima. |
| T5.2-A | `http_phases.csv`, `infrastructure.csv`, snapshots Docker, `series_1s.csv`, `metricas_periodo_execucao.csv`, `operacoes_<id>.csv`; ACTIVE | Indicador por execução, média ± DP amostral (`ddof=1`) entre 20; taxa nominal é parâmetro | Tempo de espera: `(work_started−work_submitted)×1000` para operações submetidas em ACTIVE; nenhuma sem início observado. |
| T5.3-A | `experiment_results/scientific-energy-powersaver-20261109/analysis/summary/manifest.json:results`; 16 pares TEST | FPR L2, detecção por evento e média dos recalls por execução; 20 por cenário | Latência de não detectadas permanece ausente; latência e POST estão em `lote4_detectores/tables/metricas_complementares.csv`. |
| F5.3-B | Mesmo manifesto `means:recall:estimate`; 16 pares em A3/F96 | Média oficial dos 20 recalls por execução, escala comum 0–100% | Mapa é descritivo. Contrastes por bloco e IC oficiais permanecem em `lote4_detectores/processed/contrastes_pareados.csv`. |
| F5.3-C1/C2 | `reports/scientific_campaign_visualization_20261112/processed/detectors.csv`: `entry_id`,`block`,`scenario`,`method`,`feature`,`t`,`decision`,`unavailable_reason`; A3/F96, `[30,390)` | Estado binário por execução e segundo; blocos 1–20 fixos; **sem agregação entre execuções** | Decisão ausente tem cor própria; foram observadas zero decisões e zero valores de característica ausentes nesse intervalo. |
| F5.3-D | Resumo oficial `means:post_positive_fraction:estimate`, transcrito em `lote5_alarmes/tables/alarmes_post_resumo.csv` | Proporção por execução após fim real do evento, depois média de 20 execuções | Calendário pós-emissão não garante fim do processamento; alarmes não são automaticamente falsos positivos. |

Os scripts de cada lote, listados em `inventario.csv`, verificam IDs, cenários e
blocos com o plano da campanha. O manifesto derivado de cada lote registra as
contagens auditadas. Lotes 4 e 5 confrontam resultados com os manifests
oficiais dos detectores. A calibração usa CAL_A, a verificação usa CAL_B e a
avaliação apresentada usa TEST; não houve ajuste de limiares com TEST.

**Comparações pareadas.** O contraste oficial é `recall(A3) − recall(F96)`;
as 20 diferenças são formadas dentro dos blocos. O protocolo registra IC de
95% e 10.000 reamostragens por bloco: 13 contrastes `BCa_block_mean` e três
casos degenerados `Hoeffding_degenerate`. A F5.3-B atual exibe os recalls
absolutos; a versão anterior dos contrastes e os dados inferenciais continuam
no Lote 4. IC que cruzam zero não demonstram equivalência.

**Definições transversais.** O timeout do cliente TEST é de 2 s. Duração HTTP
2xx é medida no cliente e atribuída à coorte de **início**; tentativas sem
2xx não recebem duração zero. Na tabela, CPU e memória referem-se ao
contêiner da vítima; memória está em MiB. O estoque `pending_end` aos 270 s
não é a média temporal de `waiting`. As decisões dos detectores usam o
segundo `[t−1,t)`, onde `t` é o fim da janela auditada; `False` não é NA.

## C. Auditoria visual e preparação para Overleaf

Os 11 PDFs selecionados possuem uma página, fontes incorporadas e textos
legíveis na inspeção dos PNGs. Os PDFs dos mapas e painéis combinam textos
vetoriais com conteúdo de mapa rasterizado; os mapas binários mantêm uma
coluna por segundo. As figuras exploratórias F5.1-D/E são largas (858/930 pt)
e a F5.3-C consolidada é alta (1004 pt). Verificar **na largura real de
inserção** se rótulos e linhas individuais permanecem legíveis. As versões
F5.3-C divididas por detector permanecem no Lote 5 como alternativa atual,
sem omitir blocos ou combinações.

As duas tabelas TeX usam `booktabs`, sem linhas verticais, e exigem
`\usepackage{booktabs}` no preâmbulo. A sintaxe foi inspecionada, mas a
compilação no projeto Overleaf ainda não foi feita. T5.2-A apresenta média
± DP amostral; as figuras temporais usam medianas. Essa diferença é
intencional. T5.3-A apresenta as 16 combinações e coloca latência, POST e IC
em arquivo complementar, evitando uma tabela excessivamente larga.

Os rótulos principais usam nomes descritivos. Algumas figuras e tabelas
aprovadas ainda exibem `ACTIVE`/`POST` nos rodapés ou notas, enquanto os mapas
recentes mostram “Emissão ofensiva” e “Período pós-ataque”. Tratar essa
diferença na legenda LaTeX ou em revisão editorial autorizada; não alterar
automaticamente figuras aprovadas. F5.1-D mantém “HTTP Request Flooding” no
título aprovado, enquanto as figuras definitivas usam “Inundação HTTP”.

## D. Sobreposições e função de cada item

| Possível sobreposição | Diferença científica | Encaminhamento |
|---|---|---|
| F5.2-A × F5.2-C | A mostra duração 2xx condicionada à resposta e timeouts no tempo; C mostra distribuição das proporções por bloco em ACTIVE. | Manter ambas; explicar perda de cobertura de 2xx em A. |
| F5.2-D × F5.2-E × T5.2-A | Recursos, estoque temporal da fila e síntese numérica têm unidades e estimadores distintos. | Manter; não atribuir causalidade isolada à fila/CPU. |
| T5.3-A × F5.3-B | A reúne FPR, detecção e recall; B facilita comparar os 32 recalls absolutos. | Manter se a discussão comparar mecanismos; B pode ir ao apêndice se houver limite de espaço. |
| F5.3-C × F5.3-D | C mostra decisões por bloco e segundo; D resume quantitativamente a proporção oficial após o fim real do evento. | Complementares; D pode ir ao apêndice se a persistência tiver pouco espaço na discussão. |
| F5.3-C consolidada × dividida | Mesmos dados, diagramação diferente. | Escolher uma apresentação; não inserir ambas no corpo. |

## E. Pendências e prioridades

- **P0 — nenhuma identificada** nos artefatos selecionados.
- **P1 — decisão editorial da F5.3-C:** escolher mapa consolidado por mecanismo
  ou oito painéis divididos por detector. Os mapas consolidados permitem ver
  padrões globais; os divididos mostram melhor o bloco individual em página.
- **P1 — montagem no Overleaf:** compilar as duas tabelas com `booktabs`, conferir
  largura das F5.1-D/E, altura da F5.3-C e tamanho final de fonte. Isso é uma
  verificação de integração, não uma revisão dos resultados.
- **P1 — legendas científicas:** registrar explicitamente na F5.2-A a baixa
  cobertura 2xx durante ACTIVE e as resoluções 1 s/5 s; na T5.2-A, distinguir
  sucesso eventual e CPU nativa dos indicadores operacionais de outra definição;
  na F5.3-B, distinguir recall descritivo de contraste inferencial; em F5.3-C/D,
  distinguir fim da emissão de fim do processamento.
- **P2 — padronização de fase e idioma:** harmonizar nas legendas “Emissão
  ofensiva” e “Período pós-ataque” com rodapés que ainda contêm ACTIVE/POST;
  preservar os arquivos aprovados até decisão editorial.

## F. Recomendação

Os seis itens explicitamente aprovados estão prontos como arquivos para
inserção. Os cinco itens `Revisar` são cientificamente rastreáveis, mas a
coordenação ainda deve conferir sua versão final e as legendas. As duas
F5.3-C estão completas e verificadas nos dados; falta apenas a escolha de
diagramação. Não há necessidade identificada de nova campanha, detector ou
figura para cobrir as perguntas centrais do capítulo.
