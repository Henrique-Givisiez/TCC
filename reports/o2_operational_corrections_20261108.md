# O2 — Correções operacionais C1.3.5

Base: `25bd463f23bbea7a5fccc661ae7eead73c584b01`. Sem Docker, experimentos, plano materializado, seeds definitivas, liberação ou commit. A especificação permanece byte a byte com SHA256 `a4a5eb198be5e7ac770856e616af454c566993c6b1ef69edf0948bc9b3be1734` e execution_release.allowed=false.

## Inventário

- `experiments/scientific_safety.py`: reserva de armazenamento, guard de liberação e reconhecimento estrito de perda de captura encerrada.
- `experiments/scientific_collection.py`: precedência de falhas, readiness independente, proteção de exportação/features e bloqueios de coleta/subprocesso.
- `experiments/scientific_campaign.py`: bloqueio adicional no slot e rejeição de readiness contraditória na continuação.
- `analysis/detection/scientific/engine.py`: reserva de disco antes de artefatos/candidatos de calibração.
- `experiments/c135.py`: launcher que fixa caminho/hash da versão e propaga ambiente/argumentos ao controlador existente.
- `tests/test_o2_safety.py`: testes offline do backend e das proteções.
- Este relatório.

## Recuperação: esclarecimento operacional

No contrato direto, recovery_confirmed=false é ausência de recuperação **HTTP**, resultado científico que permanece aceito quando os demais contratos passam. Não é causa de substituição, exclusão ou retuning. A expressão “recovery failure” nos controles de progressão refere-se à recuperação **operacional do ambiente**, não à métrica HTTP: cleanup confirmado, readiness independente e preflight novo antes de consumir outra tentativa.

Essa separação já existia na lógica direta e foi preservada. Agora cleanup com verified=true mas readiness.verified=false também é explicitamente recusado no backend e na continuação. Não se alteram métricas, definições dos eventos ou seleções científicas. Os testes diretos existentes exercitam nonrecovery com continuação, cleanup bloqueado, preflight e retomada.

## Classificação: antes e depois

| Condição | Antes | Depois |
|---|---|---|
| Retorno 1 por perda de captura, journals e processos encerrados | DRAIN_OR_EXECUTION_UNCONFIRMED antes de examinar captura | CAPTURE_LOSS somente com prova convergente descrita abaixo |
| Retorno não zero sem diagnóstico conclusivo | Bloqueio conservador | Preservado |
| Encerramento de produtores incompleto | Bloqueio conservador | Preservado; não reclassifica como perda recuperável |
| Cleanup ausente / execução ausente | INDETERMINATE_ATTEMPT | Preservado |
| Cleanup não verificado | CLEANUP_UNCONFIRMED | Preservado, inclusive readiness contraditória |
| Dataset inválido após execução confirmada | DATASET_INVALID | Preservado |
| Espaço insuficiente em exportação/análise | Nem todas as etapas tinham guard explícito | ContractError antes da etapa protegida; evidências mantidas |
| Features parcialmente escritas | Erros posteriores de leitura/validação | Bloqueio explícito se faltar manifest; saída não apagada |

CAPTURE_LOSS exige reconcile/ground truth concluídos, controlled_closure=true, retorno global exatamente 1, status incomplete com simulation_end e producers_drained=true. Todos os erros devem indicar explicitamente falha de integridade de captura, sem erro de origem diferente. Exige também summary CPU finalizado e sem fatal_error; sidecars CSV/PCAP iguais aos registrados no status; processos tcpdump com retorno 0 ou SIGTERM, sem launch_error; estatísticas completas relidas do stderr e iguais às dos sidecars; accepted coerente com zero/mais descartes; pelo menos uma captura com drops positivos. Arquivos ausentes, contraditórios ou estatísticas incompletas não permitem essa reclassificação.

