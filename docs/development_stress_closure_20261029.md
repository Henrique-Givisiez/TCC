# Encerramento documental de DEVELOPMENT — E12/E16

Exploração de estresse encerrada. Não preparar E20. E12/E16 cumprem a solicitação de observar pressão mais clara sobre o atendimento da infraestrutura configurada: E16 acrescenta timeouts legítimos, acúmulo de pendências e acionamento da proteção, com recuperação. Isso não estima capacidade máxima, não demonstra saturação sustentada e não autoriza afirmar perda de pacotes.

Fontes: [revisão E12](../experiment_results/development-stress-e12-20261029/analysis/stress_E12_A-review.json), [revisão E16](../experiment_results/development-stress-e16-20261029/analysis/stress_E16_A-review.json), seus journals, certificados e recursos efetivos. Ambas têm integridade técnica, dataset válido/elegível, encerramento controlado e recuperação observada. Nenhuma revisão, tentativa ou dado foi alterado nesta consolidação; não foi feita nova coleta nem reaberta auditoria histórica.

| Execução/fase | Starts legítimos / RPS | 2xx | Timeouts | Média/p95 dos 2xx, ms | Pendentes início→fim |
|---|---:|---:|---:|---:|---:|
| E12 PRE | 1933 /16,108 |1933|0|31,32/58,10|1→0|
| E12 ACTIVE |1913 /15,940|1913|0|134,78/434,88|0→4|
| E12 POST |1952 /16,268|1952|0|31,17/57,17|4→0|
| E16 PRE |1929 /16,075|1929|0|30,08/58,22|0→0|
| E16 ACTIVE |1010 /15,094|978|32|742,60/1915,82|0→20|
| E16 POST |2779 /16,056|2779|0|37,37/58,39|20→0|

Desfechos por coorte de início. E16 ACTIVE teve sucesso96,83%; não houve outros erros legítimos. Incluindo términos de timeout, média/p95 foram782,53/1980,48 ms. Duração somente dos sucessos é uma distribuição selecionada e não representa todo o impacto.

E12: seed14077813496258071338; emissão150,011098–270,009696 s, duração119,998599 s. E16: seed15360031016164088169; emissão150,006454–216,915292 s, duração66,908838 s. As fases ACTIVE da tabela começam no limite previsto150 s e terminam no certificado real; POST segue até390 s (119,99 s em E12,173,08 s em E16). Seeds, períodos e exposições diferem; não há contraste causal isolado da taxa nem réplicas confirmatórias.

Ataque E12:1409 admissões/starts/términos, zero abandonos,11,7418 RPS iniciados, todos2xx;1406 términos durante emissão e3 depois. E16:1069 admissões/starts/términos, zero abandonos,15,9770 RPS;993 respostas2xx e76 demais desfechos;1049 términos durante emissão e20 depois. Términos durante emissão:11,7168→15,6780 RPS, aumento≈33,8%; não se demonstrou platô entre patamares. Fila ofensiva admitida não iniciada atingiu1 em ambos. Espera admissão→begin p95/máxima:0,334/3,091 ms em E12 e0,352/1,032 ms em E16. Não há limitação relevante demonstrada do gerador; a agenda legítima integral segue não comprovada.

CPU Docker média PRE/ACTIVE/POST: E12=22,77/156,43/24,20%; E16=20,49/193,21/25,74%. Ambas: pool2, afinidade/cpuset0–11, CPU sem quota nos cgroups registrados. CPU100% corresponde a um núcleo lógico equivalente. Utilização próxima de dois núcleos, atrasos e timeouts são evidência conjunta de pressão sobre o atendimento, não capacidade máxima medida.

Em E16, pendências legítimas nas fronteiras150/180/210/fim real:0→3→29→20. Não houve crescimento≥5 em duas janelas completas consecutivas nem pendências com idade>3 s nessas fronteiras. Há acúmulo expressivo e perda de sucesso, mas clientes terminam por timeout: a saída da contabilidade do cliente não comprova cancelamento do trabalho na vítima. Não inferir ausência de fila interna por ausência de envelhecimento do cliente.

As quatro janelas completas E12 e as duas completas E16 excederam2×p95 PRE: comprometimento forte por duração. O trecho final E16 tem somente99 starts e6,915 s: sucesso77,78% é descritivo, sem suporte para o critério de janela completa. Separadamente, a proteção causal teve suporte próprio:32/160 (20%) sem2xx em3 s, coorte madura, motivo `service_compromise`. Decisão disponível216,894746 s; comando216,914188 s; stop recebido216,915286 s; fim efetivo216,915292 s; última conclusão ofensiva218,273778 s. Em E12 não houve parada; última conclusão270,182648 s.

Legítimos e coleta continuaram até390 s. Primeira confirmação de recuperação: fim do segundo bin330 s em E12,300 s em E16; horizontes nominais333/303 s. Decisões batch disponíveis somente após fechamento≈390,016/390,023 s; nenhuma perda posterior de qualificação. Esses tempos não são detecção online dos detectores.

Recomendação: encerrar DEVELOPMENT de estresse e fechar o [protocolo reduzido](scientific_reduced_protocol_proposal_20261029.md). E12 permanece evidência exploratória de intensidade inferior; E16 sustenta a escolha prospectiva de um cenário de impacto claro, sem garantia de que todo TEST repetirá esse efeito. Nenhum desses dados se torna BASELINE/CAL-A/CAL-B/TEST independente.
