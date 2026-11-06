# I1 — base operacional exploratória

## A. Estado inicial

Branch `refactor/project-organization`, HEAD `c4dfa55cfd0c87b8828be9121cb98e63d3caa9d4`, árvore limpa.
Inspeção somente de leitura do Docker confirmou disponíveis:

- Vítima: `sha256:3f0a418c93db324644b86f06f99b604f6aa0c833faf27abea8a3d484234f3c09`.
- Fontes: `sha256:b8e3996d9b73a155efc59fef7a33510d33187acf6e4eca488600ed28f26d453c`.

A versão 3.9.23 da vítima é evidência histórica de `reports/diagnostic_observability_20261104/runtime_audit.json`, não uma nova execução na imagem. Nenhum contêiner foi iniciado.

## B–D. Arquitetura, alterações e imagens

Reutiliza `diagnostic_run` → `run_recorded` → `main_orchestrator` → `source_experiment`.
O argumento opt-in `--operational-policy JSON` instala I1. Nesse modo os dois argumentos de imagem exigem IDs sha256 completos preexistentes. Resolve, compara, executa pelos IDs e verifica `container.attrs['Image']`. Não constrói nem baixa imagens. Fora desse modo o comportamento histórico continua disponível.

`simulator/exploratory_operations.py` contém política, prontidão, observações e cleanup de IDs próprios. Não é um executor independente. `source_experiment` recebe contexto opcional; a política científica/StressManager não foi alterada.

## E. Limites e pendências

O JSON aceita os campos abaixo, todos obrigatórios, positivos e finitos. Nenhum valor é preenchido silenciosamente. Ausência bloqueia execução.

| Campo | Referência histórica e decisão necessária |
|---|---|
| min_available_bytes | Guard histórico 2 GiB; aprovar reserva para o host atual |
| min_disk_bytes | Histórico 4 GiB; aprovar considerando exports e espaço atual |
| victim_memory_bytes | Histórico 1 GiB; aprovar orçamento |
| source_memory_bytes | Histórico 512 MiB/fonte; aprovar orçamento |
| max_artifact_bytes | Histórico 512 MiB/run de até 20 s; NÃO transportar automaticamente para 60/150 s |
| collection_max_age_seconds | Histórico 5 s; aprovar com polling efetivo |
| global_timeout_seconds | Histórico duration+90; exige > nominal+35 s para reservar setup/drenagem |
| docker_timeout_seconds | Cliente externo histórico 3 s; aprovar para operações Docker |

Versão suportada: `exploratory-I1-v1`. CPU, HTTP lento/falhas e espera por worker não são motivos de interrupção. Memória, disco, artefatos, OOM/restart, identidade e coleta essencial podem interromper. Observação ocorre a cada tick do runtime; configurar tick adequado (histórico 1 s). Coleta verifica persistência e avanço do timestamp Docker no cache; não certifica todo conteúdo persistido.

## F. Encerramento e prontidão

Timeout usa SIGALRM/ITIMER_REAL no processo principal Linux; timer anterior ativo é recusado. Abrange setup e geração no runtime. Ao entrar na finalização o timer é desarmado para não interromper a drenagem; permanecem budgets existentes (30/35 s fontes, captura e stop Docker) e timeout da API. Não é garantia de wall time rígido da finalização/exportação sob falhas do SO/daemon.

Falhas de captura/coletor não impedem tentativa das demais etapas. Coletor ainda vivo após join é falha. Remoção adicional alcança somente IDs registrados nesta execução, incluindo fontes de setup parcial. Nunca limpa recursos alheios. Redes criadas pelo runtime seguem seu cleanup existente.

Prontidão recusa contêineres ativos, fontes/vítimas residuais, processos do filtro histórico e redes experimentais ocupadas; consulta de verificação falhando bloqueia. Não há espera de 60 s usada como substituto da inspeção. Redes preexistentes vazias são permitidas; não são redes temporárias próprias residuais.

