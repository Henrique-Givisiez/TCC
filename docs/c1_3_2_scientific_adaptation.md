# C1.3.2 — Elegibilidade por método × feature e avaliação direta

## Escopo e inspeção

Branch `refactor/project-organization`; HEAD inicial
`bab3729f896f495ff254aaf34bf78f28efac7452`, working tree limpo.
Foram inspecionados engine, data, evaluation, protocol, direct_contract,
scientific_campaign e testes existentes. A autoridade nova é identificada por
`configuration_contract=complete-direct-b2-v1`. O default histórico permanece
o protocolo reduzido e conserva seus gates e métricas; o comportamento novo exige
seleção explícita da especificação direta.

Não houve Docker, tráfego, coleta, calibração real, alteração de algoritmo/CPU ou
mudança de configuração L2/A3/F96. A especificação e seu hash não precisaram mudar:
esta implementação cumpre decisões já declaradas. `execution_release.allowed=false`
continua intacto, assim como a trava de `run_partition` antes da execução.

## Problemas corrigidos

O engine condensava quatro aprovações em `eligible/approved`, e request_starts
bloqueava globalmente BASELINE, CAL_A, CAL_B e leitura/processamento TEST. A avaliação
classificava todo trecho sem overlap como benigno, incluindo processamento residual
e POST. O resumo misturava essas exposições no FPR e não representava elegibilidade
parcial por método.

## Arquivos

- `analysis/detection/scientific/engine.py`: statuses por método, propagação de
  baseline indisponível, aprovação parcial, processamento seletivo e replay.
- `analysis/detection/scientific/data.py`: release estrutural CAL_B, verificando
  todas as features e ancestralidade CAL_A, sem exigir aprovação conjunta.
- `analysis/detection/scientific/evaluation.py`: roteamento explícito das métricas
  e agregação novas; caminho histórico preservado.
- `analysis/detection/scientific/direct_metrics.py` (novo): métricas por execução.
- `analysis/detection/scientific/direct_summary.py` (novo): denominadores, ICs e
  conjuntos pareados por métrica.
- `experiments/scientific_campaign.py`: apenas retirada dos dois aborts estatísticos
  globais em CAL_A/CAL_B para a autoridade direta; nenhuma continuidade operacional nova.
- `tests/test_direct_scientific_evaluation.py` (novo): casos sintéticos direcionados.

## Elegibilidade final

Unidade: um dos quatro métodos × uma das cinco features, 20 candidatos.
`pair_status` em CAL_A registra threshold (inclusive quando escolhido mas reprovado),
support por execução (run ID, cobertura, FPR, disponível/esperado), FPR média e
máxima, lista de coberturas, eligible e reason. Cada método é julgado isoladamente.
Critérios mantidos: média ≤1%, máximo ≤5%, decisões ≥95% em cada run.

CUSUM-freeze conserva todos os candidatos da grade, replay por h e menor h numérico
elegível. Falha do CUSUM-reference ou ausência de candidato não elimina limiares
válidos de Z/CoV/EWMA. Não há extensão de grade ou seleção em CAL_B.

Baseline insuficiente/sem variância fica registrada com parameters=null e motivo;
na autoridade direta, inclusive request_starts não provoca aborto global. A
indisponibilidade propaga inelegibilidade dos métodos daquela feature, sem escolher
outras features em função do resultado. Erros de identidade/hash/autoridade ainda
são erros de integridade e não são convertidos em mera inelegibilidade.

CAL_B usa somente thresholds CAL_A, com média ≤2%, máximo ≤5%, cobertura ≥95%.
`method_accepted` e `pair_status` são condicionados à aprovação em A. Reprovação em
A não é revertida mesmo se B tiver FPR baixo. O replay confere statuses em A/B.
Booleans conjuntos históricos `eligible`, `approved` permanecem como resumos de
compatibilidade, mas não decidem liberação ou aprovação científica no contrato novo.

Após checkpoint CAL_B estruturalmente válido, TEST aceita aprovação parcial ou
nenhuma aprovação. O loader verifica inventário completo das cinco features,
verificações e respectivas calibrações vinculadas ao checkpoint CAL_A/autoridade.
Isso remove somente o gate estatístico global; não remove os locks de proveniência.

`engine.process` usa `method_evaluated` e motivo individual: pares aprovados nas
duas etapas recebem trajetória com threshold fixo; os demais recebem decisões
indisponíveis. `validate_run` reconstrói elegibilidade, motivos e trajetórias;
adulterações são recusadas. CAL_B não pode receber seu próprio artefato de verificação.
Os runs/seeds de treinamento, verificação e TEST continuam disjuntos.

Na avaliação, inelegível significa `scientifically_evaluated=false`, evento null,
latência null, FN null e métricas de desempenho indefinidas. Um método elegível sem
decisão de detecção no prazo é miss (`false`, latência null), com suporte explícito.
Receipts operacionais e sua agregação são preservados mesmo com zero métodos aprovados.

## Métricas e disponibilidade

- **L2:** FPR principal em `[30,390)`, FP/(FP+TN), somente decisões disponíveis até
  horizonte390; esperado, disponível, FP, TN, ausente e cobertura separados.
- **A3/F96 PRE:** `[30,150)`, `pre_fpr` complementar. O campo `fpr` principal é null
  nos ataques, impedindo sua mistura com L2.
