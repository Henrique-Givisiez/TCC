# D3 — proposta prospectiva de revisão da recuperação

Estado: **PROPOSTA NÃO LIBERADA, sem autorização de execução**. Não substitui a autoridade vigente, não altera nem aplica novos rótulos a C/E4 e não libera E8. Os únicos cálculos desta tarefa usam registros sintéticos construídos, sem Docker, HTTP ou simulador. Detectores e calibração permanecem inalterados.

Fontes: [diagnóstico de E4](../experiment_results/development-d3-pilots-20261028/analysis/d3_pilot_E4-recovery-diagnostic_20261028.md), seu JSON e a [regra original](development_d3_pilots_20261028.md). Artefatos novos: [proposta estruturada](../experiments/protocols/development_d3_recovery_revision_proposal_20261028/proposal.json), [avaliação sintética](../experiments/protocols/development_d3_recovery_revision_proposal_20261028/offline_validation.json), [protótipo isolado](../analysis/d3_recovery_rule_candidate_20261028.py) e [testes](../tests/test_d3_recovery_rule_candidate_20261028.py). O protótipo não é importado pelos utilitários operacionais e não recebe dados históricos de C/E4.

## Problemas que a revisão pretende resolver

Em POST_4 de E4, 451 términos 2xx versus 514 em C produziram razão de vazões de 87,7432%, mas as starts também diferiram: 450 versus 513. Com 100% de sucesso e p95 estável, a comparação de vazão absoluta mistura chegada de trabalho e capacidade de atendê-lo. Seeds distintas e geração Poisson impedem tratar a diferença de contagens como efeito ofensivo por definição. Isso não demonstra ausência de efeito: torna necessário observar os estágios intermediários.

Em POST_1, a certificação de emissão terminou 1,5645 ms após 270 s e excluiu todo o bin nominal de 30 s. O código cumpriu a regra congelada; o problema é de desenho, não um erro aritmético demonstrado. A nova regra deve definir previamente como aproveitar exposição realmente pós-emissão, sem tolerância escolhida depois de ver latência ou vazão.

## Regra candidata: carga observada, atendimento e pendências

Manter uma vítima, proxy estático, quatro clientes legítimos `/medium`, 16 RPS nominais e um atacante contínuo `/expensive` nas futuras condições E4-R2/E8-R2. As métricas abaixo referem-se aos legítimos, com o ataque contabilizado separadamente. Não usar CPU como gate único.

Para cada janela efetiva W=[a,b), registrar:

| Estágio/medida | Definição e interpretação |
|---|---|
| Oferta nominal | O_nom=16×(b−a). É expectativa configurada, não contagem de oportunidades reais. |
| Oferta realizada | O_real: oportunidades elegíveis previstas em agenda independente do despacho, por origem, incluindo não iniciadas. Sem essa evidência não distinguir completamente menor chegada de limitação do gerador. |
| Starts | N: tentativas realmente iniciadas. Reportar N/O_nom, O_real/O_nom e N/O_real, agregados e por origem, com atrasos de despacho, oportunidades perdidas e início fora da janela. |
| Términos | D e D_2xx: conclusões dentro de W, quaisquer que sejam as coortes de início. Preservar N/Δ, D/Δ e D_2xx/Δ em RPS, diferenças absolutas e comparação com C como **resultados**. |
| Atendimento da coorte | Entre as N starts em W, proporção conhecida de términos, sucessos 2xx, falhas por tipo, respostas outras e ausências de término até o prazo comum H=b+3 s. Término posterior ao prazo não transforma retrospectivamente o atendimento no prazo em sucesso. |
| Duração | Média/p50/p95 de 2xx da coorte conhecidos até H, sempre com n. Ler junto das falhas/atrasos: o p95 dos sobreviventes pode melhorar quando pedidos lentos falham. |
| Pendências | P_L e P_A: tentativas legítimas/ofensivas persistidas sem término conhecido na fronteira; quantidade, idade, mudança por janela e acumulada na confirmação. Não equivalem à fila ou trabalho residual da vítima. |

