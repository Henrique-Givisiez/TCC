"""Phase orchestration; callbacks receive typed observations or scores, never labels."""
import csv
from dataclasses import dataclass
from decimal import Decimal
import json

from .artifacts import component, encoded, open_artifact, provenance, publish
from .contracts import (CalibrationScores, DecisionRecord, DecisionValue, PolicyScore,
                        ScoreValue)
from .inputs import BoundSeries, ContractError, number


@dataclass(frozen=True)
class ScoreRun:
    records: tuple[PolicyScore, ...]
    artifact: object


@dataclass(frozen=True)
class DecisionRun:
    records: tuple[DecisionRecord, ...]
    artifact: object


def feature_key(series):
    return dict(family=series.family, feature=series.feature,
                window_size_seconds=str(series.window_size_seconds),
                feature_schema_version=series.feature_schema_version)


def verify_sources(sources, role=None):
    if not sources or not all(isinstance(s, BoundSeries) for s in sources):
        raise ContractError('Expected bound Stage 10 series')
    for s in sources:
        from .protocol import guard_reference
        guard_reference(s.reference, 'fit' if role == 'baseline' else 'scoring')
        s.verify()
        if role and s.role != role:
            raise ContractError(f'Phase requires {role} sources')
    if len({s.series.run_id for s in sources}) != len(sources):
        raise ContractError('Duplicate run/alias in a phase')
    if any(feature_key(s.series) != feature_key(sources[0].series) for s in sources):
        raise ContractError('Feature/representation/window mismatch')


def missing_check(sources, spec):
    component(spec)
    if spec.missing == 'reject' and any(o.value is None for s in sources for o in s.series.observations):
        raise ContractError('Partial null series refused by explicit missing=reject')


def source_roots(refs):
    return [x['feature_dataset'] for x in refs]


def refs_verify(refs):
    # No labels IO: snapshots contain only manifest/schema/report/selected table.
    from pathlib import Path
    from .inputs import digest, safe_file
    for ref in refs:
        from .protocol import guard_reference
        guard_reference(ref, 'artifact_verification')
        root = Path(ref['feature_dataset'])
        for path, expected in ref['consumed_files_sha256'].items():
            if digest(safe_file(root, path)) != expected:
                raise ContractError('Referenced Stage 10 source changed')


def fit_baseline(sources, fitter, spec, destination, *, fit_start_seconds=None,
                 fit_end_seconds=None, fit_intervals=None):
    sources = tuple(sources)
    verify_sources(sources, 'baseline')
    from .fitting import select_interval
    if fit_intervals is not None and (fit_start_seconds is not None or fit_end_seconds is not None):
        raise ContractError('Use common bounds or per-run fit_intervals, not both')
    if fit_intervals is None:
        if fit_start_seconds is None or fit_end_seconds is None:
            raise ContractError('Explicit fit_start_seconds and fit_end_seconds required')
        fit_intervals = {s.series.run_id: (fit_start_seconds, fit_end_seconds) for s in sources}
    if set(fit_intervals) != {s.series.run_id for s in sources}:
        raise ContractError('fit_intervals must identify every baseline run exactly once')
    selected, selections = [], []
    for source in sources:
        bounds = fit_intervals[source.series.run_id]
        if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
            raise ContractError('Each fit_interval requires start and end')
        if source.reference.get('campaign'):
            from .protocol import FROZEN
            interval = FROZEN['fit_interval']
            if tuple(map(number, bounds)) != (number(interval['start_seconds']), number(interval['end_seconds'])):
                raise ContractError('Campaign fitting must use frozen fit_interval')
        series, record = select_interval(source, *bounds)
        selected.append(series); selections.append(record)
    component(spec)
    if spec.missing == 'reject' and any(o.value is None for s in selected for o in s.observations):
        raise ContractError('Partial null fitting selection refused')
    params = fitter.fit(tuple(selected), json.loads(encoded(dict(spec.config))))
    if not isinstance(params, dict):
        raise ContractError('Fitter must return JSON parameter mapping')
    verify_sources(sources, 'baseline')
    return publish(destination, 'baseline', dict(component=component(spec),
        feature=feature_key(sources[0].series), sources=[s.reference for s in sources],
        parameters=params, fit_selections=selections,
        fitting_contract_version=2, provenance=provenance(fitter)), protected=[s.root for s in sources])


