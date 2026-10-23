# Modelo de ataque HTTP contínuo: auditoria e fundamentação

Documento para discussão com o orientador, 23/10/2026. Checkout auditado:
`e865bea5810d3eaeb16e5ebec77a02b6e4750f48`. Escopo documental: não houve mudança de
runtime/schema, campanha, recalibração, processamento novo de detectores, alteração
de resultados congelados, commit ou push. Não há AGENTS.md na cadeia de diretórios.

**Definição recomendada:** carga HTTP adversarial contínua, em controle aberto,
com intervalos exponenciais de geração e demanda computacional definida por
endpoint. “Contínua” descreve ausência de pausas/bursts programados dentro da
janela, não RPS elevado, fluxo de bytes ininterrupto ou saturação comprovada.
A literatura sustenta o mecanismo geral de consumo de recursos por HTTP válido;
os números e a distribuição escolhidos no simulador são decisões experimentais,
com limites de implementação e caracterização de capacidade ainda necessários.

## 1. Autoridade dos parâmetros: campanha, não defaults

Foram lidos README e documentos atuais de proxy, container_sources, operações,
attack_patterns, ground_truth, dataset, protocolo Stage14 v2, freezes e auditorias
anteriores de HTTP/CUSUM. A cadeia usada para os parâmetros reais foi:

```text
15A scoring manifest
 ├─ test_collection_freeze + test_inventory
 │   └─ entries[scenario=C].output_path + artifacts[path,sha256,size]
 │       ├─ raw/effective_config.json
 │       └─ raw/source_artifacts/{source_plan.json,attack_1/manifest.json,...}
 └─ four_method_calibration_freeze
     └─ protocol + matrix + seed_plan
```

Os hashes/tamanhos de **30 arquivos consumidos** foram conferidos, inclusive as
16 configurações efetivas C: são idênticas exceto id/seed. A comprovação detalhada
está em `experiment_results/continuous-attack-foundation-20261023/evidence.json`.
O leitor de auditoria nesse diretório não importa detectores nem executa runtime.

| Referência | SHA256 |
|---|---|
| 15A scoring manifest | `089a25681dd13810a94a92def805aa9a7e314955ebdcca671d625d959ae3a9d5` |
| TEST inventory | `10ab05b24e9896d41e944192909f79b366e8cbbe7e08eb24f695b5d2ad1c2b47` |
| TEST collection freeze | `8d784758ff7b751f68dc595d434a65bae1d764d5a21312b0e3d96a5f6613327d` |
| Four-method calibration freeze | `898e79394ac48a86a734100d324d0b6b966412166a0eac105dbdeccb2bd236f5` |
| Stage14 protocol v2 | `59f5311e8ee0a05523c80938b7b08ddfaacd0bf8000a077c9de1ab675803872c` |

Caminhos: `experiment_results/stage15a-test-scoring-20261019/`,
`experiment_results/stage14d-test-campaign-20261019/`,
`experiment_results/stage14-ewma-cusum-calibration-20261019/` e
`experiments/protocols/stage14_protocol_v2.json`. Os diretórios e todos os arquivos
originais permaneceram somente leitura.

A origem documental da escolha experimental é `docs/stage13b-protocol-proposals/report.md`,
§§2 e 13: manter /medium, benignos 4×2 e atacante 1×8, sem micrograde escolhida
pela separação dos scores; o próprio documento limita a evidência de saturação.
Isso era **proposta**, não autoridade final. Stage14A registra preservação dessas
escolhas; o protocolo v2 e as configurações efetivas congeladas confirmam a adoção.
Os estados históricos “não liberado” de documentos anteriores não substituem o
freeze posterior nem autorizam novas execuções agora.

## 2. Comportamento implementado

### Configuração → source → requisição

`ExperimentConfig.from_dict/load` combina JSON com dataclasses e valida tipos,
profile, quantidades, taxa e compatibilidade da topologia. `AttackConfig.end_seconds`
soma início e duração. `attack_pattern` escolhe ContinuousFlood, que descreve
uma janela única; a execução contínua preserva o gerador histórico, sem usar
allows/deadline para rejeitar cada tarefa ao começar.

`SourceManager.start` cria um container por entidade: quatro sources benignos e
um atacante nesta campanha. Cada manifesto recebe o endpoint NGINX, índice global
RNG, seed e quota de envio. `source_runner.main` cria **um worker de agendamento
por source**, relógio compartilhado homologado e ThreadPoolExecutor local.