Cleanup do backend é checado antes de tudo isso. A mudança classifica a falha técnica; não aceita o dataset nem autoriza automaticamente uma substituição. O controlador mantém whitelist, cleanup, idle e preflight de continuação; a partição não produz checkpoint com slots pendentes. Substituição permanece aprovação explícita pelo hash, no mesmo slot/seed/cenário e orçamento existente.

## Launcher e liberação

Usar futuramente, para comandos do controlador:

```
.venv/bin/python -B -m experiments.c135 --plan CAMINHO --plan-sha256 HASH status
```

O launcher confere o SHA256 fixado, recusa seleção conflitante e fornece SCIENTIFIC_SPEC_PATH absoluto e SCIENTIFIC_SPEC_SHA256 ao subprocesso. O controlador continua usando os mecanismos existentes, e os descendentes herdam o ambiente. Retorno do controlador é propagado. O default histórico global não foi alterado.

Além dos guards existentes em sequence/run_partition, há guard no collect_slot, no DockerBackend.collect antes de Popen e no main da coleta antes de ler/usar a tentativa. O entrypoint ainda exige plano, tentativa consumida, caminhos e preflight vinculados. O launcher não pode liberar execução.

O contrato estrutural ainda recusa uma especificação direta liberada: O3 deverá revisar expressamente a autoridade de liberação e sua versão/hash, além do plano e freezes. Não se introduziu um bypass via flag, variável de ambiente ou alteração de allowed. Esta etapa prepara os pontos de verificação; não cria uma autoridade futura aprovada.

## Armazenamento e retomada

Reserva de 4 GiB verificada antes de exportação, extração/reutilização de features e publicação de artefatos/candidatos científicos. Para exportação soma-se ainda o tamanho lógico raw a copiar. Os guards operacionais existentes de preflight/durante coleta continuam intactos.

A verificação não reserva espaço atomicamente nem prevê todo tamanho futuro: concorrência no filesystem e crescimento de candidatos continuam riscos. Falha real de escrita continua erro; arquivos parciais são preservados para diagnóstico. O journal/intents impedem repetir coleta consumida; pode-se retomar recuperação offline quando seus pré-requisitos forem demonstrados. Manifest parcial/corrompido não é reconstruído, sobrescrito ou silenciosamente ignorado. Não há limpeza automática de evidências.

## Testes e limites

Suíte focalizada: 33 testes aprovados em 8,647 s (test_o2_safety, test_direct_campaign_operations, test_c135_protocol). Após acrescentar o caso DATASET_INVALID, os seis testes O2 passaram novamente em 0,231 s. Os subcasos percorrem DockerBackend.recover, com arquivos reais temporários de status/sidecars/stderr e dependências de reconciliação/validação simuladas: perda comprovada, erro misto, drain incompleto, cleanup/readiness não confirmados, evidência ausente/contraditória e dataset inválido. Não são apenas códigos artificiais entregues ao controlador.

Também verificados: launcher/hash conflitante/propagação, bloqueio antes de leitura de tentativa/Popen e preservação de bytes em falha de espaço. Testes existentes cobrem interrupção após consumo, recuperação sem nova coleta, resultados científicos desfavoráveis e ausência de substituição automática. git diff --check passou.

Suíte ampliada inicial, incluindo test_scientific_campaign: 47 testes aprovados em 246,037 s. Verificação da versão final: 36 testes aprovados em 17,628 s, incluindo todos os testes O2/diretos/C1.3.5 e os casos de recuperação real de arquivos, tentativa indeterminada e retomada sem repetir coleta de ScientificCampaignTests. Não há validação real de Docker ou carga nesta etapa.

## Pendências O3 e prontidão

Pronto para revisão das correções offline, **ainda bloqueado para campanha**. O3 exige: revisar esta interpretação de recuperação; revisar alterações e testes; concluir revisão formal da liberação; congelar código/imagens/ambiente/seeds/plano com hashes definitivos; selecionar C1.3.5 inequivocamente e conceder autorização explícita. Nenhum plano ou artefato antigo deve ser reautorizado implicitamente pelos novos guards.
