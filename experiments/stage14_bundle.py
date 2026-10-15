"""Append-only materialization of reviewed V2 and its execution bindings."""
from copy import deepcopy
from pathlib import Path

from analysis.detection.protocol import (FROZEN_V2, UNRESOLVED_V2, V1_SHA256,
    V2_BINDINGS, load_protocol, write_protocol)
from experiments.stage14a.prepare import write, sha
from experiments.stage14_scientific import (ROOT, PLAN_PATH, PLAN_HASH, OUTPUT_ROOT,
    observe_environment, environment_check, now)


def materialize(root=ROOT, observation=None):
    import json
    root=Path(root)
    original_path=root/PLAN_PATH
    if sha(original_path)!=PLAN_HASH:
        raise RuntimeError('Stage14A plan changed')
    old=json.loads(original_path.read_text())
    v1, ref=load_protocol(root/'experiments/protocols/stage14_protocol.json',expected_hash=V1_SHA256)
    observation=observe_environment() if observation is None else observation
    comparison=environment_check(observation,observation)
    if comparison['fatal']:
        raise RuntimeError(f'Environment not quiescent/native: {comparison}')
    paths=[root/p for p in V2_BINDINGS]
    target=root/'experiments/protocols/stage14_protocol_v2.json'
    binding_path=root/'experiments/protocols/stage14_binding_v2.json'
    outputs=paths+[target,binding_path,target.with_suffix('.sha256'),binding_path.with_suffix('.sha256')]
    if any(p.exists() for p in outputs):
        raise FileExistsError('V2 outputs exist; no implicit overwrite/revision')
    seed_plan=dict(schema_version=1,partitions=old['partitions'],generation=old['seed_generation'],
        smoke_development=old['smoke_development'],pilot_exclusions=v1['seeds']['excluded'],
        source_stage14a_plan=dict(path=PLAN_PATH,sha256=PLAN_HASH))
    matrix=dict(schema_version=1,run_count=66,nominal_seconds=12672,
        runs=[dict(r,role=r['partition']) for r in old['runs']])
    lock=dict(schema_version=1,reference=observation,
        policy=dict(fatal=['OS/version, kernel, architecture, Python, installed dependencies',
            'Git HEAD, scientific source/recipes/runtime file hashes',
            'Docker client/server, daemon identity, Engine OS/kernel, driver/cgroup, context default',
            'image IDs/RepoDigests; missing query evidence; active containers/traffic/capture'],
            recorded_only=['branch and dirty status (runtime code remains hash-checked)',
                           'CPU model/count, memory total/available, load, timestamps, PIDs, executable path'],
            on_difference='Never update lock implicitly. Fatal divergences prevent simulation; independent audit retained.'))
    for path,value in zip(paths,[seed_plan,matrix,lock]):write(path,value)
    v2=deepcopy(v1)
    v2.update(protocol_version=2,previous_protocol_hash=V1_SHA256,created_at_utc=now(),frozen=deepcopy(FROZEN_V2),
        unresolved={k:dict(status='UNRESOLVED',value=None) for k in UNRESOLVED_V2})
    v2['seeds'].update(status='MATERIALIZED',partitions=old['partitions'])
    v2['references'].update({p:sha(root/p) for p in V2_BINDINGS})
    v2['provenance'].update(revision='Stage14A.1 explicit correction BEFORE scientific collection',
        stage14a_source_plan_sha256=PLAN_HASH,scientific_runs_before_revision=0)
    write_protocol(target,v2,previous=ref)
    references={name:dict(path=str(path.relative_to(root)),sha256=sha(path))
        for name,path in zip(['seed_plan','matrix','environment_lock','protocol'],paths+[target])}
    references['source_stage14a_plan']=dict(path=PLAN_PATH,sha256=PLAN_HASH)
    write(binding_path,dict(schema_version=1,references=references,output_root=str(OUTPUT_ROOT),test_release='LOCKED'))
    for path in [target,binding_path]:
        with path.with_suffix('.sha256').open('x') as f:f.write(f'{sha(path)}  {path.name}\n')
    return dict(protocol_sha256=sha(target),binding_sha256=sha(binding_path))

if __name__=='__main__':print(materialize())
