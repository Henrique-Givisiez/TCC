# Preparação da campanha energy-powersaver-20261109

Data: 09/11/2026. Branch: `refactor/project-organization`.
Commit de referência: `a010183bb2e0b453a3ae9433079b9b208ddbfda2`.
Novos arquivos não commitados são identificados por hashes nos manifestos.

## 1. Resumo executivo

Foram preparados o protocolo de controle ambiental, o adaptador de execução
autônoma, os manifestos e um novo plano científico de 80 slots. Foram executados
exatamente um piloto A3 e um F96, ambos aceitos tecnicamente e caracterizados.
Nenhuma execução da campanha definitiva nova foi iniciada.

Os pilotos utilizaram o perfil `power-saver`, ACPI `low-power`, EPP `power`,
alimentação externa e as imagens/configurações centrais históricas. A3 apresentou
25,37% de sucesso legítimo durante a emissão; F96, 90,97%. Ambos apresentaram
ocupação elevada dos dois workers, filas e degradação de duração HTTP.

A CPU média ofensiva foi 272,33 ms em A3 e 29,21 ms em F96, maior que no TEST
anterior e menor que nas respectivas B2. Não se reproduziu exatamente a B2, nem
se estabeleceu causalmente que o perfil, isoladamente, explique as diferenças.

Classificação: **READY_WITH_RESTRICTIONS**. A infraestrutura está preparada; a
adequação científica dos cenários, a extrapolação de 30 para 120 s e a autorização
das 80 execuções continuam reservadas ao pesquisador.

## 2. Auditoria da infraestrutura

O executor existente `scientific_campaign.Campaign` já oferecia sequência das
quatro partições, exclusão mútua, journal encadeado, tentativas consumidas,
recibos técnicos, checkpoints, recuperação offline e seleção de limiares antes
do TEST. `DockerBackend` e `scientific_collection` já faziam preflight, captura,
coleta/exportação, validação estrutural e extração de features. O launcher
`c135_o3` fixa a especificação pelo hash.

Foram reutilizados esses componentes, sem alterar seus arquivos. Os novos módulos
são `experiments/energy_control.py`, `energy_campaign.py` e
`energy_pilot_analysis.py`. A implementação adiciona observação do host, supervisão
do subprocesso existente, selos ambientais, bloqueio de autorização, status e
análise descritiva dos pilotos. Endpoints, imagens, detectores e critérios de
calibração/eligibilidade permanecem intactos.

Lacunas atendidas: energia/AC ausentes do lock anterior, ausência de verificação
durante cada run e de uma interface simples de acompanhamento. Política escolhida:
qualquer falha interrompe a progressão; nenhuma substituição, repetição ou
perda de slot é autorizada automaticamente.

## 3. Protocolo experimental

Especificação científica reutilizada: C1.3.5/O3, SHA256
`c97f8ece0198af720af4781409c12332508b45073cb62234a2c105864bf28018`.
Complemento ambiental: `docs/energy_powersaver_campaign_20261109.md`, versão 1.

Condições: `power-saver`, ACPI `low-power`, fonte externa online, topologia direta,
uma vítima com dois workers, legítimos 2×8 RPS `/medium`, timeout 2 s. A3 mantém
2×4 RPS `/expensive`, orçamento 64; F96 mantém 2×32 RPS `/medium`, orçamento 96.
As intensidades não foram aumentadas.

Pilotos: protocolo B2 de 150 s, PRE [0,30), emissão [30,60), POST [60,150), sem
warmup separado inventado. Drenagem e conclusões posteriores são preservadas.
Campanha: 4 BASELINE + 8 CAL_A + 8 CAL_B + 60 TEST; 20 blocos L2/A3/F96, 390 s,
warmup [0,30), PRE [30,150), emissão [150,270), POST [270,390). Nova calibração
própria; nenhum limiar histórico reutilizado.

