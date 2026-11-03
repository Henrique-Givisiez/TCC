# Seção 4.6 — Preparação, calibração e configuração dos detectores

Investigação documental offline em 03/11/2026. HEAD analisado: `abc1053c7b7d730efe64898f4f2fdb4d7a29dcdb`. O diretório de trabalho estava limpo no início. Não foram executados detectores, recalibrações, campanhas ou validadores que reproduzem trajetórias. As verificações desta investigação limitaram-se à leitura de JSON/CSV, conferência de referências, hashes, contagens e resumos de calibração já existentes. Somente este relatório foi acrescentado ao repositório.

## Identificação da campanha e das evidências

A campanha final identificada é **`scientific-reduced-clock-r2-20261029`**, com quatro métodos e cinco features. Sua autoridade é `experiments/protocols/scientific_reduced_clock_r2_20261029/plan.json`, SHA256 `6240452e214b0748b023a084edd6dcf4fd2fd0a43744ed70a37bdb88a4319bc4`. O plano vincula explicitamente `docs/scientific_protocol_reduced_20261029.json`, SHA256 `d4ac35dadcf97a85cecfdaecbdc28bf90ef711fc00cb2874a9872780d7ac9afb`, e a raiz efetiva dos resultados. A identificação decorre do encadeamento real dos quatro checkpoints até TEST, não do nome de um arquivo de documentação.

Para abreviar caminhos, neste relatório:

- **R** = `experiment_results/scientific-reduced-clock-r2-20261029`;
- **A(f)** = `R/analysis/<feature>`;
- **E** = `analysis/detection/scientific/engine.py`;
- **D** = `analysis/detection/detectors`.

As abreviações designam caminhos literais relativos à raiz do repositório. Por exemplo, `A(request_starts)/calibration/manifest.json` é `experiment_results/scientific-reduced-clock-r2-20261029/analysis/request_starts/calibration/manifest.json`.

Principais fontes consultadas:

| Fonte | Estrutura/funções relevantes |
|---|---|
| Plano r2 acima | `protocol`, `runtime_hashes`, `entries`, `results_root`, `handoff` |
| `docs/scientific_protocol_reduced_20261029.json` | `specification.counts`, `components`, `selection`, `alpha`, `h_grid`, gates A/B, políticas de falha e `test_feedback` |
| `experiments/scientific_campaign.py` | `run_partition`, `checkpoints`, `verify_graph`: ordem, publicação e liberação |
| E | `fit`, `trace`, `selected`, `calibrate`, `adherence`, `eligible`, `verify`, `process`, leitores de metadados |
| `analysis/detection/scientific/data.py` | `load_source`, `validate_membership`, `validate_test_release`, `verify_reference` |
| D | `ZScore`, `CoV`, `EWMA`, `CUSUMFreeze`, `CUSUM`, `_moments.py`, `_standardized.py` |
| `analysis/detection/cusum_freeze_run.py` | `process_series`, `transition_rows`: integração da transição acoplada |
| `analysis/detection/empirical.py` | `quantile_index`: índice exato do quantil |
| `R/checkpoints/{BASELINE,CAL_A,CAL_B,TEST}/manifest.json` | `receipts`, `artifacts`, `previous_checkpoint`, `authority` |
| `A(f)/{baseline,calibration,verification}/manifest.json` | momentos, limiares, candidatos, suporte e aprovação |
| `A(f)/calibration-candidates/candidate-<multiplicador>/` | `manifest.json` e `transitions.csv`, inclusive candidatos rejeitados |
| `A(f)/TEST/<entry>/manifest.json` | referências de preparação e `components` efetivamente usados |
| `R/journal/*.json` | sequência encadeada de coletas aceitas e conclusões de partições |
| `reports/scientific_reduced_clock_r2_20261030/calibration.json` | extrato documental dos limiares e da verificação; fonte auxiliar |

A conferência independente dos hashes do plano encontrou **zero divergências** entre `plan.runtime_hashes` e os arquivos atuais correspondentes. Assim, as implementações atuais citadas abaixo correspondem ao código congelado dessa campanha. A leitura recursiva da referência TEST conferiu 531 manifests e 922 arquivos distintos entre manifests, saídas e referências de fontes observáveis/validação. Esse número não representa uma nova auditoria de todos os arquivos brutos dos recibos. Foram também conferidas as referências de preparação dos 180 artefatos TEST (36 por feature), sem recalcular seus scores. O extrato `calibration.json` coincide nos campos presentes; ele omite `authority` e `code`, preservados nos manifests originais.

### Divergências e precedência das fontes

1. `experiments/stage15a_test_scoring.py` → `configurations` e seu freeze de Stage14/15 pertencem à campanha anterior: usam `cusum` sem congelamento e uma política posterior de limiar. Não constituem autoridade desta campanha, cujos `METHODS` e artefatos TEST contêm `cusum-freeze`.
2. `README.md` e `docs/cusum_freeze_calibration_pending.md` ainda apontam a calibração científica como pendente. Isso descreve uma entrega anterior. Os manifests r2 contêm calibração em CAL-A e aprovação em CAL-B para as cinco features. A afirmação histórica de pendência não descreve o estado final r2.
3. O cabeçalho de `analysis/detection/cusum_freeze_run.py` diz que não há adaptador científico naquele módulo. De fato, `process_development_run` continua restrito a DEVELOPMENT; a campanha final usa sua API em memória `process_series` por meio de **E → `trace`**, com os vínculos científicos implementados em E. O cabeçalho não deve ser interpretado como inexistência dessa integração em outro módulo.
4. `docs/scientific_protocol_20261029.json` e a documentação da proposta anterior não substituem o protocolo **reduced** vinculado ao plano r2. `docs/scientific_reduced_implementation_20261029.md` e `docs/scientific_clock_handoff_20261029.md` incluem estados prospectivos anteriores à execução; os checkpoints e o journal registram o que efetivamente ocorreu.
5. A raiz `experiment_results/scientific-reduced-20261029` é a predecessora, vinculada por `plan.handoff`. A campanha r2 aproveita o mesmo inventário científico, mas seus modelos e calibrações estão em R. A tentativa técnica anterior de BASELINE não integra as quatro fontes ajustadas; o recibo aceito do primeiro slot aponta `attempt-2`.

A precedência aplicada foi: plano e protocolo vinculados → checkpoints e referências com hashes → manifests e saídas efetivos → implementação cujo hash coincide → documentação auxiliar. Não se transplantaram parâmetros de campanhas antigas nem defaults de outros fluxos.

## 2.1 Separação das partições

| Partição | Execuções aceitas | Função e momento de participação |
|---|---:|---|
| BASELINE | 4 | Primeira etapa; estima a referência estática de cada feature, sem escolher limiares. |
| CAL-A (`CAL_A` nos arquivos) | 8 | Segunda etapa; calcula os limiares de Z-score/CoV/EWMA, constrói e avalia a grade do CUSUM com congelamento e aplica os critérios de elegibilidade. |
| CAL-B (`CAL_B` nos arquivos) | 8 | Terceira etapa; aplica as configurações já selecionadas, calcula suporte/falsos alarmes por execução e aprova ou reprova, sem nova seleção. |
| TEST | 36 | Somente aplicação da configuração liberada por CAL-B; não estima referências nem escolhe parâmetros/limiares. |

Evidências: plano → `entries[].partition`; protocolo → `counts`; checkpoints → `expected_slots`, `receipts`; E → `check_sources`; runner → `run_partition`. Os três primeiros conjuntos são do cenário de controle C16. Os 36 slots TEST estão em 12 blocos; não são 36 execuções adicionais de calibração. As quatro etapas usam os mesmos conjuntos de execuções para todas as features e métodos.

O histórico registra 56 recibos aceitos no r2, com 4/8/8/36 nas respectivas partições. A substituição do primeiro slot BASELINE preserva quatro execuções aceitas, não cinco observações de referência nem duas contribuições do mesmo slot. Evidência: `R/checkpoints/BASELINE/manifest.json` → `receipts[0].path`, `R/journal` → `HANDOFF_IMPORTED`, `TECHNICAL_FAILURE`, `REPLACEMENT_APPROVED`, `COLLECTION_ACCEPTED`.

