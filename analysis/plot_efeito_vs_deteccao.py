import glob
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Pedido do usuário: comparar o gráfico 6 (efeito do ataque -- CPU de
# pico, Stage1A, 1 rep, separado por WU) com o gráfico 45 (detecção --
# métrica por janela, Stage1A+1B+combined_sweep agregados, WU colapsado).
# Em vez de só justapor os dois gráficos antigos (que usam POPULAÇÕES
# DIFERENTES de execuções), este script recalcula CPU de pico E detecção
# para o MESMO conjunto exato de execuções (as 77 com SCALE_UP real que
# alimentam o gráfico 45) -- correspondência célula-a-célula garantida,
# não só visual.

WEDOS_DIRS = ["experiment_results/wedos_grid", "experiment_results/combined_sweep"]
RESUMO_CSV = "experiment_results/resumo_deteccao_wedos_combined_final.csv"
OUT_DIR = "results/graficos_apresentacao/03_deteccao_estatistica"
os.makedirs(OUT_DIR, exist_ok=True)

S_VALUES = ["S1", "S2", "S3", "S4"]
PCT_VALUES = [1, 5, 10]
S_RPS_FUNDO = {"S1": 40, "S2": 100, "S3": 200, "S4": 300}

df = pd.read_csv(RESUMO_CSV)
extra = df["cenario"].str.extract(r"^(S[1-4])_atk(\d+)pct")
df["cenario_S"] = extra[0]
df["intensidade_pct"] = extra[1].astype("Int64")
df = df.dropna(subset=["cenario_S", "intensidade_pct"])
df = df[df["escalou_real"] == True].copy()

# localiza o metrics_{cenario}.csv de cada linha (pode estar em qualquer
# um dos 2 diretórios) e extrai o pico de CPU do container daquela execução
def achar_metrics(cenario):
    for d in WEDOS_DIRS:
        p = os.path.join(d, f"metrics_{cenario}.csv")
        if os.path.exists(p):
            return p
    return None

peaks = []
for cenario in df["cenario"]:
    mpath = achar_metrics(cenario)
    if mpath is None:
        peaks.append(np.nan)
        continue
    m = pd.read_csv(mpath)
    peaks.append(m["average_cpu_percent"].max())
df["peak_cpu"] = peaks
df = df.dropna(subset=["peak_cpu", "tpr_novo"])

cpu_matrix = np.full((len(S_VALUES), len(PCT_VALUES)), np.nan)
tpr_matrix = np.full((len(S_VALUES), len(PCT_VALUES)), np.nan)
n_matrix = np.full((len(S_VALUES), len(PCT_VALUES)), 0)

for i, s in enumerate(S_VALUES):
    for j, pct in enumerate(PCT_VALUES):
        cell = df[(df["cenario_S"] == s) & (df["intensidade_pct"] == pct)]
        if len(cell):
            cpu_matrix[i, j] = cell["peak_cpu"].mean()
            tpr_matrix[i, j] = cell["tpr_novo"].mean()
            n_matrix[i, j] = len(cell)

row_labels = [f"{s} ({S_RPS_FUNDO[s]} rps normal)" for s in S_VALUES]
col_labels = [f"{p}% do agregado" for p in PCT_VALUES]

fig, axes = plt.subplots(1, 2, figsize=(15, 6.8))

# --- painel 1: efeito do ataque (CPU de pico) ---
ax = axes[0]
vmax_cpu = np.nanmax(cpu_matrix)
im1 = ax.imshow(cpu_matrix, cmap="Blues", aspect="auto", origin="upper", vmin=0, vmax=vmax_cpu)
ax.set_xticks(range(len(col_labels))); ax.set_xticklabels(col_labels, fontsize=9)
ax.set_yticks(range(len(row_labels))); ax.set_yticklabels(row_labels, fontsize=9)
ax.set_xlabel("intensidade do ataque (% do RPS agregado de fundo)", fontsize=9)
ax.set_ylabel("cenário de fundo (S1-S4 = tráfego normal de base)", fontsize=9)
ax.set_title("Efeito do ataque: CPU de pico\n(todas as execuções com SCALE_UP real -- dano confirmado)", fontsize=10.5)
for i in range(len(S_VALUES)):
    for j in range(len(PCT_VALUES)):
        val = cpu_matrix[i, j]
        if np.isnan(val):
            ax.text(j, i, "sem dado", ha="center", va="center", color="#999", fontsize=8)
            continue
        n = int(n_matrix[i, j])
        color = "white" if val > vmax_cpu * 0.55 else "black"
        ax.text(j, i, f"{val:.0f}%\n(n={n})", ha="center", va="center", color=color, fontsize=9.5, fontweight="bold")
cbar1 = fig.colorbar(im1, ax=ax, label="CPU de pico do container (%)")
cbar1.ax.invert_yaxis()

# --- painel 2: detecção (mesmas execuções exatas) ---
ax = axes[1]
im2 = ax.imshow(tpr_matrix, cmap="RdYlGn", aspect="auto", origin="upper", vmin=0, vmax=100)
ax.set_xticks(range(len(col_labels))); ax.set_xticklabels(col_labels, fontsize=9)
ax.set_yticks(range(len(row_labels))); ax.set_yticklabels(row_labels, fontsize=9)
ax.set_xlabel("intensidade do ataque (% do RPS agregado de fundo)", fontsize=9)
ax.set_ylabel("cenário de fundo (S1-S4 = tráfego normal de base)", fontsize=9)
ax.set_title("Detecção: % de janelas do ataque real marcadas 'DDoS Burst'\n(MESMAS execuções do painel 1 -- correspondência exata)", fontsize=10.5)
for i in range(len(S_VALUES)):
    for j in range(len(PCT_VALUES)):
        val = tpr_matrix[i, j]
        if np.isnan(val):
            ax.text(j, i, "sem dado", ha="center", va="center", color="#999", fontsize=8)
            continue
        n = int(n_matrix[i, j])
        color = "white" if val < 35 or val > 70 else "black"
        ax.text(j, i, f"{val:.0f}%\n(n={n})", ha="center", va="center", color=color, fontsize=9.5, fontweight="bold")
cbar2 = fig.colorbar(im2, ax=ax, label="% de janelas de ataque real detectadas")
cbar2.ax.invert_yaxis()

fig.suptitle(
    "Efeito do ataque × detecção -- mesmas execuções, célula a célula\n"
    "Todo dado aqui já causou SCALE_UP real (dano confirmado): a pergunta não é \"o ataque funcionou?\", é \"foi percebido?\"",
    fontsize=12.5,
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "47_efeito_vs_deteccao.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")

print("\nResumo por célula (CPU pico / %detectado / n):")
for i, s in enumerate(S_VALUES):
    for j, pct in enumerate(PCT_VALUES):
        if not np.isnan(cpu_matrix[i, j]):
            print(f"  {s}/{pct}%: CPU={cpu_matrix[i,j]:.0f}%  detectado={tpr_matrix[i,j]:.0f}%  n={int(n_matrix[i,j])}")
