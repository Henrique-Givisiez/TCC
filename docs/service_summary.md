# Resumo offline de serviço — versão1

Implementação: [experiments/summarize_service.py](../experiments/summarize_service.py).
Contrato de origem: [RequestLogger](../simulator/request_logger.py),
[ground truth](ground_truth.md) e tabela `requests` de
[dataset_schema.py](../experiments/dataset_schema.py). Não altera esses contratos,
features Stage10, detectores ou resultados congelados. Inícios continuam medidos
no cliente, antes de `session.get` e depois do agendamento no executor.

## Uso e entradas

```bash
python3 -B -m experiments.summarize_service tests/fixtures/service_summary/request_log.csv \
  --phases tests/fixtures/service_summary/phases.json \
  --output /tmp/service-summary-synthetic.json
```

O exemplo usa somente requisições sintéticas, não executa tráfego. `--as-of 7`
reconstrói um resumo limitado a7s a partir das tentativas persistidas no CSV.
O comando exige saída nova e recusa sobrescrita. Não cria diretórios nem chama
Docker, simulador, scorer, calibrador ou avaliador. O módulo de testes chama
apenas uma função pura do avaliador em dados sintéticos para a auditoria de eventos.

O JSON de fases possui `schema_version=1`, `run_id` explícito e `phases`, lista de
`name`, `start_seconds`, `end_seconds`. Nomes únicos, intervalos contíguos e
positivos desde0. A fixture usa PRE `[0,3)`, ACTIVE `[3,6)`, POST `[6,9)` e
DRAIN `[9,12)`. Esses tempos **não** são recomendação de DEVELOPMENT. Fases não
estão no `ExperimentConfig` nem são inferidas de `attack_active`. O caller deve
fornecer marcos auditados; para controles pareados, registrar os mesmos limites
do par. Drenagem é uma fase explícita após o horizonte nominal, não o ataque.

`as_of` está entre0 e o fim da partição; por padrão é seu fim. Starts incluem
somente `start<as_of`; términos conhecidos incluem `end<=as_of` das tentativas
incluídas. Fases são estritamente semiabertas. Para não perder um término
exatamente no limite final, há o bucket técnico `__at_observation_end__`, de
exposição zero. Suas taxas são null; não se desloca timestamp por epsilon. Término
num limite interno pertence à fase seguinte. Zero duração é válido.

O resumo exige um único run e IDs únicos, colunas reais de `REQUEST_FIELDS`,
linhas completas, classe coerente com gerador e desfechos válidos. Incompletas
não podem ter fim, duração ou status fabricados. Términos conhecidos exigem
duração não negativa coerente com o intervalo (tolerância de serialização1e-6ms).
Não há imputação. O resumo não certifica que o arquivo contém todas as tentativas:
um CSV sendo escrito pode não incluir requisições ainda pendentes. Usar cópia
estável/finalizada; snapshots sintéticos `as_of` não são recuperação de crash.

## Campos, relógios e denominadores

Saída JSON `schema_version=1`: identidade do run, hash SHA256/caminho do input,
plano de fases utilizado, corte, `rows` por classe/fase e `reconciliation`.
Decimais são serializados como **strings decimais**, contagens como inteiros e
ausências como JSON null. Não é um schema Stage8 ou Stage10.

| Campo por classe/fase | População/instante |
|---|---|
| `starts` | Tentativas pelo início no cliente |
| `known_ends`, `end_outcomes` | Términos conhecidos pelo fim no cliente |
| `cohort_known_ends`, `cohort_outcomes` | Desfechos conhecidos das tentativas iniciadas nessa fase, mesmo quando terminam em outra |
| `cohort_open_as_of` | Starts sem término conhecido até o corte |
| `cohort_incomplete_no_end` | Subconjunto com `outcome=incomplete`, sem fim no arquivo |
| `cohort_end_after_cutoff` | Subconjunto cujo fim registrado é posterior ao corte; desfecho/duração futuros não entram no resumo daquele corte |
| `completed_cross_phase` | Tentativas com início e fim conhecidos em fases diferentes, contadas na coorte inicial; cada tentativa conta uma vez |
| `open_crossed_phase_boundary` | Tentativas sem fim conhecido até o corte para as quais alguma fronteira interna posterior ao início já foi atingida; diagnóstico de observação, não prova de execução ainda ativa |
| `duration_success_2xx_ms` | Média, p50 e p95 de sucessos2xx concluídos até o corte, por **coorte de início**; `n` e `eligible_known_successes` explícitos |

Categorias de `cohort_outcomes` e `end_outcomes`: `success_2xx`,
`other_response`, `http_error`, `transport_error`, `client_error`.
`response` com302 é `other_response`, não sucesso2xx e não falha HTTP.
`http_error` segue status>=400; `ReadTimeout` é falha de transporte, não pacote
perdido. Incompletas ficam fora das categorias concluídas, sem término/duração
presumidos. Não usar o resumo legado de respostas como contagem de starts.

`exposure_seconds=max(0,min(phase_end,as_of)−phase_start)` é duração observada
da fase, não tempo somado das chamadas. `rates_per_second` divide starts,
términos e cada categoria terminal por essa exposição. Sucesso terminal/s é
vazão, enquanto a duração2xx pertence à coorte inicial. Exposição zero produz
null; zero eventos em exposição positiva produz taxa zero. Não há taxa nominal
inferida, correção por falhas de coleta ou exposição inventada.

`cohort_fractions` explicita contagens denominadoras:

