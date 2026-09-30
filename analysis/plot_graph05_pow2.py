import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Mesmo gráfico 05 (CPU média + erros) da seção 36 (regenerate_graficos_04_05_media.py),
# mas com WU={100000,200000,400000} em vez de {100000,200000,500000} -- pedido
# do usuário para seguir progressão de potência de 2 (100k -> 200k -> 400k)
# em vez do salto "esquisito" original (100k -> 200k -> 500k). Não sobrescreve
# nenhum gráfico anterior -- nome de arquivo novo.
#
# Precisa que run_wu400000_only.py já tenha rodado (gera os 3 CSVs de
# WU=400000 que faltam em experiment_results/wu_calibration/).

WU_DIR = "experiment_results/wu_calibration"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
GREEN = "#1baf7a"
RED = "#d03b3b"


def mean_cpu(path, label_filter="attack"):
    df = pd.read_csv(path).iloc[1:]
    df = df[df["label"] == label_filter]
    return df["average_cpu_percent"].mean()


rps_values = [1, 5, 10]
wu_values = [100000, 200000, 400000]
colors = {100000: BLUE, 200000: GREEN, 400000: RED}

mean_cpu_grid, err_grid = {}, {}
for rps in rps_values:
    for wu in wu_values:
        mf = os.path.join(WU_DIR, f"metrics_rps{rps}_att4_WU{wu}.csv")
        if not os.path.exists(mf):
            raise SystemExit(f"Faltando {mf} -- rode run_wu400000_only.py antes deste script.")
        mean_cpu_grid[(rps, wu)] = mean_cpu(mf)

        af = os.path.join(WU_DIR, f"attack_summary_log_{rps}_4_WU{wu}.csv")
        adf = pd.read_csv(af)
        adf = adf[adf["total_requests"].notna()]
        err_grid[(rps, wu)] = adf["errors"].sum()

fig, axes = plt.subplots(1, 2, figsize=(15, 6))

x = range(len(rps_values))
width = 0.25
for i, wu in enumerate(wu_values):
    vals = [mean_cpu_grid[(rps, wu)] for rps in rps_values]
    offset = (i - 1) * width
    axes[0].bar([xi + offset for xi in x], vals, width=width, color=colors[wu],
                label=f"WU={wu:,}".replace(",", "."))
axes[0].axhline(60, color=RED, linestyle="--", linewidth=1)
axes[0].set_xticks(list(x))
axes[0].set_xticklabels([f"rps={r}" for r in rps_values])
axes[0].set_ylabel("CPU média (%) -- só janelas de ataque")
axes[0].set_title("wu_calibration -- CPU MÉDIA, WU em potência de 2 (100k/200k/400k)")
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

fig.suptitle("wu_calibration -- WU em progressão de potência de 2 (100k/200k/400k)")
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "05_wu_calibration_resumo_POW2.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
for rps in rps_values:
    for wu in wu_values:
        print(f"  rps={rps:>2} WU={wu:>6}: media={mean_cpu_grid[(rps,wu)]:6.1f}  erros={err_grid[(rps,wu)]:6.0f}")
