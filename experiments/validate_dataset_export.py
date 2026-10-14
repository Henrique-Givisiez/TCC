"""Stage 8 export regression: archival integrity and dataset-only audit answers."""
import argparse
import csv
import json
from pathlib import Path

from experiments.dataset_provenance import sha256_file
from experiments.export_dataset import export_run


def audit_export(directory, verify_originals=False):
    directory = Path(directory)
    manifest = json.loads((directory / 'dataset_manifest.json').read_text())
    for entry in manifest['files']:
        assert sha256_file(directory / entry['path']) == entry['sha256'], entry['path']
        if verify_originals and entry['origin_path']:
            assert sha256_file(entry['origin_path']) == entry['sha256'], entry['origin_path']
    config = json.loads((directory / manifest['configuration']).read_text())
    status = json.loads((directory / manifest['run_status']).read_text())
    inventory = json.loads((directory / manifest['source_inventory']).read_text()) if manifest['source_inventory'] else []
    event_path = directory / 'raw/attacks/attack_events.csv'
    events = []
    if event_path.exists():
        with event_path.open() as stream:
            events = list(csv.DictReader(stream))
    execution = manifest['execution_provenance']
    git = json.loads((directory / execution['path']).read_text())['code']['git'] if execution['status'] == 'recorded' else None
    return dict(run_id=manifest['run_id'], status=status['status'], errors=status.get('errors'),
                seed=config.get('seed'), configuration=manifest['configuration'], execution_git=git,
                normal_sources=config.get('normal_traffic', {}).get('clients'),
                attackers=config.get('attack', {}).get('attackers'), attack=config.get('attack'),
                source_addresses=[{k: s.get(k) for k in ('source_id', 'container_name', 'ip', 'traffic_class')} for s in inventory],
                events=events, artifacts=[e['path'] for e in manifest['files'] if e['group'] in ('traffic', 'service', 'infrastructure', 'attacks')],
                original_files_verified=sum(e['origin_path'] is not None for e in manifest['files']) if verify_originals else 0,
                dataset=str(directory))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output must be new; no overwriting datasets')
    summaries = []
    for root in args.runs:
        for configuration in sorted(root.rglob('effective_config.json')):
            run = configuration.parent
            if not any((run / name).exists() for name in ('run_status.json', 'run_status_run.json')):
                continue
            target = args.output / root.name / run.relative_to(root)
            export_run(run, target)
            summaries.append(audit_export(target, verify_originals=True))
    if not summaries:
        parser.error('No identifiable runs found')
    (args.output / 'export_validation.json').write_text(json.dumps(summaries, indent=2) + '\n')
    print(json.dumps(dict(exports=len(summaries), originals_verified=sum(s['original_files_verified'] for s in summaries),
                          completed=sum(s['status'] == 'completed' for s in summaries),
                          incomplete=sum(s['status'] == 'incomplete' for s in summaries))))


if __name__ == '__main__':
    main()
