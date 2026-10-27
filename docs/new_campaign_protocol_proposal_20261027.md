# Proposta de protocolo — campanha com uma vítima

Data: 27/10/2026. Estado: **PROPOSTA PARA REVISÃO**, sem liberação de coleta.
Referência do checkout inspecionado: `73fc5e32daf832165932a3304b12e0db722535cb`.

Este documento traduz as orientações da reunião de 26/10 fornecidas na solicitação
em um desenho experimental. Não foi localizada uma ata independente da reunião;
não se atribuem à reunião decisões além das informadas. Não há `AGENTS.md` na
árvore do repositório nem na cadeia de diretórios ancestrais consultada, inclusive
na raiz do filesystem. Portanto não havia esse arquivo para leitura.

A tarefa compreende inspeção e proposta documental. Não houve execução de
experimentos, fitting, calibração, scoring ou avaliação, nem alteração de
detectores, configurações ou artefatos congelados.

## 1. Autoridades e estado atual

Documentos históricos descrevem o estado de suas respectivas etapas; um texto
antigo dizendo que TEST está bloqueado não invalida a coleta e as etapas
posteriores formalmente registradas. A cadeia atual deve ser lida pelos manifests.

| Fonte real | Papel e situação |
|---|---|
| [README](../README.md), [organização](project_organization.md) | Entrypoints, diretórios e limites dos runners |
| [configuração](experiment_configuration.md), [dataclasses ativas](../simulator/experiment_config.py) | Contrato JSON; o código ativo prevalece sobre defaults e limitações históricos |
| [ground truth](ground_truth.md), [sources](container_sources.md), [operações](application_operations.md), [padrões](attack_patterns.md) | Identidades, geração, endpoints e ciclo de vida |
| [dataset](dataset.md), [schema observado v1](../experiments/dataset_schema.py), [validação](dataset_scientific_validation.md) | Stage8/9, bytes/hashes, validade e elegibilidade distintas |
| [features](feature_timeseries.md), [schema v1](../experiments/feature_schema.py), [framework](detection_framework.md) | Stage10/11, séries regulares e separação features/labels |
| [scores](statistical_scores.md), [EWMA/CUSUM](ewma_cusum_scores.md), [calibrador](stage14-version-closure/empirical-upper-tail.md) | Fórmulas e disponibilidade; notas de autorização dessas etapas são históricas |
| [protocolo v2](../experiments/protocols/stage14_protocol_v2.json), [matriz](../experiments/protocols/stage14_matrix_v2.json), [seeds](../experiments/protocols/stage14_seed_plan_v2.json) | Desenho científico da campanha anterior |
| [freeze dos quatro métodos](../experiment_results/stage14-ewma-cusum-calibration-20261019/four_method_calibration_freeze_manifest.json) | Modelos/limiares congelados; SHA256 `898e79394ac48a86a734100d324d0b6b966412166a0eac105dbdeccb2bd236f5` |
| [protocolo de avaliação](../experiments/protocols/stage14_test_evaluation_protocol_v1.json) | Contrato de métricas/horizontes; SHA256 `c2e1ab6314ab67c984b6b0e8f505982d72ea4de2f463e8607488e73c2764ef20` |
| [freeze de coleta](../experiment_results/stage14d-test-campaign-20261019/test_collection_freeze_manifest.json), [inventário](../experiment_results/stage14d-test-campaign-20261019/test_collection_inventory.json) | TEST FROZEN, 48 runs, 16 seeds B/C/P; [relatório](stage14d1_test_collection_freeze.md) |
| [manifest 15A](../experiment_results/stage15a-test-scoring-20261019/stage15a_scoring_manifest.json), [relatório](stage15a_frozen_test_scoring.md) | Scores/decisões FROZEN, 960 combinações |
| [manifest 15B](../experiment_results/stage15b-test-evaluation-20261019/stage15b_evaluation_manifest.json), [relatório](stage15b_frozen_test_evaluation.md) | Avaliação FROZEN; SHA256 `2b36134d60f9dd5a4dc5bd721f4c5df194cc8ad695ab5d71c73156b5bb5863ca` |
| [15C](stage15c_descriptive_analysis.md) | Análise descritiva entregue para revisão, **não congelada**; sem IC/testes inferenciais |
| [métricas](evaluation_metrics_plan.md), [CPU](cpu_accounting_audit.md), [proxy](proxy_observability.md), [persistência CUSUM](cusum_persistence_audit.md) | Auditorias e limitações; propostas não equivalem a funcionalidade implementada |

