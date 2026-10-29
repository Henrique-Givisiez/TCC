"""Four-entry DEVELOPMENT N1/N2 authority using frozen E8-R2 service criteria."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import subprocess

from experiments import development_d3_e8 as e8

base=e8.base
ROOT=base.ROOT
DEFAULT_MANIFEST=ROOT/'experiments/protocols/development_d3_origins_20261029/manifest.json'
ORDER=[('A','N1'),('A','N2'),('B','N2'),('B','N1')]
ENTRY_IDS=tuple('d3_origins_'+block+'_'+endpoint for block,endpoint in ORDER)
RULE=base.RULE
_ORIGINAL_READ=base.read
_ORIGINAL_PUT=base.put


def read(path):
    return json.loads(Path(path).read_text())


def find_entry(plan,entry_id):
    matches=[e for e in plan['entries'] if e['id']==entry_id]
    if len(matches)!=1:raise ValueError('Unknown/duplicate D3_origins entry')
    return matches[0]


def seed_inputs():
    paths=set()
    for folder in ('experiments/configs','experiments/protocols','docs/stage14a/materialized','experiment_results'):
        for p in (ROOT/folder).rglob('*.json'):
            if any(x in ('development_d3_origins_20261029','development-d3-origins-20261029') for x in p.parts):continue
            if p.stat().st_size==0 or base.old.collect_seeds(read(p)):paths.add(p)
    if (ROOT/'effective_config.json').exists():paths.add(ROOT/'effective_config.json')
    return sorted(paths)


def exploratory_evidence(plan):
    item=plan['E8_reference'];review=read(ROOT/item['review_path'])
    if base.sha(ROOT/item['review_path'])!=item['review_sha256'] or base.sha(ROOT/item['manifest_path'])!=item['manifest_sha256']:
        raise ValueError('E8-R2 historical binding changed')
    parent=read(ROOT/item['manifest_path'])
    if parent['rule']!=plan['rule'] or parent['phases']!=plan['phases']:
        raise ValueError('Rule/phases differ from E8-R2')
    if review['authority']['manifest_sha256']!=item['manifest_sha256'] or review['entry_id']!='d3_pilot_E8_R2':
        raise ValueError('E8-R2 identity/authority mismatch')
    for path,h in parent['runtime_source_hashes'].items():
        if base.sha(ROOT/path)!=h:raise ValueError('Validated utility changed: '+path)
    for path,h in review['preserved_raw_hashes'].items():
        if base.sha(path)!=h:raise ValueError('Exploratory E8 raw changed')
    if not (review['classification']['technical_integrity'] and review['classification']['service_observation_valid']
            and review['lifecycle']['controlled_closure'] and review['service']['last_two_post_windows_qualified']
            and review['operations']['cleanup_verified']):raise ValueError('E8 exploratory evidence is not technically supported')
    return parent,review


def prior_campaign_readiness(plan):
    """Verify the terminal cost review as historical evidence, never N2 authority."""
    from experiments import development_d3_cost as historical
    binding=plan['readiness_reference']
    manifest=ROOT/binding['manifest_path']
    if base.sha(manifest)!=binding['manifest_sha256']:
        raise ValueError('Prior campaign manifest changed')
    previous=read(manifest);entry=historical.find_entry(previous,binding['entry_id'])
    if entry!=previous['entries'][-1] or entry['outputs']['review']!=binding['review_path']:
        raise ValueError('Readiness must select the final cost entry')
    review=historical.reviewed_entry(previous,entry,manifest)
    if base.sha(ROOT/binding['review_path'])!=binding['review_sha256'] or not gate_passes(review):
        raise ValueError('Cost readiness review changed/failed')
    return review


def validate_plan(manifest=DEFAULT_MANIFEST,*,check_outputs=True):
    p=read(manifest)
    if (p['schema']!='development-d3-origins/v1' or p['partition']!='DEVELOPMENT' or p['maximum_attempts']!=4
            or p['retry']!=0 or p['automatic_progression'] is not False or p['rule']!=RULE
            or [e['id'] for e in p['entries']]!=list(ENTRY_IDS)):
        raise ValueError('D3_origins authority/order/rule changed')
    parent,_=exploratory_evidence(p)
    design=read(ROOT/p['approved_design']['path'])
    if base.sha(ROOT/p['approved_design']['path'])!=p['approved_design']['sha256'] or p['conditions']!=design['conditions']:
        raise ValueError('Approved design binding changed')
    prior_campaign_readiness(p)
    if (p['results_root']!='experiment_results/development-d3-origins-20261029'
        or p['automatic_batch_execution'] is not False or p['next_execution_authorized'] is not False):
        raise ValueError('Origins paths or preparation-only scope changed')
    if (p['budget']['per_entry']!=parent['budget'] or p['budget']['envelope_seconds']!=4320
        or p['budget']['nominal_seconds']!=1560 or p['budget']['drain_seconds']!=120
        or p['budget']['idle_seconds']!=240 or p['budget']['administrative_seconds']!=2400):
        raise ValueError('Four-entry budget changed')
    if p['primary_reference']!=parent['primary_reference'] or p['secondary_reference']!=parent['secondary_reference']:
        raise ValueError('References differ from E8-R2')
    for path,h in p['runtime_source_hashes'].items():
        if base.sha(ROOT/path)!=h:raise ValueError('Bound origins utility changed: '+path)
    for item in p['evidence']:
        if base.sha(ROOT/item['path'])!=item['sha256']:raise ValueError('Evidence changed: '+item['path'])
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.run(['git','merge-base','--is-ancestor',p['instrumentation_commit'],head],cwd=ROOT).returncode:
        raise ValueError('Checkout outside recorded lineage')
    a=read(ROOT/p['seed_audit']['path'])
    if base.sha(ROOT/p['seed_audit']['path'])!=p['seed_audit']['sha256']:raise ValueError('Seed audit changed')
    if {x['path'] for x in a['sources']}!={str(x.relative_to(ROOT)) for x in seed_inputs()}:raise ValueError('Historical seed inventory changed')
    used=set()
    for item in a['sources']:
        path=ROOT/item['path'];values=base.old.collect_seeds(read(path) if path.stat().st_size else {})
        if base.sha(path)!=item['sha256'] or sorted(values)!=item['seeds']:raise ValueError('Historical seed source changed')
        used.update(values)
    generated={}
    for block in ('A','B'):
        g=p['seed_generation'];n=int.from_bytes(hashlib.sha256(f"{g['namespace']}:{block}:{g['indices'][block]}".encode()).digest()[:8],'big')
        if n!=p['block_seeds'][block] or n in used or n in generated.values():raise ValueError('Seed collision/derivation mismatch')
        generated[block]=n
    template=read(ROOT/p['configuration_template']['path'])
    if base.sha(ROOT/p['configuration_template']['path'])!=p['configuration_template']['sha256']:raise ValueError('E8 template changed')
    paths=[]
    for i,(e,(block,endpoint)) in enumerate(zip(p['entries'],ORDER)):
        expected={**template,'id':e['id'],'seed':generated[block],'attack':{**template['attack'],'endpoint':'/expensive','attackers':1 if endpoint=='N1' else 2,'rate':8 if endpoint=='N1' else 4}}
        cfg=base.ExperimentConfig.load(ROOT/e['config']);effective=json.loads(cfg.to_json())
        if (e['block']!=block or e['endpoint']!='/expensive' or e['condition']!=endpoint or e['order']!=i+1
            or e['requires_review_of']!=(p['entries'][i-1]['id'] if i else None)
            or effective!=expected or read(ROOT/e['config'])!=effective or e['effective_configuration']!=effective
            or base.sha(ROOT/e['config'])!=e['config_sha256']):raise ValueError('Config/pairing/order differs beyond ID/seed/offensive origin count and per-origin rate')
        paths.extend(e['outputs'].values())
    directory=(ROOT/p['entries'][0]['config']).parent
    if {str(x.relative_to(ROOT)) for x in directory.glob('*.json')}!={e['config'] for e in p['entries']}:raise ValueError('Unexpected config')
    base.verify_reference(p)
    paths+=list(p['comparison_outputs'].values())
    if len(paths)!=len(set(paths)) or any(not (ROOT/x).resolve().is_relative_to((ROOT/p['results_root']).resolve()) for x in paths):
        raise ValueError('Output collision/escape')
    if check_outputs and any((ROOT/x).exists() for x in paths):raise FileExistsError('Reserved outputs already exist')
    return dict(entry_count=4,blocks=2,block_seeds=generated,manifest_sha256=base.sha(manifest),
        seed_collisions=[],historical_seed_files=len(a['sources']),source_checkout=dict(effective_checkout_commit=head,bound_source_files_verified=True),
        docker_accessed=False,experiments_executed=False)


_ORIGINAL_ASSESS=base.assess_raw


def assess_raw(raw,config,control_raw,control_review):
    from experiments import development_d3_origins_processing as processing
    changes=[(base.old,'reconcile',processing.reconcile),(base.old,'validate_ground_truth',processing.validate_ground_truth),
             (base,'generator_evidence',processing.generator_evidence)]
    previous=[getattr(module,key) for module,key,_ in changes]
    try:
        for module,key,value in changes:setattr(module,key,value)
        return _ORIGINAL_ASSESS(raw,config,control_raw,control_review)
    finally:
        for (module,key,_),value in zip(changes,previous):setattr(module,key,value)


@contextmanager
def review_context(entry_id,manifest):
    plan=read(manifest);entry=find_entry(plan,entry_id)
    view={**plan,'entries':[entry]}
    def selected_read(path):
        return view if Path(path).resolve()==Path(manifest).resolve() else _ORIGINAL_READ(path)
    def published(path,value):
        if Path(path).resolve()==(ROOT/entry['outputs']['review']).resolve():
            value['campaign_identity']=dict(block=entry['block'],offensive_endpoint=entry['endpoint'],condition=entry['condition'],attackers=entry['effective_configuration']['attack']['attackers'],seed=entry['effective_configuration']['seed'])
            cleanup=value.get('operations',{}).get('cleanup')
            if cleanup:value['timing']=dict(cleanup_observation=dict(epoch=cleanup['observed_epoch']))
        return _ORIGINAL_PUT(path,value)
    changes=dict(ROOT=ROOT,read=selected_read,put=published,validate_plan=validate_plan,assess_raw=assess_raw)
    before={k:getattr(base,k) for k in changes}
    try:
        for k,v in changes.items():setattr(base,k,v)
        yield
    finally:
        for k,v in before.items():setattr(base,k,v)


def review_entry(entry_id,manifest=DEFAULT_MANIFEST):
    with review_context(entry_id,manifest):return base.review_entry(manifest)


def reviewed_entry(plan,entry,manifest):
    path=ROOT/entry['outputs']['review'];r=read(path)
    if (r['entry_id']!=entry['id'] or r['authority']['manifest_sha256']!=base.sha(manifest)
        or r['authority']['config_sha256']!=entry['config_sha256']
        or r['campaign_identity']!=dict(block=entry['block'],offensive_endpoint=entry['endpoint'],condition=entry['condition'],attackers=entry['effective_configuration']['attack']['attackers'],seed=entry['effective_configuration']['seed'])):
        raise ValueError('Review entry/block/authority binding mismatch')
    for raw,h in r['preserved_raw_hashes'].items():
        if base.sha(raw)!=h:raise ValueError('Run raw changed since review')
    return r


def gate_passes(r):
    return bool(r['classification']['technical_integrity'] and r['classification']['service_observation_valid']
        and r['lifecycle']['controlled_closure'] and r['dataset_validation']['dataset_valid'] and r['dataset_validation']['analysis_eligible']
        and r['operations']['cleanup_verified'] and r['operations']['execution']['returncode']==0
        and r['service']['reference_compatibility']['compatible'] and r['service']['last_two_post_windows_qualified']
        and all(c['passed'] for c in r['technical_checks']))


def run_metrics(entry,review):
    raw=ROOT/entry['outputs']['raw'];rows=base.load_requests(raw/'request_log.csv',review['lifecycle']['run_id'])
    benign=[r for r in rows if r['traffic_class']=='benign'];phases={}
    for name,a,b in (('PRE',30,150),('ACTIVE',150,270),('POST',270,390)):
        r=next(x for x in review['class_phase_service']['rows'] if x['traffic_class']=='benign' and x['phase']==name)
        cpu=review['resources']['phases'][name]
        phases[name]=dict(starts=r['starts'],start_rps=base.number(r['rates_per_second']['starts']),
            success_2xx=r['cohort_outcomes']['success_2xx'],success_fraction=base.number(r['cohort_fractions']['success_2xx_per_started']) if r['starts'] else None,
            http_errors=r['cohort_outcomes']['http_error'],transport_errors=r['cohort_outcomes']['transport_error'],client_errors=r['cohort_outcomes']['client_error'],
            incomplete=r['cohort_incomplete_no_end'],open_at_final_cutoff=r['cohort_open_as_of'],
            mean_ms=r['duration_success_2xx_ms']['mean'],p50_ms=r['duration_success_2xx_ms']['p50'],p95_ms=r['duration_success_2xx_ms']['p95'],
            pending_start=len(base.pending(benign,D(a))),pending_end=len(base.pending(benign,D(b))),
            resources=cpu,victim_cpu_mean=cpu['victim_cpu_docker_percent']['mean'],proxy_cpu_mean=cpu['proxy_cpu_docker_percent']['mean'])
    offense=next(x for x in review['generator']['nominal_start_adherence'] if x['traffic_class']=='attack')
    return dict(entry=entry['id'],block=entry['block'],endpoint=entry['endpoint'],condition=entry['condition'],seed=entry['effective_configuration']['seed'],
        technical_integrity=review['classification']['technical_integrity'],service_state=review['classification']['service_state'],
        legitimate=phases,offense=dict(nominal_rps=8,starts_ACTIVE=offense['starts'],exposure_seconds=120,
            observed_start_rps=base.ratio(offense['starts'],120),starts_over_nominal_expectation=offense['starts_over_nominal_expectation'],
            admission=review['generator']['attack_admission'],per_origin=offense['per_origin'],start_count_range=max(x['starts'] for x in offense['per_origin'])-min(x['starts'] for x in offense['per_origin']),full_scheduled_load_verified=False),
        generator_by_phase=review['generator']['nominal_start_adherence'],service_diagnostics=review['service'],
        review_sha256=base.sha(ROOT/entry['outputs']['review']))


def contrast(left,right,*,same_seed):
    keys=('starts','start_rps','success_fraction','mean_ms','p95_ms','http_errors','transport_errors','incomplete','pending_start','pending_end','victim_cpu_mean','proxy_cpu_mean')
    differences={}
    for phase in ('PRE','ACTIVE','POST'):
        differences[phase]={}
        for key in keys:
            a,b=left['legitimate'][phase][key],right['legitimate'][phase][key]
            differences[phase][key]=base.number(a)-base.number(b) if a is not None and b is not None else None
    a,b=left['offense']['observed_start_rps'],right['offense']['observed_start_rps']
    return dict(same_seed=same_seed,left=left['entry'],right=right['entry'],left_minus_right=differences,
        observed_offensive_rps=dict(left=a,right=b,left_minus_right=a-b,ratio_left_over_right=base.ratio(a,b)),
        realized_offensive_starts_differ=a!=b,
        interpretation='Planned equal aggregate nominal rate and worker budget; different origin counts; different realized arrivals are part of the descriptive contrast, not corrected away or proof of equal offered opportunities.')


def compare(manifest=DEFAULT_MANIFEST):
    validate_plan(manifest,check_outputs=False);plan=read(manifest)
    for path in plan['comparison_outputs'].values():
        if (ROOT/path).exists():raise FileExistsError('Comparison output exists; never overwrite')
    reviews={e['id']:reviewed_entry(plan,e,manifest) for e in plan['entries']}
    if len({r['lifecycle']['run_id'] for r in reviews.values()})!=4:
        raise ValueError('Four distinct run IDs required; pilots/copies cannot replace entries')
    runs={e['id']:run_metrics(e,reviews[e['id']]) for e in plan['entries']}
    pairs={}
    for block in ('A','B'):
        left,right=runs[f'd3_origins_{block}_N2'],runs[f'd3_origins_{block}_N1']
        valid=left['technical_integrity'] and right['technical_integrity']
        pairs[block]=dict(technical_pair_valid=valid,contrast=contrast(left,right,same_seed=True) if valid else None)
    between={endpoint:contrast(runs[f'd3_origins_B_{endpoint}'],runs[f'd3_origins_A_{endpoint}'],same_seed=False)
             for endpoint in ('N1','N2') if runs[f'd3_origins_B_{endpoint}']['technical_integrity'] and runs[f'd3_origins_A_{endpoint}']['technical_integrity']}
    report=dict(schema='development-d3-origins-comparison/v1',manifest_sha256=base.sha(manifest),runs=runs,
        within_block_N2_minus_N1=pairs,between_block_B_minus_A_by_condition=between,
        pilot_runs_in_comparison=0,exploratory_references=plan['exploratory_references'],
        limitations=['Common seed shares random-number streams, not guaranteed identical start times/counts.',
            'Two blocks and inverted order do not remove period/environment effects or identify maximum capacity.',
            'Never pool percentiles or treat A/B as the same seed; no detector/calibration tuning.'],
        generator_scope='Service received by observed starts; independent legitimate opportunity schedule unavailable.')
    base.put(ROOT/plan['comparison_outputs']['json'],report)
    lines=['# DEVELOPMENT D3_origins — comparação','',
           '| Entrada | Seed/bloco | Condição | Starts/RPS ataque ACTIVE | Starts legítimos ACTIVE | 2xx/fração | Média/p95 ms | CPU vítima/proxy % |',
           '|---|---|---|---|---:|---|---|---|']
    def fmt(value,n=3):return 'null' if value is None else f'{base.number(value):.{n}f}'
    for entry in plan['entries']:
        r=runs[entry['id']];l=r['legitimate']['ACTIVE'];o=r['offense']
        lines.append(f"| {r['entry']} | {r['seed']}/{r['block']} | {r['condition']} | {o['starts_ACTIVE']}/{fmt(o['observed_start_rps'])} | {l['starts']} | {l['success_2xx']}/{fmt(l['success_fraction'])} | {fmt(l['mean_ms'],2)}/{fmt(l['p95_ms'],2)} | {fmt(l['victim_cpu_mean'],2)}/{fmt(l['proxy_cpu_mean'],2)} |")
    lines+=['','| Entrada/origem | Starts ACTIVE | RPS observado | RPS nominal |','|---|---:|---:|---:|']
    for r in runs.values():
        for source in r['offense']['per_origin']:
            lines.append(f"| {r['entry']}/{source['source_id']} | {source['starts']} | {fmt(source['observed_start_rps'])} | {source['nominal_rps']} |")
    lines+=['','| Bloco (mesma seed) | RPS ataque N2/N1 | ΔRPS | Δp95 legítimo ACTIVE ms | ΔCPU vítima/proxy pp |',
        '|---|---:|---:|---:|---:|']
    for block,value in pairs.items():
        x=value['contrast']
        if x is None:
            lines.append(f'| {block} | comparação técnica inválida | null | null | null |')
            continue
        rates=x['observed_offensive_rps'];d=x['left_minus_right']['ACTIVE']
        lines.append(f"| {block} | {fmt(rates['left'])}/{fmt(rates['right'])} | {fmt(rates['left_minus_right'])} | {fmt(d['p95_ms'],2)} | {fmt(d['victim_cpu_mean'],2)}/{fmt(d['proxy_cpu_mean'],2)} |")
    lines+=['','Δ=N2−N1 dentro de cada bloco. A/B usam seeds distintas: variação B−A por condição está separada no JSON.',
        'JSON: serviço PRE/ACTIVE/POST, recursos completos, diagnósticos de prazo/pendências, taxas iniciadas e contrastes por bloco/entre seeds. Diferenças de oferta observada ficam explícitas; taxa nominal igual não prova carga realizada igual. Pilotos anteriores são referências, não réplicas destas quatro execuções.']
    with (ROOT/plan['comparison_outputs']['markdown']).open('x') as stream:stream.write('\n'.join(lines)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,default=DEFAULT_MANIFEST)
    sub=p.add_subparsers(dest='action',required=True);sub.add_parser('validate-plan');r=sub.add_parser('review');r.add_argument('--entry',choices=ENTRY_IDS,required=True);sub.add_parser('compare')
    args=p.parse_args()
    if args.action=='validate-plan':
        x=validate_plan(args.manifest);out={k:x[k] for k in ('entry_count','blocks','block_seeds','docker_accessed','experiments_executed')}
    elif args.action=='review':out=base.compact(review_entry(args.entry,args.manifest))
    else:
        x=compare(args.manifest);out=dict(runs=len(x['runs']),blocks=2,pilot_runs=0,comparison=read(args.manifest)['comparison_outputs']['json'])
    print(json.dumps(out,default=base.old.json_default))


if __name__=='__main__':main()
