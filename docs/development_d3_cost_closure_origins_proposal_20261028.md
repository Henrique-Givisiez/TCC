# Encerramento de D3_cost e proposta de origens

D3_cost encerrado em DEVELOPMENT com quatro observações tecnicamente válidas, fechamento controlado e qualificação terminal. Registro novo: [encerramento JSON](../experiment_results/development-d3-cost-20261028/analysis/d3_cost_closure_20261028.json). As quatro revisões, dados brutos, manifesto e [comparação](../experiment_results/development-d3-cost-20261028/analysis/d3_cost_comparison.md) foram preservados. Os vínculos manifesto/configuração/identidade/raw foram conferidos pelo utilitário existente; métricas por execução e contrastes dentro dos blocos foram reproduzidos offline. O registro de preparação histórico não é atualizado para representar encerramento.

## Evidência encerrada

Valores de ACTIVE; duração de sucessos legítimos, CPU em percentual Docker (pode ultrapassar 100%).

| Bloco | Endpoint | Starts ataque / RPS | Starts legítimos / 2xx | Média / p95 ms | CPU vítima / proxy % |
|---|---|---:|---:|---:|---:|
| A | /medium | 934 / 7,783 | 1940 / 1940 | 32,54 / 57,55 | 28,63 / 2,29 |
| A | /expensive | 934 / 7,783 | 1940 / 1940 | 42,15 / 94,72 | 95,79 / 2,43 |
| B | /expensive | 976 / 8,133 | 1945 / 1945 | 73,67 / 231,61 | 114,65 / 3,01 |
| B | /medium | 976 / 8,133 | 1945 / 1945 | 34,11 / 58,30 | 31,49 / 2,40 |

O contraste expensive−medium é consistente: p95 legítimo +37,17 ms em A e +173,31 ms em B; CPU da vítima +67,16 e +83,16 pontos percentuais. CPU do proxy +0,13 e +0,61 pontos. A direção repete-se, a magnitude não é estável. Os dois endpoints têm contagens ofensivas e legítimas ACTIVE iguais dentro de cada seed; B inicia 42 ataques a mais que A (+0,350 RPS, cerca de 4,5%). Isso permite descrever o contraste pareado; a diferença de B frente a A também envolve seed, chegadas, período e ambiente, sem decomposição causal desses fatores.

Nos dois /expensive, as quatro janelas ACTIVE reprovam duração, com comprometimento observado, apesar de sucesso legítimo de 100%. /medium qualifica as quatro e termina `post_compatible_no_prior_impairment`. /expensive termina `recovery_observed`: primeiras duas janelas POST confirmam no fim 330 s, horizonte exigido 333 s, com evidência efetivamente usada até 330 s e decisão batch somente após fechamento reconciliado, cerca de 390,03 s. Todas as janelas POST qualificam, sem perda posterior; as duas últimas também qualificam. Sucesso, prazo e pendências devem continuar sendo lidos junto de duração; aumento de latência é resultado de serviço, não falha técnica de coleta.

Limitações: dois blocos, ordem invertida apenas parcialmente controla período; não são estimativas de capacidade máxima nem validação científica final. Mesma seed não garante agenda ou starts iguais em geral. Taxa iniciada é observada; execução de toda a agenda programada permanece não comprovada (`full_scheduled_load_verified=false`). C histórico é secundário e não contemporâneo; PRE próprio é principal. CPU depende do suporte/frescor disponível. Não agregar percentis por média, nem promover pilotos a réplicas. Detectores, calibração e classificações históricas permanecem intactos.

## Próximo desenho para revisão

[Proposta estruturada](../experiments/protocols/development_d3_origins_proposal_20261028/proposal.json), ainda sem autoridade de execução ou configurações operacionais. Aplicar o princípio N2 do [roadmap, §2.2](new_campaign_protocol_proposal_20261027.md): variar origens com taxa agregada e orçamento de envio fixos. A escolha de `/expensive` é adaptação prospectiva de DEVELOPMENT sustentada por D3_cost; o N2 original do roadmap usa `/medium`. Não altera o desenho final histórico automaticamente.

Menor matriz recomendada: duas condições, repetidas em dois blocos novos com ordem invertida, total quatro tentativas. Um único par de duas tentativas seria exploratório, mas deixaria o contraste inteiramente associado à ordem e sem observação da variação entre blocos já evidente em D3_cost. Não acrescentar N4, nova intensidade, endpoints ou controle separado neste bloco. Reexecutar N1 é necessário como âncora do novo bloco; os N1 de D3_cost são referências exploratórias, não substitutos pareados.

