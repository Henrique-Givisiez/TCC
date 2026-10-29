# Integração científica reduzida — validação offline

Atualização operacional: a [materialização aprovada](scientific_reduced_materialization_20261029.md) registra os56 JSONs,32 seeds, plano e lock real de ambiente, com comandos/hashes efetivos. A coleta permanece não iniciada. As descrições de pendências abaixo registram a entrega anterior à materialização.

Contrato executável novo: [scientific_protocol_reduced_20261029.json](scientific_protocol_reduced_20261029.json), versão2. O protocolo anterior de98 runs e todos os resultados DEVELOPMENT/Stage14/15 permanecem preservados. Código atual exige4 BASELINE,8 CAL-A,8 CAL-B e12 blocos×C16/M16/E16=56 slots, com teto58 tentativas e duas substituições exclusivamente técnicas (uma por slot). Nenhuma configuração/plano executável/seed de tráfego real foi materializada.

Ordem prospectiva: `CME,MEC,ECM,EMC,MCE,CEM; MEC,ECM,CME,MCE,CEM,EMC`, C=C16,M=M16,E=E16. Cada permutação duas vezes; posição e precedência adjacente balanceadas. São32 grupos de seeds independentes:20 preparações e12 blocos. Configurações futuras mantêm o template vinculado, uma vítima, pool2, legítimos4×4 `/medium`, uma origem ofensiva16 RPS `/medium` ou `/expensive`, mesmos workers/timeouts/recursos. Sem E12/E20 no TEST.

Gates numéricos preservados: seleção[30,390), suporte≥342/360 por execução; CAL-A média macro FPR≤1%, máximo individual≤5%; CAL-B≤2% e≤5%. Reprovação primária de qualquer método bloqueia a próxima partição. CUSUM congelado mantém k=.5, mesma grade fechada, replay causal por h e menor h elegível. Sem candidato elegível: rejeição persistida. B/TEST não ajustam parâmetros. Os quatro métodos usam os mesmos runs; secundárias não aceitas permanecem explicitamente não avaliadas.

## Proteção e continuidade

Backend científico reutiliza `StressManager`, `Watcher`, `SampleFreshness` e reconciliação R2 adaptada de `stress_processing`, sem alterar esses componentes históricos. Preflight futuro inspeciona imagens/código/ambiente, captura passiva e recursos de um processo ocioso; antes de liberar as fontes, compara afinidade e cadeia de quotas/cpuset/memória/PIDs da vítima real com a evidência. Import/fixtures não acessam Docker.

Proteção idêntica à dos pilotos: coorte móvel de10 s maturada por3 s,≥50 starts e≥20% sem2xx no prazo individual3 s; fila ofensiva>128 por≥10 s; aquisição Docker sem amostra nova por>5 s. Valores CPU repetidos não renovam nem invalidam frescor: timestamp de aquisição deve avançar. A primeira parada envia comando somente à origem ofensiva. Continua legítimos/coleta até390 s quando operacionalmente possível; admissions anteriores podem iniciar depois do comando, e timeout não cancela trabalho na vítima.

Revisão técnica exige journals/CSV/inventário/certificados coerentes, replay causal do observador por prefixos disponíveis e cleanup comprovado. Tempos de decisão, comando, stop recebido, fim da emissão e drenagem permanecem reais. Parada por serviço tecnicamente íntegra é aceita, não substituída. Recibos vinculam observações de impacto e arquivos; mudança de código/plano ou tentativa já marcada impede repetição. Se recuperação terminal não for confirmada, a próxima coleta para para diagnóstico: não há bypass automático ou nova tentativa para procurar recuperação favorável. Indeterminação/drenagem incompleta também bloqueiam continuidade.

## Avaliação e ICs

Prazo primário é `actual_end_seconds`, com overlap positivo da janela e disponibilidade da decisão dentro da emissão real. Fim de janela e disponibilidade são campos distintos. Disponibilidade de fechamento é simulada, não latência computacional medida. Sem detecção elegível: miss, atraso observado=null; decisão posterior não transforma miss em acerto. Prazo muito curto mantém miss com suporte explícito. Eventos sem emissão observável exigem diagnóstico, sem FN fabricado ou retry automático.

