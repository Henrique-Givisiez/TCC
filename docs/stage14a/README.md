# Stage 14A — preparação conservadora

**Campanha científica NÃO liberada.** Nenhum BASELINE, CALIBRATION ou TEST foi executado. O smoke é exclusivamente funcional. O bloqueio metodológico event-level impede afirmar que as regras fundamentais estejam prontas para coleta.

## FROZEN

Protocolo `experiments/protocols/stage14_protocol.json`, `stage14-balanced`, versão 1, `FROZEN_DESIGN_PENDING_RELEASE`, SHA256 `79b204d7d781a939de7a95ab77b8e98ccbd15b5fe250fa237e0db1d0e7fa9e13`. Bytes e schema conferidos antes da preparação; original preservado. Referências documentais são verificadas pela auditoria de preservação.

Mantidos /medium; 4 benignos × 2 RPS; 1 atacante × 8 RPS ativo; uma vítima; autoscaling desligado; containers e proxy NGINX; Δ=1 s. C contínuo e P burst 2 s/período 6 s: mesma taxa ativa, volume médio diferente deliberadamente. Nenhuma equalização ou interpretação de eficácia.

Z-score assinado, ddof=1, baseline benigno independente, sem threshold. CoV causal, ddof=1, L=6 principal e L=3/12 sensibilidade, null reseta histórico, sem baseline externo/threshold. Nenhum detector novo.

## MATERIALIZED

[Plano completo](materialized/campaign_plan.json), [matriz de 66 linhas](matrix.csv), 66 configurações validadas em `materialized/configs/`, [hashes](materialized/hashes.json). A ordem é baseline, calibration, test; seeds na ordem abaixo; cenários B e tríades B/C/P. Essa é ordem planejada, independente de resultados, não otimizada por desempenho.

O procedimento preexistente foi reutilizado: SHA256 de UTF-8 `stage14-balanced-v1-seeds:partition:index`, índice inicia em zero por partição; primeiros 4 bytes como inteiro unsigned big-endian; incrementa índice sempre; rejeita seeds piloto e qualquer seed já aceita. Sem RNG externo ou consulta a resultados. Duas materializações independentes reproduzem todos os bytes, inclusive hashes/configurações.

- BASELINE: `386892579, 15825709, 556499976, 678133177, 1027200967, 774915721`.
- CALIBRATION: `250861660, 1935927024, 688216134, 3772247283, 2534925364, 2465454157, 1258649561, 1476838592, 2587138917, 1882561902, 3313573378, 4091289086`.
- TEST: `171864802, 2617993097, 4207362430, 3751420894, 3321204838, 1145928936, 3205651767, 1156532787, 258231394, 4052934802, 1511736727, 3145659914, 1214769380, 1981484633, 1488329317, 814930163`.
- Smoke/development: `2535420249` (fit_B independente), `1027529830` (score_B), `2443054165` (score_C), `1414720965` (score_P). Todas excluídas das partições científicas e piloto.

Seeds smoke: SHA256 de UTF-8 `stage14a-smoke-development-v1:index`, índice a partir de zero, primeiros quatro bytes big-endian; rejeita piloto, científicas e smoke já aceitas. Atribuição fixa fit_B/score_B/score_C/score_P. Cada run dura 30 s: PRE8/EVENT_POSITION12/POST10. Fitting de desenvolvimento [4,30), definido antes da execução, não substitui fitting científico. Nenhuma seleção de feature/threshold/direção/eficácia.

**O sidecar não altera o protocolo v1, cujo seeds.status permanece DEFERRED.** Não foi publicada revisão do protocolo nem relaxado o gate TEST. Antes da coleta é necessária revisão explícita que vincule este plano e resolva o conflito metodológico. O plano não é autorização de execução e o módulo de preparação não tem executor científico.

## VERIFIED — políticas temporais e evento

`select_interval` inclui somente `48 <= window_start` e `window_end <= 240` para fitting científico: 192 janelas Δ1 por run antes de excluir null. Os testes preexistentes verificam os limites exatos, cauda, null e pooling. Stage 10 continua preservando a série e sua cauda; não foi modificado. Scoring mantém a série completa por FROZEN.

TEST: `primary_evaluation_horizon=whole_windows_within_planned_run_duration` já é FROZEN, portanto implica [0,144) com janelas inteiramente contidas. Isso não autoriza a cauda como benigno. O executor/avaliador científico ainda precisa aplicar e persistir essa seleção; não existe avaliação completa pronta no framework.

CALIBRATION: duração 360 s explícita e limite final coerente com horizonte planejado; o início de seleção para calibração não está explicitamente definido. `[48,360)` é recomendação técnica: remove o mesmo warm-up físico de baseline, inclui somente janelas inteiras e exclui cauda. Não foi congelado, aplicado a dados científicos ou inserido silenciosamente no protocolo. Especificar também que histórico causal de CoV segue desde o começo do run, sem reset artificial no início do horizonte; a seleção controla exposição/calibração, sem cortar Stage 10. Isso requer aprovação e contrato de seleção antes de calibrar.

