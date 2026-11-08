# D1.1 — Preparação de uma execução exploratória CPU

Base confirmada: `786632c61bcde4723b19659b12592144624dbe48`, branch `refactor/project-organization`; working tree inicialmente limpo. **Nenhum Docker, piloto ou experimento executado nesta atividade. Sem commit.**

## Integração

O `StatsCollector` é criado em `simulator/source_experiment.py`, após a inicialização das duas capturas e antes de liberar as fontes. A sequência continua:

1. Construção, registro da vítima e cliente dedicado.
2. `bind_cpu(...)`.
3. Novo `bind_collector(...)`, que só ativa timing com um `TimingRequest` exploratório explícito.
4. Registro do contrato CPU no status, `start()` e liberação das fontes.

O mecanismo de ativação fica em `experiments/cpu_timing_diagnostic.py`; a única opção CLI é `--cpu-timing-diagnostic-dir` em `experiments.diagnostic_run`. Não há variável de ambiente, opção na configuração científica ou mudança nos runners da campanha. `diagnostics.enabled=true` sozinho não ativa timing. Ausência da requisição é no-op; tipo incorreto ou tentativa científica falham explicitamente.

A CLI exige exatamente a configuração D1.1, composição combined, política protegida e imagens fixadas; rejeita `--scientific-pilot-scenario`. O bind verifica novamente configuração e marcadores `cpu_timing_exploratory=true`, `campaign_slot=false`, sem scientific_pilot.

O diretório diagnóstico é criado exclusivamente, antes do acesso Docker. Diretórios raw, raw.attempt, dataset e diagnóstico devem ser novos e sem relação de ancestralidade; symlinks são resolvidos antes da checagem. A saída de timing não entra no dataset: fica em diretório irmão, com request.json separado e nome/tipo explicitamente não científico. Não há retry nem sobrescrita automática. Uma falha posterior de preflight pode deixar esse diretório reservado; preservar e escolher nova raiz.

## Configuração e integridade

`experiments/configs/cpu_timing_d1/` contém:

- `f96_240.json`: derivado do F96 aprovado; somente id, duração 390→240 e início ofensivo 150→30 foram alterados.
- `policy.json`: política protegida original; mínimo de RAM disponível 2 GiB, disco livre 4 GiB, orçamento de artefatos raw 512 MiB, timeout global 480 s e limites dos contêineres originais.
- `reference.json`: imagens e SHA256 da configuração de origem; fases [0,30), [30,150), [150,240).
- `SHA256SUMS`: hashes dos três arquivos preparados.

Mantidos: fontes em contêineres, topologia direta, vítima fixa com dois workers, tráfego legítimo 2×8/s /medium e concorrência 64; ofensivo 2×32/s /medium, work_units=5000, concorrência 96; seed 202611080134, timeout cliente 2 s e coleta CPU a 1 s. CPU, lead de 25 ms e tolerância de 50 ms não mudaram. Esta configuração é exploratória, não uma execução de 390 s do protocolo C1.3.4.

Imagens:

- vítima: `sha256:03a186aa90eec03b874c82a887b245e7190fa45cd7256af3c077cb64943d52b0`
- fonte: `sha256:b94212edd4d31c34998aea870caebc4ba145c1593d1b8dfdc27fe4917719fe3e`

A comparação offline de `expected_files` com a evidência das imagens do F96 confirmou igualdade. Presença e identidade efetivas no daemon serão verificadas pelo preflight existente, sem rebuild ou troca automática por tag. Nenhum acesso ao daemon foi feito agora.

## Comando exato — somente após autorização

Executar a partir da raiz do repositório. O bloco realiza **uma única tentativa**, sem repetição; a raiz é exclusiva e independente dos pilotos históricos:

