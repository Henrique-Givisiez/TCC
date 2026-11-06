# I2 — processamento exploratório A2/A1

## A. Estado inicial

Branch `refactor/project-organization`, HEAD `f3247f3a09b9db7a60ed9e58a052aca14cab1071`, referência presente; working tree limpo. Código e amostras históricas consultados somente de leitura. Nenhum experimento ou contêiner iniciado.

## B. Arquitetura

`experiments.exploratory_analysis`: leitor compartilhado, análise de uma execução, funções A1/A2 e publicação. Reutiliza `export_dataset.placement` para localizar arquivos exportados, `summarize_diagnostics.stats` para percentis descritivos e `ExperimentConfig` para validar o formato. Não altera pipeline científico. A CLI aceita paths raw/dataset para A1 e lista JSON explícita para papéis A2.

Exemplos de interface (não executados sobre dados reais nesta tarefa):

```bash
.venv/bin/python -B -m experiments.exploratory_analysis a2 --runs plano-a2.json --output nova-analise-a2
.venv/bin/python -B -m experiments.exploratory_analysis a1 --runs raw-L2 raw-L6 raw-L3 raw-L7 --output nova-analise-a1
```

Manifesto A2 é lista de objetos `{ "path": "caminho", "role": "M_A" }`, seguida de E_A/E_B/M_B. Papéis são metadados explícitos de planejamento, nunca inferidos do nome da pasta. Endpoint/configuração são conferidos contra cada papel. Caminhos do manifesto são relativos ao próprio manifesto. Não atribuir papéis retrospectivamente para obter uma razão desejada.

Para dataset cujo snapshot operacional é pendente (I1.1), acrescentar `certification` apontando ao `operational_policy.json` final do raw. O certificado deve vincular por hash esse manifest exportado. Sem certificado final, o dataset é inspecionado, mas não entra na comparação principal. Não reescreve dataset ou autoridade.

## C. Esquemas reais

- `request_log.csv`: run_id/request_id, generator, worker_id, target_url, elapsed_seconds/end_elapsed_seconds, duration_ms, http_status, outcome/error_type.
- Fonte identificada pelos journals com source_id/run_id/sequence e request_begin/request_finish; worker_index vem do inventário. Não usa aproximação temporal ou parsing do nome do request.
- Vítima: handler_started/handler_finished, request_id, endpoint, work_cpu_seconds, work_submitted_at/work_started_at/work_finished_at e worker_clock.pid/time_namespace.
- Vítima tem run_id nulo por desenho; vínculo é metadata.run_id + diretório + IDs. Run_id não nulo divergente é problema.
- CPU Docker: simulation_metrics.average_cpu_percent, com elapsed_seconds e suporte de nomes.
- Âncora: run_status.experiment_start_monotonic, confrontada com diagnostics/metadata.origin_monotonic e certificados de relógio.

## D. A2

Chave por execução: (run_id, request_id); não há pareamento de pedidos entre endpoints. Operação válida exige início/conclusão correlacionados, fonte/configuração corretas, CPU numérica finita não negativa e timeline verificável. Contagens explícitas de anomalias e linha por pedido; medições órfãs contadas separadamente. Estatísticas válidas de runs com problemas continuam diagnósticas, mas razões principais ficam indefinidas.

CPU zero é retida e contada. `process_time()` possui resolução finita; zero não é automaticamente corrupção. O runtime não registra resolução específica de process_time por operação, portanto não se prova a causa de um zero individual. Razões exigem média denominadora positiva; indefinido vira null, nunca zero/infinito.

Por run: n, média, mediana, DP amostral (n>1), mínimo/máximo, p95, soma e fração válida. Internamente segundos; soma CPU do kernel não é CPU total do contêiner. Bins de 10s pelo início computacional menos âncora monotônica, somente com prova de relógio. Bins vazios têm n=0 e estatísticas null; trabalhos iniciados depois da duração são contados em tail.

Razões E_A/M_A, E_B/M_B e razão das médias não ponderadas de runs por endpoint. Não é média de razões nem amostra pareada por pedido. Recusa síntese entre configurações, imagens, código/metadata ou políticas heterogêneas. Não calcula IC nem decide adequação do ataque.