| Ordem | Entrada proposta | Origens ofensivas | RPS por atacante | RPS agregados | Workers por atacante |
|---:|---|---:|---:|---:|---:|
| 1 | A_N1 | 1 | 8 | 8 | 64 |
| 2 | A_N2 | 2 | 4 | 8 | 32 |
| 3 | B_N2 | 2 | 4 | 8 | 32 |
| 4 | B_N1 | 1 | 8 | 8 | 64 |

Duas seeds novas a auditar na materialização operacional: iguais dentro do bloco, distintas entre blocos e disjuntas dos históricos/reservas. A seed compartilhada não garante streams equivalentes quando muda a quantidade de fontes. Sempre quatro clientes legítimos a 4 RPS em `/medium` (16 agregados), workers legítimos 64 agregados (16 por origem); ataque contínuo `/expensive`; uma vítima, proxy estático, autoscaling off, pool 2, timeout HTTP 2 s e monitoramento 1 s. Manter workers ofensivos 64 agregados: o gerenciador existente já reparte 64 em 32+32. Mais sessões/processos e repartição de workers integram o efeito operacional de distribuir origens; não atribuir tudo a identidade/IP isoladamente.

Warmup 0–30, PRE 30–150, ACTIVE 150–270, POST 270–390 s. Mesmas referências e objeto de critérios E8-R2, copiados integralmente na proposta: PRE próprio principal; C histórico hash-bound secundário, sem requisito de vazão absoluta de um bin de C. Grade pós-emissão certificada, exposição ≥95%, suporte ≥200 starts/durações, sucesso ≥99%, margem de referência 1 pp, ausência de sucesso no prazo ≤1%, p95 ≤1,25 das referências; quantidade/idade/crescimento de pendências conforme regra fixa; duas janelas consecutivas e qualificação terminal. Preservar b, horizonte b+3 e publicação separados; ausência de evidência não presume conclusão. Sem comprometimento ACTIVE, POST compatível não inventa recuperação. Nenhuma recalibração ou mudança retrospectiva.

Orçamento: quatro tentativas sem retry/substituição, 18 min cada, total **72 min**: 1560 s nominais +120 s drenagem +240 s repouso +2400 s administrativos. Revisão manual entre todas as entradas, novo preflight e ≥60 s desde cleanup. Integridade técnica/dataset/fechamento, compatibilidade de referências e duas últimas janelas POST qualificadas condicionam progressão; falha técnica ou ausência de recuperação/qualificação terminal bloqueia para diagnóstico, sem tentativa extra automática. Degradação ACTIVE válida não bloqueia por si só. Disponibilidade de agenda do gerador é uma conclusão separada da validade do serviço recebido.

Reutilizar exportação, reconciliação CSV/journals/fechamentos de todas as origens, ground truth e análise de classe/fase dos módulos D3/E8-R2. Na materialização, usar adaptador próprio: o módulo D3_cost fixa IDs/ordem/um atacante e não deve ser invocado como autoridade N2 nem modificado. Validar inventário de duas fontes ofensivas, encerramento certificado da última origem, denominador agregado 960 starts/120 s (não 1920), 480 nominais por origem N2, quotas 32+32 e vínculos de revisão. Isso exige fixture de duas origens antes de qualquer preflight; a proposta não alega validação operacional N2 já concluída. O gerador não requer instrumentação adicional para este desenho.

Comparar N2−N1 na mesma seed; B−A separado por condição. Publicar serviço legítimo PRE/ACTIVE/POST (starts/RPS, términos, 2xx, HTTP/transporte, prazo, incompletas, média/p95, pendências e recuperação); CPU/memória vítima/proxy e conexões; starts/RPS ofensivos agregados e por origem, admissões, atraso disponível e desigualdade de repartição. Diferenças de oferta observada devem acompanhar o contraste, sem correção silenciosa nem pressupor carga realizada igual.

Decisões para revisão: aprovar duas origens como único novo nível, adaptação para `/expensive`, dois blocos/quatro tentativas e envelope 72 min. Após fechar o desenho, materializar autoridade/IDs/seeds/paths próprios e fixture N2 reutilizando os utilitários; autorização de execução é etapa distinta. Nenhum experimento ou Docker foi executado neste encerramento/proposta.
