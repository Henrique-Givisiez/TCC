import glob
import os
import re
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Gráfico 04 refinado: lê os dados novos gerados por run_graph4_refined.py
# (5 repetições por RPS agregado, código atual -- já grava taxa de erro e
# CPU do host, ausentes nos dados originais do gráfico 04, ver changes.txt).
# Não toca nos gráficos antigos (04_curva_capacidade_reproducibilidade.png,
# ..._MEDIA.png) -- salva com nome novo, para comparação lado a lado.
#
# Estatística deliberadamente simples (pedido do usuário): média ±
# desvio-padrão entre repetições, e coeficiente de correlação de Pearson
# como argumento de apoio -- sem testes de hipótese formais.

NB_DIR = "experiment_results/normal_baseline"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
RED = "#d03b3b"
GRAY = "#666666"


def cpu_means(metrics_path):
    """Retorna (media CPU container, media CPU host) de uma execução,
    descartando a 1a linha (t=0, sempre 0.0/0.0 antes do trafego/da 1a
    leitura de host_stats)."""
    df = pd.read_csv(metrics_path).iloc[1:]
    cpu_container = df["average_cpu_percent"].mean()
    cpu_host = df["host_cpu_percent"].mean() if "host_cpu_percent" in df.columns else float("nan")
    return cpu_container, cpu_host


def error_rate_and_quality(summary_path, num_clients=4, target_duration=180, duration_tolerance_s=10):
    """Taxa de erro (%) de uma execução, mais sinalizadores de qualidade --
    não é teste estatístico, só checagem simples de completude: menos
    linhas de worker-stop do que clientes configurados, OU alguma thread
    tendo levado bem mais tempo que o alvo (180s + tolerância) para
    terminar. Sintoma real já visto neste grid (ver changes.txt) --
    indício de soluço transitório de ambiente no meio da execução, não um
    efeito real do RPS agregado testado.

    Duas severidades, tratadas diferente:
    - PARCIAL (algumas linhas faltando, mas pelo menos 1 presente): CPU
      (container/host, fonte separada) segue normal nesses casos
      (confirmado olhando a série temporal de um caso real, agg=250 rep1)
      -- só a taxa de erro é excluída.
    - TOTAL (nenhuma linha de worker-stop): confirmado num caso real
      (agg=250 rep6) que a CPU TAMBÉM fica anormal nesse caso (baixa e
      nunca escala, o tempo todo, não só um blip) -- indício de que o
      tráfego realmente não foi gerado direito desde o início, não é só
      falha de log no final. Por isso runs totalmente vazios voltam com
      fully_empty=True, e o chamador deve excluir também da CPU."""
    if not os.path.exists(summary_path):
        return float("nan"), True, True, "arquivo de resumo ausente"
    df = pd.read_csv(summary_path)
    df = df[df["total_requests"].notna()]
    if df.empty:
        return float("nan"), True, True, "nenhuma linha de worker-stop (CPU também afetada, ver changes.txt)"

    ok = df["total_requests"].sum()
    err = df["errors"].sum()
    rate = 100.0 * err / (ok + err) if (ok + err) > 0 else float("nan")

    if len(df) < num_clients:
        return rate, True, False, f"só {len(df)}/{num_clients} threads logaram o fim"

    max_elapsed = df["elapsed_time_s"].max()
    if max_elapsed > target_duration + duration_tolerance_s:
        return rate, True, False, f"duração {max_elapsed:.0f}s > alvo ({target_duration}s) + {duration_tolerance_s}s de tolerância"

    return rate, False, False, None


AGGREGATE_TARGETS = [40, 100, 200, 250, 300, 400]

