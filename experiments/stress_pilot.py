"""Single E12 DEVELOPMENT authority; never releases E16/E20 or scientific TEST."""
import argparse
import hashlib
import json
from pathlib import Path
from experiments import development_d3_minimal as base
ROOT=base.ROOT
ENTRY_ID='stress_E12_A'
DEFAULT_MANIFEST=ROOT/'experiments/protocols/development_stress_e12_20261029/manifest.json'
def validate_plan(manifest=DEFAULT_MANIFEST,check_outputs=True):
    p=base.read(manifest)
    if len(p['entries'])!=1 or p['maximum_attempts']!=1 or p['automatic_progression'] or p['retry']!=0: raise ValueError('one attempt only')
    if p['schema']!='development-stress-e12/v1' or p['partition']!='DEVELOPMENT' or p['budget']!=dict(nominal_seconds=390,drain_seconds=30,idle_seconds=60,administrative_seconds=600,envelope_seconds=1080): raise ValueError('authority scope/budget changed')
    g=p['seed_generation']
    seed=int.from_bytes(hashlib.sha256(f"{g['namespace']}:{ENTRY_ID}:{g['index']}".encode()).digest()[:8],'big')
    if seed!=p['pilot_seed']: raise ValueError('seed derivation changed')
    e=p['entries'][0]
    if e['id']!=ENTRY_ID or p['results_root']!='experiment_results/development-stress-e12-20261029':raise ValueError('identity/root changed')
    paths=list(e['outputs'].values())
    if len(paths)!=len(set(paths)) or any(not (ROOT/x).resolve().is_relative_to((ROOT/p['results_root']).resolve()) for x in paths):raise ValueError('output collision/escape')
    if {x.name for x in (ROOT/e['config']).parent.glob('*.json')}!={'stress_E12_A.json'}:raise ValueError('only E12 may be materialized')
    cfg=base.read(ROOT/e['config'])
    expected=base.read(ROOT/p['configuration_template']['path'])
    expected.update(id=ENTRY_ID,seed=p['pilot_seed']); expected['attack']['rate']=12
    if cfg!=expected or e['effective_configuration']!=cfg or base.sha(ROOT/e['config'])!=e['config_sha256']: raise ValueError('configuration drift')
    for path,digest in p['runtime_source_hashes'].items():
        if base.sha(ROOT/path)!=digest: raise ValueError('source drift: '+path)
    for item in p['evidence']+[p['seed_audit'],p['configuration_template']]:
        if base.sha(ROOT/item['path'])!=item['sha256']: raise ValueError('bound evidence changed')
    audit=base.read(ROOT/p['seed_audit']['path'])
    if p['pilot_seed'] in audit['existing_seeds']: raise ValueError('seed collision')
    for item in audit['sources']:
        if base.sha(ROOT/item['path'])!=item['sha256']: raise ValueError('seed source changed')
    if check_outputs and any((ROOT/v).exists() for v in e['outputs'].values()): raise FileExistsError('attempt output exists')
    return dict(entry=ENTRY_ID,configurations=1,seed=p['pilot_seed'],docker_accessed=False,experiments_executed=False)

def review(raw):
    from experiments import stress_processing as proc
    cfg=base.ExperimentConfig.load(ROOT/base.read(DEFAULT_MANIFEST)['entries'][0]['config'])
    result=proc.reconcile(raw,cfg)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['validate-plan','review']);a=p.parse_args()
    if a.action=='validate-plan': print(json.dumps(validate_plan()))
    else:
        validate_plan(check_outputs=False)
        from experiments.stress_review import publish
        print(json.dumps(publish()))
if __name__=='__main__': main()
