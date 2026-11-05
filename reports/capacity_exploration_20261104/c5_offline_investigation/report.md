# Investigação offline da degradação operacional em C5

## A. Resumo executivo

Esta análise reconstitui, sem iniciar contêineres ou gerar tráfego, os registros preservados de `C5_ON_r1` e compara-os a `C3_ON_r1`. C5 iniciou 128,65 requisições HTTP/s durante os 20 s de geração, sem falhas, mas desenvolveu crescimento temporal da espera pelo processamento: de valores baixos no começo para picos nos segundos 14–16. A espera média pelo worker foi 166,82 ms (p95 433,43 ms), contra 6,91 ms (p95 23,28 ms) em C3.

O achado mais forte é a correspondência entre essa espera e a duração HTTP: em C5, a correlação de Pearson descritiva por requisição é 0,992 (n=2.574), e a diferença média `HTTP − espera` fica em 39,73 ms, praticamente igual aos 39,59 ms de C3. Isso mostra que a espera acompanhou quase toda a diferença entre as médias dos dois indicadores; não prova causalidade, mas localiza o principal componente temporal associado à degradação.

Também se observou ocupação quase contínua dos dois workers e aumento de trabalho submetido ainda não iniciado até aproximadamente 62 operações derivadas pendentes. A demanda aproximada calculada por taxa de submissão × CPU média por operação é 1,88 cores em um pool de dois workers para C5, contra 1,46 em C3. Isso é compatível com pouca folga efetiva no pool. C5 teve operações mais caras em CPU do que C3, e o tempo de CPU por operação também aumentou dentro de C5; a origem dessa diferença não pode ser identificada pelos dados preservados.

As contagens de chegada em janelas de 100 e 250 ms não mostram mais dispersão agregada em C5 do que em C3. Os atrasos das fontes aparecem depois do aumento de espera na vítima, não antes. Há sinais de atraso operacional secundário nos geradores, mas não de requisições perdidas: todos os registros foram drenados. A hipótese de que quatro fontes, por si só, causaram a degradação não é demonstrada; a comparação contém uma execução de cada distribuição e altera, junto com o número de contêineres, a divisão das 64 threads de envio.

**Conclusão prática:** os dados disponíveis bastam para caracterizar C5 como uma condição de degradação operacional nesta execução e para mantê-la fora de uma faixa candidata sem revisão metodológica. Não bastam para atribuir causa às quatro fontes, estimar capacidade máxima, nem justificar uma nova execução urgente. A campanha exploratória pode ser encerrada como exploração descritiva; a causa do aumento do tempo de serviço permanece uma pendência interpretativa, não um bloqueio à campanha científica se as condições de 64 RPS forem mantidas como referências preliminares e C5 não for tratada como carga estável.

## B. Dados utilizados

Revisão analisada: branch `refactor/project-organization`, HEAD `0e8928c71159bedab14c4987e109f5040c28d570`; é o commit de referência dos artefatos. A árvore estava limpa antes da criação deste diretório de investigação. Nenhum arquivo bruto, configuração experimental, simulador ou dataset histórico foi alterado.

| Execução | ID | Configuração relevante | Registros usados |
|---|---|---|---|
| C3_ON_r1 | `383f827ba63d4bbc9fec2544479553ec` | 2 fontes × 64 RPS, 20 s | Fontes, vítima, cliente, Docker, watchdog e captura |
| C3_OFF_r1 | `bf535b3a3fc945868f6f554bf997f125` | 2 × 64 RPS, 20 s, diagnóstico interno OFF | Cliente, Docker, watchdog e captura; sem eventos de etapas |
| C5_ON_r1 | `dca9817ca23e4a27a28f3470e74c1d72` | 4 × 32 RPS, 20 s | Fontes, vítima, cliente, Docker, watchdog e captura |
| P5_128rps | `2db8ec8d31e04634ba2ccc90304bd5a8` | 2 × 64 RPS, **12 s** | Fontes, vítima, cliente, Docker, watchdog e captura |

Todos os cenários são direct, uma vítima, `/medium`, dois workers, 64 threads de envio agregadas e sem ataque. Os relógios de fonte e vítima de C3_ON, C5_ON e P5 passaram a auditoria de comparabilidade, com kernel igual e offsets de time namespace nulos. As larguras máximas dos intervalos de observação foram aproximadamente 50–62 ms. Por isso, durações locais e pares por `request_id` são a evidência temporal principal; coincidências em bins de 100 ms são frágeis a fronteiras. Mesmo os bins de 250 ms e 1 s são descritivos, não prova causal.

