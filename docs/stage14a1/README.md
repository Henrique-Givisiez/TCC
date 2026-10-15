# Stage 14A.1 — fechamento dos blockers antes da coleta

**Pronta tecnicamente para os seis BASELINE da Stage 14B, sujeita à revisão humana. Nenhuma execução científica foi iniciada.** TEST continua bloqueado, sem mecanismo de release. Esta etapa executou somente testes sintéticos/mocks e preflights/dry-run sem simulação; não houve novo smoke.

## FROZEN

- BASELINE fitting: **[48,240)**, somente janelas inteiramente contidas. Pool de observações válidas dos seis runs independentes; sem médias de médias. Null permanece null e é excluído dos momentos pelo fitter existente, sem zero/imputação.
- CALIBRATION: **[48,360)**, somente janelas inteiras. 312 s nominais por run; 12 × 312 = **3744 s = 62,4 min** benignos antes de nulls/indisponibilidades. Essa exposição não sustenta alegações sobre falsos alarmes extremamente raros.
- TEST geral: **[0,144)**, somente janelas inteiras. O papel de [0,48) em determinadas métricas primárias de falso positivo continua UNRESOLVED e deve ser decidido antes do release TEST.
- Seleções pertencem à camada científica posterior. Scoring continua sobre a série inteira; o histórico causal do CoV não reinicia em t=48. Stage 10, cauda e semântica [start,end) permanecem intactos.
- Configurações, 34 seeds científicas, 4 seeds smoke, matriz de 66 runs e ordem são as da Stage 14A. /medium, fontes/taxas/topologia/durações, Z-score assinado/ddof1 e CoV ddof1/L6 principal/L3,L12 sensibilidade permanecem inalterados. C/P mantêm a mesma taxa ativa e volumes médios deliberadamente diferentes. Nenhum novo detector ou threshold.

## CORRECTED — v1 → v2

**V1:** `experiments/protocols/stage14_protocol.json`, Stage13C, SHA256 **`79b204d7d781a939de7a95ab77b8e98ccbd15b5fe250fa237e0db1d0e7fa9e13`**. Arquivo original preservado byte a byte. O preflight Stage14A descobriu, antes de qualquer coleta científica, que o prazo `decision_available_time <= actual_end` excluía a última janela que realmente observou o evento.

**V2:** `experiments/protocols/stage14_protocol_v2.json`, SHA256 **`59f5311e8ee0a05523c80938b7b08ddfaacd0bf8000a077c9de1ab675803872c`**, predecessor v1 explícito. O validador conhece ambas as versões; alterações FROZEN não aprovadas são recusadas. A policy histórica v1 continua disponível explicitamente para leitura/replay metodológico antigo; não é aceita como policy de um run vinculado à v2.

Policy v2: `global_observation_overlap_decision_availability_v2`. Elegibilidade exige decisão positiva, score disponível e overlap **de duração positiva** entre janela W e evento E=[actual_start,actual_end). Intervalos vazios e contato apenas no boundary não contam. A disponibilidade é causal, posterior ao fechamento da janela conforme o contrato de decisões existente, e determina a primeira detecção/delay; não existe veto automático por exceder actual_end.

Exemplo testado: E=[5.2,10.5), W=[10,11), disponibilidade 11 → detecção elegível, **delay=5.8 s**. Uma janela que termina exatamente no início do evento não conta; uma que começa exatamente no fim não conta; uma que fecha no fim após observar o evento conta. Evidência inteiramente anterior, mesmo entregue tarde, não conta e não produz delay negativo. A primeira detecção usa o menor instante de disponibilidade entre decisões elegíveis.

A v2 **não define deadline adicional de disponibilidade**. Uma decisão computacionalmente tardia pode contar se sua observação foi elegível. Miss significa ausência de positivos elegíveis na série fornecida; delay/primeira detecção ficam null, e `censored_at_seconds=null`, sem inventar censura em actual_end nem estimativa de sobrevivência. Essa escolha explícita é necessária para não contradizer a última janela aceita. No caminho científico, a própria observação deve passar pelo horizonte temporal da partição. PeriodicBurst continua **um evento global**, inclusive silêncios. Não existe `burst_active` ou detecção por burst.

As únicas diferenças FROZEN são `event_truth` e a adição de `temporal_selections` explícitas. Seeds passam de DEFERRED a MATERIALIZED com os mesmos valores já publicados. O lock antes unresolved é agora vinculado por referência/hash. Direções/thresholds/TEST não foram liberados.

## MATERIALIZED — vínculos e executor

[Protocolo v2](../../experiments/protocols/stage14_protocol_v2.json), [seed plan](../../experiments/protocols/stage14_seed_plan_v2.json), [matriz v2](../../experiments/protocols/stage14_matrix_v2.json), [environment lock](../../experiments/protocols/stage14_environment_lock_v2.json), [binding](../../experiments/protocols/stage14_binding_v2.json). A matriz contém as 66 configurações e hashes originais, acrescentando role=partition. O protocolo referencia os hashes de seed plan/matriz/lock; o binding referencia todos, inclusive protocolo e plano Stage14A original com hash fixo. Não há ciclo de hashes.

