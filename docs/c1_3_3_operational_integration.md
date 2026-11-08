# C1.3.3 — Integração operacional e automação

Implementação sobre `45d4a537c99a40e5a589a39ea0d52717925bc500`, branch
`refactor/project-organization`, inicialmente sem alterações locais.
Nenhum Docker, tráfego, piloto ou campanha foi executado. Não houve push.

## Resultado e limites da entrega

O backend reconhece o contrato direto; o runner oferece sequência e retomada
explícitas. A especificação continua **bloqueada para execução**:
`execution_release.allowed = false`. O plano definitivo e suas sementes não foram
materializados. Os testes demonstram comportamento determinístico com fixtures,
não desempenho, cobertura ou segurança empírica sob A3/F96.

## Arquivos e incompatibilidades corrigidas

| Arquivo | Alteração |
|---|---|
| `experiments/scientific_collection.py` | Preflight com IDs vítima/fonte; verificação completa de código; execução com `Operations`; registro de encerramento e verificação de limpeza inclusive quando o subprocesso falha; seleção explícita das verificações diretas na recuperação offline. |
| `experiments/scientific_operations.py` | Integração pequena com imagem, prontidão, política de recursos e verificações de captura/CPU/limpeza existentes. |
| `experiments/diagnostic_run.py` | Opção explícita de piloto científico, fora da campanha, reutiliza o mesmo probe e adaptador do backend. |
| `experiments/scientific_campaign.py` | Sequência autorizada, continuação conservadora, retomada sem repetição, status e reserva temporal corrigida. |
| `experiments/stress_processing.py` | Inventário legítimo derivado de `normal_traffic.clients`; demais comparações permanecem estritas. |
| `experiments/stress_observer.py`, `stress_review.py` | Política direta gravada e reproduzida offline; degradação registrada sem comandar parada. |
| `experiments/development_d3.py` | Opção interna `capture_only` reutiliza integralmente as verificações de captura, sem exigir o proxy no contrato direto. Comportamento padrão histórico preservado. |
| `analysis/detection/scientific/evaluation.py` | `impact()` aceita CPU operacional ausente no CSV; não converte ausência em zero. A reconciliação dinâmica também atende suas duas fontes legítimas. |
| `analysis/detection/scientific/direct_contract.py` | Ordem aleatorizada verificável e versão 4; validação de vínculo da política operacional. |
| `docs/scientific_protocol_direct_20261108.json`, `.sha256` | Revisão prospectiva da ordem e política, com trava de liberação preservada. |
| `tests/test_direct_campaign_operations.py` | Fixtures operacionais e testes de integração sem Docker real. |

O preflight histórico continua exigindo suas três imagens e sua observabilidade
de proxy. No direto, `verify_image_code()` verifica todos os Python da vítima,
diagnósticos, os arquivos realmente copiados por `Dockerfile.sources` e a
configuração de lançamento. A inspeção futura usa contêiner parado, removido ao
final; não aceita uma tag como identidade congelada nem constrói imagem.

Antes da emissão são preservados: exclusividade, processos conhecidos,
contêineres parados residuais, redes ocupadas, recursos do host, memória, disco,
captura e limites efetivos de cgroup. O runtime usa IDs congelados e não tenta
reconstruir a vítima. Recursos efetivos continuam comparados ao probe do preflight.

## Política de interrupção

`scientific-direct-v1` mantém as regras de observação e seus registros causais.
`service_compromise` e `generator_queue` não comandam parada: latência, timeouts,
baixa vazão e fila são resultados experimentais. O replay exige a mesma política
e não espera um comando de parada para esses sinais.

`collection_stale` continua comandando parada quando aplicável à emissão;
`observer_failure` também provoca parada segura. Memória, disco, orçamento de
artefatos, OOM, reinício, identidade, estado e falhas de persistência/encerramento
permanecem protegidos por `Operations` e pelas validações existentes. Os limites
de recursos vêm do arquivo B2 já aprovado, vinculado por hash. Não foram relaxados.

Uma parada do observador direto não é aceita como exposição científica completa:
a recuperação a registra como falha técnica. Encerramento, emissão efetiva e
integridade continuam sendo verificados separadamente. Exceções desconhecidas
não são traduzidas em um código recuperável.

## Continuidade, retomada e checkpoints

1. Cada posição possui diretório de tentativa, intenção imutável, journal e hashes.
2. Uma intenção já existente segue exclusivamente para recuperação offline. Não
   chama novamente `collect()`. Uma intenção persistida antes de uma interrupção
   na escrita do journal é incorporada ao journal na retomada, sem nova aquisição.