Os streams diagnósticos instrumentados juntam-se ao log científico por `X-Edos-Request-Id`. Os timestamps monotônicos entre contêineres só foram agregados após a validação de relógio e relativos a `experiment_start_monotonic`. Não foi calculada latência de rede unidirecional. O diagnóstico da vítima registra entrada no `do_GET`, submissão, início/fim do trabalho no worker, observação do resultado e fim do handler. Entrada no handler não representa aceitação TCP ou recepção do primeiro byte; fim do handler não confirma que o cliente recebeu a resposta inteira.

O código verificado mantém `/medium` em 100.000 iterações do kernel `_burn_cpu` (`simulator/app/simple_server.py:18–45`), e a operação instrumentada envolve `time.monotonic()` e `time.process_time()` no worker (`:58–68`). O handler submete ao pool persistente e espera `.result()` (`:101–111`); o servidor usa `ThreadingHTTPServer` e pool de processos (`:130–143`). A geração legítima usa intervalos exponenciais relativos, submetendo após planejamento, conforme `simulator/normal_traffic.py:160–203` e a auditoria existente em `audit.md`. Estes são pontos de implementação medidos/inspecionados, não parâmetros alterados pela análise.

## C. Reconstrução temporal de C5

As estatísticas por segundo abaixo associam duração HTTP ao instante de início observado pelo cliente e espera ao instante de submissão do trabalho no handler. `handlers` e `pending` são médias temporais reconstruídas nos respectivos intervalos; `pending` é submissões menos início do trabalho derivado dos timestamps, não profundidade obtida de API privada da fila.

| Segundo | Inícios HTTP | HTTP média (ms) | Espera worker média / p95 (ms) | Handlers médios / pico | Workers médios ativos | Submetido, ainda não iniciado: média / pico |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 118 | 54,1 | 19,0 / 42,6 | 3,8 / 11 | 1,49 | 2,2 / 9 |
| 5 | 148 | 56,1 | 21,7 / 48,6 | 5,1 / 13 | 1,82 | 3,2 / 11 |
| 7 | 120 | 83,6 | 44,9 / 67,8 | 7,5 / 13 | 1,96 | 5,4 / 11 |
| 8 | 133 | 95,0 | 58,6 / 135,7 | 8,7 / 18 | 1,97 | 6,7 / 16 |
| 9 | 127 | 129,5 | 91,2 / 180,5 | 13,1 / 24 | 1,99 | 11,0 / 22 |
| 10 | 121 | 217,6 | 181,1 / 265,9 | 24,5 / 38 | 1,99 | 22,5 / 36 |
| 12 | 140 | 256,3 | 215,8 / 248,5 | 30,7 / 36 | 1,99 | 28,6 / 34 |
| 13 | 125 | 376,1 | 335,2 / 401,1 | 38,5 / 48 | 1,99 | 36,4 / 46 |
| 14 | 132 | 453,1 | 405,7 / 449,6 | 51,7 / 63 | 1,99 | 49,6 / 61 |
| 15 | 122 | 504,2 | 448,7 / 480,2 | 58,3 / 64 | 1,99 | 56,2 / 62 |
| 16 | 121 | 422,7 | 373,3 / 441,8 | 51,4 / 58 | 1,99 | 49,3 / 56 |
| 17 | 131 | 391,2 | 345,2 / 376,3 | 46,5 / 57 | 1,99 | 44,4 / 55 |
| 19 | 124 | 299,4 | 262,8 / 332,8 | 38,7 / 48 | 1,99 | 36,6 / 46 |

**Observação:** a série inicia em valores modestos, aumenta de forma persistente após cerca de 6–9 s, atinge seu máximo em torno de 14–16 s e recua parcialmente antes do fim da geração. Não é um pico único e instantâneo: é uma acumulação transitória que se desenvolve por vários segundos e depois diminui, sem retornar ao nível inicial até o segundo 20.

