import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Mesmo gráfico 05 em potência de 2 (plot_graph05_pow2.py), mas com CPU DE
# PICO em vez de média -- pedido do usuário, para comparar com o estilo do
# gráfico 05 original (que também era por pico). WU={100000,200000,400000},
# não sobrescreve o gráfico 05 nem a versão _POW2 já existente (média).
#
# Só 1 repetição por combinação (mesmo dado de wu_calibration/, que nunca
# teve repetição) -- assim como o gráfico 05 original, este é ilustrativo
# do mecanismo (pico vs média, discutido com o usuário), não uma medida
# estatística robusta feita com múltiplas repetições.

WU_DIR = "experiment_results/wu_calibration"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
GREEN = "#1baf7a"
RED = "#d03b3b"


def peak_cpu(path, label_filter="attack"):
    df = pd.read_csv(path).iloc[1:]
    df = df[df["label"] == label_filter]
    return df["average_cpu_percent"].max()


rps_values = [1, 5, 10]
wu_values = [100000, 200000, 400000]
colors = {100000: BLUE, 200000: GREEN, 400000: RED}

peak_cpu_grid, err_grid = {}, {}
for rps in rps_values:
    for wu in wu_values:
        mf = os.path.join(WU_DIR, f"metrics_rps{rps}_att4_WU{wu}.csv")
        if not os.path.exists(mf):
            raise SystemExit(f"Faltando {mf} -- rode run_wu400000_only.py antes deste script.")
        peak_cpu_grid[(rps, wu)] = peak_cpu(mf)

        af = os.path.join(WU_DIR, f"attack_summary_log_{rps}_4_WU{wu}.csv")
        adf = pd.read_csv(af)
        adf = adf[adf["total_requests"].notna()]
        err_grid[(rps, wu)] = adf["errors"].sum()

fig, axes = plt.subplots(1, 2, figsize=(15, 6))

x = range(len(rps_values))
width = 0.25
for i, wu in enumerate(wu_values):
    vals = [peak_cpu_grid[(rps, wu)] for rps in rps_values]
    offset = (i - 1) * width
    axes[0].bar([xi + offset for xi in x], vals, width=width, color=colors[wu],
                label=f"WU={wu:,}".replace(",", "."))
axes[0].axhline(60, color=RED, linestyle="--", linewidth=1, label="limiar SCALE_UP (60%)")
axes[0].set_xticks(list(x))
axes[0].set_xticklabels([f"rps={r}" for r in rps_values])
axes[0].set_ylabel("CPU de pico (%) -- só janelas de ataque")
axes[0].set_title("wu_calibration -- CPU DE PICO, WU em potência de 2 (100k/200k/400k)")
axes[0].legend()
axes[0].grid(True, alpha=0.3, axis="y")

for i, wu in enumerate(wu_values):
    vals = [err_grid[(rps, wu)] for rps in rps_values]
    offset = (i - 1) * width
    axes[1].bar([xi + offset for xi in x], vals, width=width, color=colors[wu],
                label=f"WU={wu:,}".replace(",", "."))
axes[1].set_xticks(list(x))
axes[1].set_xticklabels([f"rps={r}" for r in rps_values])
axes[1].set_ylabel("Total de erros de requisição")
axes[1].set_title("wu_calibration -- falhas de requisição")
axes[1].legend()
axes[1].grid(True, alpha=0.3, axis="y")

fig.suptitle("wu_calibration -- WU em potência de 2, ESTATÍSTICA DE PICO (1 amostra/ponto)")
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "15_wu_calibration_resumo_pico_pow2.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
for rps in rps_values:
    for wu in wu_values:
        print(f"  rps={rps:>2} WU={wu:>6}: pico={peak_cpu_grid[(rps,wu)]:6.1f}  erros={err_grid[(rps,wu)]:6.0f}")
