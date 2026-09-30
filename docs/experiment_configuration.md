# Etapa 1 — configuração de experimento

A Etapa 2 atualiza ground truth, timestamps e finalização. Veja
[o contrato atual](ground_truth.md); as preservações de labels/captura descritas
abaixo se referem ao estado ao final da Etapa 1. Parâmetros, workloads e Poisson
continuam preservados.

Execute da raiz:

```bash
python3 -m simulator.main_orchestrator --config experiments/configs/default.json
python3 -m simulator.main_orchestrator --config experiments/configs/default.json --print-config
python3 -m unittest discover -s tests
```

O JSON é carregado em dataclasses imutáveis de `simulator/experiment_config.py`.
Os campos omitidos usam os defaults desse módulo; campos desconhecidos, duplicados,
tipos incorretos e valores incoerentes são rejeitados. `default.json` explicita todos
os defaults e o teste verifica igualdade com a representação interna.

A configuração efetiva é validada e impressa antes de acessar Docker. `to_json()` e
`ExperimentConfig.load()` permitem serializar/carregar os mesmos valores. Nenhum
metadata de dataset é criado. `--print-config` funciona sem Docker e sem dependências
externas. Redirecione sua saída para um arquivo se quiser guardar a seed resolvida.

## Parâmetros e defaults

- Experimento: id `default`, duração 180 s, seed nula.
- Normal: 4 clientes, 10 RPS por cliente, endpoint `/`, work 10, sleep 0 s,
  pool compartilhado de envio 64, timeout 2 s.
- Ataque: habilitado, perfil `continuous`, 4 atacantes, 10 RPS por atacante,
  início 20 s, duração 140 s (fim derivado 160 s), endpoint `/`, work 5000,
  sleep 0 s, pool compartilhado 64, timeout 2 s, burst nulo.
- Infraestrutura: inicial 1, mínimo 1, máximo 4, custo fictício 0.02 por instância/hora.
- Autoscaler: habilitado, scale-up > 60%, scale-down < 25%, cooldown 20 s.
- Vítima: pool de 2 processos; defaults para requisições sem query: work 1000000,
  sleep 0 s. A query da requisição prevalece sobre os defaults da vítima.
- Monitoramento: loop/janela 5 s, polling Docker 1 s, histórico 30 s.

`rate` é sempre por worker. Pools de envio são compartilhados por tipo de tráfego.
`server.process_pool_workers` controla o ProcessPoolExecutor, não limita diretamente
as threads HTTP simultâneas. Docker recebe esse campo e os defaults de workload por
variáveis de ambiente; a aplicação vítima existente já suporta essas variáveis.
Endpoints são caminhos sem query/fragmento; `work` e `sleep` são acrescentados pelos
injetores. A aplicação atual executa o mesmo trabalho em qualquer caminho.

Somente `continuous` é aceito. `burst` pode ser nulo ou um objeto com
`period_seconds`, `duration_seconds`, `jitter_seconds` todos nulos. Valores ativos
são rejeitados: LDoS não foi implementado.

## Aleatoriedade e reprodução

`seed = null`: uma seed inteira de 64 bits é gerada no início da execução e
exibida na configuração efetiva. O arquivo original sozinho não determina a sequência
aleatória.

`seed = inteiro`: a aleatoriedade controlável pode ser reproduzida a partir da
configuração. Uma seed explícita é preservada. SHA-256 de `seed:componente:indice` deriva um gerador
`random.Random` por worker normal/atacante, independente da ordem de scheduling.
A distribuição exponencial/Poisson e o mecanismo open-loop permanecem.
Mesma configuração/seed não garante resultados idênticos: rede, threads, filas,
Docker, carga do host e temporização real continuam introduzindo não determinismo.

Exemplo com seed explícita (42), baseado integralmente no padrão:

```bash
python3 -m simulator.main_orchestrator --config experiments/configs/example_reproducible.json
```

## Compatibilidade

A CLI anterior continua disponível e monta a mesma representação estruturada:
`--rps`, `--attackers`, `--duration`, `--work-units`, `--normal-rps`,
`--normal-clients`, `--normal-work-units`, `--attack-start`, `--pulse-duration`,
`--attack-duration`. Não pode ser combinada com `--config`.

Historicamente `--attack-duration 0` desabilita e qualquer positivo habilita;
**não determina duração**. `--pulse-duration` determina a janela contínua inteira.
Negativos agora são rejeitados. Uma janela habilitada precisa caber na duração total;
para execução curta ajuste a janela ou desabilite o ataque explicitamente.

Runners existentes continuam usando CLI e arquivamento histórico, sem edição de
fonte pelo entrypoint. Runners que dividem taxas por 4 agora explicitam 4 clientes.
Grids, repetições e destinos de arquivamento continuam nos runners; migração completa
para geração de JSON fica para depois. `wedos_rerun_contaminated` consulta o default
estruturado do pool. Aliases históricos de leitura em `simulator/config.py` permitem
imports antigos, mas atribuir a esses nomes não configura o núcleo atual.

## Limites preservados

- Ataque contínuo é avaliado nos ticks; setup Docker não integra a duração.
- Ataque em zero pode adiar início do tráfego normal pela lógica existente.
- Para normal e ataque, `rate > 0` usa o processo Poisson/open-loop existente;
  `rate = 0` não envia requisições; `rate < 0` é inválido. Normal com clientes zero
  também não inicia. Isso não altera o agendamento, os labels ou o perfil contínuo.
- Cooldown conserva a tolerância de 1 s existente e thresholds podem superar 100%,
  pois CPU Docker pode superar 100% em múltiplos núcleos.
- Requisições em voo e parada curta de workers permanecem; não se promete uso repetido
  do orquestrador no mesmo processo nem execução concorrente dos runners.
- Imagem existente pode fazer o build do orquestrador ser pulado.
- Captura conserva interface `any`, filtro, labels e a limitação do intervalo de portas
  quando IDs crescem após ciclos de escala. Nenhum ground truth foi modificado.

Configuração técnica Docker, caminhos CSV/PCAP e compatibilidade de código legado
permanecem em `simulator/config.py`. Timeouts de cleanup, round-robin, fórmulas de
métricas, operação por work unit, protocolo HTTP e formatos CSV são implementação.
`HTTP_REQUEST_TIMEOUT_SECONDS=10` pertence ao legado; o fluxo ativo preserva 2 s.

## Verificação

Testes cobrem defaults, round-trip, seed, valores inválidos, CLI sem Docker,
configurações distintas nos componentes, ambiente Docker e wiring do orquestrador
com Docker/rede/relógio simulados. Não executam ataques reais. O build usa o Dockerfile
existente, que permanece inalterado, assim como a vítima.
