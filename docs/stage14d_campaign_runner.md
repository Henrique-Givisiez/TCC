# Stage 14D.0 — coordenador operacional da campanha

`python -B -m experiments.stage14_campaign` é um processo independente de
ChatGPT/Codex. Consome a matriz, na ordem persistida, e a autoridade explicitamente
identificada por path e SHA256. Não escolhe seeds, cenários, parâmetros,
detectores, thresholds ou métricas. Não importa scorer, calibrator ou evaluator.

**Sem release explícita TEST permanece LOCKED.** O adaptador e o executor
exigem manifesto de release com path e SHA256, vinculado à identidade exata da
campanha, HEAD, environment, binding, freeze, evaluation protocol, protocol v2,
matrix, seed plan e ordem das entradas. Não existe `--allow-test`, backend
alternativo pela CLI ou variável que retire esse bloqueio. O binding histórico
e o evaluation protocol continuam LOCKED: a autorização é um artefato separado.
Criar esse artefato requer autorização humana explícita; a existência do código
não constitui release. A entrega original Stage14D.0 não executou TEST.

## Estado e persistência

O diretório administrativo deve ficar fora do root científico. Ele contém:

- `campaign_state.json`: identidade SHA256 do plano/autoridade, HEAD e referências
  de environment/binding/protocol/seed plan/matrix/evaluation/freeze, entradas
  ordenadas com configuração congelada, seed/cenário/posição, tentativa, output,
  timestamps, estado, motivo técnico, cleanup e recibo de integridade/run ID.
- `operations.jsonl`: log persistente de transições, validação técnica, cleanup e
  checkpoints; nenhuma interpretação de eficácia.
- `campaign.lock`: lock exclusivo `flock`, liberado pelo kernel quando o processo
  termina. Não se usa apenas PID para decidir ownership.
- `stop_requested.json`: solicitação administrativa de parada entre entradas.

Escrita do checkpoint: temporário no mesmo diretório, flush, fsync do arquivo,
replace atômico e fsync do diretório. O checkpoint é a autoridade de recuperação;
um log eventualmente interrompido não autoriza repetir uma coleta. O armazenamento
deve suportar `flock`, atomic rename e fsync (preferir filesystem local Linux).

Transições permitidas:

```text
PENDING -> RUNNING -> COMPLETED_VALID
                 -> FAILED | INCOMPLETE | INVALID -> STOP/revisão humana
```

Antes de cada entrada: revalidar autoridade, preflight administrativo, verificar
ausência de output, persistir RUNNING e só então invocar o executor existente.
Depois: exigir término certificado e Stage8/9/10, valid/eligible, configuração,
lineage e inventários SHA256; confirmar cleanup do executor e só então persistir
COMPLETED_VALID. O coordenador não mata processos alheios nem remove evidências.
Stage9 é o certificado técnico existente; não se implementa uma nova política de
validade. Arquivos observacionais podem ser verificados por hash na futura coleta
autorizada, sem parsing de labels nem análise de eficácia no coordenador.

## Retomada e falhas

`resume` exige a mesma autoridade e o mesmo plano. Revalida todos os recibos
COMPLETED_VALID antes de avançar. Nunca repete esses runs e continua apenas de
PENDING. Campanha completa é idempotente: zero execuções e zero alterações no
checkpoint, log e outputs (o lock administrativo existente é apenas adquirido).

FAILED, INCOMPLETE, INVALID, checkpoint inconsistente/corrompido, hash divergente
e output inesperado causam STOP. Não existe reset/retry automático. Uma nova
tentativa futura exige decisão humana e preservação auditável da anterior.

RUNNING recuperado sem ownership anterior não prova falha científica: registra
INCOMPLETE operacional com **scientific completion unknown**, preserva qualquer
output e para. Não tenta terminar Stage8/9/10 nem aceitar a tentativa sozinho.
Se ainda houver processos/containers científicos, a validação de ambiente para
antes dessa classificação. Um segundo coordenador ativo é rejeitado pelo flock.

Interrupção antes de RUNNING deixa PENDING; interrupção após RUNNING ou após
output exige revisão; após COMPLETED_VALID a retomada verifica e pula a entrada.
SIGKILL/perda de energia não disparam rerun. Ctrl-C registra interrupção quando
possível, preservando evidências. Para parada segura prefira `abort` abaixo,
que deixa o run atual terminar. Uma falha de cleanup também impede avanço.

## Comandos futuros, somente depois de release válida

