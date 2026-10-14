# Validação da Etapa 8

Executada em 14/10/2026. Os produtores existentes permanecem sem alterações.
Os 23 testes novos passaram; a suíte completa passou com 88 testes, incluindo os
65 testes do baseline. Nenhum commit foi criado.

## Exportação dos runs reais arquivados

`experiment_results/stage8-final/export_validation.json` registra 19 exportações
dos runs já validados das Etapas 3–7: 17 completed e 2 incomplete, 1.377 arquivos
originais verificados por SHA256. Todos os originais continuam no lugar e todas
as cópias preservam bytes. Inclui A/B/C da Etapa 3 (aliases antigos), A/B/C,
technical e falha do proxy da Etapa 4, A/B/C e falha da Etapa 5, as três operações
da Etapa 6 e continuous/periodic/multiple/capacity da Etapa 7. Esta regressão é da
camada de exportação sobre ensaios reais arquivados; não é reexecução física dos
19 cenários. A suíte completa exercita novamente as regressões dos produtores.

Os exemplos solicitados estão em:

* `experiment_results/stage8-final/stage7-validation/continuous/dataset_manifest.json`
* `experiment_results/stage8-final/stage7-validation/periodic/dataset_manifest.json`

| Propriedade | ContinuousFlood | PeriodicBurst |
|---|---|---|
| Run ID | aac4906df9ae494ab1d87ca99adcc8b6 | 99619e207ea2462b9b2eea7cba67940a |
| Seed / benignos / atacantes | 42 / 4 / 1 | 42 / 4 / 1 |
| Operação / taxa por atacante | /expensive / 10 RPS | /expensive / 10 RPS durante burst |
| Perfil | continuous | periodic_burst |
| Burst / período | não aplicável | 1 s / 3 s |
| Janela planejada | [2,13.5) s | [2,13.5) s |
| actual_start | 2.006147884 s | 2.091675663 s |
| actual_end | 13.507326259 s | 13.507451791 s |
| drained_end | 13.335780747 s | 12.016331814 s |
| Status | completed | completed |
| SHA/dirty da execução | não registrado | não registrado |

Nos dois inventários: normal_1…normal_4 → 172.20.0.3…172.20.0.6; attack_1 →
172.20.0.7. Os nomes/IDs efêmeros de containers estão preservados nos respectivos
inventários. Configuração/seed estão em metadata/effective_config.json; tempos em
raw/attacks/attack_events.csv; packets em raw/traffic (CSV e PCAP), requests em
raw/service, métricas em raw/infrastructure. Metadata/run_status.json preserva
motivos/status, identidade do proxy e âncoras. Os manifests resolvem todos os paths.

Não é possível recuperar com confiança o commit de execução desses runs antigos:
nenhum registro anterior à execução existia. export_provenance não é usado para
preencher essa lacuna. Versões/digests já registrados permanecem na topologia.

## Novo ensaio real com proveniência prospectiva

Executado pelo novo `experiments.dataset_run`, usando a configuração existente
`experiments/configs/periodic_burst.json`, sem alterar tráfego ou parâmetros.

* Run `927e03c2d49843c8b74427070067527e`, completed.
* Dataset: `experiment_results/stage8-validation/fresh-periodic-dataset`.
* Auditoria: `experiment_results/stage8-validation/fresh-audit.json`.
* Commit capturado antes da invocação: `106181886683bc36dc86da1914ea4a2b96636b45`.
* Dirty: true; caminhos/status e hashes do código observados naquele instante.
* Docker servidor 28.0.4; versões de cliente/servidor e ambiente registrados.
* Seed 42; 4 fontes benignas, 1 atacante; mesmas associações source/IP acima.
* /light benigno e /expensive atacante; 10 RPS por atacante; burst 1 s/período 3 s.
* actual_start 2.091430033; actual_end 13.507819348; drained_end 12.053012158 s.

134 requests iniciadas/concluídas, todas com routing evidence via proxy. Foram 25
ataques nos quatro bursts, distribuídos 9/5/3/8, mantendo o resultado do baseline
estocástico. 80 requests benignas têm attack_active=1 e continuam traffic_class=benign.
O aggregation audit original registra 25 admissões, nenhum abandono, 25 inícios
e 25 conclusões do atacante. Duas requests terminam no silêncio (começo→fim):
5.907428116→6.024365399 e 11.860125121→12.053012158 s. Clock audit e probes de isolamento
originais são preservados: sources em edos_sources, vítima não resolvível pelo nome
e inacessível diretamente pelo IP nas probes técnicas. Nenhuma nova instrumentação
temporal foi criada.

## Limitações

Proveniência Git do host não comprova conteúdo de imagens previamente construídas:
image IDs/digests são evidência separada. Código dirty não é reconstruível apenas
pelos hashes. Não se afirma alinhamento sem erro entre epoch e monotônico, ligação
packet/request direta ou equivalência dos dois processos tcpdump. Ausências e falhas
não são corrigidas. Regras formais de validade ficam para a Etapa 9; features para
a Etapa 10. Veja o inventário e contratos em [dataset.md](dataset.md).