No modo host, `start_http_flood` cria um worker por atacante, com executor da
classe compartilhado. Em containers, cada origem tem seu próprio executor, cuja
quota deriva do mesmo orçamento agregado. O controle de início/parada no host
ocorre nos ticks do orquestrador; em containers o controle consulta o relógio
aproximadamente a cada 10 ms. O fluxo prioritário desta auditoria é containers.

### O que é contínuo e como se gera a taxa

`traffic_injectorV0.http_request_worker` executa enquanto attack_active:

1. escolhe a URL do serviço, registra admissão no GroundTruth/journal e submete
   uma tarefa `_send_one` ao executor;
2. sorteia `rng.expovariate(rps_per_worker)`;
3. espera esse intervalo via stop_event.wait e repete, sem esperar a resposta.

O primeiro despacho é imediato após iniciar o worker, sem sorteio anterior.
Intervalos sorteados posteriores são exponenciais; a seed deriva de
`SHA256(str(seed)+":attack:"+str(worker_index))`, independente de IP/nome Docker.
São streams pseudoaleatórios reproduzíveis de sorteios, não reprodução exata do
escalonamento do SO, do tempo de HTTP ou das contagens por janela entre execuções.
Não há bursts, silêncio programado, adaptação à CPU da vítima ou feedback dos
detectores no ramo continuous. Há gaps aleatórios naturais entre despachos.

**`attack.rate` é nominal por entidade atacante**, não por send worker nem total.
Aqui um atacante/source tem um scheduler a 8 RPS: espera exponencial média de
0,125 s. Os 64 send workers não geram 64×8 RPS. Com N fontes iguais a λ, o alvo
agregado seria Nλ; somente o orçamento de concorrência é dividido entre fontes.

`worker_quotas(64,N)` usa divisão inteira/resto, e exige N≤64 quando N>0. Uma fonte
recebe 64; quatro receberiam 16 cada. Mais fontes aumentam a oferta nominal total
se λ permanecer constante, mas reduzem quota por fonte com orçamento fixo.
Não é uma intervenção que modifica apenas diversidade de IPs.

### Concorrência e filas

O executor limita tarefas simultâneas; a fila de submissões contínuas não possui
limite explícito. Sob carga, o scheduler pode continuar admitindo enquanto as
tarefas aguardam. CPU do gerador, escrita síncrona do journal, locks, overhead de
submit e wake-up também afetam despacho/início. A ocupação de uma tarefa inclui
HTTP e persistência final, não apenas tempo em socket.

Cada scheduler mantém uma Session Requests compartilhada pelas suas tarefas.
O pool de conexões padrão da receita não transforma pool_maxsize=10 em limite
duro de dez envios, pois pool_block=False. Há reutilização HTTP/1.1; redirects e
retries operacionais estão desligados no caminho proxy. Nenhum desses mecanismos
faz taxa nominal ser igual a throughput recebido. O proxy tem upstream estático,
sem autoscaling/reload, e conecta as redes de entrada/backend à vítima.

### Endpoint e trabalho

Campanha C: `GET http://edos_service:80/medium`. O NGINX encaminha à vítima;
`request_workload('/medium')` devolve **100000 iterações**, sleep zero. `_burn_cpu`
executa sqrt e sin no laço, através de ProcessPoolExecutor persistente com dois
processos; o handler HTTP espera a conclusão desse trabalho antes da resposta.
A fila de processos da vítima é distinta da fila de envio do cliente.

`/light`, `/medium`, `/expensive` correspondem a 10000/100000/1000000 iterações.
Isso é orçamento de um kernel sintético, não duração fixa, CPU-segundos conhecidos,
FLOPs medidos ou vulnerabilidade de uma aplicação real. CPU-segundos por requisição
precisam de caracterização no ambiente. Não há banco de dados, busca dependente
de entrada, payload especialmente construído, TLS ou slow-header/slow-body aqui.

**Benigno e atacante usam o mesmo /medium.** work_units=10 no benigno e 5000 no
atacante são campos legados ignorados neste path. Não há assimetria de custo
computacional por request entre classes nessa campanha. Há acréscimo controlado
de oferta; o total nominal durante C é 8 benignos + 8 atacantes = **16 RPS**.