Os hashes acima identificam as autoridades documentadas, não constituem uma
nova auditoria exaustiva dos arquivos congelados nesta tarefa.

### 1.1 Geração, taxa e operações

`ExperimentConfig` contém `normal_traffic.clients`, `normal_traffic.rate`,
`normal_traffic.endpoint`, `attack.enabled`, `attack.attackers`, `attack.rate`,
`attack.endpoint`, `attack.profile`, `attack.start_seconds`,
`attack.duration_seconds`, além de `duration_seconds` e `seed` globais.
Configurações reais de referência:
[application_operations.json](../experiments/configs/application_operations.json),
[container_sources.json](../experiments/configs/container_sources.json) e
[proxy_single_victim.json](../experiments/configs/proxy_single_victim.json).
São exemplos/validações, não a matriz da nova campanha.

No modo `traffic_sources.execution="containers"`, cada cliente/atacante é uma
origem em contêiner; inventário e manifests preservam índices lógicos.
`rate` é **RPS nominal por origem**, não taxa agregada nem taxa por thread de
envio. Oferta nominal benigna = `clients × rate`; ofensiva = `attackers × rate`
durante atividade. O ritmo é aberto, com esperas exponenciais e primeiro despacho
imediato; scheduling, filas e concorrência impedem equiparar oferta a starts/s.
Código: [normal_traffic.py](../simulator/normal_traffic.py),
[traffic_injectorV0.py](../simulator/traffic_injectorV0.py),
[source_manager.py](../simulator/source_manager.py).

`max_concurrent_sends` é orçamento **agregado por classe**, dividido por
`divmod(budget,N)` entre sources; filas não emprestam slots entre si. Variar N
altera também sessões, filas e recursos dos geradores. Mesmo com taxa agregada
fixa, não se isola um efeito abstrato de quantidade de IPs.

Em [simple_server.py](../simulator/app/simple_server.py),
`OPERATION_WORK_UNITS` define `/light=10000`, `/medium=100000`,
`/expensive=1000000` iterações do mesmo kernel, com sleep zero. Esses caminhos
exatos ignoram query `work/sleep` e defaults de ambiente. Não são tempos de CPU
garantidos. Outros caminhos, inclusive `/expensive/`, conservam o mecanismo
legado. [service_destination.py](../simulator/service_destination.py) monta a URL
sem query para as três operações. A Stage6 validou custo fixo e independência de
query, com três ensaios técnicos; seus tempos não definem a capacidade científica.

### 1.2 Instâncias, capacidade e autoscaling

Fixar `infrastructure.initial_instances=min_instances=max_instances=1` e
`autoscaler.enabled=false`; `load_balancer.enabled=true` mantém NGINX estático.
O validador já rejeita proxy com autoscaling e sources em containers sem proxy
ou com autoscaling. Autoscaling existe no ramo legado, com thresholds/cooldown
em `AutoscalerConfig` e [autoscaler_logic.py](../simulator/autoscaler_logic.py),
mas atualização dinâmica de upstream não existe no fluxo proposto.

`server.process_pool_workers=2` controla processos da aplicação, não reserva duas
CPUs. [docker_manager.py](../simulator/docker_manager.py), `HttpProxy.start` e
`SourceManager.start` não explicitam quota/cpuset/shares: **uma instância fixa não
é capacidade física garantida**. Preservar pool e política de recursos por bloco;
registrar limites efetivos/imagens/versões. Se forem adicionados limites no futuro,
isso define outro ambiente a caracterizar e calibrar.

Topologia fixa de uma vítima foi validada nas Etapas3–6 e empregada na coleta
Stage14/15. Isso não valida novas intensidades nem prova saturação/EDoS.

### 1.3 Ajuste, calibração e quatro métodos

