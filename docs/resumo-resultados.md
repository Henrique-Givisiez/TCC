A campanha mostrou que **o custo das requisições mudou o impacto do ataque mesmo com a mesma taxa ofensiva nominal**. Com 16 requisições por segundo direcionadas a `/medium` (M16), o serviço legítimo manteve 100% de sucesso. Com a mesma taxa nominal direcionada a `/expensive` (E16), a duração média aumentou, surgiram timeouts e a proteção interrompeu o ataque em 10 das 12 execuções.

Foram concluídas **56 coletas**, das quais **36 compõem o teste final**. O teste teve 12 blocos completos, cada um com controle sem ataque (C16), ataque a `/medium` (M16) e ataque a `/expensive` (E16). A vítima operou com capacidade fixa e recebeu 16 RPS legítimos nominais nos três cenários.

**Impacto no serviço**

| Métrica na fase ACTIVE | C16 | M16 | E16 |
|---|---:|---:|---:|
| Sucesso das requisições legítimas | 100% | 100% | 93,43% |
| Timeouts legítimos | 0% | 0% | 6,57% |
| Duração média das requisições legítimas concluídas, incluindo timeouts | 30,6 ms | 36,7 ms | 643,8 ms |
| CPU média da vítima, na escala Docker | 20,6% | 40,6% | 184,6% |
| Interrupções antecipadas do ataque | — | 0/12 | 10/12 |

No contraste pareado E16−M16, a duração média aumentou **607 ms** (IC95% de 541 a 691 ms) e os timeouts aumentaram **6,57 pontos percentuais** (IC95% de 4,56 a 8,25). A proteção atuou independentemente dos detectores. Com isso, a exposição ofensiva média foi de **82,4 s em E16** e **120,0 s em M16**. Houve recuperação confirmada nas 12 execuções de cada cenário ofensivo.

**Desempenho dos detectores**

Todas as 20 combinações de método e variável passaram pela verificação independente em CAL-B. A tabela destaca a **contagem de requisições iniciadas**, uma das cinco variáveis avaliadas.

| Método | Eventos detectados M16 / E16 | Falsos alarmes por janela M16 / E16 | Atraso médio quando detectou M16 / E16 |
|---|---:|---:|---:|
| Z-score | 12/12 · 12/12 | 1,05% · 0,85% | 0,994 s · 0,995 s |
| CoV | 6/12 · 6/12 | 2,13% · 1,54% | 1,327 s · 1,328 s |
| EWMA | 12/12 · 12/12 | 3,84% · 3,41% | 1,494 s · 1,495 s |
| CUSUM com congelamento | 12/12 · 12/12 | 0,77% · 0,90% | 1,410 s · 1,411 s |

Nessa variável, **o Z-score teve o menor atraso médio**. O **CUSUM com congelamento combinou detecção de todos os eventos com taxas de falso alarme abaixo de 1% nos dois cenários**. O CoV perdeu seis eventos por cenário, e seu desempenho variou conforme a variável. Em E16, por exemplo, detectou 12/12 eventos usando CPU e 6/12 usando bytes de payload TCP.

Com 12 eventos por cenário, **12/12 corresponde a um IC95% de 73,54% a 100%**. Vale apresentar a contagem junto do intervalo. O atraso é calculado entre os eventos detectados e usa o fechamento da janela como instante de disponibilidade da decisão.
