import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Pedido do usuário: "prove visualmente" a explicação de clustering
# Poisson para os picos de CPU anômalos (agg=160 e agg=320/rep4). Usa
# timestamps REAIS de pacotes (traffic_capture_*.csv, capturados por
# tcpdump_sniffer.py, timestamp = segundos desde o início da simulação --
# mesmo relógio de elapsed_time_s em metrics.csv) dessas execuções
# específicas -- não é uma re-simulação, é o dado que realmente aconteceu.
#
# Resultado ao investigar: a explicação de "clustering por acaso"
# SE CONFIRMA no caso agg=160 (rajada de pacotes pouco antes do pico),
# mas NÃO se confirma no caso agg=320/rep4 -- lá aconteceu o oposto
# (menos requisições chegaram, não mais), revelando outro mecanismo
# (atraso de início, não clustering). Os dois gráficos mostram isso
# lado a lado, com honestidade sobre qual explicação vale pra qual caso.

NB_DIR = "experiment_results/normal_baseline"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
GREEN = "#1baf7a"
RED = "#d03b3b"
GRAY = "#888888"
ORANGE = "#e08a1e"


def carregar_requisicoes(agg, rep):
    df = pd.read_csv(os.path.join(NB_DIR, f"traffic_capture_normal_agg{agg}_WU10_refined_rep{rep}.csv"))
    return df[df["dst_port"] == 8080].copy()


# ---------------------------------------------------------------------
# Gráfico 43: agg=320 -- primeiros 6s, comparando rep1/rep4/rep5
# CONCLUSÃO: rep4 tem MENOS requisições no início, não mais -- o pico de
# 127% não é clustering, é outra coisa (provável atraso de início do
# container/servidor, não coberto por este gráfico).
# ---------------------------------------------------------------------
fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
picos_320 = {1: 84.13, 4: 127.82, 5: 83.48}
cores_320 = {1: BLUE, 4: RED, 5: BLUE}
bins = np.arange(0, 6.25, 0.25)

for ax, rep in zip(axes, [1, 4, 5]):
    reqs = carregar_requisicoes(320, rep)
    reqs = reqs[reqs["timestamp"] <= 6.0]
    counts, edges = np.histogram(reqs["timestamp"], bins=bins)
    ax.bar(edges[:-1], counts, width=0.23, align="edge", color=cores_320[rep], alpha=0.85)
    ax.axvline(5.0, color="#333", linestyle=":", linewidth=1)
    ax.set_ylabel("reqs/0.25s")
    ax.set_ylim(0, 16)
    total = len(reqs)
    ax.text(0.98, 0.85, f"rep{rep}: {total} requisições em 6s -- CPU no t=5s: {picos_320[rep]}%",
            transform=ax.transAxes, ha="right", va="top", fontsize=10, fontweight="bold")

axes[0].text(5.05, 14, "t=5s\n(1ª leitura\nde CPU)", fontsize=8, color="#333")
axes[-1].set_xlabel("segundos desde o início da simulação")
fig.suptitle(
    "Prova com pacotes reais (tcpdump) -- agg=320: a rep4 teve MENOS requisições, não mais\n"
    "Contradiz a hipótese de \"clustering por acaso\" -- o pico de 127% tem outra causa",
    fontsize=12,
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "43_prova_pacotes_agg320_pico_isolado.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")

# CSV com os dados binados, pra transparência
rows = []
for rep in [1, 4, 5]:
    reqs = carregar_requisicoes(320, rep)
    reqs = reqs[reqs["timestamp"] <= 6.0]
    counts, edges = np.histogram(reqs["timestamp"], bins=bins)
    for edge, c in zip(edges[:-1], counts):
        rows.append(dict(rep=rep, janela_inicio_s=round(edge, 2), n_requisicoes=int(c)))
csv_path = os.path.join(OUT_DIR, "43_prova_pacotes_agg320_pico_isolado.csv")
pd.DataFrame(rows).to_csv(csv_path, index=False)
print(f"Salvo: {csv_path}")


# ---------------------------------------------------------------------
# Gráfico 44: agg=160 -- janela de 6s em torno do PRÓPRIO pico de cada rep
# CONCLUSÃO: aqui SIM aparece uma rajada real pouco antes do pico nas
# repetições que escalam (rep4, rep5) -- confirma o clustering Poisson
# neste caso.
# ---------------------------------------------------------------------
janelas_160 = {1: (15, 21, 57.37, False), 4: (60, 66, 71.63, True), 5: (160, 166, 79.05, True)}

fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=False)
for ax, rep in zip(axes, [1, 4, 5]):
    t0, t1, pico, escalou = janelas_160[rep]
    reqs = carregar_requisicoes(160, rep)
    reqs = reqs[(reqs["timestamp"] >= t0) & (reqs["timestamp"] <= t1)]
    bins_local = np.arange(t0, t1 + 0.25, 0.25)
    counts, edges = np.histogram(reqs["timestamp"], bins=bins_local)
    cor = GREEN if escalou else GRAY
    ax.bar(edges[:-1], counts, width=0.23, align="edge", color=cor, alpha=0.85)
    peak_t = t0 + 5.0  # a leitura de CPU ocorre 5s após o início da janela mostrada
    ax.axvline(peak_t, color="#333", linestyle=":", linewidth=1)
    status = "ESCALOU" if escalou else "não escalou"
    ax.text(0.98, 0.85, f"rep{rep} ({status}): pico de CPU={pico}% em t={peak_t:.0f}s",
            transform=ax.transAxes, ha="right", va="top", fontsize=10, fontweight="bold")
    ax.set_ylabel("reqs/0.25s")
    ax.set_xlabel(f"segundos desde o início da simulação (janela t={t0}-{t1})")

fig.suptitle(
    "Prova com pacotes reais (tcpdump) -- agg=160: rajada real pouco antes do pico\n"
    "nas repetições que escalaram -- aqui SIM confirma o clustering por acaso (Poisson)",
    fontsize=12,
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "44_prova_pacotes_agg160_transicao.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")

rows = []
for rep in [1, 4, 5]:
    t0, t1, pico, escalou = janelas_160[rep]
    reqs = carregar_requisicoes(160, rep)
    reqs = reqs[(reqs["timestamp"] >= t0) & (reqs["timestamp"] <= t1)]
    bins_local = np.arange(t0, t1 + 0.25, 0.25)
    counts, edges = np.histogram(reqs["timestamp"], bins=bins_local)
    for edge, c in zip(edges[:-1], counts):
        rows.append(dict(rep=rep, escalou=escalou, janela_inicio_s=round(edge, 2), n_requisicoes=int(c)))
csv_path = os.path.join(OUT_DIR, "44_prova_pacotes_agg160_transicao.csv")
pd.DataFrame(rows).to_csv(csv_path, index=False)
print(f"Salvo: {csv_path}")