Exposição e impacto são calculados uma vez por run, não multiplicados por cinco features/quatro métodos. ACTIVE de serviço começa150 s e termina no certificado real; POST segue até390. Exposição ofensiva usa actual_start→actual_end. Resumos por coorte/fase incluem starts/términos/2xx por segundo, sucesso no horizonte b+3, timeout, pendências/idade, médias de duração de todos os términos e dos2xx, CPU média Docker e recuperação. Percentis permanecem individuais. Taxas realizadas e duração de exposição acompanham os contrastes E16−M16: estimam a política protegida, não efeito a dose constante. Parada informativa não é censura independente para extrapolar detecção até120 s.

| Métrica | IC pontual95% | Unidade / denominador |
|---|---|---|
| Detecção, qualquer falso alarme, parada antecipada, recuperação confirmada |Wilson; exato binomial nos extremos|Uma execução por condição em cada bloco; n elegível explícito|
| Diferença de detecção entre métodos/cenários |Discordâncias pareadas, exatos97,5% combinados por Bonferroni|Somente blocos com ambos os eventos avaliados|
| FPR, recall, F1, persistência POST e fração restrita sem detecção |BCa10000; Hoeffding para distribuição limitada degenerada|Resumos por execução; mesmos índices de bloco preservam pares|
| Frações de sucesso/timeout de serviço |BCa10000; Hoeffding limitado se degenerado|Média macro das frações por execução, não proporção de todas as requisições agrupadas|
| Exposição, horário de parada/fim, taxas de atendimento, médias de duração/CPU, pendências e suas diferenças pareadas |BCa10000; IC=null se degenerado/insuficiente, com motivo|Médias de resumos por execução/bloco; diferença antes do bootstrap. Nenhum bound fictício de timeout|
| Atraso condicional de detecção |IC da média somente com≥8 detectados; média/mediana=null sem detecções|Somente detectados, com misses e seleção explícitos|
| p50/p95 de duração e janelas individuais |Sem IC agregado e sem média de percentis|Descrições por execução; janelas/requisições não viram réplicas|

Todos os ICs condicionam ao treinamento congelado, são pontuais e não certificam superioridade/equivalência. BCa e semente de análise permanecem os existentes. Reamostragem não trata janelas como independentes. Agrupamento por bloco conserva métodos e cenários; pares incompletos são alinhados pelo ID de bloco, nunca por posição remanescente.

Falha técnica interrompe o runner e preserva tentativa. Operador pode aprovar uma das duas substituições por hash da falha ou encerrar explicitamente um slot TEST como atrição, exigindo motivo técnico permitido e cleanup confirmado. BASELINE/CAL-A/CAL-B não aceitam redução oportunista de n. Atrição não pode selecionar serviço ruim/miss/taxa baixa. Resultados válidos das outras condições permanecem; resumo mostra slots ausentes e n de pares/operacionais. Não há encerramento silencioso ou substituição automática.

## Validação e próximos passos

[Testes científicos](../tests/test_scientific_campaign.py) reutilizam o fluxo completo e incorporam E16 com fim antecipado, misses de prazo curto, ICs de impacto/exposição, pares incompletos e atrição explícita. Também verificam rejeição A/B, h por replay, corrupção de artefatos, dois limites de substituição, locks, crash/retomada sem nova coleta e recuperação offline via exportação/Stage9/features reais de fixture. Testes dos pilotos/fontes validam observador causal, controle exclusivo do atacante, respostas em voo e drenagem. O registro compacto final acompanha esta entrega.

