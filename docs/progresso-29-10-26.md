# Relatório de progresso — 29/10/2026

**Escopo:** implementação, experimentos, resultados e mudanças no planejamento. Não inclui a escrita do TCC.

## 1. Resumo do avanço

Hoje concluímos a comparação entre uma e duas origens ofensivas, implementamos a cadeia científica de avaliação dos detectores e revisamos o tamanho da campanha principal.

Após o retorno do professor Bordim, priorizamos um cenário com pressão mais clara sobre a infraestrutura. Executamos dois novos pilotos:

- **E12:** comprometimento forte de duração, com todas as requisições legítimas concluídas com sucesso.
- **E16:** timeouts legítimos, acúmulo de pendências, elevada utilização de CPU e parada controlada do ataque, seguida de recuperação.

**E16 forneceu a evidência de comprometimento do atendimento que faltava.** A recomendação atual é encerrar a escalada, sem preparar E20, e fechar uma campanha principal reduzida.

## 2. Comparação de origens ofensivas: D3_origins

Foram executadas quatro condições, mantendo uma vítima estática, 16 RPS legítimos em `/medium` e ataque em `/expensive`:

| Condição | Atacantes | RPS por atacante | Total nominal | Workers ofensivos |
|---|---:|---:|---:|---:|
| N1 | 1 | 8 | 8 RPS | 64 |
| N2 | 2 | 4 | 8 RPS | 32 + 32 |

A ordem foi **A: N1→N2; B: N2→N1**, com seed compartilhada dentro de cada bloco e distinta entre blocos.

### Correção do processamento

A primeira revisão de A_N1 reprovou a integridade por um erro no novo adaptador. Ele exigia igualdade integral entre:

- O certificado de fim da emissão, ainda com requisições em andamento.
- O estado final do evento, após a drenagem dessas requisições.

A transição de `emission_ended` para `completed` era prevista pelo produtor dos registros.

O adaptador foi corrigido para validar separadamente os campos invariantes de emissão e a evolução da drenagem. Foram acrescentadas fixtures N1/N2 com respostas em voo e casos inválidos.

**A execução não foi repetida.** Dados, tentativa e revisão original foram preservados; uma revisão R2 registrou a correção e sua proveniência.

### Resultados

As quatro revisões R2 tiveram integridade técnica e recuperação observada.

| Execução | RPS ofensivos reais | Starts legítimos ACTIVE | Sucesso legítimo | Média / p95 | CPU vítima |
|---|---:|---:|---:|---:|---:|
| A_N1 | 7,958 | 1.840 | 100% | 42,47 / 97,17 ms | 89,10% |
| A_N2 | 7,375 | 1.841 | 100% | 47,50 / 127,18 ms | 94,35% |
| B_N2 | 7,842 | 1.921 | 100% | 42,28 / 98,59 ms | 92,43% |
| B_N1 | 8,267 | 1.922 | 100% | 43,14 / 96,71 ms | 93,62% |

N2 teve p95 maior nos dois blocos, mas o contraste variou: **+30,01 ms em A e +1,88 ms em B**. N2 também iniciou menos requisições ofensivas nos dois blocos.

**Conclusão:** o bloco foi encerrado como evidência exploratória. Não demonstrou um efeito isolado e proporcional do número de origens. Taxas realizadas, processos, sessões e divisão dos workers precisam acompanhar a interpretação.

## 3. Implementação da avaliação científica

O Codex implementou a cadeia para avaliar:

- Z-score;
- CoV;
- EWMA;
- CUSUM com congelamento.

O núcleo do CUSUM já existia. O avanço de hoje foi sua integração científica, incluindo **replay completo para cada candidato a limiar `h`**, pois o limiar altera a trajetória dos estados aceitos.

Também foram implementados:

- Separação BASELINE → CAL-A → CAL-B → TEST.
- Artefatos e checkpoints vinculados.
- Bloqueio de TEST até aprovação de CAL-B.
- Runner com retomada sem repetição acidental.
- Substituições exclusivamente técnicas, limitadas e explicitamente aprovadas.
- Intervalos de confiança por execução/bloco, preservando pareamento.
- Tratamento de eventos não detectados, com atraso `null`.
- Preservação da cauda de drenagem após 390 s, sem incluí-la indevidamente no intervalo primário.

**Validação relatada:** 108 testes aprovados, sendo 13 de integração e 95 regressões. O fluxo completo foi exercitado com 98 coletas sintéticas.

Essas fixtures validam o processamento; **não são resultados experimentais dos detectores**.

### Situação dos ICs

Os ICs foram relatados como implementados e testados. Antes da campanha reduzida, ainda precisamos conferir sua correspondência com o protocolo final, especialmente diante da possibilidade de ataque encerrado antecipadamente.

## 4. Mudança no planejamento da campanha

A proposta inicial previa:

| Partição | Runs |
|---|---:|
| BASELINE | 6 |
| CAL-A | 12 |
| CAL-B | 16 |
| TEST | 64 |
| **Total** | **98** |

O TEST teria 16 blocos de C16/M8/E4/E8. O envelope estimado era de 29h24, chegando a 30h com substituições técnicas.

**Essa campanha foi pausada antes da materialização.** O Codex confirmou que as configurações reais não haviam sido criadas.

A revisão ocorreu por dois motivos:

1. Evitar uma campanha extensa antes de confirmar a representatividade do estresse.
2. Preservar tempo para análise, escrita e eventual extensão, sem tentar cobrir todas as possibilidades.

A campanha reduzida ainda será fechada. As quantidades de repetições e de coletas benignas também deverão ser reavaliadas.

## 5. Retorno do orientador e prioridade adotada

O professor Bordim destacou a necessidade de gerar estresse com impacto sobre os limites da infraestrutura.

