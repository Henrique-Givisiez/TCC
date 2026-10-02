# Validação da Etapa 5

Execução no Ubuntu nativo, contexto `default`. CLI, SDK padrão e socket fixo
apontaram para o daemon `177c5506-8b67-45e1-ab1c-acd019f2994e`, Ubuntu 24.04.1,
kernel `6.11.0-29-generic`, igual ao Python host. Artefatos locais em
`experiment_results/stage5-final/`; esse diretório é ignorado pelo Git.
Nenhum commit foi feito nesta implementação.

## Cenários finais

A/B/C usam 30 s, seed 42, uma vítima, proxy ligado, autoscaling desligado.
Ataque contínuo de B/C entre 10 e 20 s. Taxa por entidade 10 req/s, workload
benigno 10 e atacante 5000, timeout 2 s. Cada classe ativa mantém orçamento 64,
dividido explicitamente em 16 workers por origem. Não há limite CPU/memória novo.

| Caso | Sources benignos/atacantes | Requests benignas/atacantes | Respostas bem-sucedidas | Erros transporte | Pacotes CSV/PCAP | Status |
|---|---:|---:|---:|---:|---:|---|
| A | 4/0 | 1134/0 | 1134 | 0 | 5312/5312 | completed |
| B | 0/4 | 0/395 | 395 | 0 | 1909/1909 | completed |
| C | 4/4 | 1133/395 | 1528 | 0 | 7404/7404 | completed |
| Proxy interrompido | 4/4 | 132/108 | 194 | 46 | 1104/1104 | incomplete |

Todas as tentativas finalizadas têm IDs únicos e destinos exclusivamente
`http://edos_service:80/...`. Todas as respostas bem-sucedidas foram correlacionadas
request log → access log/remote_addr → backend inventory → hostname existente
na resposta. Nenhuma requisição de readiness/auditoria foi incorporada aos requests
científicos. Todas as métricas mantiveram `num_instances=1`, `NO_ACTION` e somente
nomes de vítimas. Ground truth, campos e schemas científicos foram preservados.

O cenário de falha configura 10 s e ataque entre 1 e 9 s. O runner aplica
`container.stop(timeout=1)` ao proxy após 3.1 s. O controle detecta estado `exited`,
registra incompletude, fecha admissão e drena os sources. Os erros continuam no
endpoint único, sem recuperação ou fallback. Captura na bridge permanece íntegra,
com zero descartes; `run_status` contém somente os erros esperados do proxy.

## Inventário e isolamento

Mapa observado em C, válido para o seu `run_id`:

| IP | source_id lógico | traffic_class |
|---|---|---|
| 172.20.0.3 | normal_1 | benign |
| 172.20.0.4 | normal_2 | benign |
| 172.20.0.5 | normal_3 | benign |
| 172.20.0.6 | normal_4 | benign |
| 172.20.0.7 | attack_1 | attack |
| 172.20.0.8 | attack_2 | attack |
| 172.20.0.9 | attack_3 | attack |
| 172.20.0.10 | attack_4 | attack |

O proxy frontend foi `172.20.0.2:80`, na rede `edos_sources` (`172.20.0.0/16`).
Backend permanece na `edos_network` (`172.19.0.0/16`). Vítimas não publicam portas;
somente NGINX publica `127.0.0.1:8080`. Esses IPs não definem identidade científica:
B reutilizou endereços que A havia usado para benignos, agora para atacantes.
O inventário completo registra containers, hostnames, imagem, budgets e status.

Cada source acessou o proxy. Em todos os sources dos quatro casos, probes técnicos
por nome da vítima falharam com `gaierror`, e por IP com `TimeoutError`. Os sources
estavam conectados somente a `edos_sources`; nenhum à rede backend. Manifestos
não contêm nomes/IPs das vítimas. Os probes recebem endereços apenas no processo
auxiliar de diagnóstico, antes da janela científica. O isolamento foi medido neste
host, sem mudar globalmente firewall ou permissões.

## Captura experimental

Comparação simultânea em C, antes da janela, com cinco requests de cada source:

| Interface | Pacotes | Descrições repetidas | IPs de origens / respostas | Fora do segmento |
|---|---:|---:|---:|---:|
| lo | 0 | 0 | 0/0 | 0 |
| br-7e2468afd861 | 240 | 0 | 8/8 | 0 |
| vethd9722a7 | 240 | 0 | 8/8 | 0 |
| any | 696 | 461 | 8/8 | 0 |

A bridge foi escolhida após essas comparações e uma falha real preliminar em que
a veth desapareceu ao parar o proxy. A bridge preserva cobertura sem duplicação
e continua disponível após a falha. O nome é descoberto no inventário de rede,
não codificado como constante. Nenhuma saída de `any` integra o CSV oficial.

Filtro final desta execução:

```text
tcp and ((dst host 172.20.0.2 and dst port 80) or (src host 172.20.0.2 and src port 80))
```

Todos os pacotes CSV pertencem à tupla source↔proxy; nenhum a proxy↔victim.
IPs de origem observados correspondem exatamente ao inventário, com cobertura
nos dois sentidos. O CSV continua com `traffic_class=unknown`. Em todos os casos,
a captura bruta integral teve zero descrições repetidas e a mesma quantidade de
pacotes do CSV. Os dois processos tcpdump reportaram zero descartes pelo kernel.
O comparador inclui tupla, sequência/ACK TCP absoluta, flags, opções TS e tamanho;
não remove retransmissões nem deduplica o dataset.

