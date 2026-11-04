# Validação da topologia direta — 04/11/2026

## A. Estado inicial e inspeção

- Branch: `refactor/project-organization`.
- HEAD inicial: `a2b2311349c52b9310c0fd5bbc58baa76d1eec49`, confirmado por Git, sem presumir a revisão da auditoria anterior.
- Working tree inicial limpo; nenhuma alteração local preexistente. Nenhum `AGENTS.md` encontrado na árvore inspecionada. Nenhum commit criado nesta tarefa.
- Python do host: 3.12.3 (`.venv/bin/python`). Engine Docker local Linux; imagens necessárias já disponíveis. Nenhum contêiner em execução no início. `edos_sources` e `edos_network` preexistentes e vazias. tcpdump disponível com `cap_net_admin,cap_net_raw`.
- A imagem da vítima segue o Dockerfile histórico baseado em Python 3.9; não foi migrada nem reconstruída. O host de execução usa Python 3.12. Não se presume Python 3.12 dentro da vítima.

### Componentes e dependências identificadas

| Categoria | Situação anterior e tratamento |
|---|---|
| Configuração/validação | `ExperimentConfig` exigia `load_balancer.enabled` para fontes em contêineres. Adicionado seletor explícito, mantendo restrições de autoscaling. |
| Redes/destino | `docker_manager` cria vítima em `edos_network`; `SourceManager` cria fontes exclusivamente em `edos_sources`; `HttpProxy` ligava ambas. Destino lógico existente `http://edos_service:80`, validado em `service_destination.py`. A aplicação já escuta em 80. |
| Inicialização/ciclo de vida | `main_orchestrator.main` encaminha execução de fontes em contêineres para `source_experiment.run`. Este construía `HttpProxy` incondicionalmente, verificava identidade e iniciava `ProxyMonitor`. Agora seleciona o destino conforme a topologia. |
| Captura/monitoramento | `source_network_audit` compara loopback, bridge, veth e `any`; `TcpdumpSniffer`, `RawCapture` e `CaptureLifecycle` mantêm captura/encerramento/contadores. `StatsCollector` lê CPU Docker da vítima. |
| Exportação/offline | `dataset_run` registra proveniência; `export_dataset` copia bytes e indexa hashes; `validate_dataset` verifica integridade e referências. Extrator reconhecia somente `source_proxy`; agora reconhece também `source_victim`. |
| Integridade | Auditoria bloqueava qualquer acesso por nome/IP da vítima. Agora aceita nome da vítima somente no modo direto e continua rejeitando acesso ao endereço da rede backend. Artefatos NGINX continuam exigidos pelo verificador de coleta quando aplicáveis. |
| Protocolo/relatórios | `development_d3` tem fases fixas e autoridade por hashes. Não foi alterado nem usado para aprovar a execução curta. Criado verificador específico de infraestrutura, sem critérios de detecção. |

`SourceManager`, `GroundTruth`, agregador e validador geral já aceitam ataque desabilitado, zero atacantes e tabela de eventos vazia com cabeçalho. Não foi necessário adaptar ataques, ACTIVE, PRE ou os detectores. O pipeline de avaliação de detectores não participa desta validação.

Comandos existentes inspecionados: `simulator.main_orchestrator --config ... --print-config`, `experiments.dataset_run --config ... --output ... --dataset-output ...`, `experiments.export_dataset`, `experiments.validate_dataset` e `experiments.extract_features`. Testes existentes usam `unittest`, incluindo configuração, fontes, proxy, ciclo da captura, exportação, features, CPU e temporização HTTP.

Plano executado: configuração/destino; auditoria; metadados/exportação; testes; duas execuções legítimas curtas; reconciliação independente; regressão e relatório. Riscos identificados: redes ocupadas, identidade ambígua, captura duplicada, sondagens de preparação, amostras de CPU ausentes e autoridade científica congelada.

## B. Arquitetura implementada

`topology.mode` aceita `proxy` e `direct`; ausência significa `proxy` no fluxo de fontes em contêineres. O caminho histórico de geradores no host permanece preservado. O seletor novo habilita o modo direto somente com fontes em contêineres, autoscaler e load balancer desabilitados, e exatamente uma vítima fixa (`min=initial=max=1`). Valores inválidos e combinações contraditórias nesse fluxo são rejeitados.

A serialização omite o modo padrão `proxy` para preservar o JSON canônico das configurações históricas. O modo efetivo continua explícito no status e nos metadados de captura; `direct` é serializado na configuração. Configurações históricas e seus datasets não foram reescritos.