Há checks antes/depois de cada run e nas transições, e amostras ambientais a cada
5 s durante a coleta. Perfil, ACPI, EPP/governor, limites, boot, afinidade e imagens
divergentes interrompem. Suspensão é detectada pelo desvio BOOTTIME−MONOTONIC.
Temperaturas, throttling e frequências instantâneas são registrados quando
disponíveis, sem serem tratados como médias efetivas da execução.

Aceitação dos pilotos exige certificado/cleanup, processo, dataset e ambiente
válidos; a caracterização exige relógios, identidade e ciclos completos. Não há
um limiar retrospectivo de indisponibilidade ou saturação para aceitar o cenário.

## 4. Automação

Bundle: `experiments/protocols/energy-powersaver-20261109/`.
Plano: `plan.json`; controle: `control.json`; ambiente: `environment.json`;
histórico de sementes: `seed_audit.json`. Todos os 80 IDs usam o prefixo
`ps_direct80_`; sementes novas preservam o pareamento por bloco.

Resultados definitivos reservados:
`experiment_results/scientific-energy-powersaver-20261109/`.
Esse diretório não foi utilizado para coleta nesta atividade.

O CLI pode operar em terminal sem Codex. O hash do controle é:

`40a61e298f1c9d471d82d58bae84f66cab5be18afb58153d0bfe083caaf5be27`

**Comando de início, exclusivamente após autorização posterior: ESTE COMANDO NÃO
FOI EXECUTADO.**

```bash
.venv/bin/python -B -m experiments.energy_campaign run \
  --control-sha256 40a61e298f1c9d471d82d58bae84f66cab5be18afb58153d0bfe083caaf5be27 \
  --authorize-campaign energy-powersaver-20261109
```

Consulta e interrupção segura:

```bash
.venv/bin/python -B -m experiments.energy_campaign check
.venv/bin/python -B -m experiments.energy_campaign status
.venv/bin/python -B -m experiments.energy_campaign stop
```

Retomada: mesmo comando de início, acrescentando `--resume --reason 'diagnóstico
realizado pelo pesquisador'`. Slots aceitos não são recoletados. Tentativa consumida
sem selo ambiental válido não pode ser repetida ou aceita automaticamente.
Falhas parciais ou desconhecidas exigem intervenção. Não há retry automático.

Estados: PENDING, RUNNING, ACCEPTED técnico, REJECTED técnico, FAILED e INTERRUPTED.
Elegibilidade dos detectores permanece um resultado científico separado.
Status fornece contagens, partição, tempo, ETA aproximado e último ambiente/erro.
Logs: `collection/<id>/attempt-1/execution.log`; amostras e selos no mesmo diretório;
transições gerais em `automation/events/`. O checkpoint TEST consolida o resumo.
O procedimento completo está no documento de protocolo.

## 5. Validação técnica

- Suíte integrada: **75 testes aprovados**, incluindo controlador científico,
  operações diretas, protocolo direto, avaliação, C1.3.5 e controles de energia.
- Após os últimos ajustes, **13 testes do adaptador aprovados**: bloqueio sem
  autorização, energia/AC/EPP/governor/boot/suspensão, encerramento por divergência,
  validação posterior ao processo, publicação sem sobrescrita, plano de 80 slots,
  pareamento, sequência/retomada e interrupção por falha. São fixtures/mocks.
- O analisador novo reproduziu os valores B2 conhecidos: CPU ofensiva
  364,683652/33,084671 ms, picos ACTIVE 324/241 e timeouts legítimos 471/416.
- `freeze` validou o plano pelo loader científico existente; nenhuma coleta foi
  iniciada por esse comando. O CLI de validação foi usado como check offline final.
- O status confirmou 80 PENDING e zero RUNNING/ACCEPTED/REJECTED/FAILED/INTERRUPTED
  na campanha nova, sem eventos de execução.
