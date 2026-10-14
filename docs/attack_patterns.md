# Etapa 7 — padrões temporais do atacante

## Diagnóstico do baseline

`AttackConfig` controla operação/path, taxa, entidades e janela global.
No host, `main_orchestrator.py` inicia e para o atacante nas iterações de
monitoramento; em containers, `source_runner.py` observa a janela no relógio
compartilhado, aproximadamente a cada 10 ms. A ativação autoriza admissão, mas
não estabelece `actual_start`.

`traffic_injectorV0.http_request_worker` produz em open-loop: constrói a URL,
chama `GroundTruth.admit`, submete ao `ThreadPoolExecutor` e espera um intervalo
exponencial sorteado com `worker_seed(seed, 'attack', índice_global)`. O produtor
não aguarda a resposta. O executor limita concorrência, mas sua fila não tem
limite explícito. `_send_one` registra o início, realiza HTTP via service endpoint
e registra conclusão/erro. NGINX é o único destino operacional dos sources.

O baseline já separava o envio HTTP em uma função, mas o produtor misturava
admissão, construção da URL e controle temporal/RPS. `BurstConfig` já existia,
com `period_seconds`, `duration_seconds` e um campo inativo de jitter, porém os
parâmetros preenchidos eram rejeitados. Não havia scheduler de bursts. O runner
também não reconstruía o objeto aninhado de burst recebido em JSON.

Os testes de configuração, proxy, sources e ground truth dependem da fila
contínua, da distribuição de workers e dos limites de emissão versus conclusão.
As validações anteriores usam um único evento contínuo. Os validadores da Etapa 5
têm contagens de sources fixas; o validador novo deriva as contagens da configuração.
O mecanismo da vítima e os testes das operações da Etapa 6 são independentes do
scheduling do atacante.

## Taxa por entidade e capacidade

**`attack.rate` é RPS nominal por entidade atacante/source, com default 10.**
Esse já era o comportamento do host e dos containers. Quando N atacantes estão
ativos, a taxa nominal agregada é `N × rate`. Quatro sources a 10 RPS representam
40 RPS nominais durante atividade, não 10 RPS agregados. Essa semântica permanece
idêntica nos dois padrões. Não existe `average_rps` na configuração.

Somente `max_concurrent_sends` é um orçamento agregado de workers por classe.
`SourceManager.worker_quotas` permanece intacto: 64 workers e quatro sources
produzem quotas 16/16/16/16; um único source recebe 64. O scheduler não modifica
essa distribuição, os índices RNG, source IDs ou inventário.

No periódico, `rate` representa oportunidades Poisson durante o burst.
Oportunidades sem capacidade disponível são ignoradas imediatamente, antes da
admissão; não há espera por capacidade, compensação ou dívida entre bursts.
A taxa realizada pode diminuir por capacidade e scheduling. Em amostras curtas,
contagens também flutuam pelo processo Poisson: a taxa nominal não é um teto
determinístico de contagens em cada intervalo.

## Desenho adotado

`simulator/attack_patterns.py` contém somente janelas determinísticas:

- `ContinuousFlood`: janela `[start_seconds, end_seconds)`.
- `PeriodicBurst`: janelas `[start + k×period, min(start + k×period + burst_duration, end))`.

Ambos oferecem `next_window(elapsed)` e `allows(elapsed)`. Não importam HTTP,
RNG, configuração da vítima ou detectores. A âncora de todos os sources é o mesmo
relógio de experimento, com os bursts definidos a partir de `start_seconds`.
O período é início-a-início, sem somar duração do burst ao período.

O contínuo é selecionado explicitamente pela factory, mas conserva seu produtor,
primeiro envio imediato, sequência de intervalos Poisson, admissão antes da fila
e fila histórica. O controle externo da janela também permanece intacto.

O periódico usa o mesmo envio HTTP `_send_one`, com esta política:

1. O produtor espera a janela ativa e sorteia intervalos Poisson, inclusive antes
   da primeira oportunidade de cada burst. Não adiciona um envio obrigatório na
   fronteira do burst, nem executa catch-up após atrasos do scheduler.