3. Recibos existentes são verificados e reutilizados; falhas existentes continuam
   consumidas. Não há substituição nem atrito técnico automáticos.
4. A continuação automática direta admite somente `CAPTURE_LOSS`, `DATASET_INVALID`,
   `MISSING_REQUIRED_ARTIFACTS` e `MONITOR_SUPPORT`, com falha vinculada à intenção,
   limpeza comprovada e novo preflight completo aprovado. O evento
   `CONTINUATION_READY` vincula por hash falha, limpeza e preflight.
5. Divergência de identidade/journal, estado indeterminado, erro desconhecido,
   alteração do congelamento ou limpeza incerta interrompem a sequência.
6. Todos os slots seguros restantes da partição podem ser coletados; qualquer
   falha pendente impede análise/checkpoint dessa partição. BASELINE/CAL_A/CAL_B
   incompletas não liberam a seguinte. TEST parcial não gera consolidação completa.
7. As autorizações de substituição e encerramento formal do TEST continuam sendo
   comandos separados, vinculados ao hash da falha, dentro do orçamento de duas
   substituições. Os mesmos cenário, semente e slot são preservados.

Recuperação HTTP ausente permanece no resultado operacional e não bloqueia por
si a próxima execução direta. **Prontidão operacional** precisa ser comprovada
novamente. Isso não demonstra recuperação científica nem ausência de efeitos no
kernel. O filtro de processos continua sendo o filtro conhecido do projeto.

Uma interrupção após coleta completada permite reconstruir o recibo sem nova
execução. Se não existirem execução/limpeza suficientes, a retomada para com
`INDETERMINATE_ATTEMPT`; não tenta adivinhar se o filho ainda está executando.
Não há recuperação destrutiva automática de processos ou contêineres desconhecidos.

## Duração e orçamento

Preservados: nominal 390 s, emissão programada `[150,270)`, POST `[270,390)`,
até 30 s adicionais de drenagem nas fontes e 60 s entre tentativas encerradas com
segurança. Drenagem é orçamento de conclusão, não emissão adicional nem extensão
dos denominadores científicos. O certificado real deve satisfazer esses limites.

O subprocesso mantém o limite científico existente de **480 s**, incluindo setup,
390 s nominais, drenagem, encerramento e exportação. Sobram 60 s em relação a
390+30; não se afirma que esse saldo suporta todos os piores casos simultâneos.
Os prazos existentes de fechamento continuam: manager 35 s (inclui drenagem e
certificação), captura com esperas de 5 s, CPU até 6 s, diagnóstico da vítima 3 s e
parada da vítima 5 s. São limites, não tempos tipicamente gastos em série.

O timeout global da proteção reutiliza os mesmos 480 s; apenas o antigo valor
exploratório de 240 s era incompatível com 390 s. Chamadas operacionais Docker
diretas usam os 3 s já aprovados. O encerramento externo conserva SIGTERM ao grupo,
espera de 35 s e SIGKILL se necessário; prazo excedido impede progressão automática.
Artefatos e verificação de limpeza são tentados também nesses encerramentos.

O runner agora recusa consumir uma tentativa se restarem menos de **540 s** no
envelope existente de 1080 s: 480 de subprocesso + 60 de intervalo. Antes, podia
reduzir silenciosamente o subprocesso a 420 s. O teto administrativo continua
600 s, condicionado à reserva: preparação prolongada pode esgotar o envelope sem
consumir uma tentativa. A margem efetiva de setup/encerramento/exportação precisa
ser medida na C1.3.4; não houve aumento arbitrário do limite de subprocesso.

O intervalo também considera a limpeza de falhas técnicas, não somente recibos
aceitos. Na retomada, o tempo já transcorrido conta; relógio futuro é recusado.

## Randomização e congelamento

Versão 4 da especificação direta; o identificador permanece para preservar a
política de sementes prospectivas. O protocolo histórico reduzido não foi alterado.
SHA-256 desta revisão:
`be39b12ffcd09699da6311fb7a86ddab342dfba503e699b9df6833f9fed46303`.

Semente de randomização: `202611080133`. Algoritmo
`sha256-sort-prebalanced-indices-v1`: ordena os índices 0–19 da lista previamente
balanceada pela chave SHA-256 ASCII de `semente:índice`, com índice como desempate.
Não depende da implementação de `random.shuffle` nem de resultados experimentais.
A lista contém três ciclos das seis permutações e duas permutações complementares;
somente sua ordem é embaralhada. A ordem resultante está integralmente registrada
em `test_order` e é reconstruída pelo validador.

