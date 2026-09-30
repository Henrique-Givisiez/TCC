# Etapa 2 — ground truth de novas execuções

O contrato aplica-se a novas execuções pelo orquestrador. Os CSVs históricos não
foram alterados. `label` histórico NÃO equivale a `traffic_class` ou `attack_active`.

## Fontes de verdade

- `traffic_class` de requisições: função geradora (`normal` → `benign`,
  `attack` → `attack`). A janela, workload e métricas não classificam origem.
- `traffic_class` de pacotes: sempre `unknown`. Nenhum registro associa os sockets
  dos geradores às conexões capturadas. IPs/portas/backend/keep-alive não resolvem
  essa ausência de instrumentação.
- `attack_active` e `active_event_ids`: uma instância de `GroundTruth`, compartilhada
  pelo orquestrador, geradores, request logger e sniffer. CPU, RTT, autoscaler e
  detectores não participam da consulta.
- `attack_id/event_id` em requisições do atacante: evento passado à tarefa que a
  originou. Requisições normais não recebem identidade causal de ataque.
- `run_id`: UUID por execução; `request_id`: contador único dentro dessa execução.
  IDs de evento são únicos por execução e campanha agrupa eventos.

As flags operacionais `attack_active` do injetor e `traffic_active` do gerador
normal controlam workers. Não são fonte de labels. O sniffer não tem `set_label()`
nem `current_label`. O modelo aceita várias campanhas/eventos e sobreposição;
o orquestrador atual cria somente `attack_001/event_001`, perfil `continuous`.
Não foi implementado LDoS.

## Relógio e instante da observação

`ExperimentClock` registra um par `epoch_initial`/`monotonic_initial` depois do
setup da infraestrutura, antes de iniciar a captura e os geradores. Pequenos custos
de inicialização dos logs integram esse período; não se promete início em zero.
O par aparece nos eventos e em `run_status.json`, inclusive sem ataques.

`timestamp` é Unix epoch em segundos, observado com `time.time()`; `elapsed_seconds`
é diferença monotônica em relação à âncora. Durações usam diferenças monotônicas.
A amostragem dos dois relógios não é atômica: não se promete precisão de microssegundos
por haver casas decimais no CSV.

Para cada tentativa, o início é registrado na tarefa de envio, antes de
`session.get()`, com o pequeno custo de instrumentação associado. Não é submissão
à fila, primeiro byte na rede ou chegada à vítima. Conclusão é o retorno/exceção
da chamada HTTP, antes da escrita do resultado. O registro mantém o contexto do
**início**, mesmo quando a resposta chega depois do evento.

Para pacotes, `timestamp` vem da própria linha `tcpdump -tt`, nunca do horário de
leitura/escrita. `elapsed_seconds = timestamp - epoch_initial`: essa conversão usa
relógio de parede, sujeito a ajustes do sistema. Não é uma medição monotônica.
Uma pequena incerteza perto das fronteiras também decorre dos dois relógios.

## Intervalo efetivo e fechamento

O intervalo ativo é `[actual_start_seconds, actual_end_seconds)`:

1. Ativação apenas autoriza admissão; não cria intervalo ativo.
2. A primeira tentativa iniciada pelo atacante estabelece `actual_start`.
3. Cada submissão registra admissão antes de entrar no executor.
4. A parada fecha admissão sob o mesmo lock que registra admissões.
5. Tarefas já admitidas permanecem na fila e podem começar depois de `stop_requested`.
6. Quando a admissão está fechada e não há tarefa admitida ainda por iniciar,
   registra-se o instante observado de certificação desse estado como `actual_end`.
7. Conclusões das chamadas são acompanhadas separadamente até `drained_end`.

Isso não reescreve os executores: somente conta admissões, inícios e conclusões.
Se a resolução do relógio não distingue fechamento da última tentativa, aguarda-se
outra transição observada; nenhum epsilon/timestamp sintético é inserido.
`actual_end` é uma certificação no cliente, não o instante do último pacote.
`drained_end` é a última conclusão; pode anteceder `actual_end` se todas as chamadas
já terminaram antes da parada.

Para evento iniciado e ainda aberto, consultas durante a execução retornam ativo.
Se o evento finaliza incompleto e não tem fim conhecido, consultas depois do último
início conhecido retornam `None` (campo CSV vazio), em vez de fabricar 0 ou 1.
O trecho entre primeiro e último início conhecido conserva presença temporal.
`active_event_ids` contém somente eventos cuja presença pode ser afirmada;
`attack_active` vazio impede interpretar uma lista vazia como ausência comprovada.
Um evento executado com fim conhecido pode conservar seu intervalo mesmo que sua
drenagem seja incompleta.