2. Uma reserva não bloqueante limita tarefas submetidas ao número de send workers.
   Sem slot, a oportunidade não entra na fila nem no ground truth.
3. A tarefa preserva o deadline do seu burst original. Antes do início observado,
   o logger revalida deadline, janela global, padrão e parada.
4. O predicate opcional `admit_if` é avaliado sob o lock do evento, usando a mesma
   amostra de relógio que registra o início. Só então admissão e início ocorrem
   juntos. Não há intervalo entre verificar uma amostra antiga e registrar outra.
5. Se expirar, não recebe request ID, não escreve tentativa falha/descartada,
   não chama HTTP e não é reaproveitada no burst seguinte.
6. A reserva é liberada na conclusão da tarefa, inclusive em falhas. HTTP já
   iniciado continua até seu retorno/timeout normal.

O callback temporal está no wrapper de scheduling e no ponto genérico de
admissão/início; `_send_one` não conhece período, burst ou próximo envio.
Os inícios continuam sendo os observados pelo cliente antes de `session.get`,
como no baseline; não representam o primeiro byte na rede. O custo normal de
instrumentação após a amostra não foi removido nem convertido em timestamp sintético.

## Configuração

Reutilizam-se `attack.profile` e `attack.burst`, sem um segundo campo `pattern`:

```json
{
  "attack": {
    "profile": "periodic_burst",
    "attackers": 1,
    "rate": 10,
    "endpoint": "/expensive",
    "start_seconds": 2,
    "duration_seconds": 11.5,
    "burst": {"duration_seconds": 1, "period_seconds": 3}
  }
}
```

`attack.duration_seconds` é a janela global; `attack.burst.duration_seconds` é
a duração de cada burst. A ausência de profile conserva `continuous`.
Para o contínuo, `burst=null` ou um objeto com campos todos nulos permanecem
compatíveis. Parâmetros de burst preenchidos exigem `periodic_burst`.

Validação antecipada exige período/duração finitos e positivos, duração menor ou
igual ao período, ambos presentes para o periódico. Duração igual ao período
elimina silêncio; isso equivale temporalmente à atividade contínua, mantendo a
política de capacidade do periódico. Jitter não é implementado e qualquer valor
não nulo é rejeitado. RandomBurst/CustomPattern também são rejeitados.

`experiments/configs/periodic_burst.json` usa sources em containers, uma vítima,
NGINX, autoscaling desativado e operações sem `work`. Os valores temporais são
somente de validação. Operação e padrão podem ser combinados independentemente.

## Ground truth e observabilidade

Há um único evento `attack_001/event_001`, com `profile` identificando o padrão.
Não foram adicionadas colunas, `burst_active`, eventos por burst ou novas classes.

- `actual_start`: primeira tentativa iniciada, não ativação nem oportunidade.
- `actual_end`: admissão global encerrada e todas as admitidas iniciadas.
- `drained_end`: última conclusão, calculada separadamente.
- `attack_active`: intervalo efetivo global `[actual_start, actual_end)`, incluindo
  silêncios. Não fica 1 antes da primeira tentativa nem equivale automaticamente
  à janela planejada.
- `traffic_class`: origem causal, independente da operação e do estado do burst.

O evento não é fechado nas fronteiras dos bursts. Por isso, mesmo se o último
burst acabar em 12 s, a certificação de emissão pode ocorrer na parada global
em 13,5 s. `drained_end` pode anteceder `actual_end` quando as últimas requests
terminam antes dessa parada; não se força igualdade ou ordem inversa.

O hook de journal reutiliza o registro `admission` já existente. No periódico,
suas amostras coincidem com `request_begin`; a auditoria existente continua
verificando `admitted - abandoned == started`. O contador de oportunidades não
foi instrumentado: logs permitem contar admissões e inícios, não todas as
oportunidades que expiraram ou encontraram capacidade ocupada.

## Arquivos modificados

- `simulator/attack_patterns.py`: janelas/factory.
- `simulator/experiment_config.py`: validação do padrão e comentário sobre taxa.
- `simulator/traffic_injectorV0.py`: scheduling periódico, reservas e HTTP compartilhado.
- `simulator/ground_truth.py`, `request_logger.py`, `source_journal.py`: admissão
  condicional junto ao início observado, sem mudança de schema.