**SHA256 do binding:** `8b542efa2868596eb3a4577b03353c0768d161ed81f9701d5f8466bbac21396f`. Arquivos `.sha256` externos acompanham protocolo e binding. [Inventário final](artifact_hashes.json) lista os demais hashes.

`experiments/stage14_bundle.py` materializa somente em caminhos novos e recusa sobrescrita. Não é executor. `experiments/stage14_scientific.py` executa no máximo uma linha explicitamente selecionada, com dry-run padrão e sem Stage11 automático. A interface exige o hash do binding explicitamente revisado, além de partição e número global da matriz: BASELINE 1–6; CALIBRATION 7–18; TEST 19–66 (bloqueado).

Dry-run real já executado, sem `--execute`:

```bash
.venv/bin/python -B -m experiments.stage14_scientific \
  --binding-sha256 8b542efa2868596eb3a4577b03353c0768d161ed81f9701d5f8466bbac21396f \
  --partition baseline --run 1 \
  --audit-output docs/stage14a1/baseline_01_dry_run.json
```

O output de auditoria deve sempre ter nome novo; o arquivo acima já existe. **Não acrescentar `--execute` antes da revisão humana.** Para uma execução futura autorizada, essa flag seleciona exatamente uma linha. Não existe execução de campanha em lote ou release automático de TEST.

Antes de simular, o executor verifica hashes/identidades, seeds e role/scenario, configuração e hash, ambiente e ausência de concorrência/output. Revalida as referências e hashes de runtime imediatamente antes da chamada. Usa lock exclusivo de host entre invocações e reserva atomicamente o diretório determinístico `experiment_results/stage14-scientific-v2/<order>_<partition>_<seed>_<scenario>`. Não permite output arbitrário, reuso ou sobrescrita. Seeds/configs não são argumentos livres na CLI. BASELINE/CALIBRATION exigem B sem ataque; TEST é recusado inclusive no dry-run, sem abrir tabelas científicas.

`scientific_run_before.json` contém UUID de execução, configuração planejada e resolvida com defaults, role, linha, partição/cenário/seed, referências/hashes, protocolo, timestamps, Git HEAD/branch/status e ambiente observado. O `run_id` interno Stage8 é criado pelo simulador existente; ao terminar, o metadata liga esse ID ao UUID prévio e à configuração/experiment_id. Não foi alterado o gerador histórico de IDs.

O backend futuro roda simulação → exportação Stage8 → validação Stage9 → extração Stage10 Δ1. Exige status completed, configuração efetiva igual à planejada resolvida, elegibilidade Stage9, run IDs/hashes de lineage concordantes, rede observável e janela/duração planejada corretas. `scientific_run_after.json` registra status, erros se houver, timestamps, referências Stage8/9/10 e hashes dos outputs. Falhas preservam a reserva, o metadata anterior e todos os artefatos parciais; não há replay automático. Resultados ficam prontos para consumo Stage11 pelo caminho `stage10`, com vínculo de protocolo disponível no metadata e APIs `load_campaign_series`/`bind_source`. O fitting posterior continua sendo ação separada sobre os seis benignos.

Seleções v2 em `analysis/detection/horizons.py`: trabalham sobre observações/scores/decisões/labels já autorizados, sem IO de verdade. Calibração aplica [48,360) **antes do callback calibrador**, após scoring causal completo, e persiste a seleção no artefato. Avaliação aplica o horizonte da partição a scores/decisões/labels alinhados; atribuição de eventos também restringe janelas observacionais quando vinculada à v2. O helper de seleção não concede release TEST: gates existentes continuam recusando carregamento/análise TEST.

## Ambiente: divergências fatais e registradas

Lock nativo observado: Ubuntu 24.04.1 LTS, kernel 6.11.0-29-generic, x86_64, Docker Engine 28.0.4 no contexto default; versões exatas Python/dependências/imagens/receitas/runtime estão no JSON. O lock observa o ambiente dirty real; não declara clean nem exige commit.

Fatais: divergência de OS/version/kernel/arquitetura/Python/dependências, Git HEAD, bytes de código científico/receitas/runtime, versões client/server Docker, daemon/Engine OS/kernel/driver/cgroup/context, IDs/RepoDigests de imagens; ausência de evidência consultável; containers/processos de simulação/tráfego/captura concorrentes. Kernel/software/imagens são conservadoramente fixados por influírem na captura/semântica numérica/execução. Docker Desktop e contexto diferente de default são recusados.