A comparação preliminar identificou bufferização em captura curta e um erro de
descoberta da interface. Foram corrigidos antes da bateria final. As evidências
preliminares, incluindo a veth desaparecida e a correção da finalização temporal
de capturas parciais, permanecem em `experiment_results/stage5-development/`.

## Ground truth e relógios

Quatro amostras por container, antes da liberação, demonstraram namespace de tempo
`time:[4026531834]` igual ao host e valor monotônico remoto entre os valores locais
anterior/posterior. C e falha verificaram os oito containers; A/B, quatro cada.
A reconstrução utiliza uma única âncora compartilhada e um único `run_id`.

| Evento | actual_start | actual_end | drained_end |
|---|---:|---:|---:|
| B | 10.008971362 | 20.005101503 | 20.030536275 |
| C | 10.012609308 | 20.005479465 | 20.026529458 |

Inícios/fins são auditados por journals locais, não pelo NGINX. Contagens de
admissão, abandono, início e conclusão foram consistentes em todos os sources.
Nenhuma origem escreveu no CSV científico global. O host reconciliou o contexto
global em requests, métricas e pacotes, inclusive na execução incompleta.
O teste distribuído com tentativa enfileirada após parada certifica emissão em
8.001 s, enquanto a última conclusão ocorre em 100 s. Origem sem certificado de
fechamento impede inventar `actual_end`; ausência de conclusão não vira inatividade.

## Imagens

Sources: `edos_sources:stage5`, executada pelo ID imutável
`sha256:459555985229df012095b50d5ca363ccb06b890429518e63810d0e45d898d725`.
Digest local de configuração da imagem, sem RepoDigest publicado. Base Python
`3.12.10-slim-bookworm@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db`.

Proxy permanece
`nginx:1.28.0-alpine@sha256:30f1c0d78e0ad60901648be663a710bdadf19e4c10ac6782c235200619158284`.
A imagem da vítima permanece a do baseline. Dockerfile e dependências dos sources,
IDs de imagem, inventários e configuração NGINX foram arquivados por execução.

## Regressões

- `python -B -m unittest discover -s tests -q`: **46 testes passaram**;
  inclui 38 anteriores e oito novos, cobrindo orçamento, clock incompatível,
  fila/fim de emissão versus drenagem, origem ausente, captura parcial, journals,
  arquivamento por run_id e saída prematura de source com exit code zero.
- Etapa 3 real A/B/C: completed; 1140/395/1536 requests, zero erros registrados.
- Etapa 4 real A/B/C: completed; 1141/395/1536 requests.
- Etapa 4 técnica com duas vítimas: 351 requests, ambos os hostnames alcançados.
- Etapa 4 falha real: incomplete, com 141 tentativas e 110 respostas.
- Protocolo: HTTP/1.1, URI/query preservados, upstream keep-alive com zero novos
  SYNs backend durante dez requests, falha de backend `[504,200,504,200]`, zero retries.
- Verificação final: contexto/daemons iguais; redes de simulação vazias;
  nenhum container da validação e nenhum tcpdump residual; nenhum novo DENIED
  de recebimento de sinais desde o início das capturas da Etapa 5.

Os quatro containers existentes de outros projetos, criados em 2025, permaneceram
intactos. Não representam resíduos destas execuções. Redes e imagens permanecem
para reutilização; não foram removidas indiscriminadamente.

Artefatos principais: `validation_summary.json`, `execution_environment.json`,
A/B/C/failure, `regression-stage3/`, `regression-stage4/`, `regression-protocol/`.
O comando e resultado dos checks Git estão em `git_diff_check.txt` e
`git_status_short.txt` no mesmo diretório local de resultados.

## Arquivos envolvidos

Novos: `docker/Dockerfile.sources`, `docker/requirements.sources.txt`,
`simulator/source_runner.py`, `source_journal.py`, `source_manager.py`,
`source_aggregate.py`, `source_experiment.py`, `capture_evidence.py`,
`experiments/source_network_audit.py`, `validate_source_containers.py`,
`experiments/configs/container_sources.json`, `tests/test_source_containers.py`
e os dois documentos `container_sources*.md`.

Alterados: `.gitignore`, `README.md`, `experiments/result_archive.py`,
`simulator/config.py`, `experiment_config.py`, `main_orchestrator.py`,
`http_proxy.py`, `service_destination.py`, `request_logger.py`,
`normal_traffic.py`, `traffic_injectorV0.py`, ambos os summary loggers e
`tcpdump_sniffer.py`. O summary logger atacante teve seus finais de linha
normalizados para LF para permitir `git diff --check` sem whitespace novo.

Limitações metodológicas e operacionais estão descritas em
[container_sources.md](container_sources.md): filas independentes, instrumentação,
IPv4/TCP, clocks locais demonstravelmente comparáveis, ausência de recuperação
resistente a crash e isolamento limitado ao ambiente efetivamente testado.
Não foram adicionados LDoS, detectores, autoscaling ou heurísticas por número de IPs.