A campanha anterior separa DEVELOPMENT, seis BASELINE benignos de 240s,
12 CALIBRATION benignos de 360s e TEST de 16 seeds × B/C/P de 144s. Ajuste do
baseline seleciona `[48,240)`; calibração `[48,360)`; observação/scoring TEST
`[0,144)` e avaliação primária `[48,144)`. Esses números são históricos.
Estado causal começa em zero, sem reset na fronteira de avaliação. O novo desenho
não herda automaticamente esses horizontes ou a mesma população benigna.

| Método/código em `analysis/detection/detectors/` | Score implementado | Limiar primário histórico |
|---|---|---|
| `zscore.py` | `(x−mu_B)/sigma_B`; momentos benignos, desvio amostral ddof=1; sigma zero recusa fit | Quantil empírico upper-tail dos scores benignos CALIBRATION |
| `cov.py` | `s(H)/mean(H)`, ddof=1; H inclui observação atual; L=6 principal, 3/12 sensibilidade; sem fit estático | Mesmo procedimento, por configuração/feature; não é corte teórico universal de CoV |
| `ewma.py` | `E_t=.2 z_t+.8 E_(t−1)`, inicial zero, assinado | Mesmo procedimento, usando normalização Z-score congelada |
| `cusum.py` | `C_t=max(0,C_(t−1)+z_t−.5)`, inicial zero | Mesmo procedimento, usando normalização Z-score congelada |

Para cada método/feature/configuração, [empirical.py](../analysis/detection/empirical.py)
ordena os N scores disponíveis de CALIBRATION, com peso igual por score:
`j=ceil((N−1)(1−alpha))`, índice zero; `h=s[j]`, sem interpolação. Alpha primário
histórico é `.01` (sensibilidades `.005/.02`). O mesmo h vale para os runs daquela
configuração, não um h novo por ataque. Alarme estrito `score>h`; igualdade é
negativa. Ausentes são excluídos e contados; alpha não garante FPR de cada run
nem probabilidade de falso alarme por execução. Não se usa automaticamente h=3.

Z-score mantém baseline diante de null; CoV limpa histórico e exige L válidos
consecutivos, média zero indisponível. EWMA/CUSUM zeram estado em null. Todos
preservam indisponibilidade, sem imputação. As cinco features primárias históricas
são `ingress_packet_count`, `ingress_tcp_payload_length_sum_bytes`,
`request_starts`, `mean_duration_ms` e `mean_cpu_percent`, separadamente: 20
configurações, sem fusão de scores. Scoring, calibração e decisão são contratos
separados em [pipeline.py](../analysis/detection/pipeline.py).

Fórmulas, guards, causalidade e missing têm testes; Stage14/15 comprova aplicação
congelada desse desenho. Isso não valida transferência de limiares para novo
endpoint benigno, carga, instrumentação ou política CUSUM.

### 1.4 Observações e limitações

| Fonte/schema real | Disponível | Limite de interpretação |
|---|---|---|
| `request_log.csv`, `experiments/dataset_schema.py:requests` | `elapsed_seconds`, `end_elapsed_seconds`, `duration_ms`, `traffic_class`, `http_status`, `outcome`, `error_type`, IDs e URL | Início no cliente antes de `session.get`, depois da fila; não é admissão nem chegada à vítima |
| `simulation_metrics.csv` | `average_cpu_percent`, `mem_usage`, `num_instances`, nomes, `avg_rtt_ms`, relógio/run e CPU host existente | Vítima: média de amostras/cache; frescor/intervalos brutos não persistidos; RTT agregado não mede serviço benigno isolado |
| Stage10 `timeseries/service.csv` | `request_starts`, `request_completions`, `request_failures`, `http_failures`, `transport_failures`, `client_failures`, `mean_duration_ms` | Mistura classes e resultados; mean_duration inclui falhas concluídas; não substitui estratificação benigna |
| Stage10 `timeseries/infrastructure.csv` | `mean_cpu_percent`, `mean_memory_mib` | Média dos ticks suportados, não integração temporal de CPU |
| `proxy_artifacts/monitor_samples.jsonl`, schema_version=1 | CPU proxy, memória bruta, contadores/taxas por interface, active/reading/writing/waiting, accepted/handled/requests totais; tempos próprios, erros e qualidade | Primeira leitura/deltas inválidos null; waiting não é fila; consultas de monitoramento interferem nos totais |
| `proxy_access.log` e `routing_evidence.jsonl` | Status/upstream, tempos operacionais, request IDs, respostas identificáveis | Não medir latência específica proxy→vítima nesta campanha; diferença de tempos não isola custo do proxy |

