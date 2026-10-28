# Encerramento de D2 e proposta operacional de D3

Estado em 28/10/2026: **D2 encerrado documentalmente; D3 proposto, sem execução autorizada por este documento**. Nenhum experimento foi executado nesta tarefa. Manifestos históricos, revisões e comparação consolidada permanecem preservados.

## Evidências e resultado de D2

Autoridade: [manifesto v4](../experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v4.json), SHA256 `020128bf603a11e65d5ba239bfc260cd4527fa303c61c8c6ed660193af2dc9d8`. O campo histórico `prepared_offline_not_executed` não foi reescrito: a conclusão decorre das sete revisões posteriores, não desse campo. O [registro de encerramento](../experiment_results/development-d2-endpoint-comparison-20261027/analysis/d2_documentary_closure_20261028.json) identifica e resume cada revisão, com hashes, e referencia a [comparação consolidada](../experiment_results/development-d2-endpoint-comparison-20261027/analysis/d2_endpoint_comparison.md) e seu JSON.

As sete revisões apontam aprovação dos critérios, dataset válido/elegível e ausência de falha técnica, problema do gerador ou degradação pelos critérios de D2. Houve 120/120 ticks úteis suportados da vítima em cada run e drenagem observada de aproximadamente 6–12 ms. Isso não certifica frescor de cada leitura Docker nem recuperação sob ataque. Alguns registros ainda indicavam intervalo mínimo de repouso pendente no instante da revisão; aprovação dos dados não equivale a aprovação automática da próxima execução.

Condições: uma vítima, proxy estático, quatro clientes, 4 RPS agregados, sem ataque; 150 s nominais, warmup de 30 s e 120 s úteis. Nas **seis execuções comparativas**, todas as starts úteis terminaram em 2xx, sem falhas HTTP/transporte/cliente, respostas outras ou incompletas; captura CSV/PCAP com zero drops de kernel.

| Endpoint | Starts A / B | RPS efetivos A / B | Média 2xx A / B (ms) | p95 2xx A / B (ms) | CPU média vítima A / B (%) |
|---|---:|---:|---:|---:|---:|
| `/light` | 474 / 473 | 3,950 / 3,942 | 9,03 / 9,19 | 44,47 / 44,31 | 0,91 / 0,95 |
| `/medium` | 474 / 473 | 3,950 / 3,942 | 18,66 / 19,35 | 54,30 / 56,69 | 4,53 / 5,10 |
| `/expensive` | 474 / 473 | 3,950 / 3,942 | 110,59 / 104,78 | 149,02 / 141,30 | 37,57 / 37,97 |

**Probe separado:** `d2_probe_expensive_4rps`, seed própria, 507 starts/2xx úteis, 4,225 RPS, média 108,88 ms, p95 146,04 ms e CPU média 43,07%. Sem falhas/incompletas, zero drops e sem acumulação pelo critério de concorrência do cliente. Serviu para manter a taxa comum de 4 RPS; não é uma terceira réplica de `/expensive` nem integra os contrastes das seis execuções.

**Contrastes entre endpoints na mesma seed:** A usa seed `13280835547037124428` na ordem light→medium→expensive; B usa `15642065855960901168` na ordem inversa. O aumento de p95 expensive−medium foi +94,72 ms em A e +84,61 ms em B; medium−light foi +9,83 e +12,39 ms. São comparações planejadas com agenda aleatória comum dentro de cada réplica, sem garantia de tempos efetivos idênticos.

**Variação A/B por endpoint:** as seeds são distintas. As diferenças de p95 A−B foram +0,16 ms (`/light`), −2,39 ms (`/medium`) e +7,72 ms (`/expensive`). Não são contrastes com a mesma seed; combinam variação de réplica, período e ambiente. A ordem inversa reduz assimetria de precedência, mas não elimina deriva. Duas réplicas sustentam descrição exploratória, não inferência de capacidade máxima, razão causal de custo ou SLO. Os custos reservados são 10 mil/100 mil/1 milhão de iterações; não se convertem diretamente em milissegundos ou multiplicadores de capacidade.

## D3: matriz curta e prioridade

O [roadmap](new_campaign_protocol_proposal_20261027.md) (§2.1–3.1) e o [plano documental](../experiments/protocols/development_service_plan_20261027.json) separam custo (`D3_cost`) de taxa (`D3_rate`). Propõe-se antecipar o contraste de custo, mantendo os fatores separados. D3 permanece DEVELOPMENT, com serviço e suporte dos geradores como objetivos; detectores não escolhem cargas.

Fixos: uma vítima, proxy estático, autoscaling desligado, sources em containers, quatro clientes legítimos em `/medium`, **4 RPS por cliente = B=16 RPS**, um atacante nas condições ofensivas, ataque contínuo. Pool da vítima=2; timeout=2 s nas duas classes; orçamento de envio=64 por classe; monitoramento/poll=1 s e histórico=30 s. Registrar imagens, limites efetivos, código e ambiente; pool=2 não é quota de CPU. `work_units`/`sleep_seconds` não alteram os endpoints reservados.

