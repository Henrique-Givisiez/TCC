import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Heatmap estilo gráfico 17, mas para o grid de ATAQUE (wu_calibration --
# dado já existente, nenhum experimento novo): linhas = rps/atacante
# (1/5/10), colunas = WU (100k/200k/400k), cor + número = CPU média
# (janelas de ataque). Cada célula anota: CPU média, RPS agregado
# (rps/atacante x 4 atacantes), taxa de timeout, e nº máximo de
# instâncias que aquela combinação chegou a escalar.
#
# Diferença em relação ao 17: aqui não há repetição (1 amostra/célula,
# mesma limitação do gráfico 05/wu_calibration original) e as duas
# dimensões (rps, WU) contribuem pra "severidade", não só uma delas --
# então "cada linha uniforme" não é a leitura esperada aqui como era no
# 17 (que testava invariância); esse heatmap é descritivo, não um teste
# de hipótese.

WU_DIR = "experiment_results/wu_calibration"
OUT_DIR = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
os.makedirs(OUT_DIR, exist_ok=True)

RPS_VALUES = [1, 5, 10]
WU_VALUES = [100000, 200000, 400000]
NUM_ATTACKERS = 4

cpu_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), np.nan)
timeout_rate_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), np.nan)
max_inst_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), 0)

for i, rps in enumerate(RPS_VALUES):
    for j, wu in enumerate(WU_VALUES):
        mf = os.path.join(WU_DIR, f"metrics_rps{rps}_att4_WU{wu}.csv")
        df = pd.read_csv(mf)
        attack = df[df["label"] == "attack"]
        cpu_matrix[i, j] = attack["average_cpu_percent"].mean()
        max_inst_matrix[i, j] = df["num_instances"].max()

        af = os.path.join(WU_DIR, f"attack_summary_log_{rps}_4_WU{wu}.csv")
        adf = pd.read_csv(af)
        adf = adf[adf["total_requests"].notna()]
        ok = adf["total_requests"].sum()
        timeouts = adf["errors"].sum()
        timeout_rate_matrix[i, j] = 100.0 * timeouts / (ok + timeouts) if (ok + timeouts) > 0 else 0.0

fig, ax = plt.subplots(figsize=(9, 7))
im = ax.imshow(cpu_matrix, cmap="YlOrRd", aspect="auto", origin="upper")

ax.set_xticks(range(len(WU_VALUES)))
ax.set_xticklabels([f"WU={wu:,}".replace(",", ".") for wu in WU_VALUES])
ax.set_yticks(range(len(RPS_VALUES)))
ax.set_yticklabels([f"{r} rps/atacante" for r in RPS_VALUES])
ax.set_xlabel("work units por requisição de ataque")
ax.set_ylabel("RPS por atacante (4 atacantes fixos)")

for i, rps in enumerate(RPS_VALUES):
    for j, wu in enumerate(WU_VALUES):
        cpu = cpu_matrix[i, j]
        agregado = rps * NUM_ATTACKERS
        timeout_rate = timeout_rate_matrix[i, j]
        max_inst = int(max_inst_matrix[i, j])
        color = "white" if cpu > np.nanmax(cpu_matrix) * 0.6 else "black"
        label = f"{cpu:.1f}%\n{agregado} rps agregado\n{timeout_rate:.1f}% timeout\nmáx {max_inst} inst."
        ax.text(j, i, label, ha="center", va="center", color=color, fontsize=8.5)

cbar = fig.colorbar(im, ax=ax, label="CPU média do container (%, janelas de ataque)")
cbar.ax.invert_yaxis()

ax.set_title(
    "Grid de ataque (wu_calibration) -- CPU média por célula\n"
    "1 amostra/célula -- descritivo, não teste de invariância (ver gráfico 17)"
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "21_grid_heatmap_ataque.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
