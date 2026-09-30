# Evidência de validação — Etapa 2

A execução controlada usou o orquestrador real e um backend Docker, durante 6 s,
seed 42, 1 cliente × 8 RPS, 1 atacante × 5 RPS, janela planejada [1,4),
monitoramento de 0.25 s e autoscaler desabilitado apenas nesse cenário de teste.
Workloads conservaram os defaults (normal 10, ataque 5000). Container teve nome
exclusivo e porta 18080; foi removido depois de drenar os produtores.
Nada foi escrito em `experiment_results/`.

Artefatos da execução: `/tmp/edos-stage2-validation/`. Run ID:
`9704aa0175a946c18fb71e570b3ca9ca`. Foram registradas 70 tentativas HTTP,
70 durações exportadas e 24 linhas de métricas. Todas as chamadas tiveram resposta
200, com 57 tentativas benignas e 13 do atacante.

A execução tem `run_status.status=incomplete`, `producers_drained=true`, porque
**a captura ao vivo não pôde ser feita**: tcpdump sem permissão e `sudo -n` exigindo
senha. O arquivo de captura contém somente cabeçalho. Isso demonstra que a falha
não é ocultada e não fabrica pacotes. O evento de ataque ficou `completed`, pois
seu ciclo de execução HTTP foi observado e drenado, independentemente do sniffer.

## Evento real

Extrato de `attack_events.csv`, tempos relativos em segundos (arredondados aqui,
sem alegação de precisão física equivalente às casas decimais dos arquivos):

| Campo | Valor |
| --- | --- |
| `attack_id` | `attack_001` |
| `event_id` | `event_001` |
| `profile` | `continuous` |
| `scheduled_start_seconds` | 1 |
| `scheduled_end_seconds` | 4 |
| `activation_requested_seconds` | 1.002821 |
| `actual_start_seconds` | 1.004676 |
| `stop_requested_seconds` | 4.002654 |
| `actual_end_seconds` | 4.002659 |
| `last_request_start_seconds` | 3.947372 |
| `drained_end_seconds` | 3.951550 |
| `status` | `completed` |
| `end_reason` | `scheduled_end` |

A última chamada terminou antes do sinal de parada; por isso `drained_end` antecede
`actual_end`. Ambos são instantes efetivamente observados com semânticas diferentes.

## Requisições reais

Extrato de `request_log.csv`:

| request_id | elapsed_seconds | traffic_class | attack_active | attack_id/event_id de origem | active_event_ids |
| --- | --- | --- | --- | --- | --- |
| `request_000000001` | 0.011344 | benign | 0 | vazios | `[]` |
| `request_000000014` | 1.004676 | attack | 1 | attack_001/event_001 | `["event_001"]` |
| `request_000000016` | 1.347786 | benign | 1 | vazios | `["event_001"]` |
| `request_000000049` | 4.087206 | benign | 0 | vazios | `[]` |

Para a requisição benigna coexistente:

```text
timestamp = 1790808009.7666278
elapsed_seconds = 1.347785839000153
end_elapsed_seconds = 1.3517292890001045
duration_ms = 3.9434499999515538
traffic_class = benign
attack_active = 1
http_status = 200
outcome = response
```

Esses valores vêm da chamada efetiva no cliente, não da submissão ao executor.

## Métricas reais

Uma linha de `simulation_metrics.csv` apresentou:

```text
timestamp = 1790808009.4248736
elapsed_seconds = 1.0060333239998727
elapsed_time_s = 1.01
num_instances = 1
average_cpu_percent = 0.0
attack_active = 1
active_event_ids = ["event_001"]
```

Não há `label` nem `traffic_class`. O estado temporal veio do início efetivo do
evento mesmo com CPU em zero; não veio da CPU ou de um label global do sniffer.

## Captura: limites da evidência

Cabeçalho real, sem linhas, em `/tmp/edos-stage2-validation/traffic_capture.csv`:

```text
run_id,timestamp,elapsed_seconds,src_ip,src_port,dst_ip,dst_port,packet_length,traffic_class,attack_active,active_event_ids
```

Também foi possível decodificar **10 pacotes reais de um PCAP histórico**, em modo
offline, usando tcpdump e o parser novo. O PCAP foi somente lido. A saída de teste
ficou em `/tmp/edos-stage2-offline-capture/`, sem substituir capturas históricas.
O primeiro timestamp decodificado, preservado, foi `1762192991.418390`, classe
`unknown`. Sua timeline de teste estava vazia; o estado 0 nessa saída valida apenas
a consulta à timeline vazia, não representa ground truth do experimento histórico.

O cenário E foi demonstrado em teste automatizado com **timestamp e evento
sintéticos explícitos**:

```text
timestamp = 1700000022.0
elapsed_seconds = 22.0
traffic_class = unknown
attack_active = 1
active_event_ids = ["event_001"]
```

Isso valida a semântica e o uso do timestamp capturado. Não é apresentado como
pacote coletado no ataque real desta execução. A captura ao vivo durante o ataque
continua pendente de uma permissão de tcpdump disponível no host.

## Testes e estado do repositório

Os 23 testes automatizados passaram, incluindo os 10 testes da Etapa 1.
A comparação de todas as 70 requisições e 24 métricas com os intervalos
registrados em `attack_events.csv` passou; IDs/classes/durações correlacionados
com `rtt_log.csv` também foram verificados. `git diff --check` passou.
Nenhum arquivo em `experiment_results/` ou `results/` foi modificado. Sem commit.

Estado dos arquivos (`git status --short`):

```text
 M .gitignore
 M CLAUDE.md
 M README.md
 M docs/experiment_configuration.md
 M experiments/run_atacantes_intensidade_grid.py
 M experiments/run_atacantes_intensidade_grid_pow2_reps.py
 M experiments/run_ataque_isolado.py
 M experiments/run_desempate_combinado_isolado.py
 M experiments/run_desempate_rps1.py
 M experiments/run_experiments.py
 M experiments/run_experiments_clients_rps.py
 M experiments/run_experiments_combined.py
 M experiments/run_experiments_normal.py
 M experiments/run_extra_reps_agg250.py
 M experiments/run_extra_reps_clients8.py
 M experiments/run_graph4_completar_150_350.py
 M experiments/run_graph4_pow2_base20.py
 M experiments/run_graph4_refined.py
 M experiments/run_wu400000_only.py
 M experiments/verify_s4_candidate.py
 M experiments/wedos_combined_grid.py
 M experiments/wedos_failure_sweep.py
 M experiments/wedos_repro_test.py
 M experiments/wedos_s3_mystery.py
 M simulator/config.py
 M simulator/main_orchestrator.py
 M simulator/normal_traffic.py
 M simulator/tcpdump_sniffer.py
 M simulator/traffic_injectorV0.py
 M tests/test_experiment_config.py
?? docs/ground_truth.md
?? docs/ground_truth_validation.md
?? experiments/result_archive.py
?? simulator/ground_truth.py
?? simulator/request_logger.py
?? tests/test_ground_truth.py
```