Requisições **iniciadas continuam medidas no cliente**. `request_completions`
conta términos conhecidos de todos os outcomes. Falhas concluídas distinguem
`http_error` (>=400), `transport_error`, `client_error`; `incomplete` não recebe
término/duração fabricados. Para sucesso científico usar explicitamente 2xx;
`outcome=response` inclui outros status abaixo de400. Starts por instante inicial,
conclusões/s por instante final; duração por coorte de início, com travessias de
fase explícitas. Reconciliar contagens após drenagem, não subtrair taxas de coortes
diferentes como se fossem a mesma população.

No modo containers há journals locais e agregação em
[source_aggregate.py](../simulator/source_aggregate.py), além de status/controle
por origem; [ground_truth.md](ground_truth.md) define o CSV final. No fluxo host,
a linha é escrita na conclusão e finalização marca abertas como incompletas;
queda abrupta pode perder tentativas ainda não persistidas. Não prometer resistência
a crash sem conferir o modo. Resumos legados de `total_requests/real_rps` contam
respostas e não são fonte principal de starts ou sucessos.

Eventos usam `actual_start_seconds` (primeira tentativa), `actual_end_seconds`
(certificação de fim de emissão) e `drained_end_seconds` (conclusões). Fim nominal,
fim de emissão e drenagem podem divergir; nenhum equivale por definição à
recuperação do serviço.

**CPU por CPU lógica de cada contêiner:** não há série publicada desse tipo nos
schemas atuais. `percpu_usage` aparece como fallback para obter o número de CPUs
na fórmula de CPU total Docker em `stats_collector.py` e `proxy_monitor.py`; não
é exportação de consumo por núcleo. A auditoria de CPU documenta que o array pode
nem existir em cgroup v2. 100% Docker corresponde a um núcleo lógico equivalente,
não identifica qual CPU executou. A indisponibilidade dessa decomposição não
bloqueia o protocolo: usar CPU total por contêiner disponível, declarar suporte e
limitações, sem acrescentar monitoramento do host físico.

Monitoramento novo do proxy tem smokes técnicos completed e testes documentados
em [proxy_observability.md](proxy_observability.md); não consta dos 48 TEST
congelados. Estratificação de serviço/recursos e IC da nova campanha são trabalho
futuro. Os problemas de frescor da CPU das vítimas permanecem documentados; não
transformar repetição de valor em evidência automática de cache stale.

## 2. Matriz inicial: desenvolvimento antes de avaliação

Notação: `N_B` clientes, taxa por cliente `b`, oferta benigna `B=N_B b`;
`N_A` atacantes, taxa por atacante `a`, oferta ofensiva `A=N_A a`.
Recomendação inicial: `N_B=4`, por continuidade do arranjo validado, sem afirmar
que represente uma população real. Clientes usam `/medium`; ataque de referência
também `/medium`. Assimetria usa `/expensive`. `/light` participa da
caracterização de custo, sem multiplicar todos os blocos finais por três endpoints.

Em todos os blocos: uma vítima, proxy estático, sources em containers, contínuo,
autoscaling off, pool da vítima, timeout, orçamentos de envio, HTTP/keep-alive,
versão da instrumentação e ambiente constantes. Registrar desvios e ordem.

### 2.1 Ensaios exploratórios de capacidade — DEVELOPMENT

| Ensaio/pergunta | Clientes e atacantes | Fator e constantes | Controle e métricas |
|---|---|---|---|
| D1: onde a carga legítima deixa de ser atendida com qualidade? | `N_B=4`, sem ataque, `/medium`; aumentar b por patamares | Só B; manter topologia/custo/pools | Menor patamar como referência; starts/s, 2xx/s, p50/p95/média de duração 2xx, erros/incompletas, CPU/memória vítima/proxy, conexões e qualidade de coleta |
| D2: qual o custo relativo das operações no arranjo? | Mesmos clientes e B baixo de D1; sem ataque, comparar `/light`, `/medium`, `/expensive` | Só endpoint; B suficientemente baixo para evitar comparar apenas filas saturadas | `/medium` como referência; métricas D1 e trabalho fixo confirmado |
| D3: o gerador e o serviço suportam a faixa ofensiva planejada? | Regime benigno nominal de D1; um atacante; aumentar A em `/medium`; poucos probes `/expensive` | Taxa e, em sub-bloco separado, endpoint | Benigno correspondente; D1 mais starts por classe/origem, backlog observável/drenagem e divergência oferta→starts→conclusões |