A referência é congelada no artefato BASELINE. Os parâmetros de forma (`L=6`, `lambda=0.2`, `k=0.5`, convenções e inicialização) já estão definidos pelo protocolo/código congelados antes das coletas. Os limiares ficam selecionados e imutáveis ao publicar CAL-A. CAL-B apenas condiciona a liberação para TEST; seu checkpoint encerra o congelamento da configuração utilizável na avaliação. Não há treinamento adaptativo entre runs ou durante TEST. Evidências: E → `fit`, `calibrate`, `process`; runner → `run_partition`; §2.7 e §2.10.

## 2.2 Construção das referências a partir de BASELINE

Para cada feature, E → `fit` exige exatamente quatro fontes BASELINE e verifica, **em cada execução**, pelo menos 342 valores presentes nas 360 observações de índices 30 a 389. Usa o recorte `observations[30:390]`, correspondente às janelas de 1 s completamente contidas em `[30,390)`. Os valores anteriores e a cauda posterior não participam do ajuste.

`D/zscore.py` → `ZScore.fit` percorre cada série, exclui valores `None`, guarda `support_by_run` e concatena os valores válidos das quatro execuções. Não calcula uma média de quatro desvios-padrão nem combina estimativas por run. Cada observação válida tem peso igual; se houvesse números válidos diferentes, os pesos totais das execuções seriam proporcionais ao suporte válido. Na campanha, cada run contribuiu com 360 valores: **1.440 válidos e zero ausentes por feature**.

Seja B o multiconjunto concatenado, com n valores válidos. A implementação calcula:

\[
\mu_B=\frac{1}{n}\sum_{x\in B}x,\qquad
s_B^2=\frac{1}{n-1}\sum_{x\in B}(x-\mu_B)^2,\qquad
\sigma_B=\sqrt{s_B^2}.
\]

Evidência: `D/_moments.py` → `sample_moments`, `standard_deviation`; `D/zscore.py` → `ZScore.fit`. A convenção é amostral, **`ddof=1`**, com no mínimo dois valores. Média e variância são calculadas como frações exatas dos valores decimais recebidos; `mean_exact` e `variance_exact` são persistidos como numerador/denominador. `mu` e `sigma` são as representações decimais de 50 dígitos significativos, `ROUND_HALF_EVEN`. O residual usa a média racional exata antes do arredondamento, e não uma subtração prévia em float.

| Método | O que obtém de BASELINE | O que não é transferido entre execuções |
|---|---|---|
| Z-score | Média exata, variância exata e sigma da feature, suporte e convenções. | Não tem estado acumulativo temporal. |
| CoV | Não possui referência estática estimada em BASELINE; `start_run` recebe `None`. O fluxo científico exige, porém, um modelo BASELINE válido da feature para liberar sua calibração juntamente com os outros métodos. | Histórico local de seis valores começa vazio em cada run. |
| EWMA | Reutiliza exatamente a referência Z-score da feature; não estima outro modelo. | Estado EWMA inicia em zero em cada run, não no estado final de BASELINE. |
| CUSUM com congelamento | Reutiliza exatamente a referência Z-score da feature; não estima outro modelo. | Estado acumulado inicia em zero em cada run; nenhum estado final de BASELINE é herdado. |

Evidências: E → `fit`, `calibrate`, `trace`; `D/_standardized.py` → `start_run`; `D/cusum_freeze.py` → `start_run`; `A(f)/baseline/manifest.json` → `parameters`. A referência inteira e seu hash permanecem congelados em CAL-A, CAL-B e TEST. BASELINE não determina `lambda`, `k` ou `lookback`; esses valores são fixos.

### Referências numéricas persistidas

Os números abaixo são transcrições literais, sem arredondamento adicional. Para a média racional e a variância exatas, a autoridade é o campo indicado, não uma reconstrução a partir desta tabela.

| Feature | `parameters.mu` | `parameters.sigma` | Válidos/ausentes | Evidência |
|---|---|---|---|---|
| `request_starts` | `15.927777777777777777777777777777777777777777777778` | `4.0382542627404321164287777025188940008939261913884` | 1440/0 | `A(request_starts)/baseline/manifest.json` → `parameters`, `mean_exact`, `variance_exact` |
| `mean_duration_ms` | `29.653516115652196590618808654050546778073623526026` | `5.0684375169314449160593784500482526041907384848921` | 1440/0 | `A(mean_duration_ms)/baseline/manifest.json` → `parameters`, `mean_exact`, `variance_exact` |
| `ingress_packet_count` | `40.055555555555555555555555555555555555555555555556` | `10.985161371833495406251992911734639219218830851038` | 1440/0 | `A(ingress_packet_count)/baseline/manifest.json` → `parameters`, `mean_exact`, `variance_exact` |
| `ingress_tcp_payload_length_sum_bytes` | `3121.8444444444444444444444444444444444444444444444` | `791.76762037028332552866791553681864371035392430694` | 1440/0 | `A(ingress_tcp_payload_length_sum_bytes)/baseline/manifest.json` → `parameters`, `mean_exact`, `variance_exact` |
| `mean_cpu_percent` | `20.759263888888888888888888888888888888888888888889` | `5.5164429437562402883169803627284575803893956762647` | 1440/0 | `A(mean_cpu_percent)/baseline/manifest.json` → `parameters`, `mean_exact`, `variance_exact` |

## 2.3 Implementação exata dos quatro detectores

Em todas as fórmulas, x_t é a observação da feature, h é o limiar congelado da combinação e z_t é o residual padronizado pela referência da mesma feature. A precisão decimal é 50, com `ROUND_HALF_EVEN`. A decisão disponível é sempre **score > h**: igualdade produz decisão negativa válida. Não há valor absoluto no Z-score nem no denominador do CoV. Evidências: E → `trace`, `calibrate`; `D/cusum_freeze.py` → `step`, `freeze_spec`.

### Z-score

\[
z_t=\frac{x_t-\mu_B}{\sigma_B},\qquad
q_t=z_t,\qquad a_t=\mathbf{1}\{q_t>h_Z\}.
\]

O score publicado é o **Z-score com sinal**, com alarme na cauda superior. A subtração da média usa `mean_exact`; o quociente usa `sigma` decimal validado contra `variance_exact`. Não há histórico móvel, adaptação, confirmação ou estado temporal a inicializar: `start_run` carrega a normalização congelada. Parâmetro calibrado: apenas `h_Z`. Fixos: `ddof=1`, ponderação por observação, precisão e políticas de missing/zero sigma. Evidências: `D/zscore.py` → `CONFIG`, `start_run`, `update`; E → `trace`.

`x_t=None` publica score e decisão nulos, sem alterar a referência. Média BASELINE igual a zero, isoladamente, não causa divisão por zero: o divisor é sigma. Variância BASELINE zero, sigma não positivo ou menos de dois valores rejeitam o modelo; não se acrescenta epsilon. Observação zero é válida quando a referência é válida. Uma série corrente constante não torna o score indisponível, pois não se estima um novo sigma sobre ela.

### Coeficiente de Variação (CoV)

Se H_t contém as últimas **seis observações consecutivas válidas**, incluindo x_t:

\[
\bar x_t=\frac{1}{6}\sum_{x\in H_t}x,\qquad
s_t^2=\frac{1}{5}\sum_{x\in H_t}(x-\bar x_t)^2,\qquad
q_t=\frac{\sqrt{s_t^2}}{\bar x_t},\qquad
a_t=\mathbf{1}\{q_t>h_{CoV}\}.
\]

Evidências: `D/cov.py` → `cov_spec`, `start_run`, `update`; `D/_moments.py` → `sample_moments`; E → `trace` fixa explicitamente `lookback=6`. O score é sigma amostral dividido pela média aritmética local, sem módulo/epsilon; o alarme usa cauda superior. Os momentos são recalculados a partir da deque retida, evitando uma atualização incremental da variância. `lookback=6` é fixo, não resultado de busca em CAL-A. Só `h_CoV` é calibrado.

O histórico começa vazio por run. As primeiras cinco observações válidas consecutivas não geram score. Um `None` limpa a deque e produz indisponibilidade; é preciso completar novamente seis válidas consecutivas. Média local zero gera score/decisão nulos, mas preserva o histórico já atualizado; não equivale a um missing que limpa a deque. Sigma local zero com média não nula produz score zero válido. Nas features científicas, valores negativos são recusados na entrada; não se interpreta o caso de média negativa como variante desta campanha. Janelas fora de ordem/sem continuidade produzem erro de contrato, não um alarme.

### EWMA