Na drenagem, 29 respostas concluíram no bin `[20, 20,25) s`; nesse mesmo bin a média temporal de handlers caiu para 7,98, de workers ativos para 1,22 e de submetidos ainda não iniciados para 6,69 (pico 22). Não há outro bin de drenagem com atividade depois de 20,25 s nos registros reconstruídos. A execução marcou `producers_drained=true`, zero requisições não resolvidas e conclusão normal. Portanto a espera e o trabalho pendente não persistiram após a drenagem.

Gráficos: [linha temporal C3 × C5, bins de 1 s](c3_c5_timeline_1s.png), [detalhe C5, bins de 250 ms](c5_detailed_timeline_250ms.png) e [fontes C5, bins de 250 ms](c5_sources_timeline_250ms.png). Os gráficos e CSVs mantêm os bins de 100 ms para inspeção exploratória, com a ressalva de alinhamento indicada acima.

## D. Comportamento dos geradores

Em C5 foram registrados 2.573 inícios HTTP na janela de 20 s (128,65/s) e um início fora dela; 2.545 conclusões ocorreram antes do fim da janela e 29 durante a drenagem. As 2.574 tentativas registradas foram concluídas, sem falhas HTTP ou tentativas não resolvidas. Os inícios observados ficaram próximos da taxa nominal; a acumulação de espera no worker não impediu os geradores de iniciar quantidade próxima à prevista durante esta execução.

Por fonte, os inícios dentro da janela foram: `normal_1` 617 (30,85/s), `normal_2` 660 (33,00/s), `normal_3` 640 (32,00/s) e `normal_4` 657 (32,85/s). A média de atraso submissão→início da tarefa, calculada dentro do relógio de cada fonte, foi respectivamente 3,10; 41,09; 16,25 e 7,98 ms. As medianas ficaram próximas de 0,18–0,19 ms, enquanto os p95 foram 3,69; 312,14; 147,74 e 68,88 ms. Os máximos foram 166,82; 429,50; 278,56 e 193,05 ms. Assim, os atrasos foram heterogêneos e concentrados na cauda, não uma desaceleração uniforme das quatro fontes.

No alinhamento por segundo, as médias de submissão→início começam a se elevar em fontes a partir de aproximadamente 13–14 s, depois de a espera da vítima já ter começado a subir entre 7–9 s. Em 15 s houve espera média de 170 ms em `normal_2`, 103 ms em `normal_3`, 69 ms em `normal_4` e 38 ms em `normal_1`; em 16 s `normal_2` e `normal_3` mantinham 346 e 197 ms. Esta precedência temporal é compatível com as respostas demoradas ocupando threads de envio e produzindo espera secundária no executor das fontes. Não demonstra a direção causal: as fontes partilham o host e a resolução do alinhamento temporal é limitada.

As pendências da fonte são obtidas por sobreposição dos eventos `submitted`→`task_started`, não por introspecção do `ThreadPoolExecutor`. Os máximos por fonte durante toda a execução foram 4, 19, 12 e 10. Não houve perda final: todas as fontes drenaram. O campo de pico agregado por bin nos CSVs soma os máximos das fontes dentro do bin; por construção, não é um máximo agregado simultâneo exato.

## E. Comportamento da vítima

O handler bloqueia em `.result()` enquanto a operação é executada no pool persistente de dois processos. Os eventos instrumentados fornecem espera submit→início do worker, duração de parede e CPU do processo worker, transporte/observação do resultado e duração local do handler. A espera não equivale a duração pura da fila: pode incluir fila do executor, agendamento, IPC e serialização. A fila privada não foi consultada diretamente.

Em C5, sobre 2.574 requisições correspondidas por identificador:

| Medida | C3_ON_r1 | C5_ON_r1 |
|---|---:|---:|
| HTTP: média / mediana / p95 / máximo | 46,51 / 54,05 / 71,44 / 105,80 ms | 206,55 / 163,44 / 488,47 / 561,38 ms |
| Espera do worker: média / mediana / p95 / máximo | 6,91 / 4,14 / 23,28 / 47,52 ms | 166,82 / 127,13 / 433,43 / 496,88 ms |
| Trabalho no worker, parede: média / p95 | 11,39 / 15,64 ms | 14,68 / 23,92 ms |
| CPU do worker por operação: média / p95 | 11,37 / 15,62 ms | 14,65 / 23,80 ms |
| Handlers simultâneos: pico reconstruído | 11 | 64 |
| Handlers simultâneos: média temporal em 20 s | 2,40 | 23,34 |
| Workers ativos: média de dois | 1,46 | 1,87 |
| Ambos os workers ativos, fração dos 20 s | 60,8% | 90,5% |

