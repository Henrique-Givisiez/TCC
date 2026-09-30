import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator import config

# Investigação pedida pelo usuário: a hipótese de "saturação de CPU do host"
# (gráfico 19/49) não explica a maior parte das células anômalas do grid 48
# -- ex. S4/1 atacante/15% tem pico de host_cpu_percent de só 42% mas 100%
# de timeout. Hipótese alternativa: fila/backlog de requisições (no
# ProcessPoolExecutor do servidor e/ou no _send_pool do cliente, ambos sem
# limite de tamanho de fila) crescendo sem que a CPU precise saturar, porque
# o trabalho por requisição (WU=200000, mais leve que os WU=400000 do
# gráfico 19) é curto -- o gargalo pode ser concorrência/backlog, não CPU.
#
# Este script reconstrói, a partir do rtt_log já coletado (sem novo
# Docker), a concorrência aproximada de requisições "em voo" ao longo do
# tempo: cada linha de rtt_log.csv é uma requisição BEM-SUCEDIDA, com
# timestamp = instante de conclusão (time.time()) e rtt = duração em ms
# (ver normal_traffic.py/_send_one_normal e traffic_injectorV0.py/_send_one).
# início reconstruído = timestamp - rtt/1000. Uma varredura de eventos
# (+1 no início, -1 no fim) dá o número de requisições simultaneamente em
# andamento a cada instante -- se esse número disparar muito acima da
# capacidade conhecida do servidor (num_instances x
# INSTANCE_MAX_CONCURRENT_REQUESTS) ou do _send_pool do cliente
# (HTTP_NORMAL_MAX_CONCURRENT_SENDS=64), é evidência direta de fila/backlog.
#
# Célula analisada: S4 (300 rps agregado normal), 1 atacante, 15% de
# intensidade, WU=200000, rep1 -- a mais gritante encontrada no gráfico 49
# (pico host_cpu_percent=42%, 100% timeout). Dados de
# experiment_results/atacantes_intensidade_grid/.

GRID_DIR = "experiment_results/atacantes_intensidade_grid"
OUT_DIR = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
os.makedirs(OUT_DIR, exist_ok=True)

SUFFIX = "S4_atk15pct_att1_wu200000_rep1"
INSTANCE_CAP = config.INSTANCE_MAX_CONCURRENT_REQUESTS
SEND_POOL_CAP = config.HTTP_NORMAL_MAX_CONCURRENT_SENDS

rtt = pd.read_csv(os.path.join(GRID_DIR, f"rtt_log_{SUFFIX}.csv"))
metrics = pd.read_csv(os.path.join(GRID_DIR, f"metrics_{SUFFIX}.csv"))

# --- Reconstrução da concorrência a partir do rtt_log ---
rtt["end"] = rtt["timestamp"]
rtt["start"] = rtt["timestamp"] - rtt["rtt"] / 1000.0
t0 = rtt["start"].min()
rtt["start_rel"] = rtt["start"] - t0
rtt["end_rel"] = rtt["end"] - t0

events = pd.concat([
    pd.DataFrame({"t": rtt["start_rel"], "delta": 1}),
    pd.DataFrame({"t": rtt["end_rel"], "delta": -1}),
]).sort_values("t")
events["concurrency"] = events["delta"].cumsum()

max_conc = events["concurrency"].max()
frac_above_sendpool = 100.0 * (events["concurrency"] > SEND_POOL_CAP).mean()
print(f"Concorrência reconstruída (rtt_log, {len(rtt)} requisições bem-sucedidas):")
print(f"  pico = {max_conc:.0f}  |  limite do _send_pool do cliente = {SEND_POOL_CAP}")
print(f"  % de eventos com concorrência > {SEND_POOL_CAP} (limite do _send_pool): {frac_above_sendpool:.1f}%")

# Capacidade dinâmica do servidor ao longo do tempo (num_instances x INSTANCE_MAX_CONCURRENT_REQUESTS)
metrics["server_cap"] = metrics["num_instances"] * INSTANCE_CAP
scale_up_ticks = metrics.loc[metrics["decision"] == "SCALE_UP", "elapsed_time_s"]

# --- Figura: 2 painéis ---
fig, (ax_conc, ax_rtt) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)

ax_conc.step(events["t"], events["concurrency"], where="post", color="tab:blue", lw=0.8,
             label="Concorrência reconstruída (rtt_log)")
ax_conc.step(metrics["elapsed_time_s"], metrics["server_cap"], where="post", color="black",
             lw=1.5, linestyle="--", label=f"Capacidade do servidor (instâncias x {INSTANCE_CAP})")
ax_conc.axhline(SEND_POOL_CAP, color="tab:red", lw=1.5, linestyle=":",
                label=f"Limite do _send_pool do cliente ({SEND_POOL_CAP})")
for t in scale_up_ticks:
    ax_conc.axvline(t, color="green", lw=0.8, alpha=0.5)
ax_conc.axvspan(config.ATTACK_START_TIME_SECONDS,
                config.ATTACK_START_TIME_SECONDS + config.PULSE_DURATION,
                color="orange", alpha=0.08, label="Janela do ataque")
ax_conc.set_ylabel("Nº de requisições em voo (reconstruído)")
ax_conc.set_title(f"Concorrência reconstruída x capacidade -- {SUFFIX}\n"
                   "(linhas verdes = SCALE_UP disparado)")
ax_conc.legend(loc="upper left", fontsize=8)

ax_rtt.scatter(rtt["end_rel"], rtt["rtt"], s=2, alpha=0.3, color="tab:blue")
ax_rtt.axhline(2000, color="tab:red", lw=1.2, linestyle=":", label="Timeout do cliente (2000 ms)")
ax_rtt.axvspan(config.ATTACK_START_TIME_SECONDS,
               config.ATTACK_START_TIME_SECONDS + config.PULSE_DURATION,
               color="orange", alpha=0.08)
ax_rtt.set_xlabel("Tempo decorrido (s, reconstruído a partir do rtt_log)")
ax_rtt.set_ylabel("RTT (ms) das requisições bem-sucedidas")
ax_rtt.set_yscale("log")
ax_rtt.legend(loc="upper left", fontsize=8)

fig.tight_layout()
out_path = os.path.join(OUT_DIR, "50_fila_processpool_S4_att1_15pct.png")
fig.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"\nSalvo: {out_path}")
