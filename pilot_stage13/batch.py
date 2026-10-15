"""Expand only after the first seed passed every structural gate. Stop on failure."""
import contextlib
import json
from .run import OUT,ORDERS,execute,compare,put


def main():
    gate=json.loads((OUT/'comparability/101.json').read_text())
    assert gate['all_analysis_eligible'] and gate['nominal_comparability'] and gate['same_images']
    completed=[]
    try:
        for seed,order in ORDERS.items():
            if seed==101:continue
            for scenario in order:
                print(f'START seed={seed} scenario={scenario}',flush=True)
                path=OUT/f'logs/batch_{seed}_{scenario}.log'
                with path.open('x') as log,contextlib.redirect_stdout(log):execute(seed,scenario)
                c=json.loads((OUT/f'cost/{seed}/{scenario}.json').read_text())
                completed.append([seed,scenario])
                print(f"DONE {seed}/{scenario}: eligible={c['analysis_eligible']} wall={c['total_wall_seconds']:.2f}s",flush=True)
            compare(seed)
        put(OUT/'batch_status.json',dict(status='completed',completed=completed))
    except BaseException as exc:
        put(OUT/'batch_status.json',dict(status='stopped',completed=completed,error=repr(exc)))
        raise

if __name__=='__main__':main()
