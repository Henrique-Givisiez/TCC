"""
Rerroda os pontos contaminados pelo diagnóstico ao vivo de
INSTANCE_MAX_CONCURRENT_REQUESTS (2->4->8->revertido a 2, ver changes.txt
seção sobre o diagnóstico do timeout):
  - Stage1A run 1/48 (S1, 1%, WU=200000) -- já estava em andamento quando
    revertido, rodou inteiro com pool=8.
  - As 3 repetições do mistério S3 (S3, 1%, WU=300000) -- mix de pool
    2/4/8 entre as 3 repetições.

Sobrescreve os mesmos arquivos (mesma convenção de nome usada
originalmente), agora com pool=2 consistente (valor final, confirmado em
config.py).
"""
import subprocess

from experiments import wedos_combined_grid as grid
from simulator.experiment_config import ExperimentConfig

assert ExperimentConfig().server.process_pool_workers == 2, (
    f"esperava pool=2, achou {ExperimentConfig().server.process_pool_workers} -- "
    "confirme config.py antes de rerodar"
)

print("===== Rerodando Stage1A ponto 1/48 (S1, 1%, WU=200000) com pool=2 =====", flush=True)
grid.run_point("S1", grid.NORMAL_SCENARIOS["S1"], 1, 200000, rep=1, tag="stage1a")

print("\n===== Rerodando mistério S3 (3 repetições) com pool=2 =====", flush=True)
subprocess.run(["python3", "-m", "experiments.wedos_s3_mystery"])

print("\nReruns de pontos contaminados concluídos.", flush=True)
