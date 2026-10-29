# Encerramento de D3_origins — DEVELOPMENT

Estado em 29/10/2026: **encerrado documentalmente com quatro execuções R2 tecnicamente válidas**, quatro tentativas consumidas e nenhuma repetição de A_N1. Este fechamento usa o [manifesto R2](../experiments/protocols/development_d3_origins_20261029/manifest_r2.json), as quatro revisões `*-review-r2.json` e a [comparação R2](../experiment_results/development-d3-origins-20261029/analysis/d3_origins_comparison_r2.md). O [registro JSON de encerramento](../experiment_results/development-d3-origins-20261029/analysis/d3_origins_closure_20261029.json) vincula os artefatos por hash e registra a reprodução offline das métricas e dos contrastes. Não constitui freeze científico de TEST nem autorização de nova coleta.

Condições: quatro clientes legítimos em `/medium`, 16 RPS agregados; ataque contínuo em `/expensive`, 8 RPS nominais agregados. N1=1×8 RPS, 64 workers; N2=2×4 RPS, 32+32 workers. A executou N1→N2, B executou N2→N1, com seeds distintas entre blocos e compartilhadas dentro deles. ACTIVE=[150,270), após warmup 0–30 e PRE 30–150; POST=270–390 s. Envelope autorizado do bloco: quatro tentativas de 18 min, total 72 min; não é uma medição do tempo humano gasto na correção offline.

| Bloco/condição | Starts / RPS ofensivos ACTIVE | Starts / RPS legítimos ACTIVE | 2xx legítimos | Média / p95 legítimos ms | CPU vítima / proxy % |
|---|---:|---:|---:|---:|---:|
| A/N1 | 955 / 7,9583 | 1840 / 15,3333 | 1840 / 100% | 42,47 / 97,17 | 89,10 / 2,33 |
| A/N2 | 885 / 7,3750 | 1841 / 15,3417 | 1841 / 100% | 47,50 / 127,18 | 94,35 / 2,57 |
| B/N2 | 941 / 7,8417 | 1921 / 16,0083 | 1921 / 100% | 42,28 / 98,59 | 92,43 / 2,35 |
| B/N1 | 992 / 8,2667 | 1922 / 16,0167 | 1922 / 100% | 43,14 / 96,71 | 93,62 / 2,43 |

Duração e desfechos seguem coortes de início; RPS=starts/120 s. CPU é percentual Docker, 100%=um núcleo lógico equivalente, sem certificação de frescor de cada tick da vítima. O JSON da comparação conserva PRE/ACTIVE/POST, recursos, pendências, prazo e suporte; não se resumem essas dimensões apenas ao p95 dos sucessos.

| Execução/origem ofensiva | Starts ACTIVE | RPS realizados | RPS nominais |
|---|---:|---:|---:|
| A/N1 attack_1 | 955 | 7,9583 | 8 |
| A/N2 attack_1 | 451 | 3,7583 | 4 |
| A/N2 attack_2 | 434 | 3,6167 | 4 |
| B/N2 attack_1 | 508 | 4,2333 | 4 |
| B/N2 attack_2 | 433 | 3,6083 | 4 |
| B/N1 attack_1 | 992 | 8,2667 | 8 |

N2 iniciou menos ataques que N1 nos dois blocos: −70 starts/−0,5833 RPS em A (−7,33% perante N1) e −51/−0,4250 RPS em B (−5,14%). Perante os 960 starts nominais, N2 realizou 92,1875% em A e 98,0208% em B; N1 realizou 99,4792% e 103,3333%. São contagens de um processo de chegadas aleatório e do envio observado, não prova de descarte ou incapacidade do gerador. Não se transforma déficit perante uma expectativa em perda de registro. A repartição N2 diferiu por 17 starts em A e 75 em B, mantendo 32 workers por origem.

