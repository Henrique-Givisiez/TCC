"""Hash-bound R2 processing release and append-only re-review of the same N1 run."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path

from experiments import development_d3_origins as origins

ROOT=origins.ROOT
DEFAULT_MANIFEST=ROOT/'experiments/protocols/development_d3_origins_20261029/manifest_r2.json'
FIRST=origins.ENTRY_IDS[0]
_ORIGINAL_OPERATION_CHECKS=origins.base.old.operation_checks


def validate_plan(manifest=DEFAULT_MANIFEST,*,check_outputs=False):
    plan=origins.read(manifest);binding=plan['processing_revision']
    parent_path=ROOT/binding['parent_manifest']['path']
    if origins.base.sha(parent_path)!=binding['parent_manifest']['sha256']:
        raise ValueError('R2 parent authority changed')
    parent=origins.read(parent_path)
    # The execution authority remains archived; only processing/output bindings
    # change prospectively. Configs, raw/dataset paths, order and budget are fixed.
    expected=deepcopy(parent)
    expected['runtime_source_hashes']=plan['runtime_source_hashes']
    expected['processing_revision']=binding
    expected['evidence']=parent['evidence']+binding['additional_evidence']
    for entry in expected['entries']:
        for key in ('analysis','validation','review'):
            path=Path(entry['outputs'][key]);entry['outputs'][key]=str(path.with_name(path.stem+'-r2'+path.suffix))
    expected['comparison_outputs']={key:str(Path(value).with_name(Path(value).stem+'_r2'+Path(value).suffix)) for key,value in parent['comparison_outputs'].items()}
    if plan!=expected or binding['revision']!='origins-processing-r2':
        raise ValueError('R2 changed fields outside the prospective processing release')
    archives=binding['archived_sources']
    changed={path for path,h in parent['runtime_source_hashes'].items() if plan['runtime_source_hashes'].get(path)!=h}
    if changed!={'experiments/development_d3_origins_processing.py'} or set(archives)!=changed:
        raise ValueError('Unexpected historical source replacement')
    for source,item in archives.items():
        if item['sha256']!=parent['runtime_source_hashes'][source] or origins.base.sha(ROOT/item['path'])!=item['sha256']:
            raise ValueError('Historical execution source archive changed')
    first=parent['entries'][0];original=origins.reviewed_entry(parent,first,parent_path)
    if (binding['original_review']['path']!=first['outputs']['review']
        or origins.base.sha(ROOT/first['outputs']['review'])!=binding['original_review']['sha256']):
        raise ValueError('Original review changed')
    raw=ROOT/first['outputs']['raw']
    if {str(p):origins.base.sha(p) for p in raw.rglob('*') if p.is_file()}!=original['preserved_raw_hashes']:
        raise ValueError('Original raw inventory changed')
    # Reuses full configuration/seed/reference/lineage checks against R2 hashes.
    result=origins.validate_plan(manifest,check_outputs=check_outputs)
    result['processing_revision']=binding['revision']
    return result


def historical_operation_checks(plan,entry,manifest):
    """Audit execution-time authority using exact archived bytes for changed code."""
    binding=plan['processing_revision'];parent_path=ROOT/binding['parent_manifest']['path']
    parent=origins.read(parent_path);old_entry=origins.find_entry(parent,entry['id'])
    ops=ROOT/parent['results_root']/'operations'/entry['id']
    attempt=origins.read(ops/'attempt.json');pf_path=(ROOT/attempt['preflight_path']).resolve()
    if not pf_path.is_relative_to(ops.resolve()):raise ValueError('Historical preflight path escapes entry')
    pf=origins.read(pf_path);sha=origins.base.sha
    if (attempt['authorization_scope']!=entry['id'] or attempt['manifest_sha256']!=sha(parent_path)
        or pf['manifest_sha256']!=sha(parent_path) or sha(pf_path)!=attempt['preflight_sha256']
        or pf['approved_entry']!=entry['id'] or not pf['ready'] or pf['preflight_id']!=attempt['preflight_id']
        or attempt['approved_source_hashes']!=pf['checks']['operational_code_sha256']
        or any(attempt['approved_source_hashes'].get(k)!=h for k,h in parent['runtime_source_hashes'].items())
        or entry['config_sha256']!=old_entry['config_sha256']):
        raise ValueError('Historical execution/preflight/config authority mismatch')
    verified={}
    for source,h in attempt['approved_source_hashes'].items():
        archive=binding['archived_sources'].get(source)
        actual=archive['path'] if archive else source
        if sha(ROOT/actual)!=h:raise ValueError('Execution source evidence changed: '+source)
        verified[source]=dict(path=actual,sha256=h,archived=bool(archive))
    execution=origins.read(ops/'execution_result.json');cleanup=origins.read(ops/'cleanup_observation.json')
    before={x['id']:x['status'] for x in pf['checks']['containers_before']}
    after={x['id']:x['status'] for x in cleanup['containers']}
    cleanup_ok=(before==after and cleanup['no_active_containers'] and cleanup['no_scientific_processes']
        and cleanup['port_check_returncode']==0 and len(cleanup['port_8080'].strip().splitlines())==1)
    return dict(bound_preflight_path=attempt['preflight_path'],bound_preflight_sha256=attempt['preflight_sha256'],
        execution=execution,cleanup=cleanup,cleanup_verified=cleanup_ok,
        execution_manifest_sha256=sha(parent_path),execution_sources_verified=verified,
        attempt_sha256=sha(ops/'attempt.json'),attempt_reused=True,new_attempt_consumed=False)


@contextmanager
def review_context(entry_id,manifest):
    plan=origins.read(manifest);entry=origins.find_entry(plan,entry_id)
    binding=plan['processing_revision']
    def checks(p,e,m):
        return historical_operation_checks(plan,entry,manifest) if entry_id==FIRST else _ORIGINAL_OPERATION_CHECKS(p,e,m)
    with origins.review_context(entry_id,manifest):
        previous_put=origins.base.put;previous_checks=origins.base.old.operation_checks
        def publish(path,value):
            if Path(path).resolve()==(ROOT/entry['outputs']['review']).resolve():
                value['processing_provenance']=dict(revision=binding['revision'],processing_manifest_path=str(Path(manifest).relative_to(ROOT)),
                    processing_manifest_sha256=origins.base.sha(manifest),code_sha256=plan['runtime_source_hashes'],
                    original_review=binding['original_review'] if entry_id==FIRST else None,
                    execution_manifest_sha256=value['operations'].get('execution_manifest_sha256',origins.base.sha(manifest)),
                    same_run_reanalysis=entry_id==FIRST,new_attempt_consumed=False if entry_id==FIRST else True,
                    publication_utc=datetime.now(timezone.utc).isoformat())
            return previous_put(path,value)
        try:
            origins.base.put=publish;origins.base.old.operation_checks=checks
            yield
        finally:
            origins.base.put=previous_put;origins.base.old.operation_checks=previous_checks


def handoff_record(plan,manifest=DEFAULT_MANIFEST):
    entry=plan['entries'][0];review=origins.reviewed_entry(plan,entry,manifest)
    provenance=review['processing_provenance'];binding=plan['processing_revision']
    if (provenance['revision']!=binding['revision'] or provenance['original_review']!=binding['original_review']
        or provenance['processing_manifest_sha256']!=origins.base.sha(manifest)
        or provenance['code_sha256']!=plan['runtime_source_hashes']
        or provenance['execution_manifest_sha256']!=binding['parent_manifest']['sha256']
        or provenance['same_run_reanalysis'] is not True or provenance['new_attempt_consumed'] is not False
        or review['lifecycle']['run_id']!=origins.read(ROOT/entry['outputs']['raw']/'run_status.json')['run_id']
        or not origins.gate_passes(review)):
        raise ValueError('Corrected first review does not permit prospective progression')
    attempt=ROOT/plan['results_root']/'operations'/FIRST/'attempt.json'
    if review['operations']['attempt_sha256']!=origins.base.sha(attempt):raise ValueError('Consumed attempt changed')
    return dict(revision=binding['revision'],manifest_path=str(Path(manifest).relative_to(ROOT)),
        manifest_sha256=origins.base.sha(manifest),review_path=entry['outputs']['review'],
        review_sha256=origins.base.sha(ROOT/entry['outputs']['review']),run_id=review['lifecycle']['run_id'],
        attempt_sha256=origins.base.sha(attempt),attempt_consumed=True,next_entry=plan['entries'][1]['id'],
        manual_review_hash_required=True,automatic_execution_authorized=False)


def validate_handoff(plan,manifest=DEFAULT_MANIFEST):
    path=Path(manifest).parent/'revision_r2/handoff.json'
    record=handoff_record(plan,manifest)
    if origins.read(path)!=record:raise ValueError('Prospective handoff binding changed')
    return record


def review_entry(entry_id,manifest=DEFAULT_MANIFEST):
    validate_plan(manifest)
    if entry_id!=FIRST:validate_handoff(origins.read(manifest),manifest)
    with review_context(entry_id,manifest):return origins.base.review_entry(manifest)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('validate-plan');r=sub.add_parser('review');r.add_argument('--entry',choices=origins.ENTRY_IDS,required=True)
    sub.add_parser('compare');args=p.parse_args()
    if args.action=='validate-plan':
        result=validate_plan();out={key:result[key] for key in ('entry_count','blocks','processing_revision','docker_accessed','experiments_executed')}
    elif args.action=='review':out=origins.base.compact(review_entry(args.entry))
    else:
        validate_plan();validate_handoff(origins.read(DEFAULT_MANIFEST));report=origins.compare(DEFAULT_MANIFEST);out=dict(runs=len(report['runs']),blocks=2)
    print(json.dumps(out,default=origins.base.old.json_default))


if __name__=='__main__':main()
