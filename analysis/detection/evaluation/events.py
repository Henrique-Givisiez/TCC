"""Verified original Stage 8 event truth. Only evaluators import this module."""
import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from ..inputs import ContractError, checked_output, digest, number, read_json, safe_file
from ..pipeline import refs_verify


@dataclass(frozen=True)
class EventTruth:
    run_id: str
    event_id: str
    planned_start_seconds: Decimal | None
    planned_end_seconds: Decimal | None
    actual_start_seconds: Decimal
    actual_end_seconds: Decimal
    drained_end_seconds: Decimal | None
    profile: str


@dataclass(frozen=True)
class VerifiedEvents:
    events: tuple[EventTruth, ...]
    reference: dict
    feature_dataset: Path
    stage8_dataset: Path
    source_reference: dict

    def verify(self):
        current = load_event_truth(self.feature_dataset, self.source_reference,
                                   stage8_dataset=self.stage8_dataset)
        if current.reference != self.reference or current.events != self.events:
            raise ContractError('Event truth changed')


def load_event_truth(feature_dataset, source_reference, *, stage8_dataset):
    """Resolve the content-addressed Stage 8 reference using a candidate ROOT.

    Stage 10 stores no absolute Stage 8 path. The root is a locator only: both
    manifests must bind its exact bytes, run, clocks and event-file hash/size.
    Arbitrary CSV paths are never accepted.
    """
    root, original = Path(feature_dataset).resolve(), Path(stage8_dataset).resolve()
    if root != Path(source_reference['feature_dataset']).resolve():
        raise ContractError('Event feature dataset differs from score source')
    refs_verify([source_reference])
    fm_path = safe_file(root, 'feature_manifest.json')
    if digest(fm_path) != source_reference['feature_manifest_sha256']:
        raise ContractError('Feature manifest changed')
    fm = read_json(fm_path)
    mp = safe_file(original, 'dataset_manifest.json')
    mh = digest(mp)
    m = read_json(mp)
    run_id = source_reference['run_id']
    if (mh != fm['dataset_manifest_sha256'] or mh != source_reference['dataset_manifest_sha256']
            or m.get('run_id') != run_id or fm['source_run_id'] != run_id
            or m.get('schema_version') != 1 or m.get('status') != 'completed'):
        raise ContractError('Stage 8 manifest/run binding mismatch')
    report_path = checked_output(root, fm, fm['stage9_validation_report']['path'])
    report = read_json(report_path)
    if (digest(report_path) != fm['stage9_validation_report']['sha256']
            or report.get('dataset_manifest_sha256') != mh or report.get('run_id') != run_id
            or report.get('analysis_eligible') is not True or report.get('dataset_valid') is not True):
        raise ContractError('Stage 9 evidence mismatch')

    def linked(relative):
        a = [x for x in m['files'] if x['path'] == relative]
        b = [x for x in fm['input_files'] if x['path'] == relative]
        if len(a) != 1 or len(b) != 1 or any(a[0][k] != b[0][k] for k in ('sha256','bytes')):
            raise ContractError('Original input reference mismatch')
        path = safe_file(original, relative)
        if digest(path) != a[0]['sha256'] or path.stat().st_size != a[0]['bytes']:
            raise ContractError('Original input hash/size mismatch')
        return path, a[0]

    status_path, status_ref = linked(m['run_status'])
    status = read_json(status_path)
    if status.get('run_id') != run_id or status.get('status') != 'completed':
        raise ContractError('Original clock/run mismatch')
    for key, value in fm['window']['anchors'].items():
        if value is None or number(status[key]) != number(value):
            raise ContractError('Stage 8/10 clock anchors mismatch')
    path, entry = linked('raw/attacks/attack_events.csv')
    records = []
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'run_id','event_id','scheduled_start_seconds','scheduled_end_seconds',
                    'actual_start_seconds','actual_end_seconds','drained_end_seconds','profile',
                    'experiment_start_timestamp','experiment_start_monotonic'}
        if not required.issubset(reader.fieldnames or ()):
            raise ContractError('Original event columns missing')
        for row in reader:
            if None in row or any(row.get(k) is None for k in required):
                raise ContractError('Malformed original event')
            if row['run_id'] != run_id or not row['event_id']:
                raise ContractError('Event run/identity mismatch')
            for key in ('experiment_start_timestamp','experiment_start_monotonic'):
                if number(row[key]) != number(status[key]):
                    raise ContractError('Event clock mismatch')
            val = lambda k: None if row[k] == '' else number(row[k])
            start, end, drained = (val(k) for k in ('actual_start_seconds','actual_end_seconds','drained_end_seconds'))
            if start is None or end is None or start < 0 or end < start or (drained is not None and drained < start):
                raise ContractError('Effective event boundaries unavailable/invalid')
            records.append(EventTruth(run_id, row['event_id'], val('scheduled_start_seconds'),
                val('scheduled_end_seconds'), start, end, drained, row['profile']))
    if len({e.event_id for e in records}) != len(records):
        raise ContractError('Duplicate original event identity')
    if digest(path) != entry['sha256'] or digest(mp) != mh:
        raise ContractError('Original truth changed while loading')
    refs_verify([source_reference])
    reference = dict(run_id=run_id, feature_manifest_sha256=digest(fm_path),
                     dataset_manifest_sha256=mh, events_path=entry['path'],
                     events_sha256=entry['sha256'], events_bytes=entry['bytes'],
                     stage9_report_sha256=digest(report_path), run_status_sha256=status_ref['sha256'],
                     stage8_dataset=str(original), time_basis='elapsed_since_verified_experiment_start')
    return VerifiedEvents(tuple(records), reference, root, original, dict(source_reference))


def evaluate_events(decisions, truth, *, policy, selection=None):
    """Explicit V1 (historical deadline) or V2 (observation overlap) attribution.

    An alarm whose window ends at/before the causal start is not a detection,
    even if computationally delayed until after the start. No persistence rule.
    """
    from . import EventResult
    from ..pipeline import validate_decision_run
    from ..protocol import EVENT_POLICY_V2, load_protocol
    legacy = policy == 'global_overlap_and_availability_within_event_v1'
    if not legacy and policy != EVENT_POLICY_V2:
        raise ContractError('Explicit supported event attribution policy required')
    if not isinstance(truth, VerifiedEvents):
        raise ContractError('Verified original event truth required')
    manifest = validate_decision_run(decisions)
    if manifest['source'] != truth.source_reference:
        raise ContractError('Decisions and event truth refer to different sources')
    from ..horizons import select_for_evaluation
    eligible_records, _ = select_for_evaluation(decisions.records, manifest['source'], selection)
    campaign = manifest['source'].get('campaign')
    if campaign:
        ref = campaign['protocol']
        doc, _ = load_protocol(ref['path'], expected_hash=ref['protocol_hash'])
        if doc['frozen']['event_truth']['policy'] != policy:
            raise ContractError('Event policy differs from campaign protocol')
    truth.verify()
    results = []
    for event in truth.events:
        times = [r.available_at_seconds for r in eligible_records
                 if r.decision is True and r.score.score_available
                 and r.score.window_start_seconds < event.actual_end_seconds
                 and r.score.window_end_seconds > event.actual_start_seconds
                 and event.actual_start_seconds < event.actual_end_seconds
                 and r.available_at_seconds >= event.actual_start_seconds
                 and (not legacy or r.available_at_seconds <= event.actual_end_seconds)]
        first = min(times) if times else None
        results.append(EventResult(event.event_id, first is not None, first,
            None if first is None else first-event.actual_start_seconds, event.actual_end_seconds if legacy else None))
    truth.verify()
    return tuple(results)
