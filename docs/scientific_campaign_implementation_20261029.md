# Protocolo científico fechado e integração offline

Base adotada: **6 BASELINE, 12 CAL-A, 16 CAL-B e 16 blocos TEST × C16/M8/E4/E8**, todos com 16 RPS legítimos. N2 continua evidência exploratória preservada. O [contrato numérico](scientific_protocol_20261029.json) está fechado; a campanha real ainda não foi materializada nem liberada. A [proposta anterior](scientific_protocol_proposal_20261029.md) registra a justificativa e o orçamento, não substitui o contrato executado. Não se alteraram as autoridades DEVELOPMENT/Stage14/15 nem os componentes históricos.

| Decisão fechada | Regra implementada |
|---|---|
| BASELINE | Seis realizações C16; ajuste em [30,390), ddof=1 e peso por observação. Momentos fixos para Z-score/EWMA/CUSUM congelado; CoV L6 sem fit externo. Feature primária sem sigma positivo ou com suporte <342/360 bloqueia a cadeia |
| CAL-A, Z/CoV/EWMA | Quantil empírico superior de 99%, índice zero ceil((N−1)×.99); decisão estrita >. Verificação de elegibilidade: média dos FPR por run ≤1%, nenhum >5%, cada run ≥342 decisões disponíveis. Não ajustar o quantil se reprovar |
| CAL-A, CUSUM congelado | k=.5, inicial zero, h_ref do CUSUM original em A; s=h_ref se positivo, senão s=1. Grade s×{0,.25,.5,.75,1,1.5,2,3,4,8,16}. Replay completo desde zero para cada h/run, sem reset em 30 s. Escolher menor h numérico com média FPR ≤1%, máximo por run ≤5% e disponibilidade ≥95%. Não assumir monotonicidade. Igualdade a h é aceita sem alarme |
| Nenhum candidato elegível | Publicar rejeição, incluindo suporte e candidatos, interromper sem checkpoint CAL-A. Sem expansão de grade, aumento de amostra ou fallback em B/TEST |
| CAL-B | Uma aplicação dos modelos/h fixos a 16 C16 independentes. Aprovar cada método primário se média FPR ≤2%, nenhum run >5%, disponibilidade ≥95% em todos. As desigualdades são inclusivas. Reprovação de qualquer um dos quatro em `request_starts` bloqueia TEST. Reexecutar a análise para conferir integridade não permite retuning ou nova coleta |
| Secundárias | Mesmas cinco features pré-declaradas. Ausência de baseline/limiar/verificação válida deixa a secundária explícita como não avaliada, com n avaliado=0; não se escolhem features pelo resultado, nem se imputa desempenho favorável |
| Gate estatístico | CAL-B é verificação operacional fora da amostra, não prova de FPR populacional ≤1% ou ≤2%. IC é publicado; seu limite superior não é um critério adicional implícito |
| Detecção | Janela com overlap positivo com evento real; decisão positiva disponível entre início e fim efetivos da emissão, inclusive prazo final. Fim da janela ≤ disponibilidade; disponibilidade simulada no fechamento é identificada como tal, sem alegação de latência computacional medida |
| Miss / indisponível | Sem decisão elegível: detecção operacional=0 e atraso observado=null, com suporte visível. Não excluir miss por ausência de degradação. Secundária sem calibração é não avaliada. Métrica restrita usa tempo até detecção ou fim da emissão, normalizado por duração; não é atraso observado imputado |

Z-score superior, CoV L6, EWMA λ=.2 e CUSUM congelado são os quatro avaliados. O CUSUM original serve somente à escala de calibração. As funções de fitting/calibração recebem observações e identidades, nunca ground truth. Labels/eventos entram somente na avaliação de TEST. C16/PRE de TEST não ajustam baseline ou h. Os loaders científicos são novos e validam membership da nova autoridade, sem recodificar TEST como DEVELOPMENT ou relaxar os locks antigos.

