# Inspeção visual por amostragem

Inspeção manual de PNGs renderizados, além das verificações automatizadas de dimensão, conteúdo e pares PNG/PDF.

| Grupo | Amostra | Resultado |
|---|---|---|
| Calibração | `figures/calibracao/CAL_A_CAL_B_elegibilidade.png` | Barra de cores foi reposicionada abaixo das matrizes; títulos, valores e elegibilidade legíveis. |
| Desempenho | `figures/desempenho/disponibilidade_operacional.png` | Rótulos e escalas legíveis. |
| Sinais | `figures/sinais/comparativas/mean_cpu_percent_matriz_cenarios.png` | Séries e fases legíveis; lacunas preservadas. |
| Infraestrutura e alarmes | `figures/infraestrutura_vs_alarmes/ps_direct80_037_A3_cusum-freeze_mean_duration_ms_integrado.png` | Sete faixas sincronizadas legíveis na versão de investigação; CPU e memória usam pontos amostrados. |
| Infraestrutura e workers | `figures/infraestrutura/distribuicoes/workers_two_fraction_por_cenario.png` | Fração calculada por integração exata dos eventos; escala de zero a um e ECDF legíveis. |
| Comparações de detector | `figures/comparacoes/por_detector/ps_direct80_027_F96_cusum-freeze_quatro_sinais.png` | Quatro sinais elegíveis, fase ofensiva e episódios de alarme visíveis. |

Os painéis integrados completos são altos e exigem inspeção em tamanho amplo; para uma página de TCC, a seleção posterior deverá priorizar versões compactas ou recortes. A amostragem visual não equivale a uma revisão manual de todas as figuras.
