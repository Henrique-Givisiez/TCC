# Resultados da Etapa 12A

**28 testes específicos aprovados; suíte completa: 249 testes aprovados.** Nenhuma mudança em arquivos preexistentes das Etapas 0–11, nenhum commit e nenhuma execução de campanha/simulador.

## Implementação e validação funcional

Z-score assinado com fitting independente e desvio amostral (ddof=1); CoV local com histórico incluindo observação atual, ddof=1 e missing que reinicia o histórico. Baseline Z-score com menos de duas observações válidas ou σ=0 é recusado; CoV com média zero fica indisponível, sem epsilon. Baseline null é excluído e contado, score null permanece indisponível.

A validação funcional gerou **5 baselines e 30 score artifacts**. Z-score: cinco features somente no par Stage 5 A→C, nominalmente comparável em operação/carga benigna/topologia. CoV: cinco features em benigno A, contínuo C, ContinuousFlood Stage 7, PeriodicBurst e /expensive. L=3 foi passado explicitamente como parâmetro de desenvolvimento, sem escolha científica ou otimização. Nenhum Z-score transferiu baseline para operações/cargas sem benigno equivalente.

Baselines usam toda a série observável disponível, incluindo cauda; a regra de horizonte científico continua pendente. As execuções históricas têm seed 42 e lacunas de proveniência, portanto os scores não representam avaliação científica independente.

Artefatos: `experiment_results/stage12a-final/`: `baselines/<feature>/manifest.json`; `scores/<method>/<case>/<feature>/{manifest.json,scores.csv}`; `diagnostics.csv`; `summary.json`; `audit.json`. A saída anterior `stage12a-validation/` é uma validação intermediária; os resultados aqui referem-se à saída final com hashes da implementação atual.

## Pequena inspeção tabular

Overlap é somente diagnóstico pós-hoc: os scores abaixo já estavam finalizados quando o reader do evaluator abriu labels. Valores arredondados apenas nesta apresentação; CSVs preservam os números persistidos. Disponibilidade dos scores válidos coincide com o fechamento da respectiva janela.

| Método / cenário / feature | Janela | Valor | Score | Motivo de indisponibilidade | Overlap pós-hoc |
|---|---|---:|---:|---|---:|
| zscore / C / request_starts | [0,1) | 34.0000 | -0.2873 | — | 0.0000 |
| zscore / C / request_starts | [2,3) | 40.0000 | 0.3644 | — | 0.0000 |
| zscore / C / request_starts | [10,11) | 83.0000 | 5.0347 | — | 0.9891 |
| zscore / C / request_starts | [11,12) | 75.0000 | 4.1658 | — | 1.0000 |
| cov / periodic / request_starts | [0,1) | 11.0000 | — | warmup_consecutive_valid | 0.0000 |
| cov / periodic / request_starts | [2,3) | 17.0000 | 0.5455 | — | 0.9083 |
| cov / periodic / request_starts | [3,4) | 9.0000 | 0.5913 | — | 1.0000 |
| cov / periodic / request_starts | [5,6) | 10.0000 | 0.1111 | — | 1.0000 |
| cov / periodic / request_starts | [6,7) | 3.0000 | 0.5151 | — | 1.0000 |
| cov / periodic / request_starts | [12,13) | 7.0000 | 0.4774 | — | 1.0000 |
| cov / expensive / mean_cpu_percent | [0,1) | — | — | missing_observation_reset | 0.0000 |
| cov / expensive / mean_cpu_percent | [2,3) | 158.1300 | — | warmup_consecutive_valid | 0.9946 |
| cov / expensive / mean_cpu_percent | [3,4) | 158.1300 | — | warmup_consecutive_valid | 1.0000 |
| cov / expensive / mean_cpu_percent | [4,5) | 203.6900 | 0.1518 | — | 1.0000 |

Esta inspeção confirma mecanismos qualitativos: Z-score preserva sinais abaixo/acima da média; CoV varia conforme o histórico local e permanece ausente no warm-up; CPU sem amostra reinicia o histórico. O PeriodicBurst conserva overlap global mesmo quando o score local varia nas janelas de silêncio. Nada disso estabelece detecção, atraso, eficácia, ranking ou threshold.

## Testes e integridade

Z-score: μ/s verificáveis manualmente em [1,2,3], scores −1/0/+1, comparação com statistics.mean/stdev independente, n insuficiente, baseline constante, null no baseline/scoring, peso entre runs, parâmetros incoerentes, grandes offsets e escalas pequenas. CoV: L=2/3/5 de desenvolvimento, fórmula manual e comparação independente, inclusão de x_t, warm-up, gaps/reset/retomada, média zero/quase zero, constantes, sinal negativo algébrico, parâmetros inválidos e ausência de fit estático.

Integração: persistência/round-trip, referências e hashes de baseline, disponibilidade no fechamento, ausência de decisões, prefixos causais iguais quando a série recebe extensão futura, determinismo de bytes e independência do contexto Decimal global. Um bloqueio de abertura de labels cobre fitting/scoring reais.

Os 30 arquivos consumidos na validação histórica preservaram hash/mtime. A auditoria ampliada verificou **3839 arquivos preexistentes**, também sem mudança de hash/mtime, incluindo core/tests/docs da Etapa 11 e outputs antigos. Todos os 35 manifests finais e 30 score CSVs foram reabertos/verificados; hashes da proveniência dos scores coincidem com os arquivos atuais. Hashes do diagnóstico e fontes estão em audit.json. Não foram reescritos relatórios anteriores.

## Arquivos adicionados e pendências

Somente adicionados: `analysis/detection/detectors/_moments.py`, `zscore.py`, `cov.py`; `analysis/detection/validate_stage12a.py`; `tests/test_statistical_scores.py`; `docs/statistical_scores.md`; este relatório; derivados nos diretórios de validação. Nenhum arquivo preexistente foi modificado.

Não houve conflito com a Etapa 11: o mesmo contrato aceitou um método com fit estático e outro com estado/lookback sem fit. Nenhuma calibração/policy/evaluator estatístico foi acrescentado. Thresholds, L científico, seeds, horizon/estabilização, incerteza, nova campanha e eficácia continuam fora do escopo. Shannon aguarda definição de distribuição e representação.

Definições, convenções, custos e reprodução: [statistical_scores.md](statistical_scores.md).
