# D1 — Instrumentação diagnóstica CPU

Base: `400ca8f8913bb4385c5e9aefcddc5acbf4037581`, branch `refactor/project-organization`. Nenhum Docker, piloto, captura ou campanha executado. Sem otimizações, alteração de protocolo ou commit.

## Implementação e ativação

Arquivos desta atividade:

- `simulator/stats_collector.py`: checkpoints opcionais e método `bind_timing_diagnostics`.
- `simulator/cpu_diagnostics.py`: buffer limitado em memória e saída exclusiva no encerramento.
- `tests/test_cpu_timing_diagnostics.py`: seis testes offline novos.
- Este relatório.

O relatório anterior `reports/c134_pilot_offline_audit_20261108.md`, que já estava staged ao iniciar D1, permanece intacto.

A instrumentação fica **desabilitada por padrão**. Ativação pelo harness diagnóstico, após `bind_cpu` e antes de `start`:

```python
collector.bind_timing_diagnostics(
    diagnostic_directory / 'collector.cpu-timing-diagnostic.json',
    max_records=2048,
)
```

Não foi acrescentada flag ao runner científico nem ativação automática. O harness do teste futuro deverá fazer essa ligação explicitamente. Usar diretório novo, separado dos datasets/pilotos, preferencialmente fora da árvore raw exportada.

A saída exige sufixo `.cpu-timing-diagnostic.json`, usa criação exclusiva e declara `kind=cpu_timing_diagnostic_non_scientific`. Não acrescenta campos às observações CPU, não é entrada de `assign_cpu` e não é certificado de elegibilidade.

## Medições

Cada registro é identificado por run, sequência e contêiner. Checkpoints são segundos monotônicos absolutos do host; tempos científicos continuam relativos à origem oficial. Diferenças para aquisições bem-sucedidas:

| Medida | Cálculo |
|---|---|
| Atraso de início | `schedule_delay_seconds`, igual a max(0, início−agendamento) |
| containers.get / inspect | `inspect_end − inspect_start` |
| Validação identidade/geração | `validation_end − inspect_end` |
| container.stats | `stats_end − validation_end` |
| Extração/processamento até recebimento | `received − stats_end` |
| Cálculo delta CPU | `delta_end − delta_start` |
| Serialização científica | `serialization_end − serialization_start` |
| Write científico | `write_end − serialization_end` |
| Flush explícito | `flush_end − write_end` |
| Fsync científico | `fsync_end − flush_end` |
| Folga após trabalho da iteração | `remaining_until_next_seconds = next_scheduled_monotonic − schedule_observed_monotonic` |

`received` reutiliza o timestamp científico original convertido à base monotônica absoluta; não é uma nova definição de recebimento. A reconstrução por soma à origem pode ter arredondamento float muito pequeno. O atraso inclui o início antes da preparação do registro; o intervalo início→inspect_start permite observar esse preâmbulo.

O arquivo científico continua line-buffered: `write` pode incluir flush implícito. A medição do flush explícito não representa todo o custo de flush; alterar buffering aqui seria otimização e não foi feito. Checkpoints são medidas inclusivas dos pequenos custos de marcação/dispatch, não profiling exato de instruções. Folga é uma observação, não nova espera nem novo agendamento.

Se uma chamada falha, `acquisition_exception` e `acquisition_error` preservam a ocorrência. Checkpoints de etapas não concluídas ficam ausentes; o intervalo até a exceção pode medir a tentativa falha, mas não deve ser misturado aos percentis de sucesso.

## Isolamento e encerramento

Durante a coleta, diagnóstico acrescenta apenas leituras monotônicas e registros em memória. Não há nova chamada Docker, arquivo, serialização diagnóstica, fsync diagnóstico ou thread por amostra. Cada iteração continua executando inspect antes de stats; o cliente dedicado e `one_shot=True` permanecem como estavam.

O buffer guarda até `max_records`, sem truncamento ou descarte silencioso. Exceder o limite causa falha explícita do coletor. Após encerrar aquisições e fechar evidência/cliente, escreve o documento diagnóstico com flush/fsync, antes do summary científico. Erros diagnósticos entram em `self.failure`, são registrados no summary quando possível e propagados por `stop`. O documento tem contagem implícita pelo array ordenado, capacidade, identificação e estado de conclusão da coleta.

