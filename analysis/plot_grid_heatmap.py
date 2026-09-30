import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Heatmap do grid clientes×RPS: linhas = RPS agregado, colunas = nº de
# clientes, cor + número = CPU média do container naquela célula. Mostra
# a grade inteira de uma vez (30 células), em vez de resumida em linhas
# por decomposição (gráfico 11) -- se a hipótese "RPS agregado é o que
# importa" está certa, cada LINHA deveria ficar com cor quase uniforme,
# independente da coluna (nº de clientes). Reaproveita
# resumo_clients_rps_grid.csv, já calculado -- nenhum experimento novo.

GRID_DIR = "experiment_results/clients_rps_grid"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
os.makedirs(OUT_DIR, exist_ok=True)

AGGREGATE_TARGETS = [16, 32, 64, 128, 256, 512]
CLIENT_COUNTS = [1, 2, 4, 8, 16]

df = pd.read_csv(os.path.join(GRID_DIR, "resumo_clients_rps_grid.csv"))

# Matriz linha=agregado (ordem crescente de cima pra baixo -> inverte
# depois pro imshow ficar com 16 no topo), coluna=clientes.
matrix = np.full((len(AGGREGATE_TARGETS), len(CLIENT_COUNTS)), np.nan)
n_matrix = np.full((len(AGGREGATE_TARGETS), len(CLIENT_COUNTS)), 0)
max_inst_matrix = np.full((len(AGGREGATE_TARGETS), len(CLIENT_COUNTS)), 0)
for _, row in df.iterrows():
    i = AGGREGATE_TARGETS.index(int(row["target_aggregate"]))
    j = CLIENT_COUNTS.index(int(row["clients"]))
    matrix[i, j] = row["cpu_container_mean"]
    n_matrix[i, j] = row["n"]

    # Nº máximo de instâncias que essa célula chegou a escalar, olhando
    # direto nos CSVs brutos (não está no resumo) -- maior valor de
    # num_instances entre todas as repetições daquela célula.
    agg, clients = int(row["target_aggregate"]), int(row["clients"])
    files = glob.glob(os.path.join(GRID_DIR, f"metrics_agg{agg}_clients{clients}_WU10_rep*.csv"))
    max_inst = 0
    for f in files:
        max_inst = max(max_inst, pd.read_csv(f)["num_instances"].max())
    max_inst_matrix[i, j] = max_inst

fig, ax = plt.subplots(figsize=(9, 8))
im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto", origin="upper")

ax.set_xticks(range(len(CLIENT_COUNTS)))
ax.set_xticklabels([f"{c} cliente(s)" for c in CLIENT_COUNTS])
ax.set_yticks(range(len(AGGREGATE_TARGETS)))
ax.set_yticklabels([f"{a} RPS" for a in AGGREGATE_TARGETS])
ax.set_xlabel("nº de clientes (decomposição)")
ax.set_ylabel("RPS agregado alvo")

# Anota cada célula com o valor de CPU, o RPS/cliente que gerou aquela
# célula (agregado / nº de clientes -- a decomposição de verdade) e o nº
# de repetições válidas, quando diferente de 5.
for i in range(len(AGGREGATE_TARGETS)):
    for j in range(len(CLIENT_COUNTS)):
        val = matrix[i, j]
        if np.isnan(val):
            continue
        n = n_matrix[i, j]
        rps_per_client = AGGREGATE_TARGETS[i] / CLIENT_COUNTS[j]
        rps_str = f"{rps_per_client:g} rps/cli"
        max_inst = int(max_inst_matrix[i, j])
        color = "white" if val > np.nanmax(matrix) * 0.6 else "black"
        label = f"{val:.1f}%\n{rps_str}\nmáx {max_inst} inst."
        if n != 5:
            label += f" (n={n})"
        ax.text(j, i, label, ha="center", va="center", color=color, fontsize=8)

cbar = fig.colorbar(im, ax=ax, label="CPU média do container (%)")
# Barra de cor invertida: maior calor embaixo, menor em cima -- pedido do
# usuário (não muda o mapeamento cor<->valor, só a orientação da barra).
cbar.ax.invert_yaxis()

ax.set_title(
    "Grid clientes×RPS -- CPU média por célula\n"
    "Cada LINHA deveria ficar com cor uniforme, se RPS agregado é o que importa"
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "17_grid_heatmap_cpu.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
