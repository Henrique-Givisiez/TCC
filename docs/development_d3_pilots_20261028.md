# D3 — preparação operacional dos três pilotos

Estado: **preparado offline, não executado**, em 28/10/2026. Autoridade própria em [manifest.json](../experiments/protocols/development_d3_pilots_20261028/manifest.json), derivada da [proposta D2/D3](development_d2_closure_d3_proposal_20261028.md). Nenhum Docker, preflight real ou experimento foi executado nesta preparação. Artefatos e utilitários anteriores foram preservados; as adaptações ficam em módulos novos. Detectores, calibração e matriz comparativa não foram alterados ou gerados.

## Configurações, seeds e orçamento

| Piloto | Legítimos | Ataque contínuo | Seed exclusiva | Dependência |
|---|---|---|---:|---|
| C | 4 clientes `/medium`, 4 RPS cada, 16 agregados | Desligado, zero atacantes | 9815791543916838410 | Prontidão própria |
| E4 | Mesmo regime legítimo | 1 atacante `/expensive`, 4 RPS | 12610705592690224256 | C aceito e revisão selecionada explicitamente |
| E8 | Mesmo regime legítimo | 1 atacante `/expensive`, 8 RPS | 17352852899873815260 | Revisão de E4 apta à progressão e selecionada explicitamente |

Somente os [três JSONs completos](../experiments/configs/development_d3_pilots_20261028/) foram materializados e validados por `ExperimentConfig`. Uma vítima, proxy estático, autoscaling desligado, pool=2, timeout=2 s, orçamento de envio=64 por classe (16 por origem legítima e 64 no atacante), monitoramento/poll=1 s, histórico=30 s. D1 sustenta B=16 como candidato com margem; D2 sustenta 4 RPS `/expensive` isolados. Mistura e 8 RPS continuam perguntas dos pilotos.

Seeds derivadas de SHA256 `namespace:label:index`, primeiros oito bytes big endian, com rejeição de colisões. Namespaces distintos para pilotos e reserva da matriz. O [inventário auditado](../experiments/protocols/development_d3_pilots_20261028/seed_audit.json) contém hashes e seeds de 5.066 arquivos históricos, incluindo D1/D2 e autoridades de partições. Um JSON histórico vazio (`previous_preservation_after.json`) é preservado e hash-bound, sem seeds extraíveis. Novo arquivo histórico com seeds ou alteração de fonte auditada bloqueia a validação até revisão explícita.

Reservas futuras **sem configurações**: MATRIX_A=`9634421485314958828`, MATRIX_B=`15153626459498739899`. Cada piloto tem seed própria; comparações com C são referências exploratórias entre seeds distintas, não pareamento da futura matriz. Pilotos nunca entram como réplicas dela.

Tempos mantidos: WARMUP `[0,30)`, PRE `[30,150)`, ACTIVE `[150,270)`, POST `[270,390)`; 390 s nominais, até 30 s de drenagem e ≥60 s de repouso depois do cleanup. C usa as mesmas fases de referência, sem evento ofensivo. Uma origem atacante pode fechar perto de 270 s, antes dos quatro legítimos; seu fechamento é confrontado com a própria janela. O cutoff final é o máximo dos fechamentos **observados**, nunca um término HTTP escolhido ou um timestamp fabricado.

Teto de três tentativas, sem retries/substituições: 1.170 s nominais +90 s de drenagem +180 s de repouso = **24 min** reservados; mais até **10 min administrativos**, envelope dos pilotos de **34 min**. Reserva inclui repouso após a última tentativa. Estouro exige nova revisão, sem repetição automática. Encerramento fora da janela reservada é desvio de protocolo que bloqueia progressão; se os registros estiverem íntegros, conserva-se a observação de serviço.

## Critérios e regra exploratória de recuperação

**C:** em PRE/ACTIVE/POST, aderência agregada 0,8–1,2 e por origem 0,65–1,35; ≥99% 2xx/starts, ≤1% falhas/starts, zero abertas/incompletas/respostas outras, vazão terminal ≥12,8 2xx/s, ≥200 durações 2xx por fase e p95≤250 ms. Os bins extremos de cada fase exigem ≥50 sucessos; queda de vazão ≥20% junto com duplicação de p95 bloqueia aceitação. O limite de 250 ms continua a referência operacional exploratória de D1, não um SLO científico novo. Exigem-se conclusão e fechamento controlados.

