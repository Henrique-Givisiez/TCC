import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator import config

# Recorte do gráfico 48 (plot_atacantes_intensidade_grid.py) pedido pelo
# usuário: só os 4 cenários em progressão de potência de 2 (40/80/160/320
# agregado normal -- S1/S6/S7/S8), em vez dos 8 cenários completos (S1-S8).
# Mesmos dados (experiment_results/atacantes_intensidade_grid/), mesma
# métrica (pico de CPU do container, ▲ = SCALE_UP, "to" = % timeout),
# layout 1x4 em vez de 2x4. Nenhum Docker novo, nenhum script existente
# alterado.

GRID_DIR = "experiment_results/atacantes_intensidade_grid"
OUT_DIR = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
os.makedirs(OUT_DIR, exist_ok=True)

NORMAL_SCENARIOS = {
    "S1": 40, "S6": 80, "S7": 160, "S8": 320,
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
fig, axes = plt.subplots(1, n_scen, figsize=(6 * n_scen, 5.4), squeeze=False)
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

axes[0].set_ylabel("Nº de atacantes")
fig.suptitle(
    "Intensidade do ataque × nº de atacantes, progressão de potência de 2 "
    "(40/80/160/320 agregado, WU=200.000, 1 rep)\n"
    "▲ = SCALE_UP disparado -- \"to\" = % de timeout quando > 0.5%",
    fontsize=12, y=1.03,
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "53_atacantes_intensidade_grid_pow2.png")
fig.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"\nSalvo: {out_path}")
