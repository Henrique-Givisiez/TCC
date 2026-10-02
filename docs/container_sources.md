# Etapa 5 — origens de rede em containers

A execução `traffic_sources.execution=containers` usa uma origem por container,
com identidade lógica estável `normal_1`, `attack_1`, etc. IP, hostname e ID Docker
são atributos da execução, registrados em `source_inventory.json`. Não classifique
ataques pela quantidade de IPs: o número de origens é uma variável experimental.

```text
normal_N / attack_N → edos_sources → NGINX → edos_network → vítima(s):80
                                       ↑
                               127.0.0.1:8080 no host
```

Sources pertencem exclusivamente a `edos_sources`; vítimas exclusivamente a
`edos_network`; somente o proxy pertence às duas. Vítimas não publicam portas.
O endpoint recebido por cada gerador é `http://edos_service:80`, alias do proxy.
O endpoint externo permanece `http://127.0.0.1:8080` para validações históricas.
A configuração dos sources não contém inventário, nomes, IPs ou portas de vítimas.
Não há fallback ou redirecionamento; falhas deixam o mesmo endpoint configurado.

## Execução

```bash
docker context show
docker build -f docker/Dockerfile.sources -t edos_sources:stage5 .
python3 -m experiments.validate_source_containers --output experiment_results/nova-etapa5
# Uma execução direta, em diretórios transitórios ainda não utilizados:
python3 -m simulator.main_orchestrator --config experiments/configs/container_sources.json
```

Não execute cenários simultâneos: compartilham a publicação 8080. O núcleo usa
exclusivamente o socket nativo do Ubuntu. O modo `host` continua explícito para
as Etapas 1–4; o modo container exige proxy ligado e autoscaling desligado.
Nenhum cenário científico desta etapa altera o NGINX ou sua política de retries,
keep-alive, HTTP/1.1 e upstreams estáticos. LDoS e detectores não foram adicionados.

A imagem comum usa Python `3.12.10-slim-bookworm` e digest de base fixado no
Dockerfile, requests `2.32.3` e dependências transitivas fixadas. O Docker SDK e
bibliotecas de análise não entram na imagem. O build copia uma lista de módulos,
sem `config.py`, Docker manager, load balancer histórico ou inventários.
Ambos os modos usam o código existente de ritmo e envio, evitando um segundo
motor de tráfego. Summary loggers recebem caminhos explícitos.

O host resolve a tag local uma vez e executa os containers pelo ID imutável da
imagem. Como o build local não foi publicado em registry, seu digest registrado
é o digest da configuração da imagem (`digest_kind=local_image_config`), não um
RepoDigest fictício. A base tem RepoDigest fixado. Os artefatos guardam ambos,
além do Dockerfile e arquivo de dependências usados.

## Entidades e orçamento de envio

Nesta etapa `clients=4` cria quatro sources benignos; `attackers=4` cria quatro
sources atacantes. Cada manifesto atribui explicitamente um índice lógico a uma
origem. O planejamento das origens está separado do motor, permitindo uma futura
atribuição de várias entidades a uma origem, ainda não implementada.

Seeds usam o índice lógico global original por classe, nunca o IP ou ID Docker.
Índices diferentes conservam streams independentes; reiniciar cada source no
índice zero seria incorreto. As taxas são por entidade, com Poisson open-loop,
workload e timeout anteriores. Cada entidade mantém sua sessão HTTP.

`max_concurrent_sends` continua sendo o orçamento agregado da classe. Para N
sources, a divisão é `divmod(budget,N)`, entregando o resto aos primeiros índices.
Com quatro sources e orçamento 64, são 16 workers por source; com três, 22/21/21.
Quantidades superiores ao orçamento são rejeitadas. A atribuição aparece no
source plan, manifestos e inventário. Classes desabilitadas não criam sources.

Filas agora são independentes: um source não empresta slots ociosos de outro.
Isso pode mudar o comportamento sob saturação mesmo mantendo a soma 64.
Não interprete igualdade de seed como igualdade exata de tempos observados entre
topologias: scheduling, containers, instrumentação e filas fazem parte do experimento.

## Relógio e ground truth

Antes de liberar qualquer gerador, o host verifica quatro amostras por container:
mesmo namespace de tempo do host e timestamp monotônico remoto contido entre as
leituras locais anterior/posterior ao exec. Namespace diferente ou amostra fora
do intervalo aborta o setup, sem mudar a semântica da timeline. A evidência fica
em `clock_validation.json`. A mesma âncora epoch/monotônica e o mesmo `run_id`
são distribuídos por arquivos de controle, sem chamadas HTTP de controle.

Cada source grava somente em seu próprio diretório. Journals JSONL com sequência
local registram admissão, abandono, início/fim HTTP, snapshots de eventos,
fechamento da emissão e certificação de drenagem. As transições locais reutilizam
`GroundTruth` da Etapa 2. CSVs locais são evidência; não são o dataset global.

O host é o único escritor dos CSVs científicos agregados e verifica identidade,
sequências e contagens de admissão/início/conclusão. Request IDs incluem o
`source_id` lógico e contador local, permanecendo iguais nos logs locais,
request log agregado, RTT e header do NGINX. Não se renumeram após a execução.
A ordem global é determinada por timestamps com desempate por ID.

A timeline global conserva:

- `actual_start`: primeiro início HTTP atacante no executor;
- `actual_end`: todas as origens fecharam a admissão e nenhuma tentativa admitida
  está esperando para iniciar; usa as certificações locais de fim de emissão;
