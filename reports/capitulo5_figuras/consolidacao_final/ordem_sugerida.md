# Ordem sugerida para o Capítulo 5

A sequência progride das escolhas exploratórias aos efeitos operacionais e,
depois, às decisões dos detectores. Cada ID identifica um arquivo do
`inventario.csv`; a numeração das figuras cabe ao LaTeX.

| Ordem | Seção | Item | Pergunta e contribuição | Relação editorial |
|---:|---|---|---|---|
| 1 | 5.1 | F5.1-B | Quanto diferem os custos de `/medium` e `/expensive`? Sustenta a assimetria computacional. | Duas execuções por endpoint; descrição, sem inferência. |
| 2 | 5.1 | F5.1-D | Onde a emissão efetiva deixa de acompanhar a taxa nominal? Expõe admissões que nem iniciaram HTTP. | Não usar isoladamente para justificar concorrência 96. |
| 3 | 5.1 | F5.1-E | Como variaram o atendimento e os desfechos legítimos nos pilotos combinados? | Explicar que 96 teve maior degradação observada apesar de menor início HTTP ofensivo; apenas uma execução por condição. |
| 4 | 5.2 | F5.2-A | Como duração 2xx e timeouts evoluíram antes, durante e após a emissão? | Ler junto com C; omissões de duração são ausência de 2xx, não duração zero. |
| 5 | 5.2 | F5.2-C | Como os 20 blocos variaram em sucesso eventual e timeout durante ACTIVE? | Complementa a série temporal com distribuição pareada. |
| 6 | 5.2 | F5.2-D | Como CPU e memória da vítima evoluíram? | Contexto operacional; CPU acima de 100% é esperada. |
| 7 | 5.2 | F5.2-E | Houve acúmulo de operações aguardando execução na vítima? | Relacionar descritivamente a D e A, sem conclusão causal isolada. |
| 8 | 5.2 | T5.2-A | Quais indicadores resumem o ACTIVE nas 20 execuções? | Média ± DP complementa as medianas das figuras; conferir nota de definição. |
| 9 | 5.3 | T5.3-A | Como as 16 combinações se comportaram em detecção, recall e FPR? | Base quantitativa; latência e POST ficam no CSV complementar. |
| 10 | 5.3 | F5.3-B | Quais combinações têm recall alto ou baixo em cada mecanismo? | Visualização descritiva dos recalls da tabela; contrastes pareados oficiais podem ser citados separadamente. |
| 11 | 5.3 | F5.3-C1 e F5.3-C2 | Quando os alarmes aparecem, persistem ou oscilam em cada bloco? | Escolher consolidada ou divisão por detector; manter a mesma ordem de blocos. |
| 12 | 5.3 | F5.3-D | Qual a frequência resumida de alarmes no período pós-ataque? | Complementa C; candidata ao apêndice se faltar espaço. |

## Discussão 5.4

Articular os mecanismos selecionados com atendimento legítimo, recursos,
espera na vítima e manifestações dos detectores. Os contrastes de recall
comparam configurações completas de A3 e F96; não isolam taxa, endpoint ou
concorrência. Alarmes após 270 s podem coexistir com requisições e operações
remanescentes. Não há proposta de nova visualização nesta seção.
