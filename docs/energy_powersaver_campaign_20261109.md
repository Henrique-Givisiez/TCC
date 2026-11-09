# Protocolo complementar de ambiente e operação — energy-powersaver-20261109

Versão 1. Estado: preparação; campanha completa NÃO autorizada. Este documento
adiciona controle ambiental ao C1.3.5/O3 sem alterar detectores, critérios de
calibração, elegibilidade, eventos ou métricas. O perfil econômico define uma
condição prospectiva; não constitui reconstrução do perfil histórico da B2.

## Arquitetura auditada

`experiments.c135_o3` seleciona o contrato científico por caminho e SHA256.
`scientific_campaign.Campaign` já materializa recibos, journal encadeado e quatro
checkpoints; `run_sequence` já permite operação independente do Codex.
`DockerBackend` faz preflight, consome uma tentativa, chama
`scientific_collection`, valida/exporta datasets, extrai features e recupera
processamentos offline. O runtime reutiliza as proteções operacionais, captura,
relógios certificados, journals das fontes e observador existentes.

BASELINE ajusta os modelos; CAL_A seleciona os limiares; CAL_B verifica cada par
método × feature; TEST processa as fontes com essas referências congeladas e
produz avaliações e resumo. A rejeição científica de um par continua tornando
esse par inelegível, sem recalibrar nem criar um novo bloqueio global. Erros
estruturais de análise, baseline inválida e calibração inconsistente interrompem.

Lacunas anteriores: perfil/AC não integravam o lock; não havia monitor de energia,
um selo ambiental por tentativa ou visão simples de acompanhamento. O adaptador
`experiments.energy_campaign` acrescenta esses componentes e reutiliza o
controlador científico. Nesta versão, toda falha interrompe a sequência: não há
continuação automática após perda técnica, substituição, redução de amostra ou
descarte de bloco. Essa política é mais conservadora que o caminho genérico.

## Isolamento e autoridade

- Bundle: `experiments/protocols/energy-powersaver-20261109/`.
- Pilotos: `experiment_results/pilots-energy-powersaver-20261109/{A3,F96}/`.
- Campanha reservada: `experiment_results/scientific-energy-powersaver-20261109/`.
- Caracterização: `reports/energy-powersaver-20261109/`.
- Nenhum piloto integra BASELINE/CAL_A/CAL_B/TEST.
- Publicações JSON usam criação exclusiva e fsync, sem sobrescrita.
- O protocolo científico original permanece imutável, SHA256
  `c97f8ece0198af720af4781409c12332508b45073cb62234a2c105864bf28018`.
- `preparation.json` congela código/configurações dos pilotos. `plan.json` congela
  80 novas identidades/sementes, configurações, dependências e código científico.
  `control.json`, selecionado por SHA256 no terminal, vincula o plano à referência
  ambiental, versão da automação e proveniência do checkout, inclusive alterações
  não commitadas. Nenhum commit é necessário ou executado.

## Condição ambiental e aceitação

Condição obrigatória: perfil Ubuntu `power-saver`, ACPI `low-power`, pelo menos
uma alimentação `Mains` verificável e todas as alimentações registradas online.
O pesquisador seleciona o perfil manualmente. Falha de leitura obrigatória
interrompe; a ferramenta nunca chama `powerprofilesctl set` ou escreve em sysfs.

A primeira referência válida de piloto congela boot, kernel, afinidade do
controlador, políticas por CPU (driver, governor, EPP, mínimo/máximo), parâmetros
intel_pstate e os dispositivos Mains. Os dois pilotos e a campanha exigem essa
mesma referência. Reboot ou alteração de política exigem revisão humana: não se
troca a referência silenciosamente. Suspensão/retomada é verificada pela mudança
da diferença BOOTTIME−MONOTONIC, tolerância técnica de 0,25 s.

Limites essenciais auditados para este notebook: CPUs efetivas 0–11, sem quota
CPU ou memória nos cgroups do contêiner/ancestrais; HostConfig sem novos limites
de CPU, cpuset, memória, PIDs ou parent. As imagens imutáveis de vítima/fontes são
as mesmas da campanha anterior. Alteração desses limites bloqueia, em vez de
ser automaticamente corrigida. O preflight científico mantém a verificação de
imagem/código e dos recursos efetivos da vítima antes da liberação das fontes.