- Os quatro checkpoints antigos mantiveram seus hashes originais, incluindo TEST
  `0747cbc481cc5d7b72be1bfeecb63ca5eb66eeeeb11f6db6a878a2246aeb91b0`.

## 6. Piloto A3

Run `afb557ab3cf243d2b29719a533f2cb7b`.
Dados: `experiment_results/pilots-energy-powersaver-20261109/A3/`.
Dataset SHA256: `0ce72eed4aa54ebfbb581c7cb5ebe21ec8d226963feaba8526266829daa24011`.
Fonte derivada: `reports/energy-powersaver-20261109/A3.json`.

### Computação da coorte submetida em [30,60)

| Classe | Submetidas/iniciadas/concluídas da coorte | Inícios/conclusões dentro da janela | CPU média/mediana/p95 ms | Parede média/mediana/p95 ms | Espera média/mediana/p95 ms |
|---|---:|---:|---:|---:|---:|
| Legítima | 477/477/477 | 347/349 | 28,50/27,90/35,16 | 28,45/27,86/35,20 | 5.506,43/5.277,42/11.023,83 |
| Ofensiva | 251/251/251 | 185/183 | 272,33/267,11/306,13 | 272,36/267,07/306,39 | 5.398,41/5.074,43/10.893,67 |

Taxa total de submissão: 24,27/s; conclusão dentro da janela: 17,73/s. Conclusões
por janela podem incluir trabalhos submetidos antes dela. Pendências iniciais 2,
finais 198; pico ACTIVE 201, sendo pico aguardando 199. Média de workers ocupados
1,994/2; ambos ocupados por 99,44% do intervalo.

Em bins de 10 s, submissões/conclusões/pendentes finais: 244/195/51,
253/163/141, 231/174/198. Há crescimento sustentado. O pico completo foi 223,
durante POST; não confundir esse valor com o pico de emissão.

### HTTP legítimo por coorte de início

| Período | Inícios | 2xx | Timeouts | Sucesso | Todos encerramentos: média/mediana/p95 ms | Somente 2xx: média/mediana/p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| PRE | 482 | 482 | 0 | 100% | 45,94/38,23/79,44 | 45,94/38,23/79,44 |
| ACTIVE | 477 | 121 | 356 | 25,37% | 1.759,92/2.004,36/2.005,61 | 1.039,93/980,91/1.952,85 |
| POST | 1.401 | 1.170 | 231 | 83,51% | 398,43/39,36/2.005,03 | 81,30/37,13/83,29 |

Emissão ofensiva: 251 admissões, submissões, tarefas despachadas e inícios HTTP;
8,367 inícios/s; zero expirações pré-HTTP; 54 respostas 2xx e 197 timeouts.
Despacho médio/p95: 0,39/0,63 ms. HTTP ofensivo em voo médio/pico: 14,67/26.
Planos ofensivos independentes: não disponíveis, registrados como null.

Pendências computacionais atingem zero no ponto 80 s dos bins, e são zero em
150 s. Isso não transforma todo o POST em período recuperado: ele contém 231
timeouts. As conclusões posteriores da coorte são mantidas, sem imputação.

Integridade: 2.611 operações correlacionadas; ciclos completos; processo rc=0;
dataset válido/elegível; certificado completed e cleanup verificado. Selo ambiental
válido, 33 amostras, todas com power-saver e AC online, além de checks antes/depois.

## 7. Piloto F96

Run `eeb1e87525ed448eba6417e04cb9190a`.
Dados: `experiment_results/pilots-energy-powersaver-20261109/F96/`.
Dataset SHA256: `8a8d65e6c01cdf22a46dc5670601dd084ca91b9ede0f124e54730c463a799f44`.
Fonte derivada: `reports/energy-powersaver-20261109/F96.json`.

