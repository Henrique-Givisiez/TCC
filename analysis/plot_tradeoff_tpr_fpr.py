import glob
import json
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Pedido do usuário: um gráfico só, mostrando sensibilidade (TPR nos
# ataques mais furtivos) CONTRA falso-positivo (tráfego limpo), pras 5
# regras de decisão discutidas -- não um heatmap, um scatter (forma certa
# pra comparar duas métricas contínuas entre poucas categorias). Resolve
# de uma vez a pergunta "por que não trocar E por OU": mostra visualmente
# o trade-off, não só em texto.
#
# TPR = média nas execuções de 1% de intensidade (S1-S4, wedos_grid +
# combined_sweep) que causaram SCALE_UP real -- o teste mais duro que já
# usamos (furtividade). FPR = % de execuções 100% normais
# (clients_rps_grid) que disparam alarme -- medido separado para tráfego
# limpo (n=151) e para execuções com o soluço transitório (n=9), ligados
# por uma linha pra mostrar a faixa.

OUT_DIR = "results/graficos_apresentacao/03_deteccao_estatistica"
os.makedirs(OUT_DIR, exist_ok=True)

GRAY = "#555555"
BLUE = "#2a78d6"
ORANGE = "#e08a1e"
RED = "#d03b3b"
ROXO = "#7a3fd6"


def mmss_para_seg(s):
    mm, ss = s.split(":")
    return float(mm) * 60 + float(ss)


REGRAS = {
    "Combinado atual\n(piso E (Z ou CUSUM))": (lambda df: df["Status Burst"] == "DDoS Burst", GRAY),
    "Entropia sozinha": (lambda df: df["Al. Ent."] == "Sim", ROXO),
    "CUSUM sozinho": (lambda df: df["Al. CUSUM"] == "Sim", BLUE),
    "Z-score sozinho": (lambda df: df["Al. Z"] == "Sim", ORANGE),
    "Z OU CUSUM\n(sem piso)": (lambda df: (df["Al. Z"] == "Sim") | (df["Al. CUSUM"] == "Sim"), RED),
}

# --- TPR: 1% de intensidade, só execuções com SCALE_UP real ---
tpr_rows = {nome: [] for nome in REGRAS}
for results_dir in ["experiment_results/wedos_grid", "experiment_results/combined_sweep"]:
    for rtt_path in sorted(glob.glob(os.path.join(results_dir, "rtt_log_*atk1pct*.csv"))):
        suffix = os.path.basename(rtt_path)[len("rtt_log_"):-len(".csv")]
        metrics_path = os.path.join(results_dir, f"metrics_{suffix}.csv")
        xlsx_path = os.path.join(results_dir, f"rtt_bursts_{suffix}.xlsx")
        if not os.path.exists(metrics_path) or not os.path.exists(xlsx_path):
            continue
        metrics = pd.read_csv(metrics_path)
        if not (metrics["decision"] == "SCALE_UP").any():
            continue
        attack_rows = metrics[metrics["label"] == "attack"]
        if attack_rows.empty:
            continue
        a0, a1 = attack_rows["elapsed_time_s"].min(), attack_rows["elapsed_time_s"].max()
        df = pd.read_excel(xlsx_path)
        tempos = df["Janela (MM:SS.s)"].apply(mmss_para_seg)
        dentro = (tempos >= a0) & (tempos <= a1)
        if dentro.sum() == 0:
            continue
        for nome, (regra, _cor) in REGRAS.items():
            alarme = regra(df)
            tpr_rows[nome].append(100.0 * (alarme & dentro).sum() / dentro.sum())

tpr_medio = {nome: np.mean(vals) for nome, vals in tpr_rows.items()}
n_tpr = len(next(iter(tpr_rows.values())))

# --- FPR: clients_rps_grid, limpo vs soluço ---
GRID_DIR = "experiment_results/clients_rps_grid"


def is_soluco(summary_path, expected_clients):
    if not os.path.exists(summary_path):
        return None
    df = pd.read_csv(summary_path)
    df = df[df["total_requests"].notna()]
    return len(df) < expected_clients


fpr_rows = {nome: {"limpo": [], "soluco": []} for nome in REGRAS}
for xlsx_path in sorted(glob.glob(os.path.join(GRID_DIR, "rtt_bursts_agg*_clients*_WU10_rep*.xlsx"))):
    suffix = os.path.basename(xlsx_path)[len("rtt_bursts_"):-len(".xlsx")]
    m = re.match(r"agg(\d+)_clients(\d+)_WU10_rep(\d+)", suffix)
    if not m:
        continue
    clients = int(m.group(2))
    summary_path = os.path.join(GRID_DIR, f"normal_traffic_summary_log_{suffix}.csv")
    soluco = is_soluco(summary_path, clients)
    if soluco is None:
        continue
    df = pd.read_excel(xlsx_path)
    for nome, (regra, _cor) in REGRAS.items():
        disparou = bool(regra(df).any())
        fpr_rows[nome]["soluco" if soluco else "limpo"].append(disparou)

fpr_limpo = {nome: 100.0 * np.mean(fpr_rows[nome]["limpo"]) for nome in REGRAS}
fpr_soluco = {nome: 100.0 * np.mean(fpr_rows[nome]["soluco"]) for nome in REGRAS}
n_limpo = len(fpr_rows[next(iter(REGRAS))]["limpo"])
n_soluco = len(fpr_rows[next(iter(REGRAS))]["soluco"])

# ---------------------------------------------------------------------
# Gráfico
# ---------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 8))

# zonas de fundo -- ajuda a leitura sem precisar de legenda extra
ax.axvspan(0, 15, color="#1baf7a", alpha=0.06, zorder=0)
ax.axhspan(70, 100, color="#1baf7a", alpha=0.06, zorder=0)
ax.text(1, 97, "zona ideal\n(sensível, poucos alarmes falsos)", fontsize=8.5, color="#2a8f5c",
        ha="left", va="top", style="italic")
ax.text(97, 22, "zona ruim\n(insensível E/OU\nfalso-alarme alto)", fontsize=8.5, color="#a83a3a",
        ha="right", va="bottom", style="italic")

# posição manual do rótulo de cada método -- (dx, dy em pontos, alinhamento
# horizontal) -- evita colisão entre rótulos de pontos próximos (Z-score x
# Z OU CUSUM ficam quase colados no topo; Combinado atual x Entropia ficam
# quase colados embaixo).
LABEL_POS = {
    "Combinado atual\n(piso E (Z ou CUSUM))": (14, 10, "left"),
    "Entropia sozinha": (14, -4, "left"),
    "CUSUM sozinho": (14, 8, "left"),
    "Z-score sozinho": (-10, 14, "right"),
    "Z OU CUSUM\n(sem piso)": (10, -18, "left"),
}

for nome, (_regra, cor) in REGRAS.items():
    y = tpr_medio[nome]
    x_limpo = fpr_limpo[nome]
    x_soluco = fpr_soluco[nome]
    # linha ligando o FPR em tráfego limpo ao FPR com soluço -- mostra a faixa
    ax.plot([x_limpo, x_soluco], [y, y], color=cor, linewidth=1.4, alpha=0.55, zorder=2)
    ax.scatter([x_soluco], [y], s=90, facecolors="none", edgecolors=cor, linewidths=1.8, zorder=3)
    ax.scatter([x_limpo], [y], s=220, color=cor, edgecolors="white", linewidths=1.2, zorder=4)

    nome_label = nome.replace("\n", " ")
    dx, dy, ha = LABEL_POS[nome]
    ax.annotate(
        nome_label, xy=(x_limpo, y), xytext=(dx, dy),
        textcoords="offset points", ha=ha, fontsize=9.5, color=cor, fontweight="bold",
    )

# marcador extra na legenda pra explicar os 2 pontos por método
from matplotlib.lines import Line2D
handles = [
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#555", markersize=13,
           markeredgecolor="white", label="FPR em tráfego limpo (n=151)"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="none", markeredgecolor="#555",
           markersize=10, markeredgewidth=1.8, label="FPR em execuções com soluço (n=9)"),
]
ax.legend(handles=handles, loc="lower right", fontsize=9, framealpha=0.95, bbox_to_anchor=(1.0, -0.02))

ax.set_xlim(-3, 103)
ax.set_ylim(-3, 103)
ax.set_xlabel("Falso-positivo -- % de execuções SEM ataque que disparam alarme (menor = melhor)", fontsize=10.5)
ax.set_ylabel("Sensibilidade -- % de janelas detectadas nos ataques mais furtivos, 1% de intensidade\n"
              "(maior = melhor)", fontsize=10.5)
ax.set_title(
    "Sensibilidade × falso-positivo, por regra de decisão\n"
    f"Sensibilidade: média em {n_tpr} execuções furtivas (1% intensidade, dano real confirmado)\n"
    f"Falso-positivo: {n_limpo} execuções limpas + {n_soluco} com soluço",
    fontsize=11.5,
)
ax.grid(True, alpha=0.25)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "46_tradeoff_sensibilidade_fpr.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")

print("\nResumo:")
for nome in REGRAS:
    print(f"  {nome.replace(chr(10), ' ')}: TPR={tpr_medio[nome]:.1f}%, "
          f"FPR_limpo={fpr_limpo[nome]:.1f}%, FPR_soluco={fpr_soluco[nome]:.1f}%")
