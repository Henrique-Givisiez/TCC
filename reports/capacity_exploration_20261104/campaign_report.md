# Campanha exploratória de capacidade — 04/11/2026

## A. Resumo executivo

Foram feitos cinco pilotos legítimos de 12 s (2 fontes, 8–128 RPS agregados) e 11 execuções válidas da matriz principal de 20 s. A matriz prevista tinha 14 execuções; três repetições de 128 RPS não foram realizadas depois que C5 (4 fontes) acionou o limite de progressão: p95 de espera pelo worker de 433 ms, acima do limite operacional predefinido de 100 ms. O run terminou normalmente, sem falhas HTTP, mas esse sinal recomenda não repetir a condição antes de avaliar os dados. Não houve execução ofensiva.

As fontes iniciaram requisições próximas às taxas nominais até 128 RPS nos cenários observados; não apareceu evidência de saturação do gerador. A 64 RPS, as condições com duas e quatro fontes tiveram resultados semelhantes em duração HTTP, com alguma variação nas taxas de uma execução de 20 s. A 128 RPS agregados, duas fontes apresentaram p95 HTTP de 71 ms (ON) em uma execução; quatro fontes apresentaram espera p95 pelo processamento de 433 ms, p95 HTTP de 488 ms e pico de 64 handlers. A evidência aponta para uma fila/espera do processamento da vítima na distribuição por quatro fontes, mas uma única repetição impede afirmar estabilidade ou capacidade máxima.

Todos os 16 resultados incluídos (5 pilotos + 11 principais) terminaram normalmente, passaram a validação dos cinco contratos científicos e reportaram zero perda de captura no kernel, zero falhas HTTP e limpeza completa. Todos os escritores diagnósticos habilitados reportaram logs completos sem perdas nem erros de escrita. A comparação ON/OFF a 64 RPS mostrou diferenças médias HTTP menores que 1 ms e diferenças de CPU Docker de 1,8–3,6 pontos percentuais; a 128 RPS as execuções ON/OFF divergiram muito, sem repetição suficiente para atribuir a diferença à instrumentação.

**Conclusão exploratória:** 8 e 64 RPS agregados foram operacionalmente regulares nas repetições observadas. 128 RPS com duas fontes permaneceu sem falhas, mas foi observado apenas uma vez em cada estado de instrumentação. 128 RPS com quatro fontes mostrou degradação importante no caminho de espera do worker e fica fora de uma faixa recomendável até ser investigado. Nenhuma dessas faixas é uma capacidade máxima nem parâmetro definitivo de campanha.

## B. Estado do repositório e recuperação

- Branch: `refactor/project-organization`.
- HEAD: `74d70b949896c413d6f5e184e7709ff0b1c18364`.
- Working tree inicial: limpo. As implementações históricas de topologia direta (`ae052a8`) e diagnósticos (`f1701cf`) estão no histórico; as alterações posteriores relevantes anteriores a esta tarefa eram documentais.
- A sessão anterior deixou novos auxiliares/configurações/relatórios não rastreados, preservados. O código científico rastreado não foi editado nesta campanha; não foram criados commits.
- Após a desconexão, o processo da matriz não existia mais, `docker ps` não mostrava contêineres ativos e o checkpoint confirmou que C5_ON_r1 havia terminado. Não foi reiniciada a matriz integral.
- A matriz tinha sido definida como C1=2×4=8, C2=2×32=64, C3=2×64=128, C4=4×16=64, C5=4×32=128 RPS agregados, por 20 s, duas repetições. Repetições C2 e C4 abaixo do gatilho, e C1 r2, foram retomadas com os mesmos arquivos de configuração, uma de cada vez. C3 r2 (ON/OFF) e C5 r2 ficaram sem executar após o gatilho de progressão; C5 r2 repetiria a condição que gerou espera elevada. Nenhum arquivo de resultado foi sobrescrito.
- O script `run_matrix.py` não oferece retomada: cria seleção e configs com modo exclusivo e processa a lista integral até o primeiro bloqueio. Por isso, a retomada usou apenas o CLI existente `experiments.capacity_exploration` nas quatro configurações seguras que faltavam.