Não executar varredura ilimitada nem selecionar por recall/F1 dos detectores.
Definir antes dos ensaios critérios de serviço (limite aceitável de p95, erros,
aderência da taxa iniciada à oferta e estabilidade), teto seguro da exploração e
regra de parada. Seus valores dependem do objetivo de serviço ainda não definido.
CPU alta sozinha não define capacidade. Com base nos ensaios escolher B baixo,
nominal e alto ainda legítimo, e duas intensidades ofensivas A1<A2 que cubram
impactos distintos sem perder a capacidade de observar o gerador.

Warmup, PRE útil, intervalo ativo e POST dependem de estabilização, suporte de
amostragem, memória dos métodos e drenagem observados em DEVELOPMENT. Fixar esses
tempos antes de CALIBRATION/TEST; não copiar automaticamente 48/36/60s. Para
comparar taxas manter a mesma duração ativa e acompanhamento; o POST deve permitir
estudar persistência, sem assegurar recuperação não observada.

### 2.2 Experimentos finais propostos

| Cenário/pergunta | Clientes e atacantes | Variável alterada; condições mantidas | Controle benigno | Métricas necessárias |
|---|---|---|---|---|
| B-baixo/B-nominal/B-alto: como variam serviço e falsos alarmes no legítimo? | 4 clientes `/medium`, b de cada regime; `attack.enabled=false` | Apenas B; mesmos endpoints/infraestrutura/tempos | Cada cenário é seu controle; comparações entre regimes declaradas | FPR, positivos/tempo, disponibilidade; serviço benigno e recursos D1 |
| A1/A2: aumentar intensidade aumenta detecção e impacto? | B nominal fixo; `N_A=1`, `a=A1` ou `A2`, `/medium` | Só taxa ofensiva; mesma janela ativa e custo | B-nominal da mesma seed e intervalo de referência | Métricas de detecção completas, starts/conclusões/falhas por classe, serviço benigno, CPU/memória vítima/proxy e conexões |
| N2: distribuir a mesma taxa ofensiva muda o comportamento? | B nominal; `N_A=2`, `a=A1/2`, `/medium` | Só número de origens, **A=A1 constante**; orçamento agregado de envio fixo | B-nominal; contraste principal com A1 | Métricas A1 mais taxa por origem e repartição de workers; documentar filas/sessões como parte do efeito |
| E: custo ofensivo maior causa impacto com a mesma taxa? | B nominal em `/medium`; `N_A=1`, `a=A1`, ataque `/expensive` | Só endpoint ofensivo; A, N, benigno e tempos fixos | B-nominal; contraste principal com A1 `/medium` | Métricas A1, duração/erros por endpoint e divergência entre oferta e serviço |

São **sete condições por seed**: três benignas e quatro com ataque; A1 é âncora
reutilizada pelos contrastes. Não cruzar todas as taxas com todas as quantidades,
endpoints e regimes benignos. Se dois patamares de DEVELOPMENT não separarem
regimes úteis, reduzir a matriz antes do congelamento. Mais atacantes a taxa por
origem constante aumentariam também A: essa pergunta composta fica fora do bloco
N2, podendo receber protocolo posterior.

Reutilizar B-nominal como controle por seed é permitido, mas induz dependência
entre contrastes: preservar esse bloco completo na inferência. Para B-baixo e
B-alto o regime é conhecido previamente por desenho; não escolher em TEST qual
calibração usar pela taxa observada durante ataque.

## 3. Calibração, avaliação e incerteza

### 3.1 Populações e congelamento

Adotar quatro conjuntos separados: DEVELOPMENT (capacidade/decisões), BASELINE
(ajuste benigno), CALIBRATION (limiares benignos) e TEST (avaliação final). Seeds,
runs e diretórios independentes entre conjuntos. Mesma seed entre condições TEST
é pareamento planejado, não reutilização de BASELINE/CALIBRATION.

