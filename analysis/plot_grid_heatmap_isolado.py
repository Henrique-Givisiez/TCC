import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Heatmap estilo gráfico 21 (ataque), mas para ATAQUE ISOLADO (sem
# tráfego normal) -- completa o trio de grids: 17 = só tráfego normal
# (clientes×RPS), 21 = ataque + 40 agregado de tráfego normal padrão
# (wu_calibration), este = só ataque (--normal-rps 0 de verdade).
#
# Fonte: experiment_results/desempate_combinado_isolado/ (seção 62/66),
# condição "isolado", que já tem 5 REPETIÇÕES por célula nas 9
# combinações (rps=1/5/10 × WU=100k/200k/400k) -- melhor que a amostra
# única de experiment_results/ataque_isolado/ (tarefa 5 original), por
# isso usado aqui em vez daquele. Cada célula mostra média±desvio de CPU
# (não 1 amostra só), RPS agregado, taxa de timeout, e nº máximo de
# instâncias observado entre as 5 repetições.

DESEMPATE_DIR = "experiment_results/desempate_combinado_isolado"
OUT_DIR = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
os.makedirs(OUT_DIR, exist_ok=True)

RPS_VALUES = [1, 5, 10]
WU_VALUES = [100000, 200000, 400000]
NUM_ATTACKERS = 4
NUM_REPS = 5

cpu_mean_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), np.nan)
cpu_std_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), np.nan)
timeout_rate_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), np.nan)
max_inst_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), 0)

for i, rps in enumerate(RPS_VALUES):
    for j, wu in enumerate(WU_VALUES):
        cpu_vals, timeout_vals, max_inst = [], [], 0
        for rep in range(1, NUM_REPS + 1):
            suffix = f"isolado_rps{rps}_att{NUM_ATTACKERS}_WU{wu}_rep{rep}"
            mf = os.path.join(DESEMPATE_DIR, f"metrics_{suffix}.csv")
            af = os.path.join(DESEMPATE_DIR, f"attack_summary_log_{suffix}.csv")
            if not os.path.exists(mf) or not os.path.exists(af):
                continue

            df = pd.read_csv(mf)
            attack = df[df["label"] == "attack"]
            cpu_vals.append(attack["average_cpu_percent"].mean())
            max_inst = max(max_inst, df["num_instances"].max())

            adf = pd.read_csv(af)
            adf = adf[adf["total_requests"].notna()]
            ok = adf["total_requests"].sum()
            timeouts = adf["errors"].sum()
            timeout_vals.append(100.0 * timeouts / (ok + timeouts) if (ok + timeouts) > 0 else 0.0)

        if cpu_vals:
            cpu_mean_matrix[i, j] = np.mean(cpu_vals)
            cpu_std_matrix[i, j] = np.std(cpu_vals, ddof=1) if len(cpu_vals) > 1 else 0.0
            timeout_rate_matrix[i, j] = np.mean(timeout_vals)
            max_inst_matrix[i, j] = max_inst

fig, ax = plt.subplots(figsize=(9, 7))
im = ax.imshow(cpu_mean_matrix, cmap="YlOrRd", aspect="auto", origin="upper")

ax.set_xticks(range(len(WU_VALUES)))
ax.set_xticklabels([f"WU={wu:,}".replace(",", ".") for wu in WU_VALUES])
ax.set_yticks(range(len(RPS_VALUES)))
ax.set_yticklabels([f"{r} rps/atacante" for r in RPS_VALUES])
ax.set_xlabel("work units por requisição de ataque")
ax.set_ylabel("RPS por atacante (4 atacantes fixos)")

for i, rps in enumerate(RPS_VALUES):
    for j, wu in enumerate(WU_VALUES):
        cpu_mean = cpu_mean_matrix[i, j]
        cpu_std = cpu_std_matrix[i, j]
        agregado = rps * NUM_ATTACKERS
        timeout_rate = timeout_rate_matrix[i, j]
        max_inst = int(max_inst_matrix[i, j])
        color = "white" if cpu_mean > np.nanmax(cpu_mean_matrix) * 0.6 else "black"
        label = (f"{cpu_mean:.1f}%±{cpu_std:.1f}\n{agregado} rps agregado\n"
                  f"{timeout_rate:.1f}% timeout\nmáx {max_inst} inst. (n=5)")
        ax.text(j, i, label, ha="center", va="center", color=color, fontsize=8)

cbar = fig.colorbar(im, ax=ax, label="CPU média do container (%, janelas de ataque)")
cbar.ax.invert_yaxis()

ax.set_title(
    "Grid de ataque ISOLADO (sem tráfego normal) -- CPU média por célula\n"
    "5 repetições/célula -- comparar com gráfico 21 (combinado)",
    fontsize=11,
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "28_grid_heatmap_isolado.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")

for i, rps in enumerate(RPS_VALUES):
    for j, wu in enumerate(WU_VALUES):
        print(f"  rps={rps:>2} WU={wu:>6}: cpu={cpu_mean_matrix[i,j]:6.1f}±{cpu_std_matrix[i,j]:4.1f}  "
              f"timeout={timeout_rate_matrix[i,j]:5.1f}%  max_inst={int(max_inst_matrix[i,j])}")