| Etapa/condição | Ataque | Atacantes | RPS por atacante / agregados | Contraste e ordem proposta |
|---|---|---:|---:|---|
| C — controle | Desligado | 0 | 0 / 0 | Controle benigno correspondente, mesmos limites de fase |
| M4 — âncora | `/medium` | 1 | 4 / 4 | Primeiro membro do contraste de custo |
| E4 — custo | `/expensive` | 1 | 4 / 4 | E4−M4: muda somente endpoint ofensivo |
| M8 — intensidade | `/medium` | 1 | 8 / 8 | M8−M4: muda somente taxa ofensiva |
| E8 — intensidade | `/expensive` | 1 | 8 / 8 | E8−E4: muda somente taxa ofensiva; condicionado ao suporte de E4 |

Plano máximo: duas seeds DEVELOPMENT novas, auditadas contra as partições históricas/futuras, iguais entre condições dentro de cada bloco. A: C→M4→E4→M8→E8; B: C→E4→M4→E8→M8. Concluir/revisar o par de custo de cada bloco antes de subir intensidade; sem progressão automática. A inversão é balanceamento parcial, não elimina período. Controle compartilhado cria dependência entre contrastes; preservar o bloco na análise. Pilotos não entram como réplicas desta matriz. Não incluir variação de número de atacantes neste D3.

**Justificativa das cargas.** A [síntese D1](../experiment_results/development-d1-20261027/analysis/d1_final_synthesis_capturefix_v2.json) encontrou, em 16 RPS, 15,825–15,875 starts/s, 100% 2xx, p95 58,37–58,62 ms e CPU média 21,57–22,40%. É candidato nominal com margem maior que 64 RPS, onde CPU média chegou a 89,05–94,75%, apesar de aprovação do serviço. Usar 64 RPS como base confundiria efeitos ofensivos com alta ocupação legítima. Os 32 RPS também passaram nas tentativas aceitas, mas não são necessários para este contraste; a tentativa histórica L04_B com problema de captura não substitui a repetição CF1 válida.

Ataque inicial de 4 RPS ancora-se no `/expensive` isolado aceito em D2. **D2 não valida B=16 mais A=4**, nem a execução de uma origem ofensiva em lugar de quatro origens legítimas. O passo 4→8 é uma duplicação curta para procurar impactos distintos, mantendo N=1; 8 RPS em `/expensive` ainda depende de piloto. D1 com `/medium` isolado não certifica a mistura nem permite extrapolar linearmente CPU. Se 4 e 8 não separarem impactos úteis, registrar esse resultado e propor nova autoridade; não aumentar indefinidamente nem escolher taxas por recall/F1.

## Tempos e métricas por classe/fase

Tempos candidatos, iguais em todas as condições: warmup `[0,30)`, PRE útil `[30,150)`, ACTIVE `[150,270)` com emissão contínua por 120 s, POST `[270,390)` com apenas legítimos; total nominal **390 s**, depois até 30 s de DRAIN e pelo menos 60 s de repouso após cleanup. O controle usa as mesmas janelas de referência. Auditar início/fim efetivos de emissão ofensiva e conclusões, além dos marcos nominais; contabilizar desvios nas fronteiras.

Os 30 s de warmup e blocos úteis de 120 s preservam o suporte observado em D1/D2 e permitem quatro coortes de 30 s por fase. PRE com 16 RPS oferece cerca de 1.920 starts, ACTIVE com 4 RPS ofensivos cerca de 480; são expectativas nominais, não suporte garantido. D1/D2 sustentam observação benigna nessas durações, **não validam estabilização da mistura, memória de detectores ou POST suficiente**. Piloto deve verificar essas três questões e o limite de drenagem. POST final sem recuperação observada será reportado como censura à direita, não como recuperação nem como motivo para excluir o run.

| Classe/fase | Medidas e denominadores |
|---|---|
| Legítimos: PRE, ACTIVE e POST | Oferta nominal, starts/s agregado e por origem, aderência starts/oferta; 2xx/s por instante de término; sucessos/falhas/incompletas por coorte de início, divididos pelas starts da coorte; média/p50/p95 das durações 2xx com n explícito. Contrastar ACTIVE/PRE e com C da mesma seed; medir persistência no POST. |
| Ataque: ACTIVE; términos em POST/DRAIN | Mesmas contagens por origem/endpoint; separar HTTP, transporte, cliente, timeout e respostas outras. Medir emissão efetiva, in-flight no cliente, pendências nas fronteiras, drenagem e divergência oferta→starts→términos. Não chamar in-flight de fila medida da vítima. |
| Ambas: coortes de 30 s e DRAIN | Reconciliar starts=terminadas+abertas no cutoff observado; finais por coorte podem cruzar fases. Registrar late starts, conclusões cruzadas, source_closed, logger_complete e censura. Não subtrair taxas de populações diferentes para estimar falhas. |
| Infraestrutura: todas as fases | CPU total Docker e memória vítima/proxy, conexões/status disponíveis, suporte, gaps e erros de coleta, captura CSV/PCAP e drops. 100% CPU equivale a um núcleo lógico; memória da vítima e memória bruta do proxy usam convenções distintas. |

