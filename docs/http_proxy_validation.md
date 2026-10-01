# Evidência da validação da Etapa 4

Validação real no Ubuntu nativo em 2026-10-01. Artefatos completos em
[`experiment_results/stage4-final/`](../experiment_results/stage4-final/).
Não houve commit. Saídas automáticas continuam ignoradas pelo Git; esta página registra os resultados verificáveis.

## Ambiente e captura

CLI (`default`) e SDK retornaram o daemon `177c5506-8b67-45e1-ab1c-acd019f2994e`,
Ubuntu 24.04.1 LTS, kernel `6.11.0-29-generic`. O proxy e as vítimas usaram a
`edos_network` desse daemon. NGINX `1.28.0-alpine` executado pelo digest
`sha256:30f1c0d78e0ad60901648be663a710bdadf19e4c10ac6782c235200619158284`.

Tcpdump iniciou sem sudo com `cap_net_admin,cap_net_raw=eip`, capturou HTTP real
e terminou via SIGTERM enviado pelo Python. Depois da correção local AppArmor:
nenhum novo `DENIED operation="signal"` desde a captura limpa, nenhum processo
tcpdump e nenhum container da validação remanescente. Perfil tcpdump manteve enforce.
Veja [environment_validation.json](../experiment_results/stage4-final/environment_validation.json).

Capturas simultâneas de dez GETs via proxy:

| Interface | Observações | Cliente↔proxy | Descrições TCP repetidas |
|---|---:|---:|---:|
| lo | 37 | 37 | 0 |
| any | 294 | 37 | 139 |
| bridge | 87 | 0 | 0 |

Comparação de tupla/seq/ACK/flags/timestamp TCP/comprimento; não altera pacotes nem
faz deduplicação do dataset. Raw captures e resumo estão em
[capture_audit](../experiment_results/stage4-final/capture_audit/).
Captura oficial: `lo`, BPF `tcp and host 127.0.0.1 and port 8080`.

## Cenários finais

A/B/C: 30 s, seed 42, uma vítima, autoscaling desligado, sem alteração de
workloads/pools/RPS/timeouts. B/C: ataque contínuo planejado de 10 a 20 s.

| Caso | Status | Vítimas | Métricas | Tentativas | Benignas 200 | Ataque 200 | Pacotes | Access rows |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | completed | 1 | 30 | 1140 | 1140 | 0 | 4943 | 1140 |
| B | completed | 1 | 30 | 395 | 0 | 395 | 1806 | 395 |
| C | completed | 1 | 30 | 1534 | 1139 | 395 | 6933 | 1534 |
| technical | completed | 2 | 10 | 351 | 351 | 0 | 1455 | 351 |
| failure | incomplete | 1 | 4 | 141 | 110 | 0 | 595 | 110 |

Todas as 90 métricas científicas: `num_instances=1`, `decision=NO_ACTION`.
No cenário C, 393 tentativas benignas começaram durante o ataque e mantiveram classe benign.
Origem, IDs, intervalos efetivos, run_id e classe unknown dos pacotes foram conferidos.
Schemas CSV de métricas/request/eventos/RTT/pacotes foram comparados com a regressão da Etapa 3 e permanecem idênticos.

[Resumo final](../experiment_results/stage4-final/validation_summary.json).

## Roteamento, isolamento e falha

Durante todos os cenários proxy, o construtor do seletor client-side foi substituído
no teste por uma função que falha se chamada. Nenhuma chamada ocorreu. Ambos os
geradores ficaram com `_load_balancer=None` e somente `_service_endpoint` como destino.
Não recebem o inventário; updates de backends e URLs fora do serviço são rejeitados.
Todos os target_url arquivados apontam para `http://127.0.0.1:8080/`; nenhuma URL de vítima.

Exemplo real de C (`run_id=f060075d028d4b6cbd0021d0bbc60fba`):

```text
request_log: request_000000002 → http://127.0.0.1:8080/?work=10&sleep=0.0
access log: request_000000002 → upstream=172.19.0.2:80 → status=200
inventário: 172.19.0.2 → hostname=0ccfd31418b9 → nenhuma porta publicada
resposta: host=0ccfd31418b9 work=10 sleep=0.0000s elapsed=0.0023s
```

A validação fez essa associação para todas as respostas 200, além de verificar
unicidade dos request IDs no access log, upstream único e pertencimento ao inventário.
A vítima existente não foi modificada. O proxy foi o único publicador da porta 8080.

Duas vítimas (somente técnico): hostname `72784ab7c464` recebeu 176 requests e
`5fd829e29eb1` recebeu 175, total 351. Nenhuma tinha PortBindings.

Falha real: stop Docker aplicado após ~3 s e confirmado pelo teste. O próximo tick
detectou `proxy identity/state changed: exited`; status incomplete. Foram 110 respostas
e 31 erros de transporte, todos ainda destinados ao proxy. Não houve restart,
recriação, troca de endpoint ou fallback para vítima. Também houve testes unitários
de substituição, estado stopped, erro de consulta e status incomplete em falha de setup.

O primeiro ensaio de falha teve defeito na sincronização da thread de teste e
não aplicou a interrupção. Ele não é evidência de falha. O runner foi corrigido
para exigir confirmação de stop; a bateria final acima passou.

## Protocolo e retries

Teste técnico separado, sem dataset científico:

- Dez requests com HTTP/1.1; caminho e query codificada preservados no access log.
- Hostnames alternados e workload `work=17&sleep=0.001` confirmado na resposta.
- Keep-alive cliente observado por connection_requests; backends reutilizaram as
  conexões do readiness, com payload capturado e zero SYNs novos para vítimas.
- Após parar uma vítima, quatro tentativas produziram `[504,200,504,200]`.
  Quatro entradas de log, uma seleção upstream cada; zero retries/failover observados.

O primeiro teste esperava 502; o erro real de conexão foi timeout 504. A checagem
foi corrigida para aceitar 502/504, mantendo a exigência de uma única tentativa.
[Evidência de protocolo](../experiment_results/stage4-final/protocol/validation.json).

## Regressão e reprodução

38 testes unitários passaram: os 29 anteriores e nove novos. Cobrem configuração,
seed/Poisson, workloads, ground truth, wiring histórico, integridade, isolamento,
rejeição de acesso direto, archive com run_id e status incompleto.

Regressão real da Etapa 3 (`load_balancer.enabled=false`):

| Caso | Status | Tentativas | Pacotes |
|---|---|---:|---:|
| A | completed | 1141 | 4624 |
| B | completed | 395 | 1648 |
| C | completed | 1536 | 6511 |

[Resumo histórico](../experiment_results/stage4-final/stage3-regression/validation_summary.json).

Comandos executados (diretórios novos):

```bash
.venv/bin/python -B -m unittest discover -s tests -q
.venv/bin/python -B -m experiments.validate_http_proxy --output experiment_results/stage4-final
.venv/bin/python -B -m experiments.validate_proxy_protocol --output experiment_results/stage4-native/protocol_final
.venv/bin/python -B -m experiments.validate_single_victim --output experiment_results/stage4-native/stage3-regression
git diff --check
git status --short
```

Limites: não há autoscaling dinâmico ou LDoS. Integridade é periódica; o host ainda
pode alcançar IPs da bridge. O proxy adiciona overhead e modifica a assinatura TCP.
Reprodução controla configuração/seed, não o scheduling nem o tempo exato do host.
Runners continuam sequenciais; o diretório de saída deve ser novo.

Detalhes do desenho e das diretivas: [http_proxy.md](http_proxy.md).
