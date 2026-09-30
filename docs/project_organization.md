# Etapa 0 — organização estrutural

Referência: `develop_loadbalancer`. Branch de trabalho: `refactor/project-organization`.

O núcleo está em `simulator/`, os executores em `experiments/` e o pós-processamento em `analysis/`. Os quatro `run_burst_*` são análises; `verify_s4_candidate.py` executa experimentos. `EntCusumZV3.py` continua sendo usado pelas análises. Pipelines `run_all_*` permanecem junto aos experimentos.

Imports usam os pacotes correspondentes; comandos Python usam `python3 -m`. O diretório de execução documentado é a raiz. O contexto Docker é derivado da localização de `docker_manager.py`; o Dockerfile copia `simulator/app/`, preservando `/app`, porta, imagem base e comando do servidor.

`experiment_results/` (6.469 arquivos rastreados no diagnóstico) não foi movido. Seus caminhos de leitura/escrita e os nomes dos CSVs transitórios foram preservados. Gráficos, logs, dataset e artefatos soltos foram reunidos em `results/`. Artigos foram movidos para `docs/references/`; relatórios e registros textuais históricos foram preservados em `docs/`.

Somente o orquestrador de backup, seu injetor e `Versions/` foram classificados como legado. Sufixos V0/v2/v3 não foram usados como evidência isolada de obsolescência. `wedos_stage1b_resume.py` continua disponível como retomada específica.

## Limites preservados

- Alguns módulos têm efeitos durante importação; `docker_manager.py` conecta ao daemon e pode encerrar o processo. Scripts de experimento/análise podem executar trabalho no nível superior.
- Configuração é compartilhada por núcleo e análises; os imports devem apontar para a mesma instância de `simulator.config`.
- Os runners compartilham arquivos transitórios na raiz. A organização não adiciona suporte a execuções concorrentes.
- `PCAP_FILE_NORMAL_TRAFFIC` referencia um arquivo preparatório não usado pelo fluxo atual; o parâmetro foi preservado.
- Documentos históricos descrevem versões anteriores e não são especificações atualizadas do comportamento. Consulte o código ativo e o README para caminhos/comandos atuais.
- O único `requirements.txt` reúne dependências do núcleo e das análises, incluindo `openpyxl` para XLSX. Não foram introduzidas versões fixas sem uma base de reprodutibilidade anterior.

## Validação da reorganização

- Sintaxe e comparação de AST dos 97 arquivos Python movidos: somente imports, comandos de módulos, destinos de gráficos/dataset e contexto Docker mudaram; a aplicação vítima foi preservada.
- Destinos dos imports locais e módulos chamados pelos subprocessos conferidos. Imports do núcleo executados com `docker.from_env` simulado; declarações de import dos 100 módulos dos quatro pacotes resolvidas sem executar os corpos dos experimentos/análises. Identidade compartilhada de `simulator.config` confirmada.
- Self-tests existentes de `load_balancer`, `cost_calculator`, `host_stats` e `autoscaler_logic` passaram.
- Argumentos do orquestrador (`--help`) verificados com cliente Docker simulado; `analysis.ml_feature_extraction --help` e `experiments.run_wedos_grid_fill_reps --dry-run` passaram. O dry-run encontrou 59 configurações e nenhuma execução nova pendente.
- Dependências instaladas em ambiente virtual isolado em `/tmp`, usando Python 3.8.10; `pip check` passou.
- Build real de `Dockerfile` passou com tag separada `edos-organization-validation:stage0`. Nenhuma simulação foi executada. O contexto permanece grande (~3,95 GB), pois inclui o histórico do repositório; otimização do contexto não fez parte desta etapa.
- Artefatos de pesquisa, logs, ZIPs e documentos históricos movidos foram comparados byte a byte com a referência Git. `experiment_results/` permaneceu inalterado.

Esses checks não constituem validação experimental de ponta a ponta nem certificam o fluxo legado. Os scripts temporários de auditoria e o ambiente de validação ficaram fora do repositório.
