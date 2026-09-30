"""Preserve per-run ground truth alongside metrics without changing experiment grids."""
import csv
import json
from pathlib import Path
import shutil


def move_result(source, destination):
    result = shutil.move(source, destination)
    if Path(source).name != 'simulation_metrics.csv':
        return result
    destination = Path(destination)
    with destination.open(newline='') as f:
        reader = csv.DictReader(f)
        first = next(reader, {})
        run_id = first.get('run_id')
        current_schema = 'run_id' in (reader.fieldnames or [])
    if current_schema and not run_id:
        status = Path(source).parent / 'run_status.json'
        run_id = json.loads(status.read_text())['run_id']
    # Historical metrics never acquire a newly fabricated association.
    if not run_id:
        return result
    suffix = destination.stem[8:] if destination.stem.startswith('metrics_') else destination.stem
    for name in ['attack_events.csv', 'request_log.csv', 'run_status.json']:
        artifact = Path(source).parent / name
        if not artifact.exists():
            raise FileNotFoundError(f'ground truth artifact missing: {artifact}')
        if artifact.suffix == '.json':
            data = json.loads(artifact.read_text())
            if data['run_id'] != run_id:
                raise ValueError(f'run_id mismatch: {artifact}')
        else:
            with artifact.open(newline='') as f:
                for row in csv.DictReader(f):
                    if row['run_id'] != run_id:
                        raise ValueError(f'run_id mismatch: {artifact}')
        target = destination.parent / f'{artifact.stem}_{suffix}{artifact.suffix}'
        shutil.move(artifact, target)
    return result