São registrados UTC, identificadores, perfil, ACPI, políticas, AC/bateria,
boot/kernel/afinidade, imagens e limites, commit e working tree. Temperaturas,
contadores de throttling e frequência instantânea são observações opcionais;
ausência é explícita. Não se mede frequência efetiva média por worker, e valores
instantâneos não são usados como sua estimativa.

Há checks antes e depois de cada run e nas transições. Durante a coleta, a cada
5 s, consultas read-only validam energia, Docker/limites e hashes de autoridade,
código e configuração. Não se inicia container para monitorar. Há custo não nulo
de observação, não quantificado por benchmark. Mudanças entre amostras podem
escapar: não se afirma monitoramento contínuo. O mesmo método é usado nos dois
pilotos e na campanha.

Uma divergência envia SIGTERM ao grupo do subprocesso de coleta, permitindo o
encerramento/drenagem existentes por até 35 s; só depois usa SIGKILL se necessário.
O adaptador preserva logs, último estado válido e selo ambiental inválido, verifica
cleanup e não inicia a próxima run. Não remove contêineres alheios. Sem selo
ambiental válido, uma tentativa consumida não pode ser recuperada como aceita.

## Pilotos autorizados

Um único A3, seguido de um único F96, sem retries. As configurações derivam das
efetivas B2, alterando somente ID/semente. Há auditoria de sementes históricas.

| Campo | A3 | F96 |
|---|---|---|
| Legítimo | 2 × 8 RPS, `/medium`, orçamento 64 (32/fonte) | Igual |
| Ofensivo | 2 × 4 RPS, `/expensive`, orçamento 64 | 2 × 32 RPS, `/medium`, orçamento 96 |
| Workers da vítima / timeout cliente | 2 / 2 s | Igual |
| Duração | 150 s | 150 s |
| Pré / emissão / pós | [0,30) / [30,60) / [60,150) | Igual |

Não há warmup separado no protocolo B2: [0,30) é a referência anterior ao ataque.
Não se inventa um descarte de warmup retrospectivo. Coortes HTTP são selecionadas
pelo início e computacionais pela submissão. Conclusões posteriores permanecem
na coorte. A drenagem existente dos geradores tem reserva de 30 s; o orçamento
operacional B2 é 240 s. Antes do F96 há idle mínimo de 60 s e verificação da
certificação anterior. Encerramento de HTTP não equivale a cancelamento do trabalho.

Aceitação técnica exige processo encerrado, certificado operacional `completed`,
cleanup confirmado, dataset válido/elegível e selo ambiental válido. A análise
descritiva ainda exige relógios/identidades/journals íntegros e ciclos computacionais
completos. Timeouts não são, por si só, falha técnica nem critério de adequação.

O analisador produz PRE/ACTIVE/POST: CPU e parede por operação; contagens e taxas
de submissão/início/conclusão; média/mediana/p95 da espera; filas aguardando,
executando e pendentes; ocupação média e fração com dois slots; bins de 10 s;
HTTP iniciado/2xx/timeouts/erros/sucesso e durações de todos os encerramentos e de
2xx; planos disponíveis, admissões, despacho/expirações e HTTP em voo. Planos
ofensivos sem registro independente são `null`, nunca nominal × duração.

Não há um limiar novo de sucesso ou saturação. A interpretação é descritiva e a
adequação científica pertence ao pesquisador. Não se aumentam intensidades.

## Campanha prevista

São 4 BASELINE, 8 CAL_A, 8 CAL_B e 60 TEST em 20 blocos L2/A3/F96, com a ordem
balanceada já aprovada e novas sementes por bloco. Duração 390 s; WARMUP [0,30),
PRE [30,150), emissão [150,270), POST [270,390); idle 60 s e orçamento de coleta
480 s. Os 16 pares método × feature mantêm exatamente os critérios C1.3.5; CPU
permanece descritiva. BASELINE e as duas calibrações são inteiramente novas.

O plano só é congelado após os dois pilotos aceitos e caracterizados. O comando
`freeze` não é autorização nem coleta. A execução das 80 runs exige uma invocação
posterior explícita com identidade e SHA256 do controle. A decisão sobre a adequação
dos pilotos deve anteceder essa invocação. O contrato de energia não modifica o
contrato científico original e não reutiliza limiares históricos.

## Comandos independentes do Codex

Da raiz do repositório, usando `.venv/bin/python -B -m experiments.energy_campaign`:

