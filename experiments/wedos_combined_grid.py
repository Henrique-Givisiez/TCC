"""
Fase 1 do plano W-EDoS — varredura combinada (Tabela 5, Sotelo Monge et al.),
grade mais ampla que o run_experiments_combined.py atual (mesmo espírito,
não o substitui nem o altera).

Uso:
  python3 -m experiments.wedos_combined_grid stage1a      # grossa, 1 rep, grade ampla
  python3 -m experiments.wedos_combined_grid stage1b      # fina, N reps, grade reduzida
                                               # (edite FINE_* abaixo antes)

Sem sudo (setcap do tcpdump já aplicado). Salva em
experiment_results/wedos_grid/, com sufixo _repN para não colidir com o
combined_sweep original (que continua em experiment_results/combined_sweep/
intacto) nem entre stages.
"""
import argparse
import itertools
import os
import shutil
import subprocess

NORMAL_SCENARIOS = {
    "S1": 40,
    "S2": 100,
    "S3": 200,
    "S4": 300,  # sujeito a revisão pela Fase 0.5 -- ver relatório final
}

NORMAL_NUM_CLIENTS = 4
ATTACK_NUM_ATTACKERS = 4
NORMAL_WORK_UNITS = 10
SIMULATION_DURATION = 180

RESULTS_DIR = "experiment_results/wedos_grid"
os.makedirs(RESULTS_DIR, exist_ok=True)


def run_point(scenario_name, normal_aggregate_rps, pct, work_units, rep, tag):
    attack_aggregate_rps = normal_aggregate_rps * pct / 100.0
    normal_rps_per_client = normal_aggregate_rps / NORMAL_NUM_CLIENTS
    attack_rps_per_attacker = attack_aggregate_rps / ATTACK_NUM_ATTACKERS

    print(f"\n===== [{tag}] {scenario_name} ({normal_aggregate_rps} req/s normal) + "
          f"{pct}% ataque (~{attack_aggregate_rps:.3f} req/s) @ WU={work_units} rep={rep} =====",
          flush=True)

    cmd = [
        "python3", "-m", "simulator.main_orchestrator",
        "--normal-clients", "4",
        "--normal-rps", str(normal_rps_per_client),
        "--rps", str(attack_rps_per_attacker),
        "--attackers", str(ATTACK_NUM_ATTACKERS),
        "--work-units", str(work_units),
        "--normal-work-units", str(NORMAL_WORK_UNITS),
        "--duration", str(SIMULATION_DURATION),
    ]
    subprocess.run(cmd)

    suffix = f"{scenario_name}_atk{pct}pct_wu{work_units}_{tag}_rep{rep}"

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


def stage1a():
    intensities = [1, 5, 10]
    wu_values = [200000, 300000, 400000, 500000]
    total = len(NORMAL_SCENARIOS) * len(intensities) * len(wu_values)
    i = 0
    for scenario_name, agg in NORMAL_SCENARIOS.items():
        for pct in intensities:
            for wu in wu_values:
                i += 1
                print(f"\n[Stage1A {i}/{total}]", flush=True)
                run_point(scenario_name, agg, pct, wu, rep=1, tag="stage1a")
    print("\nStage 1A concluída.", flush=True)


# Editar antes de rodar stage1b, com base no resultado da stage1a
FINE_SCENARIOS = dict(NORMAL_SCENARIOS)
FINE_INTENSITIES = [2, 3, 7]
FINE_WU = [225000, 250000, 275000, 325000, 350000]
FINE_REPS = 2


def stage1b():
    total = len(FINE_SCENARIOS) * len(FINE_INTENSITIES) * len(FINE_WU) * FINE_REPS
    i = 0
    for scenario_name, agg in FINE_SCENARIOS.items():
        for pct in FINE_INTENSITIES:
            for wu in FINE_WU:
                for rep in range(1, FINE_REPS + 1):
                    i += 1
                    print(f"\n[Stage1B {i}/{total}]", flush=True)
                    run_point(scenario_name, agg, pct, wu, rep=rep, tag="stage1b")
    print("\nStage 1B concluída.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["stage1a", "stage1b"])
    args = parser.parse_args()
    if args.stage == "stage1a":
        stage1a()
    else:
        stage1b()
