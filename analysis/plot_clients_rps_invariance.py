import glob
import os
import re
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Lê os dados de run_experiments_clients_rps.py e testa a hipótese: RPS
# AGREGADO é o que importa, independente de quantos clientes o compõem.
# Eixo X em escala log2 (potências de 2), estatística simples
# (média±desvio-padrão entre as 5 repetições), sem teste de hipótese formal
# -- combinado com o usuário.

GRID_DIR = "experiment_results/clients_rps_grid"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
os.makedirs(OUT_DIR, exist_ok=True)

AGGREGATE_TARGETS = [16, 32, 64, 128, 256, 512]
CLIENT_COUNTS = [1, 2, 4, 8, 16]
COLORS = {1: "#2a78d6", 2: "#1baf7a", 4: "#e08a1e", 8: "#d03b3b", 16: "#7a3fd6"}
MARKERS = {1: "o", 2: "s", 4: "^", 8: "D", 16: "v"}


def run_stats(metrics_path, summary_path):
    df = pd.read_csv(metrics_path).iloc[1:]
    cpu_container = df["average_cpu_percent"].mean()
    cpu_host = df["host_cpu_percent"].mean() if "host_cpu_percent" in df.columns else float("nan")

    raw = pd.read_csv(summary_path)
    expected_clients = raw["num_clients"].dropna().iloc[0] if raw["num_clients"].notna().any() else None
    sdf = raw[raw["total_requests"].notna()]
    ok = sdf["total_requests"].sum()
    err = sdf["errors"].sum()
    achieved_rps = sdf["real_rps"].sum()
    err_rate = 100.0 * err / (ok + err) if (ok + err) > 0 else float("nan")

    # Sinal simples (não é teste estatístico) de run incompleto: menos
    # linhas de worker-stop do que clientes configurados -- indica que
    # alguma thread de tráfego (daemon=True) não terminou de escrever seu
    # resumo antes do processo encerrar, geralmente sintoma de um soluço
    # de ambiente no meio da execução (ver changes.txt). Sinalizado, não
    # descartado automaticamente -- decisão de manter ou não fica visível
    # no console/CSV-resumo em vez de escondida.
    incomplete = expected_clients is not None and len(sdf) < expected_clients

    return cpu_container, cpu_host, err_rate, achieved_rps, incomplete


rows = []
for agg in AGGREGATE_TARGETS:
    for clients in CLIENT_COUNTS:
        pattern = os.path.join(GRID_DIR, f"metrics_agg{agg}_clients{clients}_WU10_rep*.csv")
        metric_files = sorted(glob.glob(pattern))
        if not metric_files:
            print(f"[WARNING] Sem dados para agregado={agg}, clientes={clients} -- pulando.")
            continue

        cpu_c_vals, cpu_h_vals, err_vals, achieved_vals = [], [], [], []
        incomplete_reps = []
        for mf in metric_files:
            rep = re.search(r"_rep(\d+)\.csv$", mf).group(1)
            suffix = f"agg{agg}_clients{clients}_WU10_rep{rep}"
            sf = os.path.join(GRID_DIR, f"normal_traffic_summary_log_{suffix}.csv")
            if not os.path.exists(sf):
                continue
            cpu_c, cpu_h, err_rate, achieved, incomplete = run_stats(mf, sf)
            if incomplete:
                incomplete_reps.append(rep)
                continue  # run incompleto (thread de log não terminou) -- fora do cálculo
            cpu_c_vals.append(cpu_c)
            cpu_h_vals.append(cpu_h)
            err_vals.append(err_rate)
            achieved_vals.append(achieved)

        if incomplete_reps:
            print(f"[AVISO] agregado={agg} clientes={clients}: repetição(ões) {incomplete_reps} "
                  f"incompleta(s) (menos linhas de worker-stop do que clientes configurados) "
                  f"-- excluída(s) do cálculo, não só a taxa de erro.")

        if not cpu_c_vals:
            continue

        # Um único run (de 150) pode ficar sem taxa de erro (NaN) se as
        # threads de tráfego normal -- daemon=True -- não terminarem de
        # escrever o resumo antes do processo encerrar (visto de fato no
        # canto mais extremo do grid, agg=512/clientes=2 -- ver
        # changes.txt). Isso não afeta CPU (vem de outra fonte), só
        # descarta esse ponto específico do cálculo de erro em vez de
        # quebrar o script inteiro.
        err_valid = [v for v in err_vals if v == v]  # v==v é False só para NaN
        n_err_dropped = len(err_vals) - len(err_valid)
        if n_err_dropped:
            print(f"[AVISO] agregado={agg} clientes={clients}: {n_err_dropped} repetição(ões) "
                  f"sem taxa de erro registrada (log incompleto), ignorada(s) só nesse cálculo.")

        rows.append(dict(
            target_aggregate=agg, clients=clients, n=len(cpu_c_vals),
            n_incomplete_excluded=len(incomplete_reps),
            achieved_aggregate_mean=stats.mean(achieved_vals),
            cpu_container_mean=stats.mean(cpu_c_vals),
            cpu_container_std=stats.stdev(cpu_c_vals) if len(cpu_c_vals) > 1 else 0.0,
            cpu_host_mean=stats.mean(cpu_h_vals),
            error_rate_mean=stats.mean(err_valid) if err_valid else float("nan"),
            error_rate_std=stats.stdev(err_valid) if len(err_valid) > 1 else 0.0,
            error_rate_n=len(err_valid),
        ))

