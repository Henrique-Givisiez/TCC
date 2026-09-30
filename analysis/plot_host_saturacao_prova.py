import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Prova direta da teoria "o host satura em 8 núcleos e é aí que o erro
# explode": usa os 3 níveis de rps/atacante em WU=400000 (único WU no
# wu_calibration com host_cpu_percent, coletado depois da seção 37) --
# CPU do HOST inteiro ao longo do tempo, não do container, com o total
# de erros de cada nível anotado. Se a teoria estiver certa, a linha que
# fica colada em ~100% (todos os 8 núcleos lógicos ocupados) deve ser
# exatamente a que tem erro catastrófico.

WU_DIR = "experiment_results/wu_calibration"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
os.makedirs(OUT_DIR, exist_ok=True)

RPS_VALUES = [1, 5, 10]
COLOR = {1: "#2a78d6", 5: "#1baf7a", 10: "#d03b3b"}
WU = 400000

fig, ax = plt.subplots(figsize=(12, 7))

for rps in RPS_VALUES:
    mf = os.path.join(WU_DIR, f"metrics_rps{rps}_att4_WU{WU}.csv")
    df = pd.read_csv(mf)
    attack = df[df["label"] == "attack"]

    af = os.path.join(WU_DIR, f"attack_summary_log_{rps}_4_WU{WU}.csv")
    adf = pd.read_csv(af)
    adf = adf[adf["total_requests"].notna()]
    total_errors = int(adf["errors"].sum())

    ax.plot(attack["elapsed_time_s"], attack["host_cpu_percent"], color=COLOR[rps],
            linewidth=2, marker="o", markersize=3,
            label=f"rps/atacante={rps} -- {total_errors} erros no total")

ax.axhline(100, color="#333", linestyle="--", linewidth=1.2,
           label="100% = os 8 núcleos lógicos do host saturados")
ax.axhline(60, color="#999", linestyle=":", linewidth=1, alpha=0.7)

ax.set_ylim(0, 105)
ax.set_xlabel("tempo (s)")
ax.set_ylabel("CPU do HOST inteiro (%) -- não do container")
ax.set_title(
    "CPU do host durante o ataque (WU=400.000) -- prova da saturação de 8 núcleos\n"
    "A linha que gruda em ~100% é exatamente a que colapsa em erro"
)
ax.legend(loc="center right", fontsize=10)
ax.grid(True, alpha=0.3)

fig.tight_layout()
out_path = os.path.join(OUT_DIR, "19_host_saturacao_prova.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
