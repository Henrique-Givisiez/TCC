"""Finite preregistered matrix, after independent review of the five pilots.

Run from the repository root with PYTHONPATH=. No retries or scientific evaluation.
"""
import json
from pathlib import Path
import sys
import time

from experiments.capacity_exploration import run

root=Path('experiment_results/capacity-exploration-20261104')
configs=Path('experiments/configs/capacity_exploration_20261104')
for name in ['P1_8rps','P2_32rps','P3_64rps','P4_96rps','P5_128rps']:
    prior=json.loads((root/name/'capacity_summary.json').read_text())
    assert prior['progression']['allowed'] and not prior['failures'],name
    assert json.loads((root/name/'verification/verification.json').read_text())['accepted'],name

matrix={'C1':(2,8),'C2':(2,64),'C3':(2,128),'C4':(4,64),'C5':(4,128)}
order=['C1_ON_r1','C2_ON_r1','C2_OFF_r1','C4_ON_r1','C3_ON_r1','C3_OFF_r1','C5_ON_r1',
       'C3_OFF_r2','C3_ON_r2','C5_ON_r2','C2_OFF_r2','C2_ON_r2','C4_ON_r2','C1_ON_r2']
selection=dict(matrix={k:dict(clients=n,aggregate_rps=rate,rps_per_client=rate/n) for k,(n,rate) in matrix.items()},
    duration_seconds=20,seeds=[44112101,44112102],order=order,reason='five safe integral pilots; no further intensity escalation')
with (root/'selected_matrix.json').open('x') as stream:json.dump(selection,stream,indent=2);stream.write('\n')
base=json.loads((configs/'P1_8rps.json').read_text())
for name in order:
    scenario,mode,rep=name.split('_');n,rate=matrix[scenario]
    c=json.loads(json.dumps(base));c.update(id=name,duration_seconds=20,seed=44112100+int(rep[1:]))
    c['normal_traffic'].update(clients=n,rate=rate/n)
    c['diagnostics']['enabled']=mode=='ON'
    with (configs/(name+'.json')).open('x') as stream:json.dump(c,stream,indent=2);stream.write('\n')

results=[]
for name in order:
    time.sleep(3)
    print('START '+name,flush=True)
    try:
        result=run(configs/(name+'.json'),root/name)
    except BaseException as exc:
        (root/'matrix_stop.json').write_text(json.dumps(dict(name=name,error=repr(exc),completed=results),indent=2)+'\n')
        raise
    compact=dict(name=name,run_id=result['run_id'],nominal_rps=result['nominal_rps'],
        started_rps=result['phases']['started_rps'],failures=result['failures'],
        http_mean_ms=result['http_duration_ms']['mean'],http_p95_ms=result['http_duration_ms']['p95'],
        cpu_mean=result['cpu_docker_percent']['mean'],progression=result['progression'],
        worker_wait_p95_ms=result['victim']['work_wait_ms']['p95'] if result['victim'] else None)
    results.append(compact)
    (root/'matrix_progress.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(compact),flush=True)
    if not result['progression']['allowed']:
        (root/'matrix_stop.json').write_text(json.dumps(dict(name=name,reason='progression_guard',completed=results),indent=2)+'\n')
        sys.exit(2)
print('MATRIX_COMPLETE',flush=True)
