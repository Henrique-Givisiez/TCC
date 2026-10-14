# Etapa 6 — operações da aplicação vítima

O cliente escolhe uma operação. A vítima define o número de iterações de CPU,
independentemente da query e dos defaults legados de ambiente. A arquitetura
permanece `sources → edos_sources → NGINX → edos_network → vítima`.

## Inspeção do baseline

`simulator/app/simple_server.py` atendia GET em qualquer path, interpretando
`work` e `sleep` da query. Na ausência desses parâmetros, usava `WORK_UNITS`
e `PROCESSING_TIME`, propagados por `docker_manager.start_instance` a partir de
`ServerConfig`. `_burn_cpu` executava operações matemáticas em um loop com esse
número de iterações, dentro do mesmo `ProcessPoolExecutor` persistente. O handler
aguardava o resultado e eventualmente dormia. HTTP/1.1, Content-Length e o prefixo
`host=` da resposta permitem keep-alive e correlação com o backend.

`normal_traffic.py` e `traffic_injectorV0.py` construíam
`base_url + endpoint + ?work=...&sleep=...`. Em modo proxy, a base é exclusivamente
`service_endpoint`; no modo histórico é obtida do seletor existente.
`NormalTrafficConfig`/`AttackConfig`, os overrides da CLI e os manifests usados por
`source_runner.py` carregam os parâmetros legados. Scripts históricos como
`run_experiments.py`, `run_experiments_normal.py`, `run_experiments_combined.py`,
`wedos_combined_grid.py` e os grids WU dependem deles.

Dependências explícitas incluem `tests/test_experiment_config.py`,
`tests/test_http_proxy.py` e `experiments/validate_proxy_protocol.py` (path arbitrário,
query codificada e resposta com `work=17`). `HttpProxy.start` usa `work=0&sleep=0`
para readiness; `experiments/source_network_audit.py` usa a mesma operação para
auditar interfaces e isolamento. Os validadores das Etapas 3–5 dependem da mesma
infraestrutura, dos schemas, das respostas identificáveis e do mecanismo legado.

Remover indiscriminadamente a query, proibir paths arbitrários ou mudar o prefixo
da resposta quebraria essas verificações e as execuções históricas. Alterar pools,
workers ou o momento de registrar requests também poderia modificar a geração e
o ground truth. Nenhuma dessas mudanças faz parte da Etapa 6.

## Implementação mínima

Arquivos alterados: `simulator/app/simple_server.py`,
`simulator/service_destination.py`, `simulator/normal_traffic.py`,
`simulator/traffic_injectorV0.py`, `simulator/experiment_config.py` (comentários),
`experiments/configs/application_operations.json`,
`experiments/validate_application_operations.py`, `tests/test_application_operations.py`,
`README.md` e este documento. Não há alteração no orquestrador, lifecycle dos
sources/proxy, captura, ground truth ou configurações históricas.

| Path exato | Iterações de CPU definidas na vítima | Sleep |
| --- | ---: | ---: |
| `/light` | 10.000 | 0 |
| `/medium` | 100.000 | 0 |
| `/expensive` | 1.000.000 | 0 |

A tabela `OPERATION_WORK_UNITS` fica exclusivamente em
`simulator/app/simple_server.py`. `request_workload` seleciona o custo pelo path
antes de interpretar qualquer query ou default de ambiente. `work` e `sleep`,
inclusive valores inválidos, são ignorados nesses três paths. O kernel matemático,
o pool persistente e o protocolo HTTP permanecem os mesmos. São quantidades fixas
de trabalho, não promessas de tempo de execução.

Os geradores reutilizam o campo `endpoint` existente. `request_url`, em
`service_destination.py`, envia somente o path para essas operações; conhece os
nomes públicos, sem importar a tabela de custos da vítima. Não há novo modo de
seleção de operação, alteração de seed/Poisson ou política temporal de ataque.