Recomendação para a matriz enxuta: **calibração por regime legítimo declarado**.
B-baixo, B-nominal e B-alto recebem baseline/calibração representativos de suas
respectivas cargas, com a mesma operação legítima e instrumentação. Os quatro
ataques usam sem alteração o modelo/limiares B-nominal, inclusive E: mudar apenas
o endpoint do atacante não muda o regime legítimo. Não calibrar no ataque caro.
Uma calibração única para toda uma faixa legítima é alternativa válida se essa
mistura representar a operação pretendida, com pesos/exposição definidos antes;
nesse caso avaliar FPR também por estrato. Não misturar silenciosamente as duas
perguntas nem afirmar robustez a mudança de regime a partir de modelos por regime.

Preservar do protocolo existente: inputs observáveis sem rótulos, separação de
roles/hashes, modelo benigno externo para Z/EWMA/CUSUM, CoV local sem fitting,
calibração por configuração, seleção temporal posterior ao processamento causal,
null explícito e TEST sem realimentação. Considerar Δ=1s, L=6, lambda=.2, k=.5 e
alpha=.01 pontos de partida por continuidade, a confirmar em DEVELOPMENT e
congelar antes da nova calibração; não escolhas ótimas comprovadas.

Não transferir automaticamente os thresholds congelados. A campanha antiga é
evidência de desenvolvimento para a formulação futura, jamais novo TEST cego.
Nenhum resultado TEST, antigo ou novo, pode recalibrar/selecionar a nova política
durante sua avaliação final. Alterações motivadas após TEST exigem outra versão
e novo conjunto independente. Registrar manifesto próprio, sem editar Stage14/15.

### 3.2 Métricas e unidade experimental

Manter matriz binária por janelas puras: TP/FP/TN/FN, recall, precisão, F1 e FPR;
boundary e unavailable contados separadamente, denominador zero null. Mostrar
suporte por método/feature/run, exposição benigna e positivos por tempo (definir
se por exposição total ou disponível; reportar ambas quando divergem). Não fundir
janelas em episódios sem uma nova regra prévia.

Manter evento detectado por decisão positiva disponível cuja janela tenha
interseção positiva com o evento efetivo; atraso = primeira disponibilidade
elegível − actual_start. A política histórica não exige decisão antes de
actual_end: conservar explicitamente essa definição ou pré-especificar uma
métrica adicional com prazo, sem substituição posterior. Miss tem atraso null.
Apresentar **proporção de eventos detectados junto da distribuição do atraso dos
detectados**, número de misses e suporte. Um atraso menor em poucos detectados
não significa detector superior. Alarmes POST ficam separados de atraso e de
recuperação do serviço.

Unidade experimental = execução. Para cada condição repetir em seeds previamente
listadas; todos os métodos pontuam os mesmos runs. Comparação entre métodos é
pareada no run; entre ataque e controle, na seed/bloco, sem supor trajetória
idêntica só porque a seed coincide. Sorteio por componente/índice usa SHA256 e
`random.Random`; clocks/rede/scheduler não são determinísticos. N2 altera streams
e filas, não reproduz exatamente o processo agregado de A1.

Usar execução sequencial, ordem balanceada/randomizada dentro dos blocos e seed
administrativa de ordem registrada, sem concorrência de runs. Arquivar tentativas
e falhas, sem excluir por mau desempenho ou repetir até obter resultado favorável.
[stage14_campaign.py](../experiments/stage14_campaign.py) já oferece checkpoint,
lock, recibos e retomada, com STOP e sem retry automático; sua autoridade/matriz
são específicas. Reutilizar o padrão exige adaptação versionada, não simplesmente
apontar o runner antigo para qualquer JSON novo.

### 3.3 Repetições e intervalos de confiança propostos

Não fixar n apenas porque a campanha antiga usou16 seeds. Planejar n pela precisão
desejada dos contrastes primários, variabilidade entre runs de DEVELOPMENT e
orçamento. Fixar n, seeds, nível de confiança (recomendação95%), contrastes e
tratamento de falhas antes de TEST, sem parada por significância observada.
Para referência de orçamento, 16 réplicas dariam112 runs TEST nesta matriz, mas
não é dimensionamento aprovado nem garantia de precisão.

