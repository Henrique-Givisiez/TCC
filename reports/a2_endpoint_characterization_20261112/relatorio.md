# A2 — caracterização visual do impacto dos endpoints HTTP

## Escopo e auditoria

Foram processadas somente as quatro execuções em `experiment_results/endpoint-characterization-a2-20261106T200836Z/`: M_A e M_B em `/medium`; E_A e E_B em `/expensive`. `raw/effective_config.json` e `raw/run_status.json` confirmam duas fontes × 1 RPS, 2 RPS nominais agregados, 60 s, concorrência legítima agregada quatro, topologia direta sem NGINX, uma vítima, dois workers persistentes, diagnóstico ligado, timeout HTTP de 2 s e ausência de ataque. Os demais parâmetros efetivos são iguais salvo ID e endpoint. A ordem real de coleta foi M_A → E_A → E_B → M_B; logo os rótulos A/B indicam repetição, não blocos simultâneos. As execuções terminaram `completed/simulation_end`, com fontes drenadas e `errors=[]`.

Cada execução dispõe de `request_log.csv`, `rtt_log.csv`, `victim_stats.jsonl`, `simulation_metrics.csv`, eventos da vítima, eventos dos dois geradores, journals e status. Os 101 IDs HTTP de cada execução são únicos e correspondem aos 101 ciclos computacionais completos. Há dez handlers de auditoria de captura por execução, anteriores ao experimento, excluídos. Os eventos dos geradores distinguem `planned`, `submitted`, `task_started`, `http_started`, `http_finished` e `task_finished`; nenhum deles foi equiparado ao evento de entrada do handler ou aos instantes computacionais. Os 101 segmentos do painel usam `elapsed_seconds` e `end_elapsed_seconds` do log HTTP. O RPS iniciado é 101/60 = 1,6833 em cada execução; não se substituiu esse valor pelo nominal de 2.

O início efetivo da execução vem de `run_status.experiment_start_monotonic`. A vítima registra `work_submitted_at`, `work_started_at`, `work_finished_at` e CPU do processo worker em `handler_finished`; todos os workers declararam `CLOCK_MONOTONIC` e o mesmo namespace de tempo. A telemetria Docker usa `monotonic` relativo ao mesmo início. A correspondência de IDs e os relógios permitem alinhar as séries, com a ressalva de que a duração HTTP inclui rede, espera e processamento. A telemetria bruta da vítima tem 21 amostras por execução, 20 em [0,60), com cadência mediana próxima de 3,02 s. `simulation_metrics.csv` tem somente dez ticks por execução e não foi usada para preencher a telemetria.

No código da coleta (`8182681`, `simulator/app/simple_server.py`), `/medium` usa 100.000 unidades e `/expensive` 1.000.000 unidades do mesmo kernel determinístico, sem espera artificial. Essa diferença de orçamento computacional é a diferença de implementação identificada entre os endpoints; qualquer custo incidental do handler, escalonamento e ambiente pode também influir nos tempos realizados. As duas repetições por endpoint usam mesma configuração e semente, mas não constituem amostra suficiente para inferência estatística ou garantia de trajetórias independentes.

## Resumo por execução em [0,60)

| Execução | HTTP iniciadas / 200 | CPU worker média / mediana / p95 (ms/op) | CPU Docker média / máximo (%) | Memória média (MiB) | HTTP mediana / p95 (ms) | Workers ocupados: 0/1/2 (fração) | Pico aguardando |
|---|---:|---:|---:|---:|---:|---:|---:|
| M_A | 101 / 101 | 29.28 / 29.17 / 33.91 | 4.68 / 9.89 | 23.61 | 35.69 / 42.49 | 0.952 / 0.047 / 0.001 | 1 |
| M_B | 101 / 101 | 28.37 / 28.12 / 32.32 | 4.56 / 10.00 | 23.62 | 34.54 / 40.84 | 0.953 / 0.046 / 0.001 | 1 |
| E_A | 101 / 101 | 225.85 / 218.68 / 262.79 | 32.80 / 91.49 | 23.88 | 224.64 / 292.10 | 0.672 / 0.277 / 0.052 | 1 |
| E_B | 101 / 101 | 227.72 / 225.72 / 259.12 | 32.44 / 87.81 | 23.84 | 232.11 / 282.22 | 0.668 / 0.280 / 0.052 | 1 |

