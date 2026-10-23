# Proposta de avaliação para discutir com o orientador

Proposta documental, sem execução. [Auditoria, fórmulas, populações e evidências](evaluation_metrics_plan.md).

**Quais métricas serão usadas? Como avaliá-las?**

Avaliaremos detecção, qualidade do serviço benigno e recursos separadamente.
Na detecção: recall, FPR, precisão/F1, proporção de eventos detectados e atraso,
com misses, disponibilidade e alarmes pós-evento explícitos. No serviço benigno:
vazão de sucessos, duração HTTP mediana/p95 e média, erros e tentativas incompletas.
Nos recursos: CPU/memória das vítimas e do proxy, CPU do host e conexões NGINX.
Os resultados serão resumidos por execução e fase e comparados entre seeds
pareadas, mostrando dispersão. Não usaremos janelas como repetições independentes.

| Dimensão | Mínimo por execução | Interpretação e situação |
|---|---|---|
| Detectores | Recall/FPR/precisão/F1; eventos detectados/total; delays dos detectados; alarmes POST; suporte | Já publicado na15B; distribuição/pareamento na15C. Não reavaliar TEST. POST não é tempo de recuperação |
| Serviço benigno | Starts/s, sucessos2xx/s, média/mediana/p95 de duration_ms2xx, n, HTTP erros, transporte/timeouts identificáveis e incompletas | Logs existem; resumo estratificado é análise futura. Declarar instrumentação incluída na duração; não usar avg_rtt_ms como latência benigna |
| Recursos | CPU/memória vítimas e proxy, CPU host; conexões NGINX e qualidade da coleta | CPU histórica pode estar stale; proxy novo não existe na campanha TEST. Consumo não prova saturação/overhead |
| Múltiplas vítimas | Individual, total, média por vítima e dispersão em intervalos comuns | Exige observações individuais com frescor/intervalos; sem denominador de capacidade não calcular utilização normalizada |

Para as análises futuras, PRE/ATIVO/POST usam marcos efetivos e o mesmo intervalo
no benigno pareado. Manter o startup e as fronteiras históricas separados:
a avaliação primária atual só usa [48,144), sem promover [0,48) à baseline.
Durações por coorte de início; conclusões/s por término; travessias registradas.
Fim nominal, emissão efetivamente encerrada e drenagem são marcos diferentes.
Não confundir emissão encerrada com serviço recuperado.

Mostrar pontos por seed, média/SD amostral, mediana/Q1/Q3 e n definido/total.
Comparar ataque−benigno por seed, sem tuning no TEST. Percentil de requisições
agrupadas não é média dos percentis das execuções. Eventos não detectados não
têm atraso zero; recuperação não observada permanece censurada/indeterminada.

Sequência proposta, em protocolo futuro separado:

1. Resolver frescor/suporte da CPU e declarar limites/população da duração HTTP;
   preservar as séries históricas. Implementar resumo mínimo offline e testar
   fronteiras, ausências, travessias e reconciliação das tentativas sintéticas.
2. Fixar warmup/PRE útil, acompanhamento POST e critério de recuperação se necessário;
   registrar versões, capacidade/limites, seeds, carga benigna e ordem das condições.
3. Variar RPS com endpoint/custo e N fixos; declarar qual classe/fonte varia.
4. Em bloco separado, variar custo do endpoint com RPS nominal e N fixos.
   Observar RPS efetivamente iniciado/concluído, que pode mudar sob carga.
5. Manter autoscaling desligado e upstreams estáticos; confrontar serviço benigno,
   vítimas, proxy e host. Comparações multivítima exigem coleta individual primeiro.

Não precisamos medir tudo já: p99 quando houver suporte; perdas de rede só com
hipótese e instrumentação específica; overhead causal só com comparação controlada.
HTTP erro/timeout não mede perda de pacote. Os resultados congelados e seus
thresholds continuam vinculados às definições originais; qualquer correção futura
exige versão própria e não é aplicada retroativamente.
