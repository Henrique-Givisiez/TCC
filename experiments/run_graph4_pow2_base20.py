import subprocess
import os
import shutil

# Tarefa 6b: série nova em potência de 2 (base 20): 20, 40, 80, 160, 320,
# 640 -- 10 repetições cada. O "40" é REAPROVEITADO da tarefa 6a (mesma
# metodologia, mesmo diretório/nome de arquivo -- por isso este script só
# roda os outros 5 valores). Só faz sentido rodar DEPOIS da tarefa 6a
# terminar (pra reaproveitar a versão com 10 repetições do 40, não a
# antiga com 5).

NUM_CLIENTS = 4
WORK_UNITS = 10
DURATION = 180
NUM_REPS = 10

RESULTS_DIR = "experiment_results/normal_baseline"
os.makedirs(RESULTS_DIR, exist_ok=True)

AGGREGATE_TARGETS = [20, 80, 160, 320, 640]  # 40 reaproveitado da tarefa 6a, não roda aqui

total = len(AGGREGATE_TARGETS) * NUM_REPS
count = 0

for aggregate in AGGREGATE_TARGETS:
    rps_per_client = aggregate / NUM_CLIENTS
    for rep in range(1, NUM_REPS + 1):
        count += 1
        print(f"\n===== [{count}/{total}] pow2_base20: agregado={aggregate} "
              f"(rps/cliente={rps_per_client}), rep {rep} =====")

        cmd = [
            "python3", "-m",
            "simulator.main_orchestrator",
            "--normal-rps", str(rps_per_client),
            "--normal-work-units", str(WORK_UNITS),
            "--attack-duration", "0",
            "--duration", str(DURATION),
        ]

        subprocess.run(cmd)

        suffix = f"agg{aggregate}_WU{WORK_UNITS}_refined_rep{rep}"

        shutil.move("simulation_metrics.csv", os.path.join(RESULTS_DIR, f"metrics_normal_{suffix}.csv"))

        if os.path.exists("attack_summary_log.csv"):
            os.remove("attack_summary_log.csv")

        normal_summary_src = "normal_traffic_summary_log.csv"
        if os.path.exists(normal_summary_src):
            shutil.move(normal_summary_src, os.path.join(RESULTS_DIR, f"normal_traffic_summary_log_{suffix}.csv"))
        else:
            print(f"[WARNING] {normal_summary_src} não encontrado.")

        rtt_log_src = "rtt_log.csv"
        if os.path.exists(rtt_log_src):
            shutil.move(rtt_log_src, os.path.join(RESULTS_DIR, f"rtt_log_normal_{suffix}.csv"))
        else:
            print(f"[WARNING] {rtt_log_src} não encontrado.")

        traffic_capture_src = "traffic_capture.csv"
        if os.path.exists(traffic_capture_src):
            shutil.move(traffic_capture_src, os.path.join(RESULTS_DIR, f"traffic_capture_normal_{suffix}.csv"))
        else:
            print(f"[WARNING] {traffic_capture_src} não encontrado.")

print("\npow2_base20: todas as execuções concluídas.")