As frações 0/1/2 na tabela somam 1; para percentuais, multiplicar por 100. Os arquivos `processed/summary.csv` e `processed/workers_*.csv` preservam os valores sem arredondamento. Todas as respostas foram HTTP 200; timeouts, falhas de conexão e outros encerramentos foram zero.

## Figuras e interpretação

### Painéis temporais integrados

**Arquivos:** [painel_integrado_M_A.png](figures/integradas/painel_integrado_M_A.png), [painel_integrado_M_A_compacto.png](figures/integradas/painel_integrado_M_A_compacto.png), [painel_integrado_M_B.png](figures/integradas/painel_integrado_M_B.png), [painel_integrado_M_B_compacto.png](figures/integradas/painel_integrado_M_B_compacto.png), [painel_integrado_E_A.png](figures/integradas/painel_integrado_E_A.png), [painel_integrado_E_A_compacto.png](figures/integradas/painel_integrado_E_A_compacto.png), [painel_integrado_E_B.png](figures/integradas/painel_integrado_E_B.png), [painel_integrado_E_B_compacto.png](figures/integradas/painel_integrado_E_B_compacto.png). Versão comparativa com as quatro execuções: [painel_comparativo_quatro_execucoes.png](figures/integradas/painel_comparativo_quatro_execucoes.png). Cada PNG possui PDF vetorial homônimo.

Os painéis completos apresentam, no mesmo eixo [0,60) s: segmento de cada requisição do início ao fim HTTP, CPU Docker do contêiner da vítima (%), `raw_mem_usage` do contêiner em MiB, workers ocupados, operações aguardando e duração HTTP individual (ms) posicionada no início. A versão compacta mantém as seis faixas com menor altura para consulta em página. A comparação organiza A/B nas linhas e `/medium`/`/expensive` nas colunas, sem selecionar uma repetição representativa; CPU usa escala comum 0–100% e duração, 0–400 ms. Os segmentos representam respostas HTTP 200; se houvesse outros encerramentos, seriam marcados em vermelho com `x`.

Em `/expensive`, os segmentos HTTP são visivelmente mais longos, a CPU amostrada é maior e a ocupação dos workers ocupa parcela maior do tempo. No painel individual E_A há picos de CPU e de duração que não devem ser lidos como causa um do outro: a CPU é amostrada a cada ~3 s, enquanto as requisições são eventos individuais. Não há medição direta da fila HTTP pré-handler.

### V1 — Custo computacional por requisição

**Arquivo:** [V1_cpu_por_operacao.png](figures/comparativas/V1_cpu_por_operacao.png). Fonte: `work_cpu_seconds` dos eventos `handler_finished`, multiplicado por 1000; 101 operações válidas por execução. Método: boxplots separados por execução. Médias: M_A 29.28 ms, M_B 28.37 ms, E_A 225.85 ms, E_B 227.72 ms. A média das duas médias de `/expensive` foi cerca de 7,87 vezes a de `/medium`, relação descritiva dessas execuções. CPU/op não é CPU Docker nem duração HTTP.

### V2 — CPU e memória por endpoint

**Arquivo:** [V2_cpu_memoria.png](figures/comparativas/V2_cpu_memoria.png). Fonte: `victim_stats.jsonl`, somente amostras em [0,60). Os pontos são amostras reais; o traço preto marca a mediana de cada execução. A CPU Docker média foi 4.68% e 4.56% em `/medium`, ante 32.80% e 32.44% em `/expensive`. As médias de memória ficaram entre 23.61 e 23.88 MiB, sem diferença expressiva nesta escala. O eixo de memória é ampliado para revelar variação de poucos MiB. CPU Docker pode exceder 100% em outras condições; aqui é percentual de uso do contêiner, não do host. Amostras temporais não são repetições independentes.