`DirectTarget` conecta a vítima também a `edos_sources`, com alias `edos_service`, mantendo sua conexão backend em `edos_network`. As fontes permanecem somente em `edos_sources`. Não há publicação de porta da vítima, endereço efêmero fixado ou contêiner intermediário. O IP observado é obtido da API Docker exclusivamente para identidade, auditoria e filtro de captura. O destino HTTP dos geradores continua sendo o alias lógico na porta 80.

A execução recusa redes de fontes ocupadas e vítimas preexistentes. A auditoria exige que os membros de `edos_sources` sejam exatamente as fontes e o destino esperado, confirma DNS único, identidade HTTP, cobertura bidirecional e isolamento. Em `proxy`, a vítima permanece inacessível às fontes. Em `direct`, o nome da vítima deve funcionar, mas seu endereço backend deve continuar inacessível. Contêineres criados são removidos; redes criadas pela execução são removidas e redes preexistentes são preservadas.

Captura canônica: bridge validada empiricamente, `br-7e2468afd861`, com ambos os sentidos no arquivo bruto. As features de ingresso selecionam exclusivamente IPs inventariados de fontes → destino:80. Não há deduplicação. Pacotes sem payload e registros de retransmissão continuam contando. O payload é calculado segundo o contrato TCP, sem somar cabeçalhos ou presumir bytes HTTP únicos.

A auditoria e suas sondagens terminam antes da criação da origem experimental e antes das capturas científicas. Nenhum health check HTTP é emitido no laço experimental. O PCAP final não contém pacotes anteriores à origem. `any` foi rejeitada como ponto canônico: no ensaio direto, observou 178 descrições, com 115 repetições, enquanto bridge/veth observaram 64, sem repetições e com cobertura das duas fontes.

Os metadados contêm topologia, segmento (`source_victim` ou `source_proxy`), interface, ponto de captura, ID/IP/porta de destino, BPF e referência à auditoria. Contadores e término ficam nos relatórios `.capture.json`, associados ao `run_status.json` e exportados. Segmentos desconhecidos, contraditórios e duas declarações simultâneas são rejeitados. Ausência de metadados diretos é erro; legado sem direção suportada permanece sinalizado com features de rede nulas.

## C. Arquivos modificados/adicionados

| Arquivo | Alteração | Justificativa |
|---|---|---|
| `simulator/experiment_config.py` | `TopologyConfig`, validações e serialização compatível | Seleção única e preservação histórica. |
| `simulator/direct_target.py` | Adaptador da vítima direta | Identidade, conexão ao alias, ausência de publicação e verificação de redes. |
| `simulator/source_experiment.py` | Seleção do destino, metadados, recusa de resíduos, limpeza de redes próprias | Ciclo integrado nas duas topologias. |
| `simulator/stats_collector.py` | Evidência opcional de amostras/contadores Docker | Conferir ID e fórmula de CPU sem alterar cálculo/escala/agregação. |
| `experiments/source_network_audit.py` | Auditoria específica de cada modo, DNS e identidade HTTP | Preservar isolamento e comprovar o destino. |
| `experiments/capture_topology.py` | Contrato compartilhado de segmento/destino | Evitar interpretações offline divergentes. |
| `experiments/export_dataset.py` | Exportação de artefatos diretos e routing | Preservar artefatos reais e seus hashes. |
| `experiments/validate_dataset.py` | Consistência das duas topologias e referência da vítima | Manter validações offline. |
| `experiments/extract_features.py` | Reconhecer segmento direto | Preservar fórmulas e impedir rede nula por segmento ignorado. |
| `experiments/validate_topology_run.py` | Verificação legítima curta, PCAP independente e comparação das cinco features | Validar infraestrutura sem executar critérios de campanha. |
| `experiments/configs/direct_validation_benign.json` | Configuração curta direta | Execução reproduzível de baixa carga. |
| `experiments/configs/proxy_validation_benign.json` | Configuração curta com proxy | Regressão equivalente. |
| `tests/test_direct_topology.py` | Seleção, contradições, identidade, resíduos, isolamento e metadados | Testes sem Docker real. |
| `tests/test_topology_integrity.py` | Obrigatoriedade/N/A, falhas de coleta e PCAP | Gates determinísticos de integridade. |
| `tests/test_feature_extraction.py` | Segmento direto e registros repetidos | Exercitar o extrator real. |
| `reports/direct_topology_20261104/` | Relatório, evidências compactas e logs de testes | Rastreabilidade da intervenção. |