Taxa/atacantes zero e janela não executada não criam início/fim efetivo. Ataque
habilitado deixa uma linha planejada, posteriormente `not_executed`. Ataque
explicitamente desabilitado deixa apenas o cabeçalho. Campos desconhecidos são vazios.

## Schemas

### `attack_events.csv`

| Coluna | Significado |
| --- | --- |
| `schema_version` | Contrato 1. |
| `experiment_id` | ID da configuração. |
| `run_id` | UUID da execução. |
| `experiment_start_timestamp` | Âncora epoch, segundos. |
| `experiment_start_monotonic` | Âncora monotônica local, segundos; não comparar entre hosts/boots. |
| `attack_id` | Campanha lógica. |
| `event_id` | Evento individual dentro da execução. |
| `profile` | Perfil configurado; hoje `continuous`. |
| `scheduled_start_seconds` | Início pretendido na configuração, relativo à âncora. |
| `scheduled_end_seconds` | Fim pretendido, relativo à âncora. |
| `activation_requested_seconds` | Solicitação efetiva de ativação ao injetor. |
| `actual_start_seconds` | Primeiro início de tentativa HTTP do evento. |
| `stop_requested_seconds` | Primeira solicitação efetiva de fechamento. |
| `actual_end_seconds` | Certificação de que nenhuma tentativa adicional pode começar. |
| `last_request_start_seconds` | Último início efetivamente registrado. |
| `drained_end_seconds` | Última conclusão, preenchida quando todas as tentativas terminaram. |
| `status` | `planned`, `activated`, `active`, `stopping`, `emission_ended`, `completed`, `not_executed` ou `incomplete`. |
| `end_reason` | `scheduled_end`, `simulation_end`, `interrupted` ou `error`. |

O controlador persiste snapshots nas transições de controle e conclusões de
tentativas, com substituição atômica do CSV. O início não faz I/O de disco antes
da chamada HTTP; um leitor do arquivo durante a execução pode ver o último
checkpoint, enquanto a consulta compartilhada já conhece a transição. A fonte de
verdade em execução é o componente compartilhado; o arquivo é sua representação
persistida, não uma segunda lógica independente. Não reconstruir eventos por
CPU, sucesso HTTP, RTT ou primeiras/últimas linhas das métricas.

### `request_log.csv`

```text
run_id,request_id,generator,worker_id,target_url,timestamp,elapsed_seconds,
end_timestamp,end_elapsed_seconds,duration_ms,traffic_class,attack_active,
attack_id,event_id,active_event_ids,http_status,outcome,error_type
```

- `generator`: `normal` ou `attack`; `worker_id`: índice do worker de ritmo
  desse gerador, não PID ou ID da thread do executor.
- `target_url`: destino passado ao cliente, incluindo parâmetros configurados.
- `timestamp/elapsed_seconds`: início no executor; `end_*`: conclusão.
- `duration_ms`: duração no cliente, incluindo a instrumentação no início.
- `traffic_class`: origem conhecida; `attack_active`: presença temporal no início.
- `attack_id/event_id`: origem causal, preenchida somente para atacante.
- `active_event_ids`: array JSON de eventos ativos no início, inclusive para benigno.
- `http_status`: código recebido, vazio se não houve resposta conhecida.
- `outcome`: `response`, `http_error` (status >= 400), `transport_error`,
  `client_error` ou `incomplete`.
- `error_type`: classe da exceção, sem mensagem potencialmente sensível.

Uma linha por tentativa iniciada, escrita quando ela conclui. Na finalização,
tentativas ainda abertas recebem linha `incomplete`, sem fim/duração fabricados.
IDs seguem ordem de início; linhas podem estar em ordem de conclusão. Chamadas
encerradas depois de declarar o log incompleto não reescrevem sua versão final.
Um encerramento abrupto do processo/host pode perder tentativas ainda não persistidas;
a Etapa 2 não implementa journal resistente a crash.

### `traffic_capture.csv`

```text
run_id,timestamp,elapsed_seconds,src_ip,src_port,dst_ip,dst_port,
packet_length,traffic_class,attack_active,active_event_ids
```

IPs/portas são os valores observados, em ambos os sentidos. `packet_length` conserva
o valor `tcp/length` do parser existente, tipicamente payload TCP; não promete
comprimento total do frame. `traffic_class` é sempre `unknown`.

`attack_active=1` significa apenas que um evento estava ativo no instante capturado.
Não identifica o gerador desse pacote. Não há `attack_id/event_id` causal.
O contexto é consultado novamente na finalização usando a mesma timeline, pois
leitura e registro das transições podem ser processados fora da ordem de captura.
Essa finalização atinge apenas a saída da execução atual, nunca CSVs históricos.