- `drained_end`: última conclusão, somente com certificação de drenagem completa.

Fim de emissão não espera respostas HTTP. Uma requisição enfileirada ainda pode
iniciar depois do pedido de parada; o evento continua aberto até esse início.
Uma origem sem evidência suficiente impede fabricar fechamento global. Fim de
emissão comprovado pode sobreviver a drenagem incompleta, como na Etapa 2.
O teste unitário distribuído certifica emissão em 8.001 s e drenagem em 100 s.
Como na Etapa 2, `drained_end` registra a última conclusão: pode preceder a
certificação de fechamento se todas as respostas terminarem antes da parada da
admissão. A certificação posterior não desloca artificialmente essa conclusão.

Os schemas científicos anteriores permanecem. `traffic_class` vem da identidade
do gerador. O contexto global de requests, métricas e pacotes é reconciliado ao
final; snapshots durante a execução são provisórios. Pacotes permanecem
`traffic_class=unknown`. O inventário permite auditoria externa por IP, sem mudar
automaticamente esse schema. Logs NGINX continuam sendo evidência operacional.
A duração continua HTTP client-side, incluindo instrumentação, proxy e vítima;
não representa RTT TCP. Médias legadas consomem amostras de duração por classe.

## Captura e isolamento

Antes da janela científica, cada execução compara `lo`, bridge de entrada, veth
frontend do proxy e `any`, com requisições de todos os sources identificadas como
`phase=capture_audit`. O teste valida cobertura bidirecional, múltiplos IPs,
segmento e descrições TCP repetidas. Não concatena interfaces nem deduplica dados.
Readiness e probes de isolamento também terminam antes da janela.

A bridge de entrada é selecionada somente depois de passar a comparação.
Bridge e veth apresentaram cobertura sem repetição. A falha real mostrou que a
veth desaparece quando o proxy para; a bridge permanece e permite continuar a
captura. `any` repetiu observações e é excluída do dataset oficial. A interface
é descoberta pelo inventário Docker, sem nome `br-...` codificado previamente.

O filtro exige o IP frontend do proxy e porta 80 nas duas direções, excluindo
proxy↔vítima. Contagens de origens consideram o sentido source→proxy; o sentido
de resposta tem o IP do proxy como `src_ip` e não constitui uma nona origem em C.
CSV e PCAP bruto são capturados no mesmo ponto, com entrega imediata,
sem tráfego HTTP adicional. Estatísticas de descarte e descrição de possíveis
repetições são arquivadas. Retransmissões TCP reais não são removidas.

Probes técnicos executados em cada source testam nome e IP real da vítima.
Esses endereços entram somente no processo auxiliar de diagnóstico; nunca no
manifesto ou processo gerador. DNS indisponível e conexão direta malsucedida
validam o isolamento efetivo neste host. Não presumimos que anexar redes diferentes
seja prova suficiente, nem modificamos o firewall global do Ubuntu.

Durante a janela há inspeção Docker de identidades/estado, sem readiness HTTP
periódica. Saída esperada de atacantes depois da drenagem é aceita; saída prematura
sem certificação é erro. Parada, desaparecimento ou consulta impossível do proxy
resulta em `incomplete`, sem reinício nem acesso direto à vítima.

## Artefatos e encerramento

Cada execução guarda os artefatos anteriores e:

- `source_inventory.json`, `effective_config.json` e `run_status.json`;
- `source_artifacts/source_plan.json`, `image_identity.json`, Dockerfile e dependências;
- `clock_validation.json`, `aggregation_audit.json`, PCAP bruto e diagnósticos tcpdump;
- `network_audit/`: PCAPs/textos por interface, comparação e probes de isolamento;
- por source: manifesto, controle, ready/status final, journal, CSVs locais,
  evidência de resposta e saída do container;
- todos os artefatos NGINX anteriores, com `remote_addr` adicional no access log.

CPU/memória/custo e `num_instances` continuam contando exclusivamente vítimas.
CPU do host inclui naturalmente os sources e o proxy. O host fecha admissão,
drena com limite, agrega evidências, encerra capturas e remove sources/proxy/vítimas.
Drenagem excedida é incompleta e recebe encerramento explícito, sem processo
executor residual. As duas redes nomeadas permanecem disponíveis para próximas
execuções; não são containers residuais.

`result_archive.py` associa inventário e diretório de sources pelo mesmo `run_id`.
Os artefatos transitórios da raiz precisam ser arquivados antes de repetir; o
validador usa diretórios novos por cenário e um processo Python por execução.

## Limitações

Este desenho depende de clocks demonstravelmente comparáveis no Engine local.
Não cobre geradores em máquinas diferentes, reinício do host, alterações externas
do firewall durante a janela ou adulteração dos registros. Journals não oferecem
fsync/crash recovery resistente a queda de energia. Registros BEGIN adicionam I/O
à instrumentação client-side, sem subtração artificial desse overhead.

Captura é IPv4/TCP do serviço; DNS e ARP ficam fora do CSV. Erros de resolução ou
antes de iniciar TCP podem aparecer no request log sem pacote correspondente.
A comparação de descrições é evidência de duplicação observacional, não detector
de retransmissões. O validador exige investigação caso surjam descrições repetidas.
O teste de isolamento vale para este daemon/regras; não é garantia contra sources
privilegiados ou um operador que altere a rede. Sources podem alcançar peers na
bridge de entrada. Há uma imagem comum e um worker lógico por origem; autoscaling,
LDoS, detecção e separação configurável entre entidades/origens permanecem fora.
