"""Evaluation-only adapter: labels never enter the coupled detector/processor.

An explicit evaluator/plan implements metric semantics. Scientific persisted
evaluation/release remains a future integration; this accepts synthetic inputs.
"""
from ..cusum_freeze_run import validate_run
from decimal import localcontext

from ..detectors._moments import CONTEXT
from ..inputs import ContractError, number
from . import EvaluationInput, EvaluationPlan, WindowTruth


def evaluate_synthetic(run, labels, evaluator, plan):
    if not isinstance(plan, EvaluationPlan) or plan.selection is not None:
        raise ContractError('Explicit synthetic plan without campaign selection required')
    plan.validate()
    validate_run(run)
    labels = tuple(labels)
    if len(labels) != len(run.scores):
        raise ContractError('Evaluation label/decision length mismatch')
    for score, truth in zip(run.scores, labels):
        if type(truth) is not WindowTruth or (
                score.run_id, score.window_index, score.window_start_seconds, score.window_end_seconds) != (
                truth.run_id, truth.window_index, truth.window_start_seconds, truth.window_end_seconds):
            raise ContractError('Evaluation label/decision keys differ')
        fraction = number(truth.attack_event_overlap_fraction)
        with localcontext(CONTEXT):
            seconds = fraction * (truth.window_end_seconds - truth.window_start_seconds)
        if not 0 <= fraction <= 1 or seconds != number(truth.attack_event_overlap_seconds):
            raise ContractError('Invalid overlap fraction')
    # Receives the recorded candidate decision. No threshold or stored state is
    # passed to the evaluator, and it cannot replace h through this interface.
    result = evaluator.evaluate(EvaluationInput(run.scores, run.decisions, labels), plan)
    if not isinstance(result, dict):
        raise ContractError('Evaluator must return result mapping')
    return result
