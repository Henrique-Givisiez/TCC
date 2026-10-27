# DEVELOPMENT D2 — comparação exploratória de endpoints

Estado: protocolo e configurações preparados offline; nenhum ensaio D2 executado.
Autoridade prospectiva: [manifesto D2 v3](../experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v3.json). As autoridades [v1](../experiments/protocols/development_d2_endpoint_comparison_20261027/manifest.json) e [v2](../experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v2.json) foram preservadas. V3 vincula os hashes aprovados ao anchor `d84a70d`: commits descendentes são aceitos apenas se o conjunto de fontes relevantes mantiver os mesmos hashes.

## Objetivo e evidência de D1

Comparar, sob oferta benigna comum, duração de sucesso 2xx, erros, starts,
recursos e qualidade de coleta em `/light`, `/medium` e `/expensive`. D2 é
exploratório: duas repetições por endpoint não estimam efeitos populacionais e
não permitem chamar diferenças de causais.

A síntese final de D1 mostra que 4 RPS agregados em `/medium` foram atingidos
com aderência de 96,5% e 102,1% nas réplicas L01; todas as 953 starts úteis
foram 2xx. Os p95 foram 56,79 e 55,96 ms. CPU média observada da vítima foi
5,73% e 6,52%, com os limites de cache/frescor documentados na [síntese D1](../experiment_results/development-d1-20261027/analysis/d1_final_synthesis_capturefix_v2.md).
No teto D1, 64 RPS em `/medium` foram atendidos, mas CPU média da vítima ficou
em 89,05% e 94,75%, com p95 de 61,71 e 65,36 ms. Isso fornece referência de
carga, não um SLO para os outros endpoints.

O servidor reserva 10.000 iterações para `/light`, 100.000 para `/medium` e
1.000.000 para `/expensive`; os caminhos reservados ignoram `work_units` e
`sleep_seconds` do JSON e executam o kernel CPU determinístico. Portanto,
4 RPS em `/expensive` representam nominalmente o trabalho de iterações de
40 RPS em `/medium`, entre os níveis D1 de 32 e 64 RPS. Essa equivalência é
apenas contagem de iterações, não duração ou custo medido. D1 não mediu
`/expensive`; 4 RPS não será presumido fora de saturação.

## Matriz e ordem

Todas as execuções usam uma vítima, proxy estático, quatro clientes em
contêineres, 1 RPS por cliente (4 RPS agregados), uma instância, pool de dois
processos, timeout de requisição de 2 s, concorrência máxima 64 e monitoramento
de 1 s. Ataque e autoscaling ficam desligados. Só mudam endpoint, ID e seed.
`normal_traffic.work_units=10` e `sleep_seconds=0` são mantidos como campos de
compatibilidade; o código do servidor ignora esses dois valores nos três
endpoints reservados.

| Ordem | Execução | Endpoint | Repetição/seed | Oferta agregada | Finalidade |
|---:|---|---|---|---:|---|
| 1 | `d2_probe_expensive_4rps` | `/expensive` | probe, seed próprio | 4 RPS | Verificar adequação antes da comparação |
| 2 | `d2_A_light` | `/light` | A, seed A | 4 RPS | Comparação, ordem A |
| 3 | `d2_A_medium` | `/medium` | A, seed A | 4 RPS | Comparação, ordem A |
| 4 | `d2_A_expensive` | `/expensive` | A, seed A | 4 RPS | Comparação, ordem A |
| 5 | `d2_B_expensive` | `/expensive` | B, seed B | 4 RPS | Comparação, ordem B |
| 6 | `d2_B_medium` | `/medium` | B, seed B | 4 RPS | Comparação, ordem B |
| 7 | `d2_B_light` | `/light` | B, seed B | 4 RPS | Comparação, ordem B |

Os ciclos A (`light, medium, expensive`) e B (`expensive, medium, light`)
invertem a precedência de cada par de endpoints. Isso muda a ordem comparativa,
mas não elimina deriva ambiental, efeitos de período ou carryover.
Dentro de cada repetição, o seed comum entre endpoints permite comparação
pareada de agenda; não torna os traços temporais idênticos. O probe tem seed
separado e não entra nas duas repetições finais.

## Duração, fases e drenagem

Cada configuração dura 150 s. O warmup é `[0,30)`; a observação útil é
`[30,150)`, quatro coortes de 30 s. No instante nominal 150 s, os produtores
encerram e drenam; a política do runner permite até 30 s para drenagem. O fim
observado deve vir dos quatro registros `source_closed`; o resumo usa o maior
elapsed efetivamente registrado, sem inventar timestamp. Fechamento ausente,
forçado ou logger incompleto reprova tecnicamente a execução. Só iniciar a
próxima após revisão, cleanup, prontidão e pelo menos 60 s sem execução.

Orçamento: sete tentativas máximas (um probe + seis comparativas), sem retry.
Por tentativa: 150 s nominais e até 30 s de drenagem. Há seis intervalos de
recuperação de pelo menos 60 s entre as sete tentativas. O teto de tempo da
sequência é 27 min, excluindo inicialização, preflight e tempo adicional de
interpretação.

## Critérios fixados antes da coleta

- Integridade técnica: dataset válido; execução concluída; reconciliação de
  journal/CSV; quatro fontes fechadas e drenadas; cleanup sem processo ou
  contêiner residual; suporte da vítima e proxy conforme os limites abaixo.
- Integridade de captura: CSV e PCAP devem ter seus próprios stderr e relatório
  de ciclo de vida, estatísticas finais completas, código de saída aceito e
  exatamente zero drops do kernel. Ausência de estatística reprova; não há
  tolerância a drops. Todas as tentativas usam capturefix, incluindo o pedido
  CSV `-B 4096`; o valor solicitado não prova aplicação integral do buffer.
