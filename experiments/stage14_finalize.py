"""Create post-commit operational provenance without rewriting frozen science.

New artifacts live in ignored experiment_results so the committed tree stays clean.
Never invokes simulation; performs only six BASELINE preflights.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import json

from analysis.detection.inputs import ContractError
from experiments import stage14_scientific as runner
from experiments.stage14a.prepare import write, sha

HISTORICAL_BINDING = 'experiments/protocols/stage14_binding_v2.json'
HISTORICAL_BINDING_SHA256 = '8b542efa2868596eb3a4577b03353c0768d161ed81f9701d5f8466bbac21396f'
PROTOCOL_V2_SHA256 = '59f5311e8ee0a05523c80938b7b08ddfaacd0bf8000a077c9de1ab675803872c'
AUTHORIZED_RUNTIME_UPGRADES = {'experiments/stage14_scientific.py','experiments/stage14_finalize.py'}


def finalize(observation=None):
    root = runner.ROOT
    previous_path = root/HISTORICAL_BINDING
    binding, doc, protocol, documents = runner.load_bundle(previous_path,HISTORICAL_BINDING_SHA256)
    if protocol['protocol_hash'] != PROTOCOL_V2_SHA256:
        raise ContractError('STOP: frozen V2 hash differs')
    current = runner.observe_environment() if observation is None else observation
    if current['dynamic']['git_status']:
        raise ContractError('Post-commit finalization requires clean Git tree')
    historical = documents['environment_lock']['reference']
    diff = runner.environment_check(historical,current)
    if set(diff['fatal']) - {'stable.git_head','runtime_sha256'}:
        raise ContractError(f'Unapproved environment change: {diff["fatal"]}')
    changed = {p for p in set(historical['runtime_sha256']) | set(current['runtime_sha256'])
               if historical['runtime_sha256'].get(p) != current['runtime_sha256'].get(p)}
    if changed - AUTHORIZED_RUNTIME_UPGRADES:
        raise ContractError(f'Unapproved runtime change: {sorted(changed)}')
    head = current['stable']['git_head']
    if head == historical['stable']['git_head']:
        raise ContractError('Finalization requires the new post-commit HEAD')
    destination = root/'experiment_results/stage14-finalization'/head
    destination.mkdir(parents=True,exist_ok=False)
    lock = dict(schema_version=1,reference=current,policy=documents['environment_lock']['policy'],
        historical_environment_lock=binding['references']['environment_lock'],
        source_binding=dict(path=HISTORICAL_BINDING,sha256=HISTORICAL_BINDING_SHA256),
        provenance=dict(kind='post_commit_clean_tree',campaign_git_head=head,
            authorized_runtime_upgrades=sorted(changed),protocol_unchanged=True))
    lock_path = destination/'environment_lock.json'
    write(lock_path,lock)
    final_binding = deepcopy(binding)
    final_binding.update(binding_kind='post_commit_runtime_binding_v1',campaign_git_head=head)
    final_binding['references']['definitive_environment_lock'] = dict(path=str(lock_path.relative_to(root)),sha256=sha(lock_path))
    binding_path = destination/'binding.json'
    write(binding_path,final_binding)
    # Re-open through the actual scientific runner; all scientific refs stay pinned.
    runner.load_bundle(binding_path,sha(binding_path))
    results = []
    for order in range(1,7):
        record = runner.prepare_entry(binding_path,sha(binding_path),partition='baseline',run=order,environment=current)
        row = record['row']
        if (record['status'] != 'dry_run_ready' or record['environment_comparison']['fatal']
                or row['role'] != 'baseline' or row['scenario'] != 'B' or row['duration_seconds'] != 240
                or Path(record['destination']).exists()):
            raise ContractError(f'BASELINE preflight failed: {order}')
        write(destination/f'baseline_{order:02d}_dry_run.json',record)
        results.append(dict(run=order,role=row['role'],scenario=row['scenario'],seed=row['seed'],
            duration_seconds=row['duration_seconds'],status=record['status'],fatal=[],
            output_exists=False,configuration_sha256=row['config_sha256']))
    summary = dict(campaign_git_head=head,branch=current['dynamic']['branch'],git_status=current['dynamic']['git_status'],
        protocol_v1_sha256=sha(root/'experiments/protocols/stage14_protocol.json'),
        protocol_v2_sha256=sha(root/'experiments/protocols/stage14_protocol_v2.json'),
        environment_lock_sha256=sha(lock_path),binding_sha256=sha(binding_path),
        environment_lock=str(lock_path.relative_to(root)),binding=str(binding_path.relative_to(root)),
        baseline_preflights=results,scientific_runs_executed=0,stage14b_started=False,
        containers_active=current['active_containers'],residual_processes=current['residual_processes'])
    write(destination/'summary.json',summary)
    write(destination/'hashes.json',{str(p.relative_to(destination)):sha(p) for p in sorted(destination.iterdir()) if p.is_file()})
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(finalize(),indent=2))

if __name__=='__main__':main()