**E4/E8:** três eixos separados no relatório: integridade técnica, aderência por classe/origem/fase e degradação do serviço. Critérios benignos aparecem como resultados descritivos; falhas HTTP/transporte, timeouts, maior duração, queda de vazão e requisições persistidas sem término não invalidam automaticamente a coleta. Aderência insuficiente exige diagnóstico de gerador versus pressão do serviço, sem atribuição automática ao endpoint. As mesmas faixas de aderência se aplicam aos legítimos em PRE/ACTIVE/POST e ao atacante em ACTIVE. Registrar starts tardias: limite exploratório `max(4, 1% das starts totais)`.

**Recuperação no POST — escolha exploratória, congelada neste manifesto:** usar quatro bins fixos de 30 s. Um bin só pode qualificar se estiver integralmente observado, começar após o fim **efetivo** da emissão ofensiva, tiver ≥200 starts legítimas, ≥200 durações 2xx conhecidas e nenhuma requisição da coorte sem término até o cutoff. PRE do ataque, PRE de C e bin correspondente de C também precisam de suporte (≥200 starts e durações 2xx).

Em cada bin candidato, exigir simultaneamente:

- sucesso legítimo ≥99% das starts e queda de no máximo 1 ponto percentual em relação a **cada** referência: PRE do próprio ataque, PRE de C e bin POST correspondente de C;
- vazão terminal legítima ≥90% da vazão de **cada** referência;
- p95 2xx legítimo ≤125% do p95 de **cada** referência.

Recuperação é observada ao fechar o **segundo bin consecutivo** qualificado. Reportar o instante de confirmação, não um instante preciso de recuperação. Reter bins posteriores e possível recaída; progressão exige ainda que os dois bins finais qualifiquem. O primeiro bin nominal do POST pode não qualificar se a emissão efetiva terminar alguns milissegundos após 270 s; os limites não são deslocados retrospectivamente para facilitar aprovação.

Sem confirmação até 390 s, marcar `not_observed`, `right_censored=true`, `censor_at_seconds=390`. Se o horizonte realmente observado terminar antes, censurar nesse cutoff. Suporte POST insuficiente impede confirmação e é explicitado. PRE sem suporte ou C indisponível torna a regra `not_evaluable`; falha de coleta produz `unassessable_collection`, sem alegar censura de uma observação íntegra. DRAIN reconcilia conclusões, mas não estende retrospectivamente a janela de recuperação do POST. Sucesso por coorte pode usar conclusões conhecidas na drenagem; vazão usa o instante de término. Essas escolhas não são limiares de detector.

## Processamento, integridade e progressão

[development_d3.py](../experiments/development_d3.py) reaproveita os resumos de serviço por coorte e o validador de datasets existentes, adicionando revisão conjunta. Produz resumos por classe/fase e coortes de 30 s: starts/oferta, términos/2xx por segundo, falhas separadas, durações com n, pendências nas fronteiras, média in-flight do cliente, conclusões cruzadas e CPU/memória/conexões disponíveis por fase. Denominador zero vira null. In-flight e conexões não são fila medida da vítima; p95 dos sucessos deve ser lido junto de falhas e suporte. Suporte de ticks da vítima não certifica frescor de cada leitura Docker.

A reconciliação exige inventário exato de quatro fontes legítimas e uma ofensiva quando habilitada. O índice de worker é interpretado **dentro da classe**: `normal_1` e `attack_1` podem ambos usar índice 0. Para todas as origens, verifica sequência/identidade dos journals, unicidade de begins/finishes/CSV local/agregado, campos de início e término, endpoint, status final, source_closed único e final, drenagem e ausência de encerramento forçado. Rótulos globais reconciliados não são confundidos com contexto local anterior à agregação.

`begin` + linha `incomplete` nos CSVs local e agregado, sem finish, significa **tentativa persistida sem fim conhecido**: `open_without_end>0`, `records_lost=0`; não prova que a requisição ainda esteja rodando na vítima. Finish ausente para uma linha terminal, linha faltante/extra nos CSVs, journal truncado, origem ausente ou fechamento contraditório são falhas de integridade. `logger_complete=false` também pode acompanhar incompletas persistidas: não basta esse flag isolado para concluir perda de registros. Fechamento não controlado bloqueia progressão, independentemente dessa distinção.

