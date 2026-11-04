# Fase 1 — síntese da auditoria somente de leitura

Auditoria concluída antes de escrever configurações ou executar cargas.

- Branch `refactor/project-organization`; HEAD `74d70b949896c413d6f5e184e7709ff0b1c18364`; working tree inicialmente limpo. Referências `ae052a8` e `f1701cf` presentes e ancestrais. Depois de `f1701cf`, somente `docs/relatorio_2026_11_04_2.md` foi alterado.
- Ferramentas existentes: `experiments.diagnostic_run`, `summarize_diagnostics`, `validate_topology_run`, exportador/validador e extrator de features. Resultados novos devem usar diretório exclusivo, sem sobrescrita; brutos em `experiment_results/`, evidências compactas em `reports/`.
- Seleção: `topology.mode=direct`, fontes em contêineres, uma vítima fixa, load balancer/autoscaler desabilitados; alias `edos_service:80`, segmento `source_victim`. A topologia proxy permanece disponível.

## Endpoints e work_units

`simulator/app/simple_server.py:18–35`: `/light=10000`, `/medium=100000`, `/expensive=1000000` iterações do mesmo kernel `_burn_cpu` (`:38`). Os três usam o mesmo pool persistente, handler, formato de resposta e caminho de erro. Não há limite de concorrência específico por endpoint. O número de iterações é fixo; CPU/tempo em relógio dependem do hardware e do escalonamento.

`NormalTrafficConfig.work_units=10`, `AttackConfig.work_units=5000` e `ServerConfig.default_work_units=1000000` são declarações de configuração. CLI histórica e aliases em `config.py` propagam os campos. `SourceManager` copia os campos para o manifesto da fonte; eles não alteram a taxa, a distribuição ou o tamanho do executor.

`service_destination.request_url`: para os três caminhos reservados, emite somente o caminho. Para caminhos legados, adiciona `?work=<settings.work_units>&sleep=...`. `docker_manager` passa o default do servidor em `WORK_UNITS`. O servidor consulta query/env apenas no caminho legado; os três reservados retornam seu orçamento antes de consultar esses defaults. Portanto, os campos históricos continuam funcionalmente úteis no catch-all, mas não parametrizam `/medium`. Nenhum desses valores será modificado.

**Recomendação:** manter exclusivamente `/medium`. Evidência anterior, não nova medição desta campanha: operação ao redor de 12 ms no mesmo kernel/imagem, com custo intermediário por número de iterações. Permite variar intensidade até utilização relevante dos dois workers sem trocar operação. Não é representação universal de aplicações HTTP nem justifica generalização aos outros endpoints. Não há dúvida concreta que exija matriz de endpoints.

## Gerador e concorrência

`normal_traffic.py:160–203`: RNG por seed/componente/índice global; `expovariate(rate)` após despacho/bookkeeping; primeira submissão imediata. Esperas relativas acrescidas de custos operacionais: não é Poisson homogêneo exato. A taxa é por fonte; o agregado nominal é clientes × taxa.

`source_manager.worker_quotas`: clientes são contêineres, com processo Python próprio e um produtor. O orçamento agregado `max_concurrent_sends` é dividido entre eles. O default existente é 64, e será mantido explicitamente constante; duas fontes recebem 32 threads cada, quatro recebem 16. O orçamento 4 usado na validação mínima anterior era uma escolha daquela validação, não limite arquitetural.

`ThreadPoolExecutor` tem concorrência limitada e admissão não limitada explicitamente. Listas de Futures/pendências já existem; sua limpeza não limita a fila. Não se espera resposta antes de agendar. Requests usa timeout de conexão/leitura, não deadline global. Parada sinaliza o produtor e drena tarefas admitidas por até 30 s; não há cancelamento novo. A fonte pode ser forçada a sair se incompleta, e o gerenciador tem orçamento de encerramento próprio. Alterar clientes/RPS/orçamentos é suportado por configuração.

## Vítima e observabilidade

`ThreadingHTTPServer`: thread por conexão, keep-alive com atendimentos sucessivos, sem cap explícito de handlers. Dois processos computacionais, configurados por `server.process_pool_workers`; handler bloqueia em `.result()` sem timeout próprio. Falhas seguem tratamento padrão; o diagnóstico registra e relança exceções. Não há cancelamento do trabalho remoto por timeout do cliente.

O diagnóstico observa entrada/fim de `do_GET`, chamada submit, começo/fim no worker, CPU de processo no intervalo do kernel, retorno ao handler e handlers ativos. A fila interna do pool não é medida diretamente: espera submit→worker inclui IPC, serialização e escalonamento. Operações simultâneas poderão ser reconstruídas pelo sweep dos intervalos dos workers; é concorrência observada, não profundidade de fila.

## Instrumentação e relógios

Writer JSONL assíncrono, fila de 4096 registros, buffer de arquivo de 64 KiB, descarte não bloqueante contabilizado, resumo após flush. Fechamento abrupto pode deixar resumo/buffer incompleto. IDs de tentativa e eventos científicos são reconciliados; o cabeçalho `X-Edos-Request-Id` já existe e não será ampliado.

Fontes/vítima têm auditorias de comparabilidade monotônica com host (namespace ou prova de kernel/offsets/brackets). Durações locais não exigem subtração entre contêineres. Worker↔handler só é agregado após conferir namespace. Nenhuma latência de rede unidirecional será calculada. Entrada no handler não significa primeiro byte/conexão aceita; fim não confirma recepção pelo cliente.

OFF mantém requests, RTT, captura, ticks de CPU, inventário e status. Não disponibiliza eventos internos de filas/handlers/workers. Diagnósticos não são features.

## Condições operacionais observadas

- 12 CPUs lógicas, 15.712 MiB RAM; cerca de 8.389 MiB disponíveis, swap não utilizado.
- Basal de 3 s: CPU do host 1,37%, load 0,10/0,41/0,34, pressão média de memória/CPU zero na inspeção.
- Disco: 7,1 GiB livres, filesystem em 93% de uso. Não será feita limpeza histórica; armazenamento terá teto conservador.
- Nenhum contêiner ativo; `edos_sources` e `edos_network` preexistentes e vazias.
- Tags diagnósticas já disponíveis: vítima `3f0a418c93db…`, fontes `b8e3996d9b73…`, iguais às evidências anteriores. Fontes Python 3.12.10; vítima histórica Python 3.9.23. Sem migração.
- Não existem quotas explícitas de CPU/RAM nos argumentos de criação; fontes/vítima competem pelo mesmo host. Dois workers não equivalem a 12 núcleos de capacidade computacional.

**Riscos:** filas sem admissão limitada, geração de logs, timeout não absoluto e acúmulo transitório. A investigação é viável com duração curta, orçamento de envio fixo, vigilância externa e progressão condicionada. CPU alta será tratada como utilização, não prova isolada de saturação. Não houve alteração de arquivo ou execução de carga durante a auditoria.