A espera e duração HTTP foram pareadas por `request_id`, mas são durações medidas em componentes distintos. A correlação de Pearson descritiva é 0,992 em C5 e 0,190 em C3. Em C5, `HTTP − espera` tem média 39,73 ms; em C3, 39,59 ms. A diferença entre as médias HTTP C5−C3 é 160,04 ms e entre esperas é 159,90 ms. Isso permite responder que a elevação HTTP foi predominantemente acompanhada pela espera anterior ao processamento. A igualdade aproximada dos resíduos não converte a espera em decomposição causal exata da duração HTTP.

Os intervalos observados do worker mostram que ambos os slots estavam ocupados por praticamente todo o período de alta espera: a média ficou entre 1,985 e 1,990 workers ativos nos segundos 9–19, e o percentual com os dois ocupados durante todo o intervalo de geração foi 90,5%. Ao mesmo tempo, a média temporal de submissões ainda não iniciadas chegou a 56–58 no entorno de 15–16 s, com máximos de 62. São indícios fortes de trabalho aguardando serviço, mas essa contagem é derivada da diferença de eventos e inclui a semântica temporal dos registros; não é leitura direta da fila interna.

O tempo de CPU por operação também variou: em C5, a média por segundo foi aproximadamente 12,5–12,8 ms nos primeiros segundos, subiu a 14–17 ms a partir de 6–8 s e chegou a cerca de 18 ms no segundo 13. Essa variação é relevante porque `/medium` usa o mesmo kernel de 100.000 iterações, mas não pode ser atribuída a causa específica apenas com estes dados. Trabalho de CPU medido pelo relógio de processo não é tempo de espera nem duração HTTP.

## F. Comparação C3 × C5

Ambos os cenários tiveram mesma taxa nominal agregada (128 RPS), endpoint, pool, topologia, duração, instrumentação, seed mestra e orçamento total de 64 threads. Os inícios HTTP agregados por bins foram semelhantes em sua dispersão: para C3/C5, a razão variância/média foi 1,041/1,011 em bins de 100 ms, 1,077/1,059 em 250 ms e 0,792/0,676 em 1 s. Máximos agregados por bin foram 22/24 em 100 ms, 47/46 em 250 ms e 146/148 em 1 s. Essas estatísticas descritivas não são testes de Poisson, tampouco estabelecem igualdade entre as sequências. Não há sinal de maior sobredispersão temporal agregada em C5 nesses agrupamentos.

Os inícios por fonte também não indicam que uma fonte isolada tenha recebido uma rajada agregada persistentemente maior. As quatro séries têm Fano de 100 ms entre 0,88 e 1,25 e máximo de 8–10 inícios por 100 ms. Fano próximo de 1 é apenas compatível com dispersão Poisson nesse resumo; 20 s e uma execução não permitem uma conclusão estatística forte.

A diferença mais expressiva está no serviço: CPU média por operação maior em C5 (14,65 versus 11,37 ms), ocupação maior e aumento de pendências. A taxa/submissão nominal não explica sozinha a discrepância: o mesmo volume nominal com mais CPU requerida por operação aproximou o uso dos dois workers do limite disponível. A distribuição entre duas e quatro fontes coincide com essa diferença, mas está confundida com a partilha das threads (32 por fonte versus 16) e condições operacionais de duas execuções distintas. A seed mestra não torna idênticas as sequências agregadas.

O piloto P5 é apenas contextual: durou 12 s, iniciou 1.530 tentativas (127,5/s), teve espera p95 21,87 ms, CPU média por operação 11,16 ms e HTTP p95 71,33 ms. Seu resultado se aproxima de C3 e contrasta com C5, mas a duração e o contexto diferem e P5 não é repetição controlada de nenhum deles.

### Comparação ON/OFF

C3_OFF iniciou 2.563 requisições (128,15/s) sem falhas. Sua duração HTTP foi 78,62 ms em média e p95 227,07 ms; a CPU Docker média registrada foi 189,00%, contra 161,95% em C3_ON. C3_OFF não coletou eventos internos de handler/worker/fonte, portanto não permite atribuir diferenças a etapas. A diferença de duração (ou CPU) em um único par de execuções não demonstra overhead, nem ausência de overhead da instrumentação. Em particular, os valores OFF foram mais altos do que ON em duração, o que é evidência contra a hipótese simples de que “a instrumentação explica o HTTP maior”, mas não é comparação replicada/contrabalançada suficiente para estimar seu efeito.