Os experimentos anteriores já mostravam maior CPU e duração, mas ainda não evidenciavam falhas ou limitação clara do atendimento.

Decidimos realizar uma progressão curta:

**12 → 16 → 20 RPS ofensivos como teto de planejamento**, com uma tentativa por vez e revisão antes do avanço.

Somente E12 e E16 foram preparados e executados. **E20 não foi preparado.**

## 6. Preparação do piloto e observador de parada

Foi mantido o seguinte ambiente:

| Parâmetro | Configuração |
|---|---|
| Vítima | Uma instância, pool de dois processos |
| Proxy | Estático |
| Autoscaling | Desligado |
| Legítimos | Quatro clientes × 4 RPS em `/medium` |
| Atacante | Uma origem em `/expensive` |
| Concorrência | 64 workers ofensivos; 64 legítimos agregados |
| Duração nominal | 390 s |
| Ataque nominal | 150–270 s |

A criação da vítima não fixa quota de CPU ou cpuset. Os recursos efetivos foram registrados no preflight.

Foi implementado um observador que acompanha journals durante a execução e pode encerrar somente a emissão ofensiva. Ele distingue:

- Horário da decisão e do comando de parada.
- Fim real certificado da emissão.
- Conclusão das requisições em andamento.
- Continuidade dos legítimos e da coleta.

Coortes precisam amadurecer antes das decisões, sem uso de conclusões futuras. O observador também distingue nova amostra de CPU de valor repetido/cacheado.

**Validação relatada:** 17 testes aprovados. Um teste legado relacionado à simulação de captura permaneceu documentado como falha separada.

## 7. Resultado de E12

O atacante iniciou **1.409 requisições**, realizando **11,742 RPS** durante aproximadamente 120 s. Não houve fila relevante no gerador.

| Medida legítima | PRE | ACTIVE | POST |
|---|---:|---:|---:|
| Starts | 1.933 | 1.913 | 1.952 |
| Sucesso | 100% | 100% | 100% |
| Média | 31,32 ms | 134,78 ms | 31,17 ms |
| p95 | 58,10 ms | 434,88 ms | 57,17 ms |
| CPU média da vítima | 22,77% | 156,43% | 24,20% |

Os p95 das quatro janelas ACTIVE foram **146,42; 336,85; 510,38 e 571,33 ms**.

Houve comprometimento forte de duração, mas nenhum timeout legítimo. O observador não acionou parada; o ataque terminou no horário previsto e o serviço se recuperou.

Decidimos avançar somente para E16, buscando evidência mais clara de pressão sobre o atendimento.

## 8. Resultado de E16

E16 manteve os parâmetros de E12, alterando apenas ID, seed e taxa ofensiva nominal para 16 RPS.

O ataque realizou **15,977 RPS**, com **1.069 requisições iniciadas**. A emissão durou **66,91 s**, pois o observador acionou parada controlada.

| Medida legítima | PRE | ACTIVE | POST |
|---|---:|---:|---:|
| Starts | 1.929 | 1.010 | 2.779 |
| Sucessos 2xx | 1.929 | **978 — 96,83%** | 2.779 |
| Timeouts | 0 | **32 — 3,17%** | 0 |
| Média dos sucessos | 30,08 ms | **742,60 ms** | 37,37 ms |
| p95 dos sucessos | 58,22 ms | **1.915,82 ms** | 58,39 ms |
| Pendências início→fim | 0→0 | **0→20** | 20→0 |
| CPU média da vítima | 20,49% | **193,21%** | 25,74% |

Nas fronteiras observadas, as pendências legítimas chegaram a **29**. A fila ofensiva admitida e ainda não iniciada atingiu no máximo uma requisição, sem evidência relevante de limitação do gerador.

### Parada e recuperação

A parada foi acionada por `service_compromise`: uma coorte recente apresentou **32/160 = 20% sem sucesso no prazo**.

- Decisão: aproximadamente 216,895 s.
- Fim real da emissão: aproximadamente 216,915 s.
- Última conclusão ofensiva: aproximadamente 218,274 s.
- Legítimos e coleta continuaram.
- A recuperação foi confirmada pelo par de janelas encerrado em 300 s, sem perda posterior de qualificação.

**Integridade técnica e observação de serviço foram aprovadas.** A parada por comprometimento não invalidou a execução.

## 9. Conclusões e limites

**E16 mostrou comprometimento do atendimento**, com timeouts legítimos, aumento acentuado de duração, pendências e forte ocupação do processamento.

Ainda assim:

- Não foi demonstrada perda de pacotes.
- Não foi determinada capacidade máxima exata.
- Não foi estabelecido um platô de vazão entre patamares.
- E12 e E16 têm seeds e exposições distintas.
- Timeout do cliente não comprova cancelamento do trabalho na vítima.

As médias e percentis de sucesso também precisam ser apresentados junto dos timeouts: analisar somente as respostas bem-sucedidas esconderia parte do comprometimento.

## 10. Estado atual e próximos passos

**Recomendação atual:** encerrar a escalada de estresse, sem E20, e fechar a campanha reduzida.

O trio **C16/M16/E16** foi sugerido para avaliação do desenho, ainda sem aprovação final ou materialização. E12 pode permanecer como evidência exploratória.

Antes da coleta principal, precisamos:

1. Fechar os cenários e o número de blocos.
2. Revisar as quantidades benignas necessárias à calibração.
3. Definir a política de parada e avaliação de ataques interrompidos.
4. Conferir ICs, denominadores, misses e atraso nesse protocolo.
5. Atualizar orçamento e materializar a autoridade.

**Nenhuma coleta da campanha científica principal começou.** Os dados DEVELOPMENT e as autoridades anteriores permanecem preservados. Autoscaling continua como possível extensão posterior; comportamento periódico permanece secundário.