"""
Grid novo (pedido do usuário): intensidade do ataque vs. tráfego legítimo,
variando número de atacantes e RPS por atacante, com a intensidade AGREGADA
do ataque limitada a no máximo 25% do agregado normal de cada cenário --
não pode "passar" o tráfego legítimo.

WU fixo em 200.000 (não fazia parte do que o usuário pediu variar; usado o
mesmo valor de referência intermediário de outros gráficos do projeto --
ver changes.txt).

Triagem: 1 rep, grade ampla (mesmo espírito do wedos_combined_grid.py
stage1a) -- decidir depois, com base no resultado, se vale repetir com mais
reps.

Rodado em 2 lotes (mesmo diretório de resultados, sem colisão de nome --
o nome do arquivo já inclui o cenário):
  lote 1 (changes.txt §84/86): S1-S4 = 40/100/200/300 (pontos já usados em
    outros gráficos W-EDoS do projeto).
  lote 2 (changes.txt §87): S5-S8 = 20/80/160/320, pedido explícito do
    usuário para ter mais resolução ao longo da curva de RPS agregado.
    NORMAL_SCENARIOS abaixo reflete o lote ATUALMENTE ativo neste
    arquivo -- editar antes de rodar um lote novo. S8=320 já está acima
    do teto de capacidade medido do simulador (~205-210 agregado, WU=10),
    mesma ressalva de instabilidade de baseline já documentada para S4.

Uso: python3 -m experiments.run_atacantes_intensidade_grid
"""
import os
import shutil
from experiments.result_archive import move_result
import subprocess

NORMAL_SCENARIOS = {
    "S5": 20,
    "S6": 80,
    "S7": 160,
    "S8": 320,
}
NORMAL_NUM_CLIENTS = 4
NORMAL_WORK_UNITS = 10

ATTACKERS_VALUES = [1, 2, 4]
INTENSITIES_PCT = [1, 5, 10, 15, 20, 25]  # % do agregado normal do cenário -- nunca > 25%
WORK_UNITS = 200000
SIMULATION_DURATION = 180
NUM_REPS = 1

RESULTS_DIR = "experiment_results/atacantes_intensidade_grid"
os.makedirs(RESULTS_DIR, exist_ok=True)


def run_point(scenario_name, normal_aggregate_rps, pct, attackers, rep):
    attack_aggregate_rps = normal_aggregate_rps * pct / 100.0
    normal_rps_per_client = normal_aggregate_rps / NORMAL_NUM_CLIENTS
    attack_rps_per_attacker = attack_aggregate_rps / attackers

    print(f"\n===== {scenario_name} ({normal_aggregate_rps} req/s normal) + "
          f"{pct}% ataque (~{attack_aggregate_rps:.3f} req/s, {attackers} atacante(s), "
          f"{attack_rps_per_attacker:.4f} rps/atacante) @ WU={WORK_UNITS} rep={rep} =====",
          flush=True)

    cmd = [
        "python3", "-m", "simulator.main_orchestrator",
        "--normal-clients", "4",
        "--normal-rps", str(normal_rps_per_client),
        "--rps", str(attack_rps_per_attacker),
        "--attackers", str(attackers),
        "--work-units", str(WORK_UNITS),
        "--normal-work-units", str(NORMAL_WORK_UNITS),
        "--duration", str(SIMULATION_DURATION),
    ]
    subprocess.run(cmd)

    suffix = f"{scenario_name}_atk{pct}pct_att{attackers}_wu{WORK_UNITS}_rep{rep}"

    def move_if_exists(src, name_prefix):
        if os.path.exists(src):
            move_result(src, os.path.join(RESULTS_DIR, f"{name_prefix}_{suffix}.csv"))
        else:
            print(f"[WARNING] {src} não encontrado.")

    move_if_exists("simulation_metrics.csv", "metrics")
    move_if_exists("attack_summary_log.csv", "attack_summary_log")
    move_if_exists("normal_traffic_summary_log.csv", "normal_traffic_summary_log")
    move_if_exists("rtt_log.csv", "rtt_log")
    move_if_exists("traffic_capture.csv", "traffic_capture")


def main():
    total = len(NORMAL_SCENARIOS) * len(ATTACKERS_VALUES) * len(INTENSITIES_PCT) * NUM_REPS
    i = 0
    for scenario_name, agg in NORMAL_SCENARIOS.items():
        for attackers in ATTACKERS_VALUES:
            for pct in INTENSITIES_PCT:
                for rep in range(1, NUM_REPS + 1):
                    i += 1
                    print(f"\n[{i}/{total}]", flush=True)
                    run_point(scenario_name, agg, pct, attackers, rep)
    print(f"\natacantes_intensidade_grid: todas as {total} execuções concluídas.", flush=True)


if __name__ == "__main__":
    main()