```bash
(
  set -euo pipefail
  sha256sum -c experiments/configs/cpu_timing_d1/SHA256SUMS
  RUN_ROOT="$(mktemp -d "$HOME/tcc_cpu_timing_d11_XXXXXXXX")"
  printf 'Diretório desta tentativa: %s\n' "$RUN_ROOT"
  .venv/bin/python -B -m experiments.diagnostic_run \
    --config experiments/configs/cpu_timing_d1/f96_240.json \
    --operational-policy experiments/configs/cpu_timing_d1/policy.json \
    --composition combined \
    --output "$RUN_ROOT/raw" \
    --dataset-output "$RUN_ROOT/dataset" \
    --cpu-timing-diagnostic-dir "$RUN_ROOT/diagnostics" \
    --victim-image sha256:03a186aa90eec03b874c82a887b245e7190fa45cd7256af3c077cb64943d52b0 \
    --source-image sha256:b94212edd4d31c34998aea870caebc4ba145c1593d1b8dfdc27fe4917719fe3e
)
```

A preparação verifica ≥4 GiB no filesystem diagnóstico. O preflight protegido existente verifica espaço/RAM e recursos residuais antes de executar a carga; os guards permanecem durante a execução. Se qualquer etapa falhar, não insistir, limpar recursos genericamente ou usar `--previous-run` para contornar a falha. Preservar a raiz e investigar. Guardar o caminho impresso e o código de saída; fechar a janela administrativa não implica que o diagnóstico terminou corretamente.

## Conferência após a execução

Com `RUN_ROOT` apontando para o caminho impresso, sem modificar raw/dataset:

```bash
.venv/bin/python -B -m experiments.validate_dataset \
  "$RUN_ROOT/dataset" --output "$RUN_ROOT/validation.json"
```

Conferir o conteúdo, não apenas a existência do arquivo de validação:

- `raw/run_status.json`: completed, producers_drained=true, errors vazio; os contadores CSV e PCAP devem ser completos e ter zero descartes.
- `raw/operational_policy.json`: certificação completed e progression_allowed=true; a tentativa deve estar marcada exploratória, fora da campanha.
- `validation.json`: dataset_valid/analysis_eligible verdadeiros, sem bloqueadores; falhas HTTP e avisos temporais devem ser reportados, não ocultados.
- `diagnostics/collector.cpu-timing-diagnostic.json`: kind correto, run_id igual ao status, collection_complete=true, collector_failure=null; sequências ordenadas e únicas, número de registros igual a attempts do summary CPU. Para cada aquisição bem-sucedida conferir checkpoints até fsync e o próximo agendamento; etapas ausentes em aquisições falhas precisam estar justificadas por erro explícito.
- `diagnostics/request.json` e a proveniência raw: configuração, imagens e código executado; preservar também raw.attempt.

Separar medições por início real da chamada e por janela-alvo: sem ataque [0,30), emissão [30,150), pós-emissão [150,240). Relatar n, p50/p90/p95/máximo por operação, frequência de aquisição >50 ms, atrasos e rejeições da atribuição oficial. O snapshot final pode completar após uma fronteira de fase. POST não prova ausência de processamento residual. Não usar esse teste para calibrar detectores ou afirmar elegibilidade científica.

Capacidade diagnóstica: 512 registros, superior ao tempo total máximo de 480 s com uma vítima/coleta a 1 s; excedê-la falha explicitamente. Nenhuma persistência diagnóstica adicional ocorre por aquisição. Overhead de checkpoints permanece; não há garantia de neutralidade de desempenho ou de arquivo final após morte abrupta.

## Testes desta etapa

Sete testes de integração novos, incluindo encaminhamento positivo da CLI com Docker inteiramente simulado, configuração fixa, ativação após bind_cpu/antes do start, default desligado, bloqueio científico, diretórios e espaço. Suíte ampliada: **186 testes aprovados em 9,509 s**:

```
.venv/bin/python -B -m unittest tests.test_cpu_timing_integration \
  tests.test_cpu_timing_diagnostics tests.test_cpu_observations \
  tests.test_cpu_accounting_audit tests.test_protected_compositions \
  tests.test_exploratory_certification tests.test_source_containers \
  tests.test_capture_lifecycle tests.test_tcpdump_writer \
  tests.test_dataset_validation tests.test_dataset_export
```

`git diff --check` passou. Os testes não validam comportamento real sob carga nem disponibilidade de imagens no daemon. A execução Docker descrita acima continua aguardando autorização.
