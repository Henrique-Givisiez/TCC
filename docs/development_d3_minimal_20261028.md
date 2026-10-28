# D3 — continuação mínima E4-R2

Estado: **preparado offline; nenhum Docker, preflight real ou experimento executado nesta tarefa**. Nova [autoridade](../experiments/protocols/development_d3_minimal_20261028/manifest.json), sem substituir C/E4, suas revisões ou a autoridade original. Uma entrada: `d3_minimal_E4_R2`. E8 não integra esta autoridade e permanece bloqueado na anterior. Nenhum detector, calibração ou código de geração de tráfego foi alterado.

## Entrada única, referências e orçamento

[Configuração completa](../experiments/configs/development_d3_minimal_20261028/d3_minimal_E4_R2.json): cópia exata da configuração de E4, alterando **somente ID e seed**. Quatro clientes `/medium`, 4 RPS por cliente (16 agregados); um atacante contínuo `/expensive`, 4 RPS; uma vítima, proxy estático, autoscaling off, pool=2, timeout HTTP=2 s, orçamento64 por classe. Warmup 0–30 s, PRE 30–150, ACTIVE 150–270, POST 270–390. Sources/monitoramento mantidos.

Seed exclusiva: **339969143534335847**, derivada de SHA256 `development-d3-minimal-20261028-v1:d3_minimal_E4_R2:0`, primeiros oito bytes big endian, auditada contra metadados históricos, pilotos anteriores e reservas MATRIX_A/B. Inventário/hash em [seed_audit.json](../experiments/protocols/development_d3_minimal_20261028/seed_audit.json). Não foram geradas configurações adicionais nem novas reservas da matriz.

Referência principal: **PRE da nova execução**, [30,150). Referência secundária: C histórico aceito pela regra original, agrupando os 360 s úteis fixos [30,390), sem procurar o bin mais favorável. Revisão de C: `experiment_results/development-d3-pilots-20261028/analysis/d3_pilot_C-review.json`, SHA256 **`13ad60f49f2ef91ccb548e0768241a731a69e1d4f6cfe327b3fc2af60c100140`**. A autoridade vincula essa revisão, os arquivos raw da referência e as fontes relevantes por hash. Extrair estatísticas de referência não reclassifica C.

Compatibilidade: mesmos campos legítimos, servidor, infraestrutura, proxy, monitoramento, timeout, execução e duração; fontes runtime preservadas e imagens conferidas no futuro preflight. Ambas as referências precisam de ≥200 starts e durações 2xx conhecidas, ≥99% de sucesso e ≤1% de falhas/ausência de sucesso no prazo. Exigir razão p95 PRE novo/C em [0,8;1,25] antes de confirmar compatibilidade conjunta. Incompatibilidade não apaga o serviço observado; limita a conclusão comparativa. C é histórico, não contemporâneo nem pareado pela seed nova; não identifica causalmente o efeito ofensivo ou garante estabilidade do ambiente. O PRE novo é o controle interno da tentativa.

**Uma tentativa, zero retries/substituições:** 390 s nominais +até30 s de drenagem +60 s de repouso =480 s (8 min), mais600 s administrativos: **1.080 s =18 min**. A tentativa é consumida pelo registro exclusivo `attempt.json`, mesmo se falhar. A reserva administrativa conta desde o primeiro preflight registrado, sem reiniciar com outra prontidão; o comando de execução recusa começar se faltar a reserva de480 s. Estouro/imprevisto exige diagnóstico, sem autorizar extensão/repetição ou destruir evidência para cumprir relógio. A autoridade termina após esta E4; nenhum relatório autoriza outro experimento.

## Critérios finais do serviço observado

Grade nominal POST: [270,300), [300,330), [330,360), [360,390). Cada janela é intersectada com [max(270,fim **certificado** da emissão),390). Recalcular starts, términos, coortes, exposição e taxas na interseção. Exigir≥95% da exposição nominal (28,5 s), observação completa dessa janela e suporte. Sem fusão, deslocamento, arredondamento de fronteira ou extensão do POST. Intervalos anteriores à certificação são transição, não recuperação. A drenagem fornece desfechos; não cria novas janelas.