Definir P(t−) por start<t e término≥t ou desconhecido. Exigir reconciliação **P_L(b−)−P_L(a−)=N−D**. Essa igualdade é integridade contábil, não evidência de qualidade. Um D/N baixo pode acompanhar acumulação; D/N alto pode ser drenagem de coortes antigas. Nenhum dos dois decide recuperação sozinho.

**Oferta/gerador:** propor inicialmente O_real/O_nom∈[0,8;1,2] e N/O_real∈[0,95;1,05], inclusive esta última faixa por origem. Só qualificar a carga planejada com agenda e journals reconciliados, exposição e suporte suficientes. Se chegam menos oportunidades mas a faixa ainda é representativa e todas são iniciadas/atendidas, a menor vazão absoluta não reprova o serviço. Se O_real é adequado e N cai, registrar limitação de despacho/gerador ou pressão que exige diagnóstico. Se a oferta real é desconhecida ou baixa demais, reportar atendimento condicional à carga observada e **avaliação da carga planejada inconclusiva**, sem presumir capacidade recuperada nem degradação do serviço.

A instrumentação legítima atual não registra uma agenda independente completa de oportunidades. Um log criado apenas depois do despacho também não resolve o problema: bloqueio pode impedir a própria geração de oportunidades. Para liberar a versão forte desta regra será preciso especificar e validar esse estágio em nova autoridade, sem reconstruí-lo retrospectivamente de N. Se isso exigir agenda open-loop em lugar de intervalos sorteados após despacho, registrar explicitamente a mudança do processo de oferta e seus custos; o controle novo deve usar a mesma implementação. Nenhuma dessas mudanças foi implementada nesta tarefa.

**Referências:** usar PRE do próprio run (30–150 s) e conjunto benigno do novo C nos 360 s úteis fixos (30–390 s), agrupado de antemão. C precisa passar integridade, aderência, serviço e estabilidade por fase; se houver deriva/instabilidade, não escondê-la no agrupamento: referência inadequada bloqueia inferência. Não usar o bin de C com vazão mais conveniente. Contagens/vazões de C por bin continuam publicadas; deixam de ser limiar absoluto de recuperação.

**Atendimento compatível em W**, condicionado à integridade e à oferta adequadas:

- ≥200 starts e ≥200 durações 2xx, p95 conhecido, tanto na janela candidata quanto nas duas referências; janela/coorte completamente observáveis;
- 2xx/N≥99% e não mais de 1 ponto percentual abaixo de cada referência; no máximo 1% somando falhas, respostas outras e ausência de sucesso até H;
- p95≤1,25×p95 de **ambas** as referências; recursos, média e p50 continuam descritivos;
- P_L(b−)≤max(4, ceil(1,25×max(p95 de P_L nas referências))), sem pendência legítima com idade>3 s;
- crescimento de P_L≤2 por janela e ≤2 no conjunto das duas janelas de confirmação; P_A(b−)=0 nas duas fronteiras de confirmação, sem confundir fim de emissão com drenagem;
- as mesmas exigências técnicas de journals/CSVs/fechamentos, ground truth, captura e monitoramento continuam separadas dos resultados de serviço. Falhas reais do serviço permanecem observações válidas.

A coorte está madura quando H foi observado, ou quando todos os seus términos já são conhecidos e os logs completos certificam sua finalização após b. Assim um run saudável com fechamento em 390,03 s não precisa de um timestamp artificial de 393 s. Se uma tentativa ainda não tiver término conhecido, não presumir maturidade antes do prazo. A drenagem de até 30 s pode fornecer esses desfechos; não cria novas janelas POST. Registros perdidos geram falha técnica; tentativas incompletas persistidas geram pendência/incerteza de serviço.

O zero de pendências ofensivas só certifica o cliente. Um timeout não comprova cancelamento do trabalho na vítima. Recuperação significa compatibilidade do serviço aos legítimos nas medidas disponíveis, não prova de drenagem interna completa; CPU/memória e demais limitações continuam reportadas.

## Intervalo efetivamente pós-emissão, fixado antes da coleta