São 20 blocos, uma ocorrência de L2/A3/F96 por bloco; cada cenário ocupa cada
posição 6 ou 7 vezes. As sementes de tráfego continuam agrupadas por número de
bloco, compartilhadas entre seus três cenários e independentes das partições de
preparação. Não foram geradas sementes reais nem consultados resultados para
escolher a ordem. `draft_entries()`, auditoria histórica de sementes, hashes de
runtime e `load_plan()` continuam sendo os mecanismos de preparação e validação.

| Cenário | Posição 1 | Posição 2 | Posição 3 |
|---|---:|---:|---:|
| L2 | 7 | 6 | 7 |
| A3 | 7 | 7 | 6 |
| F96 | 6 | 7 | 7 |

## Integração da CPU e preservação científica

Não foram modificados coletor, fórmula, agenda, antecipação de 25 ms, tolerância
provisória de 50 ms, disponibilidade até fechamento ou extração schema 2.
`ProtectedCollector` conserva `_on_acquisition()` e o frescor de snapshots novos;
o relógio, JSONL e encerramento continuam na cadeia existente de `source_experiment`.
O backend exige encerramento do worker sem erro fatal e mantém exportação,
validação, hashes e extração existentes. Lacunas válidas da feature não recebem
zero nem geram por si descarte automático de uma execução ofensiva.

A verificação direta reutiliza os certificados CSV/PCAP completos, em vez do gate
legado que exigia amostras de proxy e 108 ticks por fase. Não usa cobertura dos
ticks como cobertura da CPU. Proteção de frescor/persistência e integridade são
separadas da cobertura científica, diagnosticada em `cpu_quality.json`.

Elegibilidade método×feature, CAL_B estrutural, TEST sem retuning, FPR de L2,
PRE complementar e POST não benigno continuam na implementação C1.3.2.

## Interface

Os comandos abaixo são modelos para uso **depois** da preparação autorizada.
`PLAN`, `PLAN_HASH` e `SPEC_HASH` representam referências congeladas verificadas;
não foram criados nesta atividade. Os caminhos de protocolo devem ser absolutos.

```bash
export SCIENTIFIC_SPEC_PATH=/caminho/TCC/docs/scientific_protocol_direct_20261108.json
export SCIENTIFIC_SPEC_SHA256="$SPEC_HASH"
.venv/bin/python -B -m experiments.scientific_campaign --plan "$PLAN" --plan-sha256 "$PLAN_HASH" validate
.venv/bin/python -B -m experiments.scientific_campaign --plan "$PLAN" --plan-sha256 "$PLAN_HASH" status
# Depois da liberação revisada; o mesmo comando inicia ou retoma:
.venv/bin/python -B -m experiments.scientific_campaign --plan "$PLAN" --plan-sha256 "$PLAN_HASH" sequence --authorize-sequence ALL_PARTITIONS
```

`validate` e `status` não acessam Docker. `status` apresenta total, aceitos,
pendentes, tentativas consumidas, falhas pendentes, substituições autorizadas,
partição, último checkpoint, próximo slot não consumido e evidências de limpeza.
Substituições autorizadas ainda não consumidas voltam a aparecer como próximo slot.
`run --partition ... --authorize-partition ... --checkpoint-sha256 ...` permanece.
Cada chamada autorizada de sequência registra `SEQUENCE_AUTHORIZED`; esse registro
não dispensa os checkpoints nem autoriza substituições.
`approve-technical-replacement --failure-sha256 ...` e
`record-test-attrition --failure-sha256 ...` permanecem explícitos; não são ações
executadas automaticamente pela sequência. O controle continua sob lock exclusivo.

## C1.3.4 e procedimento de liberação

Não executar a sequência para realizar pilotos. Preparar três configurações
isoladas usando `direct_contract.configuration(spec, scenario, pilot_id, pilot_seed)`
para L2, A3 e F96, com identidades/diretórios e sementes diagnósticas fora dos slots.
O caminho existente `experiments.diagnostic_run` permite execução direta com
`--config`, `--output`, `--dataset-output`, IDs imutáveis de vítima/fonte,
`--operational-policy` e `--composition legitimate|combined`. O arquivo de política
deve ser a serialização de `scientific_operations.policy()` (mesmos recursos B2,
480 s), e não o original exploratório de 240 s. `prepare_attempt()` já verifica
imagens/código/prontidão; `complete_procedure()` preserva exportação e certificação.

