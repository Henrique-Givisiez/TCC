"""Single E8 authority adapting frozen E4-R2 review code, without recalibration."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess

from experiments import development_d3_minimal as base

ROOT=base.ROOT
DEFAULT_MANIFEST=ROOT/'experiments/protocols/development_d3_e8_20261028/manifest.json'
ENTRY_ID='d3_pilot_E8_R2'
RULE=base.RULE
_ORIGINAL_ASSESS=base.assess_raw


def seed_inputs():
    result=set()
    for folder in ('experiments/configs','experiments/protocols','docs/stage14a/materialized','experiment_results'):
        for path in (ROOT/folder).rglob('*.json'):
            if any(x in ('development_d3_e8_20261028','development-d3-e8-20261028') for x in path.parts):continue
            if path.stat().st_size==0 or base.old.collect_seeds(base.read(path)):result.add(path)
    if (ROOT/'effective_config.json').exists():result.add(ROOT/'effective_config.json')
    return sorted(result)


def predecessor(plan):
    binding=plan['predecessor']
    path=ROOT/binding['review_path']
    if base.sha(path)!=binding['review_sha256']:raise ValueError('E4-R2 review changed')
    review=base.read(path)
    if base.sha(ROOT/binding['manifest_path'])!=binding['manifest_sha256']:
        raise ValueError('E4-R2 authority changed')
    if review['authority']['manifest_sha256']!=binding['manifest_sha256'] or review['entry_id']!='d3_minimal_E4_R2':
        raise ValueError('Predecessor authority/identity mismatch')
    parent=base.read(ROOT/binding['manifest_path'])
    if parent['rule']!=plan['rule'] or plan['rule']!=RULE:raise ValueError('Service criteria differ from E4-R2')
    for path,h in parent['runtime_source_hashes'].items():
        if base.sha(ROOT/path)!=h:raise ValueError('Validated E4-R2 utility changed: '+path)
    for path,h in review['preserved_raw_hashes'].items():
        if base.sha(path)!=h:raise ValueError('Predecessor raw changed')
    if not (review['classification']['technical_integrity'] and review['classification']['service_observation_valid']
        and review['lifecycle']['controlled_closure'] and review['dataset_validation']['dataset_valid']
        and review['dataset_validation']['analysis_eligible'] and review['operations']['cleanup_verified']
        and review['operations']['execution']['returncode']==0
        and review['service']['last_two_post_windows_qualified']
        and review['service']['reference_compatibility']['compatible']
        and all(w['qualified'] for w in review['service']['post_windows'])
        and all(c['passed'] for c in review['technical_checks'])):
        raise ValueError('E4-R2 evidence does not support this prospective release')
    # The old continued_execution_authorized=False remains untouched. This new
    # authority is a separate, user-requested preparation, never an old gate override.
    return review


def validate_plan(manifest=DEFAULT_MANIFEST,*,check_outputs=True):
    p=base.read(manifest)
    expected_budget=dict(nominal_seconds=390,drain_seconds=30,idle_seconds=60,administrative_seconds=600,envelope_seconds=1080)
    if (p['schema']!='development-d3-e8/v1' or p['partition']!='DEVELOPMENT' or len(p['entries'])!=1
        or p['maximum_attempts']!=1 or p['retry']!=0 or p['automatic_progression'] is not False
        or p['rule']!=RULE or p['budget']!=expected_budget):raise ValueError('E8 authority/rule/budget changed')
    if p['phases']!=[['WARMUP',0,30],['PRE',30,150],['ACTIVE',150,270],['POST',270,390]]:
        raise ValueError('Phase boundaries changed')
    if p['primary_reference']['interval']!=[30,150] or p['secondary_reference']['useful_interval']!=[30,390]:
        raise ValueError('Reference intervals changed')
    previous=predecessor(p)
    for path,h in p['runtime_source_hashes'].items():
        if base.sha(ROOT/path)!=h:raise ValueError('Bound E8 utility changed: '+path)
    for e in p['evidence']:
        if base.sha(ROOT/e['path'])!=e['sha256']:raise ValueError('E8 evidence changed: '+e['path'])
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.run(['git','merge-base','--is-ancestor',p['instrumentation_commit'],head],cwd=ROOT).returncode:
        raise ValueError('Checkout outside E8 source lineage')
    audit=base.read(ROOT/p['seed_audit']['path'])
    if base.sha(ROOT/p['seed_audit']['path'])!=p['seed_audit']['sha256']:raise ValueError('Seed audit changed')
    if {x['path'] for x in audit['sources']}!={str(x.relative_to(ROOT)) for x in seed_inputs()}:
        raise ValueError('Historical seed inventory changed')
    existing=set()
    for item in audit['sources']:
        path=ROOT/item['path'];values=base.old.collect_seeds(base.read(path) if path.stat().st_size else {})
        if base.sha(path)!=item['sha256'] or sorted(values)!=item['seeds']:raise ValueError('Seed history changed')
        existing.update(values)
    g=p['seed_generation'];seed=int.from_bytes(hashlib.sha256(f"{g['namespace']}:{ENTRY_ID}:{g['index']}".encode()).digest()[:8],'big')
    if seed!=p['pilot_seed'] or seed in existing:raise ValueError('E8 seed collision/derivation mismatch')
    e=p['entries'][0]
    if e['id']!=ENTRY_ID or e['requires_review_of']!='d3_minimal_E4_R2':raise ValueError('Only E8-R2 is permitted')
    template=base.read(ROOT/p['configuration_template']['path'])
    if base.sha(ROOT/p['configuration_template']['path'])!=p['configuration_template']['sha256']:raise ValueError('E4-R2 template changed')
    expected={**template,'id':ENTRY_ID,'seed':seed,'attack':{**template['attack'],'rate':8}}
    cfg=base.ExperimentConfig.load(ROOT/e['config']);effective=json.loads(cfg.to_json())
    if effective!=expected or base.read(ROOT/e['config'])!=effective or e['effective_configuration']!=effective or base.sha(ROOT/e['config'])!=e['config_sha256']:
        raise ValueError('Configuration differs beyond ID/seed/attack rate')
    if {str(x.relative_to(ROOT)) for x in (ROOT/e['config']).parent.glob('*.json')}!={e['config']}:
        raise ValueError('Unexpected scenario config')
    control=base.verify_reference(p)
    if any(effective[k]!=control['configuration'][k] for k in base.COMPATIBLE_FIELDS):raise ValueError('C reference config incompatible')
    paths=list(e['outputs'].values())
    if len(paths)!=len(set(paths)) or any(not (ROOT/x).resolve().is_relative_to((ROOT/p['results_root']).resolve()) for x in paths):
        raise ValueError('Output collision/escape')
    if check_outputs and any((ROOT/x).exists() for x in paths):raise FileExistsError('E8 outputs already exist')
    return dict(manifest_sha256=base.sha(manifest),entry=ENTRY_ID,configurations=1,seed=seed,
        seed_collisions=[],historical_seed_files=len(audit['sources']),predecessor_review_sha256=p['predecessor']['review_sha256'],
        source_checkout=dict(effective_checkout_commit=head,source_tree_unchanged=True),docker_accessed=False,experiments_executed=False)


def assess_raw(raw,config,control_raw,control_review):
    report=_ORIGINAL_ASSESS(raw,config,control_raw,control_review)
    # Service evaluation is unchanged. The E4 helper's descriptive nominal attack
    # denominator was fixed at 4; adapt only that metadata to the E8 configuration.
    if report['generator'] is not None:
        for row in report['generator']['nominal_start_adherence']:
            if row['traffic_class']=='attack':
                expected=120*config.attack.rate*config.attack.attackers
                row['nominal_expected']=expected
                row['starts_over_nominal_expectation']=base.ratio(row['starts'],expected)
        report['generator']['configured_offensive_rps']=config.attack.rate*config.attack.attackers
    return report


@contextmanager
def review_context():
    """A serial CLI adapter; restore every in-memory binding even on failure.

    No source file/authority is changed. The frozen E4 review pipeline is reused.
    """
    changes=dict(ROOT=ROOT,validate_plan=validate_plan,assess_raw=assess_raw)
    previous={key:getattr(base,key) for key in changes}
    try:
        for key,value in changes.items():setattr(base,key,value)
        yield
    finally:
        for key,value in previous.items():setattr(base,key,value)


def review_entry(manifest=DEFAULT_MANIFEST):
    with review_context():return base.review_entry(manifest)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,default=DEFAULT_MANIFEST)
    sub=p.add_subparsers(dest='action',required=True);sub.add_parser('validate-plan');sub.add_parser('review')
    args=p.parse_args()
    if args.action=='validate-plan':
        result=validate_plan(args.manifest);print(json.dumps({k:result[k] for k in ('entry','configurations','seed','docker_accessed','experiments_executed')}))
    else:print(json.dumps(base.compact(review_entry(args.manifest))))


if __name__=='__main__':main()