if not rows:
    raise SystemExit("Nenhum dado encontrado -- rode run_experiments_clients_rps.py antes deste script.")

df = pd.DataFrame(rows)
pd.set_option("display.width", 160)
print(df.to_string(index=False))

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

for clients in CLIENT_COUNTS:
    sub = df[df["clients"] == clients].sort_values("target_aggregate")
    if sub.empty:
        continue
    ax1.errorbar(sub["target_aggregate"], sub["cpu_container_mean"], yerr=sub["cpu_container_std"],
                 fmt=f"{MARKERS[clients]}-", color=COLORS[clients], markersize=8, linewidth=1.8,
                 capsize=4, label=f"{clients} cliente(s)")

ax1.set_xscale("log", base=2)
ax1.set_xticks(AGGREGATE_TARGETS)
ax1.set_xticklabels([str(a) for a in AGGREGATE_TARGETS])
ax1.axhline(60, color="#d03b3b", linestyle=":", linewidth=1, label="limiar SCALE_UP (60%)")
ax1.set_xlabel("RPS agregado alvo (WU=10, escala log2)")
ax1.set_ylabel("CPU média do container (%) ± desvio")
ax1.set_title("CPU média por decomposição clientes×RPS\n(pontos do mesmo agregado deveriam coincidir)")
ax1.legend(fontsize=8)
ax1.grid(True, alpha=0.3)

for clients in CLIENT_COUNTS:
    sub = df[df["clients"] == clients].sort_values("target_aggregate")
    if sub.empty:
        continue
    ax2.errorbar(sub["target_aggregate"], sub["error_rate_mean"], yerr=sub["error_rate_std"],
                 fmt=f"{MARKERS[clients]}-", color=COLORS[clients], markersize=8, linewidth=1.8,
                 capsize=4, label=f"{clients} cliente(s)")

ax2.set_xscale("log", base=2)
ax2.set_xticks(AGGREGATE_TARGETS)
ax2.set_xticklabels([str(a) for a in AGGREGATE_TARGETS])
ax2.set_xlabel("RPS agregado alvo (WU=10, escala log2)")
ax2.set_ylabel("Taxa de erro média (%) ± desvio")
# Escala fixa (não auto-ajustada): o maior valor real em todo o grid
# (media+desvio) e ~0.26% -- deixado em auto-scale, o matplotlib dava zoom
# numa faixa de fracoes de ponto percentual e fazia ruido de amostragem
# (poucas dezenas de erro em milhares de requisicoes) parecer uma
# variacao dramatica, sem nenhum efeito correspondente no CPU (ver
# changes.txt). Fixar 0-1% deixa a escala honesta e comparavel com os
# outros graficos (04/05), onde a taxa de erro real tambem fica bem abaixo
# de 1% na maioria dos pontos.
ax2.set_ylim(0, 1.0)
ax2.set_title("Taxa de erro por decomposição clientes×RPS (escala fixa 0-1%)")
ax2.legend(fontsize=8)
ax2.grid(True, alpha=0.3)

fig.suptitle("Grid clientes×RPS -- RPS agregado é o que importa? (5 repetições/ponto)")
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "11_clients_rps_invariancia.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"\nSalvo: {out_path}")

csv_out = os.path.join(GRID_DIR, "resumo_clients_rps_grid.csv")
df.to_csv(csv_out, index=False)
print(f"Salvo: {csv_out}")
