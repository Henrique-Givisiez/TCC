import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator import config

# Gráfico novo pedido pelo usuário: intensidade do ataque vs. tráfego
# legítimo, variando nº de atacantes e RPS/atacante, com a intensidade
# agregada do ataque nunca passando de 25% do agregado normal do cenário
# (S1-S4). Desenho no mesmo espírito do gráfico 06 (heatmap por cenário),
# mas com nº de atacantes no eixo Y em vez de WU -- aqui o custo por
# requisição (WU) fica fixo em 200.000 (ver run_atacantes_intensidade_
# grid.py e changes.txt §84 para a justificativa de manter o WU fixo,
# espelhando o desenho do artigo Sotelo Monge et al., que também fixa o
# custo do endpoint atacado e só varia o volume/intensidade).
#
# Fonte: experiment_results/atacantes_intensidade_grid/ (72 execuções, 1
# rep, triagem -- ver changes.txt §84).

GRID_DIR = "experiment_results/atacantes_intensidade_grid"
OUT_DIR = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
os.makedirs(OUT_DIR, exist_ok=True)

NORMAL_SCENARIOS = {
    "S1": 40, "S2": 100, "S3": 200, "S4": 300,
    "S5": 20, "S6": 80, "S7": 160, "S8": 320,
}
ATTACKERS_VALUES = [1, 2, 4]
INTENSITIES_PCT = [1, 5, 10, 15, 20, 25]
WORK_UNITS = 200000


def timeout_rate(suffix):
    af = os.path.join(GRID_DIR, f"attack_summary_log_{suffix}.csv")
    if not os.path.exists(af):
        return None
    adf = pd.read_csv(af)
    ok = pd.to_numeric(adf.get("total_requests"), errors="coerce").sum()
    errs = pd.to_numeric(adf.get("errors"), errors="coerce").sum()
    return 100.0 * errs / (ok + errs) if (ok + errs) > 0 else 0.0


rows = []
for scenario, agg in NORMAL_SCENARIOS.items():
    for attackers in ATTACKERS_VALUES:
        for pct in INTENSITIES_PCT:
            suffix = f"{scenario}_atk{pct}pct_att{attackers}_wu{WORK_UNITS}_rep1"
            mf = os.path.join(GRID_DIR, f"metrics_{suffix}.csv")
            if not os.path.exists(mf):
                print(f"[AVISO] faltando: {mf}")
                continue
            df = pd.read_csv(mf).iloc[1:]  # descarta t=0
            peak_cpu = df["average_cpu_percent"].max()
            escalou = (df["decision"] == "SCALE_UP").any()
            rows.append(dict(
                scenario=scenario, attackers=attackers, pct=pct,
                peak_cpu=peak_cpu, escalou=escalou,
                timeout_pct=timeout_rate(suffix),
            ))

grid = pd.DataFrame(rows)
print(grid.to_string(index=False))

n_scen = len(NORMAL_SCENARIOS)
ncols = 4
nrows = -(-n_scen // ncols)  # ceil
fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 5.4 * nrows), squeeze=False)
axes = axes.flatten()
vmax = max(grid["peak_cpu"].max(), config.CPU_THRESHOLD_SCALE_UP)

for ax, (scenario, agg) in zip(axes, NORMAL_SCENARIOS.items()):
    mat = np.full((len(ATTACKERS_VALUES), len(INTENSITIES_PCT)), np.nan)
    scaled = np.zeros((len(ATTACKERS_VALUES), len(INTENSITIES_PCT)), dtype=bool)
    timeout_mat = np.full((len(ATTACKERS_VALUES), len(INTENSITIES_PCT)), np.nan)
    sub = grid[grid.scenario == scenario]
    for i, att in enumerate(ATTACKERS_VALUES):
        for j, pct in enumerate(INTENSITIES_PCT):
            cell = sub[(sub.attackers == att) & (sub.pct == pct)]
            if len(cell):
                mat[i, j] = cell["peak_cpu"].values[0]
                scaled[i, j] = bool(cell["escalou"].values[0])
                timeout_mat[i, j] = cell["timeout_pct"].values[0]

    im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(INTENSITIES_PCT)))
    ax.set_xticklabels([f"{p}%" for p in INTENSITIES_PCT])
    ax.set_yticks(range(len(ATTACKERS_VALUES)))
    ax.set_yticklabels([str(a) for a in ATTACKERS_VALUES])
    ax.set_xlabel("Intensidade do ataque (% do agregado normal)")
    ax.set_title(f"{scenario} ({agg} rps agregado normal)")
    for i in range(len(ATTACKERS_VALUES)):
        for j in range(len(INTENSITIES_PCT)):
            if np.isnan(mat[i, j]):
                continue
            marca = " ▲" if scaled[i, j] else ""
            to = timeout_mat[i, j]
            to_str = f"\n{to:.0f}% to" if to and to > 0.5 else ""
            cor_texto = "white" if mat[i, j] > vmax * 0.6 else "black"
            ax.text(j, i, f"{mat[i, j]:.0f}%{marca}{to_str}", ha="center", va="center",
                    color=cor_texto, fontsize=9, fontweight="bold")

for row_start in range(0, n_scen, ncols):
    axes[row_start].set_ylabel("Nº de atacantes")
for ax in axes[n_scen:]:
    ax.axis("off")
fig.suptitle(
    "Intensidade do ataque × nº de atacantes, teto de 25% do agregado normal (WU=200.000, 1 rep)\n"
    "▲ = SCALE_UP disparado -- \"to\" = % de timeout quando > 0.5%",
    fontsize=12, y=1.03,
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "48_atacantes_intensidade_grid.png")
fig.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"\nSalvo: {out_path}")
