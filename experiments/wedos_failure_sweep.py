"""
Fase 4 do plano W-EDoS — varredura de fronteira de falha (científica, OFAT).

Objetivo: achar onde o simulador deixa de ser um ataque "custo forçado
discreto" e passa a ser volumetricamente óbvio / causar colapso real —
DIFERENTE da Fase 1 (que busca furtividade). Aqui não há tráfego normal
sobreposto (mesmo regime "isolado" de wu_calibration/run_experiments.py):
o objetivo é caracterizar o ataque em si, eixo por eixo, mantendo os outros
fixos num ponto já conhecido como seguro (rps=10/atacante, WU=500000,
4 atacantes -- o "pior caso" já calibrado em wu_calibration).

Uso:
  python3 -m experiments.wedos_failure_sweep wu        # eixo WU, extensão 400k-2M
  python3 -m experiments.wedos_failure_sweep rps       # eixo RPS por atacante
  python3 -m experiments.wedos_failure_sweep attackers  # eixo nº de atacantes
  python3 -m experiments.wedos_failure_sweep all       # os três em sequência

Critério de falha (calculado depois, na consolidação, não aqui): taxa de
erro = errors / (total_requests + errors) por worker de ataque (request_count
e error_count são contadores SEPARADOS em traffic_injectorV0.py -- "Total
requests" já é só sucesso, não inclui erro).
"""
import argparse
import os
import shutil
from experiments.result_archive import move_result
import subprocess

REPS = 2
SIMULATION_DURATION = 180

RESULTS_DIR = "experiment_results/wedos_failure"
os.makedirs(RESULTS_DIR, exist_ok=True)

# Ponto fixo "seguro" já conhecido (wu_calibration rps=10/att=4/WU=500000):
BASE_RPS_PER_ATTACKER = 10
BASE_NUM_ATTACKERS = 4
BASE_WU = 500000

WU_EXT_VALUES = [400000, 500000, 750000, 1000000, 1500000, 2000000]
RPS_VALUES = [10, 20, 40, 80]
ATTACKERS_VALUES = [4, 8, 16, 32]


def run_point(axis, rps_per_attacker, attackers, wu, rep):
    tag = f"{axis}_rps{rps_per_attacker}_att{attackers}_WU{wu}_rep{rep}"
    print(f"\n===== [Fase4:{axis}] rps={rps_per_attacker} att={attackers} WU={wu} "
          f"rep={rep}/{REPS} =====", flush=True)
    cmd = [
        "python3", "-m", "simulator.main_orchestrator",
        "--rps", str(rps_per_attacker),
        "--attackers", str(attackers),
        "--work-units", str(wu),
        "--duration", str(SIMULATION_DURATION),
    ]
    subprocess.run(cmd)

    def move_if_exists(src, name_prefix):
        if os.path.exists(src):
            move_result(src, os.path.join(RESULTS_DIR, f"{name_prefix}_{tag}.csv"))
        else:
            print(f"[WARNING] {src} não encontrado.")

    move_if_exists("simulation_metrics.csv", "metrics")
    move_if_exists("attack_summary_log.csv", "attack_summary_log")
    move_if_exists("normal_traffic_summary_log.csv", "normal_traffic_summary_log")
    move_if_exists("rtt_log.csv", "rtt_log")
    move_if_exists("traffic_capture.csv", "traffic_capture")


def sweep_wu():
    for wu in WU_EXT_VALUES:
        for rep in range(1, REPS + 1):
            run_point("wu", BASE_RPS_PER_ATTACKER, BASE_NUM_ATTACKERS, wu, rep)


def sweep_rps():
    for rps in RPS_VALUES:
        for rep in range(1, REPS + 1):
            run_point("rps", rps, BASE_NUM_ATTACKERS, BASE_WU, rep)


def sweep_attackers():
    for att in ATTACKERS_VALUES:
        for rep in range(1, REPS + 1):
            run_point("attackers", BASE_RPS_PER_ATTACKER, att, BASE_WU, rep)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("axis", choices=["wu", "rps", "attackers", "all"])
    args = parser.parse_args()

    if args.axis in ("wu", "all"):
        sweep_wu()
    if args.axis in ("rps", "all"):
        sweep_rps()
    if args.axis in ("attackers", "all"):
        sweep_attackers()

    print("\nVarredura de fronteira de falha concluída.", flush=True)