[Diagnóstico sintético](event_semantics_diagnosis.json): implementação atual exige overlap positivo E=[actual_start,actual_end) **e** disponibilidade em [actual_start,actual_end]. No exemplo E=[10,10.5), janela [10,11), decisão 11, retorna detected=false. Contraria o comportamento solicitado (detected=true, delay=1 s). Alarmes anteriores e evidência inteiramente anterior são corretamente recusados. Um caso comum iniciado em 10.4 com decisão em 11 produz delay=0.6.

A causa está congelada em `frozen.event_truth.policy=global_overlap_and_availability_within_event_v1` e `availability_deadline=actual_end_inclusive_no_post_event_grace`, espelhados no validador e testes Stage13C. Corrigir só o código violaria o protocolo. **Não foi corrigido.** Recomendação para revisão: elegibilidade por overlap positivo da janela observada, disponibilidade usada no delay causal; explicitar eventual limite operacional de disponibilidade e censura, sem exclusão automática em actual_end. Versionar policy/protocolo/validador/testes juntos. PeriodicBurst permanece um evento global, inclusive silêncios; não existe `burst_active`.

## UNRESOLVED

Direções Z-score/CoV; thresholds; orçamento de falso positivo; detalhes de incerteza; eventual confirmação/histerese; liberação formal de TEST. Nada foi escolhido com smoke ou TEST. O lock observado está materializado, mas o campo original `exact_image_and_environment_lock` continua UNRESOLVED até revisão vinculante. O horizonte inicial de calibração e a política revisada de evento exigem decisão explícita.

## BLOCKERS antes da Stage 14B

1. Aprovar correção do contrato FROZEN event-level, com policy versionada, limite/censura coerentes e testes da última janela sobreposta. O comportamento atual não atende ao pedido.
2. Aprovar e registrar horizonte de calibração (proposta [48,360)); implementar seleção/denominadores auditáveis para calibração e avaliação TEST [0,144), preservando scoring completo e Stage 10.
3. Publicar revisão encadeada do protocolo que vincule seeds/plano e lock de ambiente/imagens. Original v1 permanece DEFERRED e loaders científicos ainda recusam vínculo sem seeds no protocolo.
4. Integrar protocol reference/configuração efetiva ao futuro executor científico. TEST segue bloqueado até freeze de modelos/features/parâmetros/policies e implementação de release auditável. Essas decisões finais não precisam ocorrer usando dados TEST.

## Custos previstos (não medidos pelo smoke)

| Partição | Runs | Duração/run | Total nominal |
|---|---:|---:|---:|
| BASELINE | 6 | 240 s | 1440 s |
| CALIBRATION | 12 | 360 s | 4320 s |
| TEST | 48 | 144 s | 6912 s |
| Total | 66 | — | 12672 s = 3 h 31 min 12 s |

Estimativas preexistentes da proposta B (`docs/stage13b-protocol-proposals/cost_estimates.json`): operação 13601.32 s ≈ 3 h 46 min 41 s; com reserva de 20% 16321.58 s ≈ 4 h 32 min 2 s. Aquisição ≈967 MiB; scores ≈27.3 MiB; total com metadata ≈1143.5 MiB (1.12 GiB); orçamento com folga ≈1715.2 MiB (1.68 GiB). Escala aproximada baseada no piloto e overhead de startup/teardown; não é intervalo de confiança nem promessa de tempo/espaço. Não houve reexecução histórica ou alteração do desenho por custo.

## Reproduzir preparação e comandos executados

- Inspeção: `git rev-parse HEAD`, `git branch --show-current`, `git status --short`, `sha256sum experiments/protocols/stage14_protocol.json`, leituras com `rg`/`cat`/`sed`, Docker version/info/context/ps/images, processos do host.
- Materialização: `.venv/bin/python -B -m experiments.stage14a.prepare --output docs/stage14a/materialized`. Para reproduzir usar outro diretório novo; existente é recusado.
- Ambiente: `.venv/bin/python -B -m experiments.stage14a.environment --output docs/stage14a/environment_pre_smoke.json` (e captura final em arquivo novo).
- Smoke: `.venv/bin/python -B -m experiments.stage14a.smoke --output experiment_results/stage14a-smoke-development`. Não reexecutar sobre outputs existentes.
- Testes específicos: `.venv/bin/python -B -m unittest tests.test_stage14a -v` (5 passaram).
- Suíte: `.venv/bin/python -B -m unittest discover -s tests -v`. A tentativa inicial sem `-s tests` descobriu zero testes e retornou 5; corrigida, não considerada validação.
- Diagnóstico sintético reutilizou fixture `OriginalEventTests.run_event` com validação mockada somente para isolar aritmética; não é evidência operacional de detecção.
- Auditoria por SHA256 dos arquivos preexistentes, hashes dos novos artefatos e `git diff --check` ao final. Nenhum commit/push/reset/checkout/pull/merge/rebase.