`experiments/configs/application_operations.json` omite `work_units` e
`sleep_seconds` dos clientes. Usa `/light` para benignos e `/expensive` para o
ataque contínuo já existente, com 8 segundos de duração e seed 42. Os campos
legados ainda aparecem com seus defaults na configuração efetiva e nos manifests
por compatibilidade com o schema anterior; são inertes nesses paths e não
representam nem determinam os custos das operações novas. Os defaults do servidor
também só se aplicam ao fluxo legado.

Os demais paths mantêm a semântica anterior. Em particular, `/expensive/` é um
path legado, não um alias de `/expensive`. O acesso legado continua disponível
via proxy; a restrição de custo é garantida nas três operações novas, não em
toda a superfície HTTP histórica. Uma futura retirada do legado precisa ser
decidida separadamente, após avaliar os consumidores históricos.

## Observabilidade e ground truth

Não foram alterados schemas ou mecanismos de classificação. `request_log.csv`
e os journals locais já registram `target_url`; `proxy_access.log` registra a
linha de request com path/query, tempo da requisição, upstream e request ID.
`routing_evidence.jsonl` já guarda a resposta e permite auditar o custo executado.
Não foi criado um novo log de operações.

`traffic_class` continua dependendo da origem; uma requisição benigna para
`/expensive` continua benigna. `attack_active` depende do intervalo efetivo do
evento. `actual_start` continua ligado à primeira tentativa, `actual_end` ao fim
da emissão e `drained_end` à conclusão das tentativas em voo. A classificação de
pacotes permanece `unknown`. Nenhum detector ou módulo de análise é importado
pela geração.

## Reprodução da validação

O build histórico reutiliza imagens existentes. Reconstrua ambas antes de validar
mudanças de código; não é necessário alterar a política global de build:

```bash
docker build -t edos_target_app:latest .
docker build -f docker/Dockerfile.sources -t edos_sources:stage5 .
.venv/bin/python -B -m unittest discover -s tests -p test_application_operations.py -v
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B -m experiments.validate_application_operations --output experiment_results/stage6-validation
```

Escolha um diretório de saída novo a cada repetição. Execute os validadores
sequencialmente, pois compartilham a porta do serviço. A configuração nova também
pode ser usada diretamente no orquestrador; o validador isola os artefatos por run.

O validador executa três ensaios de 8 segundos, um por operação, com quatro sources
benignos e quatro de ataque, 2 RPS por source e janela contínua entre 2 e 6 segundos.
Ambas as classes usam a mesma operação em cada ensaio, para demonstrar independência
entre classe e custo. Cada classe preserva o orçamento agregado de 64 send workers,
distribuído em 16 por source. Os três ensaios usam a mesma seed.

No ensaio light, 12 probes operacionais são enviados de um source existente via
`http://edos_service:80`, com queries ausentes, `work=0&sleep=99`,
`work=999999999999` e valores inválidos. Eles têm phase `stage6_validation`,
sem request ID científico, e são preservados em `query_probes.json`, no access log
e na captura. Não são incluídos no CSV de tentativas dos geradores. Esses probes
adicionam carga ao ensaio light; CPU/latência são demonstrações de diferenciação,
não uma calibração rigorosa de desempenho.

`validate_source_containers.validate` é reutilizado sem alteração para verificar
IDs, quotas, redes, relógios, captura bruta, isolamento, correlação com upstream,
limites efetivos do evento, drain e cleanup. As verificações adicionais exigem
URLs sem query, HTTP 200, o path correto no NGINX e o custo correto na resposta.
Não há asserts de latência absoluta nem features temporais novas.

## Resultados observados

Os três ensaios terminaram `completed`, com 88 tentativas cada (55 benignas e 33
de ataque), todas bem-sucedidas e correlacionadas com NGINX/vítima. Foram observados
oito IPs de sources, nenhuma rota direta à vítima, nenhuma repetição de descrição
de pacote na captura selecionada e nenhum erro de transporte. Os 12 probes
confirmaram os custos fixos, mesmo com query inválida ou arbitrariamente grande.