Nas continuações fornecer `--previous-run DIRETORIO_I1`; falha essencial anterior bloqueia. A omissão desse argumento não comprova resolução de uma tentativa anterior: a sequência autorizada deve vincular explicitamente o predecessor. Falha exige diagnóstico antes de nova autorização, sem editar o registro anterior.

## G. Proveniência

`effective_config.json` e `run_provenance.json` continuam existentes. `operational_policy.json`, no mesmo raw e exportado pelo exportador existente como evidência, registra versão/limites/imagens, prontidão, recursos observados, ações, duração e cleanup. Configuração efetiva registra fontes, taxa, endpoint, concorrência e workers. Journals e status mantêm os tempos HTTP/eventos e encerramento global. Ausência do relatório final significa verificação não concluída, nunca aprovação implícita.

## H. Compatibilidade

Testes representam M_A/E_A/E_B/M_B: 2×1 RPS, 4 threads, 60 s, endpoints medium/expensive; e L2/L6/L3/L7: 2/4 fontes, 16/32 RPS agregados, 64 threads, 150 s. Dois workers, diagnóstico ON, direto e sem ataque. Não foram criadas seeds/configurações executáveis nem executados ensaios.

## I. Testes

Suite unitária I1 e regressões diretas/diagnósticos/configuração/capacidade/fontes/captura/exportação: 93 testes aprovados na revisão intermediária. Usam mocks/fakes; mensagens de build/tcpdump são simuladas. Ver relatório final da implementação para última rodada. Integração real não realizada.

## J–K. Pendências e aceitação

Mecanismos implementados e verificados em unidades; liberação operacional PENDENTE de aprovação dos limites, revisão dos relatórios e validação integrada autorizada. Continuidade exige predecessor explícito. Não há watchdog externo independente nem prova universal de repouso do host; filtro de processos tem alcance conhecido. Drenagem HTTP não certifica término do trabalho computacional.

## L–M. Estado final e próxima etapa

Commit informado na resposta da implementação; sem push. Próximo escopo: processamento A2 por request_id (CPU ausente/duplicada/finita/positiva, razões por repetição), recortes A1 [0,30)/[30,150), e validação ponta a ponta autorizada. Kernel, geradores, detectores, features, autoridades e dados históricos preservados.

## Revisão I1.1 — substitui a certificação original

`cleanup_verified` descreve apenas verificações físicas de recursos próprios e threads/capturas. `run_status.json` continua sendo a fonte do estado do simulador. Durante finalização, `certification=pending` e `progression_allowed=false`; `finish()` nunca autoriza continuidade.

O entrypoint tenta exportação mesmo após falha do runtime, preserva a exceção original e registra falhas secundárias. Somente após essa tentativa `certify()` verifica os registros essenciais, o status canônico, o manifest exportado e a prontidão pós-limpeza. Uma execução incompleta pode ter limpeza confirmada, mas não constitui procedimento aceito. Falhas essenciais exigem diagnóstico antes de continuidade. `--previous-run` agora exige certificado final e hash do status inalterado; relatórios I1 antigos sem esse certificado não são aceitos automaticamente.

O export preserva um snapshot operacional ainda pendente. O relatório operacional final fica no raw e vincula por hash o status canônico e o manifest exportado. Não se reescreve o dataset para fingir que sua certificação posterior já existia no snapshot. A certificação não equivale à reconciliação A1/A2, não aprova CPU/op e não altera os estados científicos.

O timer é armado dentro do bloco protegido. Alterações parciais de handler/timer são registradas; o desarme tenta cancelar e restaurar independentemente. Falhas são retidas sem impedir as demais tentativas de cleanup. Restauração do timeout Docker também é independente. Fontes são registradas imediatamente depois da criação, antes de reload/inventário/readiness. Veja o relatório `implementation_I1_1.md` para limites, testes e pendências.
