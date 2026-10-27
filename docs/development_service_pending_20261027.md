# DEVELOPMENT — decisões antes da geração de configurações

Estado: proposta de 27/10/2026, sem autorização de execução. Complementa o
[plano documental](../experiments/protocols/development_service_plan_20261027.json)
e a [proposta da campanha](new_campaign_protocol_proposal_20261027.md).
O plano é um documento de desenho, **não** um `ExperimentConfig` parcial
executável. Não há configurações com placeholders, taxas ou seeds inventadas.

A [preparação operacional de D1](development_d1_20261027.md) propõe valores
concretos e configurações completas para esse bloco, com execução condicionada
a revisão por patamar. As demais decisões deste documento continuam aplicáveis
a D2/D3 e à futura campanha científica.

## Decisões necessárias

| Decisão | Recomendação/critério | Campos reais afetados |
|---|---|---|
| Objetivo de serviço | Definir teto aceitável para p95 de duração2xx, erros, incompletas, aderência starts/oferta e estabilidade; CPU não é critério único de capacidade | Critérios externos ao JSON do simulador |
| Varredura D1 | Definir taxa inicial, passos, teto, parada e condição de resfriamento; selecionar baixo/nominal/alto por serviço, sem usar recall/F1 | `normal_traffic.rate` (por cliente) |
| D2 | Fixar taxa suficientemente baixa comum às três operações; custos são iterações, não milissegundos garantidos | `normal_traffic.rate`, `normal_traffic.endpoint` |
| D3 | Fixar faixa e teto ofensivos; verificar oferta→starts→términos e geradores, mantendo sub-blocos taxa/custo separados | `attack.rate`, `attack.endpoint` |
| Tempos | Definir warmup, PRE útil, atividade, POST, acompanhamento de drenagem e orçamento máximo por run. Encerramento do cliente não prova recuperação da vítima | `duration_seconds`, `attack.start_seconds`, `attack.duration_seconds`; fases são metadados externos |
| Repetições, seeds e ordem | Fixar número e lista DEVELOPMENT independentes de BASELINE/CALIBRATION/TEST históricos e futuros; ordem balanceada registrada. Mesma seed para comparações planejadas, sem garantia de tempos iguais | `seed`, `id`; ordem e partição em manifesto externo |
| Recursos | Confirmar pool2, timeout2s, orçamento64 por classe e monitoramento1s propostos; declarar ambiente/limites efetivos. Não tratar pool como quota de CPU | Campos fixos listados no plano; limites Docker não possuem campos CPU em `ExperimentConfig` |
| Fases e observação | Para ataques, declarar PRE/ACTIVE/POST por marcos efetivos auditados; controle benigno usa os mesmos limites do par. DRAIN começa no fim do horizonte nominal; escolher limite observado até onde o log é completo | Plano de fases separado, com `run_id` e limites concretos |
| Falhas e repetição operacional | Definir invalidação técnica, preservação da tentativa, retomada e eventual substituição antes da coleta; não excluir runs por degradação real do serviço | Manifesto operacional externo |

Não usar defaults omitidos para disfarçar decisões: antes da geração, preencher
explicitamente as taxas/tempos/seeds resolvidos e validar cada configuração via
`ExperimentConfig.from_dict(...).validate()`, sem inicializar Docker. Campos
`work_units/sleep_seconds` são inertes nos três endpoints reservados; não são
fatores de custo. Configurações efetivas devem registrar também defaults técnicos
e imagens/código para reprodução. Nenhuma taxa final da campanha é escolhida aqui.

## Sequência proposta

1. Fechar critérios, limites e orçamento de DEVELOPMENT; confirmar campos fixos.
2. Gerar em diretório novo somente JSONs completos e válidos, com plano de ordem,
   seeds, saídas e autoridade próprios; não reaproveitar release Stage14.
3. Validar offline configurações e fases. Revisar evidências de qualidade/frescor
   de CPU das vítimas, sem exigir CPU por núcleo como pré-condição.
4. Após autorização de execução, coletar D1; escolher carga baixa de D2 e regime
   nominal/faixa de D3 por critérios pré-definidos. Documentar adaptações sem tocar
   TEST. Este trabalho **não** executa essa sequência de coleta.

O resumo de serviço entregue usa logs de cliente e não acrescenta monitoramento
do host, RTT específico proxy→vítima, UDP ou autoscaling. CUSUM e calibração
científica são tarefas posteriores, fora desta implementação.
