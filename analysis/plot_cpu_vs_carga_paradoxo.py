import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator import config

# Gráfico pedido pelo usuário para sustentar, na defesa, a explicação do
# padrão contraintuitivo do gráfico 48: cenários com mais RPS agregado (ou
# mais intensidade de ataque) às vezes mostram um PICO DE CPU MENOR do que
# cenários mais leves -- porque, quando o autoscaler trava/oscila em poucas
# instâncias (seções 90-92 do changes.txt), a maior parte do tráfego em
# excesso falha/expira ANTES de virar trabalho de CPU. Pico de CPU aqui
# mede trabalho concluído, não carga ofertada -- então, sob colapso, mais
# carga ofertada pode produzir MENOS CPU medida, não mais.
#
# Este gráfico junta as 144 células do grid 48 num único scatter: eixo X =
# carga total ofertada (rps agregado normal + rps agregado de ataque), eixo
# Y = pico de CPU do container, cor = % de timeout. Numa relação "saudável"
# (sem colapso), pico de CPU deveria crescer com a carga ofertada. Pontos
# de timeout alto que aparecem MUITO abaixo de onde os pontos saudáveis de
# carga parecida estão são exatamente a assinatura do paradoxo.
#
# Fonte: experiment_results/atacantes_intensidade_grid/ (mesmas 144
# execuções do gráfico 48). Só leitura, nenhum Docker novo.

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
                continue
            df = pd.read_csv(mf).iloc[1:]
            peak_cpu = df["average_cpu_percent"].max()
            attack_rps = agg * pct / 100.0
            rows.append(dict(
                scenario=scenario, attackers=attackers, pct=pct,
                carga_ofertada=agg + attack_rps,
                peak_cpu=peak_cpu,
                timeout_pct=timeout_rate(suffix) or 0.0,
            ))

grid = pd.DataFrame(rows)

fig, ax = plt.subplots(figsize=(10, 7))
sc = ax.scatter(grid["carga_ofertada"], grid["peak_cpu"], c=grid["timeout_pct"],
                 cmap="Reds", vmin=0, vmax=100, s=45, edgecolors="black", linewidths=0.3)
cbar = fig.colorbar(sc, ax=ax)
cbar.set_label("% de timeout")

ax.axhline(config.CPU_THRESHOLD_SCALE_UP, color="tab:blue", lw=1, linestyle="--",
           label=f"Limiar de SCALE_UP ({config.CPU_THRESHOLD_SCALE_UP:.0f}%)")
ax.axhline(config.CPU_THRESHOLD_SCALE_DOWN, color="tab:orange", lw=1, linestyle="--",
           label=f"Limiar de SCALE_DOWN ({config.CPU_THRESHOLD_SCALE_DOWN:.0f}%)")

# Destaca os pontos de colapso (timeout alto) para reforçar o contraste visual.
colapso = grid[grid["timeout_pct"] > 50]
ax.scatter(colapso["carga_ofertada"], colapso["peak_cpu"], facecolors="none",
           edgecolors="black", s=130, linewidths=1.2, label="Timeout > 50% (colapso)")

ax.set_xlabel("Carga total ofertada (rps agregado normal + ataque)")
ax.set_ylabel("Pico de CPU do container durante o run (%)")
ax.set_title(
    "Pico de CPU x carga ofertada, colorido por timeout -- as 144 células do grid 48\n"
    "Pontos de colapso (contorno preto) caem ABAIXO do que a carga ofertada faria esperar:\n"
    "pico de CPU mede trabalho concluído, não carga recebida"
)
ax.legend(loc="upper left", fontsize=9)
fig.tight_layout()

out_path = os.path.join(OUT_DIR, "52_cpu_vs_carga_paradoxo.png")
fig.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"Salvo: {out_path}")
print(grid.sort_values("carga_ofertada").to_string(index=False))
