# Visualização da campanha científica definitiva

80 execuções auditadas; figuras em `figures/`, resumos em `processed/`, catálogo em `catalogo_figuras.csv` e metodologia em [relatorio.md](relatorio.md).

Reproduzir da raiz:

```bash
python3 reports/scientific_campaign_visualization_20261112/scripts/audit.py
python3 reports/scientific_campaign_visualization_20261112/scripts/plots.py
python3 reports/scientific_campaign_visualization_20261112/scripts/report.py
python3 reports/scientific_campaign_visualization_20261112/scripts/validate.py
```

Dependências: Python 3, NumPy, pandas, Matplotlib e Pillow. `plots.py --all-traces` acrescenta trajetórias individuais para todas as combinações TEST.
