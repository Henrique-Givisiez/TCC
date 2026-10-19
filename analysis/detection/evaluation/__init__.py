"""The only Stage 11 module permitted to open labels.csv.

No scientific overlap rule or metric is implemented here. Evaluators are callbacks
which must interpret an explicit plan; original event identities/boundaries use the verified Stage 8 binding,
never inference from window labels.
"""
import csv
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Mapping, Protocol

from ..artifacts import component, provenance, publish
from ..contracts import DecisionRecord, PolicyScore
from ..inputs import ContractError, checked_output, number, read_json, safe_file, digest, grid_edges
from ..pipeline import DecisionRun, ScoreRun, refs_verify, validate_score_run, validate_decision_run
from ..horizons import EvaluationSelection, select_for_evaluation


@dataclass(frozen=True)
class EvaluationPlan:
    overlap_policy: str
    overlap_config: Mapping
    # No default event attribution, persistence, or delay rule.
    availability_policy: str
    selection: EvaluationSelection | None = None

    def validate(self):
        if not self.overlap_policy.strip() or not self.availability_policy.strip():
            raise ContractError('Explicit overlap and availability policies required')
        if self.selection is not None:
            if not isinstance(self.selection, EvaluationSelection):
                raise ContractError('Explicit EvaluationSelection required')
            self.selection.bounds()


@dataclass(frozen=True)
class WindowTruth:
    run_id: str
    window_index: int
    window_start_seconds: Decimal
    window_end_seconds: Decimal
    attack_event_overlap_seconds: Decimal
    attack_event_overlap_fraction: Decimal


@dataclass(frozen=True)
class WindowResult:
    """Future result contract, not a metric implementation; None means undefined."""
    tp: int
    fp: int
    tn: int
    fn: int
    precision: Decimal | None
    recall: Decimal | None
    f1: Decimal | None
    fpr: Decimal | None



from .events import EventTruth, VerifiedEvents, load_event_truth, evaluate_events


@dataclass(frozen=True)
class EventResult:
    event_id: str
    detected: bool
    first_detection_available_at_seconds: Decimal | None
    detection_delay_seconds: Decimal | None
    # For misses: no fabricated zero delay.
    censored_at_seconds: Decimal | None


@dataclass(frozen=True)
class EvaluationInput:
    scores: tuple[PolicyScore, ...]
    decisions: tuple[DecisionRecord, ...]
    labels: tuple[WindowTruth, ...]
    # Stage 10 v1 labels contain union overlap, not complete event identities.
    events: tuple[EventTruth, ...] | None = None


class Evaluator(Protocol):
    def evaluate(self, inputs: EvaluationInput, plan: EvaluationPlan) -> Mapping:
        """Future output: TP/FP/TN/FN, Precision/Recall/F1/FPR and event results.

        Must state coverage/denominators/undefined values, and must not claim
        event metrics while inputs.events is None. There is no built-in metric.
        """
        ...