| Estimando | Estratégia a decidir antes de TEST |
|---|---|
| Média entre execuções de FPR/recall/F1, vazão e p95 por run | IC com reamostragem de execuções/blocos completos se n/distribuição sustentarem; alternativa t para médias/diferenças aproximadamente regulares após diagnóstico em DEVELOPMENT. Mostrar pontos, mediana/IQR, média/SD e n definido |
| Diferença entre métodos ou ataque−controle | Reamostrar o mesmo bloco pareado, nunca métodos/seeds separadamente; t pareado apenas se adequado às diferenças. Contrastes primários poucos e pré-especificados; se houver família confirmatória, definir correção de multiplicidade |
| Proporção de eventos detectados, um evento por run independente | Wilson ou exato binomial como candidatos para IC marginal; conferir independência entre runs. Não aplicar ao total de janelas autocorrelacionadas. Comparação entre métodos exige informação dos pares discordantes, não ICs independentes subtraídos |
| Atraso dos detectados | IC condicional por runs, com número detectado explícito e cautela quando pequeno. Comparação de atrasos em pares detectados por ambos é selecionada e complementar. Análise de tempo até detecção com censura só com prazo/regra de elegibilidade e pressupostos próprios previamente definidos |
| Quantis de duração e séries internas | Primeiro resumir por execução; IC entre execuções não é IC do quantil de todas as requisições agrupadas. Se necessária incerteza intrarrun, blocos temporais/hierarquia com tamanho de bloco justificado pela dependência em DEVELOPMENT; não bootstrap iid de requisições/janelas |

O protocolo atual tem resumos descritivos, não implementação geral desses ICs.
Não calcular IC binomial ingênuo usando cada segundo como réplica nem fazer de
um bootstrap universal a resposta para toda métrica. Runs com métrica indefinida
continuam visíveis; IC condicionado ao subconjunto definido deve ser identificado.

## 4. Preparação da política CUSUM — sem implementação

### 4.1 Alteração de contrato necessária

Hoje `CUSUM.update` calcula residual e **atribui sempre**
`state.value=max(0,state.value+z−K)`; depois retorna esse estado como score.
`StandardizedUpperTail.residual` valida contiguidade e zera estado em missing.
Não há acesso a h no detector. `StrictUpperTail` recebe o score depois, sem
capacidade de desfazer a atualização. Portanto mudar apenas a comparação da
política não implementa o comportamento pedido.

Proposta de transição causal, para h fixo previamente persistido:

```text
estado numérico inicial S = 0
para cada observação válida, em ordem:
    z = residual com mu_B e sigma_B congelados
    candidato = max(0, S + z - k)
    alarme = candidato > h
    se candidato <= h:
        S = candidato
    senão:
        preservar S anterior
    publicar candidato como score e alarme como decisão
```

O score publicado deve ser o **candidato**, mesmo no descarte; publicar só S
esconderia alarmes quando S<=h. Próxima observação parte do S preservado, sem
reprocessar observações passadas. Ao voltar à região de aceitação, atualização
retoma imediatamente. Um descarte não é reset para zero, não congela o relógio
nem elimina o registro da observação. Avançar metadados de índice/bounds em toda
observação, inclusive descarte/missing, mantendo validação causal.

Criar componente/artefato versionado com baseline, h, regra de aceitação, estado
inicial, missing e direção explícitos. A separação atual score→calibração→decisão
precisará de extensão para essa política dependente de h; recomendar transição
integrada versionada, sem introduzir acesso a GT no detector ou uma reversão
oculta no evaluator. V1 deve continuar reproduzível e intocada.

### 4.2 Ambiguidades e recomendações

