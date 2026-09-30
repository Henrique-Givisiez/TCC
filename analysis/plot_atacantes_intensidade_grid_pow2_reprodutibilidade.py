import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator import config

# Consolidação das 5 repetições (rep1 original + rep2-rep5 disparadas na
# seção 96 do changes.txt) para os 4 cenários de potência de 2
# (S1/S6/S7/S8 = 40/80/160/320 agregado). Mesma estrutura de painéis do
# gráfico 53/54 (1x4, linhas = nº de atacantes, colunas = intensidade),
# mas agora cada célula mostra média ± desvio-padrão da CPU média de cada
# run sobre as 5 repetições, e quantas das 5 dispararam SCALE_UP (n/5) --
# mesmo padrão de reprodutibilidade já usado nos gráficos 16-18 do
# projeto. Objetivo: checar se os padrões não-monotônicos vistos com 1 rep
# (ex. S1/2 atacantes/10% vs 15%) se sustentam com mais repetições ou eram
# ruído de amostragem (ver changes.txt, diagnóstico anterior).

GRID_DIR = "experiment_results/atacantes_intensidade_grid"
OUT_DIR = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
os.makedirs(OUT_DIR, exist_ok=True)

NORMAL_SCENARIOS = {
    "S1": 40, "S6": 80, "S7": 160, "S8": 320,
}
ATTACKERS_VALUES = [1, 2, 4]
INTENSITIES_PCT = [1, 5, 10, 15, 20, 25]
WORK_UNITS = 200000
REPS = [1, 2, 3, 4, 5]


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
            mean_cpus, escalou_flags, timeouts = [], [], []
            for rep in REPS:
                suffix = f"{scenario}_atk{pct}pct_att{attackers}_wu{WORK_UNITS}_rep{rep}"
                mf = os.path.join(GRID_DIR, f"metrics_{suffix}.csv")
                if not os.path.exists(mf):
                    print(f"[AVISO] faltando: {mf}")
                    continue
                df = pd.read_csv(mf).iloc[1:]
                mean_cpus.append(df["average_cpu_percent"].mean())
                escalou_flags.append(bool((df["decision"] == "SCALE_UP").any()))
                to = timeout_rate(suffix)
                if to is not None:
                    timeouts.append(to)
            if not mean_cpus:
                continue
            rows.append(dict(
                scenario=scenario, attackers=attackers, pct=pct,
                cpu_mean=np.mean(mean_cpus), cpu_std=np.std(mean_cpus),
                n_escalou=sum(escalou_flags), n_total=len(escalou_flags),
                timeout_mean=np.mean(timeouts) if timeouts else 0.0,
            ))

grid = pd.DataFrame(rows)
print(grid.to_string(index=False))

n_scen = len(NORMAL_SCENARIOS)
fig, axes = plt.subplots(1, n_scen, figsize=(6.5 * n_scen, 5.6), squeeze=False)
axes = axes.flatten()
vmax = max(grid["cpu_mean"].max(), config.CPU_THRESHOLD_SCALE_UP)

for ax, (scenario, agg) in zip(axes, NORMAL_SCENARIOS.items()):
    mat = np.full((len(ATTACKERS_VALUES), len(INTENSITIES_PCT)), np.nan)
    std_mat = np.full((len(ATTACKERS_VALUES), len(INTENSITIES_PCT)), np.nan)
    n_esc_mat = np.zeros((len(ATTACKERS_VALUES), len(INTENSITIES_PCT)), dtype=int)
    n_tot_mat = np.zeros((len(ATTACKERS_VALUES), len(INTENSITIES_PCT)), dtype=int)
    to_mat = np.full((len(ATTACKERS_VALUES), len(INTENSITIES_PCT)), np.nan)
    sub = grid[grid.scenario == scenario]
    for i, att in enumerate(ATTACKERS_VALUES):
        for j, pct in enumerate(INTENSITIES_PCT):
            cell = sub[(sub.attackers == att) & (sub.pct == pct)]
            if len(cell):
                mat[i, j] = cell["cpu_mean"].values[0]
                std_mat[i, j] = cell["cpu_std"].values[0]
                n_esc_mat[i, j] = cell["n_escalou"].values[0]
                n_tot_mat[i, j] = cell["n_total"].values[0]
                to_mat[i, j] = cell["timeout_mean"].values[0]

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
            to = to_mat[i, j]
            to_str = f"\n{to:.0f}% to" if to and to > 0.5 else ""
            cor_texto = "white" if mat[i, j] > vmax * 0.6 else "black"
            ax.text(j, i, f"{mat[i, j]:.0f}±{std_mat[i, j]:.0f}%\n"
                           f"{n_esc_mat[i, j]}/{n_tot_mat[i, j]} escalou{to_str}",
                    ha="center", va="center",
                    color=cor_texto, fontsize=7.5, fontweight="bold")

axes[0].set_ylabel("Nº de atacantes")
fig.suptitle(
    "Reprodutibilidade (5 reps) -- CPU média ± desvio-padrão, potência de 2 "
    "(40/80/160/320 agregado, WU=200.000)\n"
    "\"n/5 escalou\" = quantas repetições dispararam SCALE_UP -- \"to\" = % de timeout médio quando > 0.5%",
    fontsize=11.5, y=1.04,
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "56_atacantes_intensidade_grid_pow2_reprodutibilidade.png")
fig.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"\nSalvo: {out_path}")
