# Relatório de progresso — 27/10/2026

**Ao final do dia, concluímos a caracterização benigna de carga com uma vítima (D1) e a comparação dos três endpoints sob a mesma taxa de requisições (D2).** Também implementamos uma variante do CUSUM com congelamento de estado e corrigimos problemas de captura e de execução dos ensaios. Os experimentos com tráfego legítimo concorrendo com ataque permanecem como próximo passo.

Este relatório abrange implementação, decisões metodológicas e resultados experimentais. Não inclui avanços na escrita do TCC.

## 1. Ponto de partida: reunião com o orientador

O trabalho foi organizado a partir das observações da reunião de 26/10:

| Orientação | Encaminhamento e situação |
|---|---|
| Avaliar consumo de CPU das instâncias e, se disponível, por núcleo | CPU da vítima e do proxy acompanhadas nos ensaios. Medição individual por núcleo ainda não concluída. |
| Examinar a infraestrutura do host, caso os dados sejam acessíveis | Mantido como complemento opcional, fora do roadmap inicial. |
| Considerar intervalos de confiança | Mantido como pendência do protocolo de avaliação. As repetições realizadas hoje têm caráter exploratório. |
| Explicar como o tráfego é gerado e justificar a escolha | Configurações, taxas por origem, seeds e comportamento observado foram documentados. A justificativa metodológica ainda precisa ser consolidada. |
| Explorar RTT proxy–servidores e UDP, se houver tempo | Mantidos fora do escopo inicial. |
| Manter a medição das requisições iniciadas no cliente | Decisão preservada na instrumentação e nas métricas. |
| Corrigir o CUSUM congelando o último estado aceito | Nova variante implementada e testada sinteticamente. Integração e calibração científicas pendentes. |
| Estressar uma instância antes de avançar para autoscaling | D1 e D2 executados com uma vítima e proxy estático. Autoscaling permanece para etapa posterior. |

A dúvida sobre os limiares foi encaminhada com a recomendação de **calibrar por regime de tráfego legítimo**. Dentro de um mesmo regime, os limiares devem permanecer fixos ao variar a intensidade ou o endpoint do ataque. Essa estratégia ainda precisa ser materializada na nova campanha de detecção.

## 2. Organização do trabalho e decisões metodológicas

Foi criada uma proposta de protocolo para a nova campanha, distinguindo:

- caracterização exploratória em **DEVELOPMENT**;
- ajuste e calibração dos detectores;
- avaliação posterior em TEST.

Os resultados congelados das campanhas anteriores foram preservados. As novas definições não foram aplicadas retroativamente aos scores, limiares ou avaliações históricos.

A preparação experimental passou a controlar configurações, seeds, ordem das execuções, integridade dos dados e critérios de progressão. Também foi estabelecida uma distinção essencial: **degradação real do serviço é um resultado experimental; falha de coleta pode impedir o uso científico daquele resultado.**

As condições opcionais — observação adicional do host, RTT específico entre proxy e servidores e UDP — não foram incorporadas ao roadmap inicial.

## 3. Resumo offline do serviço

Foi implementado um utilitário para resumir os registros de requisições por execução, classe de tráfego e fase.

O resumo diferencia:

- requisições iniciadas, agrupadas pelo instante de início;
- términos, agrupados pelo instante de conclusão;
- durações de respostas 2xx, atribuídas à fase em que a requisição começou;
- falhas, respostas de outras categorias e requisições sem término conhecido;
- requisições que atravessam fronteiras entre fases.

O corte de observação é explícito: uma requisição que termina depois dele ainda tem desfecho desconhecido naquele resumo. Isso evita usar informação futura para contabilizar sucesso, falha ou duração.

A drenagem passou a ser determinada pelos registros `source_closed` das quatro origens. O último término HTTP, isoladamente, não foi considerado suficiente para estabelecer o fim da observação.

**Validação informada:** 31 testes passaram, incluindo casos de fronteira temporal, timeout, respostas HTTP, incompletas e drenagem. A CLI também foi verificada com dados sintéticos.

## 4. Correção do CUSUM

Foi implementada a variante **`cusum-freeze:1`**, com identidade própria e preservação do CUSUM anterior.

A nova lógica mantém três elementos distintos:

| Elemento | Função |
|---|---|
| Estado armazenado | Último valor aceito da soma acumulativa; serve de base ao próximo cálculo. |
| Candidato, publicado como score | Valor calculado com a observação atual, mesmo quando ultrapassa o limiar. |
| Alarme | Decisão obtida ao comparar o candidato com o limiar. É essa decisão que chega à avaliação. |

