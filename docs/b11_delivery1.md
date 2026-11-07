# B1.1 — Entrega 1: janela lógica ofensiva

Estado inicial: refactor/project-organization, HEAD
8182681f28e39d74408a7689e11b13c76ef8f2df, working tree limpo.

O produtor contínuo usa o relógio compartilhado do ground truth e respeita [S,E).
Não há catch-up, limite de admissão por vagas ou cancelamento ativo de Futures.
A transição identificada pending -> started/discarded usa o mesmo RLock da parada
 e a mesma amostra temporal usada pelo request_begin. Após autorização, gravação
 e envio podem ocorrer depois de E: início lógico não significa primeiro byte.
Chamadas já iniciadas preservam resposta/erro/timeout e os limites de drenagem.

O caminho de produção contínuo usa admit_continuous e admission_id; as APIs
históricas admit/begin_request e o perfil periódico mantêm suas semânticas.
O gerador legítimo e os cabeçalhos CSV científicos não foram alterados.

## Journal aditivo

admission inclui admission_id e elapsed_seconds. O ID é local à fonte/run.
submitted registra submissão aceita (timestamp imediatamente anterior à chamada
submit; a persistência pode ser posterior ao início da tarefa).
task_started/task_finished registram execução do callable, não HTTP.
DiagnosticExecutor reutiliza admission_id como attempt_id.
request_begin inclui admission_id somente no journal; request_id permanece no CSV.
task_resolution registra decisão started, expired_before_http, before_window,
stopped_before_http ou rejected_before_http e seu timestamp.
Descartes também emitem abandoned_admission com ID/motivo para preservar o balanço
histórico admissions - abandoned == starts. Não criam linhas HTTP.

Balanço: admitidas = iniciadas + descartadas + não resolvidas.
Agregador e validador verificam unicidade de admissões/resoluções, vínculo com
request_begin e ausência de pendências identificadas. Journals históricos sem IDs
continuam legíveis. Incompletude técnica continua bloqueando certificação.
actual_end_seconds continua fechamento efetivo; não é substituído por E.
Drenagem HTTP não prova drenagem computacional.

## Validação e escopo

Testes sem Docker em test_continuous_deadline.py: fronteiras, fila real,
concorrência, parada, rejeição, timeout, identidade diagnóstica e produtor.
Suíte inclui ground_truth, attack_patterns, diagnostics, dataset_validation,
dataset_export e source_containers. A falha
GroundTruthTests.test_e_tcpdump_timestamp_unknown_and_final_timeline foi também
reproduzida em cópia temporária do HEAD inicial; não foi corrigida nesta entrega.

Entrega 2: observação/drenagem computacional da vítima.
Entrega 3: executor protegido e processamento específico das futuras campanhas
(a divisão final dessas entregas depende do planejamento do projeto).
Nenhuma campanha, detector, calibração, commit ou push executado.
