# Proposta mínima de CPU para múltiplas vítimas

Para discussão; nenhuma mudança ou execução autorizada por este documento.
[Auditoria completa e fontes](cpu_accounting_audit.md).

Hoje a medida principal é uma média de **amostras** de CPU Docker das vítimas,
com fallback para cache. 100% equivale aproximadamente a um núcleo lógico, não à
capacidade inteira do container. O código não define quota/cpuset nem capacidade
garantida por vítima. A campanha congelada tem uma vítima; não valida agregação
experimental com várias.

Manter a série histórica. Para uma versão futura, registrar observações individuais
com ID/época de execução, contadores, intervalos Docker e de coleta, suporte/erros,
idade e conjunto de vítimas. Sem isso, médias antigas não permitem reconstruir
uma integração temporal exata. Dado ausente não deve virar leitura nova ou zero.

| Painel futuro | Medida e finalidade |
|---|---|
| Cada vítima | CPU-s/s ou núcleos equivalentes: onde se concentra consumo. |
| Todas as vítimas | Soma do consumo alinhado e CPU-s total: demanda total. |
| Réplica típica | Média igual por vítima com suporte comum: consumo por réplica. |
| Distribuição | Mínimo/máximo/dispersão: desequilíbrio de carga. |
| Capacidade | Utilização somente com orçamento declarado/verificado; quota é teto, não reserva. |
| Proxy | Série própria de CPU/status/erros: possível gargalo intermediário. |
| Host/fontes | CPU global e evidência de pressão/geração: contenção externa às vítimas. |

Exemplo: uma vítima em 200% consome 2 núcleos equivalentes. Duas em 100% cada têm o
mesmo total, mas a média cai para 100%. A queda não prova redução da demanda ou
adição de capacidade física, sobretudo no mesmo host.

Propor inicialmente **N fixo, autoscaling desligado e upstream estático** em cada
bloco. Declarar se N maior distribui o mesmo orçamento total ou recebe capacidade
adicional realmente disponível; registrar limites efetivos e ancestrais, sem usar
pool 2 ou CPUs visíveis como reserva. Nenhuma alteração dinâmica de upstream agora.

Depois, em experimento separado e aprovado: variar RPS mantendo endpoint/N fixos;
em outro bloco variar custo do endpoint mantendo RPS/N fixos. Usar consumo total,
por vítima e desequilíbrio junto com proxy, host e qualidade do serviço benigno.
Taxas e critérios devem vir de caracterização independente, sem tuning no TEST.

Qualquer mudança de suporte, cache, ponderação ou unidade exige contrato/versão
novos e avaliação própria antes de alimentar detectores/autoscaler. Os thresholds
e os resultados existentes permanecem vinculados à definição histórica.