O p95 dos sucessos pode cair quando pedidos lentos falham: interpretá-lo sempre com falhas, timeouts e suporte. Denominador zero produz null. Ausência de suporte de latência suficiente limita a estimativa, sem apagar a evidência de indisponibilidade.

## Progressão e limites

1. **Antes de executar futuramente:** preparar autoridade própria, seeds, ordem, configs completas, saídas distintas e validação offline; revisão manual e autorização separada. Esta proposta não é manifesto executável nem altera o roadmap histórico.
2. **Piloto limitado:** reservar até três tentativas: C, E4 e, somente se houver observabilidade e encerramento controlado, E8. Verificar regime legítimo, tempos, emissão de uma origem e pressão de concorrência. Não incorporar pilotos à matriz; ajustar desenho apenas prospectivamente e documentar antes de congelar as dez condições.
3. **Integridade técnica:** exigir identidade/hashes e correspondência dos journals, dataset estruturalmente válido, logs completos, captura final única CSV/PCAP com zero drops e saída aceita, lifecycle auditável. Por fase útil, suporte da vítima ≥90% dos ticks esperados e proxy ≥90% por fonte, gaps máximos de 5 s. Falha de captura, monitor ou logger bloqueia a próxima tentativa para diagnóstico; preservar o material, sem retry automático.
4. **Oferta e geradores:** usar inicialmente aderência agregada de 0,8–1,2 por classe e 0,65–1,35 por origem em ACTIVE/PRE aplicáveis, com contagens e suporte explícitos. A insuficiência de starts exige distinguir limite do gerador de pressão de serviço; sem diagnóstico, não atribuir o efeito somente ao endpoint nem subir intensidade. Falha de transporte sob ataque, sozinha, não prova falha do gerador.
5. **Serviço é desfecho:** não aplicar ao ataque o gate benigno de ≥99% 2xx, ≤1% falhas, zero incompletas ou ausência de tendência de degradação. Aumento de duração, falhas, queda de throughput, pendências e recuperação lenta, com coleta íntegra, são resultados válidos. Relatar separadamente integridade, aderência e degradação. CPU alta sozinha não invalida nem autoriza escalada.
6. **Próximo patamar:** somente após revisão de emissão, suporte, cleanup e ≥60 s de repouso, com prontidão novamente observada. Timeout de drenagem de 30 s ou encerramento forçado interrompe progressão e exige separar saturação real de perda de evidência; preservar resultados/censura disponíveis. Se houver degradação forte já em E4, revisar utilidade de E8 antes de prosseguir, sem rejeitar E4. Sem recuperação/prontidão, parar o bloco; não estender ou repetir silenciosamente.

## Calibração e orçamento

Preservar **baseline e calibração benignas por regime legítimo declarado**. Se B=16 for confirmado como nominal, todos os cenários ofensivos de D3/futura avaliação usam o mesmo modelo e os mesmos limiares desse regime. Mudar endpoint ou intensidade ofensiva não autoriza recalibrar. Baixo/alto, se incluídos depois, recebem seus próprios conjuntos benignos; não selecionar regime pela taxa contaminada pelo ataque. DEVELOPMENT, BASELINE, CALIBRATION e TEST permanecem separados, com seeds independentes. D3 não ajusta detectores nem usa TEST; a duração final científica ainda precisa considerar memória dos métodos.

| Parcela máxima proposta | Tentativas | Nominal | DRAIN reservado | Repouso reservado | Total reservado |
|---|---:|---:|---:|---:|---:|
| Pilotos, fora da matriz | 3 | 1.170 s | 90 s | 180 s | 1.440 s = 24 min |
| Matriz, 5 condições × 2 seeds | 10 | 3.900 s | 300 s | 600 s | 4.800 s = 80 min |
| Total máximo | **13** | **5.070 s** | **390 s** | **780 s** | **6.240 s = 104 min** |

Reserva conservadora de repouso após cada tentativa, inclusive a última. Acrescentar até 30 min administrativos para startup, preflights, revisão e cleanup: envelope planejado **134 min**, sujeito a parada se a reserva se esgotar; não limita uma espera segura por intervenção. Zero retries/substituições automáticas. Se E8 não progredir, reduzir o total e registrar matriz incompleta. O custo configurado de US$0,02/vítima-h implica cerca de US$0,0303 para 13×420 s de vítima ativa; é somente contabilidade nominal da vítima, sem proxy, geradores, startup, storage ou custo real do host. Para usar o envelope inteiro como reserva de vítima ativa, o teto contábil seria US$0,0447. Nenhum recurso ou orçamento foi consumido por execução experimental nesta tarefa.
