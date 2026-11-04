# Seleção após os pilotos

Todos os pilotos de 8/32/64/96/128 RPS concluíram normalmente, sem falhas, sem perda diagnóstica/captura, com drenagem e limpeza confirmadas. P95 até worker: 0,73/1,35/9,76/13,72/21,87 ms; HTTP p95: 54,29/57,13/59,34/63,21/71,33 ms. CPU média Docker: 10,29/46,47/84,84/125,56/149,71%. Nenhum guarda foi acionado. Teto 128 mantido, sem procurar máximo.

| Cenário | Contêineres de fontes | RPS/fonte | RPS agregado | Envio agregado | Workers |
|---|---:|---:|---:|---:|---:|
| C1 | 2 | 4 | 8 | 64 threads | 2 processos |
| C2 | 2 | 32 | 64 | 64 threads | 2 processos |
| C3 | 2 | 64 | 128 | 64 threads | 2 processos |
| C4 | 4 | 16 | 64 | 64 threads | 2 processos |
| C5 | 4 | 32 | 128 | 64 threads | 2 processos |

Cada cenário ON: 20 s × duas seeds `44112101/44112102`. C2/C3 também OFF com as mesmas seeds. Ordem ON→OFF em r1 e OFF→ON em r2, pares adjacentes. Total principal: 14 execuções; com os cinco pilotos: 19. Intervalo mínimo 3 s, novo preflight e validação de cada execução antes da seguinte. Qualquer falha ou guarda bloqueia o restante, sem retry automático. Não há mudança de endpoint, work_units, executores, mecanismos estocásticos ou parâmetros científicos definitivos.
