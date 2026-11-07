# B1.1 — Entrega 2: ciclo computacional da vítima

## Estado inicial e arquitetura

Branch refactor/project-organization, HEAD a6acfd17226a6fbbaf5a1b8f407ec7abd7d3fe35,
working tree limpo. ThreadingHTTPServer e ProcessPoolExecutor persistente foram
preservados. Antes, os timestamps computacionais só chegavam ao diagnóstico no
handler_finished. Timeout no cliente não cancelava o trabalho; continua assim.

## Identificação declarada

RequestLogger.instrumentation_headers propaga X-Edos-Run-Id, Source-Id,
Request-Id, Event-Id e Traffic-Class. Para ataques, Attack-Mechanism declara
computational_asymmetry (/expensive), http_request_flooding (/medium) ou unspecified.
O mecanismo é declarado no cliente; a vítima não infere classe pelo endpoint.
A classe observada é unknown se faltarem run/request ou a classe for inválida;
attack também exige event_id. Source-Id ausente continua ausente, sem invenção.
Essas declarações são instrumentação experimental, não autenticação: devem ser
correlacionadas com o inventário e request_log do mesmo run. Benign e flooding
podem usar o mesmo /medium. Cada handler recebe operation_id UUID próprio.
Requisições de setup sem identificação permanecem unknown.

Os dois geradores mudaram exclusivamente os cabeçalhos. Distribuição, taxa,
concorrência, timeout e contrato [S,E) não mudaram. Metadados acrescentam bytes e
algum overhead de instrumentação; não se afirma overhead nulo. Kernel de CPU,
custos dos endpoints e número de workers permanecem iguais.

## Eventos e persistência

Reutiliza DiagnosticWriter, capacidade configurável (4096 por padrão) e caminho
raw/diagnostics/victim/events.jsonl. Todos os eventos possuem sequence crescente
no escritor; gaps, dropped/write_errors e resumo ausente impedem afirmar integridade.
Novos campos são aditivos; nenhum cabeçalho CSV científico foi alterado.

- handler_started: recebimento pelo handler, identidade declarada e endpoint.
- work_submitted: submissão aceita pelo executor; timestamp antes de submit.
- work_submission_failed: submissão recusada, exceção explícita, sem trabalho aceito.
- work_started: worker entrou no wrapper, antes do kernel computacional.
- work_completed: kernel terminou, mesmo com cliente desconectado; inclui CPU/op
  e timestamps históricos preservados.
- work_failed: exceção de execução; é terminal com falha, não conclusão bem-sucedida.
- work_execution_unresolved: cancelamento inesperado ou BrokenProcessPool; não
  inventa término computacional e marca a observação incompleta.
- handler_finished: tentativa de resposta terminou, com erro/status quando disponível.
- computation_observation_closed: corte monotônico, balanços por classe, lista de
  pendências, prefixo IPC esperado/recebido, perdas e erros de observação.

Workers usam Queue multiprocessing limitada, put_nowait, sequência compartilhada
sob lock e contador explícito de perdas. Não escrevem arquivos nem usam locks do
escritor. Uma thread no processo HTTP consome IPC e usa o escritor existente.
Início e término chegam independentemente do retorno HTTP; a ordem de persistência
pode diferir da ordem temporal entre processos. worker_sequence identifica o
prefixo IPC; sequence identifica a ordem de persistência. Não deduzir duração da
ordem física das linhas: usar timestamps e transições por operation_id.

Exportação recursiva já existente preserva events.jsonl e events.summary.json em
evidence/other/diagnostics/victim/, com hashes do manifesto. metadata.json registra
schema computacional 1, origem global, relógios, código e imagens.

## Relógios e balanços

Timestamps são CLOCK_MONOTONIC locais. Worker_clock acompanha os eventos; namespace
worker/servidor divergente torna a observação incompleta. A associação ao E global
exige os certificados existentes victim_clock_validation.json, metadata.json e
origem monotônica do run; não se assume sincronização perfeita de contêineres.
Sem certificado válido, analisar tempos internos e declarar residual em E indeterminado.

