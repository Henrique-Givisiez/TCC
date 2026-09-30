import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator import config

# Extensão do gráfico 48 (plot_atacantes_intensidade_grid.py): mesmo grid
# S1-S8 x atacantes x intensidade, mesmos CSVs em experiment_results/
# atacantes_intensidade_grid/ -- mas em vez de colorir por pico de CPU do
# container, colore por % do tempo de execução em que host_cpu_percent
# (CPU do host inteiro, todos os núcleos, coluna presente em todo run
# desde changes.txt §37) ficou >= 95%. Essa é a mesma condição usada na
# prova dose-resposta do gráfico 19 (plot_host_saturacao_prova.py --
# "gruda em 99-100% do t=80s até o fim" correlacionado com colapso de
# erro). Aqui aplicamos a mesma lógica às 144 células do grid 48 para
# testar visualmente se timeout alto == tempo de saturação real do host
# alto, célula por célula.

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
SATURATION_THRESHOLD = 95.0


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
            host_cpu = pd.to_numeric(df["host_cpu_percent"], errors="coerce").dropna()
            sat_pct = 100.0 * (host_cpu >= SATURATION_THRESHOLD).sum() / len(host_cpu) if len(host_cpu) else np.nan
            peak_host_cpu = host_cpu.max() if len(host_cpu) else np.nan
            escalou = (df["decision"] == "SCALE_UP").any()
            rows.append(dict(
                scenario=scenario, attackers=attackers, pct=pct,
                sat_pct=sat_pct, peak_host_cpu=peak_host_cpu, escalou=escalou,
                timeout_pct=timeout_rate(suffix),
            ))

grid = pd.DataFrame(rows)
print(grid.to_string(index=False))

n_scen = len(NORMAL_SCENARIOS)
ncols = 4
nrows = -(-n_scen // ncols)  # ceil
fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 5.4 * nrows), squeeze=False)
axes = axes.flatten()

for ax, (scenario, agg) in zip(axes, NORMAL_SCENARIOS.items()):
    mat = np.full((len(ATTACKERS_VALUES), len(INTENSITIES_PCT)), np.nan)
    scaled = np.zeros((len(ATTACKERS_VALUES), len(INTENSITIES_PCT)), dtype=bool)
    timeout_mat = np.full((len(ATTACKERS_VALUES), len(INTENSITIES_PCT)), np.nan)
    peak_mat = np.full((len(ATTACKERS_VALUES), len(INTENSITIES_PCT)), np.nan)
    sub = grid[grid.scenario == scenario]
    for i, att in enumerate(ATTACKERS_VALUES):
        for j, pct in enumerate(INTENSITIES_PCT):
            cell = sub[(sub.attackers == att) & (sub.pct == pct)]
            if len(cell):
                mat[i, j] = cell["sat_pct"].values[0]
                scaled[i, j] = bool(cell["escalou"].values[0])
                timeout_mat[i, j] = cell["timeout_pct"].values[0]
                peak_mat[i, j] = cell["peak_host_cpu"].values[0]

    im = ax.imshow(mat, cmap="Reds", vmin=0, vmax=100, aspect="auto")
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
            cor_texto = "white" if mat[i, j] > 60 else "black"
            ax.text(j, i, f"{mat[i, j]:.0f}% sat\n(pico {peak_mat[i, j]:.0f}%){marca}{to_str}",
                    ha="center", va="center",
                    color=cor_texto, fontsize=8, fontweight="bold")

for row_start in range(0, n_scen, ncols):
    axes[row_start].set_ylabel("Nº de atacantes")
for ax in axes[n_scen:]:
    ax.axis("off")
fig.suptitle(
    "Saturação real do host (% do tempo com host_cpu_percent >= 95%) por célula do grid 48\n"
    "▲ = SCALE_UP disparado -- \"to\" = % de timeout quando > 0.5% -- \"pico\" = pico de host_cpu_percent no run",
    fontsize=12, y=1.03,
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "49_host_saturacao_grid48.png")
fig.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"\nSalvo: {out_path}")
