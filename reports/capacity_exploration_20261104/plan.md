# Fase 2 — plano prévio de execução exploratória

HEAD `74d70b949896c413d6f5e184e7709ff0b1c18364`. Não criar commits nem autoridade científica. Preservar simulador, work_units, custos, detectores, schemas e datasets históricos.

## Configuração fixa

Direct; uma vítima; sem autoscaling/ataques; `/medium`; dois processos; 64 threads de envio agregadas (default suportado, constante); timeout Requests 2 s; diagnóstico ON com fila 4096 nas execuções principais. N=2 contêineres inicialmente; N2=4 na comparação de distribuição, mantendo o orçamento agregado de threads. Não adicionar limites Docker ou modificar políticas dos executores.

## Seleção incremental

Pilotos de 12 s: agregados nominais **8 → 32 → 64 → 96 → 128 RPS**, somente após revisão de cada resultado. Com duas fontes, taxas por fonte 4/16/32/48/64. O primeiro passo deriva do custo anterior ~0,012 CPU-s/operação: 8 RPS oferece ~0,096 CPU-s/s, pequeno perante dois workers. Os demais passos sondam frações progressivas desse orçamento; 128 é teto desta investigação, não alvo obrigatório. Não buscar máximo definitivo.

Após pilotos, selecionar baixa=8; intermediária inicialmente até 64; elevada = maior ponto seguro, íntegro e interpretável, até 128. Se um piloto impedir progressão, não executar o seguinte; selecionar níveis inferiores ou registrar limite/inconclusão. Um ponto com degradação limitada pode ser repetido como aproximação operacional, mas não com crescimento persistente/risco.

## Matriz reduzida proposta (valores finais dependem dos pilotos)

| Cenário | Fontes | Taxa agregada candidata | Finalidade |
|---|---:|---:|---|
| C1 | 2 | 8 | Baixa |
| C2 | 2 | Até 64 | Intermediária |
| C3 | 2 | Até 128 | Elevada segura |
| C4 | 4 | Igual C2 | Distribuição alternativa |
| C5 | 4 | Igual C3 | Distribuição alternativa |

Taxas por fonte = agregado/fontes, sem arredondamento nos candidatos. Duas repetições de **20 s** por configuração principal, seeds `44112101` e `44112102`. Pilotos usam `44112001` em diante e não são réplicas principais. Não adicionar terceira réplica salvo divergência decisiva, explicitamente justificada.

Overhead: C2/C3 OFF, duas repetições pareadas; alternar ON/OFF entre r1/r2. Somente métricas comuns serão comparadas. Distribuição usa mesmas seeds mestras, mas muda número de streams e primeiros despachos; isso não reproduz a mesma sequência agregada.

## Períodos e controle

Preparação: infraestrutura, readiness, auditoria de rede e relógios, antes da liberação das fontes; sondagens existentes `work=0`, sem criar warm-up artificial. Geração: `[0,T)` de origem experimental, reconhecendo o atraso original até release/primeiro despacho. Drenagem: tarefas admitidas seguem política existente (30 s; gerenciador até 35 s), sem fabricar conclusões. Captura/monitoramento finalizam depois; horizonte de features pode incluir cauda. Contagens/taxas do plano e totais com drenagem serão separadas.

Sem concorrência entre experimentos. Preflight exige testes aprovados, host disponível, redes vazias, nenhum contêiner experimental ativo, disco ≥4 GiB livre. Reutilizar imagens verificadas; não construir novas imagens sem necessidade. Intervalo mínimo entre execuções: 3 s e nova verificação de disponibilidade, não pretensão de equilíbrio térmico completo.

## Critérios objetivos prévios

Estes são **guardas operacionais exploratórios**, não critérios de detectores/campanha científica.

**Interrupção imediata cooperativa por SIGINT ao runner**, preservando seu finally/artefatos:

- RAM disponível do host <2 GiB; disco livre <4 GiB.
- CPU ocupada do host >85% por cinco observações consecutivas (~5 s): proteção do host, não diagnóstico de saturação.
- Memória da vítima >1 GiB ou de uma fonte >512 MiB; restart/OOM inesperado.
- Diferença observada submetidas−tarefas iniciadas−canceladas−rejeitadas >256 por fonte por três observações; não se chama profundidade exata de fila.
- Mais de 10% de falhas entre pelo menos 50 tentativas finalizadas observadas, ou erros/descartes explícitos de writer durante execução.
- Artefatos de uma execução >512 MiB, raiz total >1 GiB, ou duração externa >T+90 s.
- Perda de controle/erro persistente do vigia: interromper e impedir próxima execução.

Se a interrupção não concluir em 45 s, bloquear progressão, registrar estado e lidar somente com recursos cuja identidade pertença à execução; não fazer limpeza global.

**Impedir aumento de carga**, mesmo sem interromper a execução atual:

- Qualquer inconsistência de captura, dataset, relógio, writer, ID ou contador; coleta incompleta.
- Falhas >1%, HTTP p95 >500 ms, espera submit→worker p95 >100 ms, ou diferença pendente >64 em snapshots de três segundos finais sucessivamente crescentes.
- Conclusões dentro do plano muito abaixo dos inícios, combinadas com crescimento de pendências/atrasos; examinar cauda antes de atribuir perda.
- Reinicialização, drenagem não resolvida ou necessidade de interrupção de segurança.

Os limites de memória/log são margens muito superiores à validação prévia, porém pequenos perante recursos livres. Os limites temporais distinguem aproximação de degradação progressiva de espera sem controle. Diferenças estocásticas de taxa não acionam sozinhas reprovação.

## Tamanho e estimativa

Até cinco pilotos + dez ON + quatro OFF = **até 19 execuções**, cerca de 340 s de geração e aproximadamente 8–15 min com preparação, checagens e processamento; orçamento de trabalho com análise/documentação maior. Alocação esperada <500 MiB de artefatos; teto 1 GiB. Sem matriz de endpoints, sem ataques ou avaliação de detectores. Gráficos descritivos terão pontos por réplica, unidades e horizonte explícitos, sem IC inferencial.

## Auxiliares necessários

Wrapper externo para executar o entrypoint existente, observar host/contêineres/contadores, sinalizar parada e registrar decisões; análise offline complementar para tarefa→HTTP, fases de geração/drenagem, evolução em bins e concorrência computacional por sweep. Não modificar o gerador nem o servidor. Testar cálculo dos guardas, bins, fases e concorrência antes de executar.