Manter grade nominal [270,300), [300,330), [330,360), [360,390). Definir t0=max(270, fim **certificado** da emissão). A janela avaliada é a interseção de cada bin com [t0,390). Todas as contagens, coortes, exposições, taxas e oportunidades são recalculadas nessa interseção a partir dos registros; não reaproveitar taxas do bin integral.

Exigir exposição≥95% de 30 s (28,5 s) e os suportes já definidos. A fração anterior a t0 fica identificada como transição, com métricas próprias, sem entrar na recuperação. A mesma transformação temporal, determinada pelo ataque e independente do desempenho, é usada nos contrastes temporais descritivos do novo C; a referência benigna agrupada permanece a previamente fixada.

Exemplo **puramente sintético**: certificação em 270,0015 s produz primeira janela [270,0015;300), exposição 29,9985 s. Certificação em 272 s produz apenas 28 s: essa primeira janela não qualifica por exposição, sem fusão, deslocamento ou extensão. O restante da grade permanece intacto. Certificação ausente torna o intervalo não avaliável; t0≥390 deixa nenhuma exposição POST elegível. Não usar último início ou última conclusão ofensiva para antecipar t0.

## Confirmação, perda de qualificação e censura

Duas janelas consecutivas com oferta adequada e atendimento compatível confirmam **compatibilidade pós-emissão** no fim da segunda. Somente chamar isso de **recuperação observada** se houver degradação anterior demonstrada em ACTIVE, com suporte e chegada auditados. Se o serviço já era compatível antes, usar `post_compatible_no_prior_impairment`, sem inventar um evento de recuperação.

Publicar separadamente: integridade; suporte/oferta/gerador; atendimento; primeira confirmação; qualificação das duas janelas finais; motivo de qualquer perda posterior. Uma janela posterior que perde apenas suporte/oferta não deve receber o rótulo de recaída de serviço. Se métricas de sucesso/duração/pendências piorarem com suporte adequado, reportar esse sinal como tal. A aptidão operacional exige as duas janelas finais qualificadas, fechamento controlado, cleanup, repouso≥60 s, prontidão e revisão humana; nunca decorre automaticamente de uma confirmação anterior.

Sem confirmação até 390 s, registrar censura à direita no fim efetivamente observado, com razão (`service_impaired`, chegada/gerador ambíguos ou suporte insuficiente). Se houver falha de coleta ou falta de certificação, registrar `unassessable`, sem alegar uma observação íntegra censurada. A primeira confirmação já observada permanece registrada mesmo se houver perda posterior; a qualificação terminal é outro campo.

## Escolhas exploratórias e validação sintética

São escolhas exploratórias, **não parâmetros estatisticamente calibrados**: 30 s, exposição mínima de 95%, n≥200, duas janelas consecutivas e duas finais, prazo/idade de 3 s, faixas de oferta/starts, sucesso de 99%, margem de 1 ponto percentual, razão p95 de 1,25, piso de 4 pendências, razão de 1,25 para pendências de referência e tolerância de crescimento de 2. Os 3 s partem do timeout configurado de 2 s com margem candidata de observação; não são garantia do runtime. A escolha de agrupar C também deve ser congelada antes da nova coleta. D1/D2 e o diagnóstico motivam o desenho, mas não demonstram a cobertura ou taxa de falso bloqueio dessas margens.

O protótipo calcula métricas a partir de starts/términos sintéticos; não recebe flags de recuperação prontas. Nos casos principais, ACTIVE sintético é medido para conferir se houve degradação anterior. Oferta auditada é uma hipótese explícita dos fixtures, não validação de uma instrumentação ainda inexistente.

