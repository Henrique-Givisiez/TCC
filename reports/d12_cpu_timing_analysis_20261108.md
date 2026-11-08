# D1.2 — Análise offline dos tempos CPU

## Síntese e recomendação

**O inspect domina a cauda lenta desta execução; stats também contribui, sobretudo no POST.** Das cinco aquisições nominais >50 ms, quatro têm inspect como maior etapa; ele representa 74,04% do tempo somado dessas cinco aquisições. Processamento e validação são muito pequenos. Persistência ocorre após received e não compõe a duração de aquisição. Agendamento contribui para rejeições, mas não explica sozinho a cauda.

**Avançar para D2 delimitado é justificável; iniciar campanha ou prometer 95% ainda não.** A carga aumentou fortemente a latência HTTP, mas não reproduziu os timeouts e a indisponibilidade CPU muito mais grave do F96 anterior. Os resultados localizam um componente a investigar; não demonstram a causa interna da demora do daemon nem validam uma otimização.

## A. Integridade e tempo

Raiz analisada: `/home/henrique-givisiez/tcc_cpu_timing_d11_lV4HA6Vy`. HEAD e proveniência da execução: `3de67e597135ab3e52c156077c48382ced25d627`, working tree da execução registrada limpa. Run ID: `148c1ed5782542129544e1063a386498`.

Confirmadas 242 associações 1:1 por run_id, sequência 1–242 e contêiner `48805d80887c6403029a26347bf53890d2603e87ae5ce3c9e29680222ec2b465`. Inícios/agendamentos monotônicos conferem com os tempos relativos à origem; received diagnóstico coincide com received científico convertido à base absoluta. Todas as aquisições têm checkpoints e nenhum acquisition_error. O replay oficial `assign_cpu` revalidou deltas/referências, marcador e summary.

Execução e certificação completed; progression_allowed=true; diagnóstico collection_complete=true, collector_failure=null. 242 snapshots, zero oportunidades perdidas e zero erro fatal. CSV/PCAP aceitos: 65892 pacotes e zero descartes em ambos.

Fases das medições pelo início real da aquisição: PRE [0,30), ATTACK [30,150), POST [150,240): **30/120/90 chamadas**. Cauda separada: sequência 241 em 240,980394910 s (18,698 ms de aquisição), sequência 242 em 241,994875349 s (8,809 ms). Não entram nas estatísticas nominais.

## B. Tempos por etapa

Unidade: **ms**, inclusive folga. Quantis por interpolação linear em (n−1)p. Checkpoints delimitam intervalos instrumentados, não CPU exclusiva da operação: incluem espera e possível preempção. Arredondamento a três casas; valores submicrossegundo podem aparecer como 0,000.

### PRE — n=30
| Etapa | Média | p50 | p90 | p95 | Máximo |
| --- | --- | --- | --- | --- | --- |
| atraso de início | 0.345 | 0.387 | 0.421 | 0.430 | 0.570 |
| inspect | 3.756 | 4.289 | 4.922 | 5.216 | 6.079 |
| validação | 0.008 | 0.008 | 0.009 | 0.010 | 0.011 |
| stats | 4.691 | 4.804 | 5.528 | 5.532 | 6.889 |
| processamento até recebimento | 0.009 | 0.008 | 0.010 | 0.011 | 0.013 |
| aquisição total | 8.498 | 9.319 | 10.199 | 10.788 | 13.028 |
| delta CPU | 0.199 | 0.191 | 0.227 | 0.239 | 0.428 |
| serialização | 0.077 | 0.077 | 0.088 | 0.089 | 0.090 |
| write | 0.052 | 0.048 | 0.072 | 0.073 | 0.074 |
| flush explícito | 0.002 | 0.002 | 0.002 | 0.002 | 0.004 |
| fsync | 8.481 | 8.343 | 8.895 | 9.609 | 14.702 |
| folga até próximo agendamento | 982.199 | 981.527 | 985.335 | 985.818 | 986.111 |

### ATTACK — n=120
| Etapa | Média | p50 | p90 | p95 | Máximo |
| --- | --- | --- | --- | --- | --- |
| atraso de início | 0.888 | 0.147 | 0.259 | 1.345 | 32.058 |
| inspect | 5.445 | 2.491 | 2.819 | 16.004 | 216.591 |
| validação | 0.006 | 0.006 | 0.007 | 0.008 | 0.010 |
| stats | 5.212 | 4.499 | 5.602 | 9.195 | 23.574 |
| processamento até recebimento | 0.009 | 0.009 | 0.011 | 0.011 | 0.014 |
| aquisição total | 10.693 | 7.001 | 8.154 | 26.418 | 233.003 |
| delta CPU | 0.202 | 0.198 | 0.223 | 0.241 | 0.284 |
| serialização | 0.083 | 0.081 | 0.096 | 0.104 | 0.128 |
| write | 0.131 | 0.048 | 0.262 | 0.355 | 5.600 |
| flush explícito | 0.002 | 0.002 | 0.003 | 0.004 | 0.015 |
| fsync | 4.757 | 4.160 | 5.448 | 7.002 | 19.922 |
| folga até próximo agendamento | 983.126 | 988.038 | 988.842 | 988.918 | 989.157 |

