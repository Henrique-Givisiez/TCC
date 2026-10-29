# Sucessor da campanha reduzida — handoff de relógio

Plano sucessor: [plan.json](../experiments/protocols/scientific_reduced_clock_r2_20261029/plan.json), SHA256 `6240452e214b0748b023a084edd6dcf4fd2fd0a43744ed70a37bdb88a4319bc4`. [Handoff](../experiments/protocols/scientific_reduced_clock_r2_20261029/handoff.json), SHA256 `10a8020b986525bc066b6531b2cd237fab5dff3206886ba37602f8bb4b58a5ee`. Não houve Docker, coleta ou aprovação real de substituição nesta preparação.

As56 entradas/configurações,32 seeds, ordem, especificação científica, gates, ambiente e teto58 tentativas são exatamente os do plano anterior. Configurações não foram copiadas ou recriadas. Mudam somente freeze de código (source_manager, scientific_collection, protocol e scientific_campaign), raiz de resultados, auditoria atualizada e vínculo do handoff. A extensão do runner serve à importação verificável da tentativa consumida; não flexibiliza gates de coleta ou torna PRE_RELEASE_CLOCK_FAILURE genericamente elegível.

Plano anterior preservado, SHA256 `752b8c516faf0c931ed19347b298d7348e670797d1e286dfe6c9f6fa7b518385`. Raiz anterior preservada: `/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/scientific-reduced-20261029`. Todos os arquivos dessa raiz estão vinculados individualmente; cadeia dos dois eventos originais, claim, execução, inventário e cleanup são revalidados. Qualquer arquivo alterado, removido ou acrescentado impede handoff/aprovação/retomada. O diagnóstico é vinculado separadamente, sem editar failure.json.

## Uma substituição específica, ainda não aprovada

Slot `sci56_BASELINE_01_C16`, condição C16, seed4481859911000311360. Tentativa1 **consumida**, encerrada antes da liberação da carga científica: inventário sem run binding, sem comandos/journals de fontes, clock guard reprovado, exit1 e cleanup confirmado. Houve uma requisição histórica de setup sem trabalho; não confundir ausência de carga científica com ausência de todo tráfego HTTP.

Falha histórica: `IDENTITY_JOURNAL_MISMATCH`, SHA256 `1608b5cf5d134fb96e11919ce87f01f2779154295654eb645186294638b0dfbd`. É sintoma secundário do request_log inexistente. Diagnóstico corrigido: `PRE_RELEASE_CLOCK_FAILURE`, [evidência vinculada](clock_guard_correction_20261029/diagnosis.json). A autorização exige o hash da falha original e a prova de causa/estado pré-liberação do handoff; nenhum código é trocado no registro histórico.

A substituição preparada é somente `attempt-2` do mesmo slot/configuração/seed, com novo run ID na futura execução. Ao ser aprovada, consumirá a primeira das duas permissões globais, deixando no máximo uma para outra falha técnica permitida. Agora:1 tentativa consumida,0 substituições aprovadas,0 tentativas na raiz sucessora. Quando todas as56 entradas forem válidas sem novas falhas, serão57 tentativas contando a original; permanece teto58/17h24. Não há reinício da contagem com a raiz nova.

Nova raiz reservada: `/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/scientific-reduced-clock-r2-20261029`; ausente nesta preparação. O primeiro comando mutável nessa raiz importará registros prospectivos HANDOFF_IMPORTED e TECHNICAL_FAILURE, preservando os originais. Não cria attempt-1 nova. Antes da aprovação específica, executar BASELINE recusa coleta. Depois, só o slot importado começa em attempt-2; os demais permanecem attempt-1. Tentativa/recibo existentes são recuperados sem invocação de carga repetida. Aprovação duplicada ou de hash desconhecido é recusada.

## Comandos exatos — execução futura separada

1. Validar offline, sem consumir tentativa:

```bash
.venv/bin/python -B -m experiments.scientific_campaign --plan experiments/protocols/scientific_reduced_clock_r2_20261029/plan.json --plan-sha256 6240452e214b0748b023a084edd6dcf4fd2fd0a43744ed70a37bdb88a4319bc4 validate
```

2. Aprovar **somente** a substituição identificada acima, se autorizado. Não executa carga:

```bash
.venv/bin/python -B -m experiments.scientific_campaign --plan experiments/protocols/scientific_reduced_clock_r2_20261029/plan.json --plan-sha256 6240452e214b0748b023a084edd6dcf4fd2fd0a43744ed70a37bdb88a4319bc4 approve-technical-replacement --failure-sha256 1608b5cf5d134fb96e11919ce87f01f2779154295654eb645186294638b0dfbd
```

3. Retomar somente BASELINE (faz prontidão por tentativa e, se passar, executa as quatro entradas BASELINE). Não foi executado aqui:

```bash
.venv/bin/python -B -m experiments.scientific_campaign --plan experiments/protocols/scientific_reduced_clock_r2_20261029/plan.json --plan-sha256 6240452e214b0748b023a084edd6dcf4fd2fd0a43744ed70a37bdb88a4319bc4 run --partition BASELINE --authorize-partition BASELINE
```

O checkpoint BASELINE não autoriza CAL-A. Repetir o comando de BASELINE reutiliza recibos/checkpoints, sem repetir a tentativa original ou os slots aceitos. Falha de prontidão/recuperação interrompe normalmente. Não apagar claims, alterar binding, editar plano antigo ou invocar o comando antigo para contornar a correção.

## Validação e pendências

28 testes de campanha/relógios/fontes aprovados, incluindo fluxo56, gates A/B, substituições, handoff com recusa antes da aprovação e de evidência adulterada, attempt-2 do slot correto e retomada sem coleta duplicada. A checagem de segurança do handoff foi novamente executada após reforçar a cadeia de journal e a autoridade da claim. Tudo em fixtures temporárias; nenhuma aprovação real.

Prontidão real não foi consultada nesta tarefa. O lock de ambiente anterior é mantido; o preflight futuro verificará ambiente/imagens/captura/recursos e a nova prova de relógio antes da liberação. Fonte anterior e diagnóstico permanecem arquivados. Pendências: decisão explícita sobre aprovação específica e posterior execução de BASELINE. Esta entrega não as presume.