Executar a partir do root do repositório, com a autoridade final aprovada para a
execução. Os placeholders exigem paths e hashes explícitos, não defaults móveis.

```bash
mkdir -p experiment_results/stage14d-campaign
nohup .venv/bin/python -B -m experiments.stage14_campaign start \
  --campaign-dir experiment_results/stage14d-campaign \
  --binding <binding.json> --binding-sha256 <SHA256> \
  --release <release.json> --release-sha256 <SHA256> \
  --evaluation-protocol experiments/protocols/stage14_test_evaluation_protocol_v1.json \
  --evaluation-sha256 <SHA256> \
  > experiment_results/stage14d-campaign/console.log 2>&1 < /dev/null &
```

`nohup` e a execução em background sobrevivem ao fechamento da sessão Codex e do
terminal; não sobrevivem a reboot. Nesse caso usar resume após verificar o
estado. Não lançar outro `start` sobre um checkpoint existente.

Status read-only (lê apenas metadados do checkpoint, sem consultar Docker ou
abrir dados científicos):

```bash
.venv/bin/python -B -m experiments.stage14_campaign status \
  --campaign-dir experiment_results/stage14d-campaign
```

Exibe total, pending/running/completed_valid/failed/incomplete/invalid,
posição atual/última, timestamps, elapsed administrativo e pedido de parada.
O tempo administrativo inclui pausas e não é tempo experimental.

Retomar no mesmo diretório, com os mesmos paths/hashes de autoridade:

```bash
nohup .venv/bin/python -B -m experiments.stage14_campaign resume \
  --campaign-dir experiment_results/stage14d-campaign \
  --binding <binding.json> --binding-sha256 <SHA256> \
  --release <release.json> --release-sha256 <SHA256> \
  --evaluation-protocol experiments/protocols/stage14_test_evaluation_protocol_v1.json \
  --evaluation-sha256 <SHA256> \
  >> experiment_results/stage14d-campaign/console.log 2>&1 < /dev/null &
```

Parada controlada, sem sinalizar/matar simulador:

```bash
.venv/bin/python -B -m experiments.stage14_campaign abort \
  --campaign-dir experiment_results/stage14d-campaign
```

O pedido é persistente. Após o run atual validado não começa outro. Antes de
retomar uma parada voluntária, um operador deve revisar o checkpoint e arquivar
o arquivo administrativo `stop_requested.json` fora do diretório da campanha;
nenhum output científico deve ser removido/modificado. Não limpar esse pedido
automaticamente. Em falhas/orfandade, esta operação **não** autoriza retry.

## Isolamento e validação desta implementação

Testes usam exclusivamente temporários, fixtures sintéticas DEVELOPMENT e mocks.
Cobrem planejamento de 48 entradas, ordem, persistência, interrupções, concorrência,
retomada, certificados técnicos, colisão, atomicidade, idempotência e o guard fatal.
Os testes não executam nem inspecionam TEST real. A análise científica TEST só
poderá ocorrer após terminar a coleta e mediante autorização separada.

## Release explícita e checkpoint inicial

`experiments.stage14_test_release` valida a release independentemente de sua
construção, recarregando metadados/ambiente e exigindo os hashes e a ordem exatos.
Permite somente coleta científica e validação técnica. Fitting, calibration,
tuning, scoring/evaluation científicos, alteração de detector/threshold e retry
automático permanecem proibidos. Não autoriza novos runs fora da matriz.

A identidade da campanha é SHA256 do plano congelado antes da release. A release
refere essa identidade; o checkpoint contém adicionalmente path/SHA da release
e compara o plano completo no resume. Isso evita referência circular. A release
deve ser emitida somente após o commit e a finalização do environment/binding.
Nenhum parâmetro científico ou artefato histórico é reescrito.

Antes de destacar o processo, criar e consultar o checkpoint sem executar:

```bash
.venv/bin/python -B -m experiments.stage14_campaign initialize \
  --campaign-dir <diretorio-administrativo> \
  --binding <binding.json> --binding-sha256 <SHA256> \
  --evaluation-protocol experiments/protocols/stage14_test_evaluation_protocol_v1.json \
  --evaluation-sha256 <SHA256> \
  --release <release.json> --release-sha256 <SHA256>
```

O estado inicial deve ser exclusivamente PENDING. A seguir iniciar `resume`
via nohup, usando os mesmos paths/hashes, não `start` sobre o checkpoint criado.
O executor persiste a referência da release no registro administrativo de cada
run. O log operacional registra `execution_authority_accepted` antes de RUNNING.
Preflight continua independente da release e não concede execução por si só.