## VERIFIED — execução, ambiente e preservação finais

O pipeline funcional passou nos quatro runs de 30 s, incluindo fit_B independente e score_B/C/P: simulação → exportação Stage8 → validação Stage9 elegível → extração Stage10 Δ1 → carregamento Stage11. Foram produzidos **60 artefatos de scores** (3 alvos × 5 features × Z-score/CoV-L6/L3/L12), todos com pelo menos um score disponível. Isso demonstra operação do caminho de software, sem evidência científica de qualidade dos métodos. Nenhuma decisão, threshold, Precision/Recall/F1/Accuracy, ranking ou comparação de eficácia foi produzida.

[Resumo smoke](smoke_summary.json), [hashes de todos os outputs smoke](smoke_hashes.json). Originais em `experiment_results/stage14a-smoke-development/` (ignorado pelo Git, preservado no disco). Plano/configs/logs/raw/datasets/validation/features/models/scores separados dos dados históricos e científicos. São 4 runs de desenvolvimento, adicionais aos 66 apenas planejados; **zero dos 66 executados**. O ajuste benigno adicional foi escolhido antecipadamente para manter independência do Z-score, não em resposta a resultados.

O loader event-level original verificou hashes, manifests Stage8/10, evidência Stage9 e clocks. fit_B e score_B têm zero eventos; score_C e score_P têm exatamente um evento global cada. Nenhuma atribuição event-level científica foi calculada no smoke. O contrato de última janela continua incorreto em relação ao pedido e bloqueado pelo FROZEN, conforme diagnóstico acima.

[Ambiente pré-smoke](environment_pre_smoke.json) e [ambiente final](environment_final.json): Ubuntu 24.04.1 LTS nativo, kernel 6.11.0-29-generic, x86_64, Intel Core i7-1255U, 12 CPUs lógicas, memória total 16479375360 bytes; disponibilidade instantânea e swap registrados em meminfo/free. Python e versões instaladas exatas em pip freeze, client/server Docker Engine Community 28.0.4, contexto default, overlay2, cgroup v2. Não houve migração de ambiente. IDs de imagens, RepoDigests, receitas e hashes de módulos/configurações/protocolo registrados. Imagens observadas: target `sha256:f5dddaaf9858766170a3e32d9e8b6c045fc1c8396a2c1346a49f16a11c3ed39b`, sources `sha256:1ca696d06f03641e23e2f02285f0a9c2eeb3dd484f2ad945f8eb2fbf0488d41a`, nginx `sha256:c318e336065b17ff460aeac6d14bce5d0b13e35f25d5cb1843b635359fc00c9a`. O registro não atesta identidade de receitas e bytes de uma imagem reconstruída; vincula imagens realmente observadas e receitas atuais separadamente.

Git HEAD inicial/final `1e6cbf13ccfd2c2de453186325f64b584e724fe5`, branch `refactor/project-organization`. Árvore limpa antes da primeira escrita; [registro inicial](git_initial.json) distingue a observação inicial da captura imediatamente após criar arquivos de auditoria. Ao final há somente novos arquivos untracked da Stage14A em `docs/stage14a/`, `experiments/stage14a/` e `tests/test_stage14a.py`; nenhum diff tracked. Smoke está em diretório ignorado, sem adição forçada ao índice. Nenhum commit ou operação de sincronização/descarte.

[Preservação anterior](preservation_before.json) e [verificação posterior](preservation_after.json)/[auditoria final](completion.json): **18.590 arquivos preexistentes conferidos, zero modificados ou ausentes**, incluindo históricos, código Stage8–10, datasets, outputs e artefatos transitórios da raiz. `proxy_artifacts` antigo permaneceu intocado; o runner usou um caminho novo por run. Nenhum histórico reexecutado.

Suíte completa: **300 testes passaram**, sem falhas, via discover -s tests; [log integral](tests_full.txt). Testes novos cobrem o plano determinístico e seus contratos. Diagnóstico event-level é sintético e separado de scoring/ground truth smoke. `git diff --check` passou. Capturas host antes/depois registram Docker ps vazio; em ps, nenhum tcpdump, simulador ou gerador de tráfego residual (somente o próprio processo Python da captura). Não existem simulações concorrentes.

Resposta ao objetivo: **materialização e operação de desenvolvimento verificadas; regras científicas ainda não prontas para iniciar coleta sem revisão fundamental**. Os blockers listados precisam ser resolvidos explicitamente antes da coleta Stage14B; o smoke não os resolve e não autoriza decisões científicas.
