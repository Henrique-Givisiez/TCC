# C1.3.1 — Especificação científica direta de 80 execuções

## Estado e escopo

Branch `refactor/project-organization`; HEAD inicial `a142a7235611594d4cb78e3f7d4164cd5b4fa081`, working tree limpo.
A diferença desde CPU.2 é o commit do relatório CPU.3. Nenhuma coleta Docker,
tráfego, dataset científico, calibração ou mudança de algoritmo nesta entrega.

Nova autoridade declarativa: `docs/scientific_protocol_direct_20261108.json`,
ID `single-victim-direct-80-20261108`, versão3. SHA256 em arquivo irmão `.sha256`:
`972b895a7427b2e2ace6be9d495c80f4d152d72c1bebbc751932a8e339d8a394`.
O hash identifica a especificação, não um plano executável congelado.
Status `STRUCTURAL_ONLY_NOT_EXECUTION_RELEASED`. A especificação reduzida histórica
continua intacta e padrão do import; SHA256 original verificado nos testes.

Seleção explícita existente: `SCIENTIFIC_SPEC_PATH` E `SCIENTIFIC_SPEC_SHA256`,
ambos necessários antes de importar o módulo de protocolo. Não há autodetecção.
Uma tentativa de `run_partition` com a nova especificação é recusada antes de
qualquer lock, preflight ou coleta: C1.3.2/C1.3.3 e validação integrada pendentes.

## Matriz e configurações completas

| Elemento | Histórico | Novo |
|---|---|---|
| Preparação |4/8/8|4/8/8|
| TEST |12 blocos ×3 =36|20 blocos ×3 =60|
| Total/teto físico proposto |56/58|80/82|
| Cenários |C16/M16/E16|L2/A3/F96|
| Fontes legítimas |4×4|2×8 RPS `/medium`|
| Fontes ofensivas |1|2 em A3 e F96; zero em L2|
| Topologia |proxy|direta, sem NGINX|
| CPU |contrato histórico|features schema2; snapshots versionados|
| Aprovação declarada |bloqueio primário global|por método×feature, sem bloquear coleta TEST|

Configurações científicas completas estão embutidas na nova especificação, sem ID
ou seed de execução. `configuration()` acrescenta somente esses dois campos e
confere a serialização canônica de `ExperimentConfig`. `load_plan()` compara todo
o JSON efetivo, não apenas campos ofensivos. Endpoints, concorrência, fontes,
workers, tempo, ID, sementes e demais campos não podem ser alterados silenciosamente.

Fontes consultadas:

- L2: `experiment_results/b2-l-20261107T232559Z/raw/effective_config.json`, comparado
  integralmente ao template protegido `experiments/configs/protected_compositions/pilot-legitimate.json`:
  igualdade confirmada. A referência hash-bound usa esse template versionado, para
  não exigir distribuição dos dados brutos históricos.
- A3: `reports/b2-a-20261107T234426Z/configuration.json`.
- F96: `reports/b2-f96-20261108T002312Z/configuration.json`.

Os três relatórios B2 e o relatório CPU.3 também foram consultados. Não faltaram
parâmetros necessários. Cada referência tem hash; a validação reproduz exclusivamente
as transformações aprovadas: retirar ID/seed, duração390 e emissão150+120 s.
Não modifica os originais nem reconstrói defaults desconhecidos.

Uma vítima, pool persistente2, diagnósticos ON/queue4096, sem autoscaling/balanceador.
L2 permanece em todos os cenários: duas fontes×8 RPS, timeout2 s, concorrência64.
A3: `computational_asymmetry`, duas fontes×4 RPS `/expensive`, concorrência64.
F96: `http_request_flooding`, duas fontes×32 RPS `/medium`, concorrência96.
Não se reabre F64/F96. Kernel/endpoint, work_units históricos de compatibilidade,
monitoramento operacional5 s e demais propriedades B2 permanecem preservados.
RPS é nominal por fonte; realização efetiva será medida, não pressuposta.

## Ordem e sementes

`expected_slots(spec)` reutiliza o gerador existente:4 BASELINE L2,8 CAL_A L2,
8 CAL_B L2 e20 blocos TEST completos. Cada cenário aparece20 vezes.

Ordem: as seis permutações de L2/A3/F96, repetidas três vezes, seguidas de
L2/A3/F96 e A3/F96/L2. Cada cenário ocupa cada posição6 ou7 vezes; diferença
máxima1. Ordem fixa antes dos dados; não é otimizada por resultados. O número20
não permite igualdade exata de posições para três cenários.

40 grupos independentes:20 preparações individuais +20 blocos TEST. Uma semente
compartilhada entre os três cenários de cada bloco; nenhuma entre grupos.
`draft_entries()` é função pura de especificação, namespace e inventário histórico:
SHA256/contador, rejeição de colisões, IDs determinísticos. Gera somente rascunhos
em memória; nenhum inventário real de sementes da campanha foi materializado.

Reutilizado `collect_seeds` e o validador hash-bound de planos: verificação de
cobertura do inventário, hashes dos arquivos, disjunção dos grupos e ordem dos slots.
Para a nova autoridade, o inventário inclui também `reports`, além de
experiments/configs, experiments/protocols, docs/stage14a/materialized e
experiment_results. Inclui, assim, campanhas exploratórias e piloto CPU.
O inventário completo deverá ser atualizado no congelamento futuro. Sementes
sintéticas dos testes e namespaces de fixture não são sementes de campanha.

## Tempo, CPU e decisões metodológicas