Não foram modificados aplicação HTTP, geradores ofensivos, detectores, protocolos ou datasets históricos.

## D. Testes automatizados

Comando final completo em `commands.txt`; saída em `tests-final.txt`.

```sh
.venv/bin/python -B -m unittest tests.test_direct_topology tests.test_topology_integrity tests.test_experiment_config tests.test_feature_extraction tests.test_dataset_validation tests.test_source_containers tests.test_capture_lifecycle tests.test_dataset_export tests.test_http_proxy tests.test_proxy_monitor tests.test_single_victim tests.test_cpu_accounting_audit tests.test_http_timing_audit tests.test_application_operations tests.test_development_d3 -q
```

Resultado final: **265 testes, 264 aprovados, 1 erro, 0 falhas de asserção e 0 ignorados**. Os 251 testes do conjunto de infraestrutura passam; dos 14 D3, 13 passam e 1 rejeita a autoridade congelada.

Erro remanescente: `test_real_authority_configs_and_exclusive_seed_reservations` → `ValueError: Bound source changed: experiments/export_dataset.py`. O gate por hashes detecta corretamente a alteração de infraestrutura. Não foram atualizados hashes nem contornado o gate. Reexecutar a autoridade D3 antiga sobre este checkout exige uma etapa futura explícita de versionamento/revisão do protocolo.

Histórico das rodadas, sem omitir falhas:

| Rodada | Total | Aprovados | Falhas/erros | Ignorados | Tratamento |
|---|---:|---:|---:|---:|---|
| Inicial | 117 | 26 | 91 erros | 0 | Referência incorreta `self.config` no validador, corrigida para o parâmetro `config`. |
| Após correção | 123 | 123 | 0 | 0 | Configuração, fontes, captura, exportação e features. |
| Segmento direto | 125 | 125 | 0 | 0 | Novos casos de captura direta. |
| Regressão ampliada | 250 | 250 | 0 | 0 | Proxy, CPU, HTTP e aplicação. |
| Inclusão D3/isolamento | 265 | 263 | 1 falha + 1 erro | 0 | Serialização do padrão alterava comparação histórica; corrigida. Hash congelado mantido. |
| Rechecagem D3 pontual | 1 | 1 | 0 | 0 | End-to-end histórico passa após correção da serialização. |
| Final | 265 | 264 | 1 erro de hash congelado | 0 | Sem regressão funcional remanescente identificada no escopo. |

Cobertura científica reutilizada: fronteiras decimais e inteiras `[i,i+1)`, início e conclusão em janelas diferentes, falhas com duração, tentativas incompletas sem duração inventada, média nula sem conclusões, pacotes sem payload, direção de ingresso, soma de payload, registros repetidos sem deduplicação, CPU válida/zero suportado/ausência de suporte e fórmula Docker acima de 100%. Os testes adicionais exercitam decodificação independente de PCAP e artefatos essenciais ausentes/perdas reais.

## E. Execuções legítimas

| Parâmetro | Direta | Regressão proxy |
|---|---|---|
| Duração planejada | 24 s | 12 s |
| Fontes | 2 legítimas | 2 legítimas |
| Taxa | 1 RPS por fonte; 2 RPS agregado planejado | Igual |
| Endpoint | `/`, `work=0`, `sleep=0` | Igual |
| Atacantes/eventos | 0/0; ataque desabilitado | 0/0 |
| Monitoramento | Tick 1 s; polling solicitado 0,25 s | Igual |
| Destino lógico | `http://edos_service:80` | Igual |
| Vítima | `423361e4b6a6b977efa2bdb29bbced022d34adc00968e16ae26c0469fb6458f1` | `3af49260cdd31a2b9715f9f7bd32e80c2e1711f3d9c30b6c1e0a218f5a478adf` |
| Segmento | `source_victim` | `source_proxy` |
| Requisições/conclusões | 49/49, todas HTTP 200 | 25/25, todas HTTP 200 |
| ID da execução | `652d5cd6be0f4a78a9edfe548cdff16c` | `fbf5c0f5e8d7445b9363bcc4bbf904da` |

Comandos executados, sem campanhas:

```sh
.venv/bin/python -B -m experiments.dataset_run --config experiments/configs/direct_validation_benign.json --output experiment_results/direct-topology-20261104/direct-raw --dataset-output experiment_results/direct-topology-20261104/direct-dataset
.venv/bin/python -B -m experiments.dataset_run --config experiments/configs/proxy_validation_benign.json --output experiment_results/direct-topology-20261104/proxy-raw --dataset-output experiment_results/direct-topology-20261104/proxy-dataset
```