### POST — n=90
| Etapa | Média | p50 | p90 | p95 | Máximo |
| --- | --- | --- | --- | --- | --- |
| atraso de início | 2.925 | 0.294 | 5.476 | 19.798 | 65.633 |
| inspect | 5.667 | 3.716 | 8.028 | 16.802 | 77.713 |
| validação | 0.007 | 0.007 | 0.009 | 0.010 | 0.021 |
| stats | 6.548 | 4.716 | 12.325 | 15.592 | 58.191 |
| processamento até recebimento | 0.009 | 0.008 | 0.010 | 0.011 | 0.027 |
| aquisição total | 12.266 | 8.578 | 25.401 | 29.710 | 98.035 |
| delta CPU | 0.191 | 0.189 | 0.221 | 0.233 | 0.442 |
| serialização | 0.080 | 0.078 | 0.091 | 0.097 | 0.239 |
| write | 0.117 | 0.051 | 0.077 | 0.084 | 5.132 |
| flush explícito | 0.002 | 0.002 | 0.002 | 0.002 | 0.004 |
| fsync | 9.786 | 8.099 | 12.974 | 15.578 | 59.926 |
| folga até próximo agendamento | 974.488 | 982.622 | 985.619 | 986.042 | 989.885 |

| Fase | >25 ms | >40 ms | >50 ms | >100 ms |
| --- | --- | --- | --- | --- |
| PRE | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) |
| ATTACK | 8/120 (6.67%) | 3/120 (2.50%) | 3/120 (2.50%) | 1/120 (0.83%) |
| POST | 11/90 (12.22%) | 3/90 (3.33%) | 2/90 (2.22%) | 0/90 (0.00%) |

As cinco aquisições >50 ms permitem decomposição direta, mais forte que mera correlação entre séries:

| Sequência | Início relativo s | Total ms | Inspect ms | Stats ms |
| --- | --- | --- | --- | --- |
| 111 | 110.985755 | 51.757 | 36.535 | 15.185 |
| 121 | 120.985784 | 56.686 | 33.072 | 23.574 |
| 146 | 145.976180 | 233.003 | 216.591 | 16.371 |
| 181 | 180.981291 | 75.810 | 17.588 | 58.191 |
| 231 | 230.990872 | 98.035 | 77.713 | 20.287 |

Em ATTACK, inspect responde por 83,82% do tempo somado das três aquisições >50 ms; POST, por 54,82% das duas. No conjunto, 381,500 dos 515,290 ms pertencem ao intervalo inspect (74,04%). Em condições típicas, stats é tão ou mais caro: medianas inspect/stats ATTACK=2,491/4,499 ms e POST=3,716/4,716 ms. Portanto “inspect dominante” refere-se principalmente à **cauda**, não a todas as aquisições.

Aquisição média sobe PRE→ATTACK→POST: 8,498→10,693→12,266 ms; p95: 10,788→26,418→29,710 ms. A pior chamada ocorre no ataque (233,003 ms), mas POST tem mais chamadas >25 ms (12,22% contra 6,67%). Atrasos de início >25 ms: 0/1/3; >50 ms: 0/0/1. Há piora durante a carga e persistência temporal no POST, sem prova da causa sistêmica.

Fsync tem custo relevante, mas é posterior ao recebimento. Folgas mínimas após o trabalho da iteração: PRE 975,451 ms, ATTACK 760,058 ms, POST 876,356 ms. Não há evidência de que a persistência da própria iteração tenha invadido o agendamento seguinte. Isso não exclui interferência indireta de I/O no host. Write inclui eventual flush implícito do arquivo line-buffered; flush explícito não mede sozinho todo o custo de descarga.

## C. Disponibilidade científica

Aplicadas as regras existentes: brackets inteiros próximos às fronteiras em ±50 ms, received até o fechamento, referência válida e um candidato por janela. Sem interpolação ou tolerância adicional. Fases de disponibilidade usam a **janela-alvo**, que não é a mesma classificação do início real da aquisição.

Grade de replay: 241 janelas, devido à cauda HTTP após 240 s. Nominal=240; [240,241) é adicional e tem CPU válida, obtida na aquisição 241. A aquisição 242 aponta para janela 241, fora dessa grade. As fases WARMUP/PRE/ATTACK fixas do relatório interno de qualidade C1.3.4 não foram reutilizadas como fases D1.1: os recortes abaixo foram calculados explicitamente sobre os valores retornados pelo replay.