Todas as condições390 s: warmup[0,30), PRE[30,150), ATTACK[150,270), POST[270,390).
Drenagem adicional30 s, distinta de POST e duração nominal. Em L2 as fronteiras
são referências descritivas, sem ataque. Fim nominal não comprova fechamento real:
certificados, actual_start/actual_end, drenagem, processamento residual e recuperação
de serviço continuarão distintos e precisarão ser validados.

Cinco features e quatro métodos preservados. CPU schema2,
`victim-cpu-snapshots-v1`, aquisição1 s, antecipação25 ms, tolerância provisória50 ms,
recebimento até fechamento, null sem suporte, sem cache/interpolação. Nenhuma linha
da implementação CPU foi modificada. CPU.3 validou legítimos curtos; validação
sob ataque ainda pendente. Tolerância e disponibilidade continuam identificadas
como provisórias. Gates por fase não foram criados.

CAL_A: FPR média macro≤1%, máximo por run≤5%, decisões≥95%; CAL_B:≤2%,≤5%,≥95%.
Declarada aprovação por método×feature e reprovação como não avaliado, sem ajustar
limiares com TEST nem bloquear globalmente sua coleta. Grade CUSUM/replay, componentes,
ICs e demais parâmetros existentes foram conservados. Isso é contrato para C1.3.2,
não alegação de que o engine atual já implemente essa elegibilidade.

FPR principal: L2[30,390). PRE ofensivo: FPs complementares. Detecção respeita emissão
real e disponibilidade até actual_end; alarmes anteriores não contam; miss tem
latência observada null. POST[270,390) é persistência, não benigno automático.
Métricas operacionais legítimas e ICs existentes preservados como base.
A3−F96 é contraste entre configurações operacionais: mecanismo, endpoint, taxa e
concorrência diferem; não é efeito causal isolado nem dose equivalente.

80 slots e até duas substituições explicitamente autorizadas (uma por slot), teto82.
Sem retry automático. Mantidos códigos técnicos e proibições históricas.
Reprovação de calibração, miss, FPR alto, degradação e ausência de recuperação não
descartam um resultado válido. Falha de limpeza/recuperação operacional interrompe
para diagnóstico, sem virar automaticamente substituição técnica.

## Contratos e arquivos alterados

Novos: especificação JSON/sha256, `analysis/detection/scientific/direct_contract.py`,
`tests/test_direct_scientific_protocol.py` e este relatório.
Alterados: `protocol.py` (configuração completa, grupos, fontes de sementes e imagens)
e `experiments/scientific_campaign.py` (somente trava explícita de execução da nova autoridade).
O default histórico e seu caminho de validação permanecem disponíveis.

Lock de imagens novo contém somente papéis `victim` e `source`, com IDs sha256
imutáveis. Não exige terceira imagem, presença de NGINX ou consulta ao daemon.
O backend ainda espera nomes históricos/três imagens; sua adaptação não foi feita.

## Testes determinísticos

`python -B -m unittest tests.test_direct_scientific_protocol tests.test_experiment_config -q`:
16 testes aprovados antes do teste adicional de plano completo; módulo novo com
7 testes aprovado depois. Plano80 é materializado apenas em diretório temporário
de teste, com ambiente e sementes sintéticos; valida distribuição e aceita plano
completo, recusa seed histórica e configuração adulterada mesmo com hash recalculado.
Testes também verificam seleção explícita em subprocesso Python, hashes, CPU,
fontes, ordem, disjunção, imagens sem proxy e recusa de coleta.

Regressão científica histórica: `.venv/bin/python -B -m unittest tests.test_scientific_campaign -q`:
**16 testes aprovados em210,469 s**, sem falhas. Log temporário `/tmp/c131-scientific-tests.log`.
Verificação final do módulo novo: **7 testes aprovados em1,652 s**. Somados aos10
testes de configuração já aprovados, foram verificados33 testes distintos.
Nenhum desses testes inicia contêineres ou tráfego. Mensagens de start/build nos
testes de configuração são chamadas a mocks, não operações reais.
`git diff --check` aprovado. Não se executou validação de plano real ou Docker.

## Pendências e riscos

**C1.3.2:** `engine.py`, `data.py`, `evaluation.py` e decisões/checkpoints em
`scientific_campaign.py`: separar elegibilidade por par, retirar bloqueio global de
request_starts, impedir feedback TEST e distinguir não avaliado de miss; implementar
FPR principal L2/PRE complementar/POST persistência e resumos por cenários novos.
Revisar bindings, releases, denominadores, disponibilidade e ICs com testes sintéticos.

**C1.3.3:** `scientific_collection.py`, `scientific_campaign.py`, `stress_processing.py`,
`development_d3.collection_checks`, adaptadores de proteção/runtime: remover exigências
de proxy, quatro fontes legítimas e imagens legadas; integrar certificação direta,
política operacional compatível com390 s, identidade de imagens, recuperação,
falhas, persistência e retomada. A política B2 de240 s não serve silenciosamente
para390 s. O observador legado de interrupção por degradação não foi aprovado
implicitamente por esta especificação; decidir/adaptar no escopo próprio, sem usá-lo
para excluir observações ruins. Congelar plano, ambiente, imagens e inventário só
depois dessas adaptações e da validação integrada autorizada.

Validar estrutura não prova realização das taxas, fechamento efetivo, CPU sob ataque,
suporte dos detectores ou capacidade de concluir80 runs no prazo15/11. Não há plano
definitivamente congelado, coleta liberada ou autorização de começar C1.3.2 nesta entrega.