\[
z_t=\frac{x_t-\mu_B}{\sigma_B},\qquad
E_{-1}=0,\qquad E_t=0{,}2z_t+0{,}8E_{t-1},\qquad
q_t=E_t,\qquad a_t=\mathbf{1}\{q_t>h_E\}.
\]

Evidências: `D/ewma.py` → `LAMBDA`, `EWMA.update`, `ewma_spec`; `D/_standardized.py` → `start_run`, `residual`; E → `trace`. O score publicado é o EWMA **com sinal dos resíduos padronizados**, não uma transformação posterior por desvio-padrão próprio do EWMA. Não há divisão adicional por uma variância dependente de t ou limites de controle temporais. `lambda=0.2` e estado inicial zero são fixos; apenas `h_E` é calibrado. Não há janela finita de histórico; há um escalar recursivo por run.

Um `None` publica score/decisão nulos e **reinicia o escalar em zero**; o próximo valor válido atualiza a partir de zero. Média BASELINE zero não é por si só uma singularidade; sigma BASELINE zero/inválido rejeita a referência compartilhada. Não há estimação de sigma corrente que possa zerar durante o run. Um residual zero é válido e atualiza o estado para 0,8 do estado anterior.

### CUSUM com congelamento

\[
z_t=\frac{x_t-\mu_B}{\sigma_B},\quad S_{-1}=0,\quad
C_t=\max(0,S_{t-1}+z_t-0{,}5),\quad q_t=C_t,
\]
\[
a_t=\mathbf{1}\{C_t>h_C\},\qquad
S_t=\begin{cases}C_t,&C_t\le h_C,\\S_{t-1},&C_t>h_C.\end{cases}
\]

Evidências: `D/cusum_freeze.py` → `CUSUMFreeze.start_run`, `step`, `FreezeTransition`, `freeze_spec`; `analysis/detection/cusum_freeze_run.py` → `process_series`, `transition_rows`; E → `trace`. O score publicado é o **candidato não negativo**, inclusive quando rejeitado; não é necessariamente o estado posterior armazenado. `k=0.5`, estado inicial zero, comparação estrita e política de congelamento são fixos; só `h_C` é selecionado. Não há janela finita; o estado recursivo é um escalar limitado a `[0,h_C]` após cada transição válida.

Um `None` publica score/decisão nulos e reinicia S para zero. Média/sigma BASELINE têm os mesmos critérios do Z-score. Não há sigma local adaptativo. Outras restrições e a diferença entre congelamento e reset são detalhadas em §2.4.

### Aquecimento e casos inválidos comuns

E → `trace` processa a **série inteira desde a origem**, com estados novos por run; só depois `selected` restringe os registros usados na calibração/verificação a `[30,390)`. Assim, as primeiras 30 observações podem influenciar o estado do EWMA, do CoV e dos dois CUSUM em CAL-A/CAL-B; não entram no conjunto de scores usado pelo quantil nem no denominador dos gates. Isso difere do ajuste BASELINE, que recorta os dados antes de estimar momentos.

`analysis/detection/scientific/data.py` → `load_source` converte campo CSV vazio em `None`, exige grade científica íntegra e valida domínio. Valores não finitos, referência inconsistente, schema/identidade incompatível, grade inválida ou sequência temporal inválida são erros que interrompem o processamento. Não são convertidos silenciosamente em zero, score extremo ou decisão negativa. Evidências adicionais: `analysis/detection/inputs.py` → `number`; `D/_moments.py` → `finite_fraction`; `start_run`/`step` dos detectores.

## 2.4 CUSUM com congelamento

A unidade de processamento é uma transição acoplada ao mesmo h. O estado aceito **antes** da observação é `state.value = S_(t-1)`. O candidato `C_t` é calculado a partir dele; o score publicado e a comparação usam esse candidato. `update_accepted = not decision`; portanto o candidato é aceito **se e somente se C_t <= h**, inclusive no empate. Se C_t > h, ocorre alarme, mas `posterior_state` recebe o estado anterior. A ordem não é atualizar permanentemente e depois testar o estado preservado. Evidência: `D/cusum_freeze.py` → `step`.

```text
S = 0 no início de cada execução
para cada observação, em ordem:
    se x está ausente:
        score = null; decisão = null; S = 0
    senão:
        z = padronização com BASELINE congelada
        candidato = max(0, S + z - 0.5)
        score = candidato
        decisão = (candidato > h)
        se candidato <= h:
            S = candidato
        senão:
            S permanece igual
    avança a identidade/posição temporal da transição
```

Na observação seguinte não há uma fase de espera, trava permanente ou cooldown. Calcula-se outro candidato a partir do estado preservado; ele pode ser aceito imediatamente, reduzir o acumulado, zerá-lo pela operação `max` ou gerar novo alarme e nova rejeição. Há reset explícito na inicialização e no missing; **não há reset por alarme**. Não há fator multiplicativo de decay/amortecimento no CUSUM. A subtração fixa de k e o piso zero fazem parte da recorrência e não devem ser descritos como um decay adicional.

Exemplo documental existente, sem recomputar o detector: `A(request_starts)/calibration-candidates/candidate-0.75/transitions.csv`, run `8be2e8d414c44ff79555979d4335b5a3`, com h = `4.1861698462144926396433648224771135026908928724107`:

| Índice | Estado anterior (aproximado apenas nesta tabela) | Candidato | Aceito | Estado posterior | Decisão |
|---|---:|---:|---|---:|---|
| 147 | 4,080440394678339 | 4,836483697603035 | False | 4,080440394678339 | True |
| 148 | 4,080440394678339 | 4,093588425336512 | True | 4,093588425336512 | False |

As casas omitidas nesse exemplo estão preservadas no CSV. O alarme do índice 147 publica o candidato acima de h e a atualização retorna a ser aceita já no índice 148.

Não há argumento de ground truth, fase do ataque ou estado de emissão em `CUSUMFreeze.step`: recebe apenas observação e estado, vinculados ao detector h. O ground truth não controla o congelamento ou a retomada. Evidências: assinatura e corpo de `step`; E → `trace`; `data.py` → separação entre `load_source` e `load_truth`.

Como h determina se cada incremento entra em S, alterar h pode alterar S e, portanto, candidatos/scores de observações posteriores. Não é correto aplicar vários limiares sobre uma única trajetória já calculada do CUSUM com congelamento. Por isso E → `calibrate` executa `trace(..., 'cusum-freeze', ..., h)` separadamente para cada limiar candidato e cada execução CAL-A, desde a origem. Os arquivos `candidate-*/transitions.csv` persistem as trajetórias específicas de cada h. O relatório descreve esse mecanismo, sem concluir eliminação de persistência, superioridade ou equivalência a outra família teórica. Não se atribui a denominação Page-Hinkley.

## 2.5 Espaço de parâmetros e limiares

| Método | Fixado antes da calibração | O que CAL-A determina | Candidatos efetivamente usados |
|---|---|---|---|
| Z-score | Convenções BASELINE e cauda superior | h_Z | Um único quantil empírico por feature; não há grid de parâmetros ou varredura de limiares. |
| CoV | L=6, `ddof=1`, janela inclui corrente, reset em missing | h_CoV | Um único quantil por feature; L não varia. |
| EWMA | lambda=0.2, estado zero, normalização BASELINE, reset em missing | h_E | Um único quantil por feature; lambda não varia. |
| CUSUM com congelamento | k=0.5, estado zero, normalização BASELINE, regra acoplada e reset em missing | h_C | Onze valores por feature, obtidos da escala de referência abaixo. |

Evidências: protocolo → `components`, `h_grid`; E → `trace`, `calibrate`. Não há seleção de features por resultado TEST; as cinco features já estão declaradas no protocolo e no plano por vínculo.

Para Z-score, CoV e EWMA, E → função interna `quantile` ordena conjuntamente todos os scores **disponíveis** nas oito execuções CAL-A e no recorte `[30,390)`. Cada score válido tem peso igual. Para N scores ordenados `q_(0) <= ... <= q_(N-1)`:

\[
j=\left\lceil(N-1)(1-0{,}01)\right\rceil,\qquad h=q_{(j)}.
\]

Evidências: E → `calibrate.quantile`; `analysis/detection/empirical.py` → `quantile_index`. Trata-se da estatística de ordem superior, sem interpolação. Nesta campanha houve 2.880 decisões disponíveis por combinação em CAL-A: N=2.880 e j=2.851 (base zero) nos três métodos. Empates com h não alarmam. A escolha do quantil é agrupada por observação, enquanto a aprovação usa a média das taxas por execução (§2.6).