| Caso sintético | Comportamento construído | Resultado esperado e verificado |
|---|---|---|
| Variação benigna de chegadas | 440/520/450/510 starts nos quatro bins; mesmas durações de 50 ms, 100% 2xx, oportunidades atendidas; desvio de certificação de 1,5 ms | Todos qualificam; vazão absoluta varia e continua registrada; compatibilidade sem inventar recuperação de degradação ausente |
| Degradação persistente | Oferta/starts mantidos; 20% falhas e p95 2xx de 500 ms em ACTIVE e todo POST | Nenhuma confirmação; censura em 390 s; métricas de serviço reprovadas |
| Recuperação real | ACTIVE e primeira janela degradados; três seguintes com 100% 2xx e 50 ms | Primeira confirmação em 360 s; duas finais qualificadas |
| Limitação do gerador | 480 oportunidades, mas 240 starts por janela; atendimento das iniciadas normal | Oferta→starts insuficiente; não confundir com chegada benigna menor ou capacidade recuperada |
| Pendências antigas | Novas coortes saudáveis, mas 12 tentativas antigas sem término | Sem recuperação: idade e quantidade de pendências reprovam |
| Oferta desconhecida / coleta inválida | Falta de oportunidades independentes / falha de coleta | Inconclusivo para carga planejada / não avaliável, respectivamente |

Testes adicionais verificam conservação com conclusões cruzadas, resposta tardia que não apaga falha no prazo, pequena/grande diferença de certificação, maturidade com fechamento antecipado completo e ausência de qualquer autorização de execução no protótipo. Isso valida coerência dos cálculos e casos discriminantes, **não** comportamento real, estabilidade do gerador nem eficácia científica.

## Opções de continuação: autoridades novas e orçamento fechado

Todas são propostas, sem configurações executáveis ou seeds novas materializadas nesta tarefa. Manter 390 s nominais +até30 s de drenagem +60 s de repouso reservado **por tentativa**, inclusive a última: 480 s = 8 min. Sem retries/substituições automáticas; falha consome a tentativa e bloqueia a sequência. Tempo administrativo cobre prontidão/revisão/cleanup, não autoriza carga adicional. Opções abaixo são alternativas, não orçamentos cumulativos.

| Opção | Nova autoridade/escopo | Tentativas futuras máximas | Carga+drenagem+repouso | Reserva administrativa | Envelope máximo |
|---|---|---:|---:|---:|---:|
| A — encerrar documentalmente | Arquivar regra candidata e limitações; nenhuma continuação empírica | 0 | 0 | Trabalho documental | **0 min de experimento** |
| B — validação prospectiva mínima, recomendada | Nova autoridade R2 e novo bloco C-R2→E4-R2; E8-R2 opcional, somente após gate de E4-R2 | 2 obrigatórias +1 condicional | 16–24 min | 10 min | **26 min sem E8; 34 min com E8** |
| C — confirmar repetibilidade | Dois blocos novos C-R2/E4-R2, cada um podendo incluir E8-R2 após seu gate | 4–6 | 32–48 min | 20 min | **52–68 min** |

Antes de B/C: especificar a agenda de oferta e sua auditoria, validar instrumentação offline, congelar regra/referências/grade/saídas/fingerprints, gerar configs completas e auditar novas seeds. Pareamento planejado dentro de cada bloco novo é permitido; blocos usam seeds distintas, exclusivas de pilotos e separadas das reservas da matriz. As reservas MATRIX_A/B existentes continuam intocadas. Mudança da oferta exige controle contemporâneo; não juntar o novo C com controles históricos para aprovar o gate.

C/E4 anteriores permanecem evidência exploratória sob a autoridade original, com os mesmos rótulos e bloqueio terminal. Não aplicar a regra candidata aos seus logs, não reaproveitá-los como réplicas confirmatórias, controles do R2 ou validação empírica da regra nova. O E8 original permanece não executado/bloqueado; um eventual E8-R2 seria uma nova entrada, não continuação automática da permissão antiga. As novas condições E4-R2 propostas não são retries da tentativa histórica: sua execução exigiria autorização futura e novo desenho explícito.

**Recomendação:** adotar B somente depois de resolver a evidência independente de oferta e revisar os parâmetros exploratórios; se essa etapa não for assumida, escolher A e limitar as conclusões ao serviço observado. Não selecionar parâmetros por recall/F1 ou resultados ofensivos futuros. Calibração continua benigna por regime legítimo, sem limiares específicos por endpoint/intensidade ofensiva. Nenhuma opção foi executada nesta tarefa.