def score_run(source, detector, spec, destination, *, baseline=None):
    verify_sources((source,))
    missing_check((source,), spec)
    model = baseline.read('baseline') if baseline else None
    if model and (model['component'] != component(spec) or model['feature'] != feature_key(source.series)):
        raise ContractError('Baseline detector/config/feature mismatch')
    if model:
        refs_verify(model['sources'])
        if source.role in ('test', 'calibration') and source.series.run_id in {r['run_id'] for r in model['sources']}:
            raise ContractError('Baseline and calibration/test runs must be disjoint')
    state = detector.start_run(json.loads(encoded(model['parameters'])) if model else None,
                               json.loads(encoded(dict(spec.config))))
    records = []
    for obs in source.series.observations:
        out = detector.update(obs, state)
        if not isinstance(out, ScoreValue):
            raise ContractError('Detector must return ScoreValue')
        score = None if out.score is None else number(out.score)
        if (score is None and not out.reason) or (score is not None and out.reason is not None):
            raise ContractError('Unavailable scores require reason; available scores have no reason')
        if obs.value is None and score is not None:
            raise ContractError('Missing observation cannot silently become an observed score')
        at = obs.window_end_seconds if out.available_at_seconds is None else number(out.available_at_seconds)
        if at < obs.window_end_seconds or (records and at < records[-1].available_at_seconds):
            raise ContractError('Score availability precedes evidence closure/order')
        records.append(PolicyScore(obs.run_id, obs.window_index, obs.window_start_seconds,
                                   obs.window_end_seconds, score, score is not None, out.reason, at))
    verify_sources((source,))
    if baseline:
        baseline.read('baseline'); refs_verify(model['sources'])
    columns = ['run_id', 'window_index', 'window_start_seconds', 'window_end_seconds',
               'score', 'score_available', 'unavailable_reason', 'available_at_seconds']
    rows = [score_row(r) for r in records]
    inherited = model['sources'] if model else []
    artifact = publish(destination, 'scores', dict(component=component(spec),
        feature=feature_key(source.series), source=source.reference,
        baseline=baseline.reference if baseline else None,
        baseline_sources=inherited, parameters=model['parameters'] if model else None,
        availability='window closure simulated unless explicitly supplied; no measured compute latency',
        provenance=provenance(detector)), table=('scores.csv', columns, rows),
        protected=[source.root, *source_roots(inherited), *([baseline.root] if baseline else [])])
    return ScoreRun(tuple(records), artifact)


def score_row(r):
    return dict(run_id=r.run_id, window_index=r.window_index,
                window_start_seconds=r.window_start_seconds, window_end_seconds=r.window_end_seconds,
                score='' if r.score is None else r.score, score_available=str(r.score_available).lower(),
                unavailable_reason=r.reason or '', available_at_seconds=r.available_at_seconds)


def validate_score_run(run):
    if not isinstance(run, ScoreRun):
        raise ContractError('Expected ScoreRun')
    m = run.artifact.read('scores')
    refs_verify([m['source'], *m['baseline_sources']])
    if m['baseline']:
        open_artifact(m['baseline'], 'baseline')
    verify_table(run.artifact, 'scores.csv', [score_row(r) for r in run.records])
    return m


def verify_table(artifact, filename, rows):
    from .inputs import safe_file
    with safe_file(artifact.root, filename).open(newline='') as stream:
        actual = list(csv.DictReader(stream))
    expected = [{k: str(v) for k, v in row.items()} for row in rows]
    if actual != expected:
        raise ContractError('In-memory records differ from persisted artifact')