### Papel do CUSUM de referência

Apenas para construir a escala do grid, E processa CAL-A com `cusum-reference`, que instancia `D/cusum.py` → `CUSUM`:

\[
U_{-1}=0,\qquad U_t=\max(0,U_{t-1}+z_t-0{,}5).
\]

Esse CUSUM incorpora cada candidato no estado, sem congelamento. Usa a mesma normalização BASELINE, inicia em zero por run e reinicia em zero após missing. Seu quantil pelo mesmo j fornece `h_reference`. Define-se `scale=h_reference` se estritamente positivo; caso contrário, `scale=1`. Se não houver score de referência disponível, a calibração é rejeitada. Na campanha todos os cinco `h_reference` são positivos, logo o fallback não foi usado.

O conjunto fechado de multiplicadores é:

`[0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 8, 16]`.

Cada h é `scale * multiplier`, com contexto decimal de 50 dígitos. O grid tem os mesmos multiplicadores em todas as features, mas escala e limiares numéricos diferentes. Depende de **BASELINE pela padronização** e de **CAL-A pelo quantil do CUSUM de referência**; não depende de CAL-B ou TEST. Evidência: E → `calibrate`, `A(f)/calibration/manifest.json` → `h_reference`, `candidates`.

O CUSUM de referência **não é um quinto detector** da avaliação final: `analysis/detection/scientific/protocol.py` → `METHODS` contém quatro nomes; os 180 manifests TEST têm exatamente esses quatro métodos. Ele é uma implementação auxiliar para a escala, não uma configuração que concorre em TEST.

### Escalas e grade efetivamente persistidas

#### `request_starts`

`h_reference = 5.5815597949526568528578197633028180035878571632143`. Evidência: `A(request_starts)/calibration/manifest.json` → `h_reference`, `candidates[].{multiplier,h,eligible,trajectory}`. Cada trajetória está em `A(request_starts)/calibration-candidates/candidate-<multiplicador>/`.

| Multiplicador | h testado (literal) | Elegível em CAL-A |
|---|---|---|
| `0` | `0E-49` | Não |
| `0.25` | `1.3953899487381642132144549408257045008969642908036` | Não |
| `0.5` | `2.7907798974763284264289098816514090017939285816072` | Não |
| `0.75` | `4.1861698462144926396433648224771135026908928724107` | Sim |
| `1` | `5.5815597949526568528578197633028180035878571632143` | Sim |
| `1.5` | `8.3723396924289852792867296449542270053817857448214` | Sim |
| `2` | `11.163119589905313705715639526605636007175714326429` | Sim |
| `3` | `16.744679384857970558573459289908454010763571489643` | Sim |
| `4` | `22.326239179810627411431279053211272014351428652857` | Sim |
| `8` | `44.652478359621254822862558106422544028702857305714` | Sim |
| `16` | `89.304956719242509645725116212845088057405714611429` | Sim |
#### `mean_duration_ms`

`h_reference = 5.3970412298056553317808260144252601997241688563865`. Evidência: `A(mean_duration_ms)/calibration/manifest.json` → `h_reference`, `candidates[].{multiplier,h,eligible,trajectory}`. Cada trajetória está em `A(mean_duration_ms)/calibration-candidates/candidate-<multiplicador>/`.

| Multiplicador | h testado (literal) | Elegível em CAL-A |
|---|---|---|
| `0` | `0E-49` | Não |
| `0.25` | `1.3492603074514138329452065036063150499310422140966` | Não |
| `0.5` | `2.6985206149028276658904130072126300998620844281932` | Não |
| `0.75` | `4.0477809223542414988356195108189451497931266422899` | Sim |
| `1` | `5.3970412298056553317808260144252601997241688563865` | Sim |
| `1.5` | `8.0955618447084829976712390216378902995862532845798` | Sim |
| `2` | `10.794082459611310663561652028850520399448337712773` | Sim |
| `3` | `16.191123689416965995342478043275780599172506569160` | Sim |
| `4` | `21.588164919222621327123304057701040798896675425546` | Sim |
| `8` | `43.176329838445242654246608115402081597793350851092` | Sim |
| `16` | `86.352659676890485308493216230804163195586701702184` | Sim |
#### `ingress_packet_count`

`h_reference = 6.3378847361401747312112390920568050461955883084557`. Evidência: `A(ingress_packet_count)/calibration/manifest.json` → `h_reference`, `candidates[].{multiplier,h,eligible,trajectory}`. Cada trajetória está em `A(ingress_packet_count)/calibration-candidates/candidate-<multiplicador>/`.

| Multiplicador | h testado (literal) | Elegível em CAL-A |
|---|---|---|
| `0` | `0E-49` | Não |
| `0.25` | `1.5844711840350436828028097730142012615488970771139` | Não |
| `0.5` | `3.1689423680700873656056195460284025230977941542278` | Não |
| `0.75` | `4.7534135521051310484084293190426037846466912313418` | Sim |
| `1` | `6.3378847361401747312112390920568050461955883084557` | Sim |
| `1.5` | `9.5068271042102620968168586380852075692933824626836` | Sim |
| `2` | `12.675769472280349462422478184113610092391176616911` | Sim |
| `3` | `19.013654208420524193633717276170415138586764925367` | Sim |
| `4` | `25.351538944560698924844956368227220184782353233823` | Sim |
| `8` | `50.703077889121397849689912736454440369564706467646` | Sim |
| `16` | `101.40615577824279569937982547290888073912941293529` | Sim |
#### `ingress_tcp_payload_length_sum_bytes`

`h_reference = 5.5747172556485424936193208287997913926369615878041`. Evidência: `A(ingress_tcp_payload_length_sum_bytes)/calibration/manifest.json` → `h_reference`, `candidates[].{multiplier,h,eligible,trajectory}`. Cada trajetória está em `A(ingress_tcp_payload_length_sum_bytes)/calibration-candidates/candidate-<multiplicador>/`.

| Multiplicador | h testado (literal) | Elegível em CAL-A |
|---|---|---|
| `0` | `0E-49` | Não |
| `0.25` | `1.3936793139121356234048302071999478481592403969510` | Não |
| `0.5` | `2.7873586278242712468096604143998956963184807939020` | Não |
| `0.75` | `4.1810379417364068702144906215998435444777211908531` | Sim |
| `1` | `5.5747172556485424936193208287997913926369615878041` | Sim |
| `1.5` | `8.3620758834728137404289812431996870889554423817062` | Sim |
| `2` | `11.149434511297084987238641657599582785273923175608` | Sim |
| `3` | `16.724151766945627480857962486399374177910884763412` | Sim |
| `4` | `22.298869022594169974477283315199165570547846351216` | Sim |
| `8` | `44.597738045188339948954566630398331141095692702433` | Sim |
| `16` | `89.195476090376679897909133260796662282191385404866` | Sim |
#### `mean_cpu_percent`

`h_reference = 22.932853549879285063713564911013815877952700419856`. Evidência: `A(mean_cpu_percent)/calibration/manifest.json` → `h_reference`, `candidates[].{multiplier,h,eligible,trajectory}`. Cada trajetória está em `A(mean_cpu_percent)/calibration-candidates/candidate-<multiplicador>/`.

| Multiplicador | h testado (literal) | Elegível em CAL-A |
|---|---|---|
| `0` | `0E-48` | Não |
| `0.25` | `5.7332133874698212659283912277534539694881751049640` | Não |
| `0.5` | `11.466426774939642531856782455506907938976350209928` | Sim |
| `0.75` | `17.199640162409463797785173683260361908464525314892` | Sim |
| `1` | `22.932853549879285063713564911013815877952700419856` | Sim |
| `1.5` | `34.399280324818927595570347366520723816929050629784` | Sim |
| `2` | `45.865707099758570127427129822027631755905400839712` | Sim |
| `3` | `68.798560649637855191140694733041447633858101259568` | Sim |
| `4` | `91.731414199517140254854259644055263511810801679424` | Sim |
| `8` | `183.46282839903428050970851928811052702362160335885` | Sim |
| `16` | `366.92565679806856101941703857622105404724320671770` | Sim |

A notação `0E-49`/`0E-48` preserva o literal JSON e equivale numericamente a zero. A escolha final foi multiplicador **0,75** para request_starts, mean_duration_ms, ingress_packet_count e ingress_tcp_payload_length_sum_bytes; **0,5** para mean_cpu_percent. Os limiares finais dos outros três métodos estão na tabela de §2.8.

