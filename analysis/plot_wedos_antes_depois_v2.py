import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Versão 2 do gráfico 33 -- não sobrescreve o original (77 barras
# individuais, ilegível numa apresentação). Aqui, mesmo estilo visual dos
# heatmaps 21/28/30: linhas = cenário de fundo (S1-S4), colunas =
# intensidade do ataque (1%/5%/10%), célula = % de execuções com SCALE_UP
# real que foram detectadas pelo detector CORRIGIDO -- com anotação
# confirmando que o resultado é IDÊNTICO ao detector antigo (com o bug do
# CUSUM), reforçando visualmente a robustez do achado (changes.txt §72).

IN_CSV = "experiment_results/resumo_deteccao_wedos_combined_final.csv"
OUT_DIR = "results/graficos_apresentacao/03_deteccao_estatistica"
os.makedirs(OUT_DIR, exist_ok=True)

df = pd.read_csv(IN_CSV)
extra = df["cenario"].str.extract(r"^(S[1-4])_atk(\d+)pct")
df["cenario_S"] = extra[0]
df["intensidade_pct"] = extra[1].astype("Int64")
df = df.dropna(subset=["cenario_S", "intensidade_pct"])

S_VALUES = ["S1", "S2", "S3", "S4"]
PCT_VALUES = [1, 5, 10]

tpr_matrix = np.full((len(S_VALUES), len(PCT_VALUES)), np.nan)
n_escalou_matrix = np.full((len(S_VALUES), len(PCT_VALUES)), 0)
n_antigo_zero_matrix = np.full((len(S_VALUES), len(PCT_VALUES)), 0)
n_novo_zero_matrix = np.full((len(S_VALUES), len(PCT_VALUES)), 0)

for i, s in enumerate(S_VALUES):
    for j, pct in enumerate(PCT_VALUES):
        cell = df[(df["cenario_S"] == s) & (df["intensidade_pct"] == pct)]
        escalou = cell[cell["escalou_real"] == True]
        if escalou.empty:
            continue
        n_escalou = len(escalou)
        n_antigo_zero = int((escalou["n_bursts_antigo"] == 0).sum())
        n_novo_zero = int((escalou["n_bursts_novo"] == 0).sum())
        tpr = 100.0 * (n_escalou - n_novo_zero) / n_escalou

        tpr_matrix[i, j] = tpr
        n_escalou_matrix[i, j] = n_escalou
        n_antigo_zero_matrix[i, j] = n_antigo_zero
        n_novo_zero_matrix[i, j] = n_novo_zero

fig, ax = plt.subplots(figsize=(9, 7))
im = ax.imshow(tpr_matrix, cmap="RdYlGn", aspect="auto", origin="upper", vmin=0, vmax=100)

ax.set_xticks(range(len(PCT_VALUES)))
ax.set_xticklabels([f"{p}% do agregado" for p in PCT_VALUES])
ax.set_yticks(range(len(S_VALUES)))
ax.set_yticklabels(S_VALUES)
ax.set_xlabel("intensidade do ataque (% do RPS agregado de fundo)")
ax.set_ylabel("cenário de fundo (S1-S4, tráfego normal)")

for i in range(len(S_VALUES)):
    for j in range(len(PCT_VALUES)):
        tpr = tpr_matrix[i, j]
        if np.isnan(tpr):
            ax.text(j, i, "sem dado", ha="center", va="center", color="#999", fontsize=9)
            continue
        n = int(n_escalou_matrix[i, j])
        n_antigo_zero = int(n_antigo_zero_matrix[i, j])
        n_novo_zero = int(n_novo_zero_matrix[i, j])
        igual = "idêntico ao antigo" if n_antigo_zero == n_novo_zero else f"ERA {n_antigo_zero}, MUDOU"
        color = "white" if tpr < 35 or tpr > 70 else "black"
        label = f"{tpr:.0f}% detectado\n(n={n} com SCALE_UP real)\n{igual}"
        ax.text(j, i, label, ha="center", va="center", color=color, fontsize=9)

cbar = fig.colorbar(im, ax=ax, label="% de ataques com SCALE_UP real DETECTADOS pelo RTT")

ax.set_title(
    "Antes × depois da correção do CUSUM -- agregado por cenário\n"
    "Resultado do detector corrigido é IDÊNTICO ao antigo (com bug) em 100% dos 77 casos comparáveis",
    fontsize=11.5,
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "34_wedos_antes_depois_agregado.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")

print(df.groupby(["cenario_S", "intensidade_pct"]).size())
