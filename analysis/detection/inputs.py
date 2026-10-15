"""Read-only Stage 10 scalar reader. This module never opens ground truth."""
import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path, PurePosixPath

from experiments.feature_schema import FEATURES, KEYS, feature_schema
from .contracts import Observation, ObservedSeries


class ContractError(ValueError):
    pass


def number(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ContractError('Invalid numeric value') from exc
    if not result.is_finite():
        raise ContractError('Nonfinite numeric value')
    return result


def grid_edges(width, index):
    # Exact multiplication independent of the caller's global Decimal context.
    with localcontext() as context:
        context.prec = max(50, len(width.as_tuple().digits) + len(str(index + 1)) + 2)
        return width * index, width * (index + 1)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ContractError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    def reject(value):
        raise ContractError(f'Invalid JSON number: {value}')
    return json.loads(Path(path).read_text(), object_pairs_hook=unique, parse_constant=reject)


def safe_file(root, relative):
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ContractError('Invalid relative path')
    pure = PurePosixPath(relative)
    if pure.is_absolute() or '..' in pure.parts or pure.as_posix() != relative:
        raise ContractError('Unsafe input path')
    p = root / relative
    if root not in p.resolve().parents:
        raise ContractError('Input escapes dataset')
    for parent in (p, *p.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ContractError('Symlink input refused')
    if not p.is_file():
        raise ContractError(f'Missing input: {relative}')
    return p


def checked_output(root, manifest, relative):
    entries = [x for x in manifest['outputs'] if x['path'] == relative]
    if len(entries) != 1:
        raise ContractError(f'Missing/duplicate manifest entry: {relative}')
    p = safe_file(root, relative)
    if digest(p) != entries[0]['sha256'] or p.stat().st_size != entries[0]['bytes']:
        raise ContractError(f'Input hash/size mismatch: {relative}')
    return p


@dataclass(frozen=True)
class BoundSeries:
    """Orchestration envelope. Callbacks receive ONLY .series, never this object."""
    series: ObservedSeries
    role: str
    root: Path
    # Snapshot is immutable and checked before/after every phase.
    snapshot: tuple[tuple[str, str], ...]
    reference_json: str

    @property
    def reference(self):
        return json.loads(self.reference_json)

    def verify(self):
        for relative, expected in self.snapshot:
            if digest(safe_file(self.root, relative)) != expected:
                raise ContractError(f'Stage 10 input changed: {relative}')


def load_series(dataset, *, run_id, family, feature, window_size_seconds,
                feature_schema_version, role):
    """Explicit selection/identity; no glob of numeric columns and no labels IO."""
    if role not in ('baseline', 'calibration', 'test', 'development'):
        raise ContractError('An explicit phase role is required')
    if family not in FEATURES or feature not in FEATURES[family]:
        raise ContractError('Not an observable feature (labels/keys/unknown refused)')
    raw_root = Path(dataset).absolute()
    if raw_root.is_symlink():
        raise ContractError('Symlink dataset refused')
    root = raw_root.resolve()
    mp = safe_file(root, 'feature_manifest.json')
    before = digest(mp)
    m = read_json(mp)
    try:
        if feature_schema_version != 1 or m['feature_schema_version'] != 1:
            raise ContractError('Unsupported feature schema')
        if m['source_run_id'] != run_id:
            raise ContractError('Run ID mismatch')
        width = number(window_size_seconds)
        if width <= 0 or number(m['window']['size_seconds']) != width:
            raise ContractError('Window size mismatch')
        schema_path = checked_output(root, m, 'feature_schema.json')
        schema = read_json(schema_path)
        if schema != feature_schema():
            raise ContractError('Schema differs from supported Stage 10 v1 contract')
        if m['detector_columns'] != {f: FEATURES[f] for f in FEATURES}:
            raise ContractError('Manifest observable columns mismatch')
        table = schema['tables'][family]
        field = next(x for x in table['fields'] if x['name'] == feature)
        if field['role'] != 'feature' or feature not in table['detector_columns']:
            raise ContractError('Feature is not observable')
        report_path = checked_output(root, m, 'evidence/stage9_validation_report.json')
        report = read_json(report_path)
        binding = m['stage9_validation_report']
        if (binding['path'] != 'evidence/stage9_validation_report.json'
                or binding['sha256'] != digest(report_path)
                or binding['analysis_eligible'] is not True
                or report['analysis_eligible'] is not True or report['dataset_valid'] is not True
                or report['run_id'] != run_id
                or report['dataset_manifest_sha256'] != m['dataset_manifest_sha256']):
            raise ContractError('Stage 9 binding/eligibility mismatch')
        if family == 'network' and m['network_direction']['supported'] is not True:
            raise ContractError('feature_unavailable: network direction unsupported')
        values_path = checked_output(root, m, table['path'])
        rows = []
        with values_path.open(newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != [f['name'] for f in table['fields']]:
                raise ContractError('CSV columns mismatch')
            for index, row in enumerate(reader):
                if None in row or any(v is None for v in row.values()):
                    raise ContractError('Malformed CSV row')
                start, end = number(row[KEYS[2]]), number(row[KEYS[3]])
                expected_start, expected_end = grid_edges(width, index)
                if (row['run_id'] != run_id or row['window_index'] != str(index)
                        or start != expected_start or end != expected_end):
                    raise ContractError('Irregular grid/run identity')
                value = None if row[feature] == '' else number(row[feature])
                if value is None and not field['nullable']:
                    raise ContractError('Null in nonnullable feature')
                if value is not None and field['type'] == 'integer' and value != value.to_integral_value():
                    raise ContractError('Invalid feature domain')
                rows.append(Observation(run_id, index, start, end, value))
        if len(rows) != m['window']['windows'] or not rows:
            raise ContractError('Window count mismatch')
        if not any(r.value is not None for r in rows):
            raise ContractError('feature_unavailable: no observed values')
        watched = ('feature_manifest.json', 'feature_schema.json',
                   'evidence/stage9_validation_report.json', table['path'])
        snap = tuple((x, digest(safe_file(root, x))) for x in watched)
        if digest(mp) != before:
            raise ContractError('Manifest changed during read')
        # Recheck selected outputs after parsing; labels are intentionally NOT hashed here.
        for relative in watched[1:]:
            checked_output(root, m, relative)
        ref = dict(feature_dataset=str(root), run_id=run_id, family=family, feature=feature,
                   feature_schema_version=1, window_size_seconds=str(width),
                   feature_manifest_sha256=before, dataset_manifest_sha256=m['dataset_manifest_sha256'],
                   consumed_files_sha256=dict(snap), role=role)
        bound = BoundSeries(ObservedSeries(run_id, family, feature, width, 1, tuple(rows)),
                            role, root, snap, json.dumps(ref, sort_keys=True))
        bound.verify()
        return bound
    except (KeyError, TypeError, StopIteration) as exc:
        raise ContractError('Malformed feature manifest/schema/report') from exc