Somente registradas: branch e status dirty (mas alterações em código continuam fatais pelos hashes), CPU/modelo/contagem, RAM total/disponível, carga, PIDs, relógio e localização do Python. Hardware não é tratado como invalidação automática. Uma divergência fatal produz preflight rejeitado e impede backend; a execução registra o audit de divergência fora da árvore científica. Falha de consulta impede preflight com erro explícito. **Nunca atualiza o lock silenciosamente.** Mudanças reais de software/HEAD exigem revisão explícita de lock/binding/protocolo, não bypass.

## VERIFIED

- **339 testes passaram**, incluindo **39 novos**: [suíte completa](tests_full.txt), [novos](tests_new.txt). Testes cobrem os oito casos event-level, primeira disponibilidade, série persistida com última janela parcial, hashes/tampering inclusive matriz rehashada, role/seed/cenário/config divergentes, output existente, TEST bloqueado, ambientes fatais/dinâmicos, lineage e falha do backend mockado, limites/cauda/null, calibração causal e seleção de avaliação. Testes de fitting agrupado, ddof1, baseline independente e guardas contra labels continuam passando.
- [Dry-run CLI BASELINE 1](baseline_01_dry_run.json): `dry_run_ready`, zero divergências fatais. [Seis preflights BASELINE](baseline_six_preflight.json): todos aceitos em memória, sem reservar output, sem invocar simulação. Backend real não foi acionado; teste de integração de execução usou mocks em diretórios temporários removidos pelos testes.
- [Preservação inicial](preservation_before.json), [final](preservation_after.json): **18.585 dos 18.590 caminhos originais mantêm bytes idênticos**. As **cinco alterações de fonte/teste autorizadas** são listadas abaixo, e seus bytes originais foram preservados/verificados contra os hashes antigos em [arquivo histórico](authorized_source_before.zip). Não seria correto declarar os cinco caminhos atuais inalterados. Os 18.590 originais continuam disponíveis entre caminhos intactos e arquivo histórico.
- **911 arquivos smoke e 87 arquivos Stage14A permanecem byte a byte intactos**, além de todos os datasets/outputs históricos. Nenhuma alteração nos módulos Stage8–10. Nenhum histórico ou smoke reexecutado.
- [Ambiente inicial](environment_initial.json) e [final](environment_final.json): containers ativos=[], processos residuais de simulação/tráfego/tcpdump=[]. Não existe árvore `experiment_results/stage14-scientific-v2` nem lock de execução científica criado nesta etapa.
- `git diff --check` passou. Zero execuções científicas; zero novos dados científicos; nenhum commit/push/reset/checkout/pull/merge/rebase.

Arquivos preexistentes modificados: `analysis/detection/protocol.py`, `analysis/detection/evaluation/events.py`, `analysis/detection/evaluation/__init__.py`, `analysis/detection/pipeline.py`, `tests/test_stage13c.py`. Os testes antigos que montavam uma versão2 hipotética foram atualizados para fornecer os campos v2 agora efetivamente obrigatórios; testes históricos da policy v1 continuam intactos semanticamente.

Criados: `analysis/detection/horizons.py`, `experiments/stage14_scientific.py`, `experiments/stage14_bundle.py`, `tests/test_stage14a1.py`, sete arquivos `experiments/protocols/*_v2.{json,sha256}` e auditorias/documentação em `docs/stage14a1/`. Nenhum arquivo Stage14A foi reescrito.

Git HEAD inicial/final **`1e6cbf13ccfd2c2de453186325f64b584e724fe5`**, branch **`refactor/project-organization`**. As mudanças locais Stage14A anteriores continuam untracked; os cinco arquivos acima têm diff tracked, e os novos arquivos desta etapa estão untracked. [Estado inicial](initial_git.json), [estado final e checks](completion.json). Nenhum arquivo foi adicionado ao índice.

Comandos principais: inspeção Git/SHA256/Docker/processos; snapshots em Python; `.venv/bin/python -B -m unittest tests.test_stage14a1 -v`; `.venv/bin/python -B -m unittest discover -s tests -v`; `.venv/bin/python -B -m experiments.stage14_bundle`; CLI dry-run acima; preflight somente metadados dos seis BASELINE; comparação SHA256/arquivo original; `git diff --check`. Nenhuma chamada CLI com `--execute`.

## UNRESOLVED

Direções Z-score/CoV; thresholds; orçamento de falso positivo; confirmação/histerese; detalhes finais de incerteza; papel de TEST [0,48) em determinadas métricas de falso positivo; freeze dos modelos/features/parâmetros/policies e release formal TEST. Essas pendências **não impedem a coleta benigna BASELINE** e não foram decididas com smoke ou TEST.

## BLOCKERS

Nenhum blocker técnico identificado para coletar os seis BASELINE com esta versão/lock. A revisão humana solicitada permanece pendente, portanto **a Stage14B não foi iniciada e não está autorizada automaticamente**. Mudança fatal de ambiente/código/HEAD antes da execução volta a bloquear o preflight até revisão explícita. TEST continua bloqueado independentemente da revisão dos BASELINE.