| Decisão | Recomendação e consequência |
|---|---|
| Igualdade a h | Alarme só em `candidato>h`; aceitar igualdade, coerente com o contrato estrito atual |
| Direção | Manter unilateral superior, z assinado e piso zero; lower-tail/bilateral exigem outra especificação |
| Missing | Manter por continuidade score/decisão indisponíveis e reset numérico para zero, como V1; confirmar explicitamente, pois “preservar estado” em missing seria outra política. Nunca tratar null como observação aceitável ou alarme |
| Limiar negativo/ausente/incompatível | Recusar artefato inválido; h do CUSUM superior deve ser finito e não negativo. Validar feature, baseline, precisão e versão |
| Estado e alarme | Guardar candidato e indicador de atualização aceita em diagnósticos observáveis; S anterior/posterior auditáveis. Nenhum motivo usa rótulo |
| Horário do evento | Não consultar início/fim real ou nominal para congelar, reiniciar ou retomar; somente observação, estado anterior e parâmetros congelados |
| Persistência | Pode reduzir acumulação durante alarmes, mas não garante recuperação rápida: S preservado perto de h pode continuar gerando alarmes. Avaliar benignos e POST, não prometer correção de toda persistência |

**Calibração depende da política:** como a trajetória nova depende de h, não se
pode calibrar uma trajetória supostamente independente e afirmar que o quantil
mantém o mesmo significado após inserir o descarte. Recomenda-se primeiro, em
DEVELOPMENT sintético/benigno, verificar uma regra em duas partes: estimar h em
CALIBRATION-A usando CUSUM V1 sem descarte e aplicar esse h fixo à nova transição;
medir FPR da nova política em CALIBRATION-B benigna independente. Identificar h
como limiar de referência, sem garantia de alpha para a nova trajetória. Se o alvo
de FPR da política nova precisar ser ajustado, definir previamente busca/critério
em CALIBRATION-A e reservar B para verificação, com regra de insucesso explícita.
Não resolver iterativamente olhando TEST ou ataques avaliados. A opção final e
o custo dessa subdivisão permanecem pendentes; não reutilizar o freeze antigo
como calibração certificada da nova versão.

Testes futuros necessários: candidato abaixo/igual/acima, alarmes consecutivos
com S preservado, retomada, S inicial/h zero, decaimento natural, null/reset,
contiguidade, causalidade por prefixo e independência de labels/horários de ataque.
Comparar V1 e nova política nas mesmas observações novas, com limiares de origem
explicitada. Isso é comparação pareada entre versões, não reavaliação corretiva
do TEST congelado.

## 5. Decisões pendentes e próximo passo

| Pendente | Recomendação |
|---|---|
| Representação do legítimo e SLO | Começar com4 clientes `/medium`; definir critérios de serviço antes de capacidade, depois congelar três regimes se úteis |
| RPS, tempos, n e seeds | Derivar de DEVELOPMENT por capacidade/estabilização/precisão; não por desempenho no TEST; congelar antes da coleta científica |
| Calibração única ou por regime | Por regime declarado nesta matriz; manter B-nominal para todos os ataques, inclusive `/expensive` |
| Política CUSUM e calibração dependente de h | Aprovar a especificação da seção4 e investigar a separação A/B benigna antes de integração científica |
| Qualidade da CPU das vítimas | Declarar cache/frescor; se houver correção prospectiva, versionar e validar antes de BASELINE, sem alterar séries congeladas. CPU por núcleo não bloqueia |
| Métricas de serviço/IC | Implementar resumo por classe/coorte/fase e suporte; escolher IC por estimando, com contrates e multiplicidade pré-especificados |
| Repetições operacionais inválidas | Preservar tentativa e motivo técnico; política de substituição previamente definida, nunca guiada por score/impacto |

**Próximo passo concreto de implementação:** criar, em versão nova, um resumo
offline de serviço por execução/classe/fase a partir de `request_log.csv`, com
starts, términos, sucessos2xx, falhas, incompletas, travessias e p50/p95 suportados.
Validar com fixtures sintéticas de fronteira, timeout, missing e drenagem; preparar
o plano machine-readable de DEVELOPMENT com as chaves reais de `ExperimentConfig`
e campos ainda pendentes explicitados fora do JSON executável. Em seguida,
implementar a variante CUSUM e seus testes sintéticos conforme decisão da seção4,
antes de congelar código/ambiente para qualquer nova calibração. Nenhuma dessas
implementações nem a execução dos ensaios é realizada nesta tarefa.

Fora de escopo: autoscaling em execução, novas medições do host físico, medição
específica proxy→vítimas, UDP e modificação dos artefatos congelados. A proposta
não autoriza concluir dano econômico EDoS a partir apenas de CPU/latência.