def load_window_truth(dataset, source_reference):
    """Read labels only here, bound to the exact manifest used in scoring."""
    from pathlib import Path
    root = Path(dataset).resolve()
    if root != Path(source_reference['feature_dataset']).resolve():
        raise ContractError('Evaluation dataset differs from score source')
    refs_verify([source_reference])
    m = read_json(safe_file(root, 'feature_manifest.json'))
    p = checked_output(root, m, 'timeseries/labels.csv')
    before = digest(p)
    schema = read_json(safe_file(root, 'feature_schema.json'))
    table = schema['tables']['labels']
    records = []
    width = number(source_reference['window_size_seconds'])
    with p.open(newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != [f['name'] for f in table['fields']]:
            raise ContractError('Label columns mismatch')
        for i, row in enumerate(reader):
            if None in row or any(v is None for v in row.values()):
                raise ContractError('Malformed label row')
            start, end = number(row['window_start_seconds']), number(row['window_end_seconds'])
            overlap, fraction = number(row['attack_event_overlap_seconds']), number(row['attack_event_overlap_fraction'])
            with localcontext() as context:
                context.prec = m['window']['decimal_boundary_precision']
                expected_fraction = overlap / width
            expected_start, expected_end = grid_edges(width, i)
            if (row['run_id'] != source_reference['run_id'] or row['window_index'] != str(i)
                    or start != expected_start or end != expected_end
                    or not 0 <= fraction <= 1 or fraction != expected_fraction):
                raise ContractError('Label identity/grid/overlap mismatch')
            records.append(WindowTruth(row['run_id'], i, start, end, overlap, fraction))
    if len(records) != m['window']['windows'] or digest(p) != before:
        raise ContractError('Label count or integrity changed')
    refs_verify([source_reference])
    return tuple(records), dict(path='timeseries/labels.csv', sha256=before)


def evaluate(scores, decisions, dataset, evaluator, spec, plan, destination, *,
             event_truth=None, event_policy=None):
    if not isinstance(plan, EvaluationPlan):
        raise ContractError('Explicit EvaluationPlan required')
    plan.validate()
    m = validate_score_run(scores)
    if not isinstance(decisions, DecisionRun):
        raise ContractError('Expected DecisionRun')
    d = validate_decision_run(decisions)
    if d['score_artifact'] != scores.artifact.reference:
        raise ContractError('Decisions belong to different scores')
    selected_scores, temporal_selection = select_for_evaluation(scores.records, m['source'], plan.selection)
    selected_decisions, _ = select_for_evaluation(decisions.records, m['source'], plan.selection)
    labels, truth_ref = load_window_truth(dataset, m['source'])
    if len(labels) != len(scores.records) or len(labels) != len(decisions.records):
        raise ContractError('Evaluation alignment mismatch')
    for score, decision, truth in zip(scores.records, decisions.records, labels):
        if (decision.score != score or score.run_id != truth.run_id
                or score.window_index != truth.window_index
                or score.window_start_seconds != truth.window_start_seconds
                or score.window_end_seconds != truth.window_end_seconds):
            raise ContractError('Evaluation keys differ')
    selected_labels, _ = select_for_evaluation(labels, m['source'], plan.selection)
    event_results = None
    if event_truth is not None:
        event_results = evaluate_events(decisions, event_truth, policy=event_policy, selection=plan.selection)
    elif event_policy is not None:
        raise ContractError('Event policy requires verified event truth')
    result = evaluator.evaluate(EvaluationInput(selected_scores, selected_decisions, selected_labels,
                               None if event_truth is None else event_truth.events), plan)
    if event_truth is not None:
        event_truth.verify()
    if not isinstance(result, dict):
        raise ContractError('Evaluator must return JSON result mapping')
    validate_score_run(scores); validate_decision_run(decisions)
    _, after = load_window_truth(dataset, m['source'])
    if truth_ref != after:
        raise ContractError('Truth changed during evaluation')
    return publish(destination, 'evaluation', dict(component=component(spec),
        plan=dict(overlap_policy=plan.overlap_policy, overlap_config=dict(plan.overlap_config),
                  availability_policy=plan.availability_policy,
                  **({} if plan.selection is None else {'selection': dict(region=plan.selection.region, version=1)})),
        source=m['source'], temporal_selection=temporal_selection, scores=scores.artifact.reference, decisions=decisions.artifact.reference,
        truth=truth_ref, event_truth=None if event_truth is None else event_truth.reference,
        event_policy=event_policy, event_results=None if event_results is None else [
            dict(event_id=r.event_id, event_detected=r.detected,
                 first_detection_available_at_seconds=r.first_detection_available_at_seconds,
                 detection_delay_seconds=r.detection_delay_seconds,
                 censored_at_seconds=r.censored_at_seconds) for r in event_results],
        results=result, provenance=provenance(evaluator)),
        protected=[dataset, scores.artifact.root, decisions.artifact.root])


def pure_window_groups(labels):
    """Primary policy: 0 benign, 1 attack, partial overlap separate; no rounding.

    Callers retain the original continuous overlap for complementary analyses.
    This helper defines groups, not metrics or any detector decision threshold.
    """
    groups = {'benign': [], 'attack': [], 'boundary': []}
    for row in labels:
        fraction = row.attack_event_overlap_fraction
        if not 0 <= fraction <= 1:
            raise ContractError('Invalid ground-truth overlap')
        group = 'benign' if fraction == 0 else 'attack' if fraction == 1 else 'boundary'
        groups[group].append(row)
    return {key: tuple(values) for key, values in groups.items()}
