# Etapa 12A — Z-score assinado e CoV local

Somente dois métodos de **score**, integrados aos contratos existentes da Etapa 11. Nenhum método retorna ataque/normal. Não há threshold, calibração estatística, escolha ótima de memória, normalização adicional, imputação, remoção de outliers, Shannon ou campanha nova. Implementação correta não constitui evidência de eficácia contra LDoS.

## Convenção de desvio padrão

Adotamos **desvio amostral, ddof=1**, de forma explícita, fixa e versionada nos dois métodos:

\[
\bar{x}=\frac{1}{n}\sum_{i=1}^{n}x_i,\qquad
s^2=\frac{1}{n-1}\sum_{i=1}^{n}(x_i-\bar{x})^2,\qquad s=\sqrt{s^2}.
\]

O baseline é uma amostra finita do comportamento normal que queremos estimar, não toda a população de tráfego possível. A convenção ddof=0 descreveria a dispersão da população empírica observada; a versão ddof=1 é mais adequada à estimação adotada aqui. Para CoV usamos a definição de **CoV amostral**, interpretando o histórico como amostra local do processo. A correção n−1 elimina o viés da variância sob amostragem iid com variância finita; não torna o desvio ou a razão s/média estimadores sem viés. Autocorrelação e não estacionariedade quebram a interpretação iid: ddof=1 não as corrige.