- Aderência da oferta: starts agregados/oferta entre 0,80 e 1,20; cada origem
  entre 0,65 e 1,35; starts tardios até `max(4, 1% dos starts)`. Abaixo disso,
  distinguir insuficiência do gerador de baixa demanda do serviço antes de
  interpretar uma latência aparentemente favorável.
- Serviço: sucesso HTTP 2xx por starts ≥99%; falhas HTTP/transporte/cliente no
  máximo 1%; incompletas e outras respostas iguais a zero; vazão de términos
  2xx úteis ≥80% da oferta. Duração é sempre agrupada pela coorte de início;
  términos pela fase/instante final.
- Suporte: ao menos 200 durações 2xx conhecidas; vítima com pelo menos 108/120
  ticks úteis e gap máximo 5 s; status e Docker do proxy com pelo menos 90% dos
  120 slots esperados e gap máximo 5 s. Dados sem suporte são `null`, não zero.
- Tendência de acúmulo: revisar as quatro coortes úteis. Sinal de parada quando
  há pelo menos 50 sucessos em primeira e última coorte, vazão terminal 2xx
  cai pelo menos 20% e p95 dobra. Para o probe, adicionalmente comparar a média
  de requisições cliente em voo por coorte; crescimento final de pelo menos
  0,5 requisição e pelo menos 2× o primeiro bin é sinal de acúmulo. Essa medida
  é concorrência de requests observada, não comprimento direto da fila interna.
- O p95 é obrigatório como métrica com suporte e apresentado por execução,
  mas **não tem limite absoluto de aprovação em D2**. Não reaplicar o limite
  de `/medium` de D1: duração maior pode ser o efeito de custo investigado.
  CPU alta sozinha também não reprova; deve ser lida junto com throughput,
  tendência de duração/concorrência, falhas e incompletas.

### Gate do probe `/expensive` a 4 RPS

Reter 4 RPS como oferta comum somente se a tentativa for tecnicamente íntegra,
aderente e passar os critérios de serviço, suporte e ausência de acúmulo. O p95
fica descritivo. Falha de coleta invalida tecnicamente e encerra a sequência;
não é motivo para mudar taxa nem repetir. Se a execução for tecnicamente íntegra
e o gerador aderente, mas falhar critério de serviço ou indicar acúmulo,
encerrar esta versão e preparar nova autoridade a 2 RPS agregados (0,5 por
cliente), com novas configurações completas e seeds reservadas. Insuficiência
do gerador, falha técnica ou sinais discordantes exigem diagnóstico e parada;
não reduza a oferta para mascarar a limitação. Não iniciar D2 a 4 RPS, não
reduzir automaticamente no meio do bloco e não reutilizar esta configuração
como se a taxa tivesse sido aprovada.

## Comparações e interpretação

Para cada execução, registrar starts/RPS e aderência, sucessos, falhas,
outras respostas, incompletas, média/p50/p95 2xx, recursos médios da vítima e
proxy, suporte e contadores separados de captura. O relatório final apresenta
os seis runs, as diferenças A−B por endpoint e limitações da coleta.

O aumento observado de duração ou CPU em `/expensive` com estabilidade de
oferta e sem falhas pode ser compatível com maior custo esperado. Degradação é
avaliada por falhas, incompletas, queda de vazão e tendências sustentadas; falha
técnica inclui drops, estatísticas ausentes, inconsistência de journal/CSV ou
coleta insuficiente. Não atribuir diferença automaticamente ao endpoint quando
ordem, ambiente, generator ou suporte diferirem. O número de iterações da rota
nunca será apresentado como proporção medida de custo.

## Arquivos e comandos

As sete configurações completas estão em
`experiments/configs/development_d2_endpoint_comparison_20261027/`.
Validação offline (não acessa Docker):

```bash
.venv/bin/python -B -m experiments.development_d2 validate-plan \
  --manifest experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v3.json
```

Após autorização separada e decisão do probe, iniciar somente a entrada
individual. Exemplo para a primeira tentativa, sem batch:

```bash
.venv/bin/python -B -m experiments.development_d1_ops \
  --manifest experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v3.json \
  preflight --entry d2_probe_expensive_4rps
.venv/bin/python -B -m experiments.development_d1_ops \
  --manifest experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v3.json \
  run --entry d2_probe_expensive_4rps --preflight-id pf-0002
.venv/bin/python -B -m experiments.development_d1_ops \
  --manifest experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v3.json \
  postprocess --entry d2_probe_expensive_4rps
.venv/bin/python -B -m experiments.development_d1_ops \
  --manifest experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v3.json \
  review --entry d2_probe_expensive_4rps
```

Só depois de revisar o probe e confirmar todos os gates, seguir individualmente
na ordem do manifesto. Após as seis revisões, gerar comparações com:

```bash
.venv/bin/python -B -m experiments.development_d2_compare \
  --manifest experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v3.json
```

O preflight anterior foi preservado em `operations/d2_probe_expensive_4rps/preflight.json` como `pf-0001`; ele falhou com `PermissionError` no socket Docker, sem iniciar o probe. O utilitário aceita novos preflights versionados em subdiretórios e o comando `run` exige `--preflight-id`; repetição de prontidão não repete a tentativa científica. A síntese da parada está em `analysis/d2_stop_synthesis.md`. Docker CLI e SDK Python apontam para `/var/run/docker.sock`; o ambiente do Codex impede conexão. No terminal de usuário, executar primeiro o preflight acima; usar no `run` exatamente o ID retornado, que será `pf-0002` se não houver outra checagem. D2 não inclui ataques,
autoscaling, host adicional, RTT específico ou UDP; não usa detectores,
calibração nem TEST.
