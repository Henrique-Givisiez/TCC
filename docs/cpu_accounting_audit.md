# CPU do simulador: auditoria e proposta para múltiplas vítimas

23/10/2026; checkout `0954e68270339597ec9f4326d3d569cf51954f38`. Foram lidos README,
contratos de configuração, proxy, sources, dataset, features e artefatos congelados.
Não há AGENTS.md na cadeia de diretórios. Esta entrega acrescenta documentação e
testes, sem alterar runtime, schemas, parâmetros, detectores ou resultados.
Não houve campanha, stress, Docker stats real, inspeção de containers em execução,
commit ou push. As referências antigas de autoscaler/defaults não foram tomadas
como descrição da campanha atual.

**Resposta principal:** a CPU atual é consumo na escala Docker (100%≈um núcleo
lógico), agregado como média das amostras disponíveis das vítimas, com fallback
para cache. Não é consumo total nem porcentagem de capacidade reservada. Para
múltiplas vítimas, propõe-se preservar essa série histórica e acrescentar medidas
individuais, total, média por vítima e desequilíbrio, com intervalos/suporte explícitos;
normalização por capacidade só quando um denominador verificável for definido.

## 1. Caminho completo da observação

```text
cgroup das vítimas / contadores de CPU do host
 → Engine GET /containers/{id}/stats
 → StatsCollector._run → _compute_metrics → _calc_cpu_percent
 → cache + histórico por ID
 → get_averages(window_seconds=monitoring.interval_seconds)
 → valor avg_cpu do orquestrador
 ├─ autoscaler legado, quando permitido/habilitado, antes do arredondamento
 └─ log_metrics_to_csv: average_cpu_percent arredondado a 2 casas
     → exportação byte a byte Stage8
     → Stage10: mean_cpu_percent por janela de timestamp do tick
     → Z-score / CoV / EWMA / CUSUM, univariados, offline
```

No fluxo `traffic_sources.execution=containers`, source_experiment.run passa
somente `victims` a collector.update_containers. No host, main_orchestrator passa
active_containers criados pelo docker_manager: também vítimas. Proxy, sources,
sniffers e demais processos não entram na lista. Não há descoberta de todos os
containers do daemon para compor essa média.

A CPU de cada vítima inclui os processos/threads no cgroup: servidor HTTP,
processos do pool e trabalho de sistema contabilizado a eles, não somente o kernel
CPU sintético. Processos externos como gerador/NGINX têm cgroups distintos, embora
compitam pelo mesmo host. Qualquer exec que rode dentro de uma vítima também
pertenceria a esse cgroup. Não se deve somar pai e filhos de uma hierarquia como
se fossem consumos independentes.

O helper docker_manager.get_container_stats usa CLI `docker stats` e outra leitura
para memória, mas **não está no caminho ativo da média**: só aparece no self-test
do próprio módulo. Não foi executado: não deve ser confundido com StatsCollector.

## 2. Fórmula, deltas e significado

Para a leitura j da vítima i, o código usa:

```text
U  = cpu_stats.cpu_usage.total_usage
U0 = precpu_stats.cpu_usage.total_usage
S  = cpu_stats.system_cpu_usage
S0 = precpu_stats.system_cpu_usage
n  = cpu_stats.online_cpus
     ou len(cpu_stats.cpu_usage.percpu_usage)
     ou 1, se ambos não fornecerem suporte

p_ij = 100 * (U−U0)/(S−S0) * n, se U−U0>0 e S−S0>0
p_ij = 0.0, caso contrário
```

U/U0 e S/S0 são tempos acumulados na interface Linux Docker, em ns. A API
normaliza as unidades: cgroup v1 cpuacct.usage é ns; cgroup v2 cpu.stat expõe
usage_usec em microssegundos, convertido pelo Engine. Não se multiplica o payload
Docker novamente por1000. Um cgroup contabiliza processos e descendentes.

Na implementação Engine 28.0.4, getSystemCPUUsage soma os sete primeiros campos
CPU de /proc/stat (user, nice, system, idle, iowait, irq, softirq), converte USER_HZ
em ns e conta as linhas cpuN para n. Não soma steal/guest/guest_nice nesse S.
Isso difere de host_stats do projeto, que soma todos os campos. A aproximação
ΔS≈n·Δt pressupõe estabilidade do suporte/contabilidade; steal relevante ou mudança
de CPUs pode prejudicar essa equivalência, sem tornar a quota um denominador válido.

O n é o número de CPUs lógicas online informado no payload, não uma quota do
container, número de vítimas ou tamanho do pool da aplicação. Quando online_cpus
falta/é zero, o código usa o array percpu; se também faltar, assume1. O último
fallback é uma convenção do simulador que pode perder a escala em payload sem
suporte: não é evidência de capacidade de uma CPU. Em cgroup v2, percpu pode não
existir; online_cpus é particularmente importante.

