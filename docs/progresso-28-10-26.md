# Relatório de progresso — 28/10/2026

**Projeto:** avaliação de ataques HTTP e detecção de anomalias em ambiente conteinerizado  
**Escopo:** implementação, experimentos, resultados e planejamento. Não inclui avanços na escrita do TCC.

## 1. Objetivo do trabalho de hoje

O trabalho avançou da caracterização isolada dos endpoints para **experimentos com tráfego legítimo e ofensivo simultâneos, em uma única vítima**.

Isso atende à orientação do professor Bordim de avaliar não apenas a quantidade de requisições, mas também o custo dos endpoints explorados pelo atacante, antes de avançar para autoscaling.

As atividades permaneceram em **DEVELOPMENT**: os resultados orientam o desenho da campanha, sem constituir ainda a avaliação final dos detectores.

## 2. Ponto de partida: encerramento de D2

D2 havia comparado `/light`, `/medium` e `/expensive` isoladamente, com aproximadamente 4 RPS agregados. Hoje, seu encerramento documental consolidou:

- Seis execuções comparativas aceitas, organizadas em dois blocos.
- Um probe separado, sem ser contabilizado como terceira repetição.
- Maior duração e consumo de CPU em `/expensive`.
- Distinção entre comparações dentro de uma mesma seed e variação entre seeds.

| Endpoint | p95 observado em A/B |
|---|---:|
| `/light` | 44,47 / 44,31 ms |
| `/medium` | 54,30 / 56,69 ms |
| `/expensive` | 149,02 / 141,30 ms |

Esses resultados justificaram priorizar `/expensive` nos pilotos de tráfego misto. Ainda faltava observar seu efeito sobre clientes legítimos atendidos simultaneamente.

## 3. Estrutura dos experimentos D3

Foi adotado o seguinte arranjo:

| Parâmetro | Configuração |
|---|---|
| Vítima | Uma instância |
| Proxy | Estático |
| Autoscaling | Desativado |
| Clientes legítimos | Quatro, a 4 RPS nominais cada |
| Carga legítima | 16 RPS agregados em `/medium` |
| Atacante nos pilotos | Uma origem |
| Endpoint ofensivo inicial | `/expensive` |
| Intensidades exploradas | 4 e 8 RPS nominais |
| Duração nominal | 390 segundos |
| Drenagem reservada | Até 30 segundos |
| Repouso entre execuções | Mínimo de 60 segundos após cleanup |

As fases foram:

| Fase | Intervalo | Finalidade |
|---|---|---|
| WARMUP | 0–30 s | Aquecimento |
| PRE | 30–150 s | Referência legítima anterior ao ataque |
| ACTIVE | 150–270 s | Tráfego legítimo e ofensivo simultâneos |
| POST | 270–390 s | Acompanhamento após a emissão ofensiva |

O controle C manteve apenas tráfego legítimo durante toda a execução.

## 4. Primeiros pilotos: controle C e ataque E4

O controle C foi aceito, com integridade técnica, aderência do gerador e critérios de serviço atendidos nas fases PRE, ACTIVE e POST.

O primeiro E4 também apresentou coleta íntegra e ausência de comprometimento pelos critérios das fases completas. Entretanto, a regra inicial de recuperação bloqueou a progressão por dois motivos:

| Janela | Motivo da reprovação |
|---|---|
| POST_1 | Começava cerca de 1,56 ms antes do encerramento certificado da emissão ofensiva |
| POST_4 | Vazão abaixo de 90% da janela correspondente do controle C |

O diagnóstico offline mostrou que:

- POST_1 passaria nas comparações de desempenho; a reprovação era temporal.
- POST_4 teve menos requisições iniciadas que C, mas todas concluíram com sucesso, sem incompletas e com p95 baixo.
- Não havia evidência de perda de requisições que justificasse interpretar automaticamente o resultado como recaída do serviço.

**Decisão:** preservar a revisão original e seu bloqueio. A regra seguinte seria aplicada prospectivamente, em uma nova execução.

## 5. Aprendizado sobre geração de carga e recuperação

A inspeção do gerador identificou uma distinção importante:

**Conseguimos avaliar o serviço recebido pelas requisições iniciadas, mas não comprovar integralmente todas as oportunidades de envio previstas para os clientes legítimos.**