| Operação | Mediana da requisição (ms) | Média CPU vítima (%) | Pacotes CSV/brutos |
| --- | ---: | ---: | ---: |
| light | 7,82 | 5,55 | 516/516 |
| medium | 30,14 | 27,77 | 419/419 |
| expensive | 227,10 | 131,06 | 555/555 |

CPU é a métrica Docker existente e pode superar 100% quando mais de um núcleo é
usado. Os valores dependem da máquina, concorrência, inicialização do pool e
carga do host. As iterações fixas e os streams RNG são reproduzíveis; durações e
ordenação das threads não são garantidas.

Artefatos: `experiment_results/stage6-validation/{light,medium,expensive}/`,
com `validation_summary.json` no diretório pai. São ensaios de validação, não
um dataset definitivo.

## Testes e regressões

Os seis testes novos em `tests/test_application_operations.py` verificam a tabela,
independência de queries/env, submissão ao pool sem sleep, HTTP/Content-Length,
compatibilidade query/env/catch-all, configuração sem custos explícitos,
ambos os geradores com seed preservada e sem seletor de backend, além de classe
por origem e drain do ground truth com operação compartilhada.

A suíte completa executou 52 testes: 51 passaram. A única falha,
`ConfigurationTests.test_default_and_roundtrip`, já ocorre no HEAD anterior:
`experiments/configs/default.json` usa `attack.rate=30`, enquanto `AttackConfig`
usa 10. Uma cópia limpa via `git archive HEAD` executou 46 testes, com 45 passando
e a mesma falha. Os valores históricos foram preservados.

Regressões executadas sequencialmente:

- Etapa 3: A/B/C `completed`, sem erros; 1.141, 395 e 1.536 tentativas,
  respectivamente. Identidade fixa da vítima e ground truth verificados.
- Etapa 4: A/B/C e o caso técnico preexistente `completed`; a parada real do proxy
  produziu `incomplete`, como esperado, sem recuperação/fallback. Os casos
  científicos mantiveram uma vítima; as duas vítimas pertencem somente ao teste
  técnico já existente, sem implementação de um novo cenário.
- Protocolo legado: dez requests HTTP/1.1 com path/query preservados,
  `work=17&sleep=0.001`, zero SYNs novos nas conexões upstream já estabelecidas
  e zero retries. Após parar um backend, respostas `[504, 200, 504, 200]`, sem
  retry para o outro backend, conforme o contrato do teste técnico anterior.
- Etapa 5: A/B/C `completed`, com 1.135, 395 e 1.529 tentativas, respectivamente,
  sem erros de transporte. Quotas, oito IPs distintos no cenário combinado,
  isolamento, captura e ground truth passaram. A parada real do NGINX produziu
  `incomplete`, 240 tentativas e 45 erros de transporte, com produtores drenados
  e nenhuma rota direta/fallback. Os validadores encerraram com exit code zero.

Os artefatos das regressões estão em
`experiment_results/stage6-regressions/{stage3,stage4,protocol,stage5}/`.
O baseline auditado é o HEAD `d11b57da0de4b19ba42696eb060b76e77b962c0f`.
Os logs da suíte atual e do baseline estão em `stage6-validation/unit_tests.log`
e `stage6-validation/baseline_tests.log`. Nenhuma configuração histórica foi
alterada. A divergência preexistente de defaults é a única falha unitária observada.
Não foram encontradas regressões novas nas verificações executadas. Ao final,
o Docker Engine local reportou zero containers em execução.

## Limites e decisões antes da Etapa 7

Os custos são uma abstração de CPU simples, sem representar uma aplicação web
completa. A separação 1:10:100 é observável neste host; escolher a intensidade
adequada para futuros experimentos exige calibração, considerando taxa, capacidade
do pool e timeout. Não é necessário calibrar pelo tempo absoluto nesta etapa.

Antes da Etapa 7, confirmar a operação cara e os parâmetros de intensidade a usar,
e decidir separadamente como tratar a divergência histórica 30/10 RPS da suíte.
O comportamento temporal de LDoS, features, detectores, mitigação, autoscaling e
datasets finais continuam fora desta implementação.