Por classe: submitted = waiting + running + completed + failed;
started = running + completed + failed; pending = waiting + running.
Submission_failed fica fora das submissões aceitas. Erros de transição/duplicações
não são mascarados como contagens válidas. Uma falha abrupta de worker pode deixar
operação sem estado terminal conhecido: é observação tecnicamente incompleta.

computational_state é um redutor de eventos, não analisador B1.2/B2. Permite consultar
contagens em instantes da vítima, após conversão justificada de E. work_completed
após E identifica conclusões residuais. Para procurar o primeiro zero pendente,
reaplicar o redutor nas transições relevantes, respeitando a cobertura disponível.

## Horizonte e drenagem

O fechamento não aguarda o esvaziamento do pool. Captura a sequência IPC sob lock,
impede novas admissões na observação e espera no máximo 1 s pelo prefixo capturado.
Emite snapshot antes de fechar o escritor; callbacks posteriores ficam fora do
horizonte. Funções HTTP fora desse horizonte continuam processando, sem inventar
telemetria dentro do horizonte. O timeout externo existente de fechamento é 3 s;
a parada Docker continua com 5 s. Resumo ausente passa a ser falha explícita.

Snapshot com pending > 0 e observation_complete=true é evidência válida de trabalho
não drenado no corte. Não torna automaticamente o run inválido. Prefixo ausente,
perda IPC, falha do executor ou escrita incompleta distinguem falha de observação;
o resumo do escritor sinaliza complete=false nesses casos.

O redutor usa três resultados: drained_observed, not_observed,
observation_incomplete. drained_observed exige evidência íntegra, pending ofensivo
zero, ausência de trabalho desconhecido pendente e ingress_closed explicitamente
comprovado pelo chamador. A vítima NÃO prova sozinha ingress_closed: o snapshot
sempre registra false. O chamador precisa reconciliar todas as tentativas ofensivas,
handlers recebidos ainda sem submissão e possibilidades de chegada tardia. Timeout
no cliente, fim lógico [S,E), ausência de respostas ou zero momentâneo não bastam.
Não se afirma drenagem global sem essa prova adicional. Legítimos podem continuar
pendentes quando o ataque é drenado. Recuperação legítima permanece outro conceito.

Se a vítima for interrompida depois de snapshot íntegro com pendências, o horizonte
está documentado como sem drenagem observada. Se a interrupção impedir snapshot ou
prefixo completo, a observação é incompleta. Não há espera indefinida, política de
certificação experimental nova ou proteção por CPU/latência/fila.

## Testes e limitações

12 testes novos em test_victim_computation: pool real local com dois processos,
waiting/running, submissão recusada, exceção no kernel, timeout HTTP local antes do
fim, BrokenPipe, identidade declarada, classes no mesmo endpoint, ausência de
identidade, residual em E, drenagem com legítimos ativos, perdas/duplicações,
fechamento com pendências e exportação byte a byte com hash.

Regressão: 193 testes, 191 passaram. Duas falhas preexistentes:
- GroundTruthTests.test_e_tcpdump_timestamp_unknown_and_final_timeline: unknown/0
  em vez de unknown/1 (já reproduzida na referência anterior).
- ApplicationOperationsTests.test_both_generators_send_paths_and_preserve_seed_and_proxy_boundary:
  mock submit não aceita admission_id; reproduzida em /tmp/cert-baseline.
Os arquivos envolvidos nessas falhas não foram corrigidos fora do escopo.
Após ajuste final da exclusão mútua do corte: 32 testes (vítima + diagnóstico) passaram.
git diff --check passou.

Python 3.12 avisa sobre fork em processo multithread; a arquitetura preexistente
já criava workers com diagnóstico ativo. O piloto deve verificar a inicialização
no runtime da imagem (Dockerfile atual usa Python 3.9), capacidade IPC, overhead e
fechamento. Não foram executados Docker, builds ou campanhas. As imagens antigas
não incorporam automaticamente este código: preparar imagens novas rastreáveis
antes do piloto. Validar também o mount, certificados de relógio e resumo/hashes
após parada real. Classificação de recuperação e executor B1.2/B2 não implementados.
