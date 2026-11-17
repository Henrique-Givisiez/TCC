# Capítulo 5 — lote 3: recursos, filas e síntese operacional

Este lote utiliza exclusivamente as 60 execuções **TEST** da campanha
`energy-powersaver-20261109`: 20 blocos completos, com uma execução de cada
cenário por bloco. Nenhum artefato oficial ou dado bruto foi modificado.

| Entrega | PDF ou LaTeX | PNG ou CSV |
|---|---|---|
| F5.2-D — CPU e memória | `figures/f52d_cpu_memoria.pdf` | `figures/f52d_cpu_memoria.png` |
| F5.2-E — filas de espera | `figures/f52e_filas_espera.pdf` | `figures/f52e_filas_espera.png` |
| T5.2-A — síntese operacional | `tables/t52a_indicadores_operacionais.tex` | `tables/t52a_indicadores_operacionais.csv` |

Os arquivos em `processed/` preservam valores por execução e as estatísticas
usadas nas figuras, incluindo Q1 e Q3 não desenhados. `processed/manifest.json`
registra hashes SHA256 das entradas e verificações de cobertura. O LaTeX usa
`booktabs` (`\usepackage{booktabs}` no preâmbulo do Overleaf).

## Proveniência e definições

O plano `experiments/protocols/energy-powersaver-20261109/plan.json`, o
`reports/scientific_campaign_visualization_20261112/inventario_execucoes.csv`
e o manifesto dessa auditoria confirmam campanha, partição, cenário e bloco.
As fases são PRE `[30,150)`, ACTIVE `[150,270)` e POST `[270,390)` segundos.
As linhas são **medianas entre execuções**, calculadas depois do indicador de
cada execução; segundos e requisições individuais não são réplicas.

### F5.2-D — recursos da vítima

- **CPU:** `reports/scientific_campaign_visualization_20261112/processed/docker_<id>.csv`,
  campos `t`, `cpu`, `state`. São snapshots Docker nativos do **contêiner da
  vítima**. Somente `state=valid` entra no cálculo. A aquisição é próxima de
  1 s, mas irregular: há **4 a 6 snapshots válidos por execução e janela de
  5 s** em `[30,390)`. Calcula-se a média aritmética dessas observações em
  cada execução e janela; depois, a mediana entre as 20 execuções. Não há
  ponderação temporal nem interpolação. `t` é o instante de recebimento da
  leitura. A fórmula operacional, em `simulator/cpu_observations.py:delta`, é
  `Δtotal_usage / Δsystem_cpu_usage × online_cpus × 100`. Assim, 100%
  corresponde a aproximadamente **um processador lógico**; o valor não é
  limitado a 100% nem exclusivo dos dois workers.
- **Memória:** `reports/scientific_campaign_visualization_20261112/processed/memory_<id>.csv`,
  campos `t`, `mem`. Sua origem é
  `dataset/raw/infrastructure/simulation_metrics.csv:mem_usage`, filtrado em
  `reports/scientific_campaign_visualization_20261112/scripts/audit.py` por
  `num_instances=1` e `active_containers_names=target_instance_1`.
  `simulator/stats_collector.py:_compute_metrics` calcula
  `max(memory_stats.usage − cache, 0) / 1024²`; a unidade é **MiB** e o
  resultado é arredondado a duas casas na gravação do CSV operacional.
  Há **uma observação por execução e janela de 5 s**; nenhuma série agrega
  outros contêineres. O gráfico liga observações sucessivas para leitura,
  sem criar valores intermediários no arquivo derivado.

Ambas as séries têm 72 janelas por execução e 20 valores válidos por cenário
em cada janela. A tabela usa a média por execução em ACTIVE dos snapshots
nativos de CPU e das observações de memória; os resultados coincidem com
`processed/infrastructure.csv:cpu_mean,mem_mean_mib` da auditoria.

**Não equiparar estimadores de CPU:** a métrica operacional oficial
`ACTIVE/mean_cpu_docker_percent` usa a agregação do coletor em janelas de
5 s, distinta dos snapshots nativos aqui usados. Por exemplo, as médias
oficiais são 51,19%, 205,70% e 228,20% para L2, A3 e F96, enquanto a
tabela deste lote mostra 51,2%, 212,0% e 235,7% pelos snapshots nativos.
As séries não foram ajustadas para coincidir.

### F5.2-E — espera nos geradores e na vítima

- **Geradores legítimos:** para cada uma das duas fontes legítimas por
  execução, o script lê
  `collection/<id>/attempt-1/raw/source_artifacts/<source>/output/diagnostics/events.jsonl`
  e emparelha `submitted.at` com `task_started.at` pelo `attempt_id`. A fila
  corresponde aos intervalos semiabertos `[submitted, task_started)`.
  Sua profundidade é integrada exatamente dentro de cada segundo e dividida
  por 1 s; as duas fontes legítimas são somadas **dentro da mesma execução**.
  Contagens por segundo de ambos os eventos foram verificadas contra
  `reports/investigacao-temporal-energy-20261110/series_fontes_1s.csv`.
  Uma contagem de submissões não foi tratada como profundidade de fila.
  Foram emparelhadas 371.459 tarefas legítimas nas 60 execuções. Os CSVs
  `processed/f52e_geradores_legitimos_por_fonte_1s.csv` e
  `processed/f52e_filas_por_execucao_1s.csv` preservam a série por fonte e
  por execução.
