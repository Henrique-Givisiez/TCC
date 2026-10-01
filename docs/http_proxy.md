# Etapa 4 — proxy HTTP real

O modo proxy usa NGINX Open Source dedicado. O modo histórico continua explícito:
`load_balancer.enabled=false` preserva o seletor client-side das Etapas 1–3.
`true` usa apenas `service_endpoint`, sem seleção de vítimas pelos clientes.
A escolha é feita antes do setup; nenhuma falha muda a topologia em runtime.

```text
gerador benigno ──┐
                  ├─ http://127.0.0.1:8080 ─ NGINX:80 ─ edos_network ─ vítima(s):80
gerador atacante ─┘
```

Somente o proxy publica `127.0.0.1:8080`. As vítimas têm `PortBindings={}`.
O proxy resolve nomes Docker do inventário, nunca portas publicadas das vítimas.
Ausência de publicação não é firewall: no Engine nativo o host pode alcançar
IPs da bridge. Os geradores não recebem esses IPs, nomes, portas ou quantidade.
Esta etapa verifica isolamento da API e do caminho HTTP, não isolamento de processos.

## Ambiente e execução

O contexto esperado é `default`; CLI e `docker.from_env().info()` devem retornar
o mesmo ID do daemon Ubuntu nativo. O núcleo fixa `unix:///var/run/docker.sock`
para criação/coleta e rejeita no setup proxy um kernel diferente do host.
Não há adaptação para WSL ou Docker Desktop.

```bash
docker context use default
docker info
docker build -t edos_target_app:latest .
docker pull nginx:1.28.0-alpine
python3 -m experiments.validate_http_proxy --output experiment_results/nova-validacao-proxy
python3 -m experiments.validate_proxy_protocol --output experiment_results/novo-teste-protocolo
```

A imagem do proxy é `nginx:1.28.0-alpine`, executada pelo digest fixo
`sha256:30f1c0d78e0ad60901648be663a710bdadf19e4c10ac6782c235200619158284`.
O setup exige que essa imagem esteja disponível localmente. Registra tag,
digest do repositório, ID da imagem de plataforma e identidade do daemon.
O Dockerfile da vítima foi preservado; o inventário registra seu ID de imagem.

A configuração científica é `experiments/configs/proxy_single_victim.json`:
30 s, seed 42, uma vítima fixa, autoscaling desligado, ataque contínuo entre
10 e 20 s. Taxas, workloads, pools e timeouts vêm dos defaults da Etapa 1.
O teste técnico usa duas vítimas fixas durante 10 s, sem ataque/autoscaling.
`proxy=true + autoscaler=true` e proxy com zero vítimas são rejeitados.
LDoS/burst continuam rejeitados.

O runner cria pastas novas e usa um processo por cenário. Não execute cenários
concorrentes: a porta 8080 é única. Uma execução direta pelo orquestrador usa
os arquivos transitórios existentes e `proxy_artifacts/`; arquive-os antes de
repetir. O diretório do proxy não é sobrescrito. O helper `move_result` associa
e move os artefatos proxy/effective config quando arquiva métricas da raiz.

## Encaminhamento e conexões

`simulator/http_proxy.py` gera configuração para N vítimas, valida nomes e inicia
NGINX apenas depois de `nginx -t`. Os backends são estáticos durante a execução.
Geração está separada do ciclo de vida, e o diretório montado permite uma futura
configuração candidata, validação, aplicação/reload e confirmação. Esse
controlador e o reload dinâmico não foram implementados.

Diretivas principais:

```nginx
upstream victims {
    server target_instance_1:80 max_fails=0;
    # Uma entrada por vítima, na ordem do inventário.
    keepalive 32;
    keepalive_timeout 60s;
    keepalive_requests 1000;
}
location / {
    proxy_pass http://victims;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_next_upstream off;
    proxy_next_upstream_tries 1;
    proxy_cache off;
    proxy_buffering off;
    proxy_request_buffering off;
    proxy_connect_timeout 5s;
    proxy_read_timeout 60s;
    proxy_send_timeout 60s;
}
```

`proxy_pass` sem URI adicional preserva caminho/query neste fluxo. HTTP/1.1 e
reutilização upstream são explícitos. `keepalive 32` limita o cache de conexões
ociosas por worker, não conexões ativas. O frontend usa keep-alive 60 s/1000
requisições; o proxy tem um worker e `worker_connections=4096`.

`proxy_next_upstream off` impede encaminhar a mesma requisição ao próximo backend;
o limite de tentativas também é explícito. `max_fails=0` desliga exclusão passiva
de servidores após falhas. Não existem health checks periódicos, cache, rate
limiting, autenticação, TLS, sticky sessions ou backend de backup.
Essas diretivas não removem retransmissões TCP.

