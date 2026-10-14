"""Offline, byte-preserving export of one run. No simulation imports."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import tempfile

from experiments.dataset_provenance import capture_provenance, sha256_file
from experiments.dataset_schema import schema

TABLES = {'request_log.csv': 'requests', 'rtt_log.csv': 'rtt',
          'traffic_capture.csv': 'packets', 'simulation_metrics.csv': 'metrics',
          'attack_events.csv': 'attacks', 'attack_summary_log.csv': 'attack_summary',
          'normal_traffic_summary_log.csv': 'normal_summary'}
ALIASES = {'request_log_run.csv': 'request_log.csv', 'metrics_run.csv': 'simulation_metrics.csv',
           'attack_events_run.csv': 'attack_events.csv', 'run_status_run.json': 'run_status.json'}
CORE = set(TABLES) - {'attack_summary_log.csv', 'normal_traffic_summary_log.csv'}


def placement(relative):
    name = ALIASES.get(relative.as_posix(), relative.as_posix())
    if name in TABLES:
        group = {'requests': 'service', 'rtt': 'service', 'packets': 'traffic',
                 'metrics': 'infrastructure', 'attacks': 'attacks'}.get(TABLES[name])
        if group:
            return f'raw/{group}/{name}', group, 'observed', TABLES[name]
    if name in ('effective_config.json', 'run_status.json', 'source_inventory.json', 'run_provenance.json'):
        return f'metadata/{name}', 'metadata', 'canonical', None
    if name == 'source_artifacts/traffic_capture.pcap':
        return 'raw/traffic/traffic_capture.pcap', 'traffic', 'observed', None
    if name == 'proxy_artifacts/routing_evidence.jsonl':
        return 'raw/service/routing_evidence.jsonl', 'service', 'operational_evidence', None
    if relative.parts[0] == 'proxy_artifacts':
        if relative.name in ('identity.json', 'backend_inventory.json', 'capture_metadata.json', 'proxy_config.conf'):
            return f'metadata/topology/proxy/{relative.name}', 'metadata', 'topology', None
        return 'evidence/proxy/' + '/'.join(relative.parts[1:]), 'evidence', 'operational', None
    if relative.parts[0] == 'source_artifacts':
        if len(relative.parts) == 2 and relative.name in ('image_identity.json', 'source_plan.json', 'clock_validation.json'):
            return f'metadata/topology/sources/{relative.name}', 'metadata', 'topology', None
        return 'evidence/sources/' + '/'.join(relative.parts[1:]), 'evidence', 'operational', None
    return f'evidence/other/{name}', 'evidence', 'operational', TABLES.get(name)


def export_run(source, destination):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if not source.is_dir():
        raise ValueError(f'Run directory does not exist: {source}')
    if destination.exists() or destination.is_symlink():
        raise ValueError(f'Destination already exists: {destination}')
    destination = destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Run and dataset must be separate directories, without nesting')
    paths = sorted(source.rglob('*'))
    if any(p.is_symlink() for p in paths):
        raise ValueError('Symlinks in a run are not exported; use a self-contained run directory')
    files = [p for p in paths if p.is_file()]
    canonical = {}
    for path in files:
        relative = path.relative_to(source).as_posix()
        name = ALIASES.get(relative, relative)
        if name in canonical:
            raise ValueError(f'Ambiguous canonical artifact: {name}')
        canonical[name] = path
    for name in ('run_status.json', 'effective_config.json'):
        if name not in canonical:
            raise ValueError(f'Missing required artifact: {name}')
    status = json.loads(canonical['run_status.json'].read_text())
    configuration = json.loads(canonical['effective_config.json'].read_text())
    run_id = status.get('run_id')
    if not run_id or status.get('status') not in ('completed', 'incomplete'):
        raise ValueError('run_status must identify run_id and completed/incomplete status')
    required = set(CORE)
    if configuration.get('traffic_sources', {}).get('execution') == 'containers':
        required.add('source_inventory.json')
    missing = sorted(required - canonical.keys())
    if missing and status['status'] == 'completed':
        raise ValueError('Missing required artifacts in completed run: ' + ', '.join(missing))
    if 'source_inventory.json' in canonical:
        inventory = json.loads(canonical['source_inventory.json'].read_text())
        if any(s.get('run_id') not in (None, run_id) for s in inventory):
            raise ValueError('Mixed run IDs in source_inventory.json')
    documentation = schema()
    warnings = []
    for name, key in TABLES.items():
        if name not in canonical:
            continue
        with canonical[name].open(newline='') as stream:
            reader = csv.DictReader(stream)
            expected = [f['name'] for f in documentation['tables'][key]['fields']]
            if reader.fieldnames != expected:
                message = f'Unrecognized original header: {name}'
                if status['status'] == 'completed':
                    raise ValueError(message)
                warnings.append(message)
            for row in reader:
                if row.get('run_id') and row['run_id'] != run_id:
                    raise ValueError(f'Mixed run IDs in {name}')
    execution = dict(status='not_recorded', reason='Execution code/environment was not recorded before this run')
    if 'run_provenance.json' in canonical:
        provenance = json.loads(canonical['run_provenance.json'].read_text())
        if provenance.get('run_id') != run_id or provenance.get('scope') != 'execution_before_invocation':
            raise ValueError('Execution provenance must be bound to this run and captured before invocation')
        execution = dict(status='recorded', path='metadata/run_provenance.json')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.dataset-export-', dir=destination.parent) as temporary:
        staging = Path(temporary) / 'dataset'
        staging.mkdir()
        entries = []
        for path in files:
            relative = path.relative_to(source)
            target, group, role, key = placement(relative)
            output = staging / target
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, output)
            digest = sha256_file(path)
            if sha256_file(output) != digest:
                raise ValueError(f'Artifact changed while exporting: {relative}')
            entry = dict(path=target, origin_path=str(path), group=group, role=role,
                         sha256=digest, bytes=output.stat().st_size)
            if key:
                entry['schema_ref'] = f'schema.json#/tables/{key}'
                entry['schema_recognized'] = not any(str(relative) in w for w in warnings)
            entries.append(entry)
        for name, value in [('schema.json', documentation), ('metadata/export_provenance.json', capture_provenance('export'))]:
            output = staging / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(value, indent=2) + '\n')
            entries.append(dict(path=name, origin_path=None, group='metadata', role='generated',
                                sha256=sha256_file(output), bytes=output.stat().st_size))
        manifest = dict(schema_version=1, run_id=run_id, status=status['status'],
                        configuration='metadata/effective_config.json', run_status='metadata/run_status.json',
                        schema='schema.json', execution_provenance=execution,
                        export_provenance='metadata/export_provenance.json',
                        source_inventory='metadata/source_inventory.json' if 'source_inventory.json' in canonical else None,
                        groups=sorted({e['group'] for e in entries}), files=entries,
                        missing_artifacts=missing, warnings=warnings,
                        structural_status='partial' if missing or warnings else 'complete',
                        validity='not_evaluated; Stage 9 responsibility')
        (staging / 'dataset_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        staging.rename(destination)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('dataset', type=Path)
    args = parser.parse_args()
    try:
        manifest = export_run(args.run, args.dataset)
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Export failed: {exc}\n')
    print(json.dumps(dict(run_id=manifest['run_id'], status=manifest['status'], dataset=str(args.dataset))))


if __name__ == '__main__':
    main()