### Início, parada e drenagem

A janela planejada é [48,84) s. source_runner ativa o evento quando observa a
janela e inicia o produtor; actual_start só é o primeiro begin na tarefa de envio.
A admissão vem antes de submit. `stop_http_flood` fecha novas admissões sob lock,
sinaliza stop_event/attack_active e faz joins curtos. Uma admissão que ocorreu
antes do stop permanece válida mesmo que seu submit/início termine depois.

Tarefas contínuas já admitidas não revalidam deadline ao executar e não são
canceladas: podem iniciar depois do fim nominal/stop. `actual_end` certifica
admissão fechada e nenhum pendente aguardando begin, com instante posterior ao
último início; não significa que todos os bytes foram transmitidos. Requisições
em voo continuam. `drained_end` registra última conclusão; source_closed é
certificação posterior. drain tenta aguardar por 30 s; SourceManager concede até
35 s antes de encerrar sources restantes, preservando incomplete/ausências.
Timeout HTTP de 2 s é conexão/leitura, não deadline absoluto incluindo fila/logs.

Isso difere de PeriodicBurst, que reserva slot antes de submit e revalida a
janela no begin, sem transportar oportunidades expiradas. Não é correto atribuir
essa política de descarte ao contínuo.

### Oferta, inícios e recebimento não são a mesma medida

| Evento/taxa | O que se sabe atualmente |
|---|---|
| Taxa configurada | λ nominal dos sorteios por scheduler/source; não é contagem observada nem teto por segundo. |
| Admissões | Journal admission, antes do executor; submit frustrado pode produzir abandoned_admission. Não identifica por si só um HTTP recebido. |
| Inícios cliente | request_begin/request_log.elapsed_seconds, depois da fila e locks anteriores ao sample, antes de logs síncronos e session.get. request_starts é contado offline por essa janela de começo. |
| Transmissão | Não há timestamp de primeiro byte por request_id; TCP capturado não é um contador direto de requests HTTP. |
| Recebimento NGINX | Access com request_id evidencia processamento; `$msec` marca conclusão/log, não início de chegada. Não usar esse timestamp como se fosse RPS recebido por janela de begin. |
| Recebimento vítima | Upstream, routing evidence e corpo/hostname demonstram caminho/resposta. Não há timestamp científico de chegada à vítima. Falhas podem ocorrer antes dela. |
| Conclusões | request_log.end_elapsed_seconds; podem pertencer a outras janelas e ocorrer após emissão. Não são novos request_starts. |

Mais detalhes dos limites das durações estão em `docs/http_timing_audit.md`.

## 3. Parâmetros atuais e justificativas

Classificação: **L** = princípio diretamente sustentado pela literatura citada;
**E** = decisão experimental; **C** = adequação dependente de caracterização de
capacidade. E+C não significa que a adequação já foi demonstrada. Nenhum artigo
abaixo fornece o conjunto numérico do nosso cenário.