## G. Capacidade computacional

Uma aproximação de demanda de CPU do pool é:

`D = (operações submetidas durante geração / 20 s) × média de CPU de processo por operação`.

Para C3, `2.562/20 × 11,371 ms ≈ 1,457 core`, cerca de 72,8% da capacidade nominal de dois slots em CPU. Para C5, `2.572/20 × 14,651 ms ≈ 1,884 cores`, cerca de 94,2% de dois slots. A medida independente por intervalos observados dá média de 1,458 workers ativos em C3 e 1,874 em C5. A concordância dessas duas descrições e os períodos com ambos ocupados sustentam aproximação de alta ocupação efetiva do pool em C5.

O cálculo é uma aproximação descritiva, não uma capacidade máxima: a média de CPU das operações inclui a variação de execução observada, e a demanda não modela custos do handler, IPC, distribuição de serviço ou disponibilidade variável de CPU. O recíproco do tempo médio de CPU (ou `2/E[S]`) não é uma taxa máxima medida; não deve ser usado para selecionar taxa da campanha.

Uma descrição de fila ajuda a interpretar o padrão: quando dois workers passam quase todo o tempo ocupados, uma pequena folga restante pode ser consumida por variação de serviço e chegadas, elevando a espera sem que a taxa média de chegadas exceda matematicamente a capacidade em toda janela. Não foi ajustado um modelo M/M/2; as hipóteses sobre tempos de serviço e regime estacionário não foram demonstradas, e o perfil temporal mostra transiente e recuperação parcial.

## H. Avaliação das hipóteses

| Hipótese | Evidências favoráveis | Evidências contrárias | Limitações | Avaliação |
|---|---|---|---|---|
| **H1 — Acúmulo progressivo de trabalho** | Pendências derivadas crescem de ~1 operação média em C3 para ~50–58 em C5 no pico; espera sobe ao longo de vários segundos; workers ocupados. | Pendências e espera recuam antes do fim e drenam rapidamente; não há acúmulo permanente. | Um C5; pendência é derivada, não leitura direta da fila; trabalhos têm eventos instrumentados somente em conclusões completas. | **Parcialmente sustentada:** houve crescimento temporário de trabalho aguardando início, não crescimento indefinido. |
| **H2 — Concentrações temporárias de requisições** | Existe variabilidade natural; C5 atinge concorrência e pendência elevadas. | Fano agregado em 100/250 ms é semelhante ou menor em C5; máximos de 250 ms são 46 versus 47 em C3; inícios por segundo permanecem próximos do nominal. | Bins podem mascarar estrutura sub-100 ms; uma execução e sincronização de até ~60 ms de bracket. | **Compatível, mas não demonstrada como explicação diferencial:** não há evidência de chegadas agregadas mais agrupadas em C5 nas janelas examinadas. |
| **H3 — Efeito da distribuição entre fontes** | C5 usa quatro processos de fonte com 16 threads cada em vez de dois com 32; atrasos de fonte surgem e variam entre contêineres. | Chegadas agregadas por bins se parecem; C5 iniciou a taxa agregada nominal sem perdas. | C3/C5 não são repetidos por distribuição, além de variar 32/16 threads por fonte; condições de host/ordem podem diferir. | **Inconclusiva:** a distribuição pode afetar o escalonamento, mas não se pode atribuir a degradação ao número de fontes. |
| **H4 — Limitação secundária dos geradores** | Atrasos submit→início tornam-se grandes em todas as fontes em momentos tardios; p95 agregado 145,7 ms e máximos até 429,5 ms; threads bloqueadas por HTTP demorado são mecanismo plausível. | Inícios totais permanecem em 128,65/s; todas as tentativas drenam sem perda/cancelamento. | Não há CPU por fonte nem medição direta da fila privada; comparação temporal depende do alinhamento. | **Parcialmente sustentada como efeito secundário:** há atraso operacional observado no executor de fontes, aparecendo após a espera da vítima; não há perda de requisições demonstrada. |
| **H5 — Interferência operacional do host** | Fontes e vítima compartilham host sem limites de CPU; CPU por operação cresce durante C5 e acompanha agregadamente host busy (Pearson descritivo ~0,75 em 21 bins completos). | Host busy médio observado ~29,8%, máximo ~36,6%; memória disponível mínima ~7,7 GiB; não há reinicialização, perda ou erro registrado. | CPU do host é agregada; sem CPU individual das fontes, frequência, pressão por núcleo, temperatura ou scheduler tracing; correlação dentro de uma execução não prova mecanismo. | **Compatível, mas não demonstrada:** falta evidência de esgotamento global de CPU/memória, mas não se eliminam interferências locais ou de frequência/escalonamento. |
| **H6 — Aproximação da capacidade do pool** | Demanda de CPU aproximada 1,88/2 cores; workers ativos médios 1,87/2, ambos ocupados em 90,5% do período; espera e pendência elevadas acompanham isso. | Não houve falhas HTTP; o backlog recuou e drenou; a capacidade não foi buscada sistematicamente. | Serviço varia dentro da execução e entre execuções; CPU Docker inclui outros processos do contêiner; só um C5. | **Sustentada para esta execução como alta ocupação/folga pequena;** não demonstra capacidade máxima ou saturação permanente. |