Para cada janela efetiva [a,b):

| Requisito | Critério congelado |
|---|---|
| Suporte | ≥200 starts legítimas; ≥200 durações2xx para confirmar latência; p95 conhecido. Falhas numerosas continuam evidência de degradação mesmo sem200 sucessos. |
| Sucesso/conclusões no prazo | Horizonte H=b+3 s; 2xx da coorte conhecidos até H /starts ≥99%; queda≤1 ponto percentual versus cada referência; falhas, respostas outras e ausência de sucesso até H somam≤1%. Não transformar uma resposta posterior a H em sucesso no prazo. |
| Duração | p95 dos sucessos até H ≤1,25×p95 PRE e ≤1,25×p95 C, se referências adequadas/compatíveis; média/p50/n permanecem no JSON. |
| Pendências legítimas | P(b−)≤max(4,ceil(1,25×max(p95 P_PRE,p95 P_C))), idade de pendências≤3 s; crescimento≤2 por janela e≤2 nas duas janelas de confirmação. P95 das referências calculado em grade fixa de1 s. |
| Pendências ofensivas | Zero tentativas ofensivas de cliente pendentes nas fronteiras das duas janelas de confirmação. Não é prova de cancelamento/drenagem interna do servidor após timeout. |
| Contabilidade | P(t−): start<t, término≥t ou desconhecido. Exigir P(b−)−P(a−)=starts−términos em [a,b). Conclusões de coortes anteriores não são starts novas nem falhas. |
| Vazão | Starts/s, términos/s e2xx/s por classe/fase/janela ficam como resultados. Nenhum mínimo baseado na vazão de um bin de C é requisito direto de atendimento. |

PRE é a referência principal para identificar degradação em ACTIVE. Divergência exclusivamente do teto de duração secundário de C recebe motivo próprio (`primary_compatible_secondary_disagreement`), sem inventar degradação perante o PRE. Confirmação conjunta permanece não satisfeita até cumprir os requisitos congelados. A instabilidade/comparabilidade da referência é separada da validade da observação.

Medir ACTIVE em quatro janelas nominais de30 s com os mesmos critérios legítimos, sem exigir que a origem ofensiva tenha drenado enquanto o ataque está ativo. Se houver degradação legítima demonstrada com suporte, duas janelas POST consecutivas qualificadas geram evento de recuperação. Se ACTIVE estiver adequadamente observado e não mostrar degradação, usar **`post_compatible_no_prior_impairment`**, com `recovery_event=null`. Se ACTIVE não puder ser avaliado, não afirmar ausência de degradação: usar estado anterior desconhecido. Registrar separadamente primeira confirmação, qualificação das duas janelas finais e motivos de perdas posteriores.

As margens acima são exploratórias; não são limiares de detector calibrados nem SLO comprovado. Preservam o desenho prospectivo: 30 s,95%,n200,99%,1pp,1,25,piso4,crescimento2 e prazo/idade3 s. Nenhum resultado futuro ajusta esses valores nesta autoridade.

## Tempo da evidência versus publicação

O timeout escalar de2 s é passado a `requests.get`; não é teto garantido de duração total. Conexão/leitura e custos locais podem excedê-lo. **3 s é margem exploratória de acompanhamento após b**, não garantia do runtime nem prazo por requisição contado da agenda de envio. A idade de pendências é uma medida distinta, contada de seu início observado.

No fim do bin b, registrar somente términos já conhecidos e pendências existentes naquele instante. O JSON conserva `snapshot_at_bin_end`, `bin_end_seconds` e **`evidence_horizon_seconds=b+3`**. Se o horizonte não foi observado e ainda faltam términos da coorte, o desfecho permanece desconhecido: `cohort_mature=false`, frações finais=null, sem qualificação presumida. Se todos os términos já forem conhecidos antes de H, a finalização pode ser certificada antecipadamente **após reconciliação completa**, indicando `cohort_finalized_early=true` e o horizonte efetivamente usado. Não fabricar observação até393 s se todos os clientes fecharam íntegros em390,03 s.