A captura mantém `any`, BPF e parser IPv4. Tráfego fora da faixa de portas, IPv6,
perdas no tcpdump e tráfego de outras fontes não são resolvidos nesta etapa.
Falha de captura marca a execução incompleta, sem invalidar automaticamente um
evento cujo ciclo de vida foi registrado e drenado corretamente.

### `rtt_log.csv`

```text
timestamp,rtt,run_id,request_id,traffic_class,elapsed_seconds
```

`timestamp/elapsed_seconds` representam conclusão; `rtt` é `duration_ms` da
requisição correspondente, em milissegundos. Não é RTT TCP. A exportação detalhada
inclui chamadas com resposta sem status HTTP de erro; falhas de transporte e
respostas HTTP >= 400 ficam no request log, sem aparecer como RTTs bem-sucedidos.
Os acumuladores legados usados para as médias do orquestrador conservam as fórmulas
e os contadores anteriores, incluindo respostas HTTP de erro.

### `simulation_metrics.csv`

```text
run_id,timestamp,elapsed_seconds,elapsed_time_s,num_instances,
average_cpu_percent,mem_usage,avg_rtt_ms,decision,active_containers_names,
attack_active,active_event_ids,host_cpu_percent
```

`timestamp/elapsed_seconds`: instante da observação da linha, depois das ações do
tick e antes de escrevê-la. `elapsed_time_s`: versão arredondada para compatibilidade
nominal de consumidores de métricas. Nenhum `label` nem `traffic_class`.
`attack_active` caracteriza esse instante, **não a janela agregada inteira**.

CPU/memória preservam a média das amostras consultadas nos últimos
`monitoring.interval_seconds`, com o fallback existente. CPU Docker deriva de
contadores do próprio Docker; CPU host usa diferenças entre chamadas. O RTT médio
usa listas drenadas entre leituras, escolhendo origem pelo estado operacional como
antes. Não se atribui uma janela temporal única a essas grandezas nesta etapa;
um estado pontual não autoriza reclassificar todas as amostras agregadas.

### `run_status.json`

```text
schema_version,experiment_id,run_id,experiment_start_timestamp,
experiment_start_monotonic,status,end_reason,producers_drained,errors
```

Pequeno registro de integridade, necessário inclusive para cenários sem ataque.
`status` é `completed` ou `incomplete`; `producers_drained` informa fechamento dos
produtores HTTP; `errors` registra problemas de encerramento/captura. Não é o novo
formato final de metadata/dataset. Este registro começa após preparação da
infraestrutura; falhas anteriores ao estabelecimento da execução podem não criá-lo.

## Encerramento e compatibilidade

O `finally` do orquestrador fecha admissão e sinaliza os dois geradores, tenta drenar
workers/futures com limite de 30 s por gerador, finaliza request log, exporta RTT,
persiste eventos e só então termina tcpdump e consome stdout até EOF. Havendo
produtores não drenados, declara incompletude e não remove backends ainda em uso.
Isso não garante sobrevivência a kill/queda do host nem captura do processamento
residual da vítima depois de timeout do cliente.

As distribuições Poisson e os workloads continuam os mesmos. A espera de ritmo
pode ser interrompida pelo sinal de parada, sem alterar o sorteio positivo.
Summary loggers e fórmulas de métricas/autoscaling/custo permanecem.

`experiments/result_archive.py` arquiva eventos, requisições e status junto às
métricas com o mesmo sufixo. Os 20 runners que movem resultados usam esse ponto;
runners que delegam a eles herdam o comportamento. O helper confere `run_id` e
não associa novos logs a métricas históricas sem esse campo.
Os runners existentes ainda compartilham caminhos e não suportam concorrência.

Scripts de análise históricos continuam lendo seus artefatos antigos. Não há
fallback que interprete `label` como classe ou estado novo. Scripts que esperam
`label` ou timestamp relativo antigo de pacotes precisam de adaptação explícita
antes de ler novas saídas; detectores e extratores não foram migrados nesta etapa.

## Verificação

```bash
python3 -m unittest discover -s tests -v
git diff --check
git status --short
```

Os testes cobrem A–F, fronteiras, relógio, exceções/status HTTP, requisição em voo,
fila real do executor depois da parada, drenagem incompleta, múltiplos eventos,
arquivamento, isolamento das métricas e sorteio Poisson positivo inalterado,
além dos testes da configuração da Etapa 1.

Ver [a evidência da execução controlada](ground_truth_validation.md).