As avaliações não são mutuamente exclusivas. O mecanismo melhor sustentado é alta ocupação do pool combinada com serviço computacional mais lento/variável, que produz espera; o aumento subsequente da duração HTTP também cria atraso nos geradores. A origem da mudança do tempo de serviço segue aberta.

## I. Limitações

- Há somente uma repetição C5 e uma repetição C3 ON. Os resultados não caracterizam a variabilidade entre execuções.
- A mesma seed mestra não assegura fluxos agregados iguais entre fontes diferentes.
- C3_OFF não mede etapas internas; não serve para decomposição ON/OFF.
- Não há métricas de CPU por fonte, perfil por núcleo, frequência de CPU, temperatura, pressão de escalonamento, nem limites de CPU/memória nos contêineres.
- A CPU Docker é uso do contêiner em percentual que pode superar 100%; não é CPU por operação nem percentual de capacidade do host.
- Espera submit→worker incorpora fila, IPC, serialização e escalonamento. O pending derivado não é profundidade exata da fila privada.
- Não há observação de conexões que falharam antes do handler; registros de handler não contabilizam toda conexão TCP recebida.
- Início de HTTP é observado no cliente e não comprova chegada à vítima. Fim do handler não comprova entrega ao cliente.
- O relógio comparável permite alinhamento global, mas brackets de até ~60 ms reduzem a precisão de coincidências em 100 ms. A correlação por ID de durações não requer subtração de relógios entre processos.
- O comportamento de `/medium` não generaliza automaticamente para `/light`, `/expensive`, outra vítima, outro host ou ataques.
- Métricas de chegada e percentis são estatísticas descritivas de janelas curtas, não testes de aderência ou intervalos inferenciais.

## J. Conclusões

1. **Progressivo ou transitório?** A espera cresceu de modo progressivo/transitório ao longo da janela: início da elevação perto de 7–9 s, máximo por volta de 14–16 s, redução parcial nos segundos finais. Não foi apenas um pico isolado e não voltou ao estado inicial antes do fim da geração.
2. **A espera acompanha a maior parte do aumento HTTP?** Sim, descritivamente: delta médio de espera C5−C3 159,90 ms ante delta HTTP 160,04 ms; correlação por requisição 0,992 em C5. Isso é associação/decomposição aritmética, não prova causal.
3. **Houve operações pendentes?** Sim, observáveis como submitted→worker-start: média temporal alcançou cerca de 58, pico 62. Não é profundidade da fila exata. Drenou até 250 ms depois do fim no bin disponível.
4. **Workers ocupados nos períodos de maior espera?** Sim. A média ficou próxima de 1,99 dos dois workers nos segundos de maior espera; ambos ficaram ocupados durante 90,5% dos 20 s.
5. **Atrasos nos geradores?** Sim, principalmente de submissão até início da tarefa e concentrados tardiamente, com p95 por fonte entre 3,69 e 312,14 ms. Todas as requisições foram iniciadas/concluídas e drenadas; não se demonstrou perda.
6. **Distribuição temporal de chegada diferente?** Não foi encontrada diferença relevante na dispersão agregada por bins de 100 ms/250 ms/1 s. A sequência não é idêntica e bins não descrevem cada microintervalo.
7. **Degradação causada por quatro fontes?** Não pode ser atribuída ao número de fontes. O arranjo também muda threads por contêiner; só uma execução por cenário está disponível e as condições não isolam causalmente o efeito.
8. **Aproximação da capacidade do pool?** Sim, os dados sustentam alta ocupação efetiva e folga pequena dos dois workers nesta execução. Não sustentam um máximo de capacidade, saturação permanente, nem taxa-limite.
9. **Interferência do host?** Não há sinal de exaustão agregada de CPU ou memória. O crescimento do tempo CPU/op e a covariação com host busy são pistas, não diagnóstico causal. Interferência por frequência, escalonamento local ou competição de fontes continua possível.
10. **O que permanece inconclusivo?** Por que o tempo de CPU da mesma operação variou entre C3 e C5 e ao longo de C5; qual parte se deve ao host, compartilhamento de fontes, frequência ou variabilidade de execução; se o efeito de distribuição é reproduzível; e qual é a capacidade máxima em condições estáveis.

