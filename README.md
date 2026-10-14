# EDOS_SIM2

Simulador acadêmico de DoS/EDoS com aplicação vítima em Docker, geração de tráfego, balanceamento, autoscaling e coleta de métricas.

| Diretório | Conteúdo |
| --- | --- |
| `simulator/` | Núcleo e configuração (`config.py`); vítima em `app/simple_server.py`. |
| `experiments/` | Execução de cenários, grids, repetições e pipelines W-EDoS. |
| `analysis/` | Processamento de CSV/XLSX, detecção existente, extração de features e gráficos. |
| `results/` | Gráficos, dataset, capturas e logs antes dispersos na raiz. |
| `experiment_results/` | Histórico experimental preservado no caminho original; os runners continuam gravando aqui. |
| `docs/` | Documentação de módulos, relatórios, histórico e referências bibliográficas. |
| `legacy/` | Orquestrador/injetor anteriores e snapshots de `Versions/`. |

## Execução

Execute os comandos **a partir da raiz do repositório**, usando Python 3 e as dependências de `requirements.txt` (preferencialmente em ambiente virtual):

```bash
python3 -m pip install -r requirements.txt
python3 -m simulator.main_orchestrator --config experiments/configs/default.json
```

O entrypoint é `simulator/main_orchestrator.py`. Os parâmetros experimentais usam JSON e dataclasses em `simulator/experiment_config.py`; configuração técnica e caminhos permanecem em `simulator/config.py`. Veja [a configuração da Etapa 1](docs/experiment_configuration.md) e [o contrato de ground truth da Etapa 2](docs/ground_truth.md). O injetor ativo é **`traffic_injectorV0.py`**, apesar do nome; `legacy/traffic_injector.py` pertence ao fluxo anterior.

A simulação exige Docker acessível e permissão de captura para `tcpdump`. `--help` e `--print-config` funcionam sem acessar Docker; a configuração é validada antes de inicializar os componentes. Ele cria/limpa contêineres da simulação. O build usa o `Dockerfile` da raiz, que copia `simulator/app/` para `/app` na imagem.

Exemplos de experimentos e análises (podem executar baterias ou sobrescrever saídas):

```bash
python3 -m experiments.run_experiments_normal
python3 -m experiments.wedos_combined_grid stage1a
python3 -m analysis.run_burst_analysis
python3 -m analysis.generate_presentation_graphs
```

Os subprocessos dos runners usam `python3`; ative o mesmo ambiente virtual no terminal. Use `python3 -m <pacote>.<módulo>` também para os demais scripts, em vez de executar seus arquivos por caminho.

## Resultados e preservação

Nesta etapa, `experiment_results/` permanece no lugar para evitar mover milhares de arquivos históricos. Os CSVs transitórios (`simulation_metrics.csv`, `rtt_log.csv`, `traffic_capture.csv`, `attack_events.csv`, `request_log.csv`, `run_status.json` e os dois logs de resumo) continuam na raiz até os runners os arquivarem. Não execute cenários concorrentes: eles compartilham esses nomes, como antes.

Gráficos são gravados em `results/graficos/` ou `results/graficos_apresentacao/`; a extração de features usa `results/ml_dataset/features_raw.csv`. Análises de bursts preservam saídas ao lado dos arquivos de entrada. A análise manual de RTT pode produzir arquivos transitórios na raiz.

O `.gitignore` evita novos logs, temporários e saídas automáticas conhecidas. Resultados já rastreados continuam versionados; para incluir intencionalmente uma nova saída ignorada, use `git add -f <arquivo>`. Não há regra global ignorando CSVs, XLSX ou PCAPs; o dataset continua rastreado.

A referência histórica é `develop_loadbalancer`. A organização estrutural não modifica algoritmos, parâmetros experimentais ou formatos de dados. Veja [as notas da organização](docs/project_organization.md) e [os limites do código legado](legacy/README.md).

A topologia fixa com uma vítima, autoscaler desligado e validação sequencial
A/B/C está descrita em [docs/single_victim.md](docs/single_victim.md).
A configuração dedicada é [single_victim.json](experiments/configs/single_victim.json).

A Etapa 4 oferece [proxy HTTP NGINX real](docs/http_proxy.md), endpoint único e
vítimas sem portas publicadas, em [proxy_single_victim.json](experiments/configs/proxy_single_victim.json).
Os perfis anteriores mantêm `load_balancer.enabled=false`. Veja a
[validação da Etapa 4](docs/http_proxy_validation.md).

A Etapa 5 oferece [origens de rede em containers](docs/container_sources.md),
com redes de entrada/backend separadas, inventário de sources e agregação de logs.
Use `experiments/configs/container_sources.json`; o modo histórico no host continua
explícito para regressões. O [registro de validação](docs/container_sources_validation.md)
reúne resultados e artefatos da implementação.

A Etapa 6 oferece [operações com custo definido na vítima](docs/application_operations.md):
`/light`, `/medium` e `/expensive`. Use
`experiments/configs/application_operations.json` para o novo fluxo via sources e NGINX.
Os demais paths preservam o mecanismo legado `work`/`sleep` para compatibilidade.

A Etapa 7 oferece [padrões temporais de ataque](docs/attack_patterns.md):
`ContinuousFlood` preserva o comportamento histórico e `PeriodicBurst` alterna
bursts e silêncio, sem transportar backlog. Veja
`experiments/configs/periodic_burst.json`. `attack.rate` é RPS por atacante/source;
somente o orçamento de send workers é dividido entre sources.

A Etapa 8 acrescenta [exportação padronizada do dataset](docs/dataset.md), com
manifest/schema version 1, arquivos observados preservados byte a byte e separação
de metadata, tráfego, serviço, infraestrutura, ground truth e evidências.
Use `python3 -m experiments.export_dataset RUN_DIRECTORY DATASET_DIRECTORY`.
O entrypoint opcional `experiments.dataset_run` registra proveniência antes de
invocar a simulação existente. Runs incompletos são preservados explicitamente.

A Etapa 9 oferece [validação científica offline](docs/dataset_scientific_validation.md),
com `dataset_valid` separado de `analysis_eligible` e checks estruturais, semânticos
e de qualidade. Use `python3 -m experiments.validate_dataset DATASET_DIRECTORY
--output REPORT_OUTSIDE_DATASET.json`. O relatório preserva warnings e evidências;
o dataset permanece somente leitura.
