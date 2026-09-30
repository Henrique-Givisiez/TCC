import subprocess
import os
import shutil

# Experimento de desempate: combinado (ataque + 40 agregado de tráfego
# normal padrão) vs. isolado (só ataque, --normal-rps 0), rodados NA MESMA
# SESSÃO com repetições -- pra decidir se a discrepância vista antes
# (seção 60) é um efeito real da presença de tráfego normal ou só deriva
# de sessão/ambiente (as coletas comparadas antes tinham 15 dias de
# diferença). rps=1 excluído (já mostrou comportamento trivial e idêntico
# nos dois lados, não justifica o tempo de Docker).
#
# Ordem intercalada por repetição (combinado rep1, isolado rep1,
# combinado rep2, isolado rep2, ...) para cada célula -- controla também
# deriva de curto prazo DENTRO da sessão, não só entre sessões.

RPS_VALUES = [5, 10]
WU_VALUES = [100000, 200000, 400000]
ATTACKERS = 4
DURATION = 180
NUM_REPS = 5

RESULTS_DIR = "experiment_results/desempate_combinado_isolado"
os.makedirs(RESULTS_DIR, exist_ok=True)

CONDICOES = {
    "combinado": "10",  # --normal-rps 10 (default, 40 agregado com 4 clientes)
    "isolado": "0",     # --normal-rps 0 (desligado de vez, ver normal_traffic.py)
}

total = len(RPS_VALUES) * len(WU_VALUES) * NUM_REPS * len(CONDICOES)
count = 0

for rps in RPS_VALUES:
    for wu in WU_VALUES:
        for rep in range(1, NUM_REPS + 1):
            for condicao, normal_rps in CONDICOES.items():
                count += 1
                print(f"\n===== [{count}/{total}] desempate: {condicao} rps={rps} WU={wu} rep={rep} =====")

                cmd = [
                    "python3", "-m",
                    "simulator.main_orchestrator",
                    "--rps", str(rps),
                    "--attackers", str(ATTACKERS),
                    "--work-units", str(wu),
                    "--normal-clients", "4",
                    "--normal-rps", normal_rps,
                    "--duration", str(DURATION),
                ]

                subprocess.run(cmd)

                suffix = f"{condicao}_rps{rps}_att{ATTACKERS}_WU{wu}_rep{rep}"

                shutil.move("simulation_metrics.csv", os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv"))

                if os.path.exists("attack_summary_log.csv"):
                    shutil.move("attack_summary_log.csv", os.path.join(RESULTS_DIR, f"attack_summary_log_{suffix}.csv"))

                if os.path.exists("rtt_log.csv"):
                    shutil.move("rtt_log.csv", os.path.join(RESULTS_DIR, f"rtt_log_{suffix}.csv"))

                if os.path.exists("traffic_capture.csv"):
                    shutil.move("traffic_capture.csv", os.path.join(RESULTS_DIR, f"traffic_capture_{suffix}.csv"))

                # normal_traffic_summary_log.csv só tem dado útil em
                # "combinado" (em "isolado" o tráfego normal nunca inicia).
                if condicao == "combinado" and os.path.exists("normal_traffic_summary_log.csv"):
                    shutil.move("normal_traffic_summary_log.csv",
                                os.path.join(RESULTS_DIR, f"normal_traffic_summary_log_{suffix}.csv"))
                elif os.path.exists("normal_traffic_summary_log.csv"):
                    os.remove("normal_traffic_summary_log.csv")

print("\ndesempate_combinado_isolado: todas as execuções concluídas.")
