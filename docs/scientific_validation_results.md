# Resultados da validação científica — Etapa 9

Os 61 testes novos e a suíte completa (149 testes) passaram. Foram validados os 19 datasets reais da Etapa 8 e, adicionalmente, o run prospectivo com proveniência. Não houve alteração em produtores ou datasets, nem commit.

A comparação de hashes e mtimes de 1534 arquivos nos 20 datasets confirmou leitura sem modificações. Cada validação foi repetida para conferir igualdade integral dos relatórios. Saídas JSON: `experiment_results/stage9-final/summary.json` e um `validation_report.json` por run, fora dos datasets. CLI também exercitada: 0 para eligible e 1 para incomplete.

| Run | Status técnico | Dataset válido | Elegível | Errors | Warnings |
|---|---|---|---|---:|---:|
| stage7-regressions/stage3/A | completed | sim | sim | 0 | 1 |
| stage7-regressions/stage3/B | completed | sim | sim | 0 | 1 |
| stage7-regressions/stage3/C | completed | sim | sim | 0 | 1 |
| stage7-regressions/stage4/A | completed | sim | sim | 0 | 1 |
| stage7-regressions/stage4/B | completed | sim | sim | 0 | 1 |
| stage7-regressions/stage4/C | completed | sim | sim | 0 | 1 |
| stage7-regressions/stage4/failure | incomplete | sim | não | 0 | 2 |
| stage7-regressions/stage4/technical | completed | sim | sim | 0 | 1 |
| stage7-regressions/stage5/A | completed | sim | sim | 0 | 1 |
| stage7-regressions/stage5/B | completed | sim | sim | 0 | 1 |
| stage7-regressions/stage5/C | completed | sim | sim | 0 | 1 |
| stage7-regressions/stage5/failure | incomplete | sim | não | 0 | 5 |
| stage7-regressions/stage6/expensive | completed | sim | sim | 0 | 1 |
| stage7-regressions/stage6/light | completed | sim | sim | 0 | 1 |
| stage7-regressions/stage6/medium | completed | sim | sim | 0 | 1 |
| stage7-validation/capacity | completed | sim | sim | 0 | 1 |
| stage7-validation/continuous | completed | sim | sim | 0 | 1 |
| stage7-validation/multiple | completed | sim | sim | 0 | 1 |
| stage7-validation/periodic | completed | sim | sim | 0 | 1 |
| fresh-periodic | completed | sim | sim | 0 | 1 |

## Interpretação

Os 17 completed históricos passaram os critérios mínimos de elegibilidade, sem enfraquecer regras para obter PASS. Todos possuem um warning de proveniência de execução não registrada. Isso preserva a lacuna explicitamente documentada pela Etapa 8.

A falha do proxy da Etapa 4 permanece íntegra e inelegível: incomplete e erro operacional bloqueiam a campanha. Seus dois warnings são proveniência desconhecida e 31 requests com outcome diferente de response.

A falha da Etapa 5 também permanece íntegra e inelegível. Seus cinco warnings são proveniência desconhecida, 46 requests com falha e ausência de observações depois do fim planejado nas três modalidades (traffic/service/infrastructure), coerente com interrupção antecipada. O evento tem fim efetivo antecipado conhecido; isso não é confundido com a janela planejada.

O run prospectivo continua eligible, com warning de working tree dirty registrado antes de executar. Seu fingerprint e binding ao run passaram. Não se inventou SHA para os runs antigos.

PeriodicBurst, incluindo capacity e multiple, passou as verificações de janelas e correspondência de admissions/begins nos journals disponíveis. Conclusions no silêncio e drained_end anterior a actual_end são aceitos. ContinuousFlood conserva a regra da fila.

O dataset ContinuousFlood da Etapa 7 configura `/light`; esse valor canônico prevalece sobre descrições históricas que mencionaram `/expensive` para aquele cenário. Nenhuma configuração ou dado foi corrigido.

## Falsos positivos e limites

Nenhum check final ERROR reprovou os runs reais. Antes da implementação foram descartadas duas regras incompatíveis com o contrato: actual_end <= drained_end e rejeição de toda request contínua iniciada após fim planejado. A aprovação explícita preservou o baseline. Não se acrescentou tolerância para forçar aprovação.

Warn de ausência de fases num incomplete descreve evidência limitada; não implica corrupção. Startup com nomes de containers vazios é permitido. Ordem das linhas de requests não é usada como ordem dos inícios. Epoch retrógrado é warning e não altera duração monotônica.

Elegibilidade é mínima, não prova causalidade/degradação nem completude integral da captura. Falta de journals limita certificação de admissões/backlog; clock drift contínuo e ligação packet/request não são verificáveis diretamente. O PCAP principal e CSV são capturas distintas. Hashes não autenticam um pacote contra reescrita coordenada de manifest e dados.

Etapa 10: consumir somente analysis_eligible=true, verificar a identidade do manifest validado, manter limitações/warnings e separar resultados processados dos dados observados. Nenhuma feature, bin temporal ou detector foi implementado.

O catálogo completo, severidades e critérios estão em [dataset_scientific_validation.md](dataset_scientific_validation.md).
