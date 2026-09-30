import os
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Analisa o experimento de desempate (seção 60/61): combinado vs. isolado,
# mesma sessão, 5 repetições cada, rps=5/10 x WU=100k/200k/400k. Para cada
# célula, calcula média±desvio de (a) taxa de timeout e (b) fração de
# janelas com CPU do host >=90% -- as duas métricas usadas na
# investigação anterior. Se as barras de erro das duas condições se
# sobrepõem, a diferença observada antes é consistente com ruído/deriva
# de sessão; se ficarem claramente separadas mesmo dentro da mesma sessão,
# é evidência de um efeito real da presença de tráfego normal.

RESULTS_DIR = "experiment_results/desempate_combinado_isolado"
OUT_DIR = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
os.makedirs(OUT_DIR, exist_ok=True)

RPS_VALUES = [1, 5, 10]
WU_VALUES = [100000, 200000, 400000]
NUM_REPS = 5
COLOR = {"combinado": "#2a78d6", "isolado": "#d03b3b"}


def cell_stats(condicao, rps, wu):
    timeout_rates, frac_saturado = [], []
    for rep in range(1, NUM_REPS + 1):
        suffix = f"{condicao}_rps{rps}_att4_WU{wu}_rep{rep}"
        mf = os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")
        af = os.path.join(RESULTS_DIR, f"attack_summary_log_{suffix}.csv")
        if not os.path.exists(mf) or not os.path.exists(af):
            print(f"[WARNING] faltando dado para {suffix}")
            continue

        df = pd.read_csv(mf)
        hosts = df["host_cpu_percent"].iloc[1:] if "host_cpu_percent" in df.columns else pd.Series(dtype=float)
        if len(hosts):
            frac_saturado.append(100.0 * (hosts >= 90).sum() / len(hosts))

        adf = pd.read_csv(af)
        adf = adf[adf["total_requests"].notna()]
        ok = adf["total_requests"].sum()
        timeouts = adf["errors"].sum()
        rate = 100.0 * timeouts / (ok + timeouts) if (ok + timeouts) > 0 else 0.0
        timeout_rates.append(rate)

    return timeout_rates, frac_saturado


rows = []
for rps in RPS_VALUES:
    for wu in WU_VALUES:
        for condicao in ["combinado", "isolado"]:
            rates, fracs = cell_stats(condicao, rps, wu)
            if not rates:
                continue
            rows.append(dict(
                rps=rps, wu=wu, condicao=condicao, n=len(rates),
                timeout_mean=stats.mean(rates), timeout_std=stats.stdev(rates) if len(rates) > 1 else 0.0,
                sat_mean=stats.mean(fracs) if fracs else float("nan"),
                sat_std=stats.stdev(fracs) if len(fracs) > 1 else 0.0,
            ))

df = pd.DataFrame(rows)
pd.set_option("display.width", 160)
print(df.to_string(index=False))
csv_out = os.path.join(RESULTS_DIR, "resumo_desempate.csv")
df.to_csv(csv_out, index=False)
print(f"Salvo: {csv_out}")

fig, axes = plt.subplots(1, 2, figsize=(15, 6))

cells = [(rps, wu) for rps in RPS_VALUES for wu in WU_VALUES]
x = range(len(cells))
width = 0.35

for ax, metric, label in [(axes[0], "timeout_mean", "Taxa de timeout (%)"),
                           (axes[1], "sat_mean", "Janelas com CPU host ≥90% (%)")]:
    for k, condicao in enumerate(["combinado", "isolado"]):
        means, stds = [], []
        for rps, wu in cells:
            sub = df[(df["rps"] == rps) & (df["wu"] == wu) & (df["condicao"] == condicao)]
            if sub.empty:
                means.append(float("nan")); stds.append(0)
            else:
                means.append(sub[metric].values[0])
                stds.append(sub[metric.replace("mean", "std")].values[0])
        offset = (k - 0.5) * width
        ax.bar([xi + offset for xi in x], means, width=width, yerr=stds, capsize=4,
               color=COLOR[condicao], label=condicao)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"rps={r}\nWU={w:,}".replace(",", ".") for r, w in cells], fontsize=8)
    ax.set_ylabel(label)
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")

fig.suptitle(
    "Desempate combinado × isolado -- mesma sessão, 5 repetições/condição\n"
    "Barras de erro sobrepostas = diferença compatível com ruído; separadas = efeito real"
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "26_desempate_combinado_isolado.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