**Unidade e ICs fechados.** Avaliação TEST por execução, pareamento por bloco completo das quatro condições e métodos. Proporção de eventos por condição: Wilson bilateral 95%, exato binomial nos extremos. Diferença de detecção: discordâncias pareadas p10−p01, limites exatos bilaterais de 97,5% para cada probabilidade e combinação conservadora por Bonferroni, cobertura conjunta ≥95%. Médias e diferenças contínuas: BCa, 10.000 reamostragens, mesmos índices de blocos em ambos os lados; seed de análise fixa 2026102901, distinta do inventário de tráfego. Distribuição degenerada: Hoeffding com bounds declarados (taxas [0,1], diferenças [−1,1]), não IC [0,0]. Atraso condicional só recebe IC com ≥8 detecções; com zero detecções, média/mediana/IC=null. Disponibilidade, denominadores, reamostras indefinidas e n de pares são visíveis. Resultados são pontuais e condicionais ao treinamento congelado, sem testes de superioridade ou cobertura simultânea de todas as features. Não há bootstrap iid de janelas/requisições. A verificação CAL-B usa suas execuções benignas como unidades independentes.

**Substituições exclusivamente técnicas.** Máximo duas globalmente, uma por slot lógico, até 100 tentativas. Mesma configuração/seed/condição/partição, diretório e run ID novos; tentativa original permanece consumida e preservada. Motivos elegíveis: `CAPTURE_LOSS`, `IDENTITY_JOURNAL_MISMATCH`, `DATASET_INVALID`, `MISSING_REQUIRED_ARTIFACTS`, `MONITOR_SUPPORT`. Aprovação específica seleciona o hash do registro de falha. Reprovação em A/B, miss, FPR alto, baixa taxa realizada, degradação, recuperação ausente ou cleanup/execução indeterminados não autorizam substituição. Tentativa marcada antes da invocação impede nova execução automática; recuperação usa apenas evidências existentes. Se faltarem provas suficientes, o runner interrompe. Não classificar encerramento de serviço incompleto como mera perda técnica para obter outra observação.

**Ordem TEST pré-fixada.** Quatro ordens Williams:

| Ordem | 1º | 2º | 3º | 4º |
|---|---|---|---|---|
| A | C16 | M8 | E8 | E4 |
| B | M8 | E4 | C16 | E8 |
| C | E4 | E8 | M8 | C16 |
| D | E8 | C16 | E4 | M8 |

Blocos 1–16: **A,C,B,D, B,D,C,A, C,A,D,B, D,B,A,C**. Cada cenário ocupa cada posição quatro vezes; cada precedência ordenada entre cenários dentro do bloco ocorre quatro vezes. A ordem foi fixada antes dos dados TEST; não é sorteada novamente na retomada. Isso distribui efeitos de posição/precedência sem prometer eliminar deriva entre blocos. Seed de tráfego compartilhada apenas dentro do bloco; 50 seeds distintas no total das partições, auditadas contra históricos/reservas. Não há valores de seeds de campanha escolhidos nesta entrega.

A implementação está em [scientific](../analysis/detection/scientific/), no [runner](../experiments/scientific_campaign.py) e no [backend de coleta](../experiments/scientific_collection.py). Artefatos vinculam protocolo/plano/ambiente/código, fontes, parâmetros e fases. Cada candidato h conserva tabela completa de transições em CSV vinculada por hash. O loader pode refazer toda a calibração e conferir escolha e trajetórias. Artefatos existentes só são reutilizados se o corpo determinístico e os hashes coincidirem; nunca são sobrescritos. O grafo dos checkpoints verifica fontes e artefatos herdados.

O loader preserva a grade completa, inclusive cauda de drenagem até 421 janelas, mantendo a seleção primária [30,390); não recorta observações para fabricar um horizonte nominal. O runner usa lock exclusivo, journal encadeado e JSONs publicados exclusivamente com fsync. Um comando por partição autoriza somente aquela fase e para no checkpoint, sem autorização implícita da próxima. Dentro da fase, readiness e repouso ≥60 s são automáticos; imagens/código/ambiente/captura/porta são conferidos antes da tentativa. O claim é gravado antes de iniciar a execução. Falha interrompe imediatamente; repetir o comando recupera análises/coletas já concluídas e não volta a gerar carga para os slots aceitos. Falha científica sob autoridade fixa não é reaprovada por um novo comando. Per-entry: 390 s nominal, até 30 s drenagem, ≥60 s repouso, 600 s administrativos, envelope 1080 s; readiness repetida não reinicia a reserva de 600 s. Base de 98 runs: 10h37 nominal, 13h04 operacional incluindo nominal, 16h20 administrativos, total 29h24; teto com duas substituições: 30 h. Implementação, análise/escrita e diagnóstico excepcional permanecem fora desse envelope de coleta.