Componentes e linhas auditados, modelo de chegadas, relógios, endpoint e limitações da observabilidade estão em [audit.md](audit.md). Critérios e matriz planejada estão em [plan.md](plan.md) e [selected_matrix.md](selected_matrix.md).

Referências de implementação: operações fixas e `_burn_cpu` em [`simple_server.py`](../../simulator/app/simple_server.py#L18); pool persistente e `ThreadingHTTPServer` em [`simple_server.py`](../../simulator/app/simple_server.py#L139); amostragem exponencial após despacho em [`normal_traffic.py`](../../simulator/normal_traffic.py#L195); quotas de threads compartilhadas entre contêineres em [`source_manager.py`](../../simulator/source_manager.py#L116); configuração legada `work_units` em [`experiment_config.py`](../../simulator/experiment_config.py#L14).

## C. Auditoria dos endpoints e adequação de `/medium`

Os três endpoints usam o mesmo caminho de atendimento HTTP e pool de processos persistente de dois workers. A diferença está no orçamento fixo de iterações do kernel matemático: `/light` 10 mil, `/medium` 100 mil e `/expensive` 1 milhão de iterações de `sqrt`/`sin`. Não há parâmetro experimental de custo por requisição nesses endpoints, nem uma política de concorrência HTTP diferente por endpoint. Erros de execução do worker são tratados no caminho HTTP comum.

`/medium` foi mantido fixo: oferece mais trabalho computacional que `/light`, sem o custo muito maior de `/expensive`, e o piloto mostrou progressão visível da espera pelo worker sem alterar a aplicação. É uma escolha operacional para esta caracterização, não uma afirmação de que o endpoint seja universalmente representativo. A matriz não cruzou endpoints.

## D. Papel de `work_units`

`work_units` existe em configurações legadas de tráfego normal/ofensivo e como valor padrão do servidor. O código o propaga para configuração/manifesta, mas os destinos HTTP reservados `/light`, `/medium` e `/expensive` determinam internamente seu próprio trabalho fixo. `work_units` só tem efeito no caminho genérico/catch-all. As configurações da campanha preservaram os campos/defaults existentes; nada foi alterado para esta campanha. Assim, esse parâmetro não escala o trabalho de `/medium` e não deve ser usado como se o fizesse.

## E. Desenho experimental e segurança

- Topologia `direct`; uma vítima; autoscaling desabilitado; apenas fontes legítimas; endpoint `/medium`.
- Executor da vítima com 2 processos e limites de concorrência já existentes. Orçamento agregado de 64 threads de envio: 32 por fonte em N=2 e 16 por fonte em N=4.
- Timeout HTTP de 2 s; monitoramento Docker a cada 1 s com polling de stats de 0,25 s; diagnósticos ON nas condições principais, salvo pares OFF planejados.
- Pilotos: N=2, agregados 8, 32, 64, 96 e 128 RPS; duração 12 s; seeds 44112001–44112005. Serviram como etapas de progressão, não como campanhas/repetições inferenciais.
- Matriz principal: duração de geração 20 s; seeds r1=44112101 e r2=44112102; configuração por fonte descrita acima. A comparação OFF foi planejada para C2 e C3.
- Antes de cada cenário, o executor fez preflight dos recursos, redes, imagens e contêineres; observou CPU/memória do host e contêineres, pendências aproximadas e tamanho dos artefatos. O gate de progressão incluía falhas >1%, HTTP p95 >500 ms, worker-wait p95 >100 ms, crescimento persistente de pendências ou inconsistência dos diagnósticos. O limite de 100 ms foi um freio exploratório, não um limiar científico.
- O host tinha 12 CPUs lógicas, cerca de 15,7 GiB RAM e inicialmente ~8,4 GiB disponíveis; havia ~7,1 GiB livres no filesystem. Os pilotos indicaram CPU do host baixa/moderada; na matriz, máximo de ocupação amostrada até ~37,6%. Contêineres fonte e vítima compartilham o host, portanto há possível interferência comum.
- A auditoria Docker dos contêineres registra `Memory=0`, `NanoCpus=0`, sem quota/cpuset ou limite de PIDs: não havia limites de recursos por contêiner. A contenção operacional veio dos gates do monitor externo, do host e das concorrências existentes. Imagens locais usadas foram vítima `edos_target_app:diagnostics-20261104` (Python 3.9.23, ID `sha256:3f0a418c…234f3c09`) e fontes `edos_sources:diagnostics-20261104` (Python 3.12.10, ID `sha256:b8e3996d…26d453c`); os IDs completos constam nos `container_audits.json` e preflights por execução.
- Duração total inclui preparação, geração, drenagem, exportação e validação; a janela de taxa é a geração de 20 s. Conclusões durante drenagem foram contadas separadamente, não como starts de geração.

## F. Matriz executada e resultados dos geradores

Taxa observada abaixo é número de inícios HTTP de cliente dentro de `[0,20s)` dividido por 20 s. Ela não mede chegada TCP à vítima nem conclusão. O gerador sorteia intervalos exponenciais relativos, faz o primeiro despacho imediatamente e dorme depois do despacho; não compensa custo de agendamento/bookkeeping. Isso é uma aproximação operacional de chegadas aleatórias, não uma realização exata de um processo de Poisson homogêneo. A taxa nominal é por fonte, e a soma das fontes é o agregado nominal.

Para uma fonte com parâmetro configurado `λ`, a distribuição exponencial amostrada tem média teórica `1/λ`: 250 ms a 4 req/s, 62,5 ms a 16, 31,25 ms a 32 e 15,625 ms a 64. Nos runs ON da matriz principal, as médias empíricas de intervalos por fonte ficaram próximas desses valores; a razão variância/média das contagens planejadas por segundo variou de 0,71 a 1,25 nas 14 fontes amostradas em r1 (média descritiva 0,97). São janelas curtas e amostra finita, sem teste de aderência ou prova de independência; não devem ser usadas para certificar um processo de Poisson.

| Cenário | fontes × RPS/fonte | RPS nominal agregado | starts/s r1, r2 | HTTP p95 ms r1, r2 | HTTP média ms r1, r2 | CPU vítima média % r1, r2 | worker wait p95 ms r1, r2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| C1 ON | 2 × 4 | 8 | 8,70; 8,25 | 52,23; 56,50 | 18,46; 21,10 | 12,18; 9,35 | 0,67; 0,61 |
| C2 ON | 2 × 32 | 64 | 63,80; 61,35 | 59,56; 58,58 | 37,53; 36,26 | 85,90; 80,06 | 9,78; 9,79 |
| C2 OFF | 2 × 32 | 64 | 63,95; 61,40 | 59,34; 57,94 | 36,75; 35,64 | 82,26; 78,28 | n/a |
| C3 ON | 2 × 64 | 128 | 128,10; não repetido | 71,44; — | 46,51; — | 161,95; — | 23,28; — |
| C3 OFF | 2 × 64 | 128 | 128,15; não repetido | 227,07; — | 78,62; — | 189,00; — | n/a |
| C4 ON | 4 × 16 | 64 | 65,85; 60,85 | 60,44; 59,65 | 32,41; 31,83 | 95,35; 87,45 | 11,25; 11,32 |
| C5 ON | 4 × 32 | 128 | 128,65; não repetido | 488,47; — | 206,55; — | 205,99; — | 433,43; — |

Os cinco pilotos completaram, sem falhas: 7,33 / 33,42 / 63,92 / 96,83 / 127,50 starts/s em 8 / 32 / 64 / 96 / 128 RPS nominais. Nos 11 cenários principais concluídos, nenhuma fonte teve cancelamento, rejeição ou tarefa não resolvida ao fim. Nas condições até C4, p95 de submissão→início da tarefa foi abaixo de 0,35 ms. Em C5 essa espera subiu para média 17,36 ms e p95 145,68 ms; `task_started`→início HTTP continuou curto (p95 ~0,03 ms). O máximo por fonte da diferença derivada entre tarefas submetidas e iniciadas foi 19. Isso é evidência de atraso no agendador/ThreadPoolExecutor da fonte, compatível com tarefas esperando início, mas não é leitura exata da fila interna. A taxa HTTP dentro dos 20 s ainda ficou perto da nominal; a cauda e o atraso de início devem ser considerados separadamente.

Starts no horizonte e conclusões têm horizontes diferentes: alguns pedidos iniciados antes de 20 s concluíram durante drenagem. Por exemplo, em C5 foram 1 início após a fronteira registrada, 29 conclusões na cauda e nenhuma tarefa não resolvida; somente 127,25 conclusões/s ocorreram dentro do plano. Todos os runs foram drenados e seus escritores fecharam normalmente. Esses números não devem ser comparados como “perdas”.

## G. Caracterização da vítima

Até C4 (64 RPS), `/medium` teve duração HTTP p95 de cerca de 58,6–60,4 ms; a espera p95 entre submissão e início do trabalho ficou em 9,8–11,3 ms. Em C2_ON_r1, a espera média foi 1,92 ms, trabalho em parede 12,22 ms, transporte do resultado 0,31 ms e restante do handler 0,46 ms (handler médio 14,65 ms). O pool chegou aos dois workers, como esperado; a ocupação média derivada cresceu com carga.

Em C3_ON (2 fontes, 128 RPS), p95 HTTP foi 71,4 ms e espera p95 23,3 ms, com pico de 11 handlers; o pool continuou com pico de dois workers. Em C5_ON (4 fontes, 128 RPS), HTTP p95 foi 488,5 ms, worker-wait p95 433,4 ms, handler peak 64 e worker wall médio 14,7 ms (p95 23,9 ms). A espera média do worker foi 166,8 ms e o handler teve média 182,1 ms/p95 449,0 ms. A medição instrumentada de CPU de processo por operação (`work_cpu_ms`) teve média 14,65 ms e p95 23,80 ms; ela não é CPU Docker nem tempo de parede. A duração computacional não cresceu na mesma proporção que a espera; portanto, os dados apontam principalmente para espera entre submissão e processamento/retorno, não para operação matemática individual muito mais cara. `work_wait` inclui fila/IPC/agendamento e não isola a fila privada do `ProcessPoolExecutor`.

CPU Docker média acima de 100% é mais de um núcleo equivalente (ex.: 206% ≈ 2,06 CPUs), não percentual da capacidade total do host de 12 CPUs. Em C5 esse nível coexistiu com a espera e as durações elevadas; CPU isoladamente não foi o critério de interrupção. O monitoramento agrega processos do contêiner da vítima, incluindo workers. Existe CPU de processo por operação via telemetria do worker, mas não se deve substituir por ela nem pelo tempo de parede a utilização agregada do contêiner.

## H. Distribuição em duas ou quatro fontes e gargalos

**Observação em 64 RPS:** com 2 fontes, inícios ficaram em 63,80 e 61,35/s; com 4 fontes, 65,85 e 60,85/s. HTTP p95 e médias se sobrepuseram entre as condições. A espera p95 foi ligeiramente maior em quatro fontes (~11,3 ms contra ~9,8 ms), com pequena amostra; não demonstra um efeito estável do número de fontes. As fontes tinham pools locais de envio diferentes (32 vs 16 workers) sob o mesmo orçamento agregado, logo não é apenas uma mudança de identidade de cliente.

**Observação em 128 RPS:** os dois runs de 2 fontes concluíram sem falhas e sem gate acionado, mas têm uma repetição cada. O run de quatro fontes completou HTTP e drenagem sem falhas, mas disparou o gate por espera p95 >100 ms; a série temporal mostra crescimento e pico acima de 500 ms da espera/duração em parte da janela. Não há repetição para confirmar a persistência desse padrão.

**Interpretação:** até 64 RPS agregado, as condições avaliadas foram operacionalmente regulares. A condição de quatro fontes a 128 RPS teve atraso significativo tanto entre submissão e início da tarefa na fonte (p95 145,7 ms) quanto na espera do worker da vítima (p95 433,4 ms), com alta duração HTTP, embora sem request perdido nem timeout. Isso é evidência de degradação operacional neste run, não uma capacidade máxima medida. A taxa agregada iniciada permaneceu perto da nominal, mas isso não elimina atraso do gerador; há sinais dos dois lados do sistema. Não há evidência suficiente para afirmar saturação do host.

**Hipótese pendente:** distribuição por quatro contêineres aumenta a concorrência de handlers/solicitações simultâneas ao pool e pode explicar a espera; maior observação e repetição seriam necessárias para separar efeito da distribuição, variabilidade estocástica e estado do host. A fila privada do pool não é observável diretamente nesta implementação.

## I. Impacto da instrumentação

As diferenças pareadas `ON − OFF` de HTTP médio (ms) foram C2/r1 +0,782, C2/r2 +0,617 e C3/r1 −32,112. Em C2, p95 diferiu +0,222 e +0,643 ms; CPU média diferiu +3,64 e +1,79 pontos percentuais. As taxas iniciadas diferiram no máximo 0,15 req/s a 64 RPS. Em C3/r1 o OFF ficou muito mais lento (p95 +155,63 ms em relação ao ON), sem uma segunda repetição, enquanto CPU também diferiu; a ordem/randômica do sistema, variação natural e estado do host impedem atribuir esse contraste à telemetria.

**Conclusão:** os pares a 64 RPS não exibem diferença operacional grande nas medidas comparáveis, mas duas repetições não demonstram ausência de overhead. C3 é inconclusivo e o par de quatro fontes a 128 não foi feito. ON registrou eventos internos extras; OFF manteve os registros científicos, CPU e captura, mas os dados de espera/worker e filas são `n/a`, não zero. O gráfico e a tabela de pares mostram apenas pares efetivamente executados.

## J. Integridade e preservação científica

- Validação independente de captura/CSV/PCAP e reprocessamento dos artefatos aprovados em todos os 16 runs. Nos relatórios de captura, CSV e PCAP indicaram zero pacotes perdidos pelo kernel; os validadores também aceitaram a reconciliação de pacotes/payload e identidade de fonte/destino.
- Cinco features em todos os runs: `ingress_packet_count`, `ingress_tcp_payload_length_sum_bytes`, `request_starts`, `mean_duration_ms`, `mean_cpu_percent`. Todas as 80 verificações (5 × 16) passaram. Cada run principal teve 21 janelas; pilotos tiveram 13. Valores nulos em média HTTP aparecem quando não houve conclusão naquela janela; CPU tem janelas nulas sem amostra válida. Foram preservados como ausentes, conforme o contrato.
- Writers diagnósticos ON: capacidade 4096; `offered == enqueued == written`, `dropped=0`, `write_errors=0`, `queue_remaining=0`, `complete=true` em cada fonte e na vítima. Os resumos de consistência não apontaram eventos incompletos, duplicados, IDs não pareados ou diferenças entre tempos HTTP científicos e eventos diagnósticos. OFF não é esperado produzir logs diagnósticos.
- Em todos os runs, status `completed_normally`, fontes drenadas, verification `accepted=true`, containers ativos vazios e redes experimentais vazias no `cleanup.json`. Depois da retomada, `docker ps` também estava vazio.
- Não houve alterações em datasets históricos, definições/features, exportador científico, detectores ou protocolo D3. Nenhum hash/autoridade D3 foi atualizado. As topologias `proxy` e `direct` permanecem no código sem mudanças desta campanha.

## K. Limitações e recomendações

1. Tratar 8–64 RPS agregados como faixas preliminarmente regulares para continuar a calibração legítima, e não como limites científicos. 64 RPS teve apenas 20 s por run e duas repetições por modo para N=2 e por ON para N=4.
2. Não reutilizar 128 RPS × 4 fontes sem revisão: C5 acionou o gate e teve alta espera, apesar de não haver falhas nem perda de captura. A matriz parou em vez de repetir essa condição. As condições 128 × 2 fontes têm somente um run por modo e não suportam conclusões fortes.
3. A próxima calibração pode aprofundar 64–128 RPS de maneira planejada, mas só após revisar o comportamento C5 e critérios de segurança; não assumir capacidade máxima, nem fazer a próxima carga ofensiva equivalente a tráfego legítimo.
4. As chegadas são exponenciais amostradas por fonte, relativas ao despacho anterior, primeiro despacho imediato, e executadas após bookkeeping/sleep; não são relógio aberto com agenda absoluta. Curta duração, truncamento e cauda influenciam os totais. A proximidade entre taxa configurada e observada nesta amostra não prova ausência universal de limite do gerador.
5. Espera do worker agrega fila, IPC, serialização e despacho; não há profundidade exata da fila do pool. A CPU de processo por operação é observável nos runs ON e não equivale à CPU agregada do contêiner. Handler-start é ponto de entrada do handler, não aceite TCP nem recebimento completo do request; handler-finished não garante recebimento completo da resposta pelo cliente.
6. Duas repetições não sustentam intervalos de confiança nem variância populacional. Host compartilhado, recursos/versões de imagem observados e diferença de thread quota entre N=2/N=4 limitam a generalização. Resultados não se generalizam automaticamente a `/light`, `/expensive`, ataques ou outras máquinas.
7. A decisão entre Slowloris e ataque assimétrico permanece com o orientador. Esta campanha não avaliou detectores, limiares ou detectabilidade de ataques.

## Artefatos produzidos e comandos

- Tabelas: [runs.csv](runs.csv), [temporal_bins.csv](temporal_bins.csv), [instrumentation_pairs.csv](instrumentation_pairs.csv), [scientific_feature_integrity.csv](scientific_feature_integrity.csv), [capture_integrity.csv](capture_integrity.csv), [runs.json](runs.json), [analysis_manifest.json](analysis_manifest.json).
- Caracterização estatística descritiva das fontes: [generator_statistics_by_source.csv](generator_statistics_by_source.csv).
- Situação individual das 14 configurações planejadas: [matrix_run_status.csv](matrix_run_status.csv).
- Gráficos: [capacity_overview.png](capacity_overview.png), [capacity_time_series.png](capacity_time_series.png) (também em SVG).
- Logs de console preservados: [console_logs/](console_logs/).
- Dados brutos, PCAP, exports, configs, watchdog e verificações: `experiment_results/capacity-exploration-20261104/{P*,C*}/`.
- Configurações preservadas em `experiments/configs/capacity_exploration_20261104/`; análise em `experiments/capacity_analysis.py` e `reports/capacity_exploration_20261104/analyze_results.py`.
- Regressão final: `python -B -m unittest tests.test_capacity_exploration tests.test_diagnostics tests.test_direct_topology tests.test_topology_integrity tests.test_experiment_config tests.test_feature_extraction tests.test_dataset_validation tests.test_source_containers tests.test_capture_lifecycle tests.test_dataset_export tests.test_http_proxy tests.test_proxy_monitor tests.test_single_victim tests.test_cpu_accounting_audit tests.test_http_timing_audit tests.test_application_operations -q` — 280 testes aprovados, zero falhas.
- Durante a preparação do relatório, o sumarizador teve uma execução inicial sem `PYTHONPATH=.` e outra falha em campo de desvio padrão não fornecido pelo resumo de origem. Ambas foram corrigidas; a execução final do sumarizador e `git diff --check` passaram. Os dados brutos não foram modificados.
- Não houve mudanças no runtime do simulador.
