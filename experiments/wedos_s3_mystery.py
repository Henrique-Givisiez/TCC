"""
Fase 0.4 do plano W-EDoS — investigar o mistério de
attack_summary_log_S3_atk1pct_wu300000.csv (~490 erros de requisição apesar
de taxa de ataque planejada de só ~2 req/s agregado, ver changes.txt §31
"achado novo, ainda não investigado").

Rerroda exatamente essa config (S3=200 agregado, 1% intensidade, WU=300000)
3x e salva pra inspeção cruzada com metrics.csv (procurando SCALE_DOWN
durante a janela de ataque -- hipótese: worker de ataque preso numa URL de
instância que morreu).
"""
import os
import shutil
import subprocess

REPS = 3
SCENARIO = "S3"
NORMAL_AGGREGATE_RPS = 200
PCT = 1
WORK_UNITS = 300000
NORMAL_NUM_CLIENTS = 4
ATTACK_NUM_ATTACKERS = 4
NORMAL_WORK_UNITS = 10
SIMULATION_DURATION = 180

RESULTS_DIR = "experiment_results/wedos_grid"
os.makedirs(RESULTS_DIR, exist_ok=True)

attack_aggregate_rps = NORMAL_AGGREGATE_RPS * PCT / 100.0
normal_rps_per_client = NORMAL_AGGREGATE_RPS / NORMAL_NUM_CLIENTS
attack_rps_per_attacker = attack_aggregate_rps / ATTACK_NUM_ATTACKERS

for rep in range(1, REPS + 1):
    print(f"\n===== [S3 mystery] rep {rep}/{REPS} =====", flush=True)
    cmd = [
        "python3", "-m", "simulator.main_orchestrator",
        "--normal-rps", str(normal_rps_per_client),
        "--rps", str(attack_rps_per_attacker),
        "--attackers", str(ATTACK_NUM_ATTACKERS),
        "--work-units", str(WORK_UNITS),
        "--normal-work-units", str(NORMAL_WORK_UNITS),
        "--duration", str(SIMULATION_DURATION),
    ]
    subprocess.run(cmd)

    suffix = f"S3_atk1pct_wu300000_mystery_rep{rep}"

    def move_if_exists(src, name_prefix):
        if os.path.exists(src):
            shutil.move(src, os.path.join(RESULTS_DIR, f"{name_prefix}_{suffix}.csv"))
        else:
            print(f"[WARNING] {src} não encontrado.")

    move_if_exists("simulation_metrics.csv", "metrics")
    move_if_exists("attack_summary_log.csv", "attack_summary_log")
    move_if_exists("normal_traffic_summary_log.csv", "normal_traffic_summary_log")
    move_if_exists("rtt_log.csv", "rtt_log")
    move_if_exists("traffic_capture.csv", "traffic_capture")

print("\nS3 mystery reruns concluídas.", flush=True)