**O que ainda falta antes de qualquer coleta real:** materializar os 98 JSONs completos e o plano com a ordem fixada, 50 seeds auditadas e paths novos; registrar o lock real de Python/pacotes, kernel/daemon e IDs de três imagens; congelar os hashes do código; validar o plano offline; obter autorização específica da primeira partição. O backend real foi exercitado apenas na recuperação offline de um fixture no formato de exportação/validação/features; nenhuma prontidão real de Docker/imagens/captura foi testada nesta tarefa. O calendário até 15/11 permanece condicionado a essas etapas e à disponibilidade operacional já indicada na proposta. Não há nova exploração.

Formato do plano futuro: campos exatos `protocol` (path/sha256), `runtime_hashes`, `environment` (path/sha256), `seed_audit` (path/sha256), `entries` e `results_root`. Entradas: id, partition, block, scenario, ordinal, seed, config e config_sha256. O validador confere 6/12/16/64, ordem, template hash-bound, taxas/workers/tempos, independência e cobertura do inventário histórico. Paths de resultado devem ser novos sob `experiment_results/scientific-*`; raízes DEVELOPMENT/Stage14/15 são recusadas. Nenhum plano executável ou configuração é fornecido com placeholders nesta entrega.

Comandos abaixo são **instruções futuras**, com `PLANO` e hashes substituídos pelos caminhos/valores efetivamente materializados:

```bash
.venv/bin/python -B -m experiments.scientific_campaign --plan PLANO --plan-sha256 HASH_PLANO validate
.venv/bin/python -B -m experiments.scientific_campaign --plan PLANO --plan-sha256 HASH_PLANO run --partition BASELINE --authorize-partition BASELINE
.venv/bin/python -B -m experiments.scientific_campaign --plan PLANO --plan-sha256 HASH_PLANO run --partition CAL_A --authorize-partition CAL_A --checkpoint-sha256 HASH_CHECKPOINT_BASELINE
.venv/bin/python -B -m experiments.scientific_campaign --plan PLANO --plan-sha256 HASH_PLANO run --partition CAL_B --authorize-partition CAL_B --checkpoint-sha256 HASH_CHECKPOINT_CAL_A
.venv/bin/python -B -m experiments.scientific_campaign --plan PLANO --plan-sha256 HASH_PLANO run --partition TEST --authorize-partition TEST --checkpoint-sha256 HASH_CHECKPOINT_CAL_B
```

Cada comando imprime o checkpoint e seu hash. Para retomar, repetir exatamente o comando da partição interrompida, sob o mesmo plano/código; não apagar outputs ou claims. `status` é somente leitura. Para uma falha elegível, após diagnóstico:

```bash
.venv/bin/python -B -m experiments.scientific_campaign --plan PLANO --plan-sha256 HASH_PLANO approve-technical-replacement --failure-sha256 HASH_FALHA
```

Depois repetir o comando da mesma partição. Se houver tentativa indeterminada, checkpoint adulterado, mudança de código ou diretório parcial sem provas, o runner exige diagnóstico; não possui flag para forçar sobrescrita/repetição. Falha estatística em A/B exige nova autoridade e novos dados de calibração, não autorização de substituição.

Validação local, sem Docker/experimentos:

```bash
.venv/bin/python -B -m unittest tests.test_scientific_campaign -v
.venv/bin/python -B -m unittest tests.test_cusum_freeze tests.test_ewma_cusum tests.test_statistical_scores tests.test_empirical_policy -q
```

A [validação compacta](scientific_campaign_offline_validation_20261029.json) registra fluxo completo em diretórios temporários, rejeição de A/B, misses/prazo, ICs e degenerações, replay de h, corrupção, gates, substituição técnica, orçamento global, recuperação sem repetição e preservação dos históricos. Não foram executados Docker, prontidão real ou experimentos nem materializadas configurações/seeds da campanha.
