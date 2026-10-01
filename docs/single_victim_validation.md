# Evidência da validação da Etapa 3

Execução real sequencial: três cenários de 30 segundos, porta 8080, seed 42.
Os parâmetros de RPS/workload/pools/timeouts herdados foram preservados.
Captura real disponível; nenhum pacote sintético foi usado.

| Cenário | Status | Métricas | Tentativas | Respostas benignas | Respostas atacante | Pacotes |
|---|---|---:|---:|---:|---:|---:|
| A | completed | 30 | 1141 | 1133 | 0 | 9976 |
| B | completed | 30 | 395 | 0 | 377 | 3647 |
| C | completed | 30 | 1536 | 1129 | 381 | 13532 |

Todas as 90 métricas: `num_instances=1`, `decision=NO_ACTION`.
Em cada cenário: 61 consultas de integridade confirmaram o mesmo ID running.
Os IDs diferem entre cenários porque cada execução prepara sua própria vítima.
393 tentativas benignas no cenário C começaram durante o evento e permaneceram benignas.
Todas as observações foram conferidas contra os intervalos efetivos de attack_events.csv.
Todos os 27.155 pacotes capturados têm classe unknown.
Falhas HTTP reais continuam registradas: A=8, B=18, C=26 tentativas sem outcome=response.
Uma tentativa sem resposta bem-sucedida não invalida por si só a integridade Docker.

## Configuração efetiva C

```json
{
  "id": "single_victim_C",
  "duration_seconds": 30,
  "seed": 42,
  "normal_traffic": {
    "clients": 4,
    "rate": 10,
    "endpoint": "/",
    "work_units": 10,
    "sleep_seconds": 0.0,
    "max_concurrent_sends": 64,
    "request_timeout_seconds": 2.0
  },
  "attack": {
    "enabled": true,
    "profile": "continuous",
    "attackers": 4,
    "rate": 10,
    "start_seconds": 10,
    "duration_seconds": 10,
    "endpoint": "/",
    "work_units": 5000,
    "sleep_seconds": 0.0,
    "max_concurrent_sends": 64,
    "request_timeout_seconds": 2.0,
    "burst": null
  },
  "infrastructure": {
    "initial_instances": 1,
    "min_instances": 1,
    "max_instances": 1,
    "cost_per_instance_per_hour": 0.02
  },
  "autoscaler": {
    "enabled": false,
    "scale_up_threshold": 60.0,
    "scale_down_threshold": 25.0,
    "cooldown_seconds": 20
  },
  "server": {
    "process_pool_workers": 2,
    "default_work_units": 1000000,
    "default_sleep_seconds": 0.0
  },
  "monitoring": {
    "interval_seconds": 1,
    "stats_poll_interval_seconds": 1.0,
    "history_seconds": 30.0
  }
}
```

## Status das três execuções

### Cenário A

```json
{
  "schema_version": 1,
  "experiment_id": "single_victim_A",
  "run_id": "ab850409aa924f5f8819ccf4db9deb24",
  "experiment_start_timestamp": 1790812214.5356991,
  "experiment_start_monotonic": 7813.839549789,
  "status": "completed",
  "end_reason": "simulation_end",
  "producers_drained": true,
  "errors": [],
  "topology_integrity": {
    "expected_victim_id": "827a72cc96e41c68c66d1c0ad33df0a6c07aef292e94f2b79cfc9c1de9e8e9fb",
    "verified_victim_ids": [
      "827a72cc96e41c68c66d1c0ad33df0a6c07aef292e94f2b79cfc9c1de9e8e9fb"
    ],
    "checks": 61,
    "last_verified_elapsed_seconds": 30.00229212300019
  }
}
```

### Cenário B

```json
{
  "schema_version": 1,
  "experiment_id": "single_victim_B",
  "run_id": "35d43144d2d8401fa693c177df450399",
  "experiment_start_timestamp": 1790812248.5184777,
  "experiment_start_monotonic": 7847.822329184,
  "status": "completed",
  "end_reason": "simulation_end",
  "producers_drained": true,
  "errors": [],
  "topology_integrity": {
    "expected_victim_id": "19b640f3503c0734544a6587c53e41818ab1aaf475abe94bf722aafe81f7530b",
    "verified_victim_ids": [
      "19b640f3503c0734544a6587c53e41818ab1aaf475abe94bf722aafe81f7530b"
    ],
    "checks": 61,
    "last_verified_elapsed_seconds": 30.00332110399995
  }
}
```

### Cenário C