Adicionar `--scientific-pilot-scenario L2|A3|F96` ao comando diagnóstico instala
exatamente o mesmo adaptador `StressManager`/`ProtectedCollector` do backend,
incluindo probe de recursos efetivos e `scientific-direct-v1`. A opção exige
contrato direto explicitamente selecionado, configuração completa correspondente
ao cenário e política protegida idêntica. O registro declara
`scientific_pilot=true` e `campaign_slot=false`. Não contorna `load_plan()`:
é uma execução diagnóstica separada, sem plano80, checkpoints ou partições.
Sem essa opção, o caminho diagnóstico histórico permanece igual. Nenhuma dessas
opções foi executada nesta etapa.

Depois dos pilotos autorizados, inspecionar emissão real de 120 s, drenagem,
capture drop counters, journals/inventário, exportação, CPU/CoV e fases, prazo de
480 s, interrupções técnicas, limpeza e capacidade de iniciar a próxima execução.
Não aceitar nominal como prova da emissão nem cobertura legítima como prova sob ataque.

A liberação exige revisão explícita dos resultados e nova revisão versionada do
contrato, incluindo o validador que hoje exige `allowed=false`; atualizar hashes,
testes e documentação. Só então congelar código/IDs/ambiente, atualizar o inventário
histórico de sementes, materializar configurações e plano novos, validar todos os
vínculos e autorizar a sequência. Não existe opção de CLI que ignore essa trava.

## Testes e riscos remanescentes

Testes usam arquivos temporários, backend falso, sockets/subprocessos/Docker
simulados. Mensagens de build nos testes de fontes pertencem a `MagicMock`.
Não foi consultado o Engine. Os comandos e resultados finais estão registrados
na seção de validação abaixo.

Riscos que impedem declarar a campanha pronta: cobertura CPU sob ataques ainda
não medida; prazo de setup/exportação ainda não medido; validação integrada do
backend/observador e recuperação entre pilotos pendente; congelamento e liberação
definitivos pendentes. Slots técnicos pendentes continuam exigindo diagnóstico
e autorização, podendo bloquear fronteiras. Não se promete retomada automática
de estado operacional indeterminado nem independência do kernel entre execuções.

Esforço remanescente principal: validação integrada e decisão de liberação;
nenhuma revisão estatística ou de intensidade foi introduzida nesta entrega.

## Validação determinística

```bash
.venv/bin/python -B -m unittest tests.test_direct_campaign_operations tests.test_direct_scientific_protocol tests.test_direct_scientific_evaluation tests.test_cpu_observations tests.test_stress_pilot tests.test_protected_compositions tests.test_exploratory_operations tests.test_source_containers -q
.venv/bin/python -B -m unittest tests.test_scientific_campaign -q
git diff --check
```

Primeiro comando: **112 testes aprovados**, incluindo 25 novos testes operacionais.
Log local: `/tmp/c133-final.log`. A suíte abrange preflight completo simulado,
duas imagens e código divergente, reconciliação efetiva de journals com 2/4 fontes,
ground truth, faltas/duplicações, interrupções, limpeza, intervalo após sucesso e
falha, retomada, intenção sem journal, fronteiras, TEST parcial, substituição
explícita, sequência, randomização, CPU, contrato diagnóstico e adapter de frescor.

A primeira rodada histórica revelou duas diferenças de leitura do journal;
foram corrigidas por distinção explícita de contrato. A regra histórica continua
no ponto de validação original; o direto verifica as evidências também ao ler o
journal. Resultado da repetição completa registrado abaixo.

Segundo comando: **16 testes históricos aprovados** em 219,616 s, depois das
correções. Log local: `/tmp/c133-historical.log`. Total das duas suítes: **128
testes aprovados**. `git diff --check` não encontrou erros de whitespace.
Após os últimos ajustes no registro de autorização e nas validações temporais,
foram repetidos os 32 testes de `tests.test_direct_campaign_operations` e
`tests.test_direct_scientific_protocol`: todos aprovados (log
`/tmp/c133-last.log`). Essa repetição não adiciona casos ao total de 128.

Testes reais com Docker, cobertura/latência de CPU sob ataque, emissão e recuperação
efetivas **não executados**, conforme a restrição desta etapa. O teste de preflight
substitui Docker, socket, tcpdump e probe por mocks; a função real de reconciliação
processa somente fixtures em disco. Os dados temporários não integram a campanha.