Pendências antes de qualquer coleta: materializar/revisar56 configurações e plano,32 seeds auditadas contra o inventário então atual, diretórios novos, lock real de ambiente/imagens/recursos e hashes do código; validar o plano e autorizar BASELINE. Readiness real do backend não foi exercitada nesta tarefa. Orçamento:6h04 nominal,7h28 operacional incluindo drenagem/repouso,9h20 administrativo,total16h48; teto58 tentativas=17h24. Implementação/análise/diagnóstico excepcional ficam fora desse envelope.

Comandos futuros, após materialização, substituindo paths/hashes efetivos:

```bash
.venv/bin/python -B -m experiments.scientific_campaign --plan PLANO --plan-sha256 HASH_PLANO validate
.venv/bin/python -B -m experiments.scientific_campaign --plan PLANO --plan-sha256 HASH_PLANO run --partition BASELINE --authorize-partition BASELINE
.venv/bin/python -B -m experiments.scientific_campaign --plan PLANO --plan-sha256 HASH_PLANO run --partition CAL_A --authorize-partition CAL_A --checkpoint-sha256 HASH_BASELINE
.venv/bin/python -B -m experiments.scientific_campaign --plan PLANO --plan-sha256 HASH_PLANO run --partition CAL_B --authorize-partition CAL_B --checkpoint-sha256 HASH_CAL_A
.venv/bin/python -B -m experiments.scientific_campaign --plan PLANO --plan-sha256 HASH_PLANO run --partition TEST --authorize-partition TEST --checkpoint-sha256 HASH_CAL_B
```

Cada comando executa somente a partição autorizada e para no checkpoint. Repetir o mesmo comando retoma evidências já concluídas; claim existente nunca gera outra coleta. Após diagnóstico de falha técnica:

```bash
.venv/bin/python -B -m experiments.scientific_campaign --plan PLANO --plan-sha256 HASH_PLANO approve-technical-replacement --failure-sha256 HASH_FALHA
# Alternativa exclusivamente para slot TEST tecnicamente falho, com cleanup confirmado:
.venv/bin/python -B -m experiments.scientific_campaign --plan PLANO --plan-sha256 HASH_PLANO record-test-attrition --failure-sha256 HASH_FALHA
```

Escolher uma via explicitamente; slot aceito ou encerrado como atrição não pode ser substituído. Reprovação de CAL-B permanece bloqueio científico definitivo sob essa autoridade, sem autorização de refit ou nova amostra por essas opções.

## Parametrização mínima da autoridade

Inventário, taxas ofensivas/endpoints, cenário de controle, ordens, grupos de seeds e contraste operacional são lidos da especificação vinculada. A autoridade padrão continua a campanha56/58, com SHA256 literal conferido no carregamento: editar seu JSON não muda silenciosamente a campanha. Outra especificação requer seleção explícita das duas variáveis `SCIENTIFIC_SPEC_PATH` e `SCIENTIFIC_SPEC_SHA256`, além do vínculo correspondente no plano. O subprocesso de coleta herda essa seleção e revalida o mesmo plano. Não existe autodetecção de campanha ou alteração por resultados. Mantém-se o único contraste operacional suportado; não se criou um framework de múltiplas análises arbitrárias.

O campo de impacto segue o formato `paired_<esquerda>_minus_<direita>`. Na campanha atual permanece exatamente `paired_E16_minus_M16`, com os mesmos valores e consumidores. Testes com rótulos diferentes verificam o nome derivado da especificação. O resumo de detecção também deriva os dois cenários do contraste. Contagens de slots e grupos de seeds são calculadas da partição e das ordens; o teto de tentativas vem do contrato.

A validação de parametrização compara os resultados completos atuais com o avaliador anterior do commit de referência, incluindo chaves, ICs, pareamento e impacto. Uma autoridade temporária a7 RPS é aceita somente com seu próprio hash/plano; a autoridade atual a rejeita. Um controle C16 de fixture em formato real, sem evento, atravessa exportação, recuperação do backend, Stage9/features, calibração independente de fixture, processamento dos quatro métodos e avaliação: não fabrica detecção, miss ou atraso ofensivo. Todos os arquivos dessa fixture ficam em diretórios temporários.