| Classe | Submetidas/iniciadas/concluídas da coorte | Inícios/conclusões dentro da janela | CPU média/mediana/p95 ms | Parede média/mediana/p95 ms | Espera média/mediana/p95 ms |
|---|---:|---:|---:|---:|---:|
| Legítima | 487/487/487 | 454/454 | 29,25/28,69/36,05 | 29,18/28,53/36,01 | 1.581,36/1.716,82/2.013,16 |
| Ofensiva | 1.665/1.665/1.665 | 1.574/1.572 | 29,21/28,62/35,70 | 29,15/28,55/35,70 | 1.518,54/1.674,73/1.994,88 |

Submissão total na vítima: 71,73/s; conclusão dentro da janela: 67,53/s.
Pendências iniciais zero, finais 126; pico 137, aguardando 135. Média de workers
ocupados 1,976/2; ambos ocupados por 97,77% do intervalo. Em bins: 768/644/124,
670/663/131, 714/719/126. Há acúmulo inicial e manutenção de fila elevada, sem
crescimento monotônico durante todos os 30 s.

| Período | Inícios | 2xx | Timeouts | Sucesso | Todos encerramentos: média/mediana/p95 ms | Somente 2xx: média/mediana/p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| PRE | 509 | 509 | 0 | 100% | 45,92/37,35/80,19 | 45,92/37,35/80,19 |
| ACTIVE | 487 | 443 | 44 | 90,97% | 1.618,17/1.756,61/2.004,09 | 1.579,83/1.732,68/1.985,64 |
| POST | 1.376 | 1.376 | 0 | 100% | 63,89/36,12/79,57 | 63,89/36,12/79,57 |

Emissão ofensiva: 1.879 admissões/submissões/tarefas despachadas; 1.665 inícios
HTTP, 214 expirações anteriores ao HTTP, 55,5 inícios/s, 1.542 respostas 2xx e 123
timeouts. Planos ofensivos independentes: null. Despacho médio/mediana/p95:
1.459,65/1.182,26/3.325,90 ms. HTTP ofensivo em voo médio/pico: 84,60/96.

As expirações são atribuídas à coorte submetida durante a emissão, mesmo quando
resolvidas depois. Não são timeouts de requisições entregues à vítima. Há 93
conclusões ofensivas no POST. Pendências computacionais são zero nos pontos 70 s
e 150 s, sem afirmar instante exato de recuperação entre esses pontos.

Integridade: 4.037 operações correlacionadas; ciclos completos; rc=0; dataset
válido/elegível; certificado completed e cleanup verificado. Selo ambiental válido,
34 amostras, todas com power-saver/AC online. O F96 começou após mais de 60 s de
idle e verificação da certificação A3.

## 8. Comparação B2 × TEST anterior × pilotos

CPU/op em ms; TEST anterior resume 20 runs de ACTIVE completo (120 s). B2 e
pilotos usam coortes de submissão nos 30 s de emissão. A comparação é descritiva.

| Cenário/classe | B2 | TEST anterior | Piloto |
|---|---:|---:|---:|
| A3 legítima | 37,76 | 11,90 | 28,50 |
| A3 ofensiva | 364,68 | 96,20 | 272,33 |
| F96 legítima | 32,92 | 12,80 | 29,25 |
| F96 ofensiva | 33,08 | 12,82 | 29,21 |

O custo ficou entre as etapas anteriores. As razões piloto/TEST são aproximadamente
2,39 e 2,83 em A3 e 2,28 em ambas as classes F96. Não houve reprodução exata B2.

Para alinhar filas/ocupação, a tabela seguinte usa os primeiros 30 s do TEST
anterior (média de 20 runs), além dos 30 s B2 e dos pilotos.