Referências: [proxy](https://nginx.org/en/docs/http/ngx_http_proxy_module.html),
[upstream](https://nginx.org/en/docs/http/ngx_http_upstream_module.html).

Os geradores preservam sessões, pools e Poisson por worker. Em modo proxy,
`_load_balancer=None`; APIs dedicadas recebem uma string de endpoint, e
`update_targets` é proibido. Uma URL fora desse endpoint é rejeitada antes de
qualquer envio HTTP. Redirecionamentos estão desligados e as sessões ignoram
proxies de ambiente. Requests mantém seus retries de transporte desabilitados.
O header `X-Edos-Request-Id` correlaciona evidência operacional por tentativa,
sem transmitir `traffic_class` ou atribuir ground truth pelo proxy.

## Captura e ground truth

A captura científica proxy é exclusivamente cliente↔proxy, nas duas direções:

```text
interface: lo
BPF: tcp and host 127.0.0.1 and port 8080
```

A escolha foi validada no Ubuntu nativo: captura simultânea de dez requisições
via proxy mostrou 37 pacotes em `lo`, todos de entrada do serviço, sem descrições
TCP repetidas. `any` mostrou 294 observações, 139 repetidas e tráfego interno.
A bridge mostrou 87 observações e nenhuma da tupla loopback:8080.
O comparador usa tupla, sequência/ACK, flags, timestamp TCP e comprimento;
não deduplica nem remove retransmissões do dataset. A contagem “received by
filter” de libpcap não é a quantidade de linhas exportadas.

O segmento proxy↔vítima aparece apenas em captura técnica separada para testar
keep-alive. Nunca é concatenado ao `traffic_capture.csv` oficial. O caminho
histórico mantém sua captura anterior, explicitamente separada do modo proxy.

O tcpdump deve ter `cap_net_raw,cap_net_admin` e permitir encerramento pelo runner.
Neste host, o perfil AppArmor foi corrigido pelo usuário no arquivo local com
`signal (receive) set=(term, kill, int) peer=snap.code.code,`; o perfil principal
continuou em enforce. Captura sem sudo, SIGTERM e ausência de novos DENIED foram
validados. O sniffer espera a mensagem de readiness, verifica processo/leitor
nos ticks e drena stdout antes de finalizar o CSV.

Ground truth e schemas de request/RTT/eventos/pacotes foram preservados. Pacotes
continuam `traffic_class=unknown`; labels vêm dos geradores e da timeline da
Etapa 2, nunca de logs NGINX. Duração HTTP client-side inclui o proxy e espera
até a resposta; os nomes históricos RTT não a tornam TCP RTT.

## Integridade, métricas e artefatos

Readiness limitada confirma HTTP e hostnames das vítimas antes do relógio e da
captura; suas linhas têm `phase=setup`. Durante a janela, somente inspeção Docker
verifica ID esperado, existência e `running`, sem probes HTTP. Estado desconhecido,
substituição ou parada gera `incomplete`, sem reparação. A verificação é periódica,
não contínua. Também ocorre após drenagem, antes da parada intencional.
Falhas anteriores ao relógio têm status de setup sem inventar eventos/tempos.

Somente vítimas entram na lista monitorada, CPU/memória médias, `num_instances`
e custo fictício. CPU do host inclui naturalmente o proxy. Em summaries legados,
`num_targets=1` significa um endpoint conhecido pelo gerador, inclusive com N vítimas.

Cada pasta do runner preserva todos os CSVs anteriores, `run_status.json`,
`effective_config.json` e `proxy_artifacts/` com:

- `proxy_config.conf`, access log JSON e error log;
- `proxy_identity.json`: container, daemon, imagem/tag/digest e checks;
- `backend_inventory.json`: vítimas, hostnames, IPs, imagens e portas;
- `routing_evidence.jsonl`: request ID e corpo de resposta existente;
- `capture_metadata.json`, `readiness.json` e saída do container.

O access log contém timestamp, request, status, upstream/status, tempo total,
tempo de upstream/conexão e identificador da tentativa. A validação correlaciona
request log → access log → IP do inventário → hostname retornado, para cada 200.
Os arquivos montados sobrevivem à remoção; ausência de evidência esperada é erro.
Parada/captura/logs são finalizados antes da remoção das vítimas.

O overhead do proxy, duas conexões TCP distintas, política de reutilização,
logging operacional, filas e correlação de requests fazem parte desta arquitetura.
Não subtraia latência/CPU nem compare features temporais com a topologia antiga
como se fossem equivalentes. Essas diferenças também importarão para LDoS futuro.

Resultados desta implementação: [http_proxy_validation.md](http_proxy_validation.md).
