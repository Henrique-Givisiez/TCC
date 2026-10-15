# Resultados da Etapa 11

39 testes novos passaram; suíte completa: **221 testes, todos passaram**. Nenhum detector real, calibrador estatístico, threshold científico ou métrica foi implementado. Nenhum experimento/campanha foi executado e nenhum commit foi feito.

## Validação funcional histórica

Leitura repetida e comparação determinística de 20 seleções explícitas (cinco features em quatro runs). Apenas loader e integridade; não foram executados componentes fake nos históricos, scores ou comparações de desempenho.

| Run | Janelas | Null ingress count/bytes | Null starts | Null duração | Null CPU |
|---|---:|---:|---:|---:|---:|
| stage7-regressions/stage5/A | 31 | 0 | 0 | 0 | 3 |
| stage7-validation/continuous | 16 | 0 | 0 | 1 | 3 |
| stage7-validation/periodic | 16 | 0 | 0 | 1 | 3 |
| stage7-regressions/stage6/expensive | 9 | 0 | 0 | 0 | 3 |

A rede de stage7-regressions/stage4/A foi recusada com `feature_unavailable: network direction unsupported`. Missing observado permanece None; nenhuma imputação/normalização/remoção de outliers. O bloqueio de abertura de labels confirmou zero leituras fora do evaluator.

Os 35 arquivos dos cinco feature datasets inspecionados preservaram hashes e mtimes. Os 3.710 arquivos protegidos de simulator, experiments e dados/relatórios Stage 8–10 preservaram seus hashes antes/depois da implementação e testes. O único estado Git novo corresponde aos arquivos adicionados; documentos do diagnóstico anterior permaneceram intactos.

Resumo auditável: `experiment_results/stage11-framework-validation/summary.json`, com IDs/hashes por seleção, nulls, recusas e hashes do framework. A checagem é funcional, não uma nova certificação Stage 9 ou prova de completude física da captura.

## Arquivos e limites

Adicionados: `analysis/detection/__init__.py`, `contracts.py`, `inputs.py`, `artifacts.py`, `pipeline.py`, `evaluation/__init__.py`, `detectors/__init__.py`; `tests/test_detection_framework.py`; `docs/detection_framework.md`; este relatório. Saída gerada de validação no diretório acima. Nenhum arquivo preexistente das Etapas 0–10 foi modificado. `docs/stage11-diagnosis/` já era entrega anterior e continua sem commit.

Os testes usam fixtures sintéticas temporárias e componentes fake exclusivamente no arquivo de testes. Cobrem fases, leakage acidental, seleção/identidade/schema, integridade, mudança durante callback/depois da execução, fontes de calibração alteradas, reabertura, registros divergentes, warm-up/missing, estado, tempos de disponibilidade, determinismo e preservação de inputs. Grade Decimal também é verificada com precisão global reduzida.

Sem detectores/policies/evaluator reais ou CLI nesta etapa. Event-level possui tipos, mas não loader de intervalos efetivos nem cálculo de delay: labels Stage 10 v1 não preservam todos os eventos/IDs. Políticas de overlap/threshold/lookback e tratamento de estado nos gaps continuam pendentes. A API separa dados, mas não isola código Python malicioso. Comparabilidade e independência de seeds dependerão do protocolo futuro.

Contratos e formatos: [detection_framework.md](detection_framework.md).
