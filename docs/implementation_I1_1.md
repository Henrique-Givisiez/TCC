# I1.1 — Robustez e certificação

## A. Estado inicial

Branch `refactor/project-organization`; HEAD inicial `670dd12d82a7baa7254ac155b96b76ff3ab74994`, presente e inspecionado. Working tree limpo. Nenhum dado anterior alterado.

## B. Diagnóstico

Confirmados: certificado prematuro baseado somente em `errors`; timer armado fora do try; desarme capaz de impedir cleanup; restauração Docker capaz de abortar status; exportação posterior sem efeito na progressão. Fonte parcialmente criada já era preservada em `manager.containers` antes de reload, portanto não havia evidência de perda sistemática desse identificador. O callback imediato torna posse e identidade explícitas antes de setup adicional. Não foi alterada arquitetura.

## C. Alterações

- `exploratory_operations`: estados pendentes, checks físicos, prontidão categorizada, timer parcial/restauração, certificado pós-export e predecessor vinculado ao status.
- `source_experiment`: setup protegido, erros secundários acumulados, callback de posse, trace de interrupção e restauração protegida.
- `source_manager`: callback opcional após append da fonte criada; caminho histórico sem callback permanece disponível.
- `diagnostic_run`: conclusão de procedimento envolvendo runtime, tentativa de export e certificado; primeira exceção preservada.
- Testes existentes ajustados e `test_exploratory_certification.py` acrescentado.

## D. Certificação

Quatro dimensões: execução referencia/hash do `run_status`; limpeza física e verificações próprias; registros essenciais; exportação. Progressão só é avaliada depois dessas etapas e da prontidão pós-cleanup. Falhas essenciais bloqueiam; limpeza pode ser verdadeira mesmo com execução incompleta. Ausência de certificado final significa pendência, nunca aprovação.

Checks básicos: JSONs essenciais legíveis, CSVs presentes não vazios, captura certificada, journals presentes, finais drenados/logger completo e writers diagnósticos completos quando habilitados. Não implementa reconciliação científica de pedidos/CPU. O snapshot exportado precede a certificação: o relatório final no raw referencia o manifest e o status por hash. Dataset não é reescrito.

## E. Temporizador

Armar/configurar/desarmar ocorre sob tratamento de erros. Restaurar handler e cancelar timer são tentados independentemente. Erro secundário é acumulado. O timeout Docker é restaurado mesmo depois de setup falho; recusa da restauração é registrada. Não há garantia de limite rígido para cleanup/export/daemon/SO. Falha efetiva de cancelamento continua sendo falha essencial, exigindo diagnóstico; não é ocultada como sucesso.

## F. Inicialização parcial

O identificador é guardado em `manager.containers` e imediatamente comunicado a Operations antes de reload. Teste real do método start com contêineres fake falha na terceira fonte após duas criações: as duas permanecem conhecidas, identidade verificada e remoção restrita a elas. A recuperação existente no finally permanece como defesa adicional.

## G. Prontidão

Mantida ausência conservadora de todos os contêineres ativos. A inspeção read-only `docker ps --no-trunc` não encontrou contêineres ativos nesta sessão, compatível com o ambiente controlado. Recusas distinguem fontes/vítimas residuais, externos ativos, processos conhecidos, redes ocupadas, recursos e verificação falha; IDs são preservados. Nenhum recurso externo é removido. Não certifica isolamento absoluto, e espera fixa não aprova prontidão.

## H. Rastreabilidade

`operational_policy.json` mantém condições simultâneas/actions, histórico de prontidão, etapas de shutdown, checks de cleanup, failures, records/export/certification e referência ao status. Runtime exception e timeout possuem instante/ação. `run_status` permanece canônico para o simulador. `--previous-run` exige certificação final, procedimento completo e hash do status correspondente. Relatórios antigos permanecem intactos e não recebem aprovação retroativa.

## I. Testes

Comando de regressão, sem contêiner/tráfego real:

`.venv/bin/python -B -m unittest tests.test_exploratory_operations tests.test_exploratory_certification tests.test_direct_topology tests.test_diagnostics tests.test_experiment_config tests.test_capacity_exploration tests.test_source_containers tests.test_capture_lifecycle tests.test_dataset_export -q`

Cobre sucesso, runtime incompleto com ambiente limpo, export falho, persistência falha, original mais falha secundária, timer parcial/desarme, setup falho com cleanup, timeout Docker não restaurável, criação parcial, recursos externos e predecessor. Build/tcpdump exibidos nos testes são fakes. Integração real pendente de autorização. Resultado final na resposta e histórico do commit.

