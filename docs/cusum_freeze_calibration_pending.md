# CUSUM com congelamento — calibração e integração pendentes

Estado: **NÃO CALIBRADO CIENTIFICAMENTE**. A
[implementação v1](cusum_freeze.md) foi validada com h explícitos exclusivamente
sintéticos. Não há autorização/execução de CALIBRATION ou TEST nesta entrega.

## Dependência em h

Na V1 antiga o score é calculado sem h e recebe threshold depois. Na nova variante,
h decide qual candidato será incorporado; logo modifica estados e scores futuros.
Não se pode trocar h apenas na política de decisão de uma trajetória pronta.
Cada h avaliado requer reprocessamento causal desde a origem com os mesmos
momentos benignos. Comparações entre versões devem registrar essa diferença.

O quantil empírico antigo `ceil((N−1)(1−alpha))` de scores CUSUM sem congelamento
não certifica o FPR da trajetória nova. Não há transferência automática dos
thresholds congelados, nem justificativa para chamar h=1/2 dos testes de
calibração. O sistema não produz artifact de calibração para mascarar essa ausência.

## Estratégia ainda a decidir

A proposta de27/10 recomenda discutir uma separação benigna A/B:

1. Usar referência benigna de ajuste independente para mu/sigma e definir regime,
   feature, janela, k, horizonte e política missing antes da calibração.
2. Em CALIBRATION-A benigna, estimar h de referência por procedimento declarado
   (por exemplo, CUSUM V1 sem congelamento), ou definir uma busca própria da
   variante que **reprocesse** cada h. São alternativas a escolher previamente;
   nenhuma foi implementada ou executada nesta tarefa.
3. Congelar h e verificar a política integrada em CALIBRATION-B benigna
   independente, por execução/exposição e com indisponibilidade explícita.
   Se o critério não for atendido, aplicar regra prévia de insucesso/revisão;
   não ajustar repetidamente usando B até obter FPR desejado.
4. Congelar código/ambiente/modelo/h e avaliar apenas em novo TEST independente.
   Sem usar resultados dos ataques avaliados para escolher h, k, feature ou versão.

Precisam de decisão: alvo de falso alarme (janela/tempo/execução), critérios e
incerteza da verificação, ponderação entre runs/regimes, tamanho A/B e regra de
insucesso. Dependência temporal impede tratar janelas como réplicas iid.
Se uma busca exigir escolhas de desenvolvimento, fazê-las em DEVELOPMENT
independente e registrar multiplicidade/seleção antes da fase científica.

## Integração necessária para a nova campanha

- Aprovar a estratégia acima e a comparabilidade dos regimes benignos, sem
  recalibrar ao variar o ataque dentro do mesmo regime legítimo.
- Definir no manifesto novo a identidade `cusum-freeze:1`, baseline e h, com
  proveniência/autoridade próprios, sem editar os manifests Stage14/15.
- Implementar o binding de calibração científica e publicação/recarga de avaliação
  para o artefato acoplado. Reutilizar os contratos de dados e métricas revisados,
  mantendo a decisão do candidato e recusando h alternativo na avaliação.
- Adaptar o runner/release da nova campanha somente após revisão; o adaptador
  entregue aceita apenas DEVELOPMENT sem campanha. A API em memória e o adapter
  de avaliação fornecidos são para validação sintética, não uma liberação científica.
- Congelar matriz, seeds/pareamento, horizontes, suporte, regras de evento e
  estatísticas antes de novo TEST. Preservar V1 como comparador identificável.

Não executar o TEST antigo para medir um suposto ganho retrospectivo. Mudanças
após nova avaliação final exigem outra versão e novo conjunto independente.
Não há nesta etapa Docker, autoscaling, host adicional, RTT específico ou UDP.