### V3 — Duração HTTP por endpoint

**Arquivo:** [V3_duracao_http.png](figures/comparativas/V3_duracao_http.png). Fonte: `request_log.duration_ms`, somente respostas HTTP 200, coorte de início em [0,60). Método: boxplot e ECDF separados por execução. Medianas M_A/M_B: 35.69/34.54 ms; E_A/E_B: 224.64/232.11 ms. Os p95 constam da tabela. Tempo HTTP inclui rede, espera e serviço; não substitui CPU/op.

### V4 — Ocupação e espera computacional

**Arquivo:** [V4_workers_espera.png](figures/comparativas/V4_workers_espera.png). Fonte: instantes `work_submitted_at`, `work_started_at`, `work_finished_at` da vítima. Ocupação = intervalo início–fim; aguardando = submissão–início. Frações calculadas por integração exata dos intervalos em [0,60); espera em ms por operação; pico aguardando separado. A escala da espera é logarítmica para tornar visíveis outliers de ~130 ms em E_A/E_B e a massa próxima de 1–2 ms. Os picos aguardando foram 1 em todas as execuções; isso não mede a profundidade privada do executor. A espera por worker não mede a espera total HTTP.

### Controle de taxa efetiva

**Arquivo:** [RPS_nominal_efetivo.png](figures/comparativas/RPS_nominal_efetivo.png). Fonte: `effective_config.json` e `request_log.csv`; inícios HTTP em [0,60) divididos por 60 s. As quatro execuções atingiram 1,6833 RPS iniciados frente a 2 nominais, preservando a igualdade de taxa realizada entre endpoints nesta coleta. Planejamento e submissão de tarefas não foram contados como inícios HTTP.

## Validação e limites

- 14 figuras, cada uma em PNG 300 dpi e PDF vetorial; painéis integrados, comparação e V4 foram inspecionados visualmente. As escalas da comparação são comuns por métrica.
- IDs de HTTP, RTT, diagnósticos dos geradores e eventos computacionais coincidem por execução; os tempos de início/fim e durações são não negativos e coerentes. Todos os ciclos CPU/op são completos.
- A reconstrução mantém 0–2 workers e nenhuma operação aguardando negativa. Eventos simultâneos seguem ordem submissão, início e fim. As frações de ocupação somam 1.
- `validation/checks.json` contém hashes SHA-256 dos arquivos primários lidos, contagens, cobertura e cadência. A revalidação pós-geração não encontrou modificação de entradas.
- Memória corresponde ao contêiner `target_instance_1`, não RAM total do host ou RSS isolado do Python. Linhas entre amostras Docker servem apenas de guia visual. A pouca duração e duas repetições por endpoint limitam generalização; nenhum teste de significância ou intervalo de confiança foi calculado.

## Reprodução

Na raiz do repositório, com Python 3, `numpy`, `pandas` e `matplotlib`:

```bash
python3 reports/a2_endpoint_characterization_20261112/scripts/generate.py
python3 reports/a2_endpoint_characterization_20261112/scripts/write_report.py
python3 reports/a2_endpoint_characterization_20261112/scripts/validate.py
```

Entradas: somente os quatro runs A2 em `experiment_results/endpoint-characterization-a2-20261106T200836Z/`. Parâmetros: [0,60) s, eventos individuais e amostras Docker reais, sem interpolação ou agregação entre repetições. Saídas: `figures/`, `processed/`, `manifest.json`, `validation/checks.json`, `relatorio.md`. SHA-256 do gerador: `2427ebbe50b6eeecf3e903a52e84ff04fa28573106dcdfd55fc78be40351cfad`.