def validate_decision_run(run):
    if not isinstance(run, DecisionRun):
        raise ContractError('Expected DecisionRun')
    m = run.artifact.read('decisions')
    refs_verify([m['source']])
    open_artifact(m['score_artifact'], 'scores')
    validate_calibration(open_artifact(m['calibration'], 'calibration'))
    verify_table(run.artifact, 'decisions.csv', [decision_row(r, m['calibration']['manifest_sha256']) for r in run.records])
    return m


def decision_row(r, policy_hash):
    row = score_row(r.score)
    row.update(decision='' if r.decision is None else str(r.decision).lower(),
               decision_unavailable_reason=r.reason or '',
               decision_available_at_seconds=r.available_at_seconds, policy_reference=policy_hash)
    return row


def validate_calibration(artifact):
    c = artifact.read('calibration')
    refs_verify(c['sources'] + c['baseline_sources'])
    if c['baseline']:
        model = open_artifact(c['baseline'], 'baseline').read('baseline')
        refs_verify(model['sources'])
    for ref in c['score_artifacts']:
        m = open_artifact(ref, 'scores').read('scores')
        refs_verify([m['source'], *m['baseline_sources']])
    return c


def calibrate(score_runs, calibrator, spec, destination):
    runs = tuple(score_runs)
    if not runs:
        raise ContractError('Calibration scores required')
    manifests = [validate_score_run(r) for r in runs]
    from .protocol import guard_reference
    for m in manifests:
        guard_reference(m['source'], 'calibration')
    if any(m['source']['role'] != 'calibration' for m in manifests):
        raise ContractError('Calibration accepts only designated calibration scores, never test')
    ids = [m['source']['run_id'] for m in manifests]
    if len(set(ids)) != len(ids):
        raise ContractError('Duplicate calibration run/alias')
    for m in manifests:
        if any(m[k] != manifests[0][k] for k in ('feature', 'component', 'baseline')):
            raise ContractError('Calibration score model/feature mismatch')
    params = calibrator.calibrate(tuple(CalibrationScores(m['source']['run_id'], r.records)
                                        for r, m in zip(runs, manifests)),
                                  json.loads(encoded(dict(spec.config))))
    if not isinstance(params, dict):
        raise ContractError('Calibrator must return JSON parameter mapping')
    for run in runs:
        validate_score_run(run)
    refs = [m['source'] for m in manifests]
    return publish(destination, 'calibration', dict(component=component(spec),
        score_component=manifests[0]['component'], feature=manifests[0]['feature'],
        baseline=manifests[0]['baseline'], baseline_sources=manifests[0]['baseline_sources'],
        sources=refs, score_artifacts=[r.artifact.reference for r in runs],
        parameters=params, provenance=provenance(calibrator)),
        protected=[*source_roots(refs + manifests[0]['baseline_sources']),
                   *[r.artifact.root for r in runs],
                   *([manifests[0]['baseline']['path']] if manifests[0]['baseline'] else [])])


