import subprocess
import itertools
import os
import shutil
from experiments.result_archive import move_result

# Reexecuta os pontos do eixo X do gráfico 04 (curva de capacidade do
# baseline normal, WU=10) com repetições reais e com o código atual, que já
# grava taxa de erro (normal_traffic_summary_logger.py, changes.txt §35) e
# CPU do host (host_stats.py, changes.txt §37) -- nenhum dos dois existia
# quando os dados originais do gráfico 04 foram coletados, por isso não dá
# pra reaproveitar aqueles arquivos para essa análise (ver changes.txt).
#
# Não sobrescreve nem apaga nenhum dado existente: nomeia os arquivos de
# saída com sufixo "_refined_repN", distinto de tudo que já está em
# experiment_results/normal_baseline/.

# RPS agregado alvo (HTTP_NORMAL_NUM_CLIENTS=4, fixo -- não exposto por CLI
# ainda): --normal-rps é por cliente, então RPS agregado = normal_rps * 4.
AGGREGATE_TARGETS = [40, 100, 200, 250, 300, 400]
NUM_CLIENTS = 4  # explicitado também na CLI
NUM_REPS = 5
WORK_UNITS = 10

RESULTS_DIR = "experiment_results/normal_baseline"
os.makedirs(RESULTS_DIR, exist_ok=True)

for aggregate, rep in itertools.product(AGGREGATE_TARGETS, range(1, NUM_REPS + 1)):
    rps_per_client = aggregate / NUM_CLIENTS

    print(f"\n===== Graph4 refined: agregado={aggregate} (rps/cliente={rps_per_client}), rep {rep}/{NUM_REPS} =====")

    cmd = [
        # Sem "sudo" -- ver run_experiments_normal.py para a explicação
        # (setcap no tcpdump + Docker sem root).
        "python3", "-m",
        "simulator.main_orchestrator",
        "--normal-clients", "4",
        "--normal-rps", str(rps_per_client),
        "--normal-work-units", str(WORK_UNITS),
        "--attack-duration", "0",
        "--duration", "180",
    ]

    subprocess.run(cmd)

    suffix = f"agg{aggregate}_WU{WORK_UNITS}_refined_rep{rep}"

    # =========================
    # Metrics log (agora com host_cpu_percent embutido)
    # =========================
    move_result(
        "simulation_metrics.csv",
        os.path.join(RESULTS_DIR, f"metrics_normal_{suffix}.csv")
    )

    # =========================
    # Attack summary log -- descartado (sem ataque, sem dado útil), mesma
    # convenção de run_experiments_normal.py.
    # =========================
    if os.path.exists("attack_summary_log.csv"):
        os.remove("attack_summary_log.csv")

    # =========================
    # Normal traffic summary log (taxa de erro -- o dado novo que faltava)
    # =========================
    normal_summary_src = "normal_traffic_summary_log.csv"
    normal_summary_dst = os.path.join(RESULTS_DIR, f"normal_traffic_summary_log_{suffix}.csv")
    if os.path.exists(normal_summary_src):
        shutil.move(normal_summary_src, normal_summary_dst)
    else:
        print(f"[WARNING] {normal_summary_src} não encontrado.")

    # =========================
    # RTT log
    # =========================
    rtt_log_src = "rtt_log.csv"
    rtt_log_dst = os.path.join(RESULTS_DIR, f"rtt_log_normal_{suffix}.csv")
    if os.path.exists(rtt_log_src):
        shutil.move(rtt_log_src, rtt_log_dst)
    else:
        print(f"[WARNING] {rtt_log_src} não encontrado.")

    # =========================
    # Traffic capture (tcpdump)
    # =========================
    traffic_capture_src = "traffic_capture.csv"
    traffic_capture_dst = os.path.join(RESULTS_DIR, f"traffic_capture_normal_{suffix}.csv")
    if os.path.exists(traffic_capture_src):
        shutil.move(traffic_capture_src, traffic_capture_dst)
    else:
        print(f"[WARNING] {traffic_capture_src} não encontrado.")

print("\nGraph4 refined: todas as execuções concluídas.")
