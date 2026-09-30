import subprocess
import itertools
import os
import shutil
from experiments.result_archive import move_result

# Grid clientes x RPS/cliente: testa se o que importa é o RPS AGREGADO
# (clientes x rps_por_cliente), independente de como ele é decomposto --
# ex.: 4 clientes x 25 rps/cliente deveria dar o mesmo resultado que 2
# clientes x 50 rps/cliente (mesmos 100 agregado). Combinado com o usuário:
# agregados e nº de clientes em potência de 2 (para eixo log2 no gráfico),
# WU=10 fixo (mesma base do gráfico 04), 5 repetições por ponto.
#
# Requer --normal-clients em main_orchestrator.py (changes.txt) -- antes
# disso HTTP_NORMAL_NUM_CLIENTS era fixo em 4, não dava pra separar nº de
# clientes de rps/cliente.

AGGREGATE_TARGETS = [16, 32, 64, 128, 256, 512]
CLIENT_COUNTS = [1, 2, 4, 8, 16]
NUM_REPS = 5
WORK_UNITS = 10
DURATION = 180

RESULTS_DIR = "experiment_results/clients_rps_grid"
os.makedirs(RESULTS_DIR, exist_ok=True)

combos = list(itertools.product(AGGREGATE_TARGETS, CLIENT_COUNTS, range(1, NUM_REPS + 1)))
total = len(combos)

for i, (aggregate, clients, rep) in enumerate(combos, start=1):
    rps_per_client = aggregate / clients

    print(f"\n===== [{i}/{total}] clients_rps_grid: agregado={aggregate}, "
          f"clientes={clients}, rps/cliente={rps_per_client}, rep {rep}/{NUM_REPS} =====")

    cmd = [
        "python3", "-m",
        "simulator.main_orchestrator",
        "--normal-rps", str(rps_per_client),
        "--normal-clients", str(clients),
        "--normal-work-units", str(WORK_UNITS),
        "--attack-duration", "0",
        "--duration", str(DURATION),
    ]

    subprocess.run(cmd)

    suffix = f"agg{aggregate}_clients{clients}_WU{WORK_UNITS}_rep{rep}"

    move_result("simulation_metrics.csv", os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv"))

    if os.path.exists("attack_summary_log.csv"):
        os.remove("attack_summary_log.csv")

    normal_summary_src = "normal_traffic_summary_log.csv"
    if os.path.exists(normal_summary_src):
        shutil.move(normal_summary_src, os.path.join(RESULTS_DIR, f"normal_traffic_summary_log_{suffix}.csv"))
    else:
        print(f"[WARNING] {normal_summary_src} não encontrado.")

    rtt_log_src = "rtt_log.csv"
    if os.path.exists(rtt_log_src):
        shutil.move(rtt_log_src, os.path.join(RESULTS_DIR, f"rtt_log_{suffix}.csv"))
    else:
        print(f"[WARNING] {rtt_log_src} não encontrado.")

    traffic_capture_src = "traffic_capture.csv"
    if os.path.exists(traffic_capture_src):
        shutil.move(traffic_capture_src, os.path.join(RESULTS_DIR, f"traffic_capture_{suffix}.csv"))
    else:
        print(f"[WARNING] {traffic_capture_src} não encontrado.")

print("\nclients_rps_grid: todas as execuções concluídas.")
