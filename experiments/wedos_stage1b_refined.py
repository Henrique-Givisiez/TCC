"""
Fase 1 Stage 1B do plano W-EDoS — refinamento fino em volta das fronteiras
achadas na Stage 1A (varredura grossa), com repetições reais.

S4 excluído: teto de capacidade do simulador confirmado em ~205-210
agregado (WU=10) via varredura fina de limiar (overnight_threshold_sweep.py,
3 reps/ponto) -- S4=300 já é instável sozinho, sem qualquer ataque, então
qualquer refinamento ali mediria o teto de capacidade, não o efeito do
ataque. Documentado no relatório final, não refeito aqui.

Refinamentos, com base nos resultados brutos da Stage 1A
(experiment_results/wedos_grid/metrics_S*_stage1a_rep1.csv):

  S1 (40 agregado): só escala em pct=10%, entre WU=300000 (não, 46.7%) e
    WU=400000 (sim, 144.9%, 2 scale-ups) -- salto grande, refinar WU
    intermediário pra achar o ponto real de transição.

  S2 (100 agregado): só escala em pct=1% entre WU=400000 (não, 47.2%) e
    WU=500000 (sim, 138.9%, 2 scale-ups) -- candidato mais "limpo" já
    encontrado (baseline estável sozinho + ataque de baixíssimo volume
    força escalonamento real). Refinar WU pra achar o mínimo necessário, e
    testar intensidade ainda mais baixa (0.5%) no WU que já funciona, pra
    ver se fica ainda mais furtivo. Também roda mais 2 reps do ponto já
    validado (1%/WU=500000) pra fechar 3 repetições totais (já tem 1 da
    Stage1A).

  S3 (200 agregado): JÁ escala em pct=1%/WU=200000 (o menor WU testado),
    ou seja, mesmo o "mais barato" já é suficiente aqui -- diferente de
    S1/S2, a pergunta interessante em S3 não é "que WU mínimo funciona",
    é "até que ponto um baseline com MENOS margem (mais perto do próprio
    teto) precisa de MENOS ataque pra tombar". Refina WU pra BAIXO de
    200000 pra achar esse novo mínimo.
"""
from experiments import wedos_combined_grid as grid

REPS = 3

print("===== Stage1B: S1 @ 10%, refinando WU entre 300k e 400k =====", flush=True)
for wu in [325000, 350000, 375000]:
    for rep in range(1, REPS + 1):
        grid.run_point("S1", grid.NORMAL_SCENARIOS["S1"], 10, wu, rep=rep, tag="stage1b")

print("\n===== Stage1B: S2 @ 1%, refinando WU entre 400k e 500k =====", flush=True)
for wu in [425000, 450000, 475000]:
    for rep in range(1, REPS + 1):
        grid.run_point("S2", grid.NORMAL_SCENARIOS["S2"], 1, wu, rep=rep, tag="stage1b")

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

print("\nStage 1B (refinada) concluída.", flush=True)
