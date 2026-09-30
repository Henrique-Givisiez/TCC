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
python3 -m simulator.main_orchestrator --duration 180
```

O entrypoint é `simulator/main_orchestrator.py`. A configuração permanece em `simulator/config.py`. O injetor ativo é **`traffic_injectorV0.py`**, apesar do nome; `legacy/traffic_injector.py` pertence ao fluxo anterior.

A simulação exige Docker acessível e permissão de captura para `tcpdump`. O orquestrador importa o cliente Docker antes de processar argumentos, inclusive `--help`. Ele cria/limpa contêineres da simulação. O build usa o `Dockerfile` da raiz, que copia `simulator/app/` para `/app` na imagem.

Exemplos de experimentos e análises (podem executar baterias ou sobrescrever saídas):

```bash
python3 -m experiments.run_experiments_normal
python3 -m experiments.wedos_combined_grid stage1a
python3 -m analysis.run_burst_analysis
python3 -m analysis.generate_presentation_graphs
```

Os subprocessos dos runners usam `python3`; ative o mesmo ambiente virtual no terminal. Use `python3 -m <pacote>.<módulo>` também para os demais scripts, em vez de executar seus arquivos por caminho.

## Resultados e preservação

Nesta etapa, `experiment_results/` permanece no lugar para evitar mover milhares de arquivos históricos. Os CSVs transitórios (`simulation_metrics.csv`, `rtt_log.csv`, `traffic_capture.csv` e os dois logs de resumo) continuam na raiz até os runners os arquivarem. Não execute cenários concorrentes: eles compartilham esses nomes, como antes.

Gráficos são gravados em `results/graficos/` ou `results/graficos_apresentacao/`; a extração de features usa `results/ml_dataset/features_raw.csv`. Análises de bursts preservam saídas ao lado dos arquivos de entrada. A análise manual de RTT pode produzir arquivos transitórios na raiz.

O `.gitignore` evita novos logs, temporários e saídas automáticas conhecidas. Resultados já rastreados continuam versionados; para incluir intencionalmente uma nova saída ignorada, use `git add -f <arquivo>`. Não há regra global ignorando CSVs, XLSX ou PCAPs; o dataset continua rastreado.

A referência histórica é `develop_loadbalancer`. A organização estrutural não modifica algoritmos, parâmetros experimentais ou formatos de dados. Veja [as notas da organização](docs/project_organization.md) e [os limites do código legado](legacy/README.md).