## J. Limites operacionais — propostas, não configuração aprovada

Inspeção de 06/11/2026: MemTotal 16.475.328.512 bytes; MemAvailable aproximadamente 10,37 GB decimais; disco disponível 6.093.967.360 bytes (~5,68 GiB). Snapshot não garante disponibilidade futura.

Referências: `experiment_results/capacity-exploration-20261104/{P1_8rps,C2_ON_r1,C5_ON_r1}/watchdog.jsonl`, `execution_result.json`, raw e datasets existentes. Nenhuma análise regravada.

| Parâmetro | Histórico | Evidência lida | Candidato para revisão | Limitação / aprovação |
|---|---|---|---|---|
| min_available_bytes | 2 GiB | Disponível atual ~9,66 GiB; máximos amostrados vítima 33,9 MB/fonte 34,5 MB | 2 GiB | Guarda de reserva, não estimativa de uso máximo. Aprovar |
| min_disk_bytes | 4 GiB | Disponível ~5,68 GiB; exports duplicam parte do raw | 4 GiB | Pequena folga acima do guarda; planejar retenção. Aprovar |
| victim_memory_bytes | 1 GiB | Máximo amostrado 33.906.688 bytes em C5 | 1 GiB | Histórico curto não prova máximo de 150 s. Aprovar |
| source_memory_bytes | 512 MiB | Máximo amostrado 34.508.800 bytes em P1 | 512 MiB | Amostragem não captura todos os picos. Aprovar |
| max_artifact_bytes | 512 MiB/run curto | P1 raw/dataset 0,78/0,86 MB; C2 8,59/8,68 MB; C5 17,71/17,81 MB | 512 MiB como candidato, não obrigação | Escala linear C2 20→150s daria ~65 MB raw, mas NÃO é garantia; limite atual mede raw, não export. Aprovar e revisar no primeiro ensaio autorizado |
| collection_max_age_seconds | 5 s | Gaps das estatísticas de vítima: mediana ~2,004 s, máximo ~2,019 s nas três amostras | 5 s | Poll solicitado 0,25s não foi frequência realizada; validar em integração. Aprovar |
| global_timeout_seconds | nominal+90 s | Elapsed externos P1 23,26s/12 nominal; C2 31,39s/20; C5 32,90s/20 | A2 150 s; A1 240 s | Inclui margem maior que setup observado; timer runtime, não wall time rígido final. Aprovar |
| docker_timeout_seconds | 3 s | Stats realizados ~2s; preflight externo histórico usava3s | 3 s, provisório | Não mede latência máxima de todas as operações Docker. Aprovar/validar |

Nenhum dos candidatos foi aplicado. A2 tem baixa taxa mas endpoint caro; A1 dura mais, tem mais fontes e mais diagnóstico. Não transportar consumo de CPU para limite de memória ou tamanho de arquivo. Fonte histórica P1/C2/C5 é `/medium`; não comprova tamanho exato do A2 expensive.

## K. Pendências

Aprovar oito limites; validar integrado sob autorização; implementar I2 (CPU por request_id e recortes), sem novo kernel. Persistência atômica não é prova de durabilidade contra falta de energia. Filtro de processos não cobre todo processo possível. Remoção física não demonstra recuperação do host/kernel. Continuação requer predecessor explícito; omiti-lo não resolve uma falha anterior.

## L. Critérios de aceitação

| Critério | Estado |
|---|---|
| Separar execução/limpeza/registros/export/progressão | Implementado e testado em simulação |
| Evitar certificação antes do status/export | Implementado |
| Timer e timeout Docker sob falhas | Testado com falhas simuladas; integração real pendente |
| Fontes parciais e recursos externos | Testado com fakes |
| Prontidão e interrupções rastreáveis | Implementado |
| Regressão histórica | Suite especificada; resultado final informado na entrega |
| Preservação científica/dados | Sem mudanças nesses componentes |
| Limites definitivos e liberação A1/A2 | PENDENTES; não liberados |

## M. Estado final

Commit e estado da árvore informados na entrega. Sem push; somente arquivos operacionais, testes e documentação modificados.

## N. Próximo passo

Revisar certificado e limites; autorizar I2; depois autorizar validação integrada. Não executar A1/A2 nesta tarefa.
