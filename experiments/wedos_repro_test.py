"""
Fase 0.3 do plano W-EDoS — teste controlado da hipótese de degradação do
ambiente (WSL2+Docker) ao longo de sessões longas.

Roda 3 repetições de 2 pontos de fronteira já conhecidos:
  - baseline normal agregado=300, WU=10 (candidato a S4, ver changes.txt §30)
  - wu_calibration rps=10/WU=200000, att=4

Uso: python3 -m experiments.wedos_repro_test <lote>   # lote = A ou B

Não sobrescreve nenhum dado já coletado: usa sufixo _repro_lote{A|B}_rep{N}.
Não roda com sudo (setcap do tcpdump já aplicado, ver RESUMO_MADRUGADA_12_08.txt).
"""
import argparse
import os
import shutil
from experiments.result_archive import move_result
import subprocess

REPS = 3
SIMULATION_DURATION = 180

NB_DIR = "experiment_results/normal_baseline"
WC_DIR = "experiment_results/wu_calibration"
os.makedirs(NB_DIR, exist_ok=True)
os.makedirs(WC_DIR, exist_ok=True)


def move_if_exists(src, dst):
    if os.path.exists(src):
        move_result(src, dst)
    else:
        print(f"[WARNING] {src} não encontrado.")


def run_normal_300(lote, rep):
    print(f"\n===== [lote {lote}] Normal agg=300/WU=10 — rep {rep}/{REPS} =====", flush=True)
    cmd = [
        "python3", "-m", "simulator.main_orchestrator",
        "--normal-clients", "4",
        "--normal-rps", "75",
        "--normal-work-units", "10",
        "--attack-duration", "0",
        "--duration", str(SIMULATION_DURATION),
    ]
    subprocess.run(cmd)
    move_if_exists("simulation_metrics.csv",
                    os.path.join(NB_DIR, f"metrics_normal_rps75_WU10_repro_lote{lote}_rep{rep}.csv"))
    move_if_exists("traffic_capture.csv",
                    os.path.join(NB_DIR, f"traffic_capture_normal_rps75_WU10_repro_lote{lote}_rep{rep}.csv"))
    # attack_summary_log.csv é gerado vazio (sem ataque); descartado, mesmo
    # comportamento de run_experiments_normal.py.
    if os.path.exists("attack_summary_log.csv"):
        os.remove("attack_summary_log.csv")
    move_if_exists("normal_traffic_summary_log.csv",
                    os.path.join(NB_DIR, f"normal_traffic_summary_log_rps75_WU10_repro_lote{lote}_rep{rep}.csv"))
    move_if_exists("rtt_log.csv",
                    os.path.join(NB_DIR, f"rtt_log_normal_rps75_WU10_repro_lote{lote}_rep{rep}.csv"))


def run_wu_calibration_boundary(lote, rep):
    print(f"\n===== [lote {lote}] wu_calibration rps=10/WU=200000 — rep {rep}/{REPS} =====", flush=True)
    cmd = [
        "python3", "-m", "simulator.main_orchestrator",
        "--rps", "10",
        "--attackers", "4",
        "--work-units", "200000",
        "--duration", str(SIMULATION_DURATION),
    ]
    subprocess.run(cmd)
    move_if_exists("simulation_metrics.csv",
                    os.path.join(WC_DIR, f"metrics_rps10_att4_WU200000_repro_lote{lote}_rep{rep}.csv"))
    move_if_exists("attack_summary_log.csv",
                    os.path.join(WC_DIR, f"attack_summary_log_10_4_WU200000_repro_lote{lote}_rep{rep}.csv"))
    move_if_exists("normal_traffic_summary_log.csv",
                    os.path.join(WC_DIR, f"normal_traffic_summary_log_10_4_WU200000_repro_lote{lote}_rep{rep}.csv"))
    move_if_exists("rtt_log.csv",
                    os.path.join(WC_DIR, f"rtt_log_rps10_att4_WU200000_repro_lote{lote}_rep{rep}.csv"))
    move_if_exists("traffic_capture.csv",
                    os.path.join(WC_DIR, f"traffic_capture_rps10_att4_WU200000_repro_lote{lote}_rep{rep}.csv"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("lote", choices=["A", "B"])
    args = parser.parse_args()

    for rep in range(1, REPS + 1):
        run_normal_300(args.lote, rep)
    for rep in range(1, REPS + 1):
        run_wu_calibration_boundary(args.lote, rep)

    print(f"\nLote {args.lote} concluído.", flush=True)