## 2.6 Seleção em CAL-A

E → `adherence` calcula separadamente, por execução e combinação detector-feature, no recorte de 360 janelas:

\[
A_r=\#\{t:\operatorname{decisão}_{rt}\ne null\},\qquad
v_r=A_r/360,\qquad
f_r=\frac{\#\{t:\operatorname{decisão}_{rt}=True\}}{A_r}.
\]

Se A_r=0, f_r é `None`. Como CAL-A é controle benigno, os alarmes disponíveis são os falsos alarmes usados nesse gate; não é necessário fornecer rótulos ao detector. A fração de disponibilidade usa **todas as 360 esperadas** no denominador. A taxa de falsos alarmes usa somente decisões disponíveis. Janelas indisponíveis são contadas e excluídas do denominador dessa taxa; execuções indisponíveis não são simplesmente descartadas para melhorar a média.

E → `eligible` exige simultaneamente:

1. Uma taxa definida para **todas as oito execuções**;
2. Disponibilidade `v_r >= 0.95` **em cada execução** (pelo menos 342/360);
3. Média aritmética das oito taxas `sum(f_r)/8 <= 0.01`;
4. Máximo individual `max(f_r) <= 0.05`.

Os limites são inclusivos. Os 1% não são a fração de runs com qualquer alarme, nem uma média das cinco features/quatro métodos. O limite de 5% também é uma taxa por execução, não cinco alarmes ou cinco execuções. Quando há 360 decisões, corresponde a no máximo 18 alarmes na execução; com menos decisões disponíveis, aplica-se a taxa sobre o respectivo A_r.

A sequência real de seleção é:

1. Validar fontes CAL-A, autoridade, feature e separação de run IDs/seeds de BASELINE; carregar a referência congelada.
2. Obter **um** h por quantil para Z-score, CoV e EWMA; derivar decisões estritas e seus diagnósticos por run. Não tentar quantis alternativos para corrigir uma reprovação.
3. Obter h_reference do CUSUM auxiliar; avaliar as onze trajetórias completas do CUSUM com congelamento, persistindo suporte e elegibilidade de cada h, inclusive os rejeitados.
4. Entre os h do CUSUM que passam os quatro critérios, selecionar **`min(candidates)`**, ou seja, o menor h elegível. Não minimizar a taxa observada, maximizar disponibilidade nem usar desempenho ofensivo para ordenar os elegíveis. Não há desempate adicional: valores iguais de h resultariam na mesma configuração.
5. Definir `calibration.eligible` como existência de h elegível para CUSUM **e** aprovação dos diagnósticos de todos os outros três métodos. Assim, a liberação é conjunta por feature; não se escolhe outro detector para substituir um reprovado.

Evidência: E → `calibrate`, especialmente `candidates`, `thresholds['cusum-freeze']=min(...)`, `primary_ok`; protocolo → `no_candidate`, `secondary_failure`; runner → `run_partition`.

Sem candidato CUSUM elegível, seu limiar fica nulo; se qualquer um dos três outros gates falha, a feature também fica inelegível. O manifesto registra `NO_ELIGIBLE_THRESHOLD_OR_CAL_A_SUPPORT`. O caso de modelo secundário indisponível gera `SECONDARY_BASELINE_UNAVAILABLE`; ausência de scores de referência gera `NO_AVAILABLE_CALIBRATION_SCORES`. Não há extensão automática da grade.

Para a feature primária `request_starts`, a rejeição é persistida como `ANALYSIS_REJECTED` e interrompe o avanço, sem repetição ou retuning sob a mesma autoridade. Para features secundárias, o código preserva a feature predeclarada como **não avaliada**, sem retuning ou substituição. Essa distinção é mais precisa que dizer que toda reprovação de qualquer feature encerra obrigatoriamente toda a campanha.

Na execução final, as cinco calibrações têm `eligible=true`; todos os métodos tiveram 360/360 decisões em cada run CAL-A no horizonte usado. Os valores finais e os candidatos mostram que vários h CUSUM eram elegíveis; foi escolhido o menor, conforme a regra, e não o que apresentava menos alarmes.

## 2.7 Verificação em CAL-B

E → `process` aplica a cada fonte CAL-B os mesmos parâmetros BASELINE e os mesmos limiares de `calibration.thresholds`, com estado temporal novo por execução. E → `verify` obtém os registros correspondentes às oito fontes CAL-B e executa o mesmo cálculo `adherence`.

A aprovação exige, por método:

- Todas as oito taxas definidas;
- Disponibilidade mínima **95% por execução**;
- Média aritmética das taxas por execução **até 2%**, inclusive;
- Máximo por execução **até 5%**, inclusive.

Evidências: E → `verify`, `verification_metadata`, `eligible`; `A(f)/verification/manifest.json` → `support`, `method_accepted`, `approved`. Os 2% são uma **tolerância de verificação independente**, não um novo alvo de quantil ou uma segunda calibração. CAL-B não constrói grid, não escolhe outro candidato, não recalcula h e não altera média/sigma, L, lambda ou k. A decisão `approved` é a conjunção das quatro aprovações, por feature. Não há critério adicional de seleção: estatísticas descritivas eventualmente presentes no manifesto não alimentam `eligible`.

Se falha qualquer método da feature primária, `run_partition` registra rejeição e interrompe, com mensagem explícita de ausência de retuning, substituição ou TEST. Não há retorno a CAL-A nem tentativa do próximo h elegível. Para secundárias reprovadas, `process` usa `unavailable_traces`, preservando a feature como não avaliada. O campo `failure_policy` guarda a política declarada; sua aplicação operacional distingue primária e secundárias. Evidências: E → `verify`, `process`, `unavailable_traces`; runner → `run_partition`; protocolo → `cal_b_failure`, `secondary_failure`.

No conjunto efetivo, **20/20 combinações passaram**: os cinco manifests têm `approved=true`, os quatro valores de `method_accepted` são verdadeiros em cada um e todos os suportes têm 360/360 decisões por run. Portanto, nenhum desses ramos de reprovação ou retuning foi acionado na campanha final.

O checkpoint CAL-B foi publicado antes da primeira tentativa TEST. As configurações numéricas já eram imutáveis desde CAL-A; CAL-B forneceu a aceitação e o vínculo necessário para sua liberação definitiva a TEST (§2.10).

## 2.8 Configurações congeladas finais

As próximas linhas são transcritas dos manifests originais, conferidos contra as referências dos **36 artefatos TEST de cada feature**. Não se usaram valores default para preencher parâmetros. Notação: **B(f)** significa os momentos e convenções exatos de `A(f)/baseline/manifest.json` → `parameters`, apresentados em §2.2; **C(f)** significa `A(f)/calibration/manifest.json` → `thresholds`; **V(f)** significa `A(f)/verification/manifest.json` → `approved`, `method_accepted`. Todos esses caminhos são alcançados pelos respectivos checkpoints.

| Detector | Feature | Parâmetros fixos | Parâmetros selecionados | Limiar final (literal) | Referência/estado de BASELINE | Evidência |
|---|---|---|---|---|---|---|
| Z-score | `request_starts` | `ddof=1`; score com sinal; `>` | Somente h (quantil 0,99) | `2.4942020900355666831699134911877789299516876780782` | B(request_starts); sem herdar estado temporal | C(request_starts) → `thresholds.zscore`; V(request_starts); `A(request_starts)/TEST/*/manifest.json` → `components` |
| CoV | `request_starts` | `L=6`, `ddof=1`; inclui corrente; `>` | Somente h (quantil 0,99) | `0.44020197384584474143454651345384011981622158951587` | Sem referência estática; deque vazia por run | C(request_starts) → `thresholds.cov`; V(request_starts); `A(request_starts)/TEST/*/manifest.json` → `components` |
| EWMA | `request_starts` | `lambda=0.2`, `E_inicial=0`; `>` | Somente h (quantil 0,99) | `0.82184252009581843527280039729381922348026907952272` | B(request_starts); sem herdar estado temporal | C(request_starts) → `thresholds.ewma`; V(request_starts); `A(request_starts)/TEST/*/manifest.json` → `components` |
| CUSUM com congelamento | `request_starts` | `k=0.5`, `S_inicial=0`; publica candidato; `>` | h; multiplicador 0.75 | `4.1861698462144926396433648224771135026908928724107` | B(request_starts); sem herdar estado temporal | C(request_starts) → `thresholds.cusum-freeze`; V(request_starts); `A(request_starts)/TEST/*/manifest.json` → `components` |
| Z-score | `mean_duration_ms` | `ddof=1`; score com sinal; `>` | Somente h (quantil 0,99) | `2.1094783961845080703403979673909053506528569394976` | B(mean_duration_ms); sem herdar estado temporal | C(mean_duration_ms) → `thresholds.zscore`; V(mean_duration_ms); `A(mean_duration_ms)/TEST/*/manifest.json` → `components` |
| CoV | `mean_duration_ms` | `L=6`, `ddof=1`; inclui corrente; `>` | Somente h (quantil 0,99) | `0.29368628522741678887284617825734779536663446046100` | Sem referência estática; deque vazia por run | C(mean_duration_ms) → `thresholds.cov`; V(mean_duration_ms); `A(mean_duration_ms)/TEST/*/manifest.json` → `components` |
| EWMA | `mean_duration_ms` | `lambda=0.2`, `E_inicial=0`; `>` | Somente h (quantil 0,99) | `0.82485080672580389434373034538984648535796274525796` | B(mean_duration_ms); sem herdar estado temporal | C(mean_duration_ms) → `thresholds.ewma`; V(mean_duration_ms); `A(mean_duration_ms)/TEST/*/manifest.json` → `components` |
| CUSUM com congelamento | `mean_duration_ms` | `k=0.5`, `S_inicial=0`; publica candidato; `>` | h; multiplicador 0.75 | `4.0477809223542414988356195108189451497931266422899` | B(mean_duration_ms); sem herdar estado temporal | C(mean_duration_ms) → `thresholds.cusum-freeze`; V(mean_duration_ms); `A(mean_duration_ms)/TEST/*/manifest.json` → `components` |
| Z-score | `ingress_packet_count` | `ddof=1`; score com sinal; `>` | Somente h (quantil 0,99) | `2.5438355886237048130356729816607110859730634016742` | B(ingress_packet_count); sem herdar estado temporal | C(ingress_packet_count) → `thresholds.zscore`; V(ingress_packet_count); `A(ingress_packet_count)/TEST/*/manifest.json` → `components` |
| CoV | `ingress_packet_count` | `L=6`, `ddof=1`; inclui corrente; `>` | Somente h (quantil 0,99) | `0.46079985260600100079608569657859004721894552405793` | Sem referência estática; deque vazia por run | C(ingress_packet_count) → `thresholds.cov`; V(ingress_packet_count); `A(ingress_packet_count)/TEST/*/manifest.json` → `components` |
| EWMA | `ingress_packet_count` | `lambda=0.2`, `E_inicial=0`; `>` | Somente h (quantil 0,99) | `0.86399411324763987844351295623461228962136549040651` | B(ingress_packet_count); sem herdar estado temporal | C(ingress_packet_count) → `thresholds.ewma`; V(ingress_packet_count); `A(ingress_packet_count)/TEST/*/manifest.json` → `components` |
| CUSUM com congelamento | `ingress_packet_count` | `k=0.5`, `S_inicial=0`; publica candidato; `>` | h; multiplicador 0.75 | `4.7534135521051310484084293190426037846466912313418` | B(ingress_packet_count); sem herdar estado temporal | C(ingress_packet_count) → `thresholds.cusum-freeze`; V(ingress_packet_count); `A(ingress_packet_count)/TEST/*/manifest.json` → `components` |
| Z-score | `ingress_tcp_payload_length_sum_bytes` | `ddof=1`; score com sinal; `>` | Somente h (quantil 0,99) | `2.4933522219970410043797923314800316362849086359313` | B(ingress_tcp_payload_length_sum_bytes); sem herdar estado temporal | C(ingress_tcp_payload_length_sum_bytes) → `thresholds.zscore`; V(ingress_tcp_payload_length_sum_bytes); `A(ingress_tcp_payload_length_sum_bytes)/TEST/*/manifest.json` → `components` |
| CoV | `ingress_tcp_payload_length_sum_bytes` | `L=6`, `ddof=1`; inclui corrente; `>` | Somente h (quantil 0,99) | `0.44020197384584474143454651345384011981622158951588` | Sem referência estática; deque vazia por run | C(ingress_tcp_payload_length_sum_bytes) → `thresholds.cov`; V(ingress_tcp_payload_length_sum_bytes); `A(ingress_tcp_payload_length_sum_bytes)/TEST/*/manifest.json` → `components` |
| EWMA | `ingress_tcp_payload_length_sum_bytes` | `lambda=0.2`, `E_inicial=0`; `>` | Somente h (quantil 0,99) | `0.82466447268624497843620278070622583381989337165747` | B(ingress_tcp_payload_length_sum_bytes); sem herdar estado temporal | C(ingress_tcp_payload_length_sum_bytes) → `thresholds.ewma`; V(ingress_tcp_payload_length_sum_bytes); `A(ingress_tcp_payload_length_sum_bytes)/TEST/*/manifest.json` → `components` |
| CUSUM com congelamento | `ingress_tcp_payload_length_sum_bytes` | `k=0.5`, `S_inicial=0`; publica candidato; `>` | h; multiplicador 0.75 | `4.1810379417364068702144906215998435444777211908531` | B(ingress_tcp_payload_length_sum_bytes); sem herdar estado temporal | C(ingress_tcp_payload_length_sum_bytes) → `thresholds.cusum-freeze`; V(ingress_tcp_payload_length_sum_bytes); `A(ingress_tcp_payload_length_sum_bytes)/TEST/*/manifest.json` → `components` |
| Z-score | `mean_cpu_percent` | `ddof=1`; score com sinal; `>` | Somente h (quantil 0,99) | `2.5216858495483782033932651178999064813134306404073` | B(mean_cpu_percent); sem herdar estado temporal | C(mean_cpu_percent) → `thresholds.zscore`; V(mean_cpu_percent); `A(mean_cpu_percent)/TEST/*/manifest.json` → `components` |
| CoV | `mean_cpu_percent` | `L=6`, `ddof=1`; inclui corrente; `>` | Somente h (quantil 0,99) | `0.47630396497758366193134151234160175807132760720142` | Sem referência estática; deque vazia por run | C(mean_cpu_percent) → `thresholds.cov`; V(mean_cpu_percent); `A(mean_cpu_percent)/TEST/*/manifest.json` → `components` |
| EWMA | `mean_cpu_percent` | `lambda=0.2`, `E_inicial=0`; `>` | Somente h (quantil 0,99) | `1.3501093932566738364805615359642204654611732717045` | B(mean_cpu_percent); sem herdar estado temporal | C(mean_cpu_percent) → `thresholds.ewma`; V(mean_cpu_percent); `A(mean_cpu_percent)/TEST/*/manifest.json` → `components` |
| CUSUM com congelamento | `mean_cpu_percent` | `k=0.5`, `S_inicial=0`; publica candidato; `>` | h; multiplicador 0.5 | `11.466426774939642531856782455506907938976350209928` | B(mean_cpu_percent); sem herdar estado temporal | C(mean_cpu_percent) → `thresholds.cusum-freeze`; V(mean_cpu_percent); `A(mean_cpu_percent)/TEST/*/manifest.json` → `components` |

Convenções comuns da tabela: precisão decimal 50 e `ROUND_HALF_EVEN`; missing conforme §2.9; momentos e normalização não adaptativos. `h` do CUSUM também aparece em `components.cusum-freeze.config.h`; os demais h são lidos do manifesto CAL-A referenciado pelo run, não de uma busca em TEST. As configurações de `cov`, `ewma` e `zscore` são registradas em `components` dos runs. A referência BASELINE do CoV é uma dependência do fluxo de elegibilidade da feature, não um parâmetro passado a `CoV.start_run`.

### Suporte observado na seleção e na verificação

A tabela resume somente **CAL-A/CAL-B**, sem métricas TEST. Cada célula numérica é percentual, arredondado aqui a seis casas; as taxas decimais por execução permanecem nos manifests. Para CUSUM, CAL-A usa `candidates` do h selecionado; para os demais, `diagnostics`.

| Feature | Método | Média CAL-A (%) | Máximo CAL-A (%) | Média CAL-B (%) | Máximo CAL-B (%) | Disponibilidade mínima A/B |
|---|---|---:|---:|---:|---:|---|
| `request_starts` | Z-score | 0.937500 | 1.388889 | 1.006944 | 1.944444 | 360/360 em cada run |
| `request_starts` | CoV | 0.972222 | 1.944444 | 1.423611 | 3.333333 | 360/360 em cada run |
| `request_starts` | EWMA | 0.972222 | 2.222222 | 1.284722 | 2.777778 | 360/360 em cada run |
| `request_starts` | CUSUM com congelamento | 0.520833 | 1.666667 | 0.833333 | 2.222222 | 360/360 em cada run |
| `mean_duration_ms` | Z-score | 0.972222 | 2.222222 | 0.937500 | 1.666667 | 360/360 em cada run |
| `mean_duration_ms` | CoV | 0.972222 | 1.944444 | 1.076389 | 2.777778 | 360/360 em cada run |
| `mean_duration_ms` | EWMA | 0.972222 | 4.444444 | 0.416667 | 1.388889 | 360/360 em cada run |
| `mean_duration_ms` | CUSUM com congelamento | 0.659722 | 2.777778 | 0.208333 | 0.555556 | 360/360 em cada run |
| `ingress_packet_count` | Z-score | 0.798611 | 1.388889 | 1.180556 | 2.500000 | 360/360 em cada run |
| `ingress_packet_count` | CoV | 0.972222 | 1.944444 | 1.527778 | 3.333333 | 360/360 em cada run |
| `ingress_packet_count` | EWMA | 0.972222 | 2.500000 | 1.250000 | 3.333333 | 360/360 em cada run |
| `ingress_packet_count` | CUSUM com congelamento | 0.347222 | 1.666667 | 0.694444 | 1.944444 | 360/360 em cada run |
| `ingress_tcp_payload_length_sum_bytes` | Z-score | 0.972222 | 1.666667 | 1.006944 | 1.944444 | 360/360 em cada run |
| `ingress_tcp_payload_length_sum_bytes` | CoV | 0.972222 | 1.944444 | 1.423611 | 3.333333 | 360/360 em cada run |
| `ingress_tcp_payload_length_sum_bytes` | EWMA | 0.972222 | 2.222222 | 1.284722 | 2.777778 | 360/360 em cada run |
| `ingress_tcp_payload_length_sum_bytes` | CUSUM com congelamento | 0.520833 | 1.666667 | 0.833333 | 2.222222 | 360/360 em cada run |
| `mean_cpu_percent` | Z-score | 0.937500 | 1.666667 | 0.833333 | 2.777778 | 360/360 em cada run |
| `mean_cpu_percent` | CoV | 0.972222 | 1.944444 | 1.215278 | 2.777778 | 360/360 em cada run |
| `mean_cpu_percent` | EWMA | 0.972222 | 4.444444 | 0.069444 | 0.277778 | 360/360 em cada run |
| `mean_cpu_percent` | CUSUM com congelamento | 0.451389 | 3.055556 | 0.000000 | 0.000000 | 360/360 em cada run |

Evidência: `A(f)/calibration/manifest.json` → `diagnostics` ou `candidates[...].support`; `A(f)/verification/manifest.json` → `support`, `method_accepted`. Esta síntese aritmética lê taxas existentes e não executa calibração novamente.

## 2.9 Tratamento de indisponibilidade

| Situação | Z-score | CoV | EWMA | CUSUM com congelamento |
|---|---|---|---|---|
| Feature `None` | Score/decisão nulos; referência preservada. | Score/decisão nulos; limpa histórico. | Score/decisão nulos; acumulado vai a zero. | Candidato/score/decisão/aceitação nulos; estado vai a zero. |
| Valores seguintes ao missing | Primeiro válido já tem score. | Precisa completar seis válidos consecutivos. | Primeiro válido já atualiza a partir de zero. | Primeiro válido já calcula candidato a partir de zero. |
| Inicialização | Carrega normalização estática. | Deque vazia; cinco válidos sem score. | Estado zero; primeiro válido tem score. | Estado zero; primeiro válido tem score. |
| Média local zero | Sem média local móvel. | Indisponível; mantém deque atualizada. | Sem média local móvel. | Sem média local móvel. |
| Sigma BASELINE zero/inválido | Rejeita modelo. | Não usa sigma BASELINE numericamente; porém a feature fica inelegível pelo gate científico compartilhado. | Rejeita referência compartilhada. | Rejeita referência compartilhada. |
| Sigma local zero com média não nula | Não estima sigma local. | Score zero válido. | Não estima sigma local. | Não estima sigma local. |
| Score igual ao limiar | Decisão False válida. | Decisão False válida. | Decisão False válida. | Decisão False válida, candidato aceito. |

Evidências: `D/zscore.py` → `fit`, `start_run`, `update`; `D/cov.py` → `update`; `D/_standardized.py` → `residual`; `D/ewma.py` → `update`; `D/cusum_freeze.py` → `step`; E → `fit`, `calibrate`, `process`.

É necessário distinguir quatro situações:

1. **Feature ausente:** `observation.value=None`, por campo vazio ou por ausência de suporte direcional da fonte de rede reconhecida em `load_source`. O zero numérico não é missing.
2. **Score matematicamente indisponível:** por exemplo, média zero no CoV; também há indisponibilidade operacional por aquecimento do histórico. A feature pode estar presente nesses casos.
3. **Ausência de decisão:** E → `trace` usa `None` quando score é nulo ou h é nulo. No CUSUM o score e a decisão são produzidos juntos pela transição; missing torna ambos nulos. A falta de h válido no fluxo científico leva à inelegibilidade, e não a uma decisão negativa artificial.
4. **Decisão negativa válida:** score disponível e comparação `score > h` falsa. Ela conta no denominador de disponibilidade e da taxa por execução; não equivale a `None`.

Para uma secundária cientificamente inelegível, E → `unavailable_traces` produz score/decisão nulos para todos os métodos, com motivo `secondary_not_scientifically_calibrated`. Não é um comportamento intrínseco da fórmula CoV ou EWMA, mas do gate de preparação da feature.

Disponibilidade em CAL-A/CAL-B é `n_decisões_não_nulas/360`, por execução e método, com exigência de pelo menos 95% em **cada run**; não uma média de disponibilidade entre execuções. Um run sem decisões tem taxa indefinida e reprova. As taxas de falsos alarmes excluem as decisões nulas do denominador, mas o gate de disponibilidade impede ignorá-las sem limite. As contagens reais no recorte são 360 disponíveis e zero indisponíveis para todas as combinações em A e B. Os cinco scores iniciais indisponíveis do CoV ocorrem antes do recorte quando não há missing posterior; não reduzem automaticamente esse suporte de 360.

Metadados temporais continuam avançando nos métodos com estado mesmo diante de missing; o reset numérico não reinicia o identificador da execução nem permite reordenar observações. `Component.missing='preserve'` significa que a representação de ausência é preservada no contrato; não significa que todo acumulado numérico seja preservado diante de `None`.

## 2.10 Ausência de vazamento de TEST

### Fluxo direto e vínculos efetivamente conferidos

| Operação | Entradas numéricas utilizadas | Barreiras e evidência |
|---|---|---|
| Estimar referências | Somente quatro BASELINE, recorte 30:390 | E → `fit`, `check_sources`; modelos → `sources[].partition=BASELINE`. |
| Calcular h de Z/CoV/EWMA | Somente oito CAL-A, scores disponíveis selecionados | E → `calibrate.quantile`; calibração → `sources[].partition=CAL_A`, `baseline`. |
| Construir grid CUSUM | Referência BASELINE e quantil do CUSUM auxiliar em CAL-A | E → `calibrate`; protocolo → `h_grid`; candidatos → `sources`, `baseline`, `h`. |
| Selecionar h CUSUM | Suportes das trajetórias CAL-A de cada h | E → `eligible`, `calibrate`; candidatos congelados. |
| Verificar | Somente oito CAL-B com h já selecionado | E → `verify`; verificação → `calibration`, `sources[].partition=CAL_B`. |
| Aplicar em TEST | Série TEST mais modelo/calibração/verificação já referenciados | E → `process`; runs → `baseline`, `calibration`, `verification`, `components`; não há chamada de `fit`/`calibrate` nessa etapa. |

Foram conferidos, para cada feature, os 20 run IDs e seeds de BASELINE/CAL-A/CAL-B, sem sobreposição entre essas fontes, e a exclusão de todos os run IDs/seeds TEST dessas fontes de preparação. Cada um dos 180 manifests TEST aponta exatamente o modelo BASELINE, a calibração CAL-A e a verificação CAL-B alcançados pelos checkpoints finais. A referência de liberação de cada fonte TEST é o checkpoint CAL-B. Não há um segundo conjunto de limiares derivado de TEST nos artefatos usados.

### Ordem registrada antes da coleta TEST

| Etapa | Journal | UTC da conclusão | SHA256 do checkpoint |
|---|---|---|---|
| BASELINE | `R/journal/000016.json` | 30/10/2026 00:09:32.525253 | `389a6676d9966a2ec0c93269d0926081b16009a469877dc0a92bd83aee850118` |
| CAL-A | `R/journal/000041.json` | 30/10/2026 01:14:26.234124 | `2b0fbb2bed70548705d3d4f188e416e3ff6c104d4773556ee12a05a00d07654e` |
| CAL-B | `R/journal/000066.json` | 30/10/2026 02:19:18.833584 | `f0c343a50fa1283d12a0768ccb1b647a044daf128dbb8950d3e1bb5f98774330` |
| TEST | `R/journal/000174.json` | 30/10/2026 07:07:48.022375 | `690c7d9af50204d7170fbb08ee61dd672450d2d5dd7e8c0a1de9725669601912` |

A primeira tentativa TEST consta de `R/journal/000067.json`, em **30/10/2026 02:20:53.383270 UTC**, depois da conclusão CAL-B. A cadeia `previous_sha256` do journal foi conferida nesta investigação. Os checkpoints, por sua vez, vinculam o anterior em `previous_checkpoint`.

### Dependências indiretas

O runner exige ordem das partições e o hash do checkpoint predecessor imediato; o leitor de fontes TEST exige uma liberação CAL-B cuja verificação primária aprovou os quatro métodos. `check_authority` e os leitores de metadados conferem o código congelado e os hashes; mudanças posteriores não são incorporadas silenciosamente. `artifact` recusa reaproveitar um destino cujo conteúdo determinístico difira. Evidências: runner → `run_partition`; E → `check_authority`, `artifact`, `model_metadata`, `calibration_metadata`, `verification_metadata`; `data.py` → `validate_test_release`, `validate_membership`.

O plano inclui configurações e seeds TEST prospectivas, mas essas informações de inventário não são valores observados usados para estimar média/sigma ou limiares. A auditoria histórica de seeds em `protocol.py` → `load_plan` percorre arquivos anteriores para impedir reutilização de seeds; ela não lê suas séries para ajustar os detectores. `load_source` oferece ao motor séries escalares sem rótulos de ataque; `load_truth` é chamado no caminho de avaliação posterior ao processamento, sem alterar sua configuração.

**Conclusão documental:** no fluxo implementado e nos artefatos congelados examinados, TEST ficou fora da estimação de referências, construção do grid, seleção de parâmetros/limiares e alteração após CAL-B. A evidência sustenta essa ausência no encadeamento do repositório. Hashes e journal não permitem provar, isoladamente, a inexistência de decisões humanas ou execuções externas não registradas; não se atribui a essa conferência uma certificação sobre atividades fora dos arquivos existentes.

## Respostas consolidadas para a metodologia

1. **Partições e suas funções.** Foram usadas 4 execuções BASELINE para referência estática, 8 CAL-A para seleção dos limiares, 8 CAL-B para verificação independente e 36 TEST para aplicação final. As fontes aceitas são distintas; a substituição técnica do primeiro slot BASELINE não acrescentou uma quinta fonte de ajuste. Evidências: plano → `entries`; quatro checkpoints → `receipts`; E → `check_sources`.
2. **Construção das referências.** Para cada feature, concatenaram-se os valores válidos das quatro BASELINE nas 360 janelas de `[30,390)` por run. Estimaram-se média e variância amostral (`ddof=1`) com peso igual por observação; sigma foi obtido da raiz da variância. Houve 1.440 valores válidos e zero ausentes por feature. Momentos exatos e sigma permaneceram congelados. CoV não usa essa referência na sua fórmula, embora participe do gate científico compartilhado. Evidências: E → `fit`; `ZScore.fit`; `A(f)/baseline/manifest.json` → `parameters`.
3. **Configuração de Z-score.** Score com sinal `(x-mu_B)/sigma_B`, sem módulo ou janela móvel; decisão estrita na cauda superior. Só o limiar por feature foi calibrado em CAL-A. Evidências: `ZScore.update`; E → `trace`, `calibrate`.
4. **Configuração de CoV.** Sigma amostral dividido pela média das últimas seis observações consecutivas válidas, incluindo a corrente; `L=6` fixo. Só o limiar por feature foi calibrado. Histórico começa vazio, missing o limpa e média zero torna o score indisponível. Evidências: `CoV.start_run`, `CoV.update`; E → `trace`.
5. **Configuração de EWMA.** Recorrência `E_t=0.2*z_t+0.8*E_(t-1)` sobre resíduos da referência congelada, estado inicial zero e score com sinal. Lambda foi fixado, e só o limiar por feature foi calibrado. Missing reinicia o acumulado em zero. Evidências: `EWMA.update`; `_standardized.py` → `residual`.
6. **Configuração do CUSUM com congelamento.** Candidato `max(0,S_anterior+z_t-0.5)`, publicado como score; alarme se candidato > h. Só candidatos <= h entram no estado; candidatos acima preservam o estado anterior. O próximo valor é processado normalmente. Não há reset por alarme, decay adicional ou interferência do ground truth. Missing reinicia o estado em zero. Evidência: `CUSUMFreeze.step`.
7. **Calibração em CAL-A.** Z-score/CoV/EWMA usam um único quantil empírico superior de nível 0,99 dos scores disponíveis agrupados; CUSUM usa onze multiplicadores de uma escala obtida pelo CUSUM auxiliar sem congelamento em CAL-A, com replay completo por h. Seleciona-se o menor h elegível. Critérios: média das taxas por run <=1%, máximo por run <=5% e disponibilidade >=95% por run, com todas as taxas definidas. O CUSUM auxiliar não integra os quatro métodos finais. Evidências: E → `calibrate`, `adherence`, `eligible`; protocolo → `h_grid`.
8. **Verificação em CAL-B.** Aplicam-se os limiares selecionados, sem alteração, com tolerância de média por run <=2%, máximo <=5% e disponibilidade >=95% em cada execução. Os 2% não constituem novo alvo de calibração. As 20 combinações passaram. Não há retorno a CAL-A ou escolha do próximo candidato depois de observar B; reprovação primária bloqueia TEST, e secundárias inelegíveis permanecem não avaliadas. Evidências: E → `verify`, `process`; runner → `run_partition`; verificação → `method_accepted`, `approved`.
9. **Congelamento antes de TEST.** Parâmetros de forma e código foram fixados pelo protocolo/plano; referências no checkpoint BASELINE; limiares ao concluir CAL-A; liberação definitiva no checkpoint CAL-B. Todos os 180 manifests de aplicação TEST vinculam esses mesmos artefatos. Código atual coincide com os hashes congelados. Evidências: `plan.runtime_hashes`; checkpoints; `A(f)/TEST/*/manifest.json` → referências e `components`.
10. **Tratamento de indisponibilidade.** Ausência da feature, score indefinido, ausência de decisão e decisão negativa válida são situações distintas. Missing preserva a referência Z-score, limpa o histórico CoV e zera os estados EWMA/CUSUM; sigma BASELINE zero rejeita o modelo, sem epsilon. A disponibilidade de A/B usa decisões não nulas sobre 360 janelas esperadas e deve passar por run; a taxa de alarmes usa apenas decisões disponíveis. Toda série é processada desde a origem antes de selecionar os scores/janelas de A/B. Evidências: detectores → `update`/`step`; E → `trace`, `selected`, `adherence`.

### Pontos que permaneceram não determinados

- A inexistência de eventual influência humana, execução ou seleção realizada fora do repositório e sem registro não pode ser comprovada por estes arquivos. Dentro do fluxo e da cadeia de artefatos examinados, não foi encontrada utilização direta ou indireta de dados TEST para preparar ou alterar as configurações.

Não permaneceram lacunas nos valores finais dos vinte limiares, nas referências usadas, nos parâmetros fixos, nas regras de seleção/verificação ou nas políticas de indisponibilidade implementadas.
