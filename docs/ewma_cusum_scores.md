# EWMA e CUSUM — implementação para revisão

Estes dois métodos produzem somente scores escalares causais. Não executam
simulações, fitting, busca de parâmetros ou decisões. Nesta etapa, somente testes
sintéticos/DEVELOPMENT estão autorizados; scoring científico de CALIBRATION e
TEST permanecem sem autorização. O calibration freeze existente de Z-score/CoV
permanece inalterado.

## Normalização baseline

Ambos recebem os parâmetros de um artefato baseline Z-score existente e usam
`z_t = (x_t - mu_B) / sigma_B`. Delegam a validação dos momentos e o cálculo do
residual a `ZScore.start_run/update`, sem chamar `ZScore.fit` nem estimar parâmetros
com a série alvo. Os detectores não possuem método `fit`.

O hook explícito `baseline_spec(spec, feature)` permite que `score_run` confira um
componente de normalização diferente do componente de score. EWMA/CUSUM exigem o
componente Z-score v1 original, a mesma feature/representação/janela do baseline e
uma destas cinco features, tratadas independentemente:

- network: `ingress_packet_count`, `ingress_tcp_payload_length_sum_bytes`;
- service: `request_starts`, `mean_duration_ms`;
- infrastructure: `mean_cpu_percent`.

O score artifact mantém sua identidade EWMA/CUSUM, a referência com hash do
baseline, seus parâmetros e suas sources originais. Detectores sem esse hook
continuam exigindo a identidade original entre detector e baseline; o contrato de
Z-score e CoV não mudou. Não há leitura de labels nem arquivos de ground truth.

## EWMA

`E_t = 0.2*z_t + 0.8*E_(t-1)`, com estado inicial zero. A primeira observação
válida já produz score; não existe warm-up adicional. O score é assinado, com
direção upper-tail; não há valor absoluto, clipping em zero ou lower-tail.

`ewma_spec()` expõe somente lambda `"0.2"`, decimal exato. Configurações diferentes
ou representações não canônicas, como float binário, são rejeitadas.

## CUSUM

`C_t = max(0, C_(t-1) + z_t - 0.5)`, com estado inicial zero. O único k permitido
é `"0.5"`, decimal exato. Evidência insuficiente reduz o acumulador até zero;
zero é um score válido. Não há CUSUM inferior ou bilateral.

## Estado, precisão e disponibilidade

Null produz score unavailable, motivo `missing_observation_reset`, e zera o estado
dinâmico de cada método. A próxima observação válida começa de zero usando os
mesmos parâmetros baseline. Não há carregamento de estado através de lacuna.
Índices fora de ordem, janelas descontínuas e mudança de run no mesmo estado são
rejeitados; cada novo run requer `start_run`.

Normalização e recorrências usam contexto Decimal privado de 50 dígitos,
ROUND_HALF_EVEN, sem depender do contexto global. Disponibilidade segue o pipeline
existente no fechamento da janela, sem antecipação de evidência. O histórico começa
no início da série; uma eventual seleção temporal deve ocorrer depois do scoring,
sem reinicializar o estado na fronteira de seleção.

## Integração

```python
from analysis.detection import score_run
from analysis.detection.artifacts import open_artifact
from analysis.detection.detectors.ewma import EWMA, ewma_spec
from analysis.detection.detectors.cusum import CUSUM, cusum_spec

# source: uma série DEVELOPMENT sintética explicitamente selecionada.
# reference: referência com hash do modelo Z-score previamente congelado.
baseline = open_artifact(reference, 'baseline')
e = score_run(source, EWMA(), ewma_spec(), 'novo-ewma-dev', baseline=baseline)
c = score_run(source, CUSUM(), cusum_spec(), 'novo-cusum-dev', baseline=baseline)
```

Não há threshold no scorer. O calibrador empírico e a política estrita existentes
continuam separados e sem alterações. Os guards existentes seguem rejeitando TEST
antes da leitura dos dados. Futuras calibrações científicas exigem revisão e
autorização próprias; os 12 CALIBRATION não são usados para escolher lambda ou k.

## Testes

`tests/test_ewma_cusum.py` cobre sequências manuais, inicialização, sinal, reset
natural do CUSUM, null/reset, causalidade por prefixo, precisão e determinismo,
configuração inválida, restrição às cinco features, reutilização de parâmetros sem
fitting, identidade/provenance dos artefatos, separação score/calibração/decisão e
guards de TEST. Fixtures são sintéticas e independentes dos artefatos científicos.