```json
{
  "schema_version": 1,
  "experiment_id": "single_victim_C",
  "run_id": "f42512f9d7ef4355997426c0d594f48d",
  "experiment_start_timestamp": 1790812282.748091,
  "experiment_start_monotonic": 7882.051942117,
  "status": "completed",
  "end_reason": "simulation_end",
  "producers_drained": true,
  "errors": [],
  "topology_integrity": {
    "expected_victim_id": "5855ca2e4201676c90e544ccb15f41919d37c401513beffe0d73122b8725bf79",
    "verified_victim_ids": [
      "5855ca2e4201676c90e544ccb15f41919d37c401513beffe0d73122b8725bf79"
    ],
    "checks": 61,
    "last_verified_elapsed_seconds": 30.002497869999388
  }
}
```

## Amostras reais C

request_log_run.csv

```csv
run_id,request_id,generator,worker_id,target_url,timestamp,elapsed_seconds,end_timestamp,end_elapsed_seconds,duration_ms,traffic_class,attack_active,attack_id,event_id,active_event_ids,http_status,outcome,error_type
f42512f9d7ef4355997426c0d594f48d,request_000000001,normal,0,http://localhost:8080/?work=10&sleep=0.0,1790812282.7626638,0.01457521199972689,1790812282.892644,0.14455549499962217,129.98028299989528,benign,0,,,[],200,response,
f42512f9d7ef4355997426c0d594f48d,request_000000356,normal,3,http://localhost:8080/?work=10&sleep=0.0,1790812292.7809799,10.032891760999519,1790812292.8338342,10.08574629099985,52.85453000033158,benign,1,,,"[""event_001""]",200,response,
f42512f9d7ef4355997426c0d594f48d,request_000000354,attack,2,http://localhost:8080/?work=5000&sleep=0.0,1790812292.7586846,10.010596215999612,1790812292.7690055,10.020916867999404,10.320651999791153,attack,1,attack_001,event_001,"[""event_001""]",200,response,
```

attack_events_run.csv

```csv
schema_version,experiment_id,run_id,experiment_start_timestamp,experiment_start_monotonic,attack_id,event_id,profile,scheduled_start_seconds,scheduled_end_seconds,activation_requested_seconds,actual_start_seconds,stop_requested_seconds,actual_end_seconds,last_request_start_seconds,drained_end_seconds,status,end_reason
1,single_victim_C,f42512f9d7ef4355997426c0d594f48d,1790812282.748091,7882.051942117,attack_001,event_001,continuous,10,20,10.004246943999533,10.005558637999457,20.003950468999392,20.003953151999667,19.9656041749995,21.815935083000113,completed,scheduled_end
```

metrics_run.csv

```csv
run_id,timestamp,elapsed_seconds,elapsed_time_s,num_instances,average_cpu_percent,mem_usage,avg_rtt_ms,decision,active_containers_names,attack_active,active_event_ids,host_cpu_percent
f42512f9d7ef4355997426c0d594f48d,1790812282.7749028,0.026813901999958034,0.03,1,0.0,0.0,0.0,NO_ACTION,,0,[],7.43
f42512f9d7ef4355997426c0d594f48d,1790812292.7652042,10.017115382000156,10.02,1,3.4,24.74,11.95,NO_ACTION,single_victim_validation_da2f2a11_1,1,"[""event_001""]",3.37
```

traffic_capture.csv

```csv
run_id,timestamp,elapsed_seconds,src_ip,src_port,dst_ip,dst_port,packet_length,traffic_class,attack_active,active_event_ids
f42512f9d7ef4355997426c0d594f48d,1790812292.755113,10.0070219039917,127.0.0.1,49240,127.0.0.1,8080,0,unknown,1,"[""event_001""]"
```

## Testes e artefatos

29 testes automatizados passaram, incluindo a suíte das Etapas 1 e 2.
Teste de falha: vítima mock com status exited resulta em incomplete/error e causa explícita;
erro de API e desaparecimento/identidade alterada também falham sem assumir saúde.
O teste do loop verifica start_instance chamado somente uma vez no setup e stop_instance nunca chamado,
mesmo com CPU mock alternando 0 e 1000%. Não há substituição da vítima.
As verificações são periódicas; não constituem prova de disponibilidade contínua nem health check HTTP.

Artefatos completos desta validação local: `/tmp/edos-stage3-validation-real/{A,B,C}/`.
Cada pasta contém effective_config.json, metrics_run.csv, request_log_run.csv, attack_events_run.csv,
run_status_run.json, traffic_capture.csv, rtt_log.csv e os dois summaries legados.
Os CSVs científicos mantêm os schemas da Etapa 2; somente run_status ganhou topology_integrity.
Os artefatos em /tmp são temporários; este documento retém amostras e evidência resumida.
Nenhum resultado histórico foi alterado. Nenhum commit foi feito.