Quando o candidato ultrapassa o limiar, o detector emite alarme e mantém o estado anterior. Nas observações seguintes, continua calculando candidatos a partir desse estado. Quando o candidato volta à região aceita, a atualização é retomada.

Na implementação, a regra é **alarme quando candidato > limiar**; igualdade não produz alarme.

Essa separação resolveu a dúvida levantada durante o trabalho: **o estado congelado não precisa ultrapassar o limiar para ocorrer um verdadeiro positivo**. O teste de integração confirmou uma decisão positiva avaliada como TP mesmo com o estado armazenado abaixo do limiar.

A recuperação depende das observações recebidas; não utiliza o conhecimento do fim do ataque.

Como o limiar agora influencia a trajetória do estado, ele ficou vinculado ao processamento. Alterá-lo exige reprocessar a série. A recarga do artefato verifica a trajetória com o limiar original.

**Validação informada:** 95 testes passaram, incluindo regressões dos métodos anteriores.

**Pendência:** a variante ainda não está calibrada cientificamente nem integrada à avaliação completa da nova campanha. Os testes sintéticos não demonstram redução de falsos positivos ou de persistência após ataques.

## 5. D1 — caracterização da carga benigna

D1 avaliou uma vítima, proxy estático e quatro clientes acessando `/medium`, sem ataque e sem autoscaling.

As condições principais foram:

- taxas de 1, 2, 4, 8 e 16 RPS por cliente;
- oferta agregada de 4, 8, 16, 32 e 64 RPS;
- duas repetições por nível;
- duração nominal de 150 s, com 30 s de aquecimento e 120 s úteis;
- timeout HTTP de 2 s;
- monitoramento a cada segundo;
- recuperação mínima de 60 s entre execuções, com conferência do ambiente.

Os critérios incluíram aderência à taxa oferecida, sucesso das requisições, duração, tendências durante o ensaio, suporte de monitoramento, integridade de captura e encerramento das origens.

### Resultados de D1

| Oferta agregada | RPS efetivos A / B | p95 A / B |
|---:|---:|---:|
| 4 RPS | 4,083 / 3,858 | 55,96 / 56,79 ms |
| 8 RPS | 7,842 / 7,808 | ≈58,2 / 57,48 ms |
| 16 RPS | 15,875 / 15,825 | ≈58,5 / ≈58,5 ms |
| 32 RPS | 31,467 / 32,292 | 59,45 / 59,96 ms |
| 64 RPS | 64,150 / 63,717 | 61,71 / 65,36 ms |

O resultado B apresentado para 32 RPS corresponde à substituição aceita após a falha técnica de captura descrita abaixo.

Nos ensaios aceitos, o serviço permaneceu dentro dos critérios. No maior nível, a CPU média da vítima foi aproximadamente **89,05% em A e 94,75% em B**.

Esses percentuais seguem a convenção da métrica coletada e não representam, por si só, saturação de toda a capacidade física do host. Dois processos de trabalho também não equivalem a duas CPUs reservadas.

**Conclusão de D1:** `/medium` atendeu aos critérios até a maior carga testada, de 64 RPS agregados. Não foi determinada a capacidade máxima da aplicação.

### Falha de captura e correção

A tentativa original de L04/B apresentou **dois pacotes descartados pelo kernel na captura CSV**. O serviço havia atendido aos critérios, mas a tentativa foi considerada tecnicamente inelegível.

O diagnóstico identificou ainda que os dois processos de captura, CSV e PCAP, gravavam seus diagnósticos no mesmo caminho, permitindo sobrescrita.

Foram realizados os seguintes ajustes:

- solicitação explícita de buffer `-B 4096` para a captura CSV;
- arquivos de diagnóstico separados;
- registro do ciclo de vida de cada captura;
- verificação dos contadores finais e do encerramento dos processos.

Não foi possível atribuir os descartes a uma causa específica, como buffer, CPU, disco ou encerramento. A ocorrência foi tratada como **perda na captura**, sem inferir perda na rede.

A tentativa original foi preservada. Uma substituição com identificação e caminhos próprios foi executada e aceita, mantendo a seed B. D1 terminou com **11 tentativas experimentais e 10 execuções aceitas**.

## 6. D2 — comparação dos endpoints

D2 comparou `/light`, `/medium` e `/expensive` sob oferta comum de **4 RPS agregados**, mantendo quatro clientes, uma vítima e proxy estático.

Antes das comparações, foi executado um probe exclusivo de `/expensive`, com seed própria. Ele passou nos critérios e sustentou a manutenção de 4 RPS para o bloco comparativo.