- `simulator/source_runner.py`: reconstrução de `BurstConfig` do manifesto.
- `docker/Dockerfile.sources`: inclusão do novo módulo na imagem existente.
- `experiments/configs/periodic_burst.json`, `experiments/validate_attack_patterns.py`.
- `tests/test_attack_patterns.py`, `README.md` e este documento.

Vítima, NGINX, isolamento, captura, source inventory, distribuição de workers,
gerador benigno, detectores e configurações históricas não foram modificados.

## Testes e reprodução

O baseline executou 52 testes, todos passando. Foram acrescentados 13 testes,
com múltiplos casos de fronteira, config e relógio falso. A suíte atual passou
65/65. A cobertura inclui início-a-início, silêncio, clipping global, duty cycle
100%, rejeição de inválidos/jitter, combinações de operações, taxa por source,
quotas reais de manifestos, capacidade esgotada, slot liberado em erro, tarefa
atrasada até o próximo burst sem admissão, gate na amostra de início, conclusão
no silêncio e depois do fim global, e scheduler Poisson com relógio falso.
Os testes históricos de fila contínua, seed, proxy e ground truth continuam passando.

```bash
docker build -f docker/Dockerfile.sources -t edos_sources:stage5 .
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B -m experiments.validate_attack_patterns --output experiment_results/stage7-validation
```

Use diretório de saída novo e execute ensaios sequencialmente. A vítima não foi
alterada; usa a imagem validada na Etapa 6. O tag histórico dos sources permanece
o mesmo, e os artefatos registram o image ID efetivamente utilizado.

## Validação temporal observada

Quatro ensaios de 15 segundos, seed 42, global `[2, 13.5)`, quatro sources benignos
a 2 RPS com `/light`, uma vítima e NGINX. O periódico tem bursts de 1 segundo,
período de 3 segundos e 4 segundos totais de janelas válidas. O contínuo tem
11,5 segundos válidos. Todos terminaram `completed`, sem erros de transporte,
com captura bruta/CSV, isolamento, correlação de upstream e ground truth auditados.

| Caso | Atacantes × RPS nominal | Operação | Send workers agregados | Admissões/inícios | RPS realizado por segundo válido |
| --- | --- | --- | ---: | ---: | ---: |
| contínuo | 1 × 10 | light | 64 | 105/105 | 9,13 |
| periódico | 1 × 10 | expensive | 64 | 25/25 | 6,25 |
| múltiplos | 4 × 10 | light | 64 (16 por source) | 140/140 | 35,00 agregados |
| capacidade | 1 × 10 | expensive | 1 | 13/13 | 3,25 |

No periódico, a expectativa nominal é 40 oportunidades em 4 segundos ativos;
isso não é uma contagem observada. O número real de oportunidades não está
disponível nos logs. Os 25 inícios com seed 42 ilustram a flutuação em um ensaio
curto, não uma calibração estatística definitiva. No caso com quatro sources,
os inícios individuais foram 25, 40, 41 e 34; não houve divisão da taxa por quatro.
O índice/stream do primeiro atacante permaneceu o mesmo.

Todos os timestamps de início do ensaio periódico, em segundos relativos à âncora:

| Burst válido | Inícios observados | Conclusões no silêncio |
| --- | --- | ---: |
| [2, 3) | 2,092; 2,217; 2,242; 2,307; 2,314; 2,410; 2,444; 2,517; 2,712 | 0 |
| [5, 6) | 5,386; 5,457; 5,624; 5,802; 5,907 | 1 |
| [8, 9) | 8,471; 8,628; 8,667 | 0 |
| [11, 12) | 11,035; 11,385; 11,392; 11,398; 11,407; 11,424; 11,684; 11,860 | 1 |

Zero inícios no silêncio ou fora da janela global. As duas conclusões no silêncio
foram `5.907317 → 6.066415` e `11.860059 → 12.016332`. Essas requests não foram
canceladas. Houve 52 observações benignas nos silêncios com `attack_active=1`
(53 no caso múltiplo e 52 no caso de capacidade), confirmando o evento global.
No ensaio principal, `actual_end=13.507452` e `drained_end=12.016332`, preservando
a diferença entre fechamento de emissão e última conclusão.