```bash
# Preparação offline, uma única vez; não inicia Docker nem HTTP.
.venv/bin/python -B -m experiments.energy_campaign prepare

# Após selecionar manualmente Economia de energia e conectar a fonte:
.venv/bin/python -B -m experiments.energy_campaign check
.venv/bin/python -B -m experiments.energy_campaign pilot --scenario A3
.venv/bin/python -B -m experiments.energy_campaign pilot --scenario F96
.venv/bin/python -B -m experiments.energy_campaign analyze-pilots

# Depois dos pilotos e da revisão de seus resultados:
.venv/bin/python -B -m experiments.energy_campaign freeze
.venv/bin/python -B -m experiments.energy_campaign validate

# SOMENTE APÓS AUTORIZAÇÃO POSTERIOR — não executado na preparação:
.venv/bin/python -B -m experiments.energy_campaign run \
  --control-sha256 SHA_MOSTRADO_NO_FREEZE \
  --authorize-campaign energy-powersaver-20261109

# Consultas read-only:
.venv/bin/python -B -m experiments.energy_campaign status

# Solicitação persistida de interrupção segura:
.venv/bin/python -B -m experiments.energy_campaign stop

# Retomada explícita, após diagnóstico; não repete tentativa consumida:
.venv/bin/python -B -m experiments.energy_campaign run \
  --control-sha256 MESMO_SHA \
  --authorize-campaign energy-powersaver-20261109 \
  --resume --reason 'diagnóstico e verificação realizados pelo pesquisador'
```

O processo roda diretamente no terminal, sem depender do Codex. Para deixá-lo
autônomo, o pesquisador pode usar seu gerenciador de terminal/sessão habitual.
Nenhuma tarefa persistente é iniciada pela preparação. Impedir suspensão e manter
alimentação externa são responsabilidades operacionais; o monitor rejeita uma
mudança detectada e não modifica a configuração do desktop.

## Estados, falhas, retomada e consolidação

- PENDING: coleta ainda não iniciada.
- RUNNING: tentativa consumida em coleta, ou último estado observado antes de
  uma queda abrupta; conferir processo/lock antes de interpretar como atividade viva.
- ACCEPTED: recibo técnico validado no journal, não aprovação universal dos detectores.
- REJECTED: falha técnica diagnosticada registrada pelo controlador original.
- FAILED: falha de execução/controlador/validação sem progressão.
- INTERRUPTED: divergência ambiental ou solicitação de interrupção.

`status` mostra partição, estados/contagens, tempo decorrido, ETA aproximado,
último erro e último evento ambiental de transição. O ETA usa tempo total por
aceitação e inclui pausas; não é promessa de duração. Durante cada tentativa,
`collection/<id>/attempt-1/environment.jsonl` contém as últimas condições; logs
estão em `execution.log`. Checks/transições gerais ficam em `automation/events/`.

As transições entre partições reutilizam checkpoints e verificam os hashes do
predecessor. Sementes, configurações, modelos, calibrações e TEST mantêm seus vínculos.
Falha de um par em CAL_B preserva a inelegibilidade desse par, sem retuning;
falha estrutural de calibração impede checkpoint e bloqueia TEST.

Retomada é permitida apenas com o mesmo plano/controle, referência ambiental,
diagnóstico e `--resume --reason`. Slots aceitos são verificados e não recoletados.
Uma coleta concluída com selo válido pode ser recuperada offline pelo backend.
Uma tentativa parcial, desconhecida ou com selo inválido exige diagnóstico; o
adaptador não oferece retry automático. Substituições, attrition ou criação de
outra autoridade exigem decisão explícita separada segundo o protocolo original.
Se houver output offline parcial que o framework não possa completar, ele é
preservado para diagnóstico, sem remoção automática. Isso é uma restrição deliberada.

O último checkpoint TEST consolida avaliações/resumo pelo framework existente;
não é necessário reexecutar coleta para consolidar. Uma retomada após coleta
concluída pode completar somente o processamento offline faltante quando suportado.

## Decisão de prontidão

READY exige testes, checks, dois pilotos aceitos/caracterizados, revisão da
adequação, plano validado e ambiente congelado. READY_WITH_RESTRICTIONS identifica
restrições técnicas explícitas. Perfil incorreto, pilotos ausentes ou plano ainda
não congelado significam NOT_READY para coleta definitiva, mesmo com código preparado.

Toda campanha anterior permanece preservada. Não criar commit nesta atividade.