| Recorte | Esperadas | Válidas | Ausentes | Cobertura | Tardias | Desalinhadas | Sem referência | Maior lacuna | CoV potencial |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PRE | 30 | 29 | 1 | 96.67% | 0 | 0 | 1 | 1 | 24 |
| ATTACK | 120 | 111 | 9 | 92.50% | 7 | 2 | 0 | 2 | 79 |
| POST | 90 | 75 | 15 | 83.33% | 9 | 6 | 0 | 2 | 23 |
| Nominal | 240 | 215 | 25 | 89.58% | 16 | 8 | 1 | 2 | 126 |
| [30,240) | 210 | 186 | 24 | 88.57% | 16 | 8 | 0 | 2 | 102 |

Não há erro de aquisição, snapshot inválido, múltiplos candidatos ou oportunidade perdida. Rejeições nominais: uma janela inicial sem referência, 16 por atraso e oito por desalinhamento. A regra verifica desalinhamento antes de atraso: categorias exclusivas por prioridade, não causas independentes. Maior lacuna=2 janelas, por exemplo [145,147), [180,182), [190,192) e [230,232).

CoV exige seis observações consecutivas e reinicia nas ausências: cai de 215 observações CPU válidas para 126 oportunidades nominais; [30,240), de 186 para 102. São limites de disponibilidade, sem baseline, thresholds ou decisões calibradas. [30,240) tem 210 janelas neste diagnóstico, não as 360 da seleção científica C1.3.4; as porcentagens não certificam elegibilidade da campanha.

**Contrafactual temporal**, mantendo durações, referências e atrasos medidos: deslocar os brackets de lead 25→40→50 ms daria 215→222→227 janelas nominais válidas (89,58→92,50→94,58%) e 126→154→178 oportunidades CoV. Com lead 50 ms e atraso artificialmente zero, o teto seria 233/240 (97,08%), CoV 203/240 (84,58%). Em [30,240), esse último teto é 204/210 para CPU e 179/210 para CoV.

Hipóteses explícitas: novo lead não mudaria as durações/referências, e os brackets poderiam ser transladados mantendo a viabilidade dos snapshots. Isso é análise geométrica, não novas observações nem previsão da execução. Durações finais >50 ms e referência >100 ms continuam inviáveis mesmo com início ideal; nesse teto há cinco impedimentos por duração final e um adicional por referência, além da janela inicial. Só mudar agendamento não demonstra 95% para CoV.

## D. Representatividade da carga

Emissão ofensiva comprovada: primeiro/último início HTTP em 30,009130494/149,983663146 s. Nenhum início ofensivo POST; 96 conclusões ofensivas ocorrem em POST. Fechamento do evento em 150,404678179 s e drain até 151,856715303 s não representam extensão do intervalo de emissão HTTP.

Taxas configuradas: legítimos 2×8=16/s; ofensivos 2×32=64/s. Em 120 s de emissão: 7413 admissões (61,78/s), 363 abandonos antes de HTTP, 7050 inícios/conclusões (58,75/s), todos com resposta. A taxa configurada implica expectativa de oportunidades, não 7680 requisições garantidas. Identidades por fonte: normal_1/2=1934/1869; attack_1/2=3519/3531. Totais=3803 legítimas e 7050 ofensivas; uma legítima inicia após 240 s.

| Fase de início HTTP | Origem | Inícios | Inícios/s | Respostas | Falhas | Duração média ms | p50 ms | p95 ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PRE | normal | 463 | 15.43 | 463 | 0 | 42.03 | 34.91 | 73.68 |
| ATTACK | normal | 1918 | 15.98 | 1918 | 0 | 1309.50 | 1532.63 | 1835.58 |
| ATTACK | attack | 7050 | 58.75 | 7050 | 0 | 1288.75 | 1526.56 | 1846.36 |
| POST | normal | 1421 | 15.79 | 1421 | 0 | 65.26 | 34.21 | 77.50 |

Todos os resultados HTTP são response, status 200; zero falhas HTTP, transporte, client_error ou incompletas, inclusive legítimas. `completed_integral` descreve essa ausência de falhas detectadas, **não ausência de degradação de latência**.

A duração média legítima no ataque aumenta 31,16 vezes em relação ao PRE (42,03→1309,50 ms); p95 vai de 73,68 para 1835,58 ms. Os deltas CPU brutos, inclusive os rejeitados para a grade, têm médias PRE/ATTACK/POST de 49,98/228,29/54,93% na convenção Docker. Isso é evidência de carga, não média da feature CPU válida de um segundo. Nos primeiros cinco segundos POST, a duração legítima média é 469,28 ms; entre 155–160 s cai para 42,31 ms, e de 160–240 permanece perto de 42–44 ms. Há cauda de processamento/latência no início POST; a captura mostra recuperabilidade mais rápida que o F96 anterior.