## E. A1

Reconhece L2/L6/L3/L7 pelos parâmetros, não pelo diretório: 2×8, 4×4, 2×16, 4×8, medium, 150s e orçamento64. Dois workers, direto, diagnóstico ON, ataque ausente.

Recortes semiabertos [0,30) e [30,150). RPS usa início HTTP; duração e sucesso usam a coorte iniciada e todas as conclusões conhecidas, inclusive depois da fronteira. Contagem explícita de conclusões tardias e sem conclusão. Ausência de conclusão não vira falha definitiva. Denominador de sucesso = starts da coorte. HTTP erro, transporte, conexão, timeout e cliente são separados.

CPU usa ticks suportados no intervalo, percentual Docker (~100% por núcleo lógico equivalente), sem média temporal exata. Ausência é null; cobertura informa primeiras/últimas amostras, contagem e fechamentos de fontes. Não infere cobertura contínua de uma série de amostras nem inventa limite de gap.

Espera = work_started_at − work_submitted_at para coorte por início HTTP. Pendência reconstruída por intervalos submitted→worker-start, com máximo e estado na fronteira. Submissões/inícios/conclusões computacionais são contados por seus próprios marcos. Como esses tempos retornam no handler finalizado, a reconstrução não cobre trabalho sem metadados devolvidos e NÃO é profundidade da fila privada. Dados incompletos são excluídos da comparação principal.

Temporal_metrics usa bins10s. Comparison contém linhas principais por execução; contrastes L2/L6, L3/L7, L2/L3 e L6/L7 estão indicados no relatório. Não estima efeito causal nem escolhe finalista.

## F. Integridade

Confere configuração efetiva, run IDs, composição, horizonte nominal, fontes únicas, sequência de journals e correspondência de campos, fechamento/drenagem, captura aceita sem drops, clocks, writers e certificado operacional vinculado ao status. Campos ausentes, CPU não numérica/não finita/negativa, duplicações, endpoint/fonte divergentes são problemas explícitos. Ausência de operações válidas ou telemetria bloqueia comparação principal. Estado incompleto pode gerar diagnóstico, nunca aprovação implícita.

Leitura falhando gera diagnóstico bloqueado; não fabrica medições. Dataset: confere tamanho/hash das entradas lidas contra o manifest; recusa caminhos inseguros. Não substitui validação científica integral de todo dataset.

## G. Proveniência

Integrity registra configurações, run_id, papéis, imagens/metadata, política e certificação, proveniência do runtime, paths/hashes dos arquivos utilizados, versão I2-v1, hash do processador, parâmetros temporais e regra dos percentis. Hashes são reconferidos antes de publicar. Sem timestamps gerados arbitrariamente nos outputs, resultados são reproduzíveis com os mesmos inputs.

## H. Saídas e exemplo sintético

A2: integrity.json, per_run.csv, cpu_operations.csv, temporal_cpu.csv, ratios.json, report.md.
A1: integrity.json, per_run.csv, temporal_metrics.csv, comparison.csv, report.md.
CSV tem cabeçalhos explícitos; estatísticas estruturadas são células JSON; null em JSON, vazio em coluna escalar CSV. Sem arredondamento interno. Saída existente ou aninhada nos inputs é recusada. Falha na publicação pode deixar diretório parcial, que não deve ser interpretado como concluído nem sobrescrito.

Fixtures: medium .01s, expensive .1s por operação, quatro runs independentes; razões esperadas 10. Isso é teste sintético, NÃO medição real nem evidência da razão do simulador. Inputs permanecem inalterados.

## I. Correção I1.1

Única mudança operacional: `Operations.certify()` exige explicitamente end_reason == simulation_end junto dos critérios existentes. Teste bloqueia completed/interrupted. Nenhum outro mecanismo operacional alterado.

## J. Testes

Comando:

