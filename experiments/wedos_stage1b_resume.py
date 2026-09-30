"""
Retomada da Stage 1B (wedos_stage1b_refined.py) após interrupção por reboot
do Windows na madrugada de 13/08 (~02:30, durante S2_atk1pct_wu475000_rep1).

Não repete o que já está confirmado em experiment_results/wedos_grid/:
  - S1 @ 10%, WU em {325000, 350000, 375000} x 3 reps -- completo (9/9)
  - S2 @ 1%,  WU em {425000, 450000} x 3 reps -- completo (6/6)

Continua exatamente do próximo ponto da sequência original
(wedos_stage1b_refined.py), na mesma ordem:
  - S2 @ 1%,   WU=475000 x 3 reps
  - S2 @ 0.5%, WU=500000 x 3 reps
  - S2 @ 1%,   WU=500000 reps 2-3 (tag stage1b_confirm; rep1 já existe da Stage1A)
  - S3 @ 1%,   WU em {100000, 125000, 150000, 175000} x 2 reps
"""
from experiments import wedos_combined_grid as grid

REPS = 3

print("===== Stage1B (retomada): S2 @ 1%, WU=475000 =====", flush=True)
for rep in range(1, REPS + 1):
    grid.run_point("S2", grid.NORMAL_SCENARIOS["S2"], 1, 475000, rep=rep, tag="stage1b")

print("\n===== Stage1B: S2 @ 0.5%, WU=500000 (candidato ainda mais furtivo?) =====", flush=True)
for rep in range(1, REPS + 1):
    grid.run_point("S2", grid.NORMAL_SCENARIOS["S2"], 0.5, 500000, rep=rep, tag="stage1b")

print("\n===== Stage1B: S2 @ 1%, WU=500000 -- reps extras p/ validar candidato principal =====", flush=True)
for rep in [2, 3]:  # rep 1 já existe da Stage1A
    grid.run_point("S2", grid.NORMAL_SCENARIOS["S2"], 1, 500000, rep=rep, tag="stage1b_confirm")

print("\n===== Stage1B: S3 @ 1%, refinando WU abaixo de 200k =====", flush=True)
for wu in [100000, 125000, 150000, 175000]:
    for rep in range(1, 3):  # 2 reps (exploratório)
        grid.run_point("S3", grid.NORMAL_SCENARIOS["S3"], 1, wu, rep=rep, tag="stage1b")

print("\nStage 1B (retomada) concluída.", flush=True)
