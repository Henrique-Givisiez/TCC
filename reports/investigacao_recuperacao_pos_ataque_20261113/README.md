# Investigação complementar B1 + B2

Auditoria da recuperação pós-ataque e da cobertura da CPU na campanha TEST definitiva. Os resultados oficiais dos detectores não foram alterados.

## Reprodução

Na raiz do repositório:

```bash
python3 reports/investigacao_recuperacao_pos_ataque_20261113/scripts/analyze.py
python3 reports/investigacao_recuperacao_pos_ataque_20261113/scripts/validate.py
```

Requer Python 3, pandas, NumPy, SciPy e Matplotlib. Leia [relatorio.md](relatorio.md) para definições, resultados e limites. `processed/post_por_execucao.csv` e `processed/http_por_execucao.csv` são as tabelas principais por execução; `processed/contrastes_por_bloco.csv` preserva os pares.