Não houve admissão abandonada nem pendência admitida transportada entre bursts:
no periódico, admissões e inícios usam exatamente as mesmas amostras. O ensaio
limitado a um worker reduziu inícios para 13, sem compensar depois. O teste com
executor controlado demonstrou adicionalmente que uma oportunidade do primeiro
burst executada apenas no segundo é ignorada antes da admissão.

Artefatos em `experiment_results/stage7-validation/`: `validation_summary.json`,
CSV/journals/capturas por caso e `timestamps.md` com inícios completos. São
evidências de validação, sem camada formal de features ou dataset definitivo.

## Regressões

Todas as baterias encerraram com exit code zero, sem modificar os validadores
históricos:

| Bateria | Resultados |
| --- | --- |
| Etapa 3 | A/B/C `completed`: 1.141 / 395 / 1.537 tentativas |
| Etapa 4 | A/B/C e técnico `completed`; falha real do NGINX `incomplete`, como esperado |
| Protocolo | HTTP/1.1, URI/query e keep-alive preservados; zero retries; falha de backend `[504, 200, 504, 200]` |
| Etapa 5 | A/B/C `completed`: 1.136 / 395 / 1.528 tentativas; falha real do proxy `incomplete` |
| Etapa 6 | light/medium/expensive `completed`: 89 / 88 / 89 tentativas; todos os probes de custo/query passaram |

As medianas da regressão da Etapa 6 foram 8,33 / 26,57 / 278,20 ms. As contagens
realizadas variam um pouco com scheduling físico; o comportamento contínuo,
streams RNG e semânticas foram preservados. A configuração default e os perfis
históricos permaneceram intactos. O caso técnico com dois backends pertence
somente à regressão preexistente da Etapa 4, não a um novo cenário científico.

Inventário, quotas, relógios, isolamento source → proxy → vítima, correlações,
captura e ground truth passaram. A auditoria adicional dos quatro casos da
Etapa 7 verificou os 214 / 134 / 249 / 122 registros RTT contra seus request IDs,
run IDs e classes. Ao final, o Docker Engine reportou zero containers em execução.

Artefatos em `experiment_results/stage7-regressions/`, com
`regression_status.json` e os relatórios originais por etapa. Logs unitários e do
baseline em `stage7-validation/unit_tests.log` e `baseline_tests.log`.
O HEAD usado como baseline foi `694bb4f6d9e8cece28f49ca9d789212f4815540a`.

## Limitações e próximas etapas

O scheduling planejado dos bursts é determinístico; timestamps realizados
dependem do scheduler do SO, instrumentação, concorrência e capacidade. Não se
promete igualdade exata de contagens ou tempos entre execuções físicas.

No contínuo, preserva-se a fila histórica: tentativas admitidas antes da parada
podem começar depois dela sob saturação. A política estrita de expiração e ausência
de backlog foi adicionada somente ao periódico, como decidido. A disponibilidade
de slots é local ao source, sem empréstimo entre quotas.

A seleção de amostras RTT das métricas existentes continua baseada na janela
global. Um intervalo silencioso pode ter RTT agregado 0 por ausência de amostras
atacantes; isso não significa latência zero. Os registros individuais de request
e RTT permanecem disponíveis para a análise posterior. Essa seleção histórica
não foi redefinida nesta etapa.

Requests periódicas válidas podem concluir depois do fim global; isso foi
exercitado deterministicamente no teste, com início 11,9, fechamento 12,5 e
conclusão 14 s. Os ensaios físicos mostraram conclusões no silêncio, mas não
precisaram de conclusões além do fim global para terminar corretamente.

Os parâmetros deste ensaio não são valores científicos definitivos. Antes de
experimentos futuros, escolher intensidade, duty cycle e duração adequados à
capacidade observada, sem confundir RPS por entidade com taxa agregada.
RandomBurst, CustomPattern, jitter, sincronização sofisticada, intensidade variável,
features, detectores, dataset final, autoscaling e mitigação permanecem fora do escopo.