| Contraste N2−N1 na mesma seed | ΔRPS ofensivos | Δp95 legítimo ACTIVE ms | ΔCPU vítima pp | ΔCPU proxy pp |
|---|---:|---:|---:|---:|
| A | −0,5833 | +30,01 | +5,26 | +0,24 |
| B | −0,4250 | +1,88 | −1,20 | −0,08 |

A magnitude do contraste de duração varia muito; o contraste de CPU da vítima muda de sinal. B−A em N1: +0,3083 RPS ofensivos, −0,47 ms de p95 e +4,53 pp de CPU da vítima. B−A em N2: +0,4667 RPS, −28,59 ms e −1,93 pp. As starts legítimas ACTIVE aumentaram 82 em N1 e 80 em N2 entre blocos. B−A combina seed, chegadas, ordem, período e ambiente; não é um contraste com seed comum. Não combinar p95 por média, nem tratar os dois blocos como suporte de um efeito estável ou inferência confirmatória.

**Não é possível isolar causalmente o efeito do número de origens com este desenho e estes dados.** Além das taxas realizadas diferentes, distribuir fontes muda streams aleatórios, processos, sessões, filas e repartição dos workers. A ordem invertida controla precedência apenas parcialmente. Mesmo com 8 RPS e 64 workers nominais agregados constantes, não existe intervenção isolada em identidade/IP. O maior p95 de A/N2, apesar de menos starts ofensivos, não demonstra uma penalidade causal de N2; B não reproduz a magnitude. Não corrigir silenciosamente latência por RPS, não parear retrospectivamente trechos para igualar carga e não inferir equivalência de oferta da seed comum. `full_scheduled_load_verified=false` permanece nas quatro revisões.

As quatro revisões têm integridade técnica, dataset válido/elegível, cleanup e encerramento controlado. Nas quatro, as quatro janelas ACTIVE reprovam duração; sucesso, prazo e critérios de pendências passam. Todas as janelas POST qualificam, sem perda posterior, e a classificação é `recovery_observed`. A primeira confirmação termina no bin 330 s, com horizonte nominal 333 s e evidência efetivamente necessária até 330 s; a decisão batch só fica disponível após fechamento/reconciliação em aproximadamente 390,01–390,02 s, com publicação em UTC própria. Não apresentar 330 s como tempo de publicação em tempo real. Sucesso legítimo de 100% não elimina o comprometimento por duração.

A [revisão original reprovada de A_N1](../experiment_results/development-d3-origins-20261029/analysis/d3_origins_A_N1-review.json), o [diagnóstico](../experiment_results/development-d3-origins-20261029/analysis/d3_origins_A_N1-diagnosis_20261029.json), o manifesto/preflight originais, raw, dataset e `attempt.json` permanecem preservados. A reprovação original foi um falso negativo do adaptador: exigia que `emission_closed` já tivesse `status=completed` e `drained_end_seconds` final, embora o produtor permita respostas em voo após fechar emissão. R2 valida invariantes e evolução de estado separadamente, conservando identidade, tempos, reconciliação e critérios de serviço. O [arquivo anterior do código](../experiments/protocols/development_d3_origins_20261029/revision_r2/source_before/development_d3_origins_processing.py), a [validação da correção](../experiments/protocols/development_d3_origins_20261029/revision_r2/offline_validation.json) e a proveniência das quatro revisões R2 preservam essa cadeia. A_N1 foi reanalisado na mesma execução; A_N2, B_N2 e B_N1 já usaram a autoridade prospectiva R2. A revisão antiga continua reprovada e não é substituída nem promovida a uma quinta tentativa.

D3_origins encerra a exploração de origens nesta sequência. Não recomendar N4, novas intensidades ou repetições exploratórias para procurar uma diferença favorável. O próximo trabalho é fechar a matriz e a avaliação científica no [roadmap atualizado](new_campaign_roadmap_status_20261029.md). Uma investigação causal específica de origens exigiria outro objetivo e controle explícito das chegadas e dos recursos; não é condição automática para avaliar os detectores na matriz enxuta proposta.