def decide(score_run_result, policy, spec, calibration, destination):
    m = validate_score_run(score_run_result)
    c = validate_calibration(calibration)
    if (c['component'] != component(spec) or c['score_component'] != m['component']
            or c['feature'] != m['feature'] or c['baseline'] != m['baseline']):
        raise ContractError('Calibration/policy/model mismatch')
    refs_verify(c['sources'] + c['baseline_sources'])
    for ref in c['score_artifacts']:
        open_artifact(ref, 'scores')
    if m['source']['role'] == 'test' and m['source']['run_id'] in {r['run_id'] for r in c['sources'] + c['baseline_sources']}:
        raise ContractError('Test overlaps calibration/baseline run')
    state = policy.start_run(json.loads(encoded(c['parameters'])), json.loads(encoded(dict(spec.config))))
    records = []
    for score in score_run_result.records:
        # Unavailable input cannot be turned into a negative decision by a callback.
        if not score.score_available:
            result = DecisionValue(None, score.reason, score.available_at_seconds)
        else:
            result = policy.decide(score, state)
        if not isinstance(result, DecisionValue) or (result.decision is not None and type(result.decision) is not bool):
            raise ContractError('Policy must return DecisionValue(bool|None)')
        if (result.decision is None and not result.reason) or (result.decision is not None and result.reason is not None):
            raise ContractError('Unavailable decisions require explicit reason')
        at = score.available_at_seconds if result.available_at_seconds is None else number(result.available_at_seconds)
        if at < score.available_at_seconds or (records and at < records[-1].available_at_seconds):
            raise ContractError('Decision availability precedes score/order')
        records.append(DecisionRecord(score, result.decision, result.reason, at))
    validate_score_run(score_run_result); validate_calibration(calibration)
    refs_verify(c['sources'] + c['baseline_sources'])
    rows = [decision_row(r, calibration.manifest_sha256) for r in records]
    columns = [*score_row(records[0].score), 'decision', 'decision_unavailable_reason',
               'decision_available_at_seconds', 'policy_reference']
    a = publish(destination, 'decisions', dict(component=component(spec), feature=m['feature'],
        source=m['source'], score_artifact=score_run_result.artifact.reference,
        baseline=m['baseline'], calibration=calibration.reference,
        parameters=c['parameters'], provenance=provenance(policy)),
        table=('decisions.csv', columns, rows),
        protected=[*source_roots([m['source'], *c['sources'], *c['baseline_sources']]),
                   score_run_result.artifact.root, calibration.root,
                   *([m['baseline']['path']] if m['baseline'] else [])])
    return DecisionRun(tuple(records), a)


def load_scores(reference):
    """Resume calibration/decision from an integrity-bound persisted score artifact."""
    from .inputs import safe_file
    artifact = open_artifact(reference, 'scores')
    m = artifact.read('scores')
    records = []
    with safe_file(artifact.root, 'scores.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            if row['score_available'] not in ('true', 'false'):
                raise ContractError('Invalid score availability')
            score = None if row['score'] == '' else number(row['score'])
            available = row['score_available'] == 'true'
            reason = row['unavailable_reason'] or None
            if available != (score is not None) or (available and reason) or (not available and not reason):
                raise ContractError('Inconsistent persisted score')
            record = PolicyScore(row['run_id'], int(row['window_index']),
                number(row['window_start_seconds']), number(row['window_end_seconds']),
                score, available, reason, number(row['available_at_seconds']))
            if record.available_at_seconds < record.window_end_seconds:
                raise ContractError('Invalid persisted availability')
            records.append(record)
    run = ScoreRun(tuple(records), artifact)
    validate_score_run(run)
    return run


def load_decisions(reference):
    """Resume evaluation from separate persisted score and decision artifacts."""
    from .inputs import safe_file
    artifact = open_artifact(reference, 'decisions')
    m = artifact.read('decisions')
    scores = load_scores(m['score_artifact'])
    with safe_file(artifact.root, 'decisions.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != len(scores.records):
        raise ContractError('Decision/score length mismatch')
    records = []
    for row, score in zip(rows, scores.records):
        if row['decision'] not in ('', 'true', 'false'):
            raise ContractError('Invalid persisted decision')
        value = None if row['decision'] == '' else row['decision'] == 'true'
        reason = row['decision_unavailable_reason'] or None
        if (value is None and not reason) or (value is not None and reason):
            raise ContractError('Invalid persisted decision reason')
        at = number(row['decision_available_at_seconds'])
        if at < score.available_at_seconds or (not score.score_available and value is not None):
            raise ContractError('Invalid persisted decision availability')
        records.append(DecisionRecord(score, value, reason, at))
    run = DecisionRun(tuple(records), artifact)
    validate_decision_run(run)
    return run