## K. Recomendações

- Encerrar esta investigação offline como suficiente para caracterizar o episódio de C5, sem afirmar causa definitiva. Não há uma lacuna que exija nova carga antes de continuar o planejamento científico.
- Manter 64 RPS como referência operacional preliminar é razoável com base nas execuções curtas já documentadas, mas não como garantia universal de estabilidade. Confirmar condições e repetibilidade na campanha científica conforme seu protocolo.
- Não tratar C5 (128 RPS, quatro fontes) como configuração estável candidata sem revisão: ela cruzou o guarda de espera, atingiu concorrência/pending muito elevados e apresentou alta ocupação do pool. Excluí-la como candidata de estabilidade não significa descartar a execução nem afirmar capacidade máxima.
- Se uma decisão futura depender de atribuir causalmente a degradação ao número de fontes ou à frequência/host, então seria necessária uma execução complementar instrumentada e controlada, com medidas de host por núcleo/frequência e arranjo de fontes isolado. Isso não é requerido para encerrar a caracterização exploratória atual e não foi executado aqui.
- Nenhum detector, limiar, feature, parâmetro de ataque ou autoridade D3 foi alterado ou calibrado com estes resultados. A decisão entre mecanismos de ataque continua com o orientador.

## Apêndice — rastreabilidade e reprodução

Script desta análise: [`analyze.py`](analyze.py). Comando executado:

```bash
PYTHONPATH=. .venv/bin/python -B reports/capacity_exploration_20261104/c5_offline_investigation/analyze.py
```

O script falha se status, drenagem, verificação, captura, IDs ou integridade dos logs não satisfizerem as verificações codificadas. Não cria contêineres e não envia tráfego. O horizonte vem da configuração efetiva de cada execução; P5 é 12 s e as principais são 20 s.

Na revisão do script, foi corrigida a interpretação do horizonte de P5 para usar seus 12 s configurados, em vez de aplicar indevidamente 20 s a todas as execuções. Assim, a taxa P5 reportada é 1.530/12 = 127,5 RPS, não 76,5 RPS. Esta correção afeta somente esta análise derivada; não altera os dados nem os scripts da campanha.

Arquivos derivados:

- `analysis_manifest.json`: revisão, IDs, regra de alinhamento, fórmulas, limitações e SHA-256 das entradas.
- `artifact_inventory.csv`, `inventory_note.json`: presença e integridade dos logs, capturas, verificações e writers.
- `run_comparison.csv`, `source_details.csv`, `paired_wait_http_association.csv`: resumos, fontes e associação pareada.
- `timeline_1s.csv`, `timeline_250ms.csv`, `timeline_100ms.csv`, `arrival_dispersion.csv`: séries temporais, bins e dispersão de chegadas.
- `c3_c5_timeline_1s.png/.svg`, `c5_detailed_timeline_250ms.png/.svg`, `c5_sources_timeline_250ms.png/.svg`: figuras referenciadas acima.

Os artefatos brutos permanecem em `experiment_results/capacity-exploration-20261104/<run>/`; não foram copiados nem editados. Os eventos de captura reportaram zero perdas de kernel; as validações das cinco features foram aceitas em todas as execuções inventariadas. Os writers de fonte/vítima em execuções ON/P5 não registraram drops, erros de escrita ou fila restante.
