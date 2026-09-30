"""
Fase 3 do plano de ML (ver changes.txt): completa TODAS as configurações já
existentes em experiment_results/wedos_grid/ para 5 repetições, em vez de
expandir o grid com pontos novos. Motivo: a Fase 1 (ml_feature_extraction.py)
mostrou que 46 de 58 configs tinham só 1 repetição, e que 39 delas já têm
taxa de detecção clássica 0% -- não dá pra reportar média±IC95% nem rodar
leave-one-scenario-out com N=1 por célula.

Reaproveita wedos_combined_grid.run_point() (mesma função usada pelo
stage1a/stage1b originais -- mesmos parâmetros de CLI do
main_orchestrator.py, mesmo NORMAL_SCENARIOS) para não introduzir nenhuma
diferença metodológica entre as repetições antigas e as novas.

As repetições novas usam tag="mlfill" (não tentam replicar o tag histórico
exato de cada config -- alguns pontos do stage1b têm tags irregulares como
"stage1b_confirm" para reps específicas da mesma config nominal). Isso
significa que o sufixo de arquivo completo (config_key bruto) das reps
novas difere das antigas para a mesma config -- não é um problema para o
pipeline de ML, que agrupa por (scenario, intensity_pct, wu), não pelo
sufixo bruto; só fica registrado aqui para quem for procurar os arquivos.

S4 foi excluído do refinamento original (wedos_stage1b_refined.py) porque
já é instável sem ataque (teto de capacidade ~205-210 agregado, S4=300),
então mais reps ali não ajudam a achar fronteira limpa do detector
clássico. Para o ML esse motivo não se aplica -- mais dados dessa zona
(mesmo ruidosa) são úteis, o pipeline já isola runs instáveis por
mecanismo (is_hiccup). Por isso S4 ESTÁ incluído aqui (decisão registrada
em changes.txt, não decidida em silêncio).

Uso: python3 -m experiments.run_wedos_grid_fill_reps [--dry-run]
"""
import argparse
import glob
import os
import re

from experiments import wedos_combined_grid as grid

RESULTS_DIR = grid.RESULTS_DIR
TARGET_REPS = 5


def discover_existing_combos():
    combos = {}
    for f in glob.glob(os.path.join(RESULTS_DIR, "metrics_S*.csv")):
        suffix = os.path.basename(f)[len("metrics_"):-len(".csv")]
        m = re.match(r"(S\d+)_atk([\d.]+)pct_wu(\d+)_.*_rep(\d+)$", suffix)
        if not m:
            print(f"[AVISO] nome fora do padrão, ignorado: {suffix}")
            continue
        scenario, pct_str, wu_str, rep_str = m.groups()
        pct = float(pct_str) if "." in pct_str else int(pct_str)
        key = (scenario, pct, int(wu_str))
        combos.setdefault(key, set()).add(int(rep_str))
    return combos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="Só lista o que seria rodado, não dispara nada")
    args = parser.parse_args()

    combos = discover_existing_combos()
    plan = []
    for (scenario, pct, wu), existing_reps in sorted(combos.items()):
        missing = [r for r in range(1, TARGET_REPS + 1) if r not in existing_reps]
        for rep in missing:
            plan.append((scenario, pct, wu, rep))

    print(f"[INFO] {len(combos)} configs encontradas em {RESULTS_DIR}")
    print(f"[INFO] {len(plan)} execuções novas planejadas (alvo: {TARGET_REPS} reps/config)")

    if args.dry_run:
        for scenario, pct, wu, rep in plan:
            print(f"  {scenario} atk{pct}pct wu{wu} rep{rep}")
        return

    for i, (scenario, pct, wu, rep) in enumerate(plan, 1):
        print(f"\n[{i}/{len(plan)}]", flush=True)
        grid.run_point(scenario, grid.NORMAL_SCENARIOS[scenario], pct, wu, rep=rep, tag="mlfill")

    print("\nPreenchimento do wedos_grid concluído.", flush=True)


if __name__ == "__main__":
    main()