Não há garantia de recuperação do diagnóstico após SIGKILL, queda do host ou falha de escrita final: o buffer é volátil e um arquivo parcial não deve ser tratado como íntegro. `collection_complete` descreve conclusão do loop, não ausência de erros de aquisição individual nem certificação científica. Em erro fatal podem faltar checkpoints finais/folga; isso permanece visível.

## Preservação e testes

Permanecem nas posições originais: início monotônico, início epoch, fim epoch e fim monotônico. `received_seconds` continua igual a `call_end_seconds`, antes do delta e da persistência. Fórmula CPU, referências, intervalos, lead de 25 ms, regra ±50 ms, deadline de fechamento e política de oportunidades perdidas não foram alterados. `cpu_observations.py` e `cpu_features.py` não foram modificados.

**149 testes passaram** em 10,002 s:

```
.venv/bin/python -B -m unittest \
  tests.test_cpu_timing_diagnostics tests.test_cpu_observations \
  tests.test_cpu_accounting_audit tests.test_capture_lifecycle \
  tests.test_tcpdump_writer tests.test_source_containers \
  tests.test_dataset_validation tests.test_dataset_export
```

Os testes novos verificam durações conhecidas com relógio dirigido por operações; get→stats e argumentos; igualdade de observações/timestamps/deltas com modo ligado/desligado; saída científica byte a byte e replay temporal idênticos; serialização/write/flush/fsync separados; ausência de arquivo diagnóstico durante aquisições; fechamento, ordem, capacidade, criação exclusiva, falhas de saída e aquisição. `git diff --check` passou.

Esses testes demonstram preservação lógica sob relógio simulado, não igualdade de timestamps reais: a própria instrumentação consome tempo. O modo desligado não chama relógios diagnósticos nem cria registros/arquivo. O modo ligado adiciona checkpoints/dicionários, alocação e possível pressão de GC; pode alterar jitter. O limite evita crescimento sem controle, e a gravação final pode prolongar o encerramento. Overhead real ainda não foi medido.

## Proposta de validação controlada — não executada

1. Harness exploratório separado, sem slot científico e sem reutilizar diretórios anteriores. Mesmos recursos, fontes e carga ofensiva F96; coleta a 1 s, lead e tolerância intactos. Habilitar somente este diagnóstico, com capacidade suficiente para a execução e cauda.
2. Primeira triagem de **240 s: 30 s sem ataque, 120 s de emissão ofensiva, 90 s após emissão**. Preservar os 120 s ofensivos ajuda a observar o acúmulo que apareceu tardiamente no piloto. Isso reduz 150 s em relação ao piloto de 390 s e dispensa repetir separadamente L2/A3. É diagnóstico, não substituto de validação científica C1.3.4.
3. Analisar por início real da chamada e também por janela-alvo; identificar conclusões/atividade residual após emissão. Calcular n, p50/p90/p95, máximo e proporções de aquisição >25/>40/>50 ms para inspect, stats, validação, processamento, delta, persistência e atraso de início. p99 só como descritivo com n explícito; 30 observações de controle não sustentam inferência sobre caudas raras.
4. Reexecutar offline a atribuição oficial, cruzando rejeições com etapas lentas e folga. Separar falhas de API das chamadas bem-sucedidas. Não somar intervalos sobrepostos e não atribuir causalidade só por correlação.
5. Se o resultado apontar um componente dominante, uma execução pareada com diagnóstico desligado, mesmas condições e ordem alternada em repetições futuras, poderá avaliar o efeito observador pelos tempos científicos agregados. Não concluir overhead nulo pela diferença de duas execuções ruidosas.
6. Se 90 s POST não capturarem recuperação/latência persistente, prolongar uma próxima execução diagnóstica, sem alterar ou excluir a tentativa inicial. Não começar campanha nem otimizar o coletor antes de analisar os resultados e receber autorização.
