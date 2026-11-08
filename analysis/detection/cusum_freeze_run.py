"""Coupled freeze-score/decision trajectory; separate from legacy ScoreRun/decide.

Only DEVELOPMENT bound inputs are supported. In-memory series are for synthetic
validation; no scientific calibration or frozen TEST adapter is supplied.
"""
from dataclasses import dataclass
from decimal import Decimal, localcontext
import json

from .artifacts import component, encoded, open_artifact, provenance, publish
from .contracts import ObservedSeries
from .detectors._standardized import FEATURES
from .detectors._moments import CONTEXT
from .detectors.cusum_freeze import CUSUMFreeze
from .detectors.zscore import zscore_spec
from .inputs import ContractError
from .pipeline import feature_key, refs_verify, verify_sources


@dataclass(frozen=True)
class FreezeRun:
    # Canonical JSON snapshots prevent external mutation of config/model mappings.
    specification_json: str
    baseline_parameters_json: str
    series: ObservedSeries
    transitions: tuple

    @property
    def scores(self):
        return tuple(t.score for t in self.transitions)

    @property
    def decisions(self):
        return tuple(t.decision for t in self.transitions)


def process_series(series, *, h, baseline_parameters):
    if type(series) is not ObservedSeries or (series.family, series.feature) not in FEATURES:
        raise ContractError('Expected observed scalar series on one of the five supported features')
    if (type(series.feature_schema_version) is not int or series.feature_schema_version not in (1, 2) or not isinstance(series.observations, tuple)
            or type(series.window_size_seconds) is not Decimal
            or not series.window_size_seconds.is_finite() or series.window_size_seconds <= 0):
        raise ContractError('Invalid series schema/window')
    detector = CUSUMFreeze(h=h)
    parameters = encoded(baseline_parameters)
    state = detector.start_run(json.loads(parameters))
    transitions = []
    for observation in series.observations:
        with localcontext(CONTEXT):
            width = observation.window_end_seconds - observation.window_start_seconds
        if observation.run_id != series.run_id or width != series.window_size_seconds:
            raise ContractError('Observation differs from series run/window')
        transition = detector.step(observation, state)
        transitions.append(transition)
        state = transition.next_state
    return FreezeRun(encoded(component(detector.spec())), parameters, series, tuple(transitions))


def validate_run(run):
    if type(run) is not FreezeRun:
        raise ContractError('Expected coupled FreezeRun, not independently thresholded scores')
    specification = json.loads(run.specification_json)
    expected = process_series(run.series, h=specification['config']['h'],
                              baseline_parameters=json.loads(run.baseline_parameters_json))
    if run != expected:
        raise ContractError('Coupled trajectory/config/decision mismatch; changing h requires reprocessing')
    return specification


def transition_rows(run):
    validate_run(run)
    return [dict(window_index=t.observation.window_index,
        window_start_seconds=t.observation.window_start_seconds,
        window_end_seconds=t.observation.window_end_seconds,
        observation=t.observation.value, previous_state=t.previous_state,
        residual=t.residual, candidate=t.candidate, score=t.score.score,
        decision=t.decision.decision, update_accepted=t.update_accepted,
        posterior_state=t.posterior_state, unavailable_reason=t.score.reason,
        available_at_seconds=t.decision.available_at_seconds) for t in run.transitions]


def process_development_run(source, *, baseline, h, destination):
    # Check role before any source/model data read. Existing TEST guards stay intact.
    if source.role != 'development' or source.reference.get('campaign'):
        raise ContractError('Freeze integration supports noncampaign DEVELOPMENT only')
    verify_sources((source,))
    model = baseline.read('baseline')
    if model['component'] != component(zscore_spec()) or model['feature'] != feature_key(source.series):
        raise ContractError('Frozen normalization baseline identity/feature mismatch')
    if source.series.run_id in {ref['run_id'] for ref in model['sources']}:
        raise ContractError('Normalization and target runs must be disjoint')
    refs_verify(model['sources'])
    run = process_series(source.series, h=h, baseline_parameters=model['parameters'])
    verify_sources((source,)); baseline.read('baseline'); refs_verify(model['sources'])
    artifact = publish(destination, 'cusum-freeze-run', dict(
        component=validate_run(run), feature=feature_key(source.series),
        source=source.reference, baseline=baseline.reference,
        baseline_sources=model['sources'], parameters=json.loads(run.baseline_parameters_json),
        coupling='Candidate, decision and state share h; legacy decide/load_scores are not supported',
        threshold_origin='explicit DEVELOPMENT validation input; not scientifically calibrated',
        transitions=transition_rows(run), provenance=provenance(CUSUMFreeze(h=h))),
        protected=[source.root, baseline.root, *[ref['feature_dataset'] for ref in model['sources']]])
    return run, artifact


def load_development_run(artifact):
    """Verify provenance-bound observations and replay the coupled trajectory."""
    from .inputs import load_series
    manifest = artifact.read('cusum-freeze-run')
    reference = manifest['source']
    if reference['role'] != 'development' or reference.get('campaign'):
        raise ContractError('Only noncampaign DEVELOPMENT artifacts supported')
    refs_verify([reference, *manifest['baseline_sources']])
    f = manifest['feature']
    source = load_series(reference['feature_dataset'], run_id=reference['run_id'],
        family=f['family'], feature=f['feature'], window_size_seconds=f['window_size_seconds'],
        feature_schema_version=f['feature_schema_version'], role='development')
    model = open_artifact(manifest['baseline'], 'baseline').read('baseline')
    if (source.reference != reference or model['component'] != component(zscore_spec())
            or model['feature'] != f or model['sources'] != manifest['baseline_sources']
            or model['parameters'] != manifest['parameters']
            or reference['run_id'] in {ref['run_id'] for ref in model['sources']}):
        raise ContractError('Persisted source/normalization binding mismatch')
    # Reprocess observations against the original normalization and h. No labels IO.
    run = process_series(source.series, h=manifest['component']['config']['h'], baseline_parameters=model['parameters'])
    if validate_run(run) != manifest['component'] or json.loads(encoded(transition_rows(run))) != manifest['transitions']:
        raise ContractError('Persisted coupled trajectory differs from replay')
    return run