Ground truth: C exige tabela de eventos vazia; ataques exigem um evento contínuo com agenda 150–270 s, IDs/âncoras corretos, primeiro/último início e último término compatíveis com as tentativas ofensivas. Eventos locais, último snapshot do journal e evento global precisam concordar. Início/fim efetivos de emissão são distintos de drenagem; drenagem pode ocorrer antes ou depois do fim de emissão. Contexto global de todas as requisições é conferido, inclusive legítimas sob ataque. O validador de dataset verifica também os rótulos de métricas/pacotes; a exportação é confrontada byte a byte com o raw.

Coleta: captura CSV/PCAP com saída aceita, estatísticas finais únicas, zero drops e hash do stderr; relatório de run deve concordar com cada relatório de captura. Por PRE/ACTIVE/POST, vítima e cada fonte do proxy precisam de ≥108 slots úteis/120 e gap≤5 s. Validar identidade e desligamento do monitor. Falha técnica bloqueia a próxima tentativa; preservam-se os dados para diagnóstico.

[development_d3_ops.py](../experiments/development_d3_ops.py) adapta as rotinas de preflight/execução de D1 em um módulo separado, sem mudar suas autoridades históricas. Cada preflight/run é exclusivo de uma entrada. Para E4/E8, exigir `--predecessor-review-sha256` correspondente à revisão apta do predecessor. E8 não prossegue se E4 terminar censurado, sem suporte suficiente, sem fechamento controlado ou com falha técnica/aderência. Mesmo um relatório apto exige revisão humana, cleanup verificado, ≥60 s de repouso e nova prontidão. `run` é uma ação distinta e requer autorização explícita da entrada; nenhum comando faz batch.

O processamento offline futuro usa a ação `review` de `experiments.development_d3`, após a exportação da tentativa. Ela exige vínculo explícito attempt→preflight (ID, caminho, hashes, manifesto e fontes), configurações efetivas, resultado da execução e observação de cleanup. Grava validation, summary e review em caminhos reservados sem sobrescrever. Um returncode não zero é retido como diagnóstico e não prova, sozinho, perda de registros. Nenhum resultado ofensivo ajusta baseline, detector ou calibração: permanece a calibração benigna por regime legítimo declarado.

## Validação offline e início futuro

Os [testes sintéticos](../tests/test_development_d3.py) exercitam os formatos reais de CSV/journal/ground truth/monitor/captura, exportação, validação de dataset e revisão. Cobrem degradação válida com recuperação, ausência de recuperação com censura, coleta com drops, tentativa aberta persistida versus registro perdido, ground truth adulterado, journal truncado, suporte insuficiente, referência PRE/C, controle com serviço inadequado, vínculo de preflight, bloqueio de E8, IO completo e recusa de sobrescrita. A autoridade real é validada separadamente dos manifests sintéticos dos testes de IO. Dados sintéticos e metadados de execução sintética permanecem em diretórios temporários, sem ocupar os caminhos reservados dos pilotos.

O [registro de validação offline](../experiments/protocols/development_d3_pilots_20261028/offline_validation.json) distingue os 14 testes novos e as regressões. Dois testes legados de preparação de D2 pressupõem saídas/revisão do probe ausentes e conflitam com D2 já encerrado; seus artefatos e testes foram preservados. A autoridade de D2 é conferida com saídas existentes permitidas.

Comandos offline, sem Docker:

```bash
.venv/bin/python -B -m experiments.development_d3 validate-plan
.venv/bin/python -B -m unittest tests.test_development_d3 -v
```

Para iniciar **somente o preflight de C**, futuramente e a partir da raiz do repositório:

```bash
.venv/bin/python -B -m experiments.development_d3_ops preflight --entry d3_pilot_C
```

Esse último comando consulta Docker/imagens, porta e prontidão da captura, podendo criar/remover contêineres parados de inspeção. Não gera carga HTTP nem inicia o piloto. Ele foi preparado, **não executado**, nesta tarefa.