Existem registros de início, término e fechamento. Porém, faltam timestamps de oportunidades programadas e submissão ao executor dos clientes legítimos. Além disso, o próximo intervalo aleatório é sorteado depois da submissão.

No atacante do primeiro E4, foram reconciliadas 463 admissões, 463 inícios e 463 términos, sem abandono. O p95 de admissão até início foi de 0,323 ms; essa medida não representa atraso em relação a uma agenda previamente fixada.

A revisão prospectiva passou a avaliar:

- Sucesso e duração das coortes de requisições iniciadas.
- Conclusões até um horizonte de acompanhamento.
- Quantidade, idade e crescimento de pendências.
- Janelas POST recortadas pelo encerramento certificado da emissão.
- Duas janelas consecutivas qualificadas e manutenção da qualificação ao final.

O horizonte `b+3 s` foi definido como escolha exploratória. O timeout HTTP de 2 s não garante duração total máxima de 2 s.

Também foi explicitada a diferença entre **fim da janela avaliada, horizonte de evidência e publicação da decisão offline**.

## 6. Nova execução E4-R2

Foi preparada uma nova autoridade operacional, com ID, seed e caminhos próprios, para uma única tentativa de E4.

A execução terminou com integridade técnica e classificação:

`post_compatible_no_prior_impairment`

| Medida legítima | PRE | ACTIVE | POST |
|---|---:|---:|---:|
| Starts | 1.838 | 1.959 | 1.864 |
| RPS iniciados | 15,317 | 16,325 | 15,533 |
| Sucesso | 100% | 100% | 100% |
| Média | 29,90 ms | 34,29 ms | 29,80 ms |
| p95 | 58,29 ms | 58,34 ms | 57,63 ms |
| CPU média da vítima | 19,47% | 52,39% | 20,66% |

O atacante iniciou **443 requisições em 120 s**, equivalentes a **3,692 RPS**, ou 92,29% da taxa nominal.

As quatro janelas POST qualificaram. Houve aumento de CPU e da duração média durante o ataque, mas sem comprometimento pelos critérios definidos. Portanto, o resultado foi registrado como compatibilidade posterior, sem inventar um evento de recuperação.

## 7. Piloto E8-R2: comprometimento e recuperação observados

Com base em E4-R2, foi preparada e executada uma tentativa com **8 RPS ofensivos nominais**, mantendo 16 RPS legítimos.

| Medida legítima | PRE | ACTIVE | POST |
|---|---:|---:|---:|
| Starts | 1.932 | 1.874 | 1.904 |
| RPS iniciados | 16,100 | 15,617 | 15,867 |
| Sucesso | 100% | 100% | 100% |
| Média | 30,56 ms | 41,54 ms | 29,38 ms |
| p95 | 57,89 ms | 86,12 ms | 57,28 ms |
| CPU média da vítima | 21,08% | 89,01% | 19,56% |

O ataque iniciou **911 requisições**, equivalentes a **7,592 RPS**, ou 94,90% da taxa nominal. Todas terminaram em 2xx.

O comprometimento ocorreu **exclusivamente pelo critério de duração**: três das quatro janelas ACTIVE ultrapassaram os limites de p95, próximos de 72 ms. Sucesso, prazo e pendências passaram.

Todas as janelas POST qualificaram. O primeiro par terminou em 330 s, confirmando recuperação pela regra. Não houve perda posterior de qualificação.

Esse instante representa a confirmação por duas janelas; não significa que o serviço permaneceu comprometido até 330 s. A primeira janela POST já apresentou duração próxima do normal.

## 8. D3_cost: comparação do endpoint ofensivo

Após os pilotos, foram preparadas e executadas quatro observações para comparar ataques em `/medium` e `/expensive` com a mesma taxa nominal de 8 RPS.

- **Bloco A:** `/medium` → `/expensive`.
- **Bloco B:** `/expensive` → `/medium`.
- Mesma seed dentro de cada bloco; seeds distintas entre blocos.
- Quatro clientes legítimos e uma vítima mantidos.
- Mesmas fases e critérios de avaliação.

### Resultados durante ACTIVE

| Execução | RPS ofensivos | Starts legítimos | Sucesso legítimo | Média / p95 | CPU vítima |
|---|---:|---:|---:|---:|---:|
| A — `/medium` | 7,783 | 1.940 | 100% | 32,54 / 57,55 ms | 28,63% |
| A — `/expensive` | 7,783 | 1.940 | 100% | 42,15 / 94,72 ms | 95,79% |
| B — `/expensive` | 8,133 | 1.945 | 100% | 73,67 / 231,61 ms | 114,65% |
| B — `/medium` | 8,133 | 1.945 | 100% | 34,11 / 58,30 ms | 31,49% |