```bash
.venv/bin/python -B -m unittest tests.test_exploratory_analysis tests.test_exploratory_operations tests.test_exploratory_certification tests.test_direct_topology tests.test_diagnostics tests.test_experiment_config tests.test_capacity_exploration tests.test_source_containers tests.test_capture_lifecycle tests.test_dataset_export -q
```

Fixtures cobrem CPU válida/ausente/duplicada/negativa/não finita/zero, pedidos sem fim/órfãos/duplicados, fonte/run/endpoint/clock divergentes, razões e imagens incompatíveis, bins vazios, fronteiras30/150, N2/N4, HTTP/transporte/conexão, incompletude, leituras falhas, dataset exportado/hash adulterado, saída existente e reprodutibilidade byte a byte. Testes não iniciam Docker, tcpdump ou tráfego; mensagens exibidas por regressões vêm de fakes. Resultado final informado na entrega.

## K. Pendências

Aprovar limites I1; validar integração real posteriormente; preservar imagem/ambiente. Nenhum A1/A2 executado. Não há novas features, intervalos de confiança ou seleção automática. Para datasets I1.1 guardar o certificado final externo junto dos resultados. Explorações históricas incompatíveis ficam diagnósticas, não são aceitas pela taxa agregada apenas.

## L. Critérios de aceitação

| Critério | Estado |
|---|---|
| A1/A2 offline e formatos reais | Implementados/testados com fixtures |
| Correlação, CPU/op, razões e fronteiras | Testados |
| Proveniência e preservação dos inputs | Testadas |
| Certificado exige encerramento esperado | Implementado/testado |
| Componentes científicos preservados | Sem mudanças |
| Execução integrada real/liberação A1/A2 | Pendente; não autorizada pela I2 |

## M. Estado final

Arquivos: experiments/exploratory_analysis.py; tests/test_exploratory_analysis.py; correção em exploratory_operations.py e teste em test_exploratory_certification.py; este relatório. Commit e working tree final informados na entrega. Sem push.

## N. Próximo passo

Revisar processamento/limites, aprovar valores e autorizar validação integrada controlada. Somente depois autorizar coleta A2, mantendo ordem e imagens aprovadas. Não escolher carga ou endpoint automaticamente.

## Correções I2.1

Em A1, `integrity_reasons` separa contradições de `unavailable_reasons` por operação. Duplicações, valores corrompidos, identidades inconsistentes e ausência de eventos/metadados obrigatórios em respostas bem-sucedidas continuam bloqueando a comparação principal. Falhas de transporte e requisições incompletas podem não alcançar todas as etapas na vítima; ausências não contraditórias geram avisos explícitos, sem assumir sua causa nem invalidar automaticamente as métricas HTTP disponíveis. Os requisitos de status, certificação, journals e persistência continuam aplicados.

Estatísticas de CPU/op usam somente operações com suporte válido; em A1, a ausência de conclusão HTTP não exclui uma medição computacional íntegra. As contagens `operations_invalid` indicam operações sem suporte completo para essa análise, não necessariamente registros corrompidos. Espera por worker descreve o subconjunto com timeline disponível. Contadores computacionais e trabalho pendente ficam nulos quando não é possível reconstruí-los para todas as operações. Telemetria CPU vazia fica indisponível em A1, com aviso, sem invalidar por si só as demais métricas; arquivos ausentes/corrompidos continuam sujeitos às verificações de integridade. A2 mantém a validação rigorosa anterior.

Cada recorte A1 registra `cpu_coverage`: primeira/última amostra, quantidade, maior intervalo consecutivo e intervalos semiabertos de dez segundos sem amostras. Só entram amostras com contêiner monitorado, usando a mesma seleção da estatística de CPU. Menos de duas amostras não define intervalo consecutivo. O relatório destaca a cobertura de `[30,150)`; lacunas e trechos não observados não permitem afirmar estabilidade contínua. Nenhum limiar novo de cobertura foi criado.

`a2_ratios()` exige quatro `run_id` distintos e presentes, além dos quatro papéis, mesmo em chamada isolada. Os testes adicionais usam apenas fixtures sintéticas; nenhuma coleta ou execução real foi iniciada.
