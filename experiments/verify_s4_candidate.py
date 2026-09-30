import subprocess
import os
import shutil

# Verificação pontual (não faz parte da varredura permanente): roda o
# candidato a novo valor de S4 (250 req/s agregado, WU=10 — mesmo custo
# usado pro tráfego normal no sweep combinado) 3 vezes seguidas, pra
# checar se ele fica estável com folga real abaixo do limiar de 60% de
# CPU, em vez de confiar numa única amostra como aconteceu com o
# candidato anterior (300, que na prática só tinha ~6.4 pontos percentuais
# de margem e mostrou variância real entre execuções — ver changes.txt).

NORMAL_RPS_PER_CLIENT = 62.5  # 250 agregado / 4 clientes
NORMAL_WORK_UNITS = 10
REPS = 3
SIMULATION_DURATION = 180

RESULTS_DIR = "experiment_results/normal_baseline"
os.makedirs(RESULTS_DIR, exist_ok=True)

for rep in range(1, REPS + 1):
    print(f"\n===== Candidato S4 (250 agregado, WU=10) — repetição {rep}/{REPS} =====")

    cmd = [
        "sudo",
        "python3", "-m",
        "simulator.main_orchestrator",
        "--normal-rps", str(NORMAL_RPS_PER_CLIENT),
        "--normal-work-units", str(NORMAL_WORK_UNITS),
        "--attack-duration", "0",
        "--duration", str(SIMULATION_DURATION),
    ]
    subprocess.run(cmd)

    metrics_filename = f"metrics_normal_rps62.5_WU10_rep{rep}.csv"
    shutil.move("simulation_metrics.csv", os.path.join(RESULTS_DIR, metrics_filename))

    traffic_capture_src = "traffic_capture.csv"
    traffic_capture_filename = f"traffic_capture_normal_rps62.5_WU10_rep{rep}.csv"
    if os.path.exists(traffic_capture_src):
        shutil.move(traffic_capture_src, os.path.join(RESULTS_DIR, traffic_capture_filename))
    else:
        print(f"[WARNING] {traffic_capture_src} não encontrado.")

    attack_summary_src = "attack_summary_log.csv"
    if os.path.exists(attack_summary_src):
        os.remove(attack_summary_src)

print("\nAs 3 repetições foram concluídas.")