Os journals atuais só certificam completude pelo fechamento da origem. Esta revisão é batch/offline: `decision_not_before_seconds` não precede o cutoff certificado dos journals. A primeira confirmação pode ter `window_end_seconds=360`, `required_evidence_horizon_seconds=363` e depender de coleta/reconciliação posterior. A publicação tem carimbo UTC/epoch próprio no JSON, criado após validação do conteúdo e antes da gravação exclusiva dos relatórios. **360 s não será apresentado como instante de publicação ou decisão disponível em tempo real.**

Sem confirmação, censurar no fim nominal POST ou no cutoff efetivamente observado, o menor, com razões de serviço/suporte/referência. Ausência de término persistida não é perda de registro. Falha técnica torna a inferência `unassessable_collection`, sem alegar censura de observação íntegra ou recuperação confirmada.

## Três eixos independentes e fluxo operacional

1. **Validade técnica:** reutilizar reconciliação estrita de inventário, begins/finishes, CSVs locais/agregado, origem/IDs, ground truth local/global, fechamentos e captura/monitoramento. Dataset deve corresponder byte a byte ao raw. Vítima/proxy:≥108 slots/120 por fase e gaps≤5 s; captura final CSV/PCAP única, saída aceita e zero drops. Operação precisa de vínculo explícito attempt→preflight, hashes, configuração efetiva e cleanup. Dados não são sobrescritos.
2. **Serviço observado:** avaliar as requisições iniciadas com a regra acima. Sucesso baixo, duração alta, pendências e recuperação não observada são resultados, não corrupção automática dos dados. Fechamento não controlado permanece registrado independentemente da existência de registros completos.
3. **Gerador:** publicar starts/expectativa nominal por classe/fase/origem e contagens de admissão do ataque. Quando o journal permitir pareamento inequívoco, medir admissão→begin. Os legítimos não têm agenda/submissão registrada; **`full_scheduled_load_verified=false`**. Isso limita afirmações sobre oferta/carga programada, sem bloquear por si só a validade ou a compatibilidade do serviço recebido. Nenhuma instrumentação adicional foi implementada.

[Revisão](../experiments/development_d3_minimal.py) e [operações](../experiments/development_d3_minimal_ops.py) são módulos novos; as fontes anteriores não foram editadas. O novo preflight não exige transformar a revisão de E4 antiga em aprovação: é entrada própria, sem E8. A execução, futuramente, exige comando separado, preflight selecionado e autorização que nomeie exatamente o novo ID; sem batch ou retry. A CLI da revisão retorna resumo curto e caminho do JSON; os diagnósticos, requisitos, medidas, limites e tempos ficam no JSON.

Comando **somente de preflight**, preparado e não executado nesta tarefa, a partir da raiz:

```bash
.venv/bin/python -B -m experiments.development_d3_minimal_ops preflight --entry d3_minimal_E4_R2
```

Esse comando futuro consulta Docker/imagens/porta e prontidão da captura, sem gerar carga HTTP. Processamento futuro dos outputs da única tentativa:

```bash
.venv/bin/python -B -m experiments.development_d3_minimal review
```

A [validação offline](../experiments/protocols/development_d3_minimal_20261028/offline_validation.json) registra testes com fixtures, exportação/validação/revisão completas, causalidade temporal, desconhecimento de oferta, compatibilidade sem degradação anterior, recuperação, censura, falha de coleta, abertas versus perda, autoridade/seed/config, recusa de E8/segunda tentativa/sobrescrita e CLI curta. Os fixtures usam diretórios temporários, sem ocupar outputs reservados nem reclassificar C/E4 reais.