rows = []
for agg in AGGREGATE_TARGETS:
    metric_files = sorted(glob.glob(os.path.join(NB_DIR, f"metrics_normal_agg{agg}_WU10_refined_rep*.csv")))
    if not metric_files:
        print(f"[WARNING] Nenhum arquivo encontrado para agregado={agg} -- rodou run_graph4_refined.py?")
        continue

    cpu_c_vals, cpu_h_vals, err_vals_clean = [], [], []
    suspects, fully_empty_reps = [], []
    for mf in metric_files:
        rep = re.search(r"_rep(\d+)\.csv$", mf).group(1)
        sf = os.path.join(NB_DIR, f"normal_traffic_summary_log_agg{agg}_WU10_refined_rep{rep}.csv")
        rate, suspect, fully_empty, reason = error_rate_and_quality(sf)
        cpu_c, cpu_h = cpu_means(mf)
        if fully_empty:
            fully_empty_reps.append((rep, reason))
            continue  # CPU também descartada -- confirmado anormal nesse caso (ver docstring)
        cpu_c_vals.append(cpu_c)
        cpu_h_vals.append(cpu_h)
        if suspect:
            suspects.append((rep, reason))
        else:
            err_vals_clean.append(rate)

    if suspects:
        detail = ", ".join(f"rep{r} ({why})" for r, why in suspects)
        print(f"[AVISO] agregado={agg}: repetição(ões) suspeita(s) excluída(s) só do cálculo de "
              f"taxa de erro (CPU mantida, vem de fonte separada e não afetada): {detail}")
    if fully_empty_reps:
        detail = ", ".join(f"rep{r} ({why})" for r, why in fully_empty_reps)
        print(f"[AVISO] agregado={agg}: repetição(ões) totalmente vazia(s) excluída(s) de TUDO "
              f"(CPU também estava anormal nesses casos): {detail}")

    rows.append(dict(
        aggregate=agg, n=len(cpu_c_vals),
        n_error_suspect_excluded=len(suspects), n_fully_empty_excluded=len(fully_empty_reps),
        cpu_container_mean=stats.mean(cpu_c_vals),
        cpu_container_std=stats.stdev(cpu_c_vals) if len(cpu_c_vals) > 1 else 0.0,
        cpu_host_mean=stats.mean(cpu_h_vals),
        cpu_host_std=stats.stdev(cpu_h_vals) if len(cpu_h_vals) > 1 else 0.0,
        error_rate_mean=stats.mean(err_vals_clean) if err_vals_clean else float("nan"),
        error_rate_std=stats.stdev(err_vals_clean) if len(err_vals_clean) > 1 else 0.0,
        error_rate_n=len(err_vals_clean),
    ))

if not rows:
    raise SystemExit("Nenhum dado encontrado -- rode run_graph4_refined.py antes deste script.")

df = pd.DataFrame(rows)
print(df.to_string(index=False))

# Correlação simples (Pearson) como argumento de apoio, sem teste formal.
r_agg_err = np.corrcoef(df["aggregate"], df["error_rate_mean"])[0, 1]
r_cpu_host_err = np.corrcoef(df["cpu_host_mean"], df["error_rate_mean"])[0, 1]
print(f"\nCorrelação de Pearson (RPS agregado x taxa de erro média): r={r_agg_err:.3f}")
print(f"Correlação de Pearson (CPU media do host x taxa de erro média): r={r_cpu_host_err:.3f}")

fig, ax1 = plt.subplots(figsize=(11, 7))

ax1.errorbar(df["aggregate"], df["cpu_container_mean"], yerr=df["cpu_container_std"],
             fmt="o-", color=BLUE, markersize=9, linewidth=2, capsize=5,
             label="CPU média (container, ±desvio)")
ax1.errorbar(df["aggregate"], df["cpu_host_mean"], yerr=df["cpu_host_std"],
             fmt="s--", color=GRAY, markersize=8, linewidth=2, capsize=5,
             label="CPU média (host inteiro, ±desvio)")
ax1.axhline(60, color=RED, linestyle=":", linewidth=1, label="limiar SCALE_UP (60%)")
ax1.set_xlabel("RPS agregado (tráfego normal, WU=10)")
ax1.set_ylabel("CPU média (%)")
ax1.legend(loc="upper left")
ax1.grid(True, alpha=0.3)

ax2 = ax1.twinx()
ax2.errorbar(df["aggregate"], df["error_rate_mean"], yerr=df["error_rate_std"],
             fmt="^-", color=RED, markersize=9, linewidth=2, capsize=5,
             label="Taxa de erro média (±desvio)")
ax2.set_ylabel("Taxa de erro de requisição (%)", color=RED)
ax2.tick_params(axis="y", labelcolor=RED)
# Escala fixa, mesmo motivo do gráfico 11 (plot_clients_rps_invariance.py):
# o maior valor real aqui (média+desvio) é ~0.11%, auto-scale zoomava numa
# faixa de fração de ponto percentual e fazia ruído de amostragem parecer
# uma variação grande, sem contrapartida na CPU (ver changes.txt).
ax2.set_ylim(0, 1.0)
ax2.legend(loc="upper right")

plt.title(
    "Curva de capacidade do baseline normal (WU=10) -- REFINADA\n"
    f"5 repetições/ponto, CPU container + CPU host + taxa de erro "
    f"(r RPS×erro={r_agg_err:.2f}, r CPUhost×erro={r_cpu_host_err:.2f})"
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "04_curva_capacidade_REFINADA.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"\nSalvo: {out_path}")

csv_out = os.path.join(NB_DIR, "resumo_graph4_refined.csv")
df.to_csv(csv_out, index=False)
print(f"Salvo: {csv_out}")
