"""Regenerate only figures from the already derived tables, offline."""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path(__file__).resolve().parent
allseries=pd.read_csv(OUT/'series_1s.csv');five=pd.read_csv(OUT/'coortes_5s.csv')
# Single plot specification shared with the full analysis.
source=(OUT/'analisar.py').read_text().split("colors={'L2':",1)[1].split("(OUT/'manifesto_entradas.json')",1)[0]
exec("colors={'L2':"+source)