Após revisão do exportador, ambos os diretórios brutos foram novamente exportados para `direct-dataset-final` e `proxy-dataset-final`, sem sobrescrever as primeiras exportações. O verificador final produziu `direct-review/` e `proxy-review/`, contendo `dataset_validation.json`, `verification.json` e `features/`. Comandos exatos estão em `commands.txt`.

Todos esses diretórios estão sob `experiment_results/direct-topology-20261104/`, ignorado pelo Git por política existente. Evidências compactas e hashes foram copiados para a pasta deste relatório; os brutos completos permanecem disponíveis no workspace. Execuções posteriores devem escolher novos caminhos, pois os runners recusam sobrescrita.

## F. Validação das cinco features

Todas as comparações usam janelas de um segundo alinhadas a zero, sem sobreposição. Nenhuma definição científica foi alterada.

| Feature/coluna | Disponível | Janelas/válidos/nulos | Mínimo/máximo | Evidência de correção | Resultado |
|---|---|---|---|---|---|
| Pacotes: `ingress_packet_count` | Sim | 25/25/0 | 3/19 | PCAP binário independente = CSV = feature em todas as janelas; 155 pacotes de ingresso, incluindo 106 sem payload | Aprovado |
| Payload: `ingress_tcp_payload_length_sum_bytes` | Sim | 25/25/0 | 0/1035 bytes | Soma independente de tamanho IPv4 − cabeçalho IPv4 − cabeçalho TCP; 10.143 bytes, todas as janelas iguais | Aprovado |
| Inícios: `request_starts` | Sim | 25/25/0 | 0/5 | 49 inícios brutos; referências aos journals verificadas; contagens por timestamp de início iguais | Aprovado |
| Duração: `mean_duration_ms` | Sim | 25/24/1 | 1,8500070000300184/22,395438500097953 ms | Médias recalculadas pelas conclusões em cada janela; duração integral preservada | Aprovado |
| CPU: `mean_cpu_percent` | Sim | 25/22/3 | 0,1/0,52 % Docker | Médias dos ticks com suporte conferidas; 13 amostras Docker brutas da vítima, ID e fórmula recalculados | Aprovado |

Exemplos de rede: janela 0 = 19 pacotes/1035 bytes; janela 5 = 12/828; janela 24 = 4/0. O PCAP e o CSV concordam nesses valores e em todas as demais janelas. Nenhuma deduplicação foi aplicada. Não se exige payload positivo em cada intervalo.

Janelas nulas: duração na janela 24, por ausência de conclusões; CPU nas janelas 0 e 1, por ausência de suporte inicial do coletor, e 24, por ausência de tick de monitoramento na cauda. Não houve substituição por zeros. A janela 24 contém encerramento TCP legítimo; o horizonte histórico inclui observações após o plano, resultando em 25 janelas para 24 segundos planejados.

CPU preserva o contrato existente: a feature faz média dos ticks suportados de `simulation_metrics.csv`. Cada tick já contém a média de amostras recentes ou fallback de cache de `StatsCollector`, arredondada pelo gravador histórico; não é uma integral de CPU do segundo. Polling solicitado não garante frequência efetiva: a API Docker é bloqueante; foram 13 leituras brutas durante a execução direta. Nenhuma escala, validade ou regra de fallback foi modificada. `cpu_usage.total_usage` pertence ao cgroup do contêiner e inclui o processo servidor e os processos do `ProcessPoolExecutor`.

Temporização: origem direta epoch `1793814616.7789867`, monotônica `22807.738115214`. Timestamps de pacotes usam subtração epoch documentada; clientes usam domínio monotônico auditado, com prova de namespace/offset e brackets do host; métricas seguem o relógio experimental. Stage 9 verifica alinhamento, ordenação, vínculos início/conclusão, IDs e referências aos journals. Não se presume igualdade numérica entre instrumentos. Não se detectou discrepância que modificasse a atribuição às janelas na reconciliação PCAP/CSV.

## G. Integridade, captura, regressão e limpeza

Direto: 98 verificações gerais de dataset; 18 verificações específicas de coleta/reconciliação, nenhuma reprovada. Proxy: 97 gerais e 16 específicas, nenhuma reprovada. Em ambos, Stage 9 produz um aviso de proveniência: `EXECUTION_WORKTREE_CLEAN`, porque o checkout contém as alterações da implementação. O aviso permanece nos relatórios, com proveniência de execução/exportação; não foi suprimido.