- **Evento:** `[actual_start,actual_end)`, overlap positivo e disponibilidade entre
  início e fim efetivos. Preserva o prazo inclusivo `available<=actual_end` da
  especificação aprovada (uma janela terminando em E pode decidir em E). Alarmes
  anteriores não detectam; ausência de detecção elegível implica miss/latência null.
- **Classificação por janela:** ataque usa janelas totalmente dentro da emissão
  real, inclusive eventual trecho após270; janelas de fronteira são contabilizadas
  à parte. Recall/precisão/F1 usam essas janelas e FPs PRE, sem POST negativo.
  São métricas complementares, não substitutos da detecção por evento.
- **POST nominal:** `[270,390)` intersectado com trecho efetivamente posterior à
  emissão. Se E>270, `post_still_offensive_windows` distingue a parcela ainda
  ofensiva; a persistência começa somente após E. Se E<270, o intervalo E–270
  não é silenciosamente incorporado ao POST nominal nem ao PRE.
- **Persistência:** esperado/disponível/positivo/negativo, fração positiva,
  soma das durações das janelas positivas suportadas e último alarme disponível.
  O tempo desse último alarme desde E é registrado separadamente; não representa
  um alarme contínuo através de lacunas. L2 não recebe duração de persistência fictícia.
- **Drenagem:** janelas e decisões após390 não entram nos denominadores/detecção
  nominal. Artefatos e cauda continuam preservados.

Não houve alteração na disponibilidade dos detectores. A CPU continua impondo
recebimento até fechamento no schema2; disponibilidade computacional permanece
simulada no fechamento, não latência de processamento medida.

## Agregação e ICs

O resumo publica por método/feature/cenário: execuções previstas, tecnicamente
válidas, cientificamente avaliadas, inelegíveis, indefinidos e denominadores de cada
métrica. As métricas por run são preservadas integralmente para auditoria. Há também
inventário das 20 combinações com estados elegível/inelegível/desconhecido; mudanças
de elegibilidade entre runs TEST do mesmo par congelado são recusadas.

FPR, PRE, recall, precisão/F1, cobertura, persistência proporcional e fração restrita
usam os ICs de médias já existentes por run/bloco. Detecção usa proporção por
execução elegível; atraso é condicional aos detectados, preservando suporte mínimo8
para IC. Durações de persistência usam o helper existente de média não limitada.

Comparações entre métodos alinham o mesmo run/bloco; comparações A3–F96 fazem
interseção explícita de IDs de bloco. Cada métrica publica blocks/n_pairs próprios;
FPR indefinida não elimina o par de detecção. Diferenças de taxas usam os helpers
pareados existentes; eventos usam discordâncias pareadas; diferenças de atrasos
são condicionais a ambos detectados e sem IC abaixo de8 pares. Não se reamostram
janelas/requisições como réplicas iid. Não há novo teste de superioridade.
A3–F96 continua contraste operacional, sem equivalência de dose nem causalidade
isolada do mecanismo. Impacto/atendimento legítimo continuam agregados pelos helpers
existentes, independentemente da elegibilidade estatística.

## Testes

Comandos executados (somente fixtures/mocks):

```
.venv/bin/python -B -m unittest tests.test_direct_scientific_evaluation tests.test_direct_scientific_protocol tests.test_cpu_observations -q
.venv/bin/python -B -m unittest tests.test_scientific_campaign -q
```

Primeiro conjunto:42 testes aprovados em2,033 s; regressão histórica:16 testes
aprovados em211,484 s (log `/tmp/c132-historical.log`). O teste adicional de replay
atravessa CAL_A, candidatos CUSUM, CAL_B e process(TEST), com CoV reprovado em A,
EWMA reprovado em B e Z/freeze aprovados; thresholds permanecem iguais. Alterar
eligibilidade armazenada é recusado por validate_run. Checkpoint rejeitado
estatisticamente libera leitura estrutural, mas ancestralidade divergente é recusada.

Cobertos: baseline request_starts indisponível sem aborto, aprovações independentes,
inelegível sem FN, ausência de retuning, FPR só L2, PRE separado, POST não benigno,
E=275, alarme pré-evento, miss/latência null, decisões ausentes/tardias, drenagem e
pares por bloco/métrica. Uma fixture inicialmente passou dicts onde a API exige
artefatos com reference; foi corrigida, sem alterar a regra científica.
Verificação final após os últimos ajustes: **43 testes aprovados em2,129 s** no
conjunto direcionado; somados à regressão histórica, **59 testes distintos aprovados**.
Incluído teste de replay com contexto Decimal externo reduzido: status e métricas
mantêm os50 dígitos congelados. Nenhuma falha permanece; `git diff --check` aprovado.

## Pendências C1.3.3 e riscos

Continuam pendentes as adaptações operacionais de fontes diretas, imagens sem
proxy, reconciliação (quatro legítimos históricos), proteção e política compatível
com390 s, cleanup/recuperação e retomada. `impact(raw)` ainda depende da reconciliação
legada; esta deve ser adaptada em C1.3.3 antes de coletar, preservando as métricas
operacionais. Não se alegou compatibilidade real do backend novo.

É necessária validação integrada de390 s, incluindo CPU sob ataque, emissão real,
residual e drenagem. O piloto CPU legítimo curto não basta. Modelos/limiares ainda
não foram estimados para a campanha; a aprovação de nenhum par é garantida.
Ausências durante ataques afetam cobertura e misses operacionais, não justificam
substituição oportunista de dados. Sem plano/ambiente/seeds definitivamente congelados,
não há autorização ou prontidão para iniciar a campanha. Não se avançou para C1.3.3.