Dentro de cada bloco, as contagens ofensivas e legítimas foram iguais entre endpoints.

| Contraste `/expensive` − `/medium` | Bloco A | Bloco B |
|---|---:|---:|
| Aumento do p95 legítimo | 37,17 ms | 173,31 ms |
| Aumento relativo do p95 | 64,6% | 297,3% |
| Aumento da CPU da vítima | 67,16 pontos percentuais | 83,16 pontos percentuais |

As quatro execuções tiveram integridade técnica. Em ambos os blocos:

- `/medium`: sem comprometimento pelos critérios.
- `/expensive`: comprometimento de duração e recuperação posterior.
- Todas as janelas POST qualificaram, sem perda posterior.

**D3_cost foi encerrado documentalmente**, com reprodução offline das métricas e contrastes e preservação das revisões originais.

## 9. Implementações e validações realizadas

O trabalho de implementação concentrou-se em:

- Preparação e validação dos pilotos D3.
- Diagnóstico offline da regra inicial de recuperação.
- Processamento prospectivo de serviço para E4-R2.
- Adaptadores de execução e revisão para E8-R2.
- Configurações, manifesto e comparação pareada de D3_cost.
- Vínculos entre revisões, configurações e execuções por hashes.
- Saídas compactas da CLI, mantendo detalhes nos JSONs.
- Testes sintéticos de exportação, revisão, comparação e bloqueios operacionais.

As preparações de E8-R2 e D3_cost tiveram **cinco testes específicos aprovados cada**. As execuções reais ocorreram pelo terminal do usuário, com preflight e revisão individual.

Os detectores não foram aplicados nesses experimentos. Não houve nova calibração científica nem reavaliação do TEST congelado.

## 10. Principais conclusões e limites

1. **O custo do endpoint importa.** Nos dois blocos D3_cost, `/expensive` produziu maior CPU e maior duração das requisições legítimas que `/medium`.

2. **Comprometimento pode ocorrer com 100% de sucesso.** O efeito observado foi piora de duração, sem necessidade de erros HTTP ou requisições incompletas.

3. **A magnitude varia entre execuções.** O efeito foi maior em B. Seed, chegadas, período e ambiente não foram isolados causalmente.

4. **Menos starts não prova incapacidade de atendimento.** A taxa iniciada precisa ser interpretada junto dos desfechos e das limitações do gerador.

5. **CPU Docker de 100% equivale a um núcleo lógico.** Valores acima disso são possíveis e não representam, por si só, saturação de toda a máquina.

6. **Os resultados ainda são exploratórios.** Dois blocos sustentam o planejamento, mas não estabelecem capacidade máxima, desempenho dos detectores ou estimativa confirmatória final.

## 11. Próximo passo: número de origens ofensivas

Foi proposta a comparação:

| Condição | Atacantes | RPS por atacante | Total ofensivo | Workers por atacante |
|---|---:|---:|---:|---:|
| N1 | 1 | 8 | 8 RPS | 64 |
| N2 | 2 | 4 | 8 RPS | 32 |

Serão mantidos `/expensive`, 16 RPS legítimos, uma vítima e 64 workers ofensivos agregados.

A matriz proposta contém quatro execuções: **A: N1→N2; B: N2→N1**, com seeds novas e orçamento de até 72 minutos.

A preparação operacional deverá validar especialmente:

- Inventário e reconciliação das duas origens ofensivas.
- Encerramento certificado da última origem.
- Expectativa de 480 starts por atacante e 960 agregados em ACTIVE.
- Divisão de concorrência em 32+32.
- Taxas observadas por origem e agregadas.

**Até o último retorno recebido, esse bloco estava proposto, ainda sem execução.** A próxima entrega solicitada ao Codex é sua materialização e validação offline.

Após esse bloco, permanecem o fechamento da matriz final, o planejamento de repetições e intervalos de confiança, a integração/calibração científica dos detectores por regime legítimo e, posteriormente, os casos de autoscaling. RTT proxy–servidores, UDP e demais extensões opcionais continuam fora do escopo inicial.