| Escolha | Campanha C congelada | Classe / justificativa e limite |
|---|---|---|
| Mecanismo HTTP válido que demanda recursos | GETs completos para vítima via NGINX | L [R1,R2] para mecanismo geral; E para a implementação sintética. Não demonstra exaustão por si só. |
| Continuidade | Uma janela, sem off programado/bursts | E, compatível com oferta sustentada discutida em [R1,R2]; não é sinônimo de alta taxa. |
| Distribuição | Exponencial entre despachos posteriores, primeiro imediato | E: simplificação estocástica controlada. [R5] fundamenta distinguir controle aberto/fechado, não esta distribuição específica como comportamento universal de ataques. |
| Atacantes | 1 source/container, 1 scheduler | E: isolar um fator; não representa botnet distribuída nesta campanha. |
| Taxa atacante | 8 RPS/source; total nominal 8 | E+C: escolha mantida do piloto/protocolo. Não derivada de artigo, limite de capacidade ou otimização de detector no TEST. |
| Benignos | 4 sources ×2 RPS = 8 nominais | E+C: carga de referência fixa; mesmo /medium. Não modelo validado de usuários humanos. |
| Janela / duração do run | [48,84), 36 s ativos; run 144 s | E: PRE48/POST60 e observação de métodos, não duração típica de ataque na literatura nem garantia universal de recuperação. |
| Endpoint | /medium para ambas as classes | E+C: controle do custo de serviço; sem seleção adversarial de operação mais cara nesta campanha. |
| Custo do kernel | 100000 iterações, sleep=0 | E+C: repetibilidade do trabalho; custo físico dependente de CPU, runtime, contenção e IPC. |
| Concorrência de envio | 64 por classe; atacante recebe64, benignos16 cada | E+C: orçamento técnico. Não equivale a64 fontes/requests por segundo ou capacidade da vítima. |
| Fila contínua | Sem limite explícito/cancelamento na parada | E: preservação do contrato histórico; afeta backlog e instante de begin. Não é prescrição da literatura. |
| Timeout | 2 s por conexão/leitura Requests | E+C: não prova espera máxima global de2 s nem garante que requests atinjam o servidor. |
| Vítima | Uma instância, pool CPU2 processos | E+C: ambiente controlado. Dois processos não certificam dois núcleos dedicados ou uma capacidade conhecida. |
| Transporte/topologia | Containers → NGINX HTTP/1.1 → vítima, redes separadas | E: controle do caminho. Não é replicação de clusters/Internet dos artigos. |
| Autoscaling/custo | Desligado; custo fictício por instância-hora | E: manter infraestrutura fixa; sem cobrança cloud real ou efeito econômico incremental demonstrado. |
| Seed/amostragem | Seeds disjuntas por papel, TEST16 pareadas B/C/P; janela1s | E: desenho do protocolo. Pareamento não torna contagens/scheduling idênticos. |
| Campos legados de trabalho | attack5000, normal10, default_server1000000 | E/compatibilidade; sem efeito no trabalho de /medium, portanto não justificam intensidade desta campanha. |

**Contraste com defaults antigos:** AttackConfig ainda declara 4 atacantes,
10 RPS/atacante, início20, duração140, endpoint `/` e work5000. Esses valores não
são os parâmetros C efetivos. Os perfis antigos container_sources/proxy_single_victim
e os smokes curtos também não substituem o protocolo/configuração científica.

## 4. Fontes primárias e alcance da comparação

A numeração “página PDF” abaixo começa em1. Não se transferem RPS, concorrência,
volumes ou durações entre ambientes só porque ambos usam HTTP. As referências
sustentam partes distintas do argumento; não existe equivalência integral.

### R1 — requisições válidas e classes de ataque a recursos