As seis execuções seguiram:

- **A:** `/light` → `/medium` → `/expensive`;
- **B:** `/expensive` → `/medium` → `/light`.

A mesma seed foi utilizada entre endpoints dentro de cada réplica. A e B utilizaram seeds diferentes. A inversão da ordem reduz uma assimetria do desenho, mas não elimina efeitos de período ou variações ambientais.

### Resultados de D2

| Endpoint | Duração média A / B | p95 A / B | CPU média da vítima A / B |
|---|---:|---:|---:|
| `/light` | 9,03 / 9,19 ms | 44,47 / 44,31 ms | 0,91% / 0,95% |
| `/medium` | 18,66 / 19,35 ms | 54,30 / 56,69 ms | 4,53% / 5,10% |
| `/expensive` | 110,59 / 104,78 ms | 149,02 / 141,30 ms | 37,57% / 37,97% |

Cada execução A teve **474 starts úteis**, com 3,95 RPS efetivos. Cada execução B teve **473 starts úteis**, com aproximadamente 3,942 RPS.

Nas seis comparações:

- todas as requisições úteis tiveram sucesso 2xx;
- não houve falhas HTTP, falhas de transporte ou incompletas;
- as capturas CSV e PCAP registraram zero descartes pelo kernel;
- todas as revisões foram aceitas.

A CPU média do proxy ficou entre **1,61% e 1,72%**. A memória média da vítima permaneceu próxima de **22,5–22,9 MiB**.

O probe, mantido fora das comparações, teve 507 starts úteis, 4,225 RPS e p95 de 146,04 ms.

**Conclusão de D2:** nas duas réplicas, `/expensive` apresentou maior duração HTTP e maior consumo observado de CPU da vítima. Seu p95 foi aproximadamente **2,5–2,7 vezes** o de `/medium`, sob taxas efetivas muito próximas.

Esses resultados sustentam a escolha de endpoints com demandas distintas para a próxima etapa. Não estabelecem uma razão universal de custo nem demonstram ainda impacto sobre clientes legítimos concorrendo com atacantes.

## 7. Ajustes operacionais e rastreabilidade

Durante a preparação e retomada de D2, foram resolvidos problemas que impediam a execução e a revisão:

- substituição da exigência rígida de um único HEAD por verificação de ancestralidade e hashes dos arquivos aprovados;
- preservação de múltiplos preflights, cada um com identificação própria;
- vínculo explícito da tentativa experimental ao preflight selecionado;
- correção da inicialização de caminhos no avaliador;
- validação do caminho, hash, entrada, manifesto e prontidão do preflight usado pela revisão.

O acesso ao Docker falhou com `EPERM` no contexto observado do Codex, tanto pela CLI quanto pelo SDK Python. No terminal do usuário, o preflight passou e os experimentos foram executados normalmente. A regra específica responsável pelo bloqueio não foi identificada.

Os relatórios de comparação anteriores foram arquivados antes de gerar a consolidação completa. A saída final confirmou **sete execuções revisadas: um probe e seis comparações**.

A repetição de preflight foi tratada separadamente da repetição experimental. Por exemplo, `pf-0003` identifica a terceira checagem de prontidão daquela entrada, não três execuções do cenário.

## 8. Situação ao encerramento do dia

| Frente | Situação |
|---|---|
| Proposta da nova campanha | Documentada |
| Resumo offline do serviço | Implementado e validado |
| CUSUM com congelamento | Implementado e validado sinteticamente |
| D1 — variação da carga benigna | Concluído |
| Correção da captura e substituição de L04/B | Concluídas |
| D2 — comparação dos endpoints | Concluído e consolidado |
| Ataque concorrendo com clientes legítimos | Ainda não executado |
| Calibração e avaliação científica do novo CUSUM | Pendentes |
| Intervalos de confiança da campanha principal | Pendentes |
| CPU individual por núcleo | Pendente |
| Autoscaling | Etapa posterior |
| Host adicional, RTT proxy–servidores e UDP | Complementos opcionais |

O próximo encaminhamento proposto é **D3: medir o efeito de ataque contínuo sobre clientes legítimos**, começando pela comparação de endpoints ofensivos sob a mesma taxa e, depois, variando a intensidade. A matriz e os critérios precisam ser preparados com base nos resultados de D1 e D2.

Até o momento, os ensaios realizados hoje caracterizam carga benigna e custo observado dos endpoints. **Ainda não foram produzidos novos resultados de eficácia dos detectores sob ataque.**