- **Vítima:** `reports/investigacao-temporal-energy-20261110/series_1s.csv`,
  campos `waiting`, `running`, `pending`, `pending_end`. O cálculo em
  `analisar.py:intervals` integra os intervalos de operações
  `[work_submitted, work_started)`, `[work_started, work_completed)` e
  `[work_submitted, work_completed)` no tempo. `waiting`, `running` e
  `pending` são médias temporais por segundo, com `pending = waiting +
  running`; `pending_end` é estoque no limite final do segundo e **não** é
  média. A figura mostra apenas `waiting` da vítima. Em ACTIVE, `running`
  médio por execução é cerca de 1,992 em A3 e 1,979 em F96; foi deixado no
  CSV complementar, pois sua escala é incompatível com filas de centenas.

As séries cobrem 60 × 360 segundos em `[30,390)` e a mediana em cada segundo
tem 20 execuções por cenário. Zero significa fila reconstruída vazia, não
ausência de observação. O painel dos geradores começa em zero: as medianas
ficaram abaixo de 0,01 tarefa legítima aguardando despacho, enquanto a
espera computacional da vítima chegou a centenas de operações. A associação
temporal entre filas, CPU e atendimento legítimo não demonstra causalidade
isolada.

### T5.2-A — síntese operacional

`tables/t52a_indicadores_operacionais.csv` contém média, desvio-padrão
amostral e número de execuções válidas por cenário. O arquivo
`processed/t52a_indicadores_por_execucao.csv` conserva os valores de cada
execução, incluindo medidas complementares de duração 2xx e ocupação dos
workers. A tabela principal seleciona oito indicadores para manter a largura
adequada ao Overleaf.

- Sucesso 2xx e timeout: `processed/http_phases.csv`, classe `benign`, fase
  ACTIVE; `http_2xx_cohort / started` e `timeout_cohort / started`, em
  porcentagem. A coorte usa o **início HTTP**. Não há outras categorias em
  ACTIVE nessas 60 execuções. É o mesmo denominador utilizado na F5.2-C do
  Lote 2.
- CPU e memória: médias por execução em ACTIVE dos registros descritos
  acima, conferidas com `processed/infrastructure.csv`.
- Espera na vítima: média dos 120 valores de `waiting` de cada execução em
  ACTIVE. Pendentes ao fim de ACTIVE: `pending_end` do segundo 269, isto é,
  estoque aos 270 s. Ambos foram confrontados com
  `metricas_periodo_execucao.csv`. Esses pendentes são **operações da
  vítima**; `operational.phases.ACTIVE.pending_at_end` do recibo oficial
  refere-se a HTTP legítimo pendente no cliente e não é equivalente.
- Emissão ofensiva efetiva: `attack_http_start / 120` por execução, de
  `metricas_periodo_execucao.csv`; são **inícios HTTP**, não admissões nem
  conclusões. Emissão nominal: parâmetro fixo de 8 ou 64 RPS do inventário,
  sem desvio-padrão. Ambas são não aplicáveis ao cenário exclusivamente
  legítimo, representadas por travessão e não por zero.

O indicador operacional oficial de sucesso usa o mesmo numerador de 2xx,
mas denominador diferente em **22 execuções** (2 A3 e 20 F96), por usar
journals reconciliados. Portanto, a tabela identifica o sucesso como
**eventual da coorte iniciada**, não como sucesso dentro do prazo operacional.
O resumo oficial contém contrastes pareados e IC BCa para alguns indicadores
operacionais, mas as definições oficiais de CPU e pendências diferem das
empregadas aqui. Nenhum IC foi recalculado ou misturado com as médias e os
desvios-padrão desta tabela.

## Reprodução e validação

Na raiz do repositório:

```bash
.venv/bin/python -B reports/capitulo5_figuras/lote3_operacional/scripts/generate.py
```

O script confere partição, blocos e identidades; presença de cada janela;
completude dos arquivos de eventos de fonte; emparelhamento de tarefas;
contagens dos eventos versus a série auditada; identidade
`pending = waiting + running`; e correspondência das médias e estoques ACTIVE com os resumos
auditados. A tabela usa a execução como unidade para média e desvio-padrão
amostral (`ddof=1`). Os quatro arquivos gráficos foram inspecionados visualmente;
o CSV e o código LaTeX da tabela foram conferidos textualmente. Não há compilador
LaTeX instalado neste ambiente para verificar a tabela no Overleaf. Não foram
executadas novas campanhas.