| Captura | Capturados | Recebidos pelo filtro | Perdidos pelo kernel | Encerramento |
|---|---:|---:|---:|---|
| Direta CSV | 259 | 259 | 0 | Aceito |
| Direta PCAP | 259 | 259 | 0 | Aceito |
| Proxy CSV | 103 | 103 | 0 | Aceito |
| Proxy PCAP | 103 | 103 | 0 | Aceito |

Os totais de captura incluem os dois sentidos. Ingresso reconciliado: direto 155 pacotes/10.143 bytes; proxy 65/5.175. Duas fontes cobertas em ambos; nenhum pacote fora do segmento no PCAP, nenhum pacote anterior à origem e zero duplicatas com timestamp e descrição completos idênticos. A comparação da bridge com a veth no ensaio de preparação dá evidência adicional contra duplicação artificial. Retransmissões realmente observadas continuam válidas e não são removidas.

Direto: DNS foi verificado como resolução única para a vítima, resposta contém hostname da vítima, membros da rede são exatamente destino/fontes e não há instância de `HttpProxy`, diretório NGINX ou identidade de proxy no status. A ausência de intermediário é sustentada por esses vínculos e pela topologia auditada. Nome da vítima acessível, IP backend bloqueado em ambas as fontes.

Proxy: NGINX inicializado, fontes resolvem e alcançam seu IP frontend, respostas identificam backend correto; logs e monitoramento NGINX preservados; nome e IP backend inacessíveis às fontes; `source_proxy` processado e reconciliado. Artefatos NGINX são obrigatórios nesse modo e **não aplicáveis** no direto. Artefatos essenciais de fontes/vítima/captura continuam obrigatórios; testes demonstram reprovação quando ausentes ou com perda.

As fontes foram drenadas, os processos tcpdump encerrados e os contêineres das execuções removidos. A consulta final `docker ps --no-trunc` está vazia; `edos_sources` e `edos_network` estão vazias. São redes preexistentes e foram preservadas. A inspeção com `--all` confirmou nove contêineres alheios já parados, preservados; nenhum ID das duas execuções permanece. `ps -C tcpdump` não encontrou processo. A evidência está em `cleanup.json`. Nenhuma campanha científica foi executada.

## H. Limitações e pendências

- A autoridade D3 congelada permanece deliberadamente incompatível por hash com o novo código. Sua reautorização/versionamento é etapa separada; não se usa esta validação para habilitar campanhas.
- A validação exercita duas fontes legítimas, uma vítima fixa, porta 80 e Engine Linux local. Não valida Docker Desktop, outras portas, autoscaling, múltiplas vítimas ou comportamento sob ataque.
- A equivalência PCAP/CSV é observacional nestas execuções; não constitui prova universal de completude da captura ou ausência de deriva de relógio em experimentos longos.
- O aviso de working tree alterado permanece. Os hashes dos arquivos da implementação e das evidências estão anexados; não foi criado commit nem declarada reprodução sob autoridade científica congelada.
- Brutos são ignorados pelo Git conforme política existente. O relatório e as evidências compactas são arquivos novos do workspace; não foram adicionados ao índice ou publicados.
- O código existente já reutiliza CPU em cache quando falta leitura recente. Esse contrato foi preservado e explicitado, sem reinterpretar a feature como CPU instantânea ou integral temporal.
- A aplicação histórica executa em imagem baseada em Python 3.9; migrá-la está fora desta intervenção.

## I. Conclusão

1. **Topologia direta: aprovado.** Vítima alcançada pelo alias lógico, identidade HTTP/Docker confirmada, isolamento preservado e ausência de intermediário comprovada pelo fluxo e auditoria.
2. **Execução legítima: aprovado.** 24 segundos, duas fontes, zero atacantes/eventos, 49 conclusões HTTP 200, captura/CPU/exportação funcionais e limpeza confirmada; regressão proxy de 12 segundos também aprovada.
3. **Cinco features: aprovado.** Presentes e reconciliadas em todas as janelas com PCAP, eventos HTTP e métricas de origem, preservando nulos, direção, payload e regras temporais.

Essa aprovação se refere à infraestrutura e à validação curta descritas. A autoridade científica D3 antiga continua bloqueada, conforme a verificação de hash que permaneceu reprovada.