Quando ΔS≈n·Δt, p≈100·ΔU/Δt. Assim **100% corresponde aproximadamente a 1
CPU-segundo por segundo**, 240% a 2,4 núcleos lógicos equivalentes. Pode exceder 100%
sem erro; não há clipping em 100 ou 200. Núcleo equivalente é unidade de tempo
contabilizado, não núcleo físico dedicado, GHz, instruções ou trabalho útil igual
entre CPUs heterogêneas/SMT.

A fórmula segue a interface Linux do [Engine v1.48, ContainerStats](https://raw.githubusercontent.com/moby/moby/v28.0.4/docs/api/v1.48.yaml)
e o [Docker CLI 28.0.4, calculateCPUPercentUnix](https://raw.githubusercontent.com/docker/cli/v28.0.4/cli/command/container/stats_helpers.go).
A escolha/fallback de n e as condições dos deltas foram conferidas no checkout.
A conversão v1/v2 está em [Moby 28.0.4, stats_unix.go](https://raw.githubusercontent.com/moby/moby/v28.0.4/daemon/stats_unix.go).

### De onde vem o intervalo

As vítimas usam `container.stats(stream=False)`, **sem** one_shot. ΔU e ΔS vêm dos
dois frames fornecidos pelo Engine nessa resposta, não de duas chamadas anteriores
do StatsCollector. A API fornece read/preread; o coletor guarda somente read em
read_ts no cache e não usa esses timestamps na fórmula, nem os persiste no CSV.
A razão representa o intervalo dos contadores desses frames, não necessariamente
monitoring.interval_seconds nem stats_poll_interval_seconds.
No ramo host, o coletor é iniciado antes da criação do relógio GT e do setup do
proxy; a primeira janela consultada pode conter amostras recentes de setup. No
ramo sources, o coletor começa depois da âncora GT e do setup. Não existe campo
de fase por amostra de vítima que permita separar isso retrospectivamente no CSV.

No [Engine 28.0.4, ContainerStats](https://raw.githubusercontent.com/moby/moby/v28.0.4/daemon/stats.go),
stream=false e one-shot=false esperam dois ciclos: o primeiro preenche o estado
anterior e o segundo é retornado. Portanto **a primeira leitura do coletor pode
ter CPU válida**, não é obrigatoriamente zero. O SDK7.2.0 instalado delega a essa
API; sua implementação foi inspecionada sem abrir conexão Docker.

O coletor não exige read/preread válidos para aceitar os contadores. Se precpu
faltar, defaults numéricos são zero e pode resultar uma razão de acumulados desde
origens distintas, não um intervalo recente válido. Stats vazios retornam CPU 0 e
nome presente; erro de conversão em _compute_metrics retorna None e conserva cache.
Delta negativo, sistema sem avanço e CPU sem avanço também retornam0: inatividade
real e problema de suporte/reset não são distinguidos por esse valor.

### Tempo, cadência e erros

- `_run` coleta containers **sequencialmente**, na ordem da lista. Cada chamada
  pode aguardar o daemon; só depois da varredura espera poll_interval. O período
  de revisita é aproximadamente soma das durações das chamadas + espera + overhead,
  não simplesmente poll_interval. A defasagem entre vítimas cresce com esses custos.
- O timestamp do histórico é `time.monotonic()` **após** a chamada retornar.
  É instante de ingestão no coletor, não centro/início/fim exato de ΔU no daemon.
  O cache guarda read_ts, mas a agregação não verifica idade nem monotonicidade dele.
- Não há rejeição de read duplicado/stale; o mesmo dado pode ganhar dois timestamps
  de ingestão e peso duas vezes. Ler get_averages não consome amostras; ticks
  diferentes podem reutilizar o mesmo suporte ou o mesmo cache.
- A poda do histórico ocorre ao inserir dado novo daquele ID, pelo limite
  history_seconds. **O cache não expira**. Erros genéricos de get/stats são engolidos,
  sem contador/erro por fonte, preservando dado antigo. NotFound remove cache/histórico.
- A parada faz join de 2 s em thread daemon, sem exigir que tenha terminado. Não há
  timeout curto próprio por coleta nesse coletor; o cliente Docker tem seu timeout
  de transporte. Uma chamada lenta pode sobreviver à espera de stop. Não se mudou isso.
- Novo ID entra sem histórico. Reinício do mesmo ID não tem época/StartedAt/RestartCount
  no coletor: dados anteriores e posteriores podem coexistir na janela. As verificações
  de integridade da simulação checam ID e running nos instantes de inspeção; não
  devem ser confundidas com rastreamento contínuo de reinícios.

## 3. Agregação realmente implementada

Seja T o monotônico amostrado na chamada de get_averages(W), W em segundos e I(T)
a lista atual de IDs. Para cada vítima, selecione seus registros de histórico
`h.timestamp >= T−W`. A fronteira esquerda é **inclusiva**. Não há filtro explícito
`timestamp <= T`; em concorrência um registro inserido depois do sample de T e antes
da leitura sob lock também pode entrar. Não há recorte proporcional pelo intervalo
físico da amostra Docker; seleciona-se seu timestamp de ingestão.

Se não houver registro selecionado para i, mas houver cache, o código cria uma
entrada temporária `(T,ultimo_cpu,ultimo_mem,nome)` independentemente da idade real.
Se nem cache existir, aquela vítima não entra nos somatórios/denominador.

```text
L_i(T,W) = registros recentes de i, se houver;
           um registro com valor do cache, se não houver recente e houver cache;
           conjunto vazio, caso contrário.

m_i = quantidade de registros em L_i
A(T,W) = soma_i soma_j p_ij / soma_i m_i     [percentual Docker]
```

Se o denominador for zero: retorna CPU 0, memória 0, nomes vazios. Isso significa
falta total de suporte do coletor, não comprovação de CPU física zero. Os nomes
são a união dos nomes com algum registro/cache, não necessariamente todas as
vítimas existentes. Com uma vítima sem suporte e outra disponível, há nome presente
e a média parcial passa a ser tratada como suportada pelos consumidores.

**É média por amostra.** Há suavização sobre amostras recentes e mistura entre
vítimas, mas não integração temporal. O peso de i é m_i/Σm_i; só coincide com média
de médias por vítima se os m_i forem iguais. Com fallback, uma vítima pode ter
peso1 mesmo antiga, enquanto outra tem várias leituras recentes. Nenhum peso por
capacidade ou duração de ΔU é aplicado. history_seconds é retenção (30 s na campanha),
W é o intervalo de monitoramento pedido (1 s na campanha), não 30 s.

A variante get_averages(None), fora do caminho ativo auditado, usa uma leitura
cacheada por ID com peso igual, também sem validar idade. Não é a mesma definição
da variante com janela.

### Exemplos reproduzidos pelos testes

| Caso | Resultado atual | O que não significa |
|---|---|---|
| A=100%, B=200%, uma amostra alinhada de cada | Média150%; total seria300%=3 núcleos equivalentes |150% não é total nem utilização de uma capacidade de duas CPUs. |
| A tem20% e40%; B tem100% | (20+40+100)/3=**53,333…%** | Média igual por vítima seria ((20+40)/2+100)/2=**65%**. |
| Mesmo caso, se A 20 cobre 1 s, A 40 cobre 3s e B 100 cobre 4s | Média por tempo e vítima seria **67,5%**, não 53,33 ou 65 | Esses intervalos são dados hipotéticos do teste; o CSV histórico não os fornece. |
| T=10 s,W=2 s; A 40% em 9 s, B 160% somente em1 s, com cache | **100%**, nomes A e B; B tem 9 s de idade | Ter nomes não prova frescor/cobertura da janela. |
| Mesmo caso, B sem cache/histórico | **40%**, nome somente A | Não divide pelo número de vítimas configurado e não atribui zero à ausente. |
| Nenhuma vítima com suporte |0%, nomes[] | Stage10 exclui esse tick da média científica de recursos. |
| A 200%, depois entra B com leitura0% | Média200→100%, total continua200%=2 núcleos equivalentes | Queda da média não prova queda do consumo total ou ganho de capacidade. |

A entrada não é contada como zero antes da primeira amostra; inicialmente só muda
num_instances. Depois de uma leitura zero com nome, passa a entrar no denominador.
update_containers remove cache/histórico de quem sai; não preserva consumo passado
da vítima removida em uma janela anterior ainda em curso. Ao remover uma vítima,
a composição do indicador muda imediatamente.

## 4. CSV, feature, detectores e autoscaler

`main_orchestrator.log_metrics_to_csv` amostra epoch/elapsed ao escrever o tick,
**depois** das ações do tick. Grava round(avg_cpu,2) em average_cpu_percent e
num_instances/active_containers_names. Não persiste IDs individuais, read/preread,
duração de coleta, multiplicidade por vítima ou uso de fallback. Epoch=time.time;
elapsed usa a âncora monotônica do experimento. O histórico usa monotônico absoluto,
mas suas âncoras não são exportadas por amostra.

No ramo host, o terminal imprime o mesmo avg_cpu com 2 casas; o autoscaler recebe
o escalar **sem arredondamento**. No ramo sources, a escrita passa pelo mesmo
helper, sem essa impressão detalhada por tick. Stage8 copia os CSVs byte a byte,
sem corrigir a definição ou seu suporte.

Stage10 faz outro nível de média, usando a janela decimal **[kΔ,(k+1)Δ)** do
timestamp **do tick**, não do intervalo original Docker:

```text
J_k = ticks em W_k com active_containers_names não vazio
F_k = soma_{r em J_k} Decimal(average_cpu_percent_r) / |J_k|
      ou null, se J_k vazio
```

O valor é mean_cpu_percent, Decimal 50 dígitos/ROUND_HALF_EVEN, média de ticks
arredondados com pesos iguais, sem ponderação temporal. Tick sem nomes é preservado
nos diagnósticos mas excluído; um nome basta, mesmo parcial ou stale. Zero com
nome continua zero. Não é média das amostras Docker originais nem correção de cache.

**Não corresponde exatamente à média exibida em geral:** com um tick suportado
na janela coincide numericamente com o valor arredondado do CSV; com vários ticks
é média desses valores, podendo ter mais casas. O valor original não arredondado
não é recuperável. O teste 60,004 mostra autoscaler >60 positivo, mas CSV60,00,
cujo valor arredondado empataria e não dispararia a mesma regra.

Os detectores científicos consomem **essa feature**, explicitamente selecionada
na família infrastructure, não a CPU do proxy/host nem a CLI. Z-score normaliza
pelo baseline de F_k; CoV usa histórico local; EWMA/CUSUM usam resíduos padronizados.
Null tem tratamento declarado por detector, incluindo reset nos métodos stateful;
cache stale com valor/nome não é null e não permite reconstruir o que faltou.
Não se aplicou nenhum desses detectores a dados novos nesta auditoria.

Autoscaler.decide_scaling é consumidor operacional separado: compara média >limiar
up ou <limiar down, com min/max/cooldown. No fluxo host com scaling, avg_cpu/nomes
são anteriores à ação e num_instances do CSV pode ser posterior, sem recalcular
CPU no mesmo tick: composição e instante não são um snapshot único. Já as campanhas
congeladas e o modo containers/NGINX auditado têm autoscaling **desligado**. A
configuração proxy rejeita autoscaling ligado; não se propõe habilitar atualização
dinâmica de upstreams ou escalabilidade automática nesta etapa.

## 5. CPU do host e diferença da instrumentação do proxy

### Host

`host_stats` lê a linha agregada cpu de /proc/stat, em USER_HZ:

```text
T = soma de TODOS os campos numéricos da linha cpu
I = idle + iowait
H = 100 * (1 − delta(I)/delta(T)), se delta(T)>0
```

É uma porcentagem da escala agregada do host, normalmente 0–100, distinta da escala
Docker por container. CPU do host inclui vítimas, proxy, sources, Docker, captura,
outros processos e kernel, sem atribuir cada parcela. Inclui steal no numerador;
iowait é tratado como não ocupado nesta convenção. Não há clipping explícito.
Dados inválidos podem gerar valor fora do intervalo usual.

Primeira chamada no processo retorna0; erro de leitura ou delta total inválido
retorna0. Estado fica no módulo, não tem reset explícito em main por run; runs em
processos separados começam do zero, mas reuso do mesmo processo pode atravessar
um intervalo entre runs. Erro de leitura não atualiza a base, de modo que a leitura
válida seguinte pode cobrir o intervalo maior. Grava-se em host_cpu_percent, com2
casas. Não entra em mean_cpu_percent nem nos detectores científicos listados.

**Defeito aritmético condicional demonstrado:** /proc/stat guest e guest_nice já
estão contabilizados em user/nice no kernel. Somá-los novamente no T faz dupla
contagem quando seus deltas são não zero. Exemplo determinístico: user 100,
idle 100, guest 100 → código H=66,67%, enquanto tempo ocupado distinto/(user+idle)
seria 50%. Não há evidência suficiente de guest não zero no run congelado para
atribuir esse erro às suas observações. Não se alterou o cálculo histórico.

A base está em [kernel, /proc/stat §1.7](https://docs.kernel.org/filesystems/proc.html#miscellaneous-kernel-statistics-in-proc-stat)
e [kernel Linux 6.12, account_guest_time](https://raw.githubusercontent.com/torvalds/linux/v6.12/kernel/sched/cputime.c).
O schema congelado chama essa fonte de “psutil”; isso é um **defeito descritivo**:
o runtime usa /proc/stat e o contrato não foi reescrito nesta etapa.

### Proxy recente

ProxyMonitor tem artefatos próprios, cliente/timeouts próprios, run_id/container_id,
timestamps por fonte, duração/erro e nenhum vínculo com a média das vítimas.
Consulta stats com stream=False,one_shot=True; calcula deltas entre seus snapshots
bem-sucedidos anteriores. A primeira leitura tem CPU null; reset/delta inválido
permanece null com motivo. Rejeita read timestamp repetido; não oferece cache
antigo como dado novo. Usa intervalo observado, guarda docker_read e suporte.

É a mesma convenção de consumo Docker, **com aquisição/qualidade distintas**.
Não trocar silenciosamente o coletor das vítimas pelo do proxy ou presumir que
seus intervalos são iguais. O exec wget de status e o atendimento NGINX consomem
CPU no cgroup do proxy; a coleta posterior pode incluir esse trabalho no delta.
Esse custo é observado, não overhead causal isolado. Ver docs/proxy_observability.md.

## 6. Capacidade efetiva: o que foi e não foi configurado

Na criação de vítimas (`docker_manager.start_instance`), proxy (`HttpProxy.start`)
e sources (`SourceManager.start`), não se passam argumentos de CPU para:

| Controle | Constatação e consequência |
|---|---|
| cpu_quota / cpu_period | Não definidos pelo simulador; não existe orçamento de CPU explícito por vítima. Não se deduz quota a partir de pool 2. |
| nano_cpus / NanoCPUs | Não definidos; não há “duas CPUs” alocadas por esse mecanismo. |
| cpuset_cpus / cpuset_mems | Não definidos; não há particionamento/exclusividade explicitados no código. |
| cpu_shares / cpu.weight | Não definidos; valores/defaults herdados não são reserva. |
| cgroup_parent, RT quota/period | Não explicitados; ancestral/scheduler continuam capazes de restringir acesso. |
| Pool da aplicação | process_pool_workers=2: dois processos de trabalho persistentes; servidor HTTP/thread/IPC também consomem CPU. Não é limite rígido de200% do cgroup. |

[Docker, Resource constraints → CPU/CFS](https://docs.docker.com/engine/containers/resource_constraints/#cpu)
distingue teto por quota, CPUs permitidas e prioridade por shares; esta última não
reserva capacidade. [Kernel, CFS Bandwidth Control](https://docs.kernel.org/scheduler/sched-bwc.html)
especifica quota/period e throttling. [Kernel, cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html),
seções CPU Interface Files e Cpuset Interface Files, descreve cpu.max, cpu.weight,
restrições hierárquicas e cpuset.cpus.effective. Um teto não é mínimo garantido.

Mesmo sem flags locais, limites em cgroups ancestrais, cpuset efetivo, afinidade,
CPU online, contenção, SMT e frequência podem importar. CPUs “visíveis” por API
ou os.cpu_count não provam quota nem throughput disponível. O registro do ambiente
congelado aponta cgroup v2, Docker 28.0.4 e 12 CPUs lógicas online 0–11 no host; não
certifica 12 CPUs reservadas para cada container, nem mesmo disponibilidade uniforme.

Não foi arquivado, na evidência selecionada, um snapshot completo de HostConfig
CPU + cpu.max/ancestrais + cpuset efetivo/afinidade por vítima. O inventário backend
guarda ID/nome/IP/imagem/portas, não esses limites. **Não é possível declarar uma
capacidade garantida por vítima.** Não se inventou denominador12,2 ou12/N para
normalizar a CPU. Várias vítimas, proxy e sources compartilham o mesmo host:
somar capacidades aparentes de containers não adiciona capacidade física.

## 7. Evidência congelada conferida, com alcance limitado

Cadeia: 15A scoring manifest → TEST inventory e four-method freeze → entry 20/C,
artefatos raw/Stage10 e environment_lock. Foram conferidos SHA256/tamanhos de
**58 arquivos** e novamente seus hashes ao terminar. O JSON de auditoria registra
toda a identidade: `experiment_results/cpu-accounting-audit-20261023/evidence.json`.

- 15A manifest: `089a25681dd13810a94a92def805aa9a7e314955ebdcca671d625d959ae3a9d5`.
- Inventário: `10ab05b24e9896d41e944192909f79b366e8cbbe7e08eb24f695b5d2ad1c2b47`.
- Freeze dos quatro métodos: `898e79394ac48a86a734100d324d0b6b966412166a0eac105dbdeccb2bd236f5`.
- Todas as 48 configurações B/C/P TEST têm **uma vítima** e autoscaling desligado.
  Monitoramento/poll 1 s e history 30 s; pool 2; infraestrutura min=initial=max=1.
  Defaults antigos interval 5s, max 4 e autoscaling true não descrevem essa campanha.
- Exemplo de seed já definida 171864802, C, run_id `667624953df540e9aa3f3258d96960dd`:
  144 ticks,142 com nomes e 2 sem nomes; CPU suportada 5,50–44,46%. Gaps dos ticks
  0,956029–1,010409s, que **não são intervalos Docker** nem provam cadência do coletor.
- Stage10 possui 145 janelas,3 sem CPU; há 144 observações no score primário CUSUM/CPU.
  Recalculou-se somente a média aritmética diagnóstica dos ticks armazenados:
  coincidência exata com as features, inclusive null. As 144 observações armazenadas
  no score coincidem com a feature numérica; não se recalculou score/decisão.
- StatsCollector, host_stats, docker_manager e extract_features atuais coincidem
  com seus hashes host na proveniência desse run. Isso não certifica todos os
  limites herdados nem reconstrói medições Docker que não foram persistidas.

Não se conclui empiricamente a qualidade da agregação com múltiplas vítimas a
partir desses runs de uma vítima. Os exemplos multivítima são testes sintéticos.
Valores CSV repetidos podem vir de cache **ou** arredondamento/igualdade real;
sem timestamps brutos não se pode classificá-los retroativamente como stale.

## 8. Definições a separar em experimentos multivítima

Para um intervalo comum J de duração Δt, com suporte completo, seja ΔU_i o tempo
CPU consumido pela vítima i, em CPU-segundos, e `r_i=ΔU_i/Δt`. N é o conjunto
explicado de vítimas (incluindo política de entrada/saída); c_i é uma capacidade
explicitamente definida, em equivalentes de núcleo. Nenhuma c_i foi inferida para
os runs históricos. As fórmulas abaixo são propostas, não features novas publicadas.

| Medida | Pergunta respondida | Fórmula / unidade | Vantagem e limite |
|---|---|---|---|
| Individual | Quanto cada vítima consome? | r_i, CPU-s/s = núcleo lógico equivalente; p_i=100r_i na escala Docker | Expõe vítima quente/ociosa; exige intervalos comparáveis e preserva identidade. Não é utilização de quota. |
| Total de vítimas | Quanto processamento agregado as vítimas consomem? | R=Σr_i, núcleos equivalentes; energia de CPU em J:ΣΔU_i, CPU-s | Não cai só por mudar denominador N; não mede host inteiro, potência elétrica ou trabalho útil. Não somar intervalos incompatíveis ou cgroups sobrepostos. |
| Média por vítima | Quanto consome uma réplica típica? | r_bar=Σr_i/N, núcleos equivalentes/vítima; 100r_bar, %Docker médio | Útil com conjunto/suporte declarados; esconde desequilíbrio e cai ao adicionar réplica ociosa. Não é total. |
| Utilização de capacidade definida | Quanto do orçamento explicitado é consumido? | u_i=100r_i/c_i; U=100Σr_i/Σc_i, % do orçamento agregado, se capacidades forem aditivas e coerentes | Permite heterogeneidade; quota é teto, não reserva. Pai compartilhado pode impedir aditividade. Não usar sem denominador verificado. |
| Desequilíbrio | A demanda está distribuída? | max(r_i)−min(r_i), núcleos; ou CV_pop=sqrt(Σ(r_i−r_bar)²/N)/r_bar, adimensional | Revela hotspots que a média oculta. CV indefinido com média0; para capacidades heterogêneas comparar u_i ou distância ao alvo, não só consumo bruto. Não é o detector CoV temporal existente. |
| Proxy separado | O intermediário é gargalo? | r_proxy, mesmas unidades, mais status/erros/tempos operacionais | Mantém separação do serviço; CPU baixa não exclui limite de conexões/filas. Não soma à média das vítimas. |
| Host separado | Há contenção global? | H observado, % agregado host, com convenção explicitada | Inclui carga externa; CPU alta não atribui causa a vítima/proxy. Complementar, sem convertê-lo automaticamente em soma dos containers. |

### Pesos e alinhamento

Se um futuro desenho definir quota q em microssegundos por período P, q/P é um
teto médio de núcleos equivalentes, sujeito a cpuset e limites ancestrais; não é
reserva nem capacidade mínima garantida. Uma normalização deve dizer explicitamente
se seu c_i representa esse teto/orçamento ou outro recurso alocado verificado.

- Média simples de percentuais Docker alinhados é adequada para **consumo médio
  por vítima**: a unidade100% é a mesma, sem supor capacidades iguais. Para chamar
  isso de **utilização média de capacidade**, capacidades iguais e denominador
  definido são necessários.
- Para capacidades desiguais, utilização agregada é média de u_i com pesos c_i.
  Exemplo: c_A=1,r_A=1; c_B=3,r_B=1,5. Utilizações100% e50%: média simples75%,
  mas agregada(1+1,5)/(1+3)=**62,5%**. As capacidades são hipotéticas explícitas,
  não garantias dos containers atuais. O percentual Docker médio seria125%.
- Temporalmente, usar blocos não sobrepostos: para amostras com intervalos
  Δt_ij conhecidos, r_bar_i=Σ(r_ij·Δt_ij)/ΣΔt_ij. Peso igual por amostra só é
  equivalente quando durações/coberturas são iguais e sem duplicatas.
- Para total em J, preferir contadores nos limites comuns. Se intervalos forem
  diferentes, declarar interseção/cobertura e lacunas. Rateio proporcional de um
  intervalo que cruza fronteira pressupõe consumo uniforme nele: não é recuperação
  exata do contador interno. Não tratar uma leitura cobrindo a lacuna como várias
  observações e não integrar intervalos sobrepostos duas vezes.
- Com entrada/saída, separar total CPU-s e tempo-vítima observado. Uma média global
  ΣΔU_i / Σtempo_presente_i responde “consumo por vítima-tempo”, não média espacial
  instantânea. Sem suporte suficiente, reportar parcial/ausente, não completar com
  zeros ou multiplicar a média parcial pelo N configurado.

**Exemplo de escalabilidade:** uma vítima consome 200% = 2 núcleos equivalentes.
Adicionar outra com 0% produz média 100% e total200% inalterado. Mesmo se a carga
se distribuir 100%/100%, média 100% e total200% continuam. Um limiar de média pode
achar que há folga e propor scale-down sem que a demanda total tenha diminuído.
No mesmo host, N maior também aumenta paralelismo/overhead e disputa; não equivale
a adquirir outro servidor físico. Interpretar escala exige consumo total,
capacidade, distribuição e qualidade de serviço conjuntamente.

## 9. Problemas: defeito, limitação ou escolha

| Achado | Classificação | Proposta futura; nada alterado agora |
|---|---|---|
| Fórmula Docker e valores>100 | Comportamento correto para consumo de CPU | Manter essa unidade; explicar100%=um núcleo lógico, não normalizar pelo pool 2. |
| Média por amostra com m_i desigual | Escolha de projeto/limitação frente à pergunta “réplica típica” | Acrescentar média individual alinhada e total em contrato separado; não renomear a atual como média igual por vítima. |
| Fallback sem idade/erro exposto | Escolha histórica com limitação grave de frescor | Qualidade/idade/intervalo por fonte e ausência explícita em artefato prospectivo; não apresentar cache como leitura nova. |
| Payload vazio/reset vira zero com nome | Defeito de representação de suporte, demonstrado sinteticamente; impacto histórico não quantificável | Distinguir zero válido de indisponível/reset e segmentar épocas de execução; não alterar CSVs antigos. |
| Sem raw intervals/read validation | Limitação de identificação temporal, duplicatas e médias | Persistir contadores/read/preread, ingestão, identidade e duração antes de propor agregação por tempo. |
| Reuso de dados em vários ticks | Consequência do cache/janelas; pode criar autocorrelação aparente | Explicitar origem por amostra, frescor/cobertura; não deduplicar valores iguais por heurística em dados antigos. |
| Reinício mesmo ID sem época | Limitação de integridade da coleta | Validar/registrar StartedAt/restart generation futuramente, preservando checks atuais. Não alegar reinício no run sem evidência. |
| Média pré-scaling e contagem pós-scaling | Limitação temporal de snapshot do ramo legado | Registrar conjuntos antes/depois e intervalos, em nova definição se scaling for estudado. Campanha atual não escala. |
| Host soma guest/guest_nice de novo | Defeito aritmético condicional confirmado | Corrigir apenas prospectivamente e versionar a série host; sem alegar alteração dos scores congelados de CPU das vítimas. |
| Schema descreve psutil, runtime /proc/stat | Defeito documental confirmado | Esclarecido neste relatório; correção de schema/contrato somente em versão nova. |
| Sem capacidade garantida | Limitação do arranjo compartilhado, não falha da fórmula | Medir/registrar tetos efetivos e ancestrais; não inventar utilização normalizada ou reserva. |

## 10. Proposta mínima para múltiplas vítimas e stress futuro

1. **Preservar V1.** average_cpu_percent/mean_cpu_percent continuam com o significado
   histórico. Criar proposta versionada de observações individuais/qualidade e
   derivados separados, sem inserir dados novos nos detectores existentes.
2. **Topologia fixa inicialmente.** Para cada N escolhido previamente, vítimas
   fixas, proxy estático e autoscaling off. O proxy já gera upstream para N, mas
   essa possibilidade de código não substitui validação técnica multivítima.
   Novas políticas dinâmicas de upstream/autoscaler são trabalho separado.
3. **Declarar orçamento.** Diferenciar dois desenhos: aumentar réplicas no mesmo
   orçamento total ou aumentar recursos realmente disponíveis por N. Se adotar
   quota/cpuset, arquivar HostConfig, cpu.max/ancestrais, cpuset efetivo, CPUs online,
   afinidade e throttling. Quota limita; shares não reservam. Separar recursos para
   proxy/fontes/OS quando o desenho exigir isolamento, sem prometer garantia só por
   flags Docker. Não somar tetos de filhos que disputam o mesmo teto do pai.
4. **Medidas mínimas:** r_i e suporte; Σr_i/CPU-s total; média por vítima; min/max
   ou dispersão entre vítimas. u_i/U só com c_i explícito. Manter proxy e host em
   séries distintas, e observar pressão/throttling quando disponíveis. Avaliar
   geradores também: atraso/limite do source pode impedir atingir a oferta.
5. **Plano dos stresses futuros, sem execução agora:** primeiro variar RPS com
   endpoint/custo e N fixos por bloco; depois variar endpoint com RPS e N fixos.
   Repetir o desenho para outros N sem misturar os fatores. Registrar oferta,
   starts, conclusões, erros e qualidade do serviço benigno junto da CPU. Manter
   políticas de conexão/logging e condições de host constantes ou declaradas.
6. **Distinguir gargalos:** vítimas altas com proxy/host ainda com margem sugerem
   limite local a investigar; proxy pressionado com vítimas sem elevação sugere
   limite no caminho; host pressionado, throttling ou fontes atrasadas sugerem
   contenção do arranjo. São sinais conjuntos, não diagnóstico causal por um único
   percentual. Não escolher RPS/endpoint pela separação dos detectores no TEST.
7. **Comparabilidade:** novas ausências/reset/ponderação/normalização mudariam a
   distribuição e a memória dos detectores. Exigem versão, baseline/calibração e
   novo TEST independentes quando aplicadas cientificamente; thresholds antigos
   não são transferíveis automaticamente. Mudança só da série host não altera a
   entrada mean_cpu_percent, mas ainda muda evidência observacional e deve ser
   explicitada. Nenhuma correção foi implementada nesta auditoria.

Referência experimental complementar: Schroeder, Wierman e Harchol-Balter,
*Open Versus Closed: A Cautionary Tale*, NSDI 2006, §1/Figura1 e §5.1
([publicação oficial](https://www.usenix.org/conference/nsdi-06/open-versus-closed-cautionary-tale),
[texto](https://static.usenix.org/events/nsdi06/tech/full_papers/schroeder/schroeder_html/index.html)).
Fundamenta declarar modelo de carga/concorrência e não confundir oferta com serviço;
não fornece nossa fórmula CPU, quotas, janelas ou taxas. As alternativas métricas
acima derivam da contabilidade de tempo e da pergunta experimental, não de uma
prescrição universal de média por esse artigo.

## 11. Referências técnicas e testes

| Fonte oficial / seção | O que fundamenta; limite |
|---|---|
| [Engine API v1.48 ContainerStats/ContainerCPUUsage](https://raw.githubusercontent.com/moby/moby/v28.0.4/docs/api/v1.48.yaml) | Campos, ns, n, read/preread, two cycles/one-shot e fórmula. Não garante frescor da agregação do simulador. |
| [Docker CLI 28.0.4 calculateCPUPercentUnix](https://raw.githubusercontent.com/docker/cli/v28.0.4/cli/command/container/stats_helpers.go) | Convenção Linux do percentual; não uma normalização por quota. |
| [Moby 28.0.4 ContainerStats](https://raw.githubusercontent.com/moby/moby/v28.0.4/daemon/stats.go) | Preenchimento dos frames e resposta vazia para container parado/reiniciando. Não prova esse estado em um run apenas por CPU 0. |
| [Kernel v1 CPU Accounting Controller](https://docs.kernel.org/admin-guide/cgroup-v1/cpuacct.html) | Contabilização hierárquica e ns; não porcentagem pronta. |
| [Kernel v2 CPU Interface Files / Cpuset](https://docs.kernel.org/admin-guide/cgroup-v2.html) | usage_usec, cpu.max, weight e cpuset efetivo; restrições ancestrais. Não assegura reserva por ausência de limites locais. |
| [Kernel CFS Bandwidth Control](https://docs.kernel.org/scheduler/sched-bwc.html) | Quota/period e throttling; teto não é piso de capacidade. |
| [Docker Resource constraints → CPU](https://docs.docker.com/engine/containers/resource_constraints/#cpu) | cpus/quota/cpuset/shares e ausência de reserva por shares. |
| [Kernel /proc/stat §1.7](https://docs.kernel.org/filesystems/proc.html#miscellaneous-kernel-statistics-in-proc-stat) e [account_guest_time](https://raw.githubusercontent.com/torvalds/linux/v6.12/kernel/sched/cputime.c) | USER_HZ, categorias e dupla contabilização de guest se somado novamente. Não quantifica o efeito em artefatos sem contadores brutos. |

Links consultados em 23/10/2026. O código Engine/CLI foi consultado na tag 28.0.4,
igual à versão registrada, não presumindo que documentação latest descreva toda
particularidade desse binário. A documentação kernel distingue v1/v2; a evidência
arquivada selecionada registra v2. As condições efetivas dos cgroups não foram
reinventadas a partir dessa versão.

Novo `tests/test_cpu_accounting_audit.py`: **14 testes determinísticos** para
unidade/delta,>100, n/fallback, primeira leitura, payload inválido, duas vítimas,
pesos distintos, cache antigo/ausente, fronteira, entrada/saída, sequência/duplicata,
erros/NotFound, reinício, queda de média com total constante, arredondamento e host.
Relógio falso e Docker mock; não inicia thread real nem container. As regressões
incluem suporte de features, proxy, vítima fixa e configuração: **118 testes,
todos OK**. Mensagens de falha na saída pertencem a fixtures, não a stress real.

```bash
.venv/bin/python -B -m unittest tests.test_cpu_accounting_audit tests.test_proxy_monitor tests.test_feature_extraction tests.test_single_victim tests.test_experiment_config -v
.venv/bin/python -B experiment_results/cpu-accounting-audit-20261023/inspect_existing.py
```

Saídas novas separadas: `experiment_results/cpu-accounting-audit-20261023/`
(evidence.json, inspect_existing.py e tests.log). Mapa de código principal:
stats_collector._calc_cpu_percent/_run/get_averages/update_containers;
main_orchestrator.log_metrics_to_csv/_run;
source_experiment.run; extract_features.extract_features;
autoscaler_logic.Autoscaler.decide_scaling; host_stats.get_host_cpu_percent;
proxy_monitor.resources/ProxyMonitor; docker_manager.start_instance;
source_manager.SourceManager.start; http_proxy.HttpProxy.start.

**Para o orientador — “A CPU média como ela é calculada atualmente? Planeja mudar algo?”**
Hoje calculamos o consumo de cada vítima pelos deltas Docker; 100% equivale a um
núcleo lógico. O coletor tira a média das amostras recentes das vítimas e pode
reutilizar cache antigo. Proxy e host ficam separados. Para várias vítimas, não
pretendemos substituir silenciosamente essa média: propomos mostrar consumo por
vítima, total, média por réplica e desequilíbrio, com qualidade/tempo explícitos.
Normalizar por capacidade só depois de definir e verificar esse orçamento.
