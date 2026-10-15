"""Post-pilot integrity/comparability inventory, no detector or evaluation policy."""
import argparse
import json
from pathlib import Path
from .run import OUT,ORDERS,sha,put


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--before',required=True,type=Path)
    args=parser.parse_args();before=json.loads(args.before.read_text())
    changed=[p for p,(h,m) in before.items() if not Path(p).exists() or sha(p)!=h or Path(p).stat().st_mtime_ns!=m]
    if changed:raise RuntimeError(f'Preexisting inputs changed: {changed}')
    # Preserve the starting snapshot beside the report, not only under /tmp.
    put(OUT/'protected_inputs_before.json',before)
    inventory=[];hashes_checked=0;image_sets=[];warnings=[]
    plan=json.loads((OUT/'plan.json').read_text())
    for rel,h in plan['config_sha256'].items():assert sha(OUT/rel)==h
    for seed in ORDERS:
        for scenario in 'BCP':
            case=f'{seed}/{scenario}';d=OUT/'datasets'/case;f=OUT/'features'/case
            cost=json.loads((OUT/'cost'/f'{case}.json').read_text())
            assert sha(OUT/'runner_versions'/f"{cost['runner_sha256']}.py")==cost['runner_sha256']
            manifest=json.loads((d/'dataset_manifest.json').read_text())
            feature=json.loads((f/'feature_manifest.json').read_text())
            report=json.loads((OUT/'validation'/case/'validation_report.json').read_text())
            assert report['analysis_eligible'] and report['dataset_valid']
            assert cost['run_id']==manifest['run_id']==feature['source_run_id']==report['run_id']
            assert sha(d/'dataset_manifest.json')==cost['dataset_manifest_sha256']==feature['dataset_manifest_sha256']==report['dataset_manifest_sha256']
            assert sha(f/'feature_manifest.json')==cost['feature_manifest_sha256']
            for root,entries in [(d,manifest['files']),(f,feature['outputs'])]:
                for entry in entries:
                    p=root/entry['path'];assert sha(p)==entry['sha256'] and p.stat().st_size==entry['bytes']
                    hashes_checked+=1
            env=json.loads((OUT/'environment'/f'{case}.json').read_text())
            images={k:v['Id'] for k,v in env['images'].items()};image_sets.append(images)
            backend=json.loads((d/'metadata/topology/proxy/backend_inventory.json').read_text())
            assert len(backend)==1 and backend[0]['image_id']==images['edos_target_app:latest']
            assert json.loads((d/'metadata/topology/sources/image_identity.json').read_text())['image_id']==images['edos_sources:stage5']
            c=json.loads((d/'metadata/effective_config.json').read_text())
            assert c['normal_traffic']['endpoint']==c['attack']['endpoint']=='/medium'
            assert c['seed']==seed and c['duration_seconds']==84
            ws=[ch['check_id'] for ch in report['checks'] if ch['passed'] is False and ch['severity']=='WARNING'];warnings.extend(ws)
            inventory.append(dict(seed=seed,scenario=scenario,run_id=cost['run_id'],status=cost['status'],
                analysis_eligible=True,dataset_manifest_sha256=sha(d/'dataset_manifest.json'),feature_manifest_sha256=sha(f/'feature_manifest.json'),
                last_observation_seconds=feature['window']['last_observation_seconds'],grid_end_seconds=feature['window']['grid_end_seconds'],
                lifecycle_seconds=cost['simulation_lifecycle_seconds'],wall_seconds=cost['total_wall_seconds'],
                sizes_bytes=cost['sizes_bytes'],warnings=ws,availability=cost['feature_availability']))
    assert all(images==image_sets[0] for images in image_sets)
    put(OUT/'audit.json',dict(protected_files_checked=len(before),changed_protected_files=changed,
        manifest_entries_verified=hashes_checked,all_image_ids_equal=True,images=image_sets[0],
        inventory=inventory,warning_ids=sorted(set(warnings)),pilot_source_sha256={str(p):sha(p) for p in Path(__file__).parent.glob('*.py')},
        no_commit=True,no_previous_stage_files_changed=True))
    print(f'PASS: {len(inventory)} runs, {hashes_checked} entries, {len(before)} protected files unchanged')

if __name__=='__main__':main()