- `success_2xx_per_started`: sucessos conhecidos da coorte / starts da coorte.
- `failures_per_started`: HTTP+transporte+cliente conhecidos / starts.
- `failures_per_known_end`: essas falhas / términos conhecidos da mesma coorte.
- `incomplete_no_end_per_started`: incompletas sem fim / starts.

Denominador zero é null. `unresolved` e `final` mostram coortes ainda abertas.
Frações por starts em coorte aberta são frações **já observadas**, não estimativas
finais de sucesso/falha. Frações por término e durações são condicionadas aos que
concluíram: podem sofrer seleção por timeout/censura. Uma incompleta no log final
continua com fim desconhecido; não se converte em falha de transporte.

Quantis usam interpolação linear tipo7 (`h=(n−1)p`). n=0: média/quantis null;
n=1: quantis iguais ao único valor, sem alegação de precisão de cauda. Não se
impõe limiar de suporte arbitrário: mostrar n e decidir adequação antes da análise
científica. Não calcular IC ou tratar requisições/janelas como réplicas nesta etapa.

## Demonstração sintética e reconciliação

[Fixture CSV](../tests/fixtures/service_summary/request_log.csv) e
[fases](../tests/fixtures/service_summary/phases.json), corte12s:

| Classe/fase | Starts | Términos nessa fase | Términos da coorte | Sem fim conhecido | n2xx da coorte | Média/p50/p95 ms |
|---|---:|---:|---:|---:|---:|---|
| benign/PRE |2|1|2|0|2|1000/1000/1000|
| benign/ACTIVE |4|4|4|0|1|500/500/500|
| benign/POST |2|1|1|1|1|3000/3000/3000|
| benign/DRAIN |0|1|0|0|0|null/null/null|
| attack/POST |1|0|1|0|0|null/null/null|
| attack/bucket final |0|1|0|0|0|null/null/null|

Demais linhas sem eventos são mantidas com suporte zero. Reconciliação global:
**9 starts = 8 términos conhecidos + 1 sem fim conhecido**. Há4 cruzamentos
concluídos de fase: PRE→ACTIVE, ACTIVE→POST (timeout), POST→DRAIN (2xx) e
POST→bucket final (erro de cliente). A incompleta benigna POST também atinge
uma fronteira observacional, mas não recebe fase final presumida.

Na coorte benigna ACTIVE: 1 sucesso2xx, 1 resposta302, 1 HTTP503 e 1 timeout;
falhas/starts=2/4. Entre3 segundos de exposição, starts/s=4/3. O2xx iniciado
em2,5 e terminado em3,5 pertence aos términos ACTIVE e às durações PRE.

Com corte7s: 7 starts incluídos = 5 términos conhecidos + 2 sem término até
o corte; 2 starts futuros são ignorados. O timeout termina em8s, logo continua
aberto no corte7; falhas conhecidas ACTIVE/starts=1/4, falhas/términos da
coorte=1/3 e `final=false`. A chamada iniciada em6,5 termina em9,5: sua
duração3000ms não aparece no corte7 e aparece na coorte POST após drenagem.
A linha `incomplete` iniciada em7,5 continua sem término/duração no corte12.

## Conferência da regra histórica de eventos

Fontes: `event_level` de
[stage14_test_evaluation_protocol_v1.json](../experiments/protocols/stage14_test_evaluation_protocol_v1.json),
`event_metrics` em [stage15b_evaluation.py](../experiments/stage15b_evaluation.py)
e `independent_event` em [stage15b_reproduce.py](../experiments/stage15b_reproduce.py).
O framework genérico em `analysis/detection/evaluation/__init__.py` delega
a regra a callbacks; não impõe prazo adicional.

**Não foi encontrada divergência** entre contrato e esses dois avaliadores:
janela primária inteira em `[48,144)`, decisão positiva, interseção estritamente
positiva com `[actual_start,actual_end)`; detection_time é a menor disponibilidade
elegível. Não há condição `available_at<=actual_end`; `drained_end` não delimita
o evento. Miss tem delay null. Tocar apenas uma fronteira não é interseção positiva.

Exemplo sintético: evento `[48.25,48.75)`, janela `[48,49)`, decisão positiva
disponível em49s. Interseção=.5s; **detectado**, atraso=49−48.25=.75s, embora
a decisão seja posterior ao fim do evento. Esse mesmo comportamento é coberto
pelo teste histórico `test_event_actual_end_and_delayed_availability_are_preserved`.
O novo teste chama os dois avaliadores puros somente nesse exemplo sintético;
não reavalia os resultados congelados. A interpretação “o alarme deve ocorrer
durante o evento” seria divergente do contrato existente e exigiria métrica
nova, previamente especificada, sem corrigir retroativamente Stage15B.

## Validação e limites desta entrega

[tests/test_service_summary.py](../tests/test_service_summary.py) cobre fronteiras,
302/2xx/503, timeout, erro de cliente, incompleta, drenagem, corte parcial,
quantis, denominadores nulos, CSV inválido, IDs/run, recusa de sobrescrita,
regra histórica sintética e campos reais do plano documental DEVELOPMENT.
Validação realizada: `python3 -B -m unittest tests.test_service_summary
tests.test_ground_truth tests.test_experiment_config -v`: **31 testes, OK**;
os testes de componentes usam mocks, sem experimentos reais.
Fixtures não são experimentos nem dados científicos. A entrega não implementa
CUSUM, não altera coleta, host, RTT específico ou UDP.