As definições estão em [NIST — Measures of Scale](https://www.itl.nist.gov/div898/handbook/eda/section3/eda356.htm) e [NIST — Coefficient of Variation](https://itl.nist.gov/div898/software/dataplot/refman2/auxillar/coefvari.htm). Não foi uma escolha baseada no default de biblioteca. Os testes diferenciam explicitamente as convenções e recusam config ddof=0 nesta versão; uma variante populacional futura deverá ser identificada separadamente.

## Z-score

Implementação: `analysis/detection/detectors/zscore.py`, classe `ZScore`, spec `zscore_spec()`, versão 1.

Para B composto por observações válidas designadas baseline:

\[
\mu_B=\frac{1}{n_B}\sum_{x\in B}x,\quad
\sigma_B=\sqrt{\frac{\sum_{x\in B}(x-\mu_B)^2}{n_B-1}},\quad
z_t=\frac{x_t-\mu_B}{\sigma_B}.
\]

A mesma classe satisfaz Fitter e Detector; isso é opcional na Etapa 11. `fit` recebe tuple de ObservedSeries, `start_run` recebe os parâmetros persistidos e `update` recebe uma Observation. Nunca recebe labels, caminhos de ground truth ou configuração de ataque. O fitting não consulta o run a pontuar.

Baseline deve ser normal por desenho e comparável em feature/Δ/schema/cenário/operação. O framework verifica identidade de feature/Δ, hashes e separação por run; não certifica sozinho comparabilidade de cenário ou normalidade. A versão inicial pondera **igualmente cada observação**, inclusive entre runs de comprimentos diferentes; não calcula média de médias de runs e não inventa adjacência entre execuções. Guardamos suporte por run para auditar esse peso. Baselines científicos futuros exigirão desenho/ponderação aprovados.

Nulls do baseline são **excluídos explicitamente e contados** (`baseline_missing=exclude_and_count`). Não recebem substituto; n_valid, n_missing e support_by_run são persistidos. Isso não declara missing at random ou recuperação de informação faltante. Se n_valid<2, fitting é recusado. Se σ_B=0, fitting é recusado como `zero_baseline_sigma`, sem publicar modelo. Não existe epsilon. O scorer também valida consistência dos parâmetros e recusa baseline ausente, σ não positivo ou parâmetros incompatíveis.

Null na observação produz score ausente e `missing_observation`, sem alterar o modelo aprendido. Score disponível permanece assinado: positivo acima da média, negativo abaixo, zero igual. Não há |z|, cauda preferida ou threshold embutido. A fórmula não implica que z siga N(0,1); parâmetros estimados, séries discretas, dependência temporal e cache afetam interpretação estatística. Não produz p-value.

Config persistida: ddof, regras de missing e σ=0, ponderação, precisão e arredondamento. Artefato baseline da Etapa 11 inclui feature, fontes/IDs/hashes, config/proveniência e parameters com `mu`, `sigma`, `n_valid`, `n_missing`, `support_by_run`, `ddof`. Também guarda média e variância exatas como numerador/denominador para auditoria numérica. O score manifest referencia esse baseline e os parâmetros, sem cópia do dataset.

Custo: fitting de dois passes, O(n_B) operações e O(n_B) memória auxiliar nesta implementação simples; scoring O(1) aritmética/estado por observação. Os custos em bits dependem da precisão dos números. Pode operar online com modelo previamente ajustado e observação disponível; o framework atual materializa séries offline, portanto não é um coletor/serviço de streaming implementado.

## Coeficiente de Variação

Implementação: `analysis/detection/detectors/cov.py`, classe `CoV`, spec `cov_spec(lookback=L)`, versão 1.

\[
H_t=(x_{t-L+1},\ldots,x_t),\quad
\mu_t=\frac1L\sum_{x\in H_t}x,\quad
s_t=\sqrt{\frac{\sum_{x\in H_t}(x-\mu_t)^2}{L-1}},\quad
CV_t=\frac{s_t}{\mu_t}.
\]

L é inteiro explícito ≥2; não há default no detector. Contém **a observação atual** e L−1 anteriores da mesma série, sem futuro. L é número de janelas Stage 10, distinto de Δ. Sem gaps, a duração do histórico é L×Δ. O método não calcula desvio dentro da janela agregada original: retém valores de várias janelas, inclusive quando a feature é uma média. Testes mostram um mesmo valor corrente com CV diferente conforme seu histórico.

Não há fitting: `start_run(None, config)` inicializa deque com limite L. Parâmetros de baseline estático são recusados, evitando reutilizar artificialmente o modelo do Z-score. Cada execução recebe estado novo.

Missing segue **A: L valores consecutivos válidos**. Null apaga o histórico e produz `missing_observation_reset`; cada valor subsequente produz `warmup_consecutive_valid` até completar L valores consecutivos. Antes disso score é ausente, nunca zero. Também se verifica contiguidade de índices/bounds/run em chamadas diretas para evitar usar o mesmo estado atravessando lacunas não declaradas. Não se adotou B (últimos L válidos através de gaps), pois B aumenta silenciosamente a extensão temporal do histórico e esconde falhas de observação.

μ_t=0 produz score indisponível, `zero_lookback_mean`, inclusive para 0/0 da sequência constante zero. Não apaga o histórico válido: a janela seguinte continua deslizando e pode voltar a ter média não zero. μ_t próximo de zero, mas matematicamente não zero, mantém a razão definida; nenhum limiar/epsilon é usado. Instabilidade de interpretação relativa e sensibilidade a ruído/precisão permanecem limitações.

Não há abs(μ). A fórmula é exatamente s/μ: a interpretação usual exige escala de razão e média positiva, como nas candidatas normalmente não negativas. A implementação não altera silenciosamente valores negativos: se fornecidos, a razão algébrica terá o sinal da média, sem alegar a mesma interpretação usual de variabilidade relativa. Não há conversão para percentual (×100). Série constante não zero tem CV=0; isso é um score válido, distinto de warm-up ou 0/0.

Config persistida no score artifact: lookback, ddof=1, includes_current=true, missing_policy=consecutive_valid_reset, zero_mean=unavailable, definition=sigma/mean, precisão e arredondamento. Não existe referência de baseline externo. Não se assume que score maior represente ataque: um flood uniforme pode reduzir variabilidade relativa, e tráfego benigno esparso pode aumentá-la.

Custo: deque O(L) de memória, recomputação em dois passes O(L) por janela completa (O(NL) para N janelas). A opção simples evita deriva numérica de atualizações deslizantes e não antecipa otimizações sem necessidade. Há execução sequencial causal possível; não foi feito benchmark de throughput, nem implementado streaming em produção.

## Precisão e tempo

`_moments.py` usa Fraction para média/variância exatas dos valores Decimal observados, sem a subtração instável E[X²]−E[X]² em ponto flutuante. CoV testa média exatamente zero antes de arredondar. Z-score subtrai sua média exata antes de arredondar, preservando variações pequenas em torno de offsets grandes. Divisão/raiz e scores usam Decimal com **50 dígitos significativos, ROUND_HALF_EVEN**, em contexto próprio; não dependem da precisão global do chamador. Parâmetros exatos permitem reconstituir os arredondamentos. Raiz/score são aproximações de precisão finita, não números reais exatos; limites de expoente Decimal/custo de inteiros muito grandes permanecem limites computacionais, sem clipping para fazer rodar.

Nenhum valor é normalizado antes das equações autorizadas; nenhuma observação é removida como outlier. Disponibilidade segue a Etapa 11: ScoreValue sem horário extra é disponível no fechamento da janela observada, nunca no início; isso é relógio simulado offline, sem inventar latência medida de CPU. CoV não pontua antes do histórico necessário. Os scores não geram DecisionSeries.

## Uso com a Etapa 11

```python
from analysis.detection import fit_baseline, score_run
from analysis.detection.detectors.zscore import ZScore, zscore_spec
from analysis.detection.detectors.cov import CoV, cov_spec

# baseline_source e target_source vêm de load_series com seleção explícita.
model = fit_baseline([baseline_source], ZScore(), zscore_spec(), 'novo-baseline')
z = score_run(target_source, ZScore(), zscore_spec(), 'novos-zscores', baseline=model)

# L deve ser fornecido pelo protocolo; não há valor científico escolhido aqui.
cv = score_run(target_source, CoV(), cov_spec(lookback=L), 'novos-cv-scores')
```

Baseline source precisa role baseline; target científico não pode compartilhar seu run ID. No diagnóstico histórico desta etapa, roles são usados apenas para exercitar artefatos e todos os resultados são de desenvolvimento. Config/spec devem acompanhar o método, sem incluir labels ou parâmetros de ataque. Não há alterações no core da Etapa 11 ou na API das etapas anteriores.

## Validação e inspeção

Testes específicos:

```bash
.venv/bin/python -B -m unittest tests.test_statistical_scores -v
.venv/bin/python -B -m unittest discover -s tests -q
```

Validação histórica reproduzível em destino **novo**:

```bash
.venv/bin/python -B -m analysis.detection.validate_stage12a \
  --output experiment_results/stage12a-outra-validacao \
  --development-lookback 3
```

O número 3 nessa chamada é **parâmetro de desenvolvimento**, sem alegação de adequação científica, otimização ou recomendação definitiva. O comando só lê séries preexistentes e grava derivados; não chama simulador nem gerador de tráfego.

O comando produz baselines/score artifacts e uma tabela `diagnostics.csv`: método/run/família/feature, índice/bounds, valor, score, disponibilidade, motivo e horário. **Depois de todos os scores finalizados**, o leitor existente do evaluator carrega overlap para uma coluna posthoc. A fase de fit/scoring roda com bloqueio de abertura de labels.csv; labels não podem influenciar o cálculo. Essa tabela é diagnóstica e nunca deve retornar como entrada de detector.

Z-score histórico limita-se ao par nominalmente comparável Stage 5 A→C: `/`, quatro sources benignas ×10 RPS, containers/proxy/uma vítima e mesma configuração nominal de serviço. São execuções distintas, mas mesma seed e proveniência histórica incompleta: isso não constitui baseline/test científico independente. As cinco features candidatas exercitam cada família. Nenhum Z-score é aplicado usando esse baseline aos cenários Stage 7 ou `/expensive`, cujas operações/cargas não têm benigno equivalente.

CoV local é exercitado no benigno A, contínuo C, ContinuousFlood da Stage 7, PeriodicBurst e `/expensive`, nas cinco features. Não há transferência de baseline. São mantidas **todas as janelas da Stage 10**, inclusive startup, cauda e padding; nulos são tratados conforme cada método, sem cortar trechos convenientes ou assumir cobertura física comprovada. O benigno completo A usado no fitting inclui valores de cauda em counts; isso pode alterar μ/σ em relação ao recorte descritivo normal dentro do plano do diagnóstico anterior. Esse procedimento valida mecanismos, não congela a política científica de horizonte/estabilização.

Resultados e trechos da tabela em [statistical_scores_results.md](statistical_scores_results.md). Não foram calculados Accuracy/F1/Recall, threshold, classificação, ranking, otimização por labels ou conclusão de eficácia.

## Pendências

Shannon permanece sem implementação: é necessário definir de que distribuição/categorias virão p_i para H(X)=−Σp_i log(p_i). Agregados temporais Stage 10 não preservam necessariamente essa distribuição intrajanela; eventual representação adicional derivada de Stage 8 será decidida separadamente.

Campanha principal continua futura, controlada e com baseline/calibration/test independentes; seeds e durações dependem de piloto. Permanecem pendentes thresholds/policies, lookbacks científicos, horizonte de avaliação, recuperação/missing e métricas finais. Não houve conflito que exigisse modificar Etapas 0–11. A versão inicial testa exatamente a generalidade prevista: Z-score com modelo estático e CoV com estado/histórico local sem fit.