| Cenário/indicador | B2 | TEST anterior inicial | Piloto |
|---|---:|---:|---:|
| A3 pico pendente ACTIVE | 324 | 9,05 | 201 |
| A3 ambos workers ocupados | 99,3% | 31,3% | 99,44% |
| A3 espera legítima média ms | 11.876,92 | 13,06 | 5.506,43 |
| A3 sucesso legítimo | 8,37% | 100% | 25,37% |
| A3 inícios ofensivos/s | 7,933 | 8,123 | 8,367 |
| F96 pico pendente ACTIVE | 241 | 7,50 | 137 |
| F96 ambos workers ocupados | 97,6% | 29,1% | 97,77% |
| F96 espera legítima média ms | 2.521,78 | 2,26 | 1.581,36 |
| F96 sucesso legítimo | 19,07% | 100% | 90,97% |
| F96 inícios ofensivos/s | 49,867 | 63,057 | 55,500 |
| F96 expirações pré-HTTP | 308 | 0 | 214 |

Referência adicional de HTTP 2xx no ACTIVE completo anterior: A3 36,386 ms e
F96 27,583 ms. Nos pilotos, 1.039,93 e 1.579,83 ms; B2 1.224,78 e 1.365,34 ms.
Essas médias são condicionais a respostas 2xx, não às mesmas populações de todos
os encerramentos. F96 piloto preservou mais sucessos que B2, mas permaneceu lento.

Fontes históricas: `reports/b2-a-20261107T234426Z/` e
`reports/b2-f96-20261108T002312Z/` (http/computation_by_period.csv); relatório e
resultados A1.2 (`/tmp/tcc_a12_results.json`), com observações por execução;
resumo da campanha anterior `analysis/summary/manifest.json`. Fontes novas:
`A3.json`, `F96.json`, seus mapas `input_sha256` e os dados primários vinculados.

## 9. Riscos e limitações

- Uma realização por piloto; nenhuma comparação inferencial ou superioridade.
- A condição foi definida prospectivamente. Perfil não é causa isolada comprovada.
- A adequação de 30 s não garante o comportamento sob emissão científica de 120 s.
- F96 entrega menos inícios que o nominal e tem expirações: demanda efetiva deve
  acompanhar a análise. Não se aumenta intensidade automaticamente.
- Monitoramento amostrado a cada 5 s não prova ausência de alterações entre amostras;
  seu custo não nulo não foi quantificado por benchmark.
- Frequência instantânea não equivale à frequência efetiva média por worker.
- Reboot, suspensão ou alteração das políticas/boot congelados bloqueia retomada;
  uma nova referência exige revisão explícita, nunca substituição silenciosa.
- Tentativa incompleta ou ambiente inválido para a sequência e exige diagnóstico.
  O adaptador deliberadamente não garante retomada de qualquer falha parcial.
- O inventário histórico de sementes é fechado: adicionar novos artefatos com
  sementes fora da campanha após o freeze pode invalidar sua verificação.
- Código ainda não commitado, por instrução; hashes completos documentam a versão.

## 10. Prontidão da campanha

**READY_WITH_RESTRICTIONS.** Protocolo, automação, verificações, testes, dois pilotos,
caracterização e plano congelado estão disponíveis. O executor possui o mecanismo
para percorrer as quatro partições, mas não foi testado mediante 80 cargas reais
nesta atividade e não iniciou a campanha. A aprovação científica dos cenários e
a autorização explícita de execução permanecem pendentes.

## 11. Próximas decisões

1. Ambos os pilotos produziram estresse mensurável, sem usar timeout como único
   critério: custo, ocupação, filas e duração legítima também mudaram.
2. A3 apresentou crescimento sustentado de fila; F96 apresentou acúmulo e limitação
   de despacho. Parecem informativos para nova campanha, sujeitos à decisão do
   pesquisador e à ressalva de duração 30/120 s.
3. A automação está preparada e o plano está congelado; os 80 slots seguem PENDING.
4. Manter boot/políticas/fonte, preservar código/configurações e revisar os relatórios.
5. Somente após autorização posterior usar o comando da seção 4. Não houve commit,
   alteração automática de perfil, modificação de campanhas antigas ou coletas extras.