**Ranjan, S.; Swaminathan, R.; Uysal, M.; Knightly, E.** *DDoS-Resilient Scheduling
to Counter Application Layer Attacks under Imperfect Detection*. IEEE INFOCOM,
2006, pp.1–13. [DOI](https://doi.org/10.1109/INFOCOM.2006.127);
[texto integral, espelho do manuscrito HP Labs](https://shiftleft.com/mirrors/www.hpl.hp.com/research/ssp/papers/2006-04-infocom-ddos.pdf).

**Suporte:** §§II–III, especialmente §III.B, páginas PDF4–5. Distingue aumento da
frequência de requests e escolha de operações de maior demanda; demonstra consumo
de CPU/serviço sem precisar saturar o link. A comparação assimétrica contempla
menor volume de rede. Os clientes de parte dos ensaios usam think-time após resposta.

**Fundamenta:** separar taxa e custo por requisição e caracterizar o gargalo.
**Diferença:** nosso C mantém /medium igual ao benigno, não o ataque assimétrico
de e-commerce/TPC-W do artigo. Think-time exponencial fechado não valida o nosso
intervalo exponencial aberto nem os números8/64. Não replicamos sua defesa.

### R2 — consumo computacional por requests HTTP aparentando normalidade

**Walfish, M.; Vutukuru, M.; Balakrishnan, H.; Karger, D.; Shenker, S.** *DDoS
Defense by Offense*. ACM SIGCOMM, 2006, pp.303–314.
[PDF da versão SIGCOMM](https://www.cs.columbia.edu/~danr/courses/6772/Fall06/papers/d-by-o.pdf);
[lista do autor, identificando a versão 2006](https://cs.nyu.edu/~mwalfish/papers/).

**Suporte:** §1, página PDF1, e §§2–3, páginas PDF2–3. O modelo de ameaça inclui
requests válidos consumindo recursos computacionais; a ilustração da §3 considera
custo de serviço por request e oferta agregada frente à capacidade.

**Fundamenta:** usar HTTP válido e estudar demanda computacional, sem identificar
ataque apenas por payload malformado. **Diferença:** o artigo implementa speak-up
e hipóteses sobre banda dos atacantes; não usamos essa defesa ou suas condições.
A capacidade não foi medida aqui e “contínuo” não implica essas hipóteses. Nenhum
parâmetro8 RPS/36 s/100000 iterações vem dele. Não confundir com a versão TOCS 2010.

### R3 — baixa taxa ligada a um mecanismo específico, não a um rótulo

**Guirguis, M.; Bestavros, A.; Matta, I.; Zhang, Y.** *Reduction of Quality (RoQ)
Attacks on Internet End-Systems*. IEEE INFOCOM, 2005, pp.1362–1372.
[DOI](https://doi.org/10.1109/INFCOM.2005.1498361);
[PDF dos autores](https://people.bu.edu/danazh/research/papers/infocom05.pdf).

**Suporte:** §I, página PDF2; §II.A, página PDF2; §III e §IV. O ataque explora
transientes da adaptação de um controlador de admissão com rajadas repetidas;
a potência compara dano e custo/carga de ataque.

**Fundamenta:** pedir evidência de dano relativo ao custo e do mecanismo temporal
para alegar baixa taxa eficaz. **Diferença:** nosso contínuo não programa rajadas
nem explora controlador adaptativo demonstrado. Este artigo não fundamenta dizer
que8 RPS é LDoS, nem fornece a intensidade do nosso cenário. Mesmo um periódico
não seria automaticamente uma reprodução de RoQ sem comprovar a vulnerabilidade.

### R4 — o componente econômico do EDoS

**Baig, Z. A.; Binbeshr, F.** *Controlled Virtual Resource Access to Mitigate
Economic Denial of Sustainability (EDoS) Attacks against Cloud Infrastructures*.
CLOUDCOM-ASIA, 2013, pp.346–353.
[DOI](https://doi.org/10.1109/CLOUDCOM-ASIA.2013.51);
[registro institucional](https://pure.kfupm.edu.sa/en/publications/controlled-virtual-resource-access-to-mitigate-economic-denial-of/).

**Suporte:** §I, p.346 (página2 do PDF local, que tem capa adicional), e §§III–IV.
O argumento relaciona demanda maliciosa, provisão elástica e sustentabilidade
financeira; o trabalho propõe controle de acesso a recursos virtuais.

**Fundamenta:** exigir modelo explícito de recursos cobrados e impacto econômico.
**Diferença:** nossa vítima é fixa e o custo por instância é fictício; não medimos
cobrança cloud incremental. Essa fonte não transforma consumo de CPU em prejuízo
financeiro demonstrado. Não se importaram seus parâmetros de simulação.
O texto integral local foi lido em `docs/references/Artigos colocados/ControlledVirtualResourceAccesstoMitigateEconomicDenialofSustainabilityEDoSAttacksagainstCloudInfrastructures.pdf`.

### R5 — referência metodológica de geração, não um modelo de atacante

**Schroeder, B.; Wierman, A.; Harchol-Balter, M.** *Open Versus Closed: A Cautionary
Tale*. 3rd USENIX NSDI, 2006, pp.239–252.
[publicação e bibliografia oficiais](https://www.usenix.org/conference/nsdi-06/open-versus-closed-cautionary-tale);
[texto integral oficial](https://static.usenix.org/events/nsdi06/tech/full_papers/schroeder/schroeder_html/index.html).

**Suporte:** §1 e Figura1, pp.239–240; §5.1. Distingue chegada independente de
conclusão de chegada condicionada à resposta e mostra consequências de modelagem.

**Fundamenta:** declarar controle aberto e não chamar nossa taxa de think-time
pós-resposta. **Diferença:** não valida o processo estocástico específico do ataque,
seus parâmetros ou realismo de uma população de adversários. Nosso produtor é
aberto por não esperar HTTP, mas tem capacidade finita de iniciar/envio e custos
de software. Não se deve transportar resultados entre modelos sem verificar isso.

**Alcance da fundamentação:** R1/R2 sustentam o mecanismo HTTP→recursos; R3/R4
impõem limites às classificações; R5 sustenta explicitar o gerador. A exponencial
aberta é escolha experimental, não uma distribuição universal de ataques comprovada
por esses textos. Os comentários genéricos do código sobre “Poisson” não substituem
uma validação do processo observado ou uma referência para cada número escolhido.

## 5. Proposta formal: mecanismo, idealização e observação

Representar a condição adversarial por

```text
A = (I, N, {lambda_i}, F, {M_i}, e, w, politica_de_admissao/parada)
I = [a,b); F = Exponencial(lambda_i)
e = endpoint HTTP; w = orçamento de trabalho sintético por request
M_i = máximo de tarefas simultâneas no executor da fonte i
```

Para o C congelado: I=[48,84), N=1, lambda_1=8/s, M_1=64,
e=GET /medium, w=100000 iterações, sleep=0; política contínua com fila de
admitidos e drenagem. A vítima tem pool de trabalho 2; a rede e o NGINX permanecem
parte do sistema, não uma constante de capacidade abstrata.

### Idealização matemática, explicitamente condicional

Se as oportunidades fossem chegadas pontuais independentes sem custo de despacho,
sem primeiro ponto forçado e sem atraso de execução, poderíamos modelar

```text
lambda_i(t) = lambda_i * 1_[a,b)(t)
N_i(J) ~ Poisson(lambda_i * comprimento(J intersecao I))
Lambda_ataque = soma_i lambda_i
```

O custo médio físico c_e, em CPU-segundos/request, seria parâmetro **medido**, não
igual ao número de iterações. A oferta de trabalho aproximada seria
`Lambda_ataque*c_e` CPU-segundos/segundo; com benignos, somar a demanda deles.
Uma razão aproximada `rho = soma(lambda_i*c_e_i)/C_CPU` só é útil se C_CPU e os
custos forem caracterizados e CPU for o gargalo; não substitui filas/IPC/proxy.
Não se assumiu M/M/2: exponencial de chegadas não torna serviço exponencial.

### Diferenças da implementação

Após o primeiro despacho imediato, um intervalo observado entre submissões tem
aproximadamente a forma `E_ij + D_ij + atraso_de_wakeup`, onde E é o sorteio e D
é trabalho de despacho/locks/journal. Não há compensação por deadlines absolutos.
Mesmo sem fila HTTP, a soma não é exatamente exponencial. No caso simplificado
de D constante independente, a taxa média seria aproximadamente
`1/(1/lambda_i + D)`, não lambda_i; isso é uma aproximação ilustrativa, não ajuste
estimado com TEST. O primeiro ponto imediato também viola um Poisson homogêneo
iniciado vazio: sem overhead, seria um ponto inicial mais as chegadas exponenciais
posteriores. Para36 s e8/s, a idealização Poisson usual teria média288 requests;
o modelo sem overhead com primeiro envio imediato teria média próxima de289.

O instante de begin adiciona espera no executor e locks antes do sample.
O instante de transmissão adiciona instrumentação/preparo; chegada adiciona rede
e processamento. Consequentemente o processo de **inícios observados** não foi
validado como Poisson homogêneo. A continuidade programada aplica-se à autorização
de gerar até stop, não à garantia de que todo begin pertença a [a,b).

### Comportamento efetivamente observado, sem campanha nova

Exemplo já definido em 15C pela menor seed elegível: entry20/C,
seed171864802, run_id `667624953df540e9aa3f3258d96960dd`.

- Configuração8 RPS; **320 admissões,320 inícios e320 conclusões response**.
  Não são uma obrigação de288. Taxa descritiva por duração efetiva de evento:
  **8,889419847/s**; depende desse denominador e não prova o processo Poisson.
- Cada ID atacante tem um único access NGINX e uma resposta de routing evidence
  contendo work=100000. Isso sustenta execução do path de serviço, não um
  timestamp de recebimento por segundo na vítima nem equivalência geral sob erro.
- Primeiro begin48,009586961; fim nominal84; stop84,007432314;
  último begin83,956019089; fechamento84,007436709; drain84,016418803.
  Não houve starts atacantes após84 nesse run; houve uma conclusão após fechamento.
  Outros regimes podem produzir backlog, como demonstrado nos testes sintéticos
  anteriores, mas sua mera possibilidade não deve ser atribuída a este run.

Esta leitura não foi usada para escolher novos parâmetros ou testar distribuição,
nem prova saturação/dano econômico. A correspondência de código/receitas no host
não é uma nova certificação de conteúdo da imagem sources cached. A resposta
arquivada fornece evidência operacional do trabalho reportado naquele run.

## 6. Como escolher parâmetros futuros de forma reproduzível

Proposta para aprovação futura; **não executada** nesta etapa:

1. Declarar a pergunta: detecção de mudança de carga, degradação do serviço benigno,
   ataque assimétrico a CPU ou impacto econômico. Fixar previamente critérios de
   êxito de serviço e qual mecanismo será manipulado; não escolher intensidade
   pela curva/recall de detector no TEST já analisado.
2. Congelar código, imagem por ID/digest, limites CPU/memória, pool da vítima,
   transporte/keepalive, redes e condições do host. Distinguir taxa ofertada,
   admissões, begins e serviço concluído. Registrar presença/limites do gerador;
   uma fila nele não deve ser confundida com fila na vítima.
3. Em DEVELOPMENT/caracterização independente, medir demanda por endpoint e curva
   de capacidade de serviço com critérios externos aos detectores, por exemplo
   percentil de duração cliente previamente definido e orçamento de erros do
   tráfego benigno. Usar CPU real da vítima, throughput, caudas e erros em conjunto;
   medir custo físico em unidades explícitas. Não presumir que100000 iterações
   define uma duração, nem que pool 2 equivale a dois núcleos dedicados.
4. Definir antes uma grade de ofertas relativas à capacidade caracterizada e
   escolher níveis pelo objetivo de carga/degradação, com repetições e incerteza.
   Se variar N, manter agregado fixo quando quiser isolar distribuição de fontes;
   se mantiver taxa por fonte, declarar que também mudou o volume total. Variar
   custo por request em fator separado; /expensive versus /medium seria outra
   campanha com baseline/calibração próprias, não reinterpretação dos resultados C.
5. Verificar se o gerador acompanha a oferta e publicar a discrepância: contagens
   de admissão/begin e pendentes agregados quando journals completos; não prometer
   tempo de fila por request a partir de admission sem request_id. Se fila/custo
   de logging dominarem, classificar como limite do arranjo ou revisar gerador em
   versão separada antes do novo desenho, preservando os contratos antigos.
6. Fixar primeiro envio imediato, política de fila/parada e duração de PRE/ATIVO/POST
   antes de dados finais. Justificar duração por transientes e suporte desejado,
   sem usar persistência dos detectores no TEST para escolher POST conveniente.
   Se um Poisson ideal for requisito, uma implementação diferente precisa ser
   explicitamente versionada/validada; não é requisito para descrever o atual.
7. Separar seeds/runs de caracterização, BASELINE, CALIBRATION e novo TEST, congelar
   plano e parâmetros antes de revelar TEST. O TEST existente fica somente para
   seus objetivos congelados; nenhuma escolha nova será otimizada nele.

Não há fundamento para fornecer agora uma nova taxa “correta” em RPS sem esses
critérios e caracterização. O protocolo atual deve ser preservado e apresentado
com o alcance que efetivamente teve.

## 7. Classificação defensável e proposta para o orientador

- **Contínuo:** é a forma temporal programada, inclusive em taxa pequena. Não
  é definição de intensidade ou de efetividade de negação de serviço.
- **DoS de aplicação:** o mecanismo planejado é oferta adversarial de HTTP válido
  que compete por recursos. Para afirmar exaustão/DoS bem-sucedido, demonstrar
  perda de disponibilidade/qualidade dos benignos e gargalo, não só um alarme.
  Aqui é defensável falar de *condição experimental de carga adversarial contínua*.
- **DDoS:** o código aceita várias fontes; o C congelado tem um atacante lógico.
  Não se deve descrevê-lo como um botnet distribuído só porque há vários benignos
  ou porque os artigos estudam DDoS. Containers no mesmo host não representam
  heterogeneidade/topologia de múltiplos hosts na Internet.
- **Baixa taxa/LDoS:** declarar referência de capacidade/banda, custo por request
  e eficiência/dano observados, além de mecanismo específico. Baixa taxa pode
  ocorrer com custo assimétrico sem rajadas; mecanismos periódicos/RoQ são outra
  hipótese. RPS8 e nome ContinuousFlood não resolvem essa classificação.
- **EDoS:** demonstrar demanda maliciosa ligada a recursos efetivamente cobrados,
  provisão/escalabilidade quando relevante e incremento causal de custo/risco
  econômico contra controle. Autoscaling é importante em R4, mas cobrança por
  uso pode existir sem ele. Neste arranjo fixo com custo fictício por instância,
  não há evidência de impacto econômico incremental; consumo CPU não basta.

**Proposta de texto:** “Modelamos uma fonte adversarial que, durante um intervalo
finito, gera continuamente requisições HTTP válidas para um endpoint de custo
computacional controlado. A geração não espera respostas e usa esperas exponenciais
pseudoaleatórias entre despachos, com concorrência finita e fila de tarefas
admitidas. Taxa, número de fontes e trabalho por requisição são fatores distintos.
O modelo é inspirado em ataques de aplicação que competem pelos recursos do
servidor, mas não reproduz integralmente um ataque específico da literatura.
Nesta campanha, a condição contínua acrescenta nominalmente 8 RPS de uma fonte à
carga benigna de 8 RPS, usando /medium igualmente nas duas classes; sua classificação
como baixa taxa eficaz, saturação ou EDoS exige evidências adicionais.”

Uma [versão curta para reunião](continuous_attack_proposal.md) acompanha este relatório.

## 8. Evidências de código e verificações executadas

| Arquivo / função | Referência e papel |
|---|---|
| simulator/experiment_config.py | AttackConfig (30), end_seconds (46), ExperimentConfig.load (193), worker_seed (256). |
| simulator/attack_patterns.py | ContinuousFlood (7), attack_pattern (38): janela única; ramo periódico separado. |
| simulator/source_manager.py | worker_quotas (12), start (57), release (116), stop (156): plano, quotas e lifecycle. |
| simulator/source_runner.py | main (21): manifesto, relógio, worker por source, controle temporal e drain. |
| simulator/traffic_injectorV0.py | configure (45), _send_one (75), drain (127), http_request_worker (147), stop_http_flood (421). |
| simulator/ground_truth.py | admit (77), begin_request (96), stop (131), _close_emission (140). |
| simulator/service_destination.py | request_url (5): paths reservados sem query work/sleep; validação do endpoint. |
| simulator/app/simple_server.py | OPERATION_WORK_UNITS (13), request_workload (20), _burn_cpu (33), do_GET (56). |
| simulator/request_logger.py | begin/finish: instantes e persistência das tentativas. |
| simulator/source_aggregate.py | reconcile (26), aggregate (79): fechamento global e CSVs reconstruídos. |
| experiments/extract_features.py | request_starts (226): contagem por instante de begin, não chegada à vítima. |

Foram executados **47 testes existentes**, todos OK, de padrões, sources, GT e
limites de tempo HTTP, sem rede real/campanhas. Cobrem sorteio exponencial,
separação de quota/taxa, filas contínuas, begin tardio, parada/drenagem, endpoints
e custos. Isso não valida estatisticamente o Poisson observado ou capacidade.
Não foram criados testes novos ou modificados módulos de runtime.

```bash
.venv/bin/python -B experiment_results/continuous-attack-foundation-20261023/inspect_evidence.py
.venv/bin/python -B -m unittest tests.test_attack_patterns tests.test_source_containers tests.test_ground_truth tests.test_http_timing_audit tests.test_application_operations -v
```

Outputs novos separados: evidence.json (identidades/parâmetros/contagens),
inspect_evidence.py (auditoria somente leitura) e tests.log sob
`experiment_results/continuous-attack-foundation-20261023/`. As referências
bibliográficas foram consultadas em 23/10/2026; nenhum valor escolhido foi atribuído
a artigo que não o fornece.

**Resposta curta — “Como o ataque contínuo se comporta e qual é sua base?”**
Uma fonte adiciona GETs /medium durante 36 s, com taxa nominal 8 RPS, primeiro envio
imediato e esperas exponenciais posteriores, sem aguardar respostas. Concorrência,
logs e fila tornam os inícios observados diferentes da taxa ideal. A base é o
mecanismo de ataques HTTP válidos que consomem recursos do servidor; os números
são escolhas do experimento, não prescrições da literatura. Este cenário não
comprova sozinho LDoS, saturação, ataque assimétrico ou prejuízo EDoS.