Comparação com o **F96 aprovado** `F96_fix_400ca8f_20261108_144956`, imagens e parâmetros de carga iguais. Para evitar comparar POSTs de 90/120 s, usam-se apenas os primeiros 90 s POST de ambos; o controle abaixo usa 30 s imediatamente anteriores ao ataque original:

| Métrica | F96 anterior | D1.1 |
| --- | --- | --- |
| Controle legítimo, taxa / duração média | [120,150): 16,87/s / 49,55 ms | [0,30): 15,43/s / 42,03 ms |
| Admissões ofensivas /120 s | 7203 / 60,03/s | 7413 / 61,78/s |
| Abandonos antes do HTTP | 1532 | 363 |
| Inícios ofensivos /120 s | 5671 / 47,26/s | 7050 / 58,75/s |
| Falhas ofensivas no ataque | 5187/5671 (91,47%) | 0/7050 |
| Inícios legítimos no ataque | 1870 / 15,58/s | 1918 / 15,98/s |
| Falhas legítimas no ataque | 1741/1870 (93,10%) | 0/1918 |
| Duração legítima média no ataque | 2015,55 ms | 1309,50 ms |
| Primeiros 90 s POST: falhas legítimas | 395/1451 (27,22%) | 0/1421 |
| Primeiros 90 s POST: duração legítima média | 617,36 ms | 65,26 ms |
| CPU válida na janela de ataque de 120 s | 30/120 (25,00%) | 111/120 (92,50%) |

**Inferência fundamentada:** D1.1 é representativo de carga concorrente e suficiente para localizar etapas lentas — inclusive um inspect de 216,59 ms. **Limitação importante:** não reproduz o regime de timeouts e lacunas prolongadas do F96, nem garante que a mesma composição de custos prevaleceria nele. O período pré-ataque foi encurtado, o contexto de execução é distinto e não há comparação pareada com/sem instrumentação. Imagens iguais não provam igualdade de recursos efetivos/estado do host; o D1.1 não registrou effective_resource_probe na tentativa. Os checkpoints não medem serviço interno do daemon nem isolam preempção/espera no socket.

## E. Respostas e prioridades para D2

1. **Gargalo:** inspect é o principal componente da cauda >50 ms; stats é custo relevante e domina uma das cinco aquisições lentas. Processamento/validação/delta/serialização não são alvos prioritários pelos tempos observados. Fsync é relevante no ciclo completo, mas está fora do bracket e havia ampla folga; não há suporte para escolhê-lo como primeira correção.
2. **Piora no ataque?** Sim para p95/cauda e disponibilidade frente ao PRE; POST permanece pior em vários indicadores. Não há prova de que a carga ofensiva seja a única causa da demora de aquisição.
3. **Menor alteração com ganho temporal quantificado:** antecipar dentro da tolerância, até 50 ms, preservando as mesmas consultas. Pode melhorar disponibilidade, mas o contrafactual não resolve CoV e não é suficiente para declarar o problema corrigido. É ajuste auxiliar, não substituto da investigação de inspect.
4. **Alvo prioritário de D2:** reduzir o custo de inspect por amostra mantendo prova equivalente de identidade/geração. Cachear o objeto Container e chamar apenas stats elimina a inspeção nova, mas **não preserva sozinho** StartedAt/RestartCount/estado por aquisição. Uma cache simples não está justificada como correção científica. Separar o bracket específico de stats do bracket de inspeção é outra proposta possível, mas muda a definição operacional da evidência e não remove recebimentos tardios; exige análise prospectiva, validação do read Docker dentro do novo bracket e contrato explícito. Não basta estreitar timestamps retrospectivamente.
5. **Avançar para D2?** Sim, como implementação/protótipo delimitado e explicitamente revisado para preservar ou declarar a mudança das evidências de geração; não como autorização de campanha nem promessa de disponibilidade. Os dados justificam priorizar inspect, mas ainda não escolhem uma forma segura de suprimi-lo.
6. **Representatividade:** suficiente para diagnóstico de etapas sob carga e priorização; insuficiente para certificar a solução no regime severo do F96. A validação posterior precisará alcançar esse regime ou documentar claramente que ele não reapareceu, sem alterar taxas para forçar aprovação.

Nenhuma correção, detector, calibração, teste automatizado ou experimento foi executado nesta atividade. Apenas leituras/cálculos offline e criação deste relatório; originais preservados, sem commit